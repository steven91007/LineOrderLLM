"""把服務層的結果算成 Discord 要的 embed / 文字

這裡全部都是純函式：不碰網路、不碰 LLM、不需要 Google 憑證，
所以可以直接用手工造的 ParsedOrder 做單元測試（tests/test_discord_format.py）。

Discord 的硬限制（超過會被 API 退回 400）：
    訊息內容 2000 字
    embed：title 256、description 4096、field name 256、field value 1024、footer 2048
    單一 embed 最多 25 個 field
    一則訊息裡「所有 embed 加總」6000 字
    一則訊息最多 10 個 embed
"""

from typing import Any, Dict, List, Optional, Tuple

import discord

# 和 import_chat_log.py:29 同一份對照表。刻意複製而不是 import：
# 那個模組在 import 時會重包 sys.stdout（為了 Windows cp950 主控台），
# 在 bot 行程裡發生會把 logging 的輸出一起弄壞。
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

# 一則訊息最多塞幾個 embed，以及字數預算。
# 6000 是 Discord 的硬上限，留 500 字餘裕給我們算不到的欄位。
MAX_EMBEDS_PER_MESSAGE = 10
MAX_CHARS_PER_MESSAGE = 5500
MAX_FIELDS_PER_EMBED = 25

# 明細超過這個數量就改走附件，不再一筆一個 embed
DETAIL_EMBED_LIMIT = 10

# organize 的日期分頁 field 上限。留一格給「其餘 N 個分頁」
ORGANIZE_FIELD_LIMIT = 24


def truncate(text: str, limit: int) -> str:
    """截斷過長的字串，並在結尾標示已截斷"""
    text = str(text or '')
    if len(text) <= limit:
        return text
    return text[:limit - 1] + '…'


def count_statuses(parsed_orders: List[Any]) -> Dict[str, int]:
    """數出 可寫入／需確認／已存在 各幾筆"""
    counts = {'ready': 0, 'review': 0, 'duplicate': 0}
    for parsed in parsed_orders:
        counts[parsed.status] = counts.get(parsed.status, 0) + 1
    return counts


def format_items(order: Dict[str, Any]) -> str:
    """把禮盒／家庭號組成一行品項（和 import_chat_log._print_preview 同一個寫法）

    giftbox 和 family 都可能是 None（模型沒對到表單選項），要一起濾掉。
    """
    items = ' / '.join(x for x in (order.get('giftbox'), order.get('family')) if x)
    return items or '（無）'


def _embed_length(embed: discord.Embed) -> int:
    """算一個 embed 佔多少字（Discord 用來檢查 6000 上限的算法）"""
    return len(embed)


# ─────────────────────────── 匯入預覽 ───────────────────────────


def summary_embed(parsed_orders: List[Any], counts: Dict[str, int],
                  source_label: str, model: str,
                  elapsed_seconds: float) -> discord.Embed:
    """匯入預覽的摘要 embed"""
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

    # 「已存在」永遠不會被寫入，連按「含需確認」也一樣（chat_log_importer.py:364
    # 的 allowed 只有 ready/review）。不在這裡講清楚的話，使用者只會看到
    # 寫入結果裡一個沒來由的 skipped 數字。
    if duplicate:
        embed.add_field(
            name=f'已存在的 {duplicate} 筆不會寫入',
            value='即使按「含需確認」也不會寫入，這是為了避免同一筆訂單重複下單。'
                  '如果確定要重寫，請直接編輯總表。',
            inline=False,
        )

    return embed


def order_embed(index: int, parsed: Any) -> discord.Embed:
    """單筆訂單的明細 embed"""
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
    # CONTEXT.md 的詞彙表以「出貨日」為準（程式碼裡有些地方寫「配送日」）
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
    """把明細 embed 依「每則訊息」分組

    回傳 list of list：外層是訊息、內層是那則訊息要帶的 embed。
    同時受 10 個 embed 和 6000 字兩個上限約束。
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
    """完整的純文字預覽，給訂單太多時當附件用

    刻意重現 import_chat_log._print_preview 的版面：那個格式已經在用了，
    而且純文字不受任何 embed 限制，30 筆和 300 筆走同一條路。
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
    """訂單筆數超過明細 embed 上限時，要改附完整預覽檔"""
    return len(parsed_orders) > DETAIL_EMBED_LIMIT


def overflow_note(parsed_orders: List[Any]) -> str:
    """明細被截斷時的說明文字"""
    hidden = len(parsed_orders) - DETAIL_EMBED_LIMIT
    return f'另有 {hidden} 筆未顯示，完整內容請看附件 匯入預覽.txt'


# ─────────────────────────── 寫入結果 ───────────────────────────


def write_result_embed(result: Dict[str, Any], counts: Dict[str, int],
                       include_review: bool) -> discord.Embed:
    """把 ChatLogImporter.write() 的四種回傳形狀轉成給人看的 embed

    四種形狀（見 chat_log_importer.py:353-387）：
      1. 欄位檢查失敗    success=False + error + mismatches
      2. 沒有符合條件的  success=True  + appended_rows=0（沒有 updated_range）
      3. 寫入成功        success=True  + appended_rows + updated_range + skipped
      4. Sheets API 失敗 success=False + error + skipped（沒有 mismatches）
    所有 key 一律用 .get()。
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
            # append 是單一 API 呼叫，失敗就是整批沒進去，可以講死
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


# ─────────────────────────── 日期分頁整理 ───────────────────────────


def organize_preview_embed(result: Dict[str, Any]) -> Tuple[discord.Embed, Optional[str]]:
    """/organize 的預覽 embed

    回傳 (embed, 附件文字)。分頁數超過 24 個時，附件文字才不是 None。

    注意：空總表的回傳形狀完全沒有 summaries／stale_sheets 這兩個 key
    （sheet_date_organizer.py:79-85），所以一律用 .get()。
    """
    groups = result.get('groups') or {}
    summaries = result.get('summaries') or {}
    stale = result.get('stale_sheets') or []

    embed = discord.Embed(
        title='日期分頁整理預覽',
        description=(f'來源分頁：{result.get("source_sheet") or "—"}\n'
                     f'共 {result.get("total_rows", 0)} 筆訂單，分成 {len(groups)} 個分頁'),
        # 有分頁要被清空就用橘色：這是破壞性的部分，要看得出來
        color=0xE67E22 if stale else 0x3498DB,
    )

    overflow: Optional[str] = None
    shown = 0
    for sheet_name, rows in groups.items():
        if shown >= ORGANIZE_FIELD_LIMIT or len(embed) > MAX_CHARS_PER_MESSAGE:
            break
        embed.add_field(
            name=_sheet_field_name(sheet_name, len(rows)),
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

    embed.set_footer(text='按下「確認寫入」時會重新讀取總表，實際結果以寫入後為準')
    return embed, overflow


def _sheet_field_name(sheet_name: str, row_count: int) -> str:
    from src.services.sheet_date_organizer import UNDATED_SHEET_NAME

    mark = '⚠️ ' if sheet_name == UNDATED_SHEET_NAME else ''
    return truncate(f'{mark}{sheet_name}　{row_count} 筆', 256)


def _summary_value(summary: Optional[Dict[str, Any]]) -> str:
    """一個日期分頁的出貨統計（比照 organize_by_date._print_summary）"""
    if not summary:
        return '（無出貨統計）'

    lines = [line.text for line in summary.get('lines') or []]

    # unparsed 會有重複，CLI 在 organize_by_date.py:100 也是先 set 再排序
    for raw in sorted(set(summary.get('unparsed') or [])):
        lines.append(f'⚠️ 品項無法辨識，未列入統計：{raw}')

    totals = '／'.join(f'{count} {unit}' for unit, count in (summary.get('totals') or {}).items())
    if totals:
        lines.append(f'── 合計 {totals}')

    return '\n'.join(lines) or '（無出貨統計）'


def organize_preview_text(result: Dict[str, Any]) -> str:
    """完整的純文字版日期分頁預覽，分頁太多時當附件"""
    groups = result.get('groups') or {}
    summaries = result.get('summaries') or {}
    stale = result.get('stale_sheets') or []

    lines = [
        f'來源分頁：{result.get("source_sheet") or "—"}',
        f'共 {result.get("total_rows", 0)} 筆訂單，分成 {len(groups)} 個分頁：',
        '',
    ]
    for sheet_name, rows in groups.items():
        lines.append(_sheet_field_name(sheet_name, len(rows)))
        for line in _summary_value(summaries.get(sheet_name)).split('\n'):
            lines.append(f'      {line}')
        lines.append('')

    if stale:
        lines.append('🧹 這些日期分頁已無對應訂單，內容會被清空：')
        lines.extend(f'   {name}' for name in stale)

    return '\n'.join(lines)


def organize_result_embed(result: Dict[str, Any]) -> discord.Embed:
    """/organize 實際寫入後的結果

    要特別處理「部分寫入失敗」：success=False 但 written_sheets 有值
    （sheet_date_organizer.py:132-134）。organize_by_date.py 直接丟掉這個資訊，
    操作者就不知道破壞性重寫做到哪裡了。
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

    description = f'已寫入 {len(written)} 個分頁'
    if stale:
        description += f'，清空 {len(stale)} 個'

    embed = discord.Embed(title='✅ 日期分頁整理完成', description=description, color=0x2ECC71)
    if written:
        embed.add_field(name='分頁', value=truncate('、'.join(written), 1024), inline=False)
    return embed
