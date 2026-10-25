"""
Loading and validation of the item judgment A/B dataset (`dataset.jsonl`)

pytest and the upload script share `validate_items()`. Rules: docs/plans/jev-item-judgment.md §5.
The five-fields -> option-string mapping uses src/utils/item_resolver.py, the same rules as production.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.utils.form_options import FAMILY_OPTIONS, GIFTBOX_OPTIONS, SHUANGSHUANG_OPTIONS
from src.utils.item_resolver import ItemFields, resolve_items

EXPECTED_TOTAL = 50

# Distribution table from §5.2
CATEGORY_COUNTS: Dict[str, int] = {
    'simple': 10,
    'amended': 8,
    'numeral': 6,
    'multi_item': 6,
    'shuangshuang': 5,
    'no_order': 5,
    'over_limit': 3,
    'spec_missing': 3,
    'multi_receiver': 4,
}

DIFFICULTIES = {'easy', 'medium', 'hard'}

FIELD_KEYS = ('giftbox_spec', 'giftbox_boxes', 'family_spec', 'family_boxes', 'shuangshuang_sets')

GIFTBOX_VALUES = set(GIFTBOX_OPTIONS.values())
FAMILY_VALUES = set(FAMILY_OPTIONS.values()) | set(SHUANGSHUANG_OPTIONS.values())


def load_items(path: Union[str, Path]) -> List[dict]:
    """Read jsonl, one item per line, skipping blank lines"""
    items = []
    with open(path, encoding='utf-8') as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f'line {lineno} is not valid JSON: {error}') from error
    return items


def resolve_fields(fields: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Map the five fields to (gift box option, family column option) with production's item_resolver"""
    resolved = resolve_items(ItemFields(**fields))
    return resolved.giftbox, resolved.family


def validate_items(items: List[dict]) -> None:
    """Raise ValueError on the first invalid item, naming its id and the reason"""
    if len(items) != EXPECTED_TOTAL:
        raise ValueError(f'dataset should have {EXPECTED_TOTAL} items, got {len(items)}')

    seen = set()
    counts = {category: 0 for category in CATEGORY_COUNTS}
    for index, item in enumerate(items, 1):
        item_id = item.get('id') or f'<item {index} has no id>'
        _validate_item(item, item_id)
        if item_id in seen:
            raise ValueError(f'{item_id}: duplicate id')
        seen.add(item_id)
        counts[item['metadata']['category']] += 1

    wrong = {c: (n, CATEGORY_COUNTS[c]) for c, n in counts.items() if n != CATEGORY_COUNTS[c]}
    if wrong:
        detail = ', '.join(f'{c} has {n}, expected {want}' for c, (n, want) in wrong.items())
        raise ValueError(f'category counts do not match the distribution table: {detail}')


def _validate_item(item: dict, item_id: str) -> None:
    def fail(reason: str) -> None:
        raise ValueError(f'{item_id}: {reason}')

    for key in ('id', 'input', 'expected_output', 'metadata'):
        if key not in item:
            fail(f'missing {key}')

    inp, expected, meta = item['input'], item['expected_output'], item['metadata']

    chat_log = inp.get('chat_log')
    if not isinstance(chat_log, str) or not chat_log.strip():
        fail('input.chat_log is empty')
    if not inp.get('current_date'):
        fail('missing input.current_date')
    if 'receiver_name' not in inp:
        fail('missing input.receiver_name')

    category = meta.get('category')
    if category not in CATEGORY_COUNTS:
        fail(f'unknown category: {category!r}')
    if meta.get('difficulty') not in DIFFICULTIES:
        fail(f'unknown difficulty: {meta.get("difficulty")!r}')
    if meta.get('source') != 'synthetic':
        fail(f'source should be synthetic: {meta.get("source")!r}')

    fields = expected.get('fields')
    if not isinstance(fields, dict):
        fail('missing expected_output.fields')
    missing = [key for key in FIELD_KEYS if key not in fields]
    if missing:
        fail(f'fields is missing {missing}')
    extra = [key for key in fields if key not in FIELD_KEYS]
    if extra:
        fail(f'fields has extra keys {extra}')

    giftbox, family = expected.get('giftbox'), expected.get('family')
    if giftbox is not None and giftbox not in GIFTBOX_VALUES:
        fail(f'giftbox is not a form option string: {giftbox!r}')
    if family is not None and family not in FAMILY_VALUES:
        fail(f'family is not a form option string: {family!r}')

    if fields.get('family_boxes') and fields.get('shuangshuang_sets'):
        fail('family pack and 雙雙對對 together (column J conflict); avoid such samples')

    try:
        resolved = resolve_fields(fields)
    except (TypeError, ValueError) as error:
        fail(f'fields quantity is not an integer: {error}')
    if resolved != (giftbox, family):
        fail(f'expected does not match the mapped fields: mapped {resolved}, expected {(giftbox, family)}')

    if category == 'over_limit' and (giftbox is not None or family is not None):
        fail('over_limit items must have null giftbox and family')
    if category == 'no_order' and any(fields[key] is not None for key in FIELD_KEYS):
        fail('no_order items must have all-null fields')

    receiver = inp.get('receiver_name')
    if category == 'multi_receiver':
        if not receiver:
            fail('multi_receiver items must have receiver_name')
        if receiver not in chat_log:
            fail(f'receiver_name {receiver!r} does not appear in chat_log')
