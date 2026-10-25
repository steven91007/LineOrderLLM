"""
Item judgment A/B experiment: GPT (ChatLogParser) vs Jev, one run each on the same Langfuse dataset

Usage:
  uv run python scripts/run_item_judge_ab.py --backend gpt [--model gpt-5.6-luna] [--tag a]
  uv run python scripts/run_item_judge_ab.py --backend jev [--lang zh|en] [--tag a]
  Add --limit 3 to run only the first few items locally (no dataset run) to check the flow and traces

In Langfuse: Datasets -> item-judge-v1 -> Runs, select two runs and click Compare.
"""
import argparse
import os
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from langfuse import get_client

from evals.item_judge.evaluators import format_summary, item_evaluator, run_evaluator
from evals.item_judge.schema import load_items
from evals.item_judge.tasks import make_gpt_task, make_jev_task
from src.services.chat_log_importer import build_lm
from src.utils import langfuse_tracing as tracing
from src.utils.jev_modules.item_judge import JevItemJudge

DEFAULT_CONCURRENCY = {'gpt': 3, 'jev': 8}


def git_sha() -> str:
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
    except Exception:
        return 'unknown'


def main() -> int:
    parser = argparse.ArgumentParser(description='Item judgment A/B experiment')
    parser.add_argument('--backend', choices=('gpt', 'jev'), required=True)
    parser.add_argument('--dataset', default='item-judge-v1')
    parser.add_argument('--model', help='GPT defaults to config.DSPY_MODEL; Jev defaults to config.TYPESAFE_MODEL')
    parser.add_argument('--lang', choices=('zh', 'en'), default='zh', help='Language of the Jev questions')
    parser.add_argument('--concurrency', type=int)
    parser.add_argument('--tag', default='a', help='Distinguishes run names when re-running on the same day')
    parser.add_argument('--limit', type=int, help='Run only the first N items locally, without creating a dataset run')
    args = parser.parse_args()

    # Must be enabled before building DSPy modules so DSPy and Jev calls land in the experiment traces
    if not tracing.setup():
        print('❌ Langfuse is not enabled, cannot record the experiment')
        return 1

    if args.backend == 'gpt':
        model = args.model or config.DSPY_MODEL
        lm = build_lm(config.DSPY_API_KEY, model)
        # The A/B measures real latency and cost and is re-run to see variance, so disable the DSPy cache
        lm.cache = False
        lm.cache_in_memory = False
        task = make_gpt_task(lm, model)
        run_model = model
    else:
        judge = JevItemJudge(api_key=config.TYPESAFE_API_KEY, model=args.model or config.TYPESAFE_MODEL,
                             timeout_seconds=config.JEV_TIMEOUT_SECONDS,
                             confidence_floor=config.JEV_CONFIDENCE_FLOOR, lang=args.lang)
        task = make_jev_task(judge)
        run_model = f'{args.model or config.TYPESAFE_MODEL or "jev-latest"}-{args.lang}'

    run_name = f'{args.backend}__{run_model}__{date.today().isoformat()}{args.tag}'
    metadata = {
        'backend': args.backend, 'model': run_model, 'lang': args.lang,
        'confidence_floor': str(config.JEV_CONFIDENCE_FLOOR), 'git_sha': git_sha(),
        'dataset': args.dataset,
    }
    common = dict(
        name='item-judge',
        run_name=run_name,
        description=f'Item judgment A/B: {args.backend} ({run_model})',
        task=task,
        evaluators=[item_evaluator],
        run_evaluators=[run_evaluator],
        max_concurrency=args.concurrency or DEFAULT_CONCURRENCY[args.backend],
        metadata=metadata,
    )

    langfuse = get_client()
    if args.limit:
        items = load_items('evals/item_judge/dataset.jsonl')[:args.limit]
        result = langfuse.run_experiment(data=items, **common)
    else:
        result = langfuse.get_dataset(args.dataset).run_experiment(**common)
    langfuse.flush()

    print(format_summary(result.run_evaluations, title=f'== {run_name} =='))
    for item_result in result.item_results:
        failed = [e for e in item_result.evaluations if e.name == 'order_exact' and e.value < 1]
        if failed:
            item = item_result.item
            item_id = item.get('id') if isinstance(item, dict) else item.id
            print(f'  ✗ {item_id}: {failed[0].comment}')
    if result.dataset_run_url:
        print(f'\nLangfuse: {result.dataset_run_url}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
