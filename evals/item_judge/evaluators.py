"""
Scoring functions for the A/B experiment

item-level: whether each order's gift box column, family pack column, whole order and five fields
are correct, plus latency, cost and errors.
run-level: overall and per-category accuracy, latency distribution, total cost, and for Jev,
accuracy per confidence bucket.
"""

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional

from langfuse import Evaluation

from src.utils.item_resolver import ItemFields


def _exact(name: str, got: Any, expected: Any) -> Evaluation:
    ok = got == expected
    return Evaluation(name=name, value=1.0 if ok else 0.0,
                      comment=None if ok else f'expected={expected!r} got={got!r}')


def _expected_fields(expected_output: Dict[str, Any]) -> Dict[str, Any]:
    return ItemFields(**expected_output['fields']).normalized().to_dict()


def item_evaluator(*, input, output, expected_output, metadata=None, **kwargs) -> List[Evaluation]:
    evaluations = [
        _exact('giftbox_exact', output['giftbox'], expected_output['giftbox']),
        _exact('family_exact', output['family'], expected_output['family']),
        _exact('order_exact',
               (output['giftbox'], output['family']),
               (expected_output['giftbox'], expected_output['family'])),
        _exact('fields_exact', output['fields'], _expected_fields(expected_output)),
        Evaluation(name='latency_ms', value=round(output.get('latency_ms') or 0.0, 1)),
        Evaluation(name='input_tokens', value=output.get('input_tokens') or 0),
        Evaluation(name='errored', value=1.0 if output.get('error') else 0.0,
                   comment=output.get('error')),
    ]
    cost = output.get('cost_usd')
    evaluations.append(Evaluation(name='cost_usd', value=cost or 0.0,
                                  comment=None if cost is not None else 'cost unknown'))
    if output.get('confidence') is not None:
        evaluations.append(Evaluation(name='confidence', value=output['confidence']))
    return evaluations


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Each row: {'category', 'scores': {name: value}, 'output': {...}}; split out for unit tests"""
    def mean(values):
        values = list(values)
        return sum(values) / len(values) if values else float('nan')

    def p95(values):
        values = sorted(values)
        if not values:
            return float('nan')
        return values[min(len(values) - 1, math.ceil(0.95 * len(values)) - 1)]

    summary: Dict[str, float] = {}
    for key in ('order_exact', 'giftbox_exact', 'family_exact', 'fields_exact'):
        summary[f'accuracy_{key.removesuffix("_exact")}'] = mean(r['scores'][key] for r in rows)

    by_category = defaultdict(list)
    for row in rows:
        by_category[row['category']].append(row['scores']['order_exact'])
    for category, values in sorted(by_category.items()):
        summary[f'accuracy_by_category:{category}'] = mean(values)

    latencies = [r['output'].get('latency_ms') or 0.0 for r in rows]
    summary['latency_ms_mean'] = mean(latencies)
    summary['latency_ms_p95'] = p95(latencies)
    costs = [r['output'].get('cost_usd') or 0.0 for r in rows]
    summary['cost_usd_total'] = sum(costs)
    summary['cost_usd_per_item'] = mean(costs)
    summary['input_tokens_mean'] = mean(r['output'].get('input_tokens') or 0 for r in rows)
    summary['error_rate'] = mean(1.0 if r['output'].get('error') else 0.0 for r in rows)

    confident = [r for r in rows if r['output'].get('confidence') is not None]
    if confident:
        usable = [r for r in confident if r['output'].get('usable')]
        summary['unusable_rate'] = 1 - len(usable) / len(confident)
        summary['accuracy_when_usable'] = mean(r['scores']['order_exact'] for r in usable)
        buckets = {'<0.5': (0, 0.5), '0.5-0.8': (0.5, 0.8), '>=0.8': (0.8, 1.01)}
        for label, (low, high) in buckets.items():
            hits = [r['scores']['order_exact'] for r in confident
                    if low <= r['output']['confidence'] < high]
            if hits:
                summary[f'confidence_bucket_accuracy:{label}'] = mean(hits)
                summary[f'confidence_bucket_count:{label}'] = len(hits)

    return {k: v for k, v in summary.items() if not (isinstance(v, float) and math.isnan(v))}


def _metadata(item) -> Dict[str, Any]:
    metadata = getattr(item, 'metadata', None)
    if metadata is None and isinstance(item, dict):
        metadata = item.get('metadata')
    return metadata or {}


def run_evaluator(*, item_results, **kwargs) -> List[Evaluation]:
    rows = []
    for result in item_results:
        if result.output is None:
            continue
        rows.append({
            'category': _metadata(result.item).get('category', 'unknown'),
            'scores': {e.name: e.value for e in result.evaluations},
            'output': result.output,
        })
    return [Evaluation(name=name, value=round(value, 6)) for name, value in summarize(rows).items()]


def format_summary(evaluations: List[Evaluation], title: Optional[str] = None) -> str:
    lines = [title] if title else []
    lines += [f'{e.name:<40} {e.value}' for e in evaluations]
    return '\n'.join(lines)
