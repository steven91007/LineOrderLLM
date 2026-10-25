"""
Text pre-processing: strip emoji and zero-width characters

LINE chat logs are full of emoji (`陳虹如😊`, `要訂20A一盒🙏`). The LLM copies
them into fields such as name and address, which ends up as dirty data in the
spreadsheet and also breaks duplicate detection (recipient + phone + date).

So we clean in two places:
1. Clean the whole chat log before sending it to the LLM - saves tokens and the
   model can't copy what it never sees.
2. Clean every field the LLM returns again - the model may still produce emoji itself.

Only emoji and zero-width characters are removed; Chinese text, punctuation and
full-width symbols are always kept.
"""

import re

# Emoji and related zero-width / modifier characters.
# Deliberately leaves CJK, full-width punctuation, Zhuyin and math symbols alone,
# since those appear normally in orders.
_EMOJI_PATTERN = re.compile(
    '['
    '\U0001F000-\U0001FAFF'   # Main emoji blocks: faces, gestures, objects, flags, mahjong tiles, etc.
    '\U00002600-\U000027BF'   # Miscellaneous symbols and dingbats (☀ ✂ ✅ ➡ etc.)
    '\U00002B00-\U00002BFF'   # Supplemental arrows and geometric shapes (⬆ ⭐ etc.)
    '\U00002190-\U000021FF'   # Arrows (↔ ↩ etc.)
    '\U0000FE00-\U0000FE0F'   # Variation selectors (the one that renders a symbol as color emoji)
    '\U0001F1E6-\U0001F1FF'   # Regional indicators (flags are made of two letters)
    '\U0000200D'              # Zero-width joiner (used by combined emoji like 👨‍👩‍👧)
    '\U000020E3'              # Enclosing keycap (1️⃣ = digit + FE0F + 20E3)
    '\U000024C2\U00003030\U0000303D\U00003297\U00003299'  # Ⓜ 〰 〽 ㊗ ㊙
    ']',
    flags=re.UNICODE,
)

# Other zero-width characters: invisible, but they break string comparisons
_ZERO_WIDTH = re.compile('[​‌‎‏﻿]')


def strip_emoji(text: str) -> str:
    """Remove emoji and zero-width characters, and tidy up leftover whitespace

    Line structure is preserved (newlines untouched) because line breaks in a
    chat log carry information.
    """
    if not text:
        return text

    # For keycap emoji, only the enclosing frame and variation selector are removed;
    # the digit itself is kept (quantity information must not be lost)
    cleaned = _EMOJI_PATTERN.sub('', text)
    cleaned = _ZERO_WIDTH.sub('', cleaned)

    # Removing emoji often leaves runs of spaces or trailing spaces; clean those up too
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
    cleaned = re.sub(r'[ \t]+$', '', cleaned, flags=re.MULTILINE)
    return cleaned


def clean_field(value) -> str:
    """Standard field-value cleanup: convert to str, strip emoji, trim whitespace

    None and non-strings are always converted to strings so callers don't need
    to type-check first.
    """
    if value is None:
        return ''
    return strip_emoji(str(value)).strip()
