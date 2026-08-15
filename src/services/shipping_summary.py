"""
出貨統計：把一天的訂單彙整成備貨清單

輸出形如：

    20A 家庭號 1箱*2個地址
    20A 禮盒 1盒*2個地址
    18A 禮盒 1盒*1個地址

「個地址」數的是**訂單列數**，不是不重複地址數——一列就是一次出貨，
同一個地址下兩張單要包兩份，合併計算會少備貨。

統計的來源是試算表 I／J 欄的下拉選項字串（例如 `20A 一盒 $1,150`、
`18A 1箱 $1,850`），而不是自由文字，所以可以穩定地用規則解析。
禮盒的數量用中文（一盒、兩盒），家庭號用阿拉伯數字（1箱、2箱），
兩者不一致是表單本身的寫法，這裡讀進來之後統一轉成阿拉伯數字顯示。
"""

import re
from collections import OrderedDict
from typing import Any, Dict, List, NamedTuple

# 品項欄位在總表的位置
GIFTBOX_INDEX = 8   # I 欄 (禮盒) 欲訂購的品項
FAMILY_INDEX = 9    # J 欄 (家庭號) 欲訂購的品項

GIFTBOX_LABEL = '禮盒'
FAMILY_LABEL = '家庭號'

# 選項字串開頭的「規格 + 數量 + 單位」，例如 `20A 一盒 $1,150`、`18A 1箱 $1,850`
_OPTION_PATTERN = re.compile(r'^\s*(\d+\s*[A-Za-z])\s*([一二兩三四五六七八九十\d]+)\s*([盒箱])')

_CHINESE_TO_INT = {
    '一': 1, '二': 2, '兩': 2, '三': 3, '四': 4,
    '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
}


class SummaryLine(NamedTuple):
    """一種「規格＋類別＋單筆數量」的統計結果"""
    category: str      # 禮盒 / 家庭號
    spec: str          # 18A / 20A
    quantity: int      # 每一筆訂單的盒數或箱數
    unit: str          # 盒 / 箱
    addresses: int     # 有幾筆訂單（幾個出貨地址）
    total_units: int   # quantity * addresses，總共要備幾盒／幾箱

    @property
    def text(self) -> str:
        """`20A 家庭號 1箱*2個地址`"""
        return f'{self.spec} {self.category} {self.quantity}{self.unit}*{self.addresses}個地址'


def summarize(rows: List[List[Any]]) -> Dict[str, Any]:
    """統計一批訂單列

    Args:
        rows: 訂單資料列（不含標題列），欄位順序同總表

    Returns:
        {'lines': [SummaryLine, ...], 'order_count': int,
         'totals': {'盒': n, '箱': n}, 'unparsed': [原始字串, ...]}
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
                # 解析不出來就記下來回報，不要靜默漏掉——漏算比算錯更難發現
                unparsed.append(raw)
                continue

            spec, quantity, unit = parsed
            key = (category, spec, quantity, unit)
            counts[key] = counts.get(key, 0) + 1

    lines = [
        SummaryLine(category=category, spec=spec, quantity=quantity, unit=unit,
                    addresses=addresses, total_units=quantity * addresses)
        for (category, spec, quantity, unit), addresses in counts.items()
    ]
    # 排序：禮盒在前（和試算表的欄位順序一致），再依規格、單筆數量
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
    """把統計結果轉成要寫進試算表的資料列（單欄文字，接在訂單列下方）"""
    rows: List[List[Any]] = [[], [f'📦 {title} 出貨統計']]
    rows.extend([line.text] for line in summary['lines'])

    if summary['unparsed']:
        rows.append([f'⚠️ 有 {len(summary["unparsed"])} 筆品項無法辨識，未列入統計：'
                     + '、'.join(sorted(set(summary['unparsed'])))])

    rows.append([_totals_text(summary)])
    return rows


def _totals_text(summary: Dict[str, Any]) -> str:
    """`合計 4 筆訂單／禮盒 3 盒／家庭號 2 箱` 這種收尾行"""
    parts = [f'合計 {summary["order_count"]} 筆訂單']
    parts.extend(f'{count} {unit}' for unit, count in summary['totals'].items())
    return '／'.join(parts)


def _parse_option(option: str):
    """把選項字串拆成 (規格, 數量, 單位)，看不懂回 None"""
    match = _OPTION_PATTERN.match(option)
    if not match:
        return None

    spec = match.group(1).replace(' ', '').upper()
    quantity = _to_int(match.group(2))
    if quantity is None:
        return None

    return spec, quantity, match.group(3)


def _to_int(text: str):
    """數量字串轉整數，中文與阿拉伯數字都吃"""
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in _CHINESE_TO_INT:
        return _CHINESE_TO_INT[text]
    # 十一、十二…（表單目前沒有，但寫法便宜就先擋著）
    if text.startswith('十') and len(text) == 2 and text[1] in _CHINESE_TO_INT:
        return 10 + _CHINESE_TO_INT[text[1]]
    return None
