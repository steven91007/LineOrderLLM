"""Unit tests for discord_format

No network, no LLM, no Google credentials; all orders are hand-built.
They mainly guard two things: Discord's hard limits are never exceeded, and a few easy-to-get-wrong
pieces of logic (the "含需確認" (include review) count, the duplicate warning, the empty-sheet return shape).
"""

from collections import OrderedDict

import pytest

from src.handlers import discord_format as fmt
from src.services.chat_log_importer import ParsedOrder
from src.services.shipping_summary import SummaryLine


def make_order(index: int = 1, status: str = 'ready', long_text: bool = False) -> ParsedOrder:
    """Build one order. With long_text=True every field is padded near the limit to stress the char count"""
    filler = '長' * 300 if long_text else ''
    order = {
        'orderer': f'訂購人{index}{filler}',
        'sender_name': f'寄件人{index}',
        'sender_phone': '0912345678',
        'receiver_name': f'收件人{index}',
        'receiver_phone': '0987654321',
        'receiver_address': f'台北市大安區某某路{index}號{filler}',
        'giftbox': '20A 一盒 $1,150',
        'family': None,
        'last5': '12345',
        'shipping_date': '2026-08-26',
        'source_quote': f'原文引用{index}{filler}',
    }
    problems = ['收件地址不完整', '出貨日不是週三或週日'] if status == 'review' else []
    return ParsedOrder(
        order=order,
        row=[''] * 12,
        problems=problems,
        duplicate=(status == 'duplicate'),
        session_id=f'session-{index}',
    )


def make_orders(ready: int = 0, review: int = 0, duplicate: int = 0, long_text: bool = False):
    orders = []
    index = 1
    for status, count in (('ready', ready), ('review', review), ('duplicate', duplicate)):
        for _ in range(count):
            orders.append(make_order(index, status, long_text))
            index += 1
    return orders


# ─────────────────────── Status counts ───────────────────────


def test_count_statuses():
    orders = make_orders(ready=3, review=2, duplicate=1)
    assert fmt.count_statuses(orders) == {'ready': 3, 'review': 2, 'duplicate': 1}


def test_parsed_order_status_duplicate_wins_over_problems():
    """duplicate takes precedence over problems (chat_log_importer.py:69-72)"""
    parsed = make_order(status='review')
    parsed.duplicate = True
    assert parsed.status == 'duplicate'


# ─────────────────────── Discord hard limits ───────────────────────


def test_order_embeds_never_exceed_ten_per_message():
    messages = fmt.order_embeds(make_orders(ready=40))
    assert messages, '應該至少有一則訊息'
    for embeds in messages:
        assert len(embeds) <= fmt.MAX_EMBEDS_PER_MESSAGE


def test_order_embeds_respect_total_char_budget():
    """All embeds in one message combined must not exceed Discord's 6000 chars"""
    messages = fmt.order_embeds(make_orders(ready=10, long_text=True))
    for embeds in messages:
        assert sum(len(e) for e in embeds) <= 6000


def test_order_embeds_split_when_content_is_long():
    """When fields overflow, split into multiple messages automatically instead of cramming into one"""
    messages = fmt.order_embeds(make_orders(ready=10, long_text=True))
    assert len(messages) > 1


def test_every_embed_stays_within_field_limit():
    for embeds in fmt.order_embeds(make_orders(ready=5, review=5)):
        for embed in embeds:
            assert len(embed.fields) <= fmt.MAX_FIELDS_PER_EMBED


def test_order_embeds_caps_at_detail_limit():
    """Anything beyond the limit goes to the attachment, not into embeds"""
    embeds = [e for msg in fmt.order_embeds(make_orders(ready=40)) for e in msg]
    assert len(embeds) == fmt.DETAIL_EMBED_LIMIT


def test_truncate_marks_cut():
    assert fmt.truncate('a' * 100, 10) == 'a' * 9 + '…'
    assert fmt.truncate('abc', 10) == 'abc'
    assert fmt.truncate(None, 10) == ''


# ─────────────────────── Attachment fallback ───────────────────────


def test_needs_attachment_only_above_limit():
    assert not fmt.needs_attachment(make_orders(ready=fmt.DETAIL_EMBED_LIMIT))
    assert fmt.needs_attachment(make_orders(ready=fmt.DETAIL_EMBED_LIMIT + 1))


def test_preview_text_covers_every_order():
    orders = make_orders(ready=40)
    text = fmt.preview_text(orders)
    assert '訂單 40' in text
    assert '合計 40 筆' in text


def test_preview_text_shows_problems_and_duplicates():
    text = fmt.preview_text(make_orders(review=1, duplicate=1))
    assert '收件地址不完整' in text
    assert '試算表中已有相同收件人' in text


# ─────────────────────── Duplicate warning ───────────────────────


def test_summary_embed_warns_only_when_duplicates_exist():
    """The "不會寫入" (won't be written) warning field appears only when duplicates exist"""
    counts = {'ready': 3, 'review': 0, 'duplicate': 0}
    embed = fmt.summary_embed(make_orders(ready=3), counts, '來源', 'model', 1.0)
    assert not any('不會寫入' in f.name for f in embed.fields)

    counts = {'ready': 3, 'review': 0, 'duplicate': 2}
    embed = fmt.summary_embed(make_orders(ready=3, duplicate=2), counts, '來源', 'model', 1.0)
    assert any('已存在的 2 筆不會寫入' in f.name for f in embed.fields)


def test_summary_embed_within_limits():
    counts = {'ready': 1, 'review': 1, 'duplicate': 1}
    embed = fmt.summary_embed(make_orders(ready=1, review=1, duplicate=1),
                              counts, '很長的檔名' * 200, 'model', 12.0)
    assert len(embed) <= 6000
    assert len(embed.fields) <= fmt.MAX_FIELDS_PER_EMBED


# ─────────────────────── Items ───────────────────────


def test_format_items_handles_none():
    """giftbox / family may both be None (model didn't match a form option)"""
    assert fmt.format_items({'giftbox': None, 'family': None}) == '（無）'
    assert fmt.format_items({'giftbox': '20A 一盒 $1,150', 'family': None}) == '20A 一盒 $1,150'
    assert fmt.format_items({'giftbox': '禮盒', 'family': '家庭號'}) == '禮盒 / 家庭號'


# ─────────────────────── The four write-result shapes ───────────────────────


def test_write_result_column_mismatch():
    result = {
        'success': False,
        'error': '試算表欄位與程式預期不符，表單題目可能被改過',
        'mismatches': ['A 欄：預期「時間戳記」，實際「時間」'],
    }
    embed = fmt.write_result_embed(result, {'duplicate': 0}, False)
    assert '寫入失敗' in embed.title
    assert any('欄位對不上' in f.name for f in embed.fields)


def test_write_result_nothing_eligible_has_no_updated_range():
    """This shape has no updated_range, so result['updated_range'] can't be used directly"""
    result = {'success': True, 'appended_rows': 0, 'skipped': 3}
    embed = fmt.write_result_embed(result, {'duplicate': 3}, True)
    assert '沒有訂單被寫入' in embed.title
    assert any('其中 3 筆已存在' in f.value for f in embed.fields)


def test_write_result_success():
    result = {'success': True, 'appended_rows': 5, 'updated_range': "'表單回覆 1'!A2:L6", 'skipped': 1}
    embed = fmt.write_result_embed(result, {'duplicate': 1}, False)
    assert '已寫入 5 筆' in embed.description
    assert any("A2:L6" in f.value for f in embed.fields)


def test_write_result_api_error_has_no_mismatches_key():
    """The Sheets API failure shape has no mismatches; use .get to avoid KeyError"""
    result = {'success': False, 'error': 'Google Sheets API 錯誤：429 Quota exceeded', 'skipped': 2}
    embed = fmt.write_result_embed(result, {'duplicate': 0}, False)
    assert '寫入失敗' in embed.title
    assert any('配額' in f.name for f in embed.fields)


# ─────────────────────── Date sheet organizing ───────────────────────


def make_organize_result(sheet_count: int = 3, stale: int = 0):
    groups = OrderedDict(
        (f'2026-08-{20 + i:02d}', [[''] * 12 for _ in range(3)])
        for i in range(sheet_count)
    )
    summaries = OrderedDict(
        (name, {
            'lines': [SummaryLine('禮盒', '20A', 1, '盒', 2, 2)],
            'order_count': 3,
            'totals': OrderedDict([('盒', 2)]),
            'unparsed': [],
        })
        for name in groups
    )
    return {
        'success': True,
        'source_sheet': '表單回覆 1',
        'groups': groups,
        'summaries': summaries,
        'total_rows': sheet_count * 3,
        'written_sheets': [],
        'stale_sheets': [f'2026-07-{i:02d}' for i in range(1, stale + 1)],
        'dry_run': True,
    }


def test_organize_preview_small():
    embed, overflow = fmt.organize_preview_embed(make_organize_result(3))
    assert overflow is None
    assert len(embed.fields) == 3
    assert '20A 禮盒 1盒*2個地址' in embed.fields[0].value


def test_organize_preview_falls_back_to_attachment():
    """With too many sheets, fall back to an attachment rather than hitting the 25-field limit"""
    embed, overflow = fmt.organize_preview_embed(make_organize_result(30))
    assert overflow is not None
    assert len(embed.fields) <= fmt.MAX_FIELDS_PER_EMBED
    assert '2026-08-49' in overflow or len(overflow) > 0


def test_organize_preview_highlights_stale_sheets():
    embed, _ = fmt.organize_preview_embed(make_organize_result(3, stale=2))
    assert any('將被清空' in f.name for f in embed.fields)
    assert embed.color.value == 0xE67E22


def test_organize_preview_empty_sheet_shape_does_not_crash():
    """The empty-master-sheet return has no summaries / stale_sheets keys at all
    (sheet_date_organizer.py:79-85)"""
    result = {
        'success': True,
        'groups': OrderedDict(),
        'total_rows': 0,
        'written_sheets': [],
        'message': '總表沒有訂單資料',
    }
    embed, overflow = fmt.organize_preview_embed(result)
    assert overflow is None
    assert '共 0 筆訂單' in embed.description


def test_organize_summary_dedupes_unparsed():
    """unparsed may contain duplicates; dedupe with set then sort, like organize_by_date.py:100"""
    result = make_organize_result(1)
    name = next(iter(result['groups']))
    result['summaries'][name]['unparsed'] = ['神秘品項', '神秘品項', '另一個']
    embed, _ = fmt.organize_preview_embed(result)
    assert embed.fields[0].value.count('神秘品項') == 1


def test_organize_result_partial_failure_reports_progress():
    """On partial write failure, report how far it got; organize_by_date.py just discards this information"""
    result = {
        'success': False,
        'error': '寫入日期分頁失敗：500 Internal Error',
        'groups': OrderedDict(),
        'written_sheets': ['2026-08-20', '2026-08-23'],
        'stale_sheets': [],
    }
    embed = fmt.organize_result_embed(result)
    assert '部分寫入失敗' in embed.title
    assert any('已完成 2 個分頁' in f.name for f in embed.fields)


def test_organize_result_success():
    result = {'success': True, 'written_sheets': ['2026-08-20'], 'stale_sheets': ['2026-07-01']}
    embed = fmt.organize_result_embed(result)
    assert '已寫入 1 個分頁' in embed.description
    assert '清空 1 個' in embed.description


# ─────────────────────── Button labels ───────────────────────


class _StubHandler:
    """The View's __init__ only uses pending.counts and touches nothing else"""
    authorized_users = ['*']

    def is_authorized(self, user_id):
        return True

    def drop_pending(self, token):
        pass


def _make_view(ready: int, review: int, duplicate: int):
    from src.handlers.discord_handler import PendingImport
    from src.handlers.discord_views import ImportConfirmView

    pending = PendingImport(
        token='t',
        orders=make_orders(ready, review, duplicate),
        user_id=1,
        channel_id=2,
        created_at=0.0,
        counts={'ready': ready, 'review': review, 'duplicate': duplicate},
    )
    return ImportConfirmView(_StubHandler(), pending, timeout=60)


def test_include_review_button_counts_ready_plus_review():
    """allowed for write(include_review=True) is {'ready','review'}, so both get written.
    If the button showed only review, its count would not match appended_rows."""
    view = _make_view(ready=3, review=2, duplicate=1)
    labels = [item.label for item in view.children]
    assert labels[0] == '寫入可寫入的 (3)'
    assert labels[1] == '含需確認 (5)'
    assert labels[2] == '取消'


def test_buttons_disabled_when_nothing_to_write():
    view = _make_view(ready=0, review=0, duplicate=4)
    assert view.children[0].disabled, '沒有可寫入的就該停用'
    assert view.children[1].disabled, '沒有需確認的就該停用'
    assert not view.children[2].disabled, '取消永遠可以按'


def test_confirm_view_claim_is_single_use():
    """Double-click guard: the second _claim must return False"""
    view = _make_view(ready=1, review=0, duplicate=0)
    assert view._claim() is True
    assert view._claim() is False


# ─────────────────────── DM / channel scope ───────────────────────


def _make_handler(order_channel_id: int):
    from src.handlers.discord_handler import DiscordOrderHandler

    handler = DiscordOrderHandler(
        api_key='k', sheet_id='s', credentials_path='c', model='m',
        authorized_users=['111'], order_channel_id=order_channel_id,
    )
    handler.shutdown()
    return handler


def test_dm_is_always_allowed():
    """DMs are always allowed, whether or not a channel is configured"""
    assert _make_handler(0).is_allowed_context(999, is_dm=True)
    assert _make_handler(555).is_allowed_context(999, is_dm=True)


def test_only_configured_channel_allowed_in_guild():
    handler = _make_handler(555)
    assert handler.is_allowed_context(555, is_dm=False)
    assert not handler.is_allowed_context(999, is_dm=False)


def test_no_channel_configured_means_dm_only():
    """With no channel configured, server messages are always ignored (must not pass just because 0 == 0)"""
    handler = _make_handler(0)
    assert not handler.is_allowed_context(0, is_dm=False)
    assert not handler.is_allowed_context(999, is_dm=False)


def test_authorization_is_independent_of_context():
    handler = _make_handler(0)
    assert handler.is_authorized(111)
    assert not handler.is_authorized(222)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
