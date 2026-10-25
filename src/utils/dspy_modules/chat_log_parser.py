"""
DSPy module for parsing orders out of chat logs.

How it differs from UnifiedOrderParser:
- UnifiedOrderParser handles the "one message = one order" case
- ChatLogParser handles a whole conversation, where order details are spread
  across many messages, mixed with small talk, amendments and cancellations,
  and there may be several orderers

The output fields map directly onto the columns of the Google Form response
sheet, but items are output only as "spec + quantity"; the actual dropdown
option string is decided by form_options.
"""
import dspy
import json
import logging
import re
from typing import Any, Dict, List

from ..form_options import describe_options

logger = logging.getLogger(__name__)


class ChatLogOrderSignature(dspy.Signature):
    """Extract every confirmed order from a LINE chat log.

    Key rules:
    1. A conversation may contain zero or more orders, and one orderer may send
       to several receivers (gift-giving). Each receiver counts as a separate order.
    2. Order details are often spread over several messages: the address first,
       the quantity a few messages later, the last five digits of the bank
       transfer (匯款末五碼) at the very end. Merge the details that belong to
       the same order.
    3. If the customer later amends the order (quantity, address or date), the
       **latest** statement wins. Do not output orders the customer explicitly
       cancels.
    4. Only "asking about prices, still thinking it over, or saying outright they
       won't order" does not count as an order.
       **As soon as the customer says what they want to buy, it is a confirmed
       order**, even if:
       - they haven't paid yet / say "I'll transfer later" (我等等匯款)
       - the details are incomplete (missing phone, address or date)
       Still output these; record what is missing in issues. Do not drop the
       whole order just because it is incomplete.
    5. Do not guess information that wasn't given. Leave unmentioned fields as an
       empty string and explain in issues.
    6. Better to output too much than to miss one. Missing an order costs far
       more than an extra one.
    7. 「雙雙對對」 is a standalone fixed-bundle item (no 18A/20A spec); do not
       treat it as a spec of 家庭號 (family pack). When an order contains
       「雙雙對對」, fill only shuangshuang_sets and leave
       family_spec/family_boxes as null.
    8. Write the issues entries in Traditional Chinese (they are shown to shop
       staff), as in the examples.
    """
    chat_log = dspy.InputField(desc="Raw LINE chat log; may include timestamps and speaker names")
    current_date = dspy.InputField(desc="Today's date, format: YYYY-MM-DD (星期X), used to resolve relative dates such as 『這週三』 (this Wednesday) or 『下週日』 (next Sunday)")
    available_items = dspy.InputField(desc="List of orderable items; the parsed spec and quantity must fall within this list")
    orders_json = dspy.OutputField(desc=(
        'JSON array of orders. Format of each entry: '
        '{"orderer": "orderer\'s LINE display name", "sender_name": "sender name", "sender_phone": "sender phone", '
        '"sender_address": "sender address", "receiver_name": "receiver name", "receiver_phone": "receiver phone", '
        '"receiver_address": "receiver address", "giftbox_spec": "18A or 20A or null", "giftbox_boxes": number of boxes (盒) or null, '
        '"family_spec": "18A or 20A or null", "family_boxes": number of cases (箱) or null, '
        '"shuangshuang_sets": "number of 雙雙對對 sets (組) or null", "last5": "last five digits of the bank transfer", '
        '"shipping_date": "YYYY-MM-DD or null", "source_quote": "the original message excerpt(s) this order is based on", '
        '"issues": ["anything missing or uncertain"]}'
    ))


class OrderRecallSignature(dspy.Signature):
    """Re-check whether any order was missed.

    In testing, a single extraction pass silently drops orders, and different
    models drop different ones: some miss "the second receiver", others drop
    an entire customer who "said they'd buy but hasn't transferred yet".
    A missed order is the hardest error to notice: a wrong field is visible,
    a vanished order is not. So after extracting, go back and compare once more.

    Be lenient about what counts as "missed": if anyone in the conversation says
    what they want to buy and they are not in the extracted list, it is missed,
    even if they haven't paid or their details are incomplete.
    """
    chat_log = dspy.InputField(desc="Raw LINE chat log")
    current_date = dspy.InputField(desc="Today's date, format: YYYY-MM-DD (星期X)")
    available_items = dspy.InputField(desc="List of orderable items")
    extracted_summary = dspy.InputField(desc="Summary of the orders already extracted in the first pass, one per line as \"receiver／item\"")
    missing_orders_json = dspy.OutputField(desc=(
        'JSON array of the missed orders, in exactly the same format as the first pass. '
        'If you confirm no order was missed, output an empty array []'
    ))


class ChatLogParser(dspy.Module):
    """Chat-log order-parsing module.

    Two passes: extract first, then re-check for missed orders.
    """

    def __init__(self):
        super().__init__()
        self.parse = dspy.ChainOfThought(ChatLogOrderSignature)
        self.recall = dspy.ChainOfThought(OrderRecallSignature)
        self.available_items = describe_options()
        self.examples = self._build_examples()

    def _build_examples(self) -> List[dspy.Example]:
        """Few-shot examples covering cross-message merging, multiple receivers, and amended orders"""
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

        shuangshuang_log = (
            "2026/09/05 08:10\t陳小美\t我要訂雙雙對對兩組\n"
            "2026/09/05 08:11\t陳小美\t陳小美 0912345678 台中市西區台灣大道二段2號\n"
            "2026/09/05 08:12\t陳小美\t末五碼88888 麻煩10號出貨"
        )
        shuangshuang_out = [
            {
                "orderer": "陳小美", "sender_name": "陳小美", "sender_phone": "0912345678",
                "sender_address": "", "receiver_name": "陳小美", "receiver_phone": "0912345678",
                "receiver_address": "台中市西區台灣大道二段2號",
                "giftbox_spec": None, "giftbox_boxes": None,
                "family_spec": None, "family_boxes": None,
                "shuangshuang_sets": 2, "last5": "88888",
                "shipping_date": "2026-09-10",
                "source_quote": "我要訂雙雙對對兩組 / 末五碼88888 麻煩10號出貨",
                "issues": ["寄收件人同一人，依訊息推定"],
            },
        ]

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
            dspy.Example(
                chat_log=shuangshuang_log,
                current_date="2026-09-05 (星期六)",
                available_items=self.available_items,
                orders_json=json.dumps(shuangshuang_out, ensure_ascii=False),
            ).with_inputs("chat_log", "current_date", "available_items"),
        ]

    def forward(self, chat_log: str, current_date: str) -> List[Dict[str, Any]]:
        """Parse the chat log and return a list of order dicts (including the completeness re-check)"""
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
                # Staff-facing note (shown in the preview): "missed in the first pass, recovered by the re-check"
                order.setdefault('issues', []).append('第一輪抽取時漏掉，由複查補回')
            orders.extend(recovered)

        return orders

    def _recall_missing(self, chat_log: str, current_date: str,
                        orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Re-check for missed orders; return the ones the first pass didn't catch"""
        summary = '\n'.join(
            f'- {order.get("receiver_name") or "(no receiver given)"}／'
            f'{order.get("giftbox_spec") or order.get("family_spec") or ("雙雙對對" if order.get("shuangshuang_sets") else "?")} '
            f'{order.get("giftbox_boxes") or order.get("family_boxes") or order.get("shuangshuang_sets") or "?"}'
            for order in orders
        ) or '(the first pass extracted no orders)'

        try:
            result = self.recall(
                chat_log=chat_log,
                current_date=current_date,
                available_items=self.available_items,
                extracted_summary=summary,
            )
            candidates = self._extract_orders(result.missing_orders_json)
        except Exception as error:
            # A failed re-check must not break the whole parse; the first-pass result is still usable
            logger.warning(f'Completeness re-check failed; returning first-pass results only: {error}')
            return []

        # The re-check sometimes reports already-extracted orders again; filter them out by receiver + phone
        seen = {self._identity(order) for order in orders}
        return [
            c for c in candidates
            if self._identity(c) not in seen and not self._is_empty(c)
        ]

    @staticmethod
    def _is_empty(order: Dict[str, Any]) -> bool:
        """The re-check occasionally emits an entirely blank placeholder order; drop it.

        Criterion: no receiver and no item at all; such data is worthless.
        """
        has_receiver = bool((order.get('receiver_name') or '').strip())
        has_item = any(
            order.get(key) for key in ('giftbox_spec', 'giftbox_boxes',
                                       'family_spec', 'family_boxes',
                                       'shuangshuang_sets')
        )
        return not has_receiver and not has_item

    @staticmethod
    def _identity(order: Dict[str, Any]) -> str:
        """Order identity: receiver + phone digits, used to detect duplicates in the re-check results"""
        name = (order.get('receiver_name') or '').strip()
        phone = ''.join(ch for ch in str(order.get('receiver_phone') or '') if ch.isdigit())
        return f'{name}|{phone}'

    def _extract_orders(self, raw: str) -> List[Dict[str, Any]]:
        """Pull the order array out of the LLM output, tolerating noise such as markdown code fences"""
        if not raw:
            return []

        text = raw.strip()

        # Strip a ```json ... ``` wrapper
        fence = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # The model sometimes adds a few sentences before or after the JSON. Use
            # raw_decode starting at the first [ or {, take only the first complete
            # JSON value, and ignore whatever follows.
            #
            # This used to be a greedy \[.*\] match: any second ] in the output (an
            # extra explanation, or two arrays) pulled everything in between into the
            # match and the whole batch failed to parse.
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
