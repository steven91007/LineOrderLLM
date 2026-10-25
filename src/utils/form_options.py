"""
Column and dropdown-option mapping for the Google Form response spreadsheet

This mapping corresponds to the 『表單回覆 1』 (Form Responses 1) tab of
"2026 開家門快樂 訂購表單 (回覆)".
Item columns store the **full string** of the form's dropdown option (e.g.
`20A 一盒 $1,150`), so the "size + quantity" parsed from the chat log must be
converted here into the exact option string. The LLM must not improvise,
otherwise the written value won't match the form's own options.

Price source: price_list in src/utils/price_calculator.py (shipping included).
"""

from typing import Dict, Optional, Tuple

# Column order of 『表單回覆 1』 (A-L)
FORM_COLUMNS = [
    '時間戳記',                                    # A
    '訂購人 (請留LINE上的大名 方便與您聯絡)',        # B
    '寄件人',                                      # C
    '寄件人電話',                                  # D
    '寄件人地址',                                  # E
    '收件人',                                      # F
    '收件人電話',                                  # G
    '收件人地址',                                  # H
    '(禮盒) 欲訂購的品項',                          # I
    '(家庭號) 欲訂購的品項',                        # J
    '匯款資料如下 請填入匯款後五碼以利核對',          # K
    '欲配送日期 ',                                 # L (the trailing space is part of the form's original header)
]

FORM_RANGE = 'A:L'

# Box counts use Chinese numerals (the form options use Chinese, not Arabic digits).
# The two tables below match the Google Form dropdown options verbatim; they were
# checked against the form's original text on 2026-08-13.
#
# Three easy pitfalls - keep them exactly as-is when editing:
#   1. Gift boxes use Chinese numerals (一盒, 兩盒, ...) while family packs use
#      Arabic digits (1箱, 2箱, ...); the two are inconsistent.
#   2. "2" for gift boxes is written "兩盒", not "二盒".
#   3. The 18A 七盒 and 八盒 (7 and 8 boxes) prices have no thousands separator in
#      the form ($6510, $7400), unlike every other option. It's a typo in the form
#      itself, but written values must match the options exactly, so it's copied as-is.
FORM_OPTIONS_VERIFIED_ON = '2026-08-13'

# 精選禮盒 (premium gift box, one layer of 6 per box): tiered pricing - each tier
# has its own total price rather than unit price x quantity.
# Five or more boxes ship as two parcels, and the option string carries the
# "(兩箱寄出)" (shipped in two boxes) note.
GIFTBOX_OPTIONS: Dict[Tuple[str, int], str] = {
    ('18A', 1): '18A 一盒 $1,020',
    ('18A', 2): '18A 兩盒 $1,910',
    ('18A', 3): '18A 三盒 $2,810',
    ('18A', 4): '18A 四盒 $3,700',
    ('18A', 5): '18A 五盒 $4,720 (兩箱寄出)',
    ('18A', 6): '18A 六盒 $5,610 (兩箱寄出)',
    ('18A', 7): '18A 七盒 $6510 (兩箱寄出)',   # No comma in the original form text
    ('18A', 8): '18A 八盒 $7400 (兩箱寄出)',   # No comma in the original form text
    ('20A', 1): '20A 一盒 $1,150',
    ('20A', 2): '20A 兩盒 $2,170',
    ('20A', 3): '20A 三盒 $3,200',
    ('20A', 4): '20A 四盒 $4,220',
    ('20A', 5): '20A 五盒 $5,370 (兩箱寄出)',
    ('20A', 6): '20A 六盒 $6,390 (兩箱寄出)',
    ('20A', 7): '20A 七盒 $7,420 (兩箱寄出)',
    ('20A', 8): '20A 八盒 $8,440 (兩箱寄出)',
}

# 家庭號 (family pack, two layers of 12 per case): linear pricing, unit price 18A $1,850 / 20A $2,110
FAMILY_OPTIONS_CONFIRMED = True

FAMILY_OPTIONS: Dict[Tuple[str, int], str] = {
    ('18A', 1): '18A 1箱 $1,850',
    ('18A', 2): '18A 2箱 $3,700',
    ('18A', 3): '18A 3箱 $5,550',
    ('20A', 1): '20A 1箱 $2,110',
    ('20A', 2): '20A 2箱 $4,220',
    ('20A', 3): '20A 3箱 $6,330',
}

# "雙雙對對": fixed price $3,400 per set (組), no size grade, written to the
# 家庭號 (family pack) column (column J).
# Added 2026-09-05: the Google Form does not have this dropdown option yet, so the
# strings below are a proposed format. Once the option is actually added to the form,
# verify them verbatim against the form text (same as FORM_OPTIONS_VERIFIED_ON).
SHUANGSHUANG_OPTIONS: Dict[int, str] = {
    1: '雙雙對對 一組 $3,400',
    2: '雙雙對對 兩組 $6,800',
    3: '雙雙對對 三組 $10,200',
    4: '雙雙對對 四組 $13,600',
}

# The form goes up to 8 boxes / 3 cases / 4 sets; larger quantities have no
# matching option and must be split into multiple orders
MAX_GIFTBOX_BOXES = max(boxes for _, boxes in GIFTBOX_OPTIONS)
MAX_FAMILY_BOXES = max(boxes for _, boxes in FAMILY_OPTIONS)
MAX_SHUANGSHUANG_SETS = max(SHUANGSHUANG_OPTIONS)


def giftbox_option(spec: str, boxes: int) -> Optional[str]:
    """Convert "size + box count" into a gift-box column option string; return None if no option matches"""
    return GIFTBOX_OPTIONS.get((_normalize_spec(spec), boxes))


def family_option(spec: str, boxes: int) -> Optional[str]:
    """Convert "size + case count" into a family-pack column option string; return None if no option matches"""
    return FAMILY_OPTIONS.get((_normalize_spec(spec), boxes))


def shuangshuang_option(sets: int) -> Optional[str]:
    """Convert a set count into a 雙雙對對 option string (written to the family-pack column); return None if no option matches"""
    return SHUANGSHUANG_OPTIONS.get(sets)


def _normalize_spec(spec: str) -> str:
    """Normalize the size spelling: `18 a` and `18a` both become `18A`"""
    if not spec:
        return ''
    return spec.replace(' ', '').upper()


def describe_options() -> str:
    """Build the description of available items shown to the LLM"""
    giftbox = '、'.join(
        f'{spec} {boxes}盒'
        for (spec, boxes) in sorted(GIFTBOX_OPTIONS)
    )
    family = '、'.join(
        f'{spec} {boxes}箱'
        for (spec, boxes) in sorted(FAMILY_OPTIONS)
    )
    shuangshuang = '、'.join(
        f'{sets}組' for sets in sorted(SHUANGSHUANG_OPTIONS)
    )
    return (
        f'精選禮盒 (gift box, 6 pieces per 盒): {giftbox}\n'
        f'家庭號 (family pack, 12 pieces per 箱): {family}\n'
        f'雙雙對對 (fixed set, no size grade, goes in the 家庭號 column): {shuangshuang}'
    )
