"""
Jev item judgment module

Judges "what did this recipient finally order" from a chat log: category x spec x quantity.
Jev is a decision model and does not generate text, so the judgment is split into several
closed-option questions sent in one request. Code then assembles the answers back into the same
five fields ChatLogParser produces (ItemFields), and item_resolver maps them to form option strings.

Design: docs/plans/jev-item-judgment.md §2.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from typesafe_sdk import SystemOneResponse, TypeSafeClient, TypeSafeError

from .. import langfuse_tracing as tracing
from ..form_options import MAX_FAMILY_BOXES, MAX_GIFTBOX_BOXES, MAX_SHUANGSHUANG_SETS
from ..item_resolver import ItemFields

logger = logging.getLogger(__name__)

# Pricing: https://docs.typesafe.ai/models (input $0.042 per million tokens, output is free)
JEV_USD_PER_INPUT_TOKEN = 0.042 / 1_000_000

IS_ORDER_THRESHOLD = 0.5

NONE = 'none'
UNSPECIFIED = 'unspecified'
SPECS = ('18A', '20A')

# Over the limit maps to "limit + 1" so the resolver takes its existing
# "exceeds the form's maximum, split the order" path
OVER_LIMIT = {
    'giftbox_boxes': MAX_GIFTBOX_BOXES + 1,
    'family_boxes': MAX_FAMILY_BOXES + 1,
    'shuangshuang_sets': MAX_SHUANGSHUANG_SETS + 1,
}


def _quantity_criteria(max_count: int, unit: str, none_text: str) -> Dict[str, Optional[str]]:
    criteria: Dict[str, Optional[str]] = {NONE: none_text}
    criteria.update({str(n): f'{n}{unit}' for n in range(1, max_count + 1)})
    criteria[f'more_than_{max_count}'] = f'超過 {max_count}{unit}'
    return criteria


# Question text per language. Chinese is the default; English is an A/B variant because
# TypeSafe reports its best accuracy in English. The chat log in the state stays Chinese either way.
_TEXT = {
    'zh': {
        'is_order': (
            '針對 `focus_receiver` 這位收件人，客人有沒有明確說出要買什麼品項或數量？'
            '只是詢價、還在考慮、說再想想，或最後明確取消，都算沒有。',
            {'true': '已講出要買的品項或數量，而且沒有取消', 'false': '只詢價、考慮中、閒聊或已取消'},
        ),
        'giftbox_boxes': '`focus_receiver` 最終要訂幾盒「精選禮盒」？改單以最後一次的說法為準，加購要累加。沒有訂禮盒選 none。',
        'giftbox_spec': '`focus_receiver` 訂的精選禮盒是哪個規格？沒訂禮盒或沒講規格選 unspecified。',
        'family_boxes': '`focus_receiver` 最終要訂幾箱「家庭號」？不包含雙雙對對。改單以最後一次的說法為準。沒有訂家庭號選 none。',
        'family_spec': '`focus_receiver` 訂的家庭號是哪個規格？沒訂家庭號或沒講規格選 unspecified。',
        'shuangshuang_sets': '`focus_receiver` 最終要訂幾組「雙雙對對」？改單以最後一次的說法為準。沒有訂選 none。',
        'amended': '客人在對話中有沒有改過品項、規格或數量？',
        'none_giftbox': '沒有訂精選禮盒',
        'none_family': '沒有訂家庭號',
        'none_shuangshuang': '沒有訂雙雙對對',
        'unspecified': '沒有訂這個品項，或沒講規格',
    },
    'en': {
        'is_order': (
            'For the recipient named in `focus_receiver`, did the customer clearly state an item or '
            'quantity they want to buy? Only asking about prices, still considering, or finally '
            'cancelling all count as no.',
            {'true': 'Stated the item or quantity to buy, and did not cancel',
             'false': 'Only asked prices, still considering, chit-chat, or cancelled'},
        ),
        'giftbox_boxes': 'How many boxes of "精選禮盒" (gift box) does `focus_receiver` finally order? '
                         'If the customer amended the order, use the last statement; add-ons accumulate. '
                         'Choose none if no gift box was ordered.',
        'giftbox_spec': 'Which size spec is the "精選禮盒" (gift box) for `focus_receiver`? '
                        'Choose unspecified if no gift box was ordered or no spec was mentioned.',
        'family_boxes': 'How many cases of "家庭號" (family pack) does `focus_receiver` finally order? '
                        'Do not count "雙雙對對". Use the last statement if amended. '
                        'Choose none if no family pack was ordered.',
        'family_spec': 'Which size spec is the "家庭號" (family pack) for `focus_receiver`? '
                       'Choose unspecified if no family pack was ordered or no spec was mentioned.',
        'shuangshuang_sets': 'How many sets of "雙雙對對" does `focus_receiver` finally order? '
                             'Use the last statement if amended. Choose none if not ordered.',
        'amended': 'Did the customer change the item, spec, or quantity during the conversation?',
        'none_giftbox': 'No gift box ordered',
        'none_family': 'No family pack ordered',
        'none_shuangshuang': 'No 雙雙對對 ordered',
        'unspecified': 'Item not ordered, or spec not mentioned',
    },
}


def build_state(chat_log: str, receiver_name: Optional[str], current_date: str) -> Dict[str, Any]:
    """The state Jev sees: the whole chat log, the recipient to focus on, and an item catalog
    generated from form_options. The values are Chinese because the chat logs are Chinese."""
    return {
        'chat_log': chat_log,
        'focus_receiver': receiver_name or '（整段對話只有一位客人，就是他本人或他指定的收件人）',
        'current_date': current_date,
        'catalog': {
            '精選禮盒': f'一盒 6 顆，規格 18A 或 20A，可訂 1 到 {MAX_GIFTBOX_BOXES} 盒。客人常寫「禮盒」「盒」。',
            '家庭號': f'一箱兩層 12 顆，規格 18A 或 20A，可訂 1 到 {MAX_FAMILY_BOXES} 箱。客人常寫「家庭號」「箱」。',
            '雙雙對對': f'固定組合的獨立品項，不分規格，可訂 1 到 {MAX_SHUANGSHUANG_SETS} 組。客人常寫「雙雙對對」「雙雙」。',
        },
        'rules': [
            '同一位收件人若後來改數量或改品項，以最後一次的說法為準。',
            '「再加一盒」這類加購要和原本的數量累加。',
            '明確說取消的品項視為沒有訂購。',
            '只是詢價、還在考慮、說再想想，都不算訂購。',
            '「兩盒」「2盒」「二盒」「x2」「*2」都是 2。',
        ],
    }


def build_questions(lang: str = 'zh') -> Dict[str, Dict[str, Any]]:
    """Seven independent questions sent in one request (as the dict form the SDK accepts,
    so they can be logged to tracing as is)"""
    text = _TEXT[lang]
    spec_criteria = {spec: None for spec in SPECS}
    spec_criteria[UNSPECIFIED] = text['unspecified']
    is_order_instructions, is_order_criteria = text['is_order']

    return {
        'is_order': {'type': 'noul', 'instructions': is_order_instructions,
                     'criteria': is_order_criteria},
        'giftbox_boxes': {'type': 'choice', 'instructions': text['giftbox_boxes'],
                          'criteria': _quantity_criteria(MAX_GIFTBOX_BOXES, '盒', text['none_giftbox'])},
        'giftbox_spec': {'type': 'choice', 'instructions': text['giftbox_spec'],
                         'criteria': dict(spec_criteria)},
        'family_boxes': {'type': 'choice', 'instructions': text['family_boxes'],
                         'criteria': _quantity_criteria(MAX_FAMILY_BOXES, '箱', text['none_family'])},
        'family_spec': {'type': 'choice', 'instructions': text['family_spec'],
                        'criteria': dict(spec_criteria)},
        'shuangshuang_sets': {'type': 'choice', 'instructions': text['shuangshuang_sets'],
                              'criteria': _quantity_criteria(MAX_SHUANGSHUANG_SETS, '組', text['none_shuangshuang'])},
        'amended': {'type': 'noul', 'instructions': text['amended']},
    }


@dataclass(frozen=True)
class ItemJudgment:
    fields: ItemFields
    confidence: float                 # lowest confidence among the questions that affect the answer
    usable: bool                      # confidence >= confidence_floor
    is_order: float                   # raw Noul yes-probability
    amended: float
    answers: Dict[str, Dict[str, Any]]
    issues: List[str] = field(default_factory=list)
    model: str = ''
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0


class ItemJudgeError(Exception):
    """A Jev call failed (connection, timeout, rate limit, auth...); callers only need to catch this"""


class JevItemJudge:
    """Judge one recipient's final items with Jev"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 client: Optional[TypeSafeClient] = None, timeout_seconds: float = 10.0,
                 confidence_floor: float = 0.5, lang: str = 'zh'):
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.confidence_floor = confidence_floor
        self.lang = lang
        self._client = client or TypeSafeClient(api_key=api_key, model=model)

    def judge(self, chat_log: str, receiver_name: Optional[str] = None,
              current_date: str = '') -> ItemJudgment:
        state = build_state(chat_log, receiver_name, current_date)
        questions = build_questions(self.lang)

        with tracing.generation(
            'jev-item-judge',
            model=self.model or 'jev-latest',
            input_data={'state': state, 'questions': questions},
            metadata={'backend': 'jev', 'receiver_name': receiver_name, 'lang': self.lang},
        ) as span:
            started = time.perf_counter()
            try:
                response = self._client.system_one(
                    state=state, questions=questions, timeout=self.timeout_seconds)
            except TypeSafeError as error:
                span.update(level='ERROR', status_message=f'{type(error).__name__}: {error}')
                raise ItemJudgeError(f'{type(error).__name__}: {error}') from error
            latency_ms = (time.perf_counter() - started) * 1000

            judgment = self._compose(response, latency_ms)
            span.update(
                model=judgment.model,
                output={'fields': judgment.fields.to_dict(), 'confidence': judgment.confidence,
                        'usable': judgment.usable, 'answers': judgment.answers,
                        'issues': judgment.issues},
                usage_details={'input': judgment.input_tokens, 'output': judgment.output_tokens},
                cost_details={'input': judgment.cost_usd, 'total': judgment.cost_usd},
                metadata={'latency_ms': round(latency_ms, 1), 'confidence': judgment.confidence,
                          'usable': judgment.usable},
                level=None if judgment.usable else 'WARNING',
            )
        return judgment

    def close(self):
        self._client.close()

    def _compose(self, response: SystemOneResponse, latency_ms: float) -> ItemJudgment:
        """Assemble Jev's answers into the five fields; plain code, no further model calls"""
        choices, nouls = response.choices, response.nouls
        answers = {
            name: ({'noul': answer.noul} if answer.type == 'noul' else
                   {'choice': answer.choice, 'confidence': answer.confidence,
                    'probabilities': answer.probabilities})
            for name, answer in response.answers.items()
        }

        is_order = nouls['is_order'].noul
        amended = nouls['amended'].noul
        issues: List[str] = []
        # A Noul has no confidence; convert its distance from 0.5 into 0-1
        confidences = [abs(is_order - 0.5) * 2]

        if is_order < IS_ORDER_THRESHOLD:
            fields = ItemFields()
            issues.append('Jev judged this is not an order')
        else:
            values: Dict[str, Any] = {}
            for quantity_key, spec_key in (('giftbox_boxes', 'giftbox_spec'),
                                           ('family_boxes', 'family_spec'),
                                           ('shuangshuang_sets', None)):
                answer = choices[quantity_key]
                confidences.append(answer.confidence)
                if answer.choice == NONE:
                    continue
                values[quantity_key] = (OVER_LIMIT[quantity_key]
                                        if answer.choice.startswith('more_than_')
                                        else int(answer.choice))
                if spec_key:
                    spec = choices[spec_key]
                    confidences.append(spec.confidence)
                    values[spec_key] = None if spec.choice == UNSPECIFIED else spec.choice
            fields = ItemFields(**values)

        if amended >= 0.5:
            issues.append('Jev judged the customer amended the order')

        confidence = round(min(confidences), 4)
        input_tokens = response.usage.input_tokens or 0
        return ItemJudgment(
            fields=fields,
            confidence=confidence,
            usable=confidence >= self.confidence_floor,
            is_order=is_order,
            amended=amended,
            answers=answers,
            issues=issues,
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=response.usage.output_tokens or 0,
            latency_ms=latency_ms,
            cost_usd=input_tokens * JEV_USD_PER_INPUT_TOKEN,
        )
