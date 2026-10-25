"""
Upload the item judgment A/B dataset to Langfuse

Usage: uv run python scripts/upload_item_judge_dataset.py [--file ...] [--name item-judge-v1]

Each item is uploaded with a fixed id, so re-running is an upsert and creates no duplicates.
If the dataset content changes, upload it under a new name (item-judge-v2) instead of editing v1
in place; otherwise the baseline of earlier runs drifts.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from langfuse import get_client

from evals.item_judge.schema import load_items, validate_items

DEFAULT_FILE = 'evals/item_judge/dataset.jsonl'


def git_sha() -> str:
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], text=True).strip()
    except Exception:
        return 'unknown'


def main() -> int:
    parser = argparse.ArgumentParser(description='Upload the item judgment dataset to Langfuse')
    parser.add_argument('--file', default=DEFAULT_FILE)
    parser.add_argument('--name', default='item-judge-v1')
    args = parser.parse_args()

    items = load_items(args.file)
    validate_items(items)

    langfuse = get_client()
    if not langfuse.auth_check():
        print('❌ Langfuse authentication failed, check the LANGFUSE_* settings')
        return 1

    langfuse.create_dataset(
        name=args.name,
        description='Item judgment A/B (GPT ChatLogParser vs TypeSafe Jev), 50 synthetic chat logs',
        metadata={'items': len(items), 'git_sha': git_sha(), 'source_file': args.file},
    )
    for item in items:
        langfuse.create_dataset_item(
            dataset_name=args.name,
            id=item['id'],
            input=item['input'],
            expected_output=item['expected_output'],
            metadata=item['metadata'],
        )
    langfuse.flush()

    dataset = langfuse.get_dataset(args.name)
    print(f'✅ {args.name}: uploaded {len(items)} items, {len(dataset.items)} items in Langfuse')
    return 0


if __name__ == '__main__':
    sys.exit(main())
