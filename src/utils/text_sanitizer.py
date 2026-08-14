"""
文字前處理：把 emoji 與零寬字元清掉

LINE 聊天紀錄裡 emoji 到處都是（`陳虹如😊`、`要訂20A一盒🙏`），
會跟著被 LLM 抄進姓名、地址等欄位，寫進試算表就變成髒資料，
也讓重複檢查（收件人＋電話＋日期）比對不到。

所以兩個地方都清：
1. 送進 LLM 之前先清整份聊天紀錄——省 token，也讓模型不會看到就抄。
2. LLM 吐回來的每個欄位再清一次——模型仍可能自己生出 emoji。

只清 emoji 與零寬字元，中文、標點、全形符號一律保留。
"""

import re

# emoji 與相關的零寬／修飾字元。
# 刻意不動 CJK、全形標點、注音、數學符號這些正常會出現在訂單裡的字。
_EMOJI_PATTERN = re.compile(
    '['
    '\U0001F000-\U0001FAFF'   # 表情、手勢、物件、旗幟、麻將牌等主要 emoji 區段
    '\U00002600-\U000027BF'   # 雜項符號與裝飾符號（☀ ✂ ✅ ➡ 等）
    '\U00002B00-\U00002BFF'   # 箭頭與幾何圖形補充（⬆ ⭐ 等）
    '\U00002190-\U000021FF'   # 箭頭（↔ ↩ 等）
    '\U0000FE00-\U0000FE0F'   # 變體選擇符（讓符號顯示成彩色 emoji 的那個）
    '\U0001F1E6-\U0001F1FF'   # 區域指示符（國旗是兩個字母組成的）
    '\U0000200D'              # 零寬連接符（👨‍👩‍👧 這種組合 emoji 用的）
    '\U000020E3'              # 鍵帽的封閉框（1️⃣ = 數字 + FE0F + 20E3）
    '\U000024C2\U00003030\U0000303D\U00003297\U00003299'  # Ⓜ 〰 〽 ㊗ ㊙
    ']',
    flags=re.UNICODE,
)

# 其他零寬字元，肉眼看不到但會讓字串比對失敗
_ZERO_WIDTH = re.compile('[​‌‎‏﻿]')


def strip_emoji(text: str) -> str:
    """移除 emoji 與零寬字元，並整理清掉之後留下的多餘空白

    行結構會保留（換行不動），因為聊天紀錄的斷行本身是資訊。
    """
    if not text:
        return text

    # 鍵帽 emoji 只清掉外框與變體選擇符，保留數字本身（數量資訊不能掉）
    cleaned = _EMOJI_PATTERN.sub('', text)
    cleaned = _ZERO_WIDTH.sub('', cleaned)

    # emoji 清掉後常留下連續空白或行尾空白，順手收乾淨
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
    cleaned = re.sub(r'[ \t]+$', '', cleaned, flags=re.MULTILINE)
    return cleaned


def clean_field(value) -> str:
    """欄位值的標準清理：轉字串、去 emoji、去頭尾空白

    None 與非字串一律轉成字串，讓呼叫端不必先做型別判斷。
    """
    if value is None:
        return ''
    return strip_emoji(str(value)).strip()
