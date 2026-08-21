"""出貨日的定義

CONTEXT.md：**只有週三與週日是出貨日**，其餘日期不出貨。

這裡刻意獨立成一個沒有相依的小模組，讓解析（chat_log_importer）和稽核
（offday_orders）共用同一份定義。以前這個集合寫在 chat_log_importer 裡，
但那個模組會拉進整個 DSPy，稽核工具不該為了問「星期幾」付這個代價。

注意：2026 這份表單的既有回覆裡出現過 2026/8/18（星期二），和 CONTEXT.md 對不上。
這裡先照 CONTEXT.md 設定，落在非出貨日的訂單只會被標記出來、不會被擋掉。
若出貨日規則改了，改這個集合即可，兩邊會同時生效。
"""

from datetime import date
from typing import Union

# Monday=0 … Sunday=6，所以 2=星期三、6=星期日
SHIPPING_WEEKDAYS = {2, 6}

WEEKDAY_NAMES = '一二三四五六日'


def is_shipping_day(value: Union[date, int]) -> bool:
    """判斷是不是出貨日，吃 date 或 weekday() 的數字"""
    weekday = value if isinstance(value, int) else value.weekday()
    return weekday in SHIPPING_WEEKDAYS


def weekday_name(value: Union[date, int]) -> str:
    """回傳「三」「日」這樣的中文星期，不含「星期」兩個字"""
    weekday = value if isinstance(value, int) else value.weekday()
    return WEEKDAY_NAMES[weekday]


def shipping_days_text() -> str:
    """給人看的出貨日說明，例如「週三、週日」"""
    return '、'.join(f'週{WEEKDAY_NAMES[d]}' for d in sorted(SHIPPING_WEEKDAYS))
