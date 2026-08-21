"""日期分頁鎖定與匯入時的過期警告

出貨日已經過去的日期分頁不該再重建：貨已經出了，那份清單就是歷史紀錄。
"""

from datetime import date, datetime

import pytest

from src.handlers import discord_format as fmt
from src.services.sheet_date_organizer import UNDATED_SHEET_NAME, is_past_sheet


# ─────────────────────── 哪些分頁該鎖 ───────────────────────


def test_past_date_sheets_are_locked():
    today = date(2026, 8, 21)
    assert is_past_sheet('2026-08-19', today)
    assert is_past_sheet('2025-12-31', today)


def test_today_and_future_are_not_locked():
    """今天當天還在出貨，不能鎖"""
    today = date(2026, 8, 21)
    assert not is_past_sheet('2026-08-21', today)
    assert not is_past_sheet('2026-08-26', today)


def test_non_date_sheets_are_never_locked():
    """未指定日期會一直有新訂單進來，鎖了就更新不了"""
    today = date(2026, 8, 21)
    assert not is_past_sheet(UNDATED_SHEET_NAME, today)
    assert not is_past_sheet('表單回覆 1', today)


# ─────────────────────── 預覽呈現 ───────────────────────


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
    # 沒鎖的分頁不該有鎖頭
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
    """舊的回傳形狀沒有 locked_sheets，不能 KeyError"""
    result = make_organize_result()
    del result['locked_sheets']
    embed, _ = fmt.organize_preview_embed(result)
    assert embed.fields


# ─────────────────────── 匯入時的過期警告 ───────────────────────


def resolve(date_text: str, today: datetime):
    """直接呼叫日期檢查，不建整個 importer（會連 Google）"""
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
    """兩個毛病都要講，不能只講一個"""
    _, problems = resolve('2026-08-18', TODAY)
    assert any('不是出貨日' in p for p in problems)
    assert any('已經過去' in p for p in problems)


def test_past_date_does_not_block_writing():
    """只警告不擋——補登舊訂單時還是要寫得進去"""
    from src.services.chat_log_importer import ParsedOrder

    _, problems = resolve('2026-08-16', TODAY)
    parsed = ParsedOrder(order={}, row=[], problems=problems)
    assert parsed.status == 'review', '應該是需確認，不是被擋掉'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
