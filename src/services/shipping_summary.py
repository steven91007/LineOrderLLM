"""
Shipping statistics: aggregate one day's orders into a packing list.

Output looks like:

    20A 家庭號 1箱*2個地址
    20A 禮盒 1盒*2個地址
    18A 禮盒 1盒*1個地址

「個地址」 ("addresses") counts **order rows**, not distinct addresses -- each row
is one shipment, and two orders to the same address need two packages, so
merging them would under-stock.

The source is the dropdown option strings in sheet columns I/J (e.g.
`20A 一盒 $1,150`, `18A 1箱 $1,850`) rather than free text, so they can be parsed
reliably with rules. Gift box (禮盒) quantities are written in Chinese numerals
(一盒, 兩盒) while family packs (家庭號) use Arabic numerals (1箱, 2箱); the
inconsistency comes from the form itself, and both are converted to Arabic
numerals for display here.
"""

import re
from collections import OrderedDict
from typing import Any, Dict, List, NamedTuple

# Positions of the item columns in the master sheet
GIFTBOX_INDEX = 8   # Column I: (禮盒) 欲訂購的品項 (gift box items)
FAMILY_INDEX = 9    # Column J: (家庭號) 欲訂購的品項 (family pack items)

GIFTBOX_LABEL = '禮盒'
FAMILY_LABEL = '家庭號'

# The "spec + quantity + unit" at the start of an option string, e.g. `20A 一盒 $1,150`, `18A 1箱 $1,850`
_OPTION_PATTERN = re.compile(r'^\s*(\d+\s*[A-Za-z])\s*([一二兩三四五六七八九十\d]+)\s*([盒箱])')

# 「雙雙對對」 has no spec and is always written to the family pack (家庭號) column, formatted like `雙雙對對 一組 $3,400`
SHUANGSHUANG_LABEL = '雙雙對對'
_SHUANGSHUANG_PATTERN = re.compile(
    rf'^\s*{SHUANGSHUANG_LABEL}\s*([一二兩三四五六七八九十\d]+)\s*組'
)

# Before the form option went live, staff typed 「雙雙對對*數量」 (item*quantity) by hand; recognize that too
_SHUANGSHUANG_SHORTHAND_PATTERN = re.compile(
    rf'^\s*{SHUANGSHUANG_LABEL}\s*\*\s*(\d+)\s*$'
)

_CHINESE_TO_INT = {
    '一': 1, '二': 2, '兩': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
}


class SummaryLine(NamedTuple):
    """Statistics for one (spec + category + per-order quantity) combination."""
    category: str      # 禮盒 (gift box) / 家庭號 (family pack)
    spec: str          # 18A / 20A
    quantity: int      # Boxes (盒) or cases (箱) per order
    unit: str          # 盒 / 箱 (unit)
    addresses: int     # Number of orders (number of shipping addresses)
    total_units: int   # quantity * addresses: total boxes/cases to prepare

    @property
    def text(self) -> str:
        """`20A 家庭號 1箱*2個地址` (the spec is omitted for spec-less items such as 雙雙對對)."""
        prefix = f'{self.spec} {self.category}' if self.spec else self.category
        return f'{prefix} {self.quantity}{self.unit}*{self.addresses}個地址'


def summarize(rows: List[List[Any]]) -> Dict[str, Any]:
    """Compute statistics for a batch of order rows.

    Args:
        rows: Order data rows (excluding the header), in master-sheet column order

    Returns:
        {'lines': [SummaryLine, ...], 'order_count': int,
         'totals': {'盒': n, '箱': n}, 'unparsed': [raw string, ...]}
    """
    counts: Dict[tuple, int] = OrderedDict()
    unparsed: List[str] = []
    order_count = 0

    for row in rows:
        if not any(str(cell).strip() for cell in row):
            continue
        order_count += 1

        for index, category in ((GIFTBOX_INDEX, GIFTBOX_LABEL),
                                (FAMILY_INDEX, FAMILY_LABEL)):
            raw = str(row[index]).strip() if len(row) > index else ''
            if not raw:
                continue

            parsed = _parse_option(raw)
            if not parsed:
                # Record unparseable values for reporting rather than silently dropping them -- a missed count is harder to notice than a wrong one
                unparsed.append(raw)
                continue

            category_override, spec, quantity, unit = parsed
            line_category = category_override or category
            key = (line_category, spec, quantity, unit)
            counts[key] = counts.get(key, 0) + 1

    lines = [
        SummaryLine(category=category, spec=spec, quantity=quantity, unit=unit,
                    addresses=addresses, total_units=quantity * addresses)
        for (category, spec, quantity, unit), addresses in counts.items()
    ]
    # Sort: gift boxes first (matching the sheet column order), then by spec and per-order quantity
    lines.sort(key=lambda line: (line.category != GIFTBOX_LABEL, line.spec, line.quantity))

    totals: Dict[str, int] = OrderedDict()
    for line in lines:
        totals[line.unit] = totals.get(line.unit, 0) + line.total_units

    return {
        'lines': lines,
        'order_count': order_count,
        'totals': totals,
        'unparsed': unparsed,
    }


def summary_rows(summary: Dict[str, Any], title: str) -> List[List[Any]]:
    """Turn the statistics into rows to write to the sheet (single-column text, placed below the order rows)."""
    rows: List[List[Any]] = [[], [f'📦 {title} 出貨統計']]
    rows.extend([line.text] for line in summary['lines'])

    if summary['unparsed']:
        rows.append([f'⚠️ 有 {len(summary["unparsed"])} 筆品項無法辨識，未列入統計：'
                     + '、'.join(sorted(set(summary['unparsed'])))])

    rows.append([_totals_text(summary)])
    return rows


def _totals_text(summary: Dict[str, Any]) -> str:
    """The closing line, like `合計 4 筆訂單／禮盒 3 盒／家庭號 2 箱`."""
    parts = [f'合計 {summary["order_count"]} 筆訂單']
    parts.extend(f'{count} {unit}' for unit, count in summary['totals'].items())
    return '／'.join(parts)


def _parse_option(option: str):
    """Split an option string into (category override or None, spec, quantity, unit); return None if unreadable."""
    shuangshuang_match = _SHUANGSHUANG_PATTERN.match(option)
    if shuangshuang_match:
        quantity = _to_int(shuangshuang_match.group(1))
        if quantity is None:
            return None
        return SHUANGSHUANG_LABEL, '', quantity, '組'

    shorthand_match = _SHUANGSHUANG_SHORTHAND_PATTERN.match(option)
    if shorthand_match:
        return SHUANGSHUANG_LABEL, '', int(shorthand_match.group(1)), '組'

    match = _OPTION_PATTERN.match(option)
    if not match:
        return None

    spec = match.group(1).replace(' ', '').upper()
    quantity = _to_int(match.group(2))
    if quantity is None:
        return None

    return None, spec, quantity, match.group(3)


def _to_int(text: str):
    """Convert a quantity string to an int; accepts both Chinese and Arabic numerals."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in _CHINESE_TO_INT:
        return _CHINESE_TO_INT[text]
    # 十一, 十二, ... (11, 12; the form doesn't use these yet, but handling them is cheap)
    if text.startswith('十') and len(text) == 2 and text[1] in _CHINESE_TO_INT:
        return 10 + _CHINESE_TO_INT[text[1]]
    return None
