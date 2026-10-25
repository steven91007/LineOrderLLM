"""
Task functions for the A/B experiment: same dataset item in, same output format out

GPT: runs the full ChatLogParser (extraction + recall pass) and takes the target recipient's
     five fields, because that is how production gets its item fields; latency and cost are
     measured for the whole thing too.
Jev: JevItemJudge reads the whole chat log and judges the five fields, independent of any GPT output.

Both end with item_resolver.resolve_items to get form option strings.
"""

import time
from typing import Any, Callable, Dict, List, Optional

import dspy
import litellm
from dspy.utils.usage_tracker import track_usage

from src.utils.dspy_modules.chat_log_parser import ChatLogParser
from src.utils.item_resolver import ItemFields, fields_from_raw, resolve_items
from src.utils.jev_modules.item_judge import ItemJudgeError, JevItemJudge
from src.utils.text_sanitizer import strip_emoji


def _input(item) -> Dict[str, Any]:
    """Langfuse dataset items are objects, local --limit runs pass dicts; accept both"""
    return item['input'] if isinstance(item, dict) else item.input


def _output(fields: ItemFields, **extra) -> Dict[str, Any]:
    resolved = resolve_items(fields)
    return {
        'giftbox': resolved.giftbox,
        'family': resolved.family,
        'fields': fields.normalized().to_dict(),
        'problems': resolved.problems,
        'error': None,
        **extra,
    }


def _error_output(error: Exception, **extra) -> Dict[str, Any]:
    output = _output(ItemFields(), **extra)
    output['error'] = f'{type(error).__name__}: {error}'
    return output


def pick_order(orders: List[Dict[str, Any]], receiver_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Pick the GPT order to compare: the one matching receiver_name if given, otherwise the first"""
    if not orders:
        return None
    if receiver_name:
        target = receiver_name.replace(' ', '')
        for order in orders:
            name = str(order.get('receiver_name') or '').replace(' ', '')
            if name and (name == target or target in name or name in target):
                return order
        return None
    return orders[0]


def _gpt_cost(model: str, usage: Dict[str, Dict[str, Any]]) -> Optional[float]:
    """Compute cost from litellm's price table; None for unknown models"""
    total = 0.0
    for lm_model, entry in usage.items():
        prices = litellm.model_cost.get(lm_model) or litellm.model_cost.get(lm_model.split('/')[-1])
        if not prices:
            return None
        total += (entry.get('prompt_tokens') or 0) * prices['input_cost_per_token']
        total += (entry.get('completion_tokens') or 0) * prices['output_cost_per_token']
    return total


def make_gpt_task(lm: dspy.LM, model: str) -> Callable:
    parser = ChatLogParser()

    def task(*, item, **kwargs) -> Dict[str, Any]:
        data = _input(item)
        meta = {'backend': 'gpt', 'model': model, 'confidence': None, 'usable': None}
        started = time.perf_counter()
        try:
            # track_usage and dspy.context are thread-local, so concurrent items are counted separately
            with dspy.context(lm=lm), track_usage() as tracker:
                orders = parser(chat_log=strip_emoji(data['chat_log']),
                                current_date=data['current_date'])
        except Exception as error:
            return _error_output(error, latency_ms=(time.perf_counter() - started) * 1000,
                                 input_tokens=0, output_tokens=0, cost_usd=None,
                                 order_count=None, **meta)
        latency_ms = (time.perf_counter() - started) * 1000

        usage = tracker.get_total_tokens()
        order = pick_order(orders, data.get('receiver_name'))
        fields = fields_from_raw(order) if order else ItemFields()
        return _output(
            fields,
            latency_ms=latency_ms,
            input_tokens=sum(u.get('prompt_tokens') or 0 for u in usage.values()),
            output_tokens=sum(u.get('completion_tokens') or 0 for u in usage.values()),
            cost_usd=_gpt_cost(model, usage),
            order_count=len(orders),
            **meta,
        )

    return task


def make_jev_task(judge: JevItemJudge) -> Callable:
    def task(*, item, **kwargs) -> Dict[str, Any]:
        data = _input(item)
        meta = {'backend': 'jev', 'order_count': None}
        started = time.perf_counter()
        try:
            judgment = judge.judge(strip_emoji(data['chat_log']), data.get('receiver_name'),
                                   data['current_date'])
        except ItemJudgeError as error:
            return _error_output(error, latency_ms=(time.perf_counter() - started) * 1000,
                                 input_tokens=0, output_tokens=0, cost_usd=None,
                                 model=judge.model, confidence=None, usable=None, **meta)
        return _output(
            judgment.fields,
            latency_ms=judgment.latency_ms,
            input_tokens=judgment.input_tokens,
            output_tokens=judgment.output_tokens,
            cost_usd=judgment.cost_usd,
            model=judgment.model,
            confidence=judgment.confidence,
            usable=judgment.usable,
            jev_issues=judgment.issues,
            **meta,
        )

    return task
