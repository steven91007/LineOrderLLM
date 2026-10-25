"""
Item fields -> Google Form dropdown option strings

Both GPT (ChatLogParser) and Jev (JevItemJudge) only judge the five "category x spec x quantity"
fields. The rules that turn them into form option strings live here, so both backends go through
the same path and the A/B comparison is fair.

This logic used to live in ChatLogImporter (_resolve_item_inner etc.). It was moved without
changing behavior or the problem messages.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from . import langfuse_tracing as tracing
from .form_options import (
    FAMILY_OPTIONS_CONFIRMED,
    MAX_FAMILY_BOXES,
    MAX_GIFTBOX_BOXES,
    MAX_SHUANGSHUANG_SETS,
    family_option,
    giftbox_option,
    shuangshuang_option,
)

ITEM_FIELD_NAMES = ('giftbox_spec', 'giftbox_boxes', 'family_spec',
                    'family_boxes', 'shuangshuang_sets')


@dataclass(frozen=True)
class ItemFields:
    """Item judgment for one recipient (same field names as ChatLogParser's output)

    Quantities are usually ints, but GPT occasionally emits an unparseable string; the raw value
    is kept so the resolver can report it as a problem.
    """
    giftbox_spec: Optional[str] = None
    giftbox_boxes: Any = None
    family_spec: Optional[str] = None
    family_boxes: Any = None
    shuangshuang_sets: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def normalized(self) -> 'ItemFields':
        """For comparison: upper-case specs without spaces and int quantities,
        so "20a" equals "20A" and "2" equals 2"""
        def spec(value):
            return str(value).replace(' ', '').upper() or None if value else None

        def count(value):
            try:
                return int(value) if value not in (None, '') else None
            except (TypeError, ValueError):
                return value

        return ItemFields(
            giftbox_spec=spec(self.giftbox_spec), giftbox_boxes=count(self.giftbox_boxes),
            family_spec=spec(self.family_spec), family_boxes=count(self.family_boxes),
            shuangshuang_sets=count(self.shuangshuang_sets),
        )


@dataclass(frozen=True)
class ResolvedItems:
    giftbox: Optional[str]          # column I option string
    family: Optional[str]           # column J option string (family pack or 雙雙對對)
    problems: List[str] = field(default_factory=list)


def fields_from_raw(raw: Dict[str, Any]) -> ItemFields:
    """Take the five fields from an LLM order dict; empty strings become None, digit strings become int"""
    values = {}
    for name in ITEM_FIELD_NAMES:
        value = raw.get(name)
        if isinstance(value, str):
            value = value.strip() or None
            if value is not None and name.endswith(('_boxes', '_sets')) and value.isdigit():
                value = int(value)
        values[name] = value
    return ItemFields(**values)


def resolve_items(fields: ItemFields) -> ResolvedItems:
    """Turn the five fields into column I/J option strings, collecting reasons for manual review"""
    problems: List[str] = []

    giftbox = _traced_item(fields.giftbox_spec, fields.giftbox_boxes,
                           giftbox_option, MAX_GIFTBOX_BOXES, '禮盒', '盒', problems)
    family = _traced_item(fields.family_spec, fields.family_boxes,
                          family_option, MAX_FAMILY_BOXES, '家庭號', '箱', problems)
    shuangshuang = _traced_shuangshuang(fields.shuangshuang_sets, problems)

    if family and shuangshuang:
        problems.append('家庭號與雙雙對對同時出現，J 欄只能擇一寫入，請人工確認')
    family = family or shuangshuang

    if family and not FAMILY_OPTIONS_CONFIRMED:
        problems.append('家庭號選項字串尚未和 Google 表單核對過，請確認後再寫入')
    if shuangshuang:
        problems.append('雙雙對對選項字串尚未和 Google 表單核對過，請確認表單已加上此選項後再寫入')

    return ResolvedItems(giftbox=giftbox, family=family, problems=problems)


def _traced_item(spec: Any, boxes: Any, lookup, max_boxes: int,
                 label: str, unit: str, problems: List[str]) -> Optional[str]:
    if not spec and not boxes:
        return None

    with tracing.trace(f'resolve-item-{label}',
                       input_data={'spec': spec, 'quantity': boxes}) as span:
        option = resolve_item(spec, boxes, lookup, max_boxes, label, unit, problems)
        span.update(output=option, metadata={'matched': option is not None})
        return option


def _traced_shuangshuang(sets: Any, problems: List[str]) -> Optional[str]:
    if not sets:
        return None

    with tracing.trace('resolve-item-雙雙對對', input_data={'quantity': sets}) as span:
        option = resolve_shuangshuang(sets, problems)
        span.update(output=option, metadata={'matched': option is not None})
        return option


def resolve_item(spec: Any, boxes: Any, lookup, max_boxes: int,
                 label: str, unit: str, problems: List[str]) -> Optional[str]:
    """Map spec and quantity to the form's dropdown option string"""
    if not spec:
        problems.append(f'{label}有數量但沒有規格')
        return None
    if not boxes:
        problems.append(f'{label}有規格但沒有數量')
        return None

    try:
        count = int(boxes)
    except (TypeError, ValueError):
        problems.append(f'{label}數量無法辨識（{boxes}）')
        return None

    if count > max_boxes:
        problems.append(
            f'{label} {count}{unit}超過表單選項上限（最多 {max_boxes}{unit}），需拆單或人工處理'
        )
        return None

    option = lookup(str(spec), count)
    if not option:
        problems.append(f'{label}找不到對應選項：{spec} {count}{unit}')
    return option


def resolve_shuangshuang(sets: Any, problems: List[str]) -> Optional[str]:
    """Map a set count to the 雙雙對對 option string (it has no spec)"""
    try:
        count = int(sets)
    except (TypeError, ValueError):
        problems.append(f'雙雙對對數量無法辨識（{sets}）')
        return None

    if count > MAX_SHUANGSHUANG_SETS:
        problems.append(
            f'雙雙對對 {count}組超過表單選項上限（最多 {MAX_SHUANGSHUANG_SETS}組），需拆單或人工處理'
        )
        return None

    option = shuangshuang_option(count)
    if not option:
        problems.append(f'雙雙對對找不到對應選項：{count}組')
    return option
