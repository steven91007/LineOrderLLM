"""Date-tab locking and past-date warnings on import.

Date tabs whose shipping date has passed must not be rebuilt: the goods have
shipped, so that list is a historical record.
"""

from datetime import date, datetime

import pytest

from src.handlers import discord_format as fmt
from src.services.sheet_date_organizer import UNDATED_SHEET_NAME, is_past_sheet


# ─────────────────────── Which tabs get locked ───────────────────────


def test_past_date_sheets_are_locked():
    today = date(2026, 8, 21)
    assert is_past_sheet('2026-08-19', today)
    assert is_past_sheet('2025-12-31', today)


def test_today_and_future_are_not_locked():
    """Today is still a shipping day, so it must not be locked."""
    today = date(2026, 8, 21)
    assert not is_past_sheet('2026-08-21', today)
    assert not is_past_sheet('2026-08-26', today)


def test_non_date_sheets_are_never_locked():
    """The unspecified-date tab keeps receiving new orders; locking it would stop updates."""
    today = date(2026, 8, 21)
    assert not is_past_sheet(UNDATED_SHEET_NAME, today)
    assert not is_past_sheet('表單回覆 1', today)


# ─────────────────────── Preview rendering ───────────────────────


def make_organize_result(locked=(), stale=()):
    from collections import OrderedDict

    from src.services.shipping_summary import SummaryLine

    names = ['2026-08-19', '2026-08-23', '2026-08-26']
    groups = OrderedDict((n, [[''] * 12 for _ in range(3)]) for n in names)
    summaries = OrderedDict(
        (n, {
            'lines': [SummaryLine('禮盒', '20A', 1, '盒', 2, 2)],
            'order_count': 3,
            'totals': OrderedDict([('盒', 2)]),
            'unparsed': [],
        })
        for n in names
    )
    return {
        'success': True,
        'source_sheet': '表單回覆 1',
        'groups': groups,
        'summaries': summaries,
        'total_rows': 9,
        'written_sheets': [],
        'stale_sheets': list(stale),
        'locked_sheets': list(locked),
        'dry_run': True,
    }


def test_locked_sheets_are_marked_in_preview():
    embed, _ = fmt.organize_preview_embed(make_organize_result(locked=['2026-08-19']))
    locked_field = next(f for f in embed.fields if '2026-08-19' in f.name)
    assert '🔒' in locked_field.name
    assert '不會重建' in locked_field.name
    # Unlocked tabs shouldn't show a lock icon
    other = next(f for f in embed.fields if '2026-08-23' in f.name)
    assert '🔒' not in other.name


def test_locked_summary_field_is_added():
    embed, _ = fmt.organize_preview_embed(make_organize_result(locked=['2026-08-19']))
    assert any('已鎖定的分頁' in f.name for f in embed.fields)


def test_no_locked_field_when_nothing_locked():
    embed, _ = fmt.organize_preview_embed(make_organize_result())
    assert not any('已鎖定' in f.name for f in embed.fields)


def test_result_embed_reports_locked_count():
    result = {
        'success': True,
        'written_sheets': ['2026-08-23', '2026-08-26'],
        'stale_sheets': [],
        'locked_sheets': ['2026-08-19'],
    }
    embed = fmt.organize_result_embed(result)
    assert '已寫入 2 個分頁' in embed.description
    assert '鎖定 1 個' in embed.description


def test_organize_preview_still_handles_missing_locked_key():
    """The old result shape has no locked_sheets; must not raise KeyError."""
    result = make_organize_result()
    del result['locked_sheets']
    embed, _ = fmt.organize_preview_embed(result)
    assert embed.fields


# ─────────────────────── Past-date warnings on import ───────────────────────


def resolve(date_text: str, today: datetime):
    """Call the date check directly without building the whole importer (which would connect to Google)."""
    from src.services.chat_log_importer import ChatLogImporter

    importer = ChatLogImporter.__new__(ChatLogImporter)
    problems = []
    result = importer._resolve_shipping_date_inner(date_text, problems, today)
    return result, problems


TODAY = datetime(2026, 8, 21)


def test_past_shipping_date_is_flagged_on_import():
    _, problems = resolve('2026-08-16', TODAY)
    assert any('已經過去' in p for p in problems)


def test_today_is_not_flagged_as_past():
    _, problems = resolve('2026-08-21', TODAY)
    assert not any('已經過去' in p for p in problems)


def test_future_shipping_day_is_clean():
    result, problems = resolve('2026-08-26', TODAY)
    assert result == '2026-08-26'
    assert problems == []


def test_past_and_offday_are_reported_together():
    """Both problems must be reported, not just one."""
    _, problems = resolve('2026-08-18', TODAY)
    assert any('不是出貨日' in p for p in problems)
    assert any('已經過去' in p for p in problems)


def test_past_date_does_not_block_writing():
    """Warn only, don't block -- back-filling old orders must still be writable."""
    from src.services.chat_log_importer import ParsedOrder

    _, problems = resolve('2026-08-16', TODAY)
    parsed = ParsedOrder(order={}, row=[], problems=problems)
    assert parsed.status == 'review', '應該是需確認，不是被擋掉'


# ─────────────────────── organize() itself ───────────────────────
#
# The tests above only cover is_past_sheet and formatting and never run organize() itself,
# so a misspelled function name inside organize() (NameError) would go unnoticed; that actually happened once.
# Here a fake client runs the whole dry_run path end to end.


def make_organizer(sheet_names, existing=None):
    """Bypass FormSheetClient and feed data straight into organize()"""
    from src.services.sheet_date_organizer import SheetDateOrganizer
    from src.utils.form_options import FORM_COLUMNS

    rows = [list(FORM_COLUMNS)]
    for name in sheet_names:
        row = [''] * len(FORM_COLUMNS)
        row[0] = '2026/08/20 10:00:00'
        row[5] = '王小明'
        row[8] = '20A 一盒 $1,150'
        row[11] = name.replace('-', '/')      # desired delivery date
        rows.append(row)

    organizer = SheetDateOrganizer.__new__(SheetDateOrganizer)

    class _FakeClient:
        sheet_name = '表單回覆 1'

        def read_all_rows(self):
            return rows

    organizer.client = _FakeClient()
    organizer.service = None
    organizer.sheet_id = 'fake'
    organizer.source_sheet = '表單回覆 1'
    organizer._existing_sheets = lambda: {
        n: {'id': i, 'bandings': [], 'protections': []}
        for i, n in enumerate(existing or sheet_names)
    }
    return organizer


def test_organize_dry_run_runs_end_to_end():
    """If this path runs to completion, a NameError inside organize() gets caught"""
    organizer = make_organizer(['2026-08-19', '2026-08-23', '2026-08-26'])
    result = organizer.organize(dry_run=True, today=date(2026, 8, 21))
    assert result['success']
    assert result['total_rows'] == 3


def test_organize_marks_past_sheets_as_locked():
    organizer = make_organizer(['2026-08-19', '2026-08-23', '2026-08-26'])
    result = organizer.organize(dry_run=True, today=date(2026, 8, 21))
    assert result['locked_sheets'] == ['2026-08-19']


def test_organize_locks_nothing_when_all_upcoming():
    organizer = make_organizer(['2026-08-23', '2026-08-26'])
    result = organizer.organize(dry_run=True, today=date(2026, 8, 21))
    assert result['locked_sheets'] == []


def test_organize_does_not_treat_past_sheets_as_stale():
    """A shipped date's tab with no matching orders is not stale and must not be cleared"""
    organizer = make_organizer(
        ['2026-08-26'],                        # the master sheet only has orders on this day
        existing=['2026-08-19', '2026-08-26'],  # but the spreadsheet still has the shipped 08-19 tab
    )
    result = organizer.organize(dry_run=True, today=date(2026, 8, 21))
    assert '2026-08-19' not in result['stale_sheets'], '已出貨的分頁不該被清空'


def test_organize_still_clears_genuinely_stale_upcoming_sheets():
    """An unshipped tab that no longer has orders (the customer changed the date) must still be cleared"""
    organizer = make_organizer(
        ['2026-08-26'],
        existing=['2026-08-23', '2026-08-26'],
    )
    result = organizer.organize(dry_run=True, today=date(2026, 8, 21))
    assert result['stale_sheets'] == ['2026-08-23']

if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
