"""
Google 表單回覆試算表的欄位與下拉選項對照

這份對照表對應「2026 開家門快樂 訂購表單 (回覆)」的『表單回覆 1』分頁。
品項欄位存的是表單下拉選項的**完整字串**（例如 `20A 一盒 $1,150`），
所以聊天紀錄解析出的「規格 + 數量」必須先在這裡轉成正確的選項字串，
不能讓 LLM 自由發揮，否則寫進去的值會和表單本身的選項對不起來。

價格來源：src/utils/price_calculator.py 的 price_list（已含運費）。
"""

from typing import Dict, Optional, Tuple

# 『表單回覆 1』的欄位順序（A~L）
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
    '欲配送日期 ',                                 # L（結尾有空白，是表單原本的標題）
]

FORM_RANGE = 'A:L'

# 盒數的中文數字（表單選項用中文，不是阿拉伯數字）
# 以下兩張表逐字對應 Google 表單的下拉選項，於 2026-08-13 與表單原文核對過。
#
# 有三個容易踩到的坑，改動時請保持原樣：
#   1. 禮盒用中文數字（一盒、兩盒…），家庭號用阿拉伯數字（1箱、2箱…），兩者不一致。
#   2. 「2」在禮盒寫作「兩盒」，不是「二盒」。
#   3. 18A 七盒與八盒的價格在表單裡沒有千分位逗號（$6510、$7400），
#      其餘選項都有。這是表單本身的筆誤，但寫入值必須和選項完全一致，所以照抄。
FORM_OPTIONS_VERIFIED_ON = '2026-08-13'

# 精選禮盒（一盒一層 6 顆）：級距定價，整段報價而非單價乘數量。
# 五盒以上會分成兩箱寄出，選項字串帶有「(兩箱寄出)」註記。
GIFTBOX_OPTIONS: Dict[Tuple[str, int], str] = {
    ('18A', 1): '18A 一盒 $1,020',
    ('18A', 2): '18A 兩盒 $1,910',
    ('18A', 3): '18A 三盒 $2,810',
    ('18A', 4): '18A 四盒 $3,700',
    ('18A', 5): '18A 五盒 $4,720 (兩箱寄出)',
    ('18A', 6): '18A 六盒 $5,610 (兩箱寄出)',
    ('18A', 7): '18A 七盒 $6510 (兩箱寄出)',   # 表單原文無逗號
    ('18A', 8): '18A 八盒 $7400 (兩箱寄出)',   # 表單原文無逗號
    ('20A', 1): '20A 一盒 $1,150',
    ('20A', 2): '20A 兩盒 $2,170',
    ('20A', 3): '20A 三盒 $3,200',
    ('20A', 4): '20A 四盒 $4,220',
    ('20A', 5): '20A 五盒 $5,370 (兩箱寄出)',
    ('20A', 6): '20A 六盒 $6,390 (兩箱寄出)',
    ('20A', 7): '20A 七盒 $7,420 (兩箱寄出)',
    ('20A', 8): '20A 八盒 $8,440 (兩箱寄出)',
}

# 家庭號（一箱兩層 12 顆）：線性計價，單價 18A $1,850／20A $2,110
FAMILY_OPTIONS_CONFIRMED = True

FAMILY_OPTIONS: Dict[Tuple[str, int], str] = {
    ('18A', 1): '18A 1箱 $1,850',
    ('18A', 2): '18A 2箱 $3,700',
    ('18A', 3): '18A 3箱 $5,550',
    ('20A', 1): '20A 1箱 $2,110',
    ('20A', 2): '20A 2箱 $4,220',
    ('20A', 3): '20A 3箱 $6,330',
}

# 表單提供到 8 盒 / 3 箱，超過的量沒有對應選項，需拆單
MAX_GIFTBOX_BOXES = max(boxes for _, boxes in GIFTBOX_OPTIONS)
MAX_FAMILY_BOXES = max(boxes for _, boxes in FAMILY_OPTIONS)


def giftbox_option(spec: str, boxes: int) -> Optional[str]:
    """把「規格 + 盒數」轉成禮盒欄位的選項字串，無對應選項時回傳 None"""
    return GIFTBOX_OPTIONS.get((_normalize_spec(spec), boxes))


def family_option(spec: str, boxes: int) -> Optional[str]:
    """把「規格 + 箱數」轉成家庭號欄位的選項字串，無對應選項時回傳 None"""
    return FAMILY_OPTIONS.get((_normalize_spec(spec), boxes))


def _normalize_spec(spec: str) -> str:
    """統一規格寫法：`18 a`、`18a` 都轉成 `18A`"""
    if not spec:
        return ''
    return spec.replace(' ', '').upper()


def describe_options() -> str:
    """產生給 LLM 看的可選品項說明"""
    giftbox = '、'.join(
        f'{spec} {boxes}盒'
        for (spec, boxes) in sorted(GIFTBOX_OPTIONS)
    )
    family = '、'.join(
        f'{spec} {boxes}箱'
        for (spec, boxes) in sorted(FAMILY_OPTIONS)
    )
    return f'精選禮盒（6顆/盒）：{giftbox}\n家庭號（12顆/箱）：{family}'
