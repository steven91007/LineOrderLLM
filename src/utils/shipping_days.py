"""Definition of shipping days

CONTEXT.md: **only Wednesday and Sunday are shipping days**; nothing ships on other days.

This is deliberately a tiny dependency-free module so that parsing (chat_log_importer)
and auditing (offday_orders) share a single definition. This set used to live in
chat_log_importer, but that module pulls in all of DSPy, and the audit tool should not
pay that cost just to ask "what weekday is it".

Note: existing responses in the 2026 form include 2026/8/18 (a Tuesday), which
contradicts CONTEXT.md. For now this follows CONTEXT.md; orders that fall on a
non-shipping day are only flagged, not blocked.
If the shipping-day rule changes, just edit this set and both sides pick it up.
"""

from datetime import date
from typing import Union

# Monday=0 … Sunday=6, so 2=Wednesday, 6=Sunday
SHIPPING_WEEKDAYS = {2, 6}

WEEKDAY_NAMES = '一二三四五六日'


def is_shipping_day(value: Union[date, int]) -> bool:
    """Return whether it is a shipping day; accepts a date or a weekday() number"""
    weekday = value if isinstance(value, int) else value.weekday()
    return weekday in SHIPPING_WEEKDAYS


def weekday_name(value: Union[date, int]) -> str:
    """Return the Chinese weekday character such as "三" or "日", without the "星期" prefix"""
    weekday = value if isinstance(value, int) else value.weekday()
    return WEEKDAY_NAMES[weekday]


def shipping_days_text() -> str:
    """Human-readable shipping-day description, e.g. "週三、週日" (Wed, Sun)"""
    return '、'.join(f'週{WEEKDAY_NAMES[d]}' for d in sorted(SHIPPING_WEEKDAYS))
