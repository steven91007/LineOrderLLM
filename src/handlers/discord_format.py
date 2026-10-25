"""Turn service-layer results into the embeds / text Discord needs

Everything here is a pure function: no network, no LLM, no Google credentials,
so it can be unit-tested directly with hand-built ParsedOrder objects (tests/test_discord_format.py).

Discord's hard limits (exceeding them gets a 400 back from the API):
    Message content: 2000 chars
    embed: title 256, description 4096, field name 256, field value 1024, footer 2048
    At most 25 fields per embed
    6000 chars for "all embeds combined" in one message
    At most 10 embeds per message
"""

from typing import Any, Dict, List, Optional, Tuple

import discord

# Same mapping as import_chat_log.py:29. Deliberately copied rather than imported:
# that module re-wraps sys.stdout on import (for the Windows cp950 console),
# which would also break logging output if it happened inside the bot process.
STATUS_LABEL = {
    'ready': '可寫入',
    'review': '需確認',
    'duplicate': '已存在',
}

STATUS_EMOJI = {
    'ready': '✅',
    'review': '⚠️',
    'duplicate': '🔁',
}

STATUS_COLOR = {
    'ready': 0x2ECC71,
    'review': 0xF1C40F,
    'duplicate': 0x95A5A6,
}

# Max embeds per message, and the character budget.
# 6000 is Discord's hard limit; leave 500 chars of headroom for fields we can't account for.
MAX_EMBEDS_PER_MESSAGE = 10
MAX_CHARS_PER_MESSAGE = 5500
MAX_FIELDS_PER_EMBED = 25

# Above this many details, switch to an attachment instead of one embed per order
DETAIL_EMBED_LIMIT = 10

# Field limit for organize's date sheets. One slot is reserved for "其餘 N 個分頁" (remaining N sheets)
ORGANIZE_FIELD_LIMIT = 24


def truncate(text: str, limit: int) -> str:
    """Truncate an overly long string and mark the truncation at the end"""
    text = str(text or '')
    if len(text) <= limit:
        return text
    return text[:limit - 1] + '…'


def count_statuses(parsed_orders: List[Any]) -> Dict[str, int]:
    """Count how many are ready / review / duplicate (可寫入／需確認／已存在)"""
    counts = {'ready': 0, 'review': 0, 'duplicate': 0}
    for parsed in parsed_orders:
        counts[parsed.status] = counts.get(parsed.status, 0) + 1
    return counts


def format_items(order: Dict[str, Any]) -> str:
    """Join gift box / family pack into one item line (same approach as import_chat_log._print_preview)

    Both giftbox and family may be None (model didn't match a form option); filter both out.
    """
    items = ' / '.join(x for x in (order.get('giftbox'), order.get('family')) if x)
    return items or '（無）'


def _embed_length(embed: discord.Embed) -> int:
    """Character count of one embed (the method Discord uses to check the 6000 limit)"""
    return len(embed)


# ─────────────────────────── Import preview ───────────────────────────


def summary_embed(parsed_orders: List[Any], counts: Dict[str, int],
                  source_label: str, model: str,
                  elapsed_seconds: float) -> discord.Embed:
    """Summary embed for the import preview"""
    total = len(parsed_orders)
    duplicate = counts.get('duplicate', 0)

    embed = discord.Embed(
        title='聊天紀錄匯入預覽',
        description=f'共 {total} 筆訂單',
        color=0xF1C40F if counts.get('review') or duplicate else 0x2ECC71,
    )
    embed.add_field(
        name='狀態',
        value=(f'{STATUS_EMOJI["ready"]} 可寫入 {counts.get("ready", 0)}　'
               f'{STATUS_EMOJI["review"]} 需確認 {counts.get("review", 0)}　'
               f'{STATUS_EMOJI["duplicate"]} 已存在 {duplicate}'),
        inline=False,
    )
    embed.add_field(name='來源', value=truncate(source_label, 1024), inline=True)
    embed.add_field(name='模型', value=truncate(model, 1024), inline=True)
    embed.add_field(name='耗時', value=f'{elapsed_seconds:.0f} 秒', inline=True)

    # "Duplicate" orders are never written, even with "含需確認" (include review)
    # (allowed in chat_log_importer.py:364 is only ready/review). Without spelling it out here,
    # the user would just see an unexplained skipped count in the write result.
    if duplicate:
        embed.add_field(
            name=f'已存在的 {duplicate} 筆不會寫入',
            value='即使按「含需確認」也不會寫入，這是為了避免同一筆訂單重複下單。'
                  '如果確定要重寫，請直接編輯總表。',
            inline=False,
        )

    return embed


def order_embed(index: int, parsed: Any) -> discord.Embed:
    """Detail embed for a single order"""
    order = parsed.order
    status = parsed.status

    embed = discord.Embed(
        title=f'訂單 {index}　{STATUS_EMOJI[status]} {STATUS_LABEL[status]}',
        color=STATUS_COLOR[status],
    )
    embed.add_field(name='訂購人', value=truncate(order.get('orderer') or '—', 1024), inline=True)
    embed.add_field(
        name='寄件人',
        value=truncate(f'{order.get("sender_name") or "—"}　{order.get("sender_phone") or ""}'.strip(), 1024),
        inline=True,
    )
    embed.add_field(
        name='收件人',
        value=truncate(f'{order.get("receiver_name") or "—"}　{order.get("receiver_phone") or ""}'.strip(), 1024),
        inline=True,
    )
    embed.add_field(name='品項', value=truncate(format_items(order), 1024), inline=True)
    embed.add_field(name='末五碼', value=truncate(order.get('last5') or '—', 1024), inline=True)
    # CONTEXT.md's glossary uses "出貨日" (shipping date) as canonical (some code says "配送日")
    embed.add_field(name='出貨日', value=truncate(order.get('shipping_date') or '—', 1024), inline=True)
    embed.add_field(
        name='收件地址',
        value=truncate(order.get('receiver_address') or '—', 1024),
        inline=False,
    )

    if parsed.problems:
        embed.add_field(
            name='需確認',
            value=truncate('\n'.join(f'・{p}' for p in parsed.problems), 1024),
            inline=False,
        )

    if parsed.duplicate:
        embed.add_field(
            name='已存在',
            value='試算表中已有相同收件人／電話／出貨日的訂單，不會寫入',
            inline=False,
        )

    if order.get('source_quote'):
        embed.set_footer(text=truncate(f'依據：{order["source_quote"]}', 300))

    return embed


def order_embeds(parsed_orders: List[Any],
                 limit: int = DETAIL_EMBED_LIMIT) -> List[List[discord.Embed]]:
    """Group detail embeds per message

    Returns a list of lists: outer is messages, inner is the embeds that message carries.
    Constrained by both the 10-embed and 6000-char limits.
    """
    messages: List[List[discord.Embed]] = []
    current: List[discord.Embed] = []
    current_chars = 0

    for index, parsed in enumerate(parsed_orders[:limit], start=1):
        embed = order_embed(index, parsed)
        size = _embed_length(embed)

        too_many = len(current) >= MAX_EMBEDS_PER_MESSAGE
        too_long = current and current_chars + size > MAX_CHARS_PER_MESSAGE
        if too_many or too_long:
            messages.append(current)
            current, current_chars = [], 0

        current.append(embed)
        current_chars += size

    if current:
        messages.append(current)
    return messages


def preview_text(parsed_orders: List[Any]) -> str:
    """Full plain-text preview, used as an attachment when there are too many orders

    Deliberately reproduces the layout of import_chat_log._print_preview: that format is already
    in use, and plain text isn't bound by any embed limits, so 30 and 300 orders take the same path.
    """
    lines: List[str] = []
    counts = {'ready': 0, 'review': 0, 'duplicate': 0}

    for index, parsed in enumerate(parsed_orders, start=1):
        counts[parsed.status] = counts.get(parsed.status, 0) + 1
        order = parsed.order

        lines.append(f'─── 訂單 {index}　[{STATUS_LABEL[parsed.status]}] ' + '─' * 30)
        lines.append(f'  訂購人　　：{order.get("orderer") or "—"}')
        lines.append(f'  寄件人　　：{order.get("sender_name") or "—"}　{order.get("sender_phone") or ""}')
        lines.append(f'  收件人　　：{order.get("receiver_name") or "—"}　{order.get("receiver_phone") or ""}')
        lines.append(f'  收件地址　：{order.get("receiver_address") or "—"}')
        lines.append(f'  品項　　　：{format_items(order)}')
        lines.append(f'  末五碼　　：{order.get("last5") or "—"}')
        lines.append(f'  出貨日　　：{order.get("shipping_date") or "—"}')
        if order.get('source_quote'):
            lines.append(f'  依據　　　：{order["source_quote"]}')
        for problem in parsed.problems:
            lines.append(f'  ⚠️  {problem}')
        if parsed.duplicate:
            lines.append('  ⚠️  試算表中已有相同收件人／電話／出貨日的訂單')
        lines.append('')

    lines.append(f'合計 {len(parsed_orders)} 筆：'
                 f'可寫入 {counts["ready"]}、需確認 {counts["review"]}、已存在 {counts["duplicate"]}')
    return '\n'.join(lines)


def needs_attachment(parsed_orders: List[Any]) -> bool:
    """When the order count exceeds the detail-embed limit, attach the full preview file instead"""
    return len(parsed_orders) > DETAIL_EMBED_LIMIT


def overflow_note(parsed_orders: List[Any]) -> str:
    """Explanatory text when the details are truncated"""
    hidden = len(parsed_orders) - DETAIL_EMBED_LIMIT
    return f'另有 {hidden} 筆未顯示，完整內容請看附件 匯入預覽.txt'


# ─────────────────────────── Write result ───────────────────────────


def write_result_embed(result: Dict[str, Any], counts: Dict[str, int],
                       include_review: bool) -> discord.Embed:
    """Turn the four return shapes of ChatLogImporter.write() into a human-readable embed

    The four shapes (see chat_log_importer.py:353-387):
      1. Column check failed  success=False + error + mismatches
      2. Nothing eligible     success=True  + appended_rows=0 (no updated_range)
      3. Write succeeded      success=True  + appended_rows + updated_range + skipped
      4. Sheets API failed    success=False + error + skipped (no mismatches)
    Always use .get() for every key.
    """
    duplicate = counts.get('duplicate', 0)
    skipped = result.get('skipped', 0)

    if not result.get('success'):
        embed = discord.Embed(
            title='❌ 寫入失敗',
            description=truncate(str(result.get('error') or '未知錯誤'), 4096),
            color=0xE74C3C,
        )
        mismatches = result.get('mismatches') or []
        if mismatches:
            embed.add_field(
                name='欄位對不上',
                value=truncate('\n'.join(f'・{m}' for m in mismatches), 1024),
                inline=False,
            )
            embed.add_field(
                name='怎麼處理',
                value='表單題目可能被改過，請先核對總表的標題列，再重新貼一次聊天紀錄。',
                inline=False,
            )
        else:
            # append is a single API call; failure means the whole batch didn't go in, so we can say so definitively
            embed.add_field(
                name='怎麼處理',
                value='沒有任何資料被寫入，可以直接重試。',
                inline=False,
            )
            if _is_quota_error(result.get('error')):
                embed.add_field(
                    name='配額',
                    value='Google Sheets 每分鐘寫入配額已滿，請等一分鐘後再重試。',
                    inline=False,
                )
        return embed

    appended = result.get('appended_rows', 0)

    if not appended:
        embed = discord.Embed(
            title='沒有訂單被寫入',
            description=f'沒有訂單符合寫入條件，略過 {skipped} 筆。',
            color=0x95A5A6,
        )
    else:
        embed = discord.Embed(
            title='✅ 寫入完成',
            description=f'已寫入 {appended} 筆，略過 {skipped} 筆。',
            color=0x2ECC71,
        )
        if result.get('updated_range'):
            embed.add_field(name='範圍', value=truncate(result['updated_range'], 1024), inline=False)

    embed.add_field(
        name='寫入範圍',
        value='可寫入 + 需確認' if include_review else '只有可寫入',
        inline=True,
    )

    if duplicate:
        embed.add_field(
            name='略過的原因',
            value=f'其中 {duplicate} 筆已存在於試算表，不會重複寫入。',
            inline=False,
        )

    return embed


def _is_quota_error(error: Any) -> bool:
    text = str(error or '')
    return '429' in text or 'Quota' in text or 'quota' in text


# ─────────────────────────── Date sheet organizing ───────────────────────────


def organize_preview_embed(result: Dict[str, Any]) -> Tuple[discord.Embed, Optional[str]]:
    """Preview embed for /organize

    Returns (embed, attachment text). The attachment text is non-None only when there are more than 24 sheets.

    Note: the return shape for an empty master sheet has no summaries / stale_sheets keys at all
    (sheet_date_organizer.py:79-85), so always use .get().
    """
    groups = result.get('groups') or {}
    summaries = result.get('summaries') or {}
    stale = result.get('stale_sheets') or []
    locked = set(result.get('locked_sheets') or [])

    embed = discord.Embed(
        title='日期分頁整理預覽',
        description=(f'來源分頁：{result.get("source_sheet") or "—"}\n'
                     f'共 {result.get("total_rows", 0)} 筆訂單，分成 {len(groups)} 個分頁'),
        # Orange when some sheets will be cleared: that is the destructive part and must stand out
        color=0xE67E22 if stale else 0x3498DB,
    )

    overflow: Optional[str] = None
    shown = 0
    for sheet_name, rows in groups.items():
        if shown >= ORGANIZE_FIELD_LIMIT or len(embed) > MAX_CHARS_PER_MESSAGE:
            break
        embed.add_field(
            name=_sheet_field_name(sheet_name, len(rows), sheet_name in locked),
            value=truncate(_summary_value(summaries.get(sheet_name)), 1024),
            inline=False,
        )
        shown += 1

    if shown < len(groups):
        rest = list(groups.keys())[shown:]
        embed.add_field(
            name=f'其餘 {len(rest)} 個分頁',
            value=truncate('、'.join(rest), 1024),
            inline=False,
        )
        overflow = organize_preview_text(result)

    if stale:
        embed.add_field(
            name=f'🧹 將被清空的分頁（{len(stale)}）',
            value=truncate('\n'.join(f'・{name}' for name in stale), 1024),
            inline=False,
        )

    if locked:
        embed.add_field(
            name=f'🔒 已鎖定的分頁（{len(locked)}）',
            value='出貨日已經過去，內容維持原樣不會重建；'
                  '在試算表上手動編輯時 Google 會跳出保護提醒。',
            inline=False,
        )

    embed.set_footer(text='按下「確認寫入」時會重新讀取總表，實際結果以寫入後為準')
    return embed, overflow


def _sheet_field_name(sheet_name: str, row_count: int, is_locked: bool = False) -> str:
    from ..services.sheet_date_organizer import UNDATED_SHEET_NAME

    if is_locked:
        return truncate(f'🔒 {sheet_name}　{row_count} 筆（已出貨，不會重建）', 256)
    mark = '⚠️ ' if sheet_name == UNDATED_SHEET_NAME else ''
    return truncate(f'{mark}{sheet_name}　{row_count} 筆', 256)


def _summary_value(summary: Optional[Dict[str, Any]]) -> str:
    """Shipping stats for one date sheet (mirrors organize_by_date._print_summary)"""
    if not summary:
        return '（無出貨統計）'

    lines = [line.text for line in summary.get('lines') or []]

    # unparsed may contain duplicates; the CLI in organize_by_date.py:100 also dedupes with set then sorts
    for raw in sorted(set(summary.get('unparsed') or [])):
        lines.append(f'⚠️ 品項無法辨識，未列入統計：{raw}')

    totals = '／'.join(f'{count} {unit}' for unit, count in (summary.get('totals') or {}).items())
    if totals:
        lines.append(f'── 合計 {totals}')

    return '\n'.join(lines) or '（無出貨統計）'


def organize_preview_text(result: Dict[str, Any]) -> str:
    """Full plain-text date-sheet preview, used as an attachment when there are too many sheets"""
    groups = result.get('groups') or {}
    summaries = result.get('summaries') or {}
    stale = result.get('stale_sheets') or []

    lines = [
        f'來源分頁：{result.get("source_sheet") or "—"}',
        f'共 {result.get("total_rows", 0)} 筆訂單，分成 {len(groups)} 個分頁：',
        '',
    ]
    locked = set(result.get('locked_sheets') or [])
    for sheet_name, rows in groups.items():
        lines.append(_sheet_field_name(sheet_name, len(rows), sheet_name in locked))
        for line in _summary_value(summaries.get(sheet_name)).split('\n'):
            lines.append(f'      {line}')
        lines.append('')

    if stale:
        lines.append('🧹 這些日期分頁已無對應訂單，內容會被清空：')
        lines.extend(f'   {name}' for name in stale)

    return '\n'.join(lines)


def organize_result_embed(result: Dict[str, Any]) -> discord.Embed:
    """Result after /organize actually writes

    "Partial write failure" needs special handling: success=False but written_sheets is non-empty
    (sheet_date_organizer.py:132-134). organize_by_date.py just discards this information,
    leaving the operator unaware of how far the destructive rewrite got.
    """
    written = result.get('written_sheets') or []
    stale = result.get('stale_sheets') or []

    if not result.get('success'):
        embed = discord.Embed(
            title='⚠️ 日期分頁整理失敗' if not written else '⚠️ 部分寫入失敗',
            description=truncate(str(result.get('error') or '未知錯誤'), 4096),
            color=0xE74C3C,
        )
        if written:
            embed.add_field(
                name=f'已完成 {len(written)} 個分頁',
                value=truncate('、'.join(written), 1024),
                inline=False,
            )
            embed.add_field(
                name='怎麼處理',
                value='請重新執行 /organize 補完剩下的分頁。',
                inline=False,
            )
        if _is_quota_error(result.get('error')):
            embed.add_field(
                name='配額',
                value='Google Sheets 每分鐘寫入配額已滿，請等一分鐘後再重跑。',
                inline=False,
            )
        return embed

    locked = result.get('locked_sheets') or []
    description = f'已寫入 {len(written)} 個分頁'
    if stale:
        description += f'，清空 {len(stale)} 個'
    if locked:
        description += f'，鎖定 {len(locked)} 個（已出貨）'

    embed = discord.Embed(title='✅ 日期分頁整理完成', description=description, color=0x2ECC71)
    if written:
        embed.add_field(name='分頁', value=truncate('、'.join(written), 1024), inline=False)
    return embed


# ─────────────────────── Non-shipping-day audit ───────────────────────


def offday_embed(result: Dict[str, Any]) -> Tuple[discord.Embed, Optional[str]]:
    """Result of /offday

    Returns (embed, attachment text). The attachment text is non-None only when there are too many rows to fit in the embed.
    """
    from ..utils.shipping_days import shipping_days_text

    offday = result.get('offday') or {}
    unknown = result.get('unknown') or []
    backdated = result.get('backdated') or []
    offday_count = result.get('offday_count', 0)
    unknown_count = result.get('unknown_count', 0)
    backdated_count = result.get('backdated_count', 0)
    scope = '整張總表' if result.get('include_past') else '今天以後'

    if not offday_count and not unknown_count and not backdated_count:
        embed = discord.Embed(
            title='✅ 沒有出貨日異常的訂單',
            description=(f'來源分頁：{result.get("source_sheet") or "—"}\n'
                         f'掃描範圍：{scope}，共 {result.get("total_rows", 0)} 筆訂單\n'
                         f'全部都落在{shipping_days_text()}。'),
            color=0x2ECC71,
        )
        _add_skipped_past_note(embed, result)
        return embed, None

    embed = discord.Embed(
        title='⚠️ 出貨日需要處理的訂單',
        description=(f'來源分頁：{result.get("source_sheet") or "—"}\n'
                     f'掃描範圍：{scope}，共 {result.get("total_rows", 0)} 筆訂單\n'
                     f'非出貨日 {offday_count} 筆　日期無法辨識 {unknown_count} 筆　'
                     f'早於填表時間 {backdated_count} 筆'),
        color=0xE67E22,
    )

    overflow: Optional[str] = None
    shown = 0

    for shipping_date, orders in offday.items():
        if shown >= ORGANIZE_FIELD_LIMIT or len(embed) > MAX_CHARS_PER_MESSAGE:
            break
        label = orders[0].weekday_label
        embed.add_field(
            name=truncate(f'{shipping_date}（{label}）　{len(orders)} 筆', 256),
            value=truncate('\n'.join(_offday_line(o) for o in orders), 1024),
            inline=False,
        )
        shown += 1

    if shown < len(offday):
        embed.add_field(
            name=f'其餘 {len(offday) - shown} 個日期',
            value=truncate('、'.join(list(offday)[shown:]), 1024),
            inline=False,
        )
        overflow = offday_text(result)

    if unknown:
        embed.add_field(
            name=f'❓ 日期無法辨識　{len(unknown)} 筆',
            value=truncate('\n'.join(_unknown_line(o) for o in unknown[:15]), 1024),
            inline=False,
        )
        if len(unknown) > 15 and overflow is None:
            overflow = offday_text(result)

    if backdated:
        embed.add_field(
            name=f'⏮ 出貨日早於填表時間　{len(backdated)} 筆',
            value=truncate('\n'.join(_backdated_line(o) for o in backdated[:15]), 1024),
            inline=False,
        )
        if len(backdated) > 15 and overflow is None:
            overflow = offday_text(result)

    _add_skipped_past_note(embed, result)
    embed.set_footer(text='列號對應總表上的實際列，可以直接跳過去改')
    return embed, overflow


def _add_skipped_past_note(embed: discord.Embed, result: Dict[str, Any]) -> None:
    skipped = result.get('skipped_past', 0)
    if skipped:
        embed.add_field(
            name='已略過',
            value=f'{skipped} 筆出貨日已經過去（加上 all:true 可以一起列出來）',
            inline=False,
        )


def _offday_line(order: Any) -> str:
    phone = f'　{order.receiver_phone}' if order.receiver_phone else ''
    return f'第{order.row_number}列　{order.receiver_name or "—"}{phone}　{order.items}'


def _unknown_line(order: Any) -> str:
    raw = order.raw_date or '（空白）'
    return f'第{order.row_number}列　{order.receiver_name or "—"}　原文：{truncate(raw, 40)}'


def _backdated_line(order: Any) -> str:
    return (f'第{order.row_number}列　{order.receiver_name or "—"}　'
            f'出貨日 {order.shipping_date}　填表 {order.submitted_label}')


def offday_text(result: Dict[str, Any]) -> str:
    """Full plain-text version, used as an attachment when there are too many rows"""
    offday = result.get('offday') or {}
    unknown = result.get('unknown') or []
    backdated = result.get('backdated') or []

    lines = [
        f'來源分頁：{result.get("source_sheet") or "—"}',
        f'共 {result.get("total_rows", 0)} 筆訂單',
        f'非出貨日 {result.get("offday_count", 0)} 筆、'
        f'日期無法辨識 {result.get("unknown_count", 0)} 筆、'
        f'早於填表時間 {result.get("backdated_count", 0)} 筆',
        '',
    ]

    for shipping_date, orders in offday.items():
        lines.append(f'── {shipping_date}（{orders[0].weekday_label}）　{len(orders)} 筆')
        for order in orders:
            lines.append(f'   第{order.row_number}列　{order.receiver_name or "—"}　'
                         f'{order.receiver_phone}　{order.items}　訂購人：{order.orderer or "—"}')
        lines.append('')

    if unknown:
        lines.append(f'── 日期無法辨識　{len(unknown)} 筆')
        for order in unknown:
            lines.append(f'   第{order.row_number}列　{order.receiver_name or "—"}　'
                         f'{order.receiver_phone}　原文：{order.raw_date or "（空白）"}')
        lines.append('')

    if backdated:
        lines.append(f'── 出貨日早於填表時間　{len(backdated)} 筆')
        for order in backdated:
            lines.append(f'   第{order.row_number}列　{order.receiver_name or "—"}　'
                         f'出貨日 {order.shipping_date}　填表 {order.submitted_label}')

    return '\n'.join(lines)
