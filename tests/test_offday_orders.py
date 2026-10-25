"""Unit tests for the non-shipping-day audit.

No Google connection: fake master-sheet data is fed straight into
OffdayOrderAuditor.audit -- a fake client replaces the real FormSheetClient,
so no credentials are needed.
"""

from datetime import date, timedelta

import pytest

from src.handlers import discord_format as fmt
from src.services.offday_orders import OffdayOrderAuditor
from src.utils.form_options import FORM_COLUMNS
from src.utils.shipping_days import (
    SHIPPING_WEEKDAYS,
    is_shipping_day,
    shipping_days_text,
    weekday_name,
)

HEADER = list(FORM_COLUMNS)


def make_row(shipping_date: str, receiver: str = '王小明',
             phone: str = '0912345678', giftbox: str = '20A 一盒 $1,150') -> list:
    """Build one master-sheet row (12 columns, in FORM_COLUMNS order)."""
    row = [''] * len(FORM_COLUMNS)
    row[0] = '2026/08/21 10:00:00'   # Timestamp
    row[1] = '陳小姐'                 # Orderer
    row[5] = receiver                # Receiver
    row[6] = phone                   # Receiver phone
    row[8] = giftbox                 # Gift box
    row[11] = shipping_date          # Desired delivery date
    return row


def make_auditor(rows):
    """Bypass FormSheetClient and inject the data directly."""
    auditor = OffdayOrderAuditor.__new__(OffdayOrderAuditor)

    class _FakeClient:
        sheet_name = '表單回覆 1'

        def read_all_rows(self):
            return [HEADER] + rows

    auditor.client = _FakeClient()
    auditor.sheet_id = 'fake'
    auditor.source_sheet = '表單回覆 1'
    return auditor


# ─────────────────────── Shipping day definition ───────────────────────


def test_shipping_days_are_wednesday_and_sunday():
    """CONTEXT.md: only Wednesday and Sunday are shipping days."""
    assert SHIPPING_WEEKDAYS == {2, 6}
    assert is_shipping_day(date(2026, 8, 26))   # Wednesday
    assert is_shipping_day(date(2026, 8, 23))   # Sunday
    assert not is_shipping_day(date(2026, 8, 25))  # Tuesday
    assert shipping_days_text() == '週三、週日'


def test_weekday_name():
    assert weekday_name(date(2026, 8, 25)) == '二'
    assert weekday_name(date(2026, 8, 23)) == '日'


def test_chat_log_importer_uses_the_shared_definition():
    """Parsing and auditing must share one shipping-day definition, not each keep their own."""
    import src.services.chat_log_importer as importer
    assert importer.is_shipping_day is is_shipping_day


# ─────────────────────── Scanning logic ───────────────────────


def test_shipping_days_are_not_reported():
    auditor = make_auditor([
        make_row('2026/8/26'),   # Wednesday
        make_row('2026/8/23'),   # Sunday
    ])
    result = auditor.audit(include_past=True)
    assert result['success']
    assert result['offday_count'] == 0
    assert result['unknown_count'] == 0
    assert result['total_rows'] == 2


def test_offday_orders_are_grouped_by_date():
    auditor = make_auditor([
        make_row('2026/8/25', receiver='王小明'),   # Tuesday
        make_row('2026/8/28', receiver='李小華'),   # Friday
        make_row('2026/8/28', receiver='張先生'),   # Friday
        make_row('2026/8/26', receiver='沒問題'),   # Wednesday, shouldn't appear
    ])
    result = auditor.audit(include_past=True)
    assert result['offday_count'] == 3
    assert list(result['offday']) == ['2026-08-25', '2026-08-28']
    assert len(result['offday']['2026-08-28']) == 2
    assert result['offday']['2026-08-25'][0].weekday_label == '星期二'


def test_blank_and_garbled_dates_go_to_unknown():
    auditor = make_auditor([
        make_row('', receiver='沒填日期'),
        make_row('下週都可以', receiver='寫得很隨性'),
        make_row('2026/8/26', receiver='正常'),
    ])
    result = auditor.audit(include_past=True)
    assert result['unknown_count'] == 2
    assert result['offday_count'] == 0
    raws = {o.raw_date for o in result['unknown']}
    assert raws == {'', '下週都可以'}


def test_date_with_weekday_annotation_is_parsed():
    """Annotated forms like 「2026/8/25(星期二)」 must be understood, not counted as unrecognized."""
    auditor = make_auditor([make_row('2026/8/25(星期二)')])
    result = auditor.audit(include_past=True)
    assert result['unknown_count'] == 0
    assert result['offday_count'] == 1


def test_past_orders_skipped_by_default():
    auditor = make_auditor([
        make_row('2026/8/18', receiver='已經過去的週二'),
        make_row('2026/8/25', receiver='還沒到的週二'),
    ])
    result = auditor.audit(include_past=False, today=date(2026, 8, 21))
    assert result['offday_count'] == 1
    assert result['skipped_past'] == 1
    assert result['offday']['2026-08-25'][0].receiver_name == '還沒到的週二'


def test_include_past_lists_everything():
    auditor = make_auditor([
        make_row('2026/8/18'),
        make_row('2026/8/25'),
    ])
    result = auditor.audit(include_past=True, today=date(2026, 8, 21))
    assert result['offday_count'] == 2
    assert result['skipped_past'] == 0


def test_unknown_dates_are_never_skipped_as_past():
    """An unreadable date can't be judged past or future, so it must always be listed."""
    auditor = make_auditor([make_row('', receiver='沒填')])
    result = auditor.audit(include_past=False, today=date(2026, 8, 21))
    assert result['unknown_count'] == 1


def test_row_numbers_point_at_the_real_sheet_row():
    """Row 1 is the header, so the first data row is row 2."""
    auditor = make_auditor([
        make_row('2026/8/26'),   # Row 2, normal
        make_row('2026/8/25'),   # Row 3, Tuesday
    ])
    result = auditor.audit(include_past=True)
    assert result['offday']['2026-08-25'][0].row_number == 3


def test_blank_rows_are_skipped():
    auditor = make_auditor([
        make_row('2026/8/25'),
        [''] * len(FORM_COLUMNS),
    ])
    result = auditor.audit(include_past=True)
    assert result['total_rows'] == 1


def test_empty_sheet():
    auditor = make_auditor([])
    result = auditor.audit()
    assert result['success']
    assert result['total_rows'] == 0
    assert result['message'] == '總表沒有訂單資料'


# ─────────────────────── Discord rendering ───────────────────────


def test_embed_when_everything_is_fine():
    auditor = make_auditor([make_row('2026/8/26')])
    embed, overflow = fmt.offday_embed(auditor.audit(include_past=True))
    assert '沒有出貨日異常' in embed.title
    assert overflow is None


def test_embed_lists_offday_orders():
    auditor = make_auditor([
        make_row('2026/8/25', receiver='王小明'),
        make_row('', receiver='沒填日期'),
    ])
    embed, _ = fmt.offday_embed(auditor.audit(include_past=True))
    assert '需要處理' in embed.title
    assert any('2026-08-25（星期二）' in f.name for f in embed.fields)
    assert any('無法辨識' in f.name for f in embed.fields)


def test_embed_mentions_skipped_past_orders():
    auditor = make_auditor([make_row('2026/8/18')])
    embed, _ = fmt.offday_embed(auditor.audit(include_past=False, today=date(2026, 8, 21)))
    assert any('all:true' in f.value for f in embed.fields)


def test_embed_falls_back_to_attachment_when_too_many_dates():
    """With many dates we hit the 25-field limit and must fall back to an attachment.

    A month has only about 20 non-shipping days, not enough to hit the limit, so span two months.
    """
    start = date(2026, 9, 1)
    days = [start + timedelta(days=i) for i in range(60)]
    rows = [make_row(d.strftime('%Y/%-m/%-d')) for d in days if not is_shipping_day(d)]
    assert len(rows) > fmt.ORGANIZE_FIELD_LIMIT, '這個測試需要超過上限的日期數'
    auditor = make_auditor(rows)
    result = auditor.audit(include_past=True)
    embed, overflow = fmt.offday_embed(result)
    assert overflow is not None
    assert len(embed.fields) <= fmt.MAX_FIELDS_PER_EMBED
    assert len(embed) <= 6000


def test_offday_text_contains_every_order():
    auditor = make_auditor([
        make_row('2026/8/25', receiver='王小明'),
        make_row('2026/8/28', receiver='李小華'),
        make_row('亂寫', receiver='陳大寶'),
    ])
    text = fmt.offday_text(auditor.audit(include_past=True))
    for name in ('王小明', '李小華', '陳大寶'):
        assert name in text


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))


# ─────────────────────── Shipping date earlier than submission time ───────────────────────


def make_row_with_timestamp(shipping_date: str, submitted: str,
                            receiver: str = '王小明') -> list:
    row = make_row(shipping_date, receiver=receiver)
    row[0] = submitted
    return row


def test_backdated_order_is_flagged():
    """The shipping date had already passed when the form was filled, so it must be wrong."""
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/16', '2026/08/20 10:00:00', receiver='填錯的'),
    ])
    result = auditor.audit(include_past=True)
    assert result['backdated_count'] == 1
    order = result['backdated'][0]
    assert order.receiver_name == '填錯的'
    assert order.shipping_date == '2026-08-16'
    assert order.submitted_label == '2026-08-20'


def test_normal_order_is_not_backdated():
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/26', '2026/08/20 10:00:00'),
    ])
    assert auditor.audit(include_past=True)['backdated_count'] == 0


def test_same_day_shipping_is_not_backdated():
    """Ordering and shipping on the same day is not an error."""
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/26', '2026/08/26 08:00:00'),
    ])
    assert auditor.audit(include_past=True)['backdated_count'] == 0


def test_backdated_ignores_include_past_filter():
    """Backdated rows are necessarily before today; if include_past filtered them, they'd never be seen by default."""
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/16', '2026/08/20 10:00:00'),
    ])
    result = auditor.audit(include_past=False, today=date(2026, 8, 21))
    assert result['backdated_count'] == 1, 'backdated 不該被 include_past 過濾掉'


def test_backdated_and_offday_can_both_apply():
    """One row may have both problems; it must appear in both."""
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/18', '2026/08/20 10:00:00'),   # Tuesday and earlier than submission
    ])
    result = auditor.audit(include_past=True)
    assert result['backdated_count'] == 1
    assert result['offday_count'] == 1


def test_unparseable_timestamp_skips_the_check():
    """If the timestamp is unreadable, skip the comparison; no false positives."""
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/16', '亂寫的時間'),
    ])
    assert auditor.audit(include_past=True)['backdated_count'] == 0


def test_backdated_appears_in_embed_and_text():
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/16', '2026/08/20 10:00:00', receiver='填錯的'),
    ])
    result = auditor.audit(include_past=False, today=date(2026, 8, 21))
    embed, _ = fmt.offday_embed(result)
    assert any('早於填表時間' in f.name for f in embed.fields)
    assert '填錯的' in fmt.offday_text(result)


def test_clean_sheet_reports_no_problems():
    """Only clean when none of the three categories apply."""
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/26', '2026/08/20 10:00:00'),
    ])
    embed, _ = fmt.offday_embed(auditor.audit(include_past=True))
    assert '沒有出貨日異常' in embed.title
