"""
聊天紀錄匯入服務

流程：聊天紀錄 → DSPy/OpenAI 解析 → 規則驗證與品項對照 → 預覽 → 寫入表單回覆試算表

刻意分成「預覽」和「寫入」兩步：聊天紀錄的解析不可能百分之百正確，
有問題的訂單會被標成需人工確認，預設不寫進試算表。
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import dspy

import config

from ..utils.dspy_modules.chat_log_parser import ChatLogParser
from ..utils.form_sheet_client import (
    FormSheetClient,
    dedup_key,
    format_shipping_date,
    format_timestamp,
)
from ..utils import langfuse_tracing as tracing
from ..utils.item_resolver import ItemFields, fields_from_raw, resolve_items
from ..utils.jev_modules.item_judge import ItemJudgeError, JevItemJudge
from ..utils.shipping_days import is_shipping_day, shipping_days_text, weekday_name
from ..utils.taiwan_address import TaiwanAddressNormalizer
from ..utils.text_sanitizer import clean_field, strip_emoji
from ..utils.time_utils import time_utils

logger = logging.getLogger(__name__)

ITEM_JUDGE_BACKENDS = ('gpt', 'shadow', 'jev')

# 推理型模型（o1/o3/o4、gpt-5.x）的 API 參數要求和一般模型不同：
# 不接受 max_tokens（要用 max_completion_tokens），且 temperature 必須是 1.0。
# DSPy 2.6 只認得 o1/o3/o4 開頭，gpt-5.x 要自己處理。
REASONING_MODEL_PATTERN = re.compile(r'^(o[134](-mini)?|gpt-5)', re.IGNORECASE)
REASONING_MAX_TOKENS = 20000


def is_reasoning_model(model: str) -> bool:
    """判斷是否為推理型模型（含供應商前綴時取最後一段）"""
    name = (model or '').split('/')[-1]
    return bool(REASONING_MODEL_PATTERN.match(name))


def build_lm(api_key: str, model: str) -> dspy.LM:
    """Build the DSPy LM, handling the parameter differences of reasoning models"""
    if is_reasoning_model(model):
        # Reasoning models reject max_tokens and require temperature 1.0
        lm = dspy.LM(model=model, api_key=api_key,
                     max_tokens=REASONING_MAX_TOKENS, temperature=1.0)
        # DSPy 2.6 only detects reasoning models by the o1/o3/o4 prefix, not gpt-5.x,
        # so it still puts max_tokens into kwargs; swap in the correct parameter name here.
        lm.kwargs.pop('max_tokens', None)
        lm.kwargs['max_completion_tokens'] = REASONING_MAX_TOKENS
        lm.kwargs['temperature'] = 1.0
        return lm
    return dspy.LM(model=model, api_key=api_key, max_tokens=4000, temperature=0.1)


# 出貨日的定義集中在 shipping_days.py，稽核工具（/offday）共用同一份

@dataclass
class ParsedOrder:
    """一筆解析結果，含要寫入的資料列和需人工確認的原因"""
    order: Dict[str, Any]
    row: List[Any]
    problems: List[str] = field(default_factory=list)
    duplicate: bool = False
    session_id: str = ''

    @property
    def status(self) -> str:
        if self.duplicate:
            return 'duplicate'
        return 'review' if self.problems else 'ready'


class ChatLogImporter:
    """把聊天紀錄轉成表單回覆試算表的資料列"""

    def __init__(self, api_key: str, sheet_id: str, credentials_path: str,
                 model: str = 'gpt-5.6-luna', normalize_addresses: bool = True,
                 item_judge_backend: Optional[str] = None):
        self.model = model
        self.normalize_addresses = normalize_addresses
        self.item_judge_backend, self.item_judge = self._build_item_judge(item_judge_backend)
        # 必須在建立 DSPy 模組之前 instrument，否則抓不到 LM 呼叫
        tracing.setup()
        self._configure_dspy(api_key, model)
        self.parser = ChatLogParser()
        self.address_normalizer = TaiwanAddressNormalizer()
        self.sheet_client = FormSheetClient(credentials_path, sheet_id)

    def _configure_dspy(self, api_key: str, model: str):
        """建立語言模型物件

        不強制走 dspy.settings.configure()——那個只允許最初設定它的執行緒變更，
        在 Flask 這種每個請求跑在工作執行緒的情境下會直接拋錯。
        實際呼叫時一律用 dspy.context 套用（見 parse()），兩種情境都成立。
        """
        self.lm = build_lm(api_key, model)

        try:
            dspy.settings.configure(lm=self.lm)
        except RuntimeError as error:
            logger.debug(f'沿用既有 dspy 全域設定，改由 dspy.context 套用：{error}')

    def parse(self, chat_log: str, now: Optional[datetime] = None) -> List[ParsedOrder]:
        """解析聊天紀錄並產出待寫入的資料列（不寫入試算表）"""
        moment = now or time_utils.get_current_time()
        current_date = time_utils.format_date_with_weekday(moment, 'standard')

        # 先把 emoji 清掉再送進 LLM：省 token，也避免模型直接抄進姓名地址
        raw_chars = len(chat_log)
        chat_log = strip_emoji(chat_log)
        removed = raw_chars - len(chat_log)
        if removed:
            logger.info(f'前處理移除 {removed} 個 emoji／零寬字元')

        # 第一個 trace：LLM 抽取本身。這段是整批共用的，無法歸屬到單一訂單，
        # 所以獨立成一個 trace，不掛任何 session。
        # DSPy 的兩段呼叫（抽取 + 完整性複查）由 DSPyInstrumentor 自動記錄在這底下。
        with tracing.trace(
            'chat-log-parse',
            input_data={'chat_log': chat_log, 'current_date': current_date},
            metadata={'model': self.model, 'chat_log_chars': len(chat_log),
                      'emoji_chars_removed': removed,
                      'normalize_addresses': self.normalize_addresses},
        ) as root:
            with dspy.context(lm=self.lm):
                raw_orders = self.parser(chat_log=chat_log, current_date=current_date)
            logger.info(f'解析出 {len(raw_orders)} 筆訂單')
            root.update(output={'order_count': len(raw_orders), 'orders': raw_orders})

        existing = self.sheet_client.existing_keys()

        results = []
        for raw in raw_orders:
            key = dedup_key(
                _text(raw.get('receiver_name')),
                _text(raw.get('receiver_phone')),
                _text(raw.get('shipping_date')),
            )
            # 一筆訂單一個 session。session 在 Langfuse 是 trace 層級的屬性，
            # 所以每筆訂單必須是獨立的 root trace——掛成子 span 的話，
            # 同一個 trace 只會留下最後一筆的 session，前面的會被覆蓋掉。
            with tracing.trace(
                'order-build',
                session_id=key,
                input_data=raw,
                metadata={'source': 'chat_log', 'model': self.model},
            ) as span:
                parsed = self._build_order(raw, moment, chat_log, current_date)
                parsed.session_id = key

                if key in existing:
                    parsed.duplicate = True
                else:
                    existing.add(key)

                span.update(
                    output=parsed.order,
                    metadata={'status': parsed.status,
                              'problems': parsed.problems,
                              'row': parsed.row},
                )
            results.append(parsed)

        counts = {'ready': 0, 'review': 0, 'duplicate': 0}
        for parsed in results:
            counts[parsed.status] += 1

        # 「可直接寫入的比例」是解析品質最直接的指標，累積起來可以看趨勢
        with tracing.trace('import-summary',
                           input_data={'order_count': len(results)},
                           metadata=counts) as span:
            span.update(output=counts)
            if results:
                tracing.score('ready_ratio', counts['ready'] / len(results),
                              comment=f'{counts["ready"]}/{len(results)} 筆無需人工確認')

        # CLI 跑完就結束行程，不主動送出的話追蹤資料會留在緩衝區裡
        tracing.flush()
        return results

    def _build_order(self, raw: Dict[str, Any], moment: datetime,
                     chat_log: str = '', current_date: str = '') -> ParsedOrder:
        """把 LLM 輸出轉成資料列，同時累積需人工確認的原因"""
        problems = list(raw.get('issues') or [])

        orderer = _text(raw.get('orderer'))
        sender_name = _text(raw.get('sender_name'))
        sender_phone = _text(raw.get('sender_phone'))
        sender_address = _text(raw.get('sender_address'))
        receiver_name = _text(raw.get('receiver_name'))
        receiver_phone = _text(raw.get('receiver_phone'))
        receiver_address = _text(raw.get('receiver_address'))
        last5 = _text(raw.get('last5'))

        # 地址標準化沿用既有規則庫（區域補全、縣市升格等）。
        # 注意：升格規則會把「台北市」寫成「臺北市」，和表單既有資料的寫法不同，
        # 若要和既有資料保持一致，用 --no-normalize-address 關掉。
        if receiver_address:
            receiver_address = self._normalize_address(receiver_address, problems)
        if sender_address:
            sender_address = self._normalize_address(sender_address, problems)

        fields = self._judge_items(raw, receiver_name, problems, chat_log, current_date)
        resolved = resolve_items(fields)
        problems.extend(resolved.problems)
        giftbox, family = resolved.giftbox, resolved.family

        shipping_date = self._resolve_shipping_date(raw.get('shipping_date'), problems, moment)

        # 必填欄位檢查
        if not receiver_name:
            problems.append('缺少收件人')
        if not receiver_phone:
            problems.append('缺少收件人電話')
        if not receiver_address:
            problems.append('缺少收件人地址')
        if not giftbox and not family:
            problems.append('沒有解析出任何品項')

        order = {
            'orderer': orderer,
            'sender_name': sender_name,
            'sender_phone': sender_phone,
            'sender_address': sender_address,
            'receiver_name': receiver_name,
            'receiver_phone': receiver_phone,
            'receiver_address': receiver_address,
            'giftbox': giftbox,
            'family': family,
            'last5': last5,
            'shipping_date': shipping_date,
            'source_quote': _text(raw.get('source_quote')),
        }

        row = [
            format_timestamp(moment),
            orderer,
            sender_name,
            sender_phone,
            sender_address,
            receiver_name,
            receiver_phone,
            receiver_address,
            giftbox or '',
            family or '',
            last5,
            format_shipping_date(shipping_date),
        ]

        return ParsedOrder(order=order, row=row, problems=problems)

    @staticmethod
    def _build_item_judge(backend: Optional[str]):
        """Pick the item judgment source from ITEM_JUDGE_BACKEND

        gpt: use only the five fields from ChatLogParser (current behavior)
        shadow: still use GPT, but also ask Jev and only record whether they agree
        jev: use Jev when it is confident enough, otherwise fall back to GPT
        """
        backend = (backend or config.ITEM_JUDGE_BACKEND or 'gpt').lower()
        if backend not in ITEM_JUDGE_BACKENDS:
            logger.warning(f'Unknown ITEM_JUDGE_BACKEND "{backend}", falling back to gpt')
            return 'gpt', None
        if backend == 'gpt':
            return backend, None
        if not config.TYPESAFE_API_KEY:
            logger.warning(f'ITEM_JUDGE_BACKEND={backend} but TYPESAFE_API_KEY is not set, falling back to gpt')
            return 'gpt', None
        judge = JevItemJudge(
            api_key=config.TYPESAFE_API_KEY,
            model=config.TYPESAFE_MODEL,
            timeout_seconds=config.JEV_TIMEOUT_SECONDS,
            confidence_floor=config.JEV_CONFIDENCE_FLOOR,
        )
        return backend, judge

    def _judge_items(self, raw: Dict[str, Any], receiver_name: str, problems: List[str],
                     chat_log: str, current_date: str) -> ItemFields:
        """Decide this order's five item fields: GPT's answer or Jev's, depending on the backend"""
        gpt_fields = fields_from_raw(raw)
        if self.item_judge is None or not chat_log:
            return gpt_fields

        try:
            judgment = self.item_judge.judge(chat_log, receiver_name or None, current_date)
        except ItemJudgeError as error:
            problems.append(f'Jev 品項判斷失敗，採用 GPT 判斷（{error}）')
            return gpt_fields

        agree = judgment.fields.normalized() == gpt_fields.normalized()
        tracing.score('item_judge_agreement', 1.0 if agree else 0.0,
                      comment=None if agree else
                      f'GPT={gpt_fields.to_dict()} Jev={judgment.fields.to_dict()}')
        if not agree:
            problems.append(
                f'品項判斷兩模型不一致：GPT={_describe_fields(gpt_fields)}，'
                f'Jev={_describe_fields(judgment.fields)}'
            )

        if self.item_judge_backend != 'jev':
            return gpt_fields
        if not judgment.usable:
            problems.append(f'Jev 信心不足（{judgment.confidence:.2f}），採用 GPT 判斷')
            return gpt_fields
        if judgment.confidence < config.JEV_CONFIDENCE_REVIEW:
            problems.append(f'Jev 品項判斷信心 {judgment.confidence:.2f}，請人工確認')
        return judgment.fields

    def _normalize_address(self, address: str, problems: List[str]) -> str:
        if not self.normalize_addresses:
            return address
        with tracing.trace('normalize-address', input_data={'raw': address}) as span:
            try:
                result = self.address_normalizer.normalize_address(address) or address
            except Exception as error:
                logger.warning(f'地址標準化失敗，保留原文：{error}')
                problems.append(f'地址未標準化（{address}）')
                span.update(output=address, metadata={'error': str(error)})
                return address
            span.update(output=result, metadata={'changed': result != address})
            return result

    def _resolve_shipping_date(self, value: Any, problems: List[str],
                               moment: datetime) -> str:
        with tracing.trace('resolve-shipping-date', input_data={'raw': value}) as span:
            before = len(problems)
            result = self._resolve_shipping_date_inner(value, problems, moment)
            span.update(output=result, metadata={'issues': problems[before:]})
            return result

    def _resolve_shipping_date_inner(self, value: Any, problems: List[str],
                                     moment: datetime) -> str:
        text = _text(value)
        if not text:
            problems.append('缺少配送日期')
            return ''

        parsed = None
        for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

        if not parsed:
            problems.append(f'配送日期格式無法辨識（{text}）')
            return text

        if not is_shipping_day(parsed):
            problems.append(f'配送日 {text} 是星期{weekday_name(parsed)}，'
                            f'不是出貨日（僅{shipping_days_text()}）')

        # 出貨日早於今天：多半是模型把「上週三」之類的相對日期算錯年份或算到過去，
        # 也可能是客人真的在講已經出過的那批。只標記不擋，補登舊訂單時還是寫得進去。
        if parsed.date() < moment.date():
            problems.append(f'配送日 {parsed.strftime("%Y-%m-%d")} 已經過去'
                            f'（今天 {moment.strftime("%Y-%m-%d")}）')

        return parsed.strftime('%Y-%m-%d')

    def write(self, parsed_orders: List[ParsedOrder],
              include_review: bool = False) -> Dict[str, Any]:
        """把訂單寫入試算表，預設只寫沒有問題的那些"""
        column_check = self.sheet_client.verify_columns()
        if not column_check['ok']:
            return {
                'success': False,
                'error': column_check['error'],
                'mismatches': column_check.get('mismatches', []),
            }

        allowed = {'ready', 'review'} if include_review else {'ready'}
        to_write = [p for p in parsed_orders if p.status in allowed]

        if not to_write:
            return {'success': True, 'appended_rows': 0, 'skipped': len(parsed_orders)}

        # 每筆訂單各自記一個 span 並掛回自己的 session，
        # 這樣在 Langfuse 上點開一筆訂單的 session 就能看到「它是什麼時候被寫進去的」
        for parsed in to_write:
            with tracing.trace('write-to-sheet',
                               session_id=parsed.session_id,
                               input_data=parsed.order,
                               metadata={'status': parsed.status}) as span:
                span.update(output={'row': parsed.row})

        result = self.sheet_client.append_rows([p.row for p in to_write])
        result['skipped'] = len(parsed_orders) - len(to_write)

        with tracing.trace('sheet-append-batch',
                           input_data={'rows': len(to_write)},
                           metadata=result) as span:
            span.update(output=result)

        tracing.flush()
        return result


def _describe_fields(fields: ItemFields) -> str:
    """Short Chinese summary of the item fields, used in problem messages shown to the shop owner"""
    parts = []
    if fields.giftbox_spec or fields.giftbox_boxes:
        parts.append(f'禮盒{fields.giftbox_spec or "?"}×{fields.giftbox_boxes or "?"}')
    if fields.family_spec or fields.family_boxes:
        parts.append(f'家庭號{fields.family_spec or "?"}×{fields.family_boxes or "?"}')
    if fields.shuangshuang_sets:
        parts.append(f'雙雙對對×{fields.shuangshuang_sets}')
    return '、'.join(parts) or '無'


def _text(value: Any) -> str:
    """把 None / 非字串統一成去頭尾空白的字串，並清掉 emoji

    模型偶爾會把聊天紀錄裡的 emoji 一起抄進姓名或地址，
    寫進試算表會變髒資料，也會害重複檢查比對不到，所以每個欄位都清一次。
    """
    return clean_field(value)
