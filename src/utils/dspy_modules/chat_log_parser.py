"""
聊天紀錄訂單解析 DSPy 模組

和 UnifiedOrderParser 的差別：
- UnifiedOrderParser 處理「一則訊息 = 一張訂單」的情境
- ChatLogParser 處理「一整段對話」，訂單資訊會散在多則訊息裡，
  中間夾雜閒聊、改單、取消，而且可能有多位訂購人

輸出的欄位直接對應 Google 表單回覆試算表的欄位，
但品項只輸出「規格 + 數量」，實際的下拉選項字串由 form_options 決定。
"""
import dspy
import json
import logging
import re
from typing import Any, Dict, List

from ..form_options import describe_options

logger = logging.getLogger(__name__)


class ChatLogOrderSignature(dspy.Signature):
    """從 LINE 聊天紀錄中抽取所有成立的訂單

    重點規則：
    1. 一段對話可能包含 0 到多張訂單，一位訂購人也可能寄給多位收件人（送禮情境），
       每一位收件人算一張獨立訂單。
    2. 訂單資訊常常散在多則訊息：先報地址、隔幾則才報數量、最後才補匯款末五碼。
       要把同一張訂單的資訊合併起來。
    3. 客人若後來改單（改數量、改地址、改日期），以**最後一次**的說法為準。
       明確說取消的訂單不要輸出。
    4. 只有「詢價、還在考慮、明說不訂了」不算訂單。
       **只要客人講出要買什麼，就是一張成立的訂單**，即使：
       - 還沒付款、說「我等等匯款」
       - 資料不齊（缺電話、缺地址、缺日期）
       這些情況一樣要輸出，把缺漏寫進 issues，不要因為不完整就整筆丟掉。
    5. 不要臆測沒講的資訊。沒提到的欄位就留空字串，並在 issues 裡說明。
    6. 寧可多輸出也不要漏。漏掉一張訂單的代價遠高於多出一張。
    """
    chat_log = dspy.InputField(desc="LINE 聊天紀錄原文，可能含時間戳記與發話者名稱")
    current_date = dspy.InputField(desc="今天的日期，格式：YYYY-MM-DD (星期X)，用於解析『這週三』『下週日』等相對日期")
    available_items = dspy.InputField(desc="可訂購的品項清單，解析出的規格與數量必須落在這個範圍內")
    orders_json = dspy.OutputField(desc=(
        '訂單陣列 JSON。每筆格式：'
        '{"orderer": "訂購人LINE暱稱", "sender_name": "寄件人", "sender_phone": "寄件人電話", '
        '"sender_address": "寄件人地址", "receiver_name": "收件人", "receiver_phone": "收件人電話", '
        '"receiver_address": "收件人地址", "giftbox_spec": "18A或20A或null", "giftbox_boxes": 盒數或null, '
        '"family_spec": "18A或20A或null", "family_boxes": 箱數或null, "last5": "匯款後五碼", '
        '"shipping_date": "YYYY-MM-DD或null", "source_quote": "此訂單依據的原始訊息片段", '
        '"issues": ["缺漏或不確定之處"]}'
    ))


class OrderRecallSignature(dspy.Signature):
    """複查是否有訂單被漏掉

    實測發現單次抽取會靜默漏單，而且不同模型漏的還不是同一筆：
    有的漏掉「第二位收件人」，有的把「說要買但還沒匯款」的客人整筆丟掉。
    漏單是最難發現的錯誤——欄位填錯看得到，整筆消失看不到。
    所以抽完之後再回頭比對一次。

    判斷「漏掉」的標準要寬鬆：只要對話裡有人講出要買什麼，
    而他不在已抽取清單中，就算漏掉，即使他還沒付款或資料不齊。
    """
    chat_log = dspy.InputField(desc="LINE 聊天紀錄原文")
    current_date = dspy.InputField(desc="今天的日期，格式：YYYY-MM-DD (星期X)")
    available_items = dspy.InputField(desc="可訂購的品項清單")
    extracted_summary = dspy.InputField(desc="第一輪已經抽出來的訂單摘要，每行一筆「收件人／品項」")
    missing_orders_json = dspy.OutputField(desc=(
        '被漏掉的訂單陣列 JSON，格式與第一輪完全相同。'
        '若確認沒有漏掉任何訂單，輸出空陣列 []'
    ))


class ChatLogParser(dspy.Module):
    """聊天紀錄訂單解析模組

    兩段式：先抽取，再複查有沒有漏掉。
    """

    def __init__(self):
        super().__init__()
        self.parse = dspy.ChainOfThought(ChatLogOrderSignature)
        self.recall = dspy.ChainOfThought(OrderRecallSignature)
        self.available_items = describe_options()
        self.examples = self._build_examples()

    def _build_examples(self) -> List[dspy.Example]:
        """Few-shot 範例，涵蓋跨訊息合併、多收件人、改單三種情境"""
        multi_receiver_log = (
            "2026/08/10 22:05\t小葛\t老闆我要訂三份送客戶\n"
            "2026/08/10 22:06\t小葛\t寄件人寫 陳虹如 0937619689\n"
            "2026/08/10 22:07\t小葛\t第一位 李綉屏 0922416507 台北市大安區安和路1段135巷9號4樓\n"
            "2026/08/10 22:08\t小葛\t第二位 黃金嬌 0932182646 台北市基隆路二段22號10樓\n"
            "2026/08/10 22:09\t小葛\t都是20A一盒 麻煩16號出貨"
        )
        multi_receiver_out = [
            {
                "orderer": "小葛", "sender_name": "陳虹如", "sender_phone": "0937619689",
                "sender_address": "", "receiver_name": "李綉屏", "receiver_phone": "0922416507",
                "receiver_address": "台北市大安區安和路1段135巷9號4樓",
                "giftbox_spec": "20A", "giftbox_boxes": 1,
                "family_spec": None, "family_boxes": None, "last5": "",
                "shipping_date": "2026-08-16",
                "source_quote": "第一位 李綉屏 0922416507 台北市大安區安和路1段135巷9號4樓 / 都是20A一盒 麻煩16號出貨",
                "issues": ["未提供匯款末五碼"],
            },
            {
                "orderer": "小葛", "sender_name": "陳虹如", "sender_phone": "0937619689",
                "sender_address": "", "receiver_name": "黃金嬌", "receiver_phone": "0932182646",
                "receiver_address": "台北市基隆路二段22號10樓",
                "giftbox_spec": "20A", "giftbox_boxes": 1,
                "family_spec": None, "family_boxes": None, "last5": "",
                "shipping_date": "2026-08-16",
                "source_quote": "第二位 黃金嬌 0932182646 台北市基隆路二段22號10樓 / 都是20A一盒 麻煩16號出貨",
                "issues": ["未提供匯款末五碼"],
            },
        ]

        amended_log = (
            "2026/08/12 09:14\t周香香\t我要訂18A兩盒\n"
            "2026/08/12 09:15\t周香香\t周香香 0970866789\n"
            "2026/08/12 09:15\t周香香\t台北市南港區經貿二路157巷62號\n"
            "2026/08/12 09:40\t周香香\t不好意思改成四盒好了\n"
            "2026/08/12 19:16\t周香香\t匯款好了 末五碼53900\n"
            "2026/08/12 19:20\t周香香\t18號出貨可以嗎"
        )
        amended_out = [
            {
                "orderer": "周香香", "sender_name": "周香香", "sender_phone": "0970866789",
                "sender_address": "", "receiver_name": "周香香", "receiver_phone": "0970866789",
                "receiver_address": "台北市南港區經貿二路157巷62號",
                "giftbox_spec": "18A", "giftbox_boxes": 4,
                "family_spec": None, "family_boxes": None, "last5": "53900",
                "shipping_date": "2026-08-18",
                "source_quote": "我要訂18A兩盒 → 不好意思改成四盒好了 / 匯款好了 末五碼53900",
                "issues": ["數量經改單，以四盒為準", "寄收件人同一人，依訊息推定"],
            },
        ]

        chitchat_log = (
            "2026/08/12 10:02\t王大明\t請問還有貨嗎\n"
            "2026/08/12 10:03\t老闆\t有的喔\n"
            "2026/08/12 10:05\t王大明\t好我再想想"
        )

        return [
            dspy.Example(
                chat_log=multi_receiver_log,
                current_date="2026-08-10 (星期一)",
                available_items=self.available_items,
                orders_json=json.dumps(multi_receiver_out, ensure_ascii=False),
            ).with_inputs("chat_log", "current_date", "available_items"),
            dspy.Example(
                chat_log=amended_log,
                current_date="2026-08-12 (星期三)",
                available_items=self.available_items,
                orders_json=json.dumps(amended_out, ensure_ascii=False),
            ).with_inputs("chat_log", "current_date", "available_items"),
            dspy.Example(
                chat_log=chitchat_log,
                current_date="2026-08-12 (星期三)",
                available_items=self.available_items,
                orders_json="[]",
            ).with_inputs("chat_log", "current_date", "available_items"),
        ]

    def forward(self, chat_log: str, current_date: str) -> List[Dict[str, Any]]:
        """解析聊天紀錄，回傳訂單 dict 陣列（含完整性複查）"""
        result = self.parse(
            chat_log=chat_log,
            current_date=current_date,
            available_items=self.available_items,
            demos=self.examples,
        )
        orders = self._extract_orders(result.orders_json)

        recovered = self._recall_missing(chat_log, current_date, orders)
        if recovered:
            for order in recovered:
                order.setdefault('issues', []).append('第一輪抽取時漏掉，由複查補回')
            orders.extend(recovered)

        return orders

    def _recall_missing(self, chat_log: str, current_date: str,
                        orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """複查漏單，回傳第一輪沒抓到的訂單"""
        summary = '\n'.join(
            f'- {order.get("receiver_name") or "（未填收件人）"}／'
            f'{order.get("giftbox_spec") or order.get("family_spec") or "?"} '
            f'{order.get("giftbox_boxes") or order.get("family_boxes") or "?"}'
            for order in orders
        ) or '（第一輪沒有抽出任何訂單）'

        try:
            result = self.recall(
                chat_log=chat_log,
                current_date=current_date,
                available_items=self.available_items,
                extracted_summary=summary,
            )
            candidates = self._extract_orders(result.missing_orders_json)
        except Exception as error:
            # 複查失敗不該讓整個解析掛掉，第一輪的結果仍然可用
            logger.warning(f'完整性複查失敗，僅回傳第一輪結果：{error}')
            return []

        # 複查有時會把已抽取的訂單再報一次，用收件人＋電話擋掉
        seen = {self._identity(order) for order in orders}
        return [
            c for c in candidates
            if self._identity(c) not in seen and not self._is_empty(c)
        ]

    @staticmethod
    def _is_empty(order: Dict[str, Any]) -> bool:
        """複查偶爾會吐出整筆空白的佔位訂單，直接丟掉

        判定標準：既沒有收件人也沒有任何品項，這種資料沒有任何價值。
        """
        has_receiver = bool((order.get('receiver_name') or '').strip())
        has_item = any(
            order.get(key) for key in ('giftbox_spec', 'giftbox_boxes',
                                       'family_spec', 'family_boxes')
        )
        return not has_receiver and not has_item

    @staticmethod
    def _identity(order: Dict[str, Any]) -> str:
        """訂單識別：收件人 + 電話數字，用來比對複查結果是否重複"""
        name = (order.get('receiver_name') or '').strip()
        phone = ''.join(ch for ch in str(order.get('receiver_phone') or '') if ch.isdigit())
        return f'{name}|{phone}'

    def _extract_orders(self, raw: str) -> List[Dict[str, Any]]:
        """從 LLM 輸出中取出訂單陣列，容忍 markdown code fence 之類的雜訊"""
        if not raw:
            return []

        text = raw.strip()

        # 去掉 ```json ... ``` 包裝
        fence = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # 模型有時會在 JSON 前後多寫幾句話。從第一個 [ 或 { 開始用 raw_decode，
            # 只取第一個完整的 JSON 值，後面多出來的內容忽略掉。
            #
            # 原本這裡用貪婪的 \[.*\] 比對，只要輸出裡還有第二個 ]（多寫一段說明、
            # 或吐出兩個陣列），就會把中間所有東西一起抓進來，然後整批解析失敗。
            starts = [i for i in (text.find('['), text.find('{')) if i >= 0]
            if not starts:
                raise ValueError(f'無法從 LLM 輸出解析出訂單 JSON：{raw[:200]}')
            try:
                parsed, _ = json.JSONDecoder().raw_decode(text[min(starts):])
            except json.JSONDecodeError as error:
                raise ValueError(
                    f'無法從 LLM 輸出解析出訂單 JSON（{error}）：{raw[:200]}'
                ) from error

        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            raise ValueError(f'訂單 JSON 不是陣列格式：{raw[:200]}')

        return [order for order in parsed if isinstance(order, dict)]
