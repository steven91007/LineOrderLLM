"""
TypeSafe Jev connection check

Usage: uv run python scripts/check_typesafe.py

Verifies that TYPESAFE_API_KEY in .env works and runs one Noul + Choice on a sample order message.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from typesafe_sdk import Choice, Noul, TypeSafeClient, TypeSafeError


def main() -> int:
    if not config.TYPESAFE_API_KEY:
        print('❌ TYPESAFE_API_KEY is missing from .env')
        return 1

    with TypeSafeClient(api_key=config.TYPESAFE_API_KEY, model=config.TYPESAFE_MODEL) as client:
        try:
            models = client.models.list()
            print('Available models:', ', '.join(m.name for m in models.models))
        except TypeSafeError as e:
            print(f'⚠️ Could not list models: {e}')

        started = time.perf_counter()
        try:
            response = client.system_one(
                state={'message': '我要訂兩盒 20A 禮盒，寄到士林區文林路100號，王小明 0912345678'},
                questions={
                    'is_order': Noul(instructions='Is the customer placing an order in this LINE message?'),
                    'spec': Choice(
                        instructions='Which gift box spec did the customer order?',
                        criteria={'18A': None, '20A': None, 'not mentioned': None},
                    ),
                },
            )
        except TypeSafeError as e:
            print(f'❌ Call failed: {type(e).__name__}: {e}')
            return 1
        elapsed_ms = (time.perf_counter() - started) * 1000

    print(f'✅ Connected ({elapsed_ms:.0f} ms)')
    print('Is an order:', response.nouls['is_order'].noul)
    print('Gift box spec:', response.choices['spec'].choice)
    print('Usage:', response.usage)
    return 0


if __name__ == '__main__':
    sys.exit(main())
