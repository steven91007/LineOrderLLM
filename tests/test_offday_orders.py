"""非出貨日稽核的單元測試

不連 Google，直接把假的總表資料餵給 OffdayOrderAuditor.audit——
用一個假的 client 換掉真的 FormSheetClient，這樣連憑證都不用。
"""

from collections import OrderedDict
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
    """造一列總表資料（12 欄，順序同 FORM_COLUMNS）"""
    row = [''] * len(FORM_COLUMNS)
    row[0] = '2026/08/21 10:00:00'   # 時間戳記
    row[1] = '陳小姐'                 # 訂購人
    row[5] = receiver                # 收件人
    row[6] = phone                   # 收件人電話
    row[8] = giftbox                 # 禮盒
    row[11] = shipping_date          # 欲配送日期
    return row


def make_auditor(rows):
    """繞過 FormSheetClient，直接塞資料進去"""
    auditor = OffdayOrderAuditor.__new__(OffdayOrderAuditor)

    class _FakeClient:
        sheet_name = '表單回覆 1'

        def read_all_rows(self):
            return [HEADER] + rows

    auditor.client = _FakeClient()
    auditor.sheet_id = 'fake'
    auditor.source_sheet = '表單回覆 1'
    return auditor


# ─────────────────────── 出貨日定義 ───────────────────────


def test_shipping_days_are_wednesday_and_sunday():
    """CONTEXT.md：只有週三與週日是出貨日"""
    assert SHIPPING_WEEKDAYS == {2, 6}
    assert is_shipping_day(date(2026, 8, 26))   # 週三
    assert is_shipping_day(date(2026, 8, 23))   # 週日
    assert not is_shipping_day(date(2026, 8, 25))  # 週二
    assert shipping_days_text() == '週三、週日'


def test_weekday_name():
    assert weekday_name(date(2026, 8, 25)) == '二'
    assert weekday_name(date(2026, 8, 23)) == '日'


def test_chat_log_importer_uses_the_shared_definition():
    """解析和稽核必須共用同一份出貨日定義，不能各寫一份"""
    import src.services.chat_log_importer as importer
    assert importer.is_shipping_day is is_shipping_day


# ─────────────────────── 掃描邏輯 ───────────────────────


def test_shipping_days_are_not_reported():
    auditor = make_auditor([
        make_row('2026/8/26'),   # 週三
        make_row('2026/8/23'),   # 週日
    ])
    result = auditor.audit(include_past=True)
    assert result['success']
    assert result['offday_count'] == 0
    assert result['unknown_count'] == 0
    assert result['total_rows'] == 2


def test_offday_orders_are_grouped_by_date():
    auditor = make_auditor([
        make_row('2026/8/25', receiver='王小明'),   # 週二
        make_row('2026/8/28', receiver='李小華'),   # 週五
        make_row('2026/8/28', receiver='張先生'),   # 週五
        make_row('2026/8/26', receiver='沒問題'),   # 週三，不該出現
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
    """「2026/8/25(星期二)」這種帶註記的寫法要看得懂，不能算成無法辨識"""
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
    """日期看不懂就無從判斷過去未來，一律要列出來"""
    auditor = make_auditor([make_row('', receiver='沒填')])
    result = auditor.audit(include_past=False, today=date(2026, 8, 21))
    assert result['unknown_count'] == 1


def test_row_numbers_point_at_the_real_sheet_row():
    """第 1 列是標題，所以第一筆資料是第 2 列"""
    auditor = make_auditor([
        make_row('2026/8/26'),   # 第 2 列，正常
        make_row('2026/8/25'),   # 第 3 列，週二
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


# ─────────────────────── Discord 呈現 ───────────────────────


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
    """日期一多就會撞 25 field 上限，要退回附件

    一個月大約只有 20 個非出貨日，湊不到上限，所以要跨到兩個月。
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


# ─────────────────────── 出貨日早於填表時間 ───────────────────────


def make_row_with_timestamp(shipping_date: str, submitted: str,
                            receiver: str = '王小明') -> list:
    row = make_row(shipping_date, receiver=receiver)
    row[0] = submitted
    return row


def test_backdated_order_is_flagged():
    """填表當下出貨日就已經過去了，一定是填錯"""
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
    """當天下單當天出貨不算填錯"""
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/26', '2026/08/26 08:00:00'),
    ])
    assert auditor.audit(include_past=True)['backdated_count'] == 0


def test_backdated_ignores_include_past_filter():
    """backdated 必然早於今天，被 include_past 濾掉的話預設就永遠看不到"""
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/16', '2026/08/20 10:00:00'),
    ])
    result = auditor.audit(include_past=False, today=date(2026, 8, 21))
    assert result['backdated_count'] == 1, 'backdated 不該被 include_past 過濾掉'


def test_backdated_and_offday_can_both_apply():
    """同一列可能兩種毛病都有，兩邊都要出現"""
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/18', '2026/08/20 10:00:00'),   # 週二 且 早於填表
    ])
    result = auditor.audit(include_past=True)
    assert result['backdated_count'] == 1
    assert result['offday_count'] == 1


def test_unparseable_timestamp_skips_the_check():
    """時間戳記看不懂就不做比對，不能誤報"""
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
    """三類都沒有才算乾淨"""
    auditor = make_auditor([
        make_row_with_timestamp('2026/8/26', '2026/08/20 10:00:00'),
    ])
    embed, _ = fmt.offday_embed(auditor.audit(include_past=True))
    assert '沒有出貨日異常' in embed.title
