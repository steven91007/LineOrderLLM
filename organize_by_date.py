#!/usr/bin/env python
"""
Split the master order sheet by "欲配送日期" (desired delivery date) into one
tab per day, and produce daily shipping statistics.

Within the same spreadsheet file, each delivery date gets a tab named after the
date (e.g. 2026-08-16); orders with no date or an unreadable date are collected
in the 「未指定日期」 (unspecified date) tab.

Below each tab's order rows, that day's packing list is appended, e.g.:
    20A 家庭號 1箱*2個地址
    20A 禮盒 1盒*2個地址
    18A 禮盒 1盒*1個地址

Usage:
    # Only preview how orders would be split; the spreadsheet is untouched (default)
    python organize_by_date.py

    # Actually write once everything looks right
    python organize_by_date.py --write

    # Specify the source tab (default 「表單回覆 1」)
    python organize_by_date.py --write --source '表單回覆 1'

Note: date tabs are fully rebuilt on every run. Do not edit them by hand;
make changes in the master sheet instead.
"""

import argparse
import io
import sys

import config
from src.services.sheet_date_organizer import SheetDateOrganizer, UNDATED_SHEET_NAME

# The Windows console defaults to cp950; printing Chinese directly would crash
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def main():
    parser = argparse.ArgumentParser(description='Split the master order sheet into separate tabs by delivery date')
    parser.add_argument('--write', action='store_true',
                        help='Actually write to the spreadsheet; without this only a preview is shown')
    parser.add_argument('--source', default=None,
                        help='Source tab name (default 「表單回覆 1」)')
    args = parser.parse_args()

    missing = _check_config()
    if missing:
        print('❌ Incomplete configuration, missing: ' + ', '.join(missing))
        return 1

    organizer = SheetDateOrganizer(
        credentials_path=config.GOOGLE_CREDENTIALS_PATH,
        sheet_id=config.GOOGLE_SHEET_ID,
        source_sheet=args.source,
    )

    print(f'📄 Source tab: {organizer.source_sheet}')
    result = organizer.organize(dry_run=not args.write)

    if not result['success']:
        print(f'❌ {result["error"]}')
        return 1

    groups = result.get('groups') or {}
    if not groups:
        print(result.get('message', 'No orders to sort'))
        return 0

    summaries = result.get('summaries') or {}
    print(f'\n{result["total_rows"]} orders in total, split into {len(groups)} tabs:')
    for sheet_name, rows in groups.items():
        mark = '⚠️ ' if sheet_name == UNDATED_SHEET_NAME else '  '
        print(f'\n{mark}{sheet_name}　{len(rows)} orders')
        _print_summary(summaries.get(sheet_name))

    stale = result.get('stale_sheets') or []
    if stale:
        print(f'\n🧹 These date tabs no longer have matching orders (the delivery date may have changed); their contents will be cleared:')
        for sheet_name in stale:
            print(f'   {sheet_name}')

    if not args.write:
        print('\nThis is a preview; nothing was written. Once it looks right, add --write to create/update these tabs.')
        return 0

    print(f'\n✅ Wrote {len(result["written_sheets"])} tabs'
          + (f', cleared {len(stale)}' if stale else ''))
    return 0


def _print_summary(summary):
    """Print the shipping statistics (packing list) for a single date."""
    if not summary:
        return

    for line in summary['lines']:
        print(f'      {line.text}')

    if summary['unparsed']:
        for raw in sorted(set(summary['unparsed'])):
            print(f'      ⚠️ Unrecognized item, excluded from the statistics: {raw}')

    totals = '／'.join(f'{count} {unit}' for unit, count in summary['totals'].items())
    if totals:
        print(f'      ── Total {totals}')


def _check_config():
    missing = []
    if not config.GOOGLE_SHEET_ID:
        missing.append('GOOGLE_SHEETS_ID')
    if not config.GOOGLE_CREDENTIALS_PATH:
        missing.append('GOOGLE_SHEETS_CREDENTIALS_PATH')
    return missing


if __name__ == '__main__':
    sys.exit(main())
