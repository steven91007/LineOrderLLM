"""
Chat log import service

Flow: chat log → DSPy/OpenAI parsing → rule validation and item mapping → preview → write to the form-response spreadsheet

Preview and write are deliberately separate steps: chat log parsing can never be 100% correct,
so orders with problems are flagged for manual review and are not written to the spreadsheet by default.
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

# Reasoning models (o1/o3/o4, gpt-5.x) take different API parameters from regular models:
# they reject max_tokens (max_completion_tokens is required) and temperature must be 1.0.
# DSPy 2.6 only recognizes the o1/o3/o4 prefixes, so gpt-5.x has to be handled here.
REASONING_MODEL_PATTERN = re.compile(r'^(o[134](-mini)?|gpt-5)', re.IGNORECASE)
REASONING_MAX_TOKENS = 20000


def is_reasoning_model(model: str) -> bool:
    """Return whether the model is a reasoning model (uses the last segment when a provider prefix is present)"""
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


# Shipping days are defined in one place, shipping_days.py, shared with the audit tool (/offday)

@dataclass
class ParsedOrder:
    """One parse result: the row to write plus the reasons it needs manual review"""
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
    """Turn a chat log into rows for the form-response spreadsheet"""

    def __init__(self, api_key: str, sheet_id: str, credentials_path: str,
                 model: str = 'gpt-5.6-luna', normalize_addresses: bool = True,
                 item_judge_backend: Optional[str] = None):
        self.model = model
        self.normalize_addresses = normalize_addresses
        self.item_judge_backend, self.item_judge = self._build_item_judge(item_judge_backend)
        # Must instrument before the DSPy modules are created, otherwise LM calls are not captured
        tracing.setup()
        self._configure_dspy(api_key, model)
        self.parser = ChatLogParser()
        self.address_normalizer = TaiwanAddressNormalizer()
        self.sheet_client = FormSheetClient(credentials_path, sheet_id)

    def _configure_dspy(self, api_key: str, model: str):
        """Build the language model object

        Does not rely on dspy.settings.configure(): only the thread that first configured it may change it,
        so it raises under Flask, where each request runs on a worker thread.
        Calls always apply the LM via dspy.context instead (see parse()), which works in both cases.
        """
        self.lm = build_lm(api_key, model)

        try:
            dspy.settings.configure(lm=self.lm)
        except RuntimeError as error:
            logger.debug(f'Keeping the existing global dspy settings; applying the LM via dspy.context instead: {error}')

    def parse(self, chat_log: str, now: Optional[datetime] = None) -> List[ParsedOrder]:
        """Parse a chat log and produce the rows to write (does not write to the spreadsheet)"""
        moment = now or time_utils.get_current_time()
        current_date = time_utils.format_date_with_weekday(moment, 'standard')

        # Strip emoji before sending to the LLM: saves tokens and keeps the model from copying them into names and addresses
        raw_chars = len(chat_log)
        chat_log = strip_emoji(chat_log)
        removed = raw_chars - len(chat_log)
        if removed:
            logger.info(f'Pre-processing removed {removed} emoji/zero-width characters')

        # First trace: the LLM extraction itself. It is shared by the whole batch and cannot be attributed to a single order,
        # so it gets its own trace with no session.
        # DSPy's two calls (extraction + completeness re-check) are recorded under it automatically by DSPyInstrumentor.
        with tracing.trace(
            'chat-log-parse',
            input_data={'chat_log': chat_log, 'current_date': current_date},
            metadata={'model': self.model, 'chat_log_chars': len(chat_log),
                      'emoji_chars_removed': removed,
                      'normalize_addresses': self.normalize_addresses},
        ) as root:
            with dspy.context(lm=self.lm):
                raw_orders = self.parser(chat_log=chat_log, current_date=current_date)
            logger.info(f'Parsed {len(raw_orders)} orders')
            root.update(output={'order_count': len(raw_orders), 'orders': raw_orders})

        existing = self.sheet_client.existing_keys()

        results = []
        for raw in raw_orders:
            key = dedup_key(
                _text(raw.get('receiver_name')),
                _text(raw.get('receiver_phone')),
                _text(raw.get('shipping_date')),
            )
            # One session per order. In Langfuse, session is a trace-level attribute,
            # so each order must be its own root trace: as child spans,
            # the trace would keep only the last order's session and overwrite the earlier ones.
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

        # The share of orders that can be written directly is the most direct measure of parse quality; tracked over time it shows the trend
        with tracing.trace('import-summary',
                           input_data={'order_count': len(results)},
                           metadata=counts) as span:
            span.update(output=counts)
            if results:
                tracing.score('ready_ratio', counts['ready'] / len(results),
                              comment=f'{counts["ready"]}/{len(results)} need no manual review')

        # The CLI process exits right after running; without an explicit flush the tracing data stays in the buffer
        tracing.flush()
        return results

    def _build_order(self, raw: Dict[str, Any], moment: datetime,
                     chat_log: str = '', current_date: str = '') -> ParsedOrder:
        """Turn LLM output into a row while collecting the reasons it needs manual review"""
        problems = list(raw.get('issues') or [])

        orderer = _text(raw.get('orderer'))
        sender_name = _text(raw.get('sender_name'))
        sender_phone = _text(raw.get('sender_phone'))
        sender_address = _text(raw.get('sender_address'))
        receiver_name = _text(raw.get('receiver_name'))
        receiver_phone = _text(raw.get('receiver_phone'))
        receiver_address = _text(raw.get('receiver_address'))
        last5 = _text(raw.get('last5'))

        # Address normalization reuses the existing rule base (district completion, county-to-city upgrades, etc.).
        # Note: the upgrade rules write "台北市" as "臺北市", which differs from how existing form data spells it;
        # to stay consistent with existing data, turn it off with --no-normalize-address.
        if receiver_address:
            receiver_address = self._normalize_address(receiver_address, problems)
        if sender_address:
            sender_address = self._normalize_address(sender_address, problems)

        fields = self._judge_items(raw, receiver_name, problems, chat_log, current_date)
        resolved = resolve_items(fields)
        problems.extend(resolved.problems)
        giftbox, family = resolved.giftbox, resolved.family

        shipping_date = self._resolve_shipping_date(raw.get('shipping_date'), problems, moment)

        # Required-field checks
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
                logger.warning(f'Address normalization failed, keeping the original text: {error}')
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

        # Shipping date before today: usually the model resolved a relative date like "上週三" (last Wednesday) to the wrong year or into the past,
        # but the customer may really be talking about a batch that already shipped. Flag it without blocking, so back-filled old orders can still be written.
        if parsed.date() < moment.date():
            problems.append(f'配送日 {parsed.strftime("%Y-%m-%d")} 已經過去'
                            f'（今天 {moment.strftime("%Y-%m-%d")}）')

        return parsed.strftime('%Y-%m-%d')

    def write(self, parsed_orders: List[ParsedOrder],
              include_review: bool = False) -> Dict[str, Any]:
        """Write orders to the spreadsheet; by default only those without problems"""
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

        # Record one span per order and attach it to that order's own session,
        # so opening an order's session in Langfuse shows when it was written
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
    """Normalize None / non-strings to a stripped string and remove emoji

    The model occasionally copies emoji from the chat log into names or addresses,
    which dirties the spreadsheet and breaks duplicate detection, so every field is cleaned.
    """
    return clean_field(value)
