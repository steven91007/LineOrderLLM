"""Discord 訂單匯入處理器

把 ChatLogImporter 和 SheetDateOrganizer 接到 Discord 上。兩個服務都是同步阻塞的
（整個 repo 目前沒有任何 asyncio），所以所有服務呼叫一律丟到工作執行緒。

setup_discord_handlers(bot, handler) 比照 liff_handler.py:270 的
setup_liff_routes(app, liff_handler) 慣例。
"""

import asyncio
import io
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import tasks

from . import discord_format as fmt
from .discord_views import ImportConfirmView, OrganizeConfirmView
from ..services.chat_log_importer import ChatLogImporter, ParsedOrder
from ..services.offday_orders import OffdayOrderAuditor
from ..services.sheet_date_organizer import SheetDateOrganizer
from ..utils.time_utils import time_utils

logger = logging.getLogger(__name__)

# LINE 從 Windows 匯出的聊天紀錄常見這幾種編碼。
# import_chat_log.py 是裸的 encoding='utf-8'，但 Discord 這條路使用者不會看到
# UnicodeDecodeError，只會看到「解析出 0 筆」，所以要更寬容一點。
# 解錯碼等於用全額付費把亂碼送給 LLM。
TEXT_ENCODINGS = ('utf-8-sig', 'utf-16', 'cp950', 'utf-8')


@dataclass
class PendingImport:
    """一批解析完、等待使用者確認寫入的訂單

    只放在記憶體裡，不落地：order 裡有收件人姓名／電話／地址／匯款末五碼，
    .gitignore 已經把這類資料整批擋在版控外，寫到磁碟是另一個決定，不該順手做。
    """
    token: str
    orders: List[ParsedOrder]
    user_id: int
    channel_id: int
    created_at: float
    counts: Dict[str, int] = field(default_factory=dict)
    view: Optional[ImportConfirmView] = None


class DiscordOrderHandler:
    """Discord 側的訂單匯入邏輯"""

    def __init__(self, api_key: str, sheet_id: str, credentials_path: str,
                 model: str, authorized_users: List[str], order_channel_id: int,
                 confirm_timeout: int = 3600,
                 max_upload_bytes: int = 1_048_576,
                 ignore_prefix: str = '#',
                 min_chat_log_chars: int = 20,
                 normalize_addresses: bool = True):
        self.api_key = api_key
        self.sheet_id = sheet_id
        self.credentials_path = credentials_path
        self.model = model
        self.authorized_users = authorized_users
        self.order_channel_id = order_channel_id
        self.confirm_timeout = confirm_timeout
        self.max_upload_bytes = max_upload_bytes
        self.ignore_prefix = ignore_prefix
        self.min_chat_log_chars = min_chat_log_chars
        self.normalize_addresses = normalize_addresses

        # 各自一個 max_workers=1 的專屬執行緒池，不用 asyncio.to_thread。
        # to_thread 走共用 executor，每次會落在不同執行緒，而 ChatLogImporter 持有的
        # googleapiclient service 不是 thread-safe。單執行緒池一次解決三件事：
        # 執行緒親和性、天然序列化、省掉每次重建 service 的 0.3-2 秒。
        self._import_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='import')
        self._organize_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='organize')

        # 在工作執行緒裡延遲建立：__init__ 會讀憑證檔且可能拋錯，
        # 我們要把它變成一則 Discord 訊息，而不是啟動時的 traceback。
        self._importer: Optional[ChatLogImporter] = None

        # 三個鎖都是「忙碌就拒絕」，不排隊
        self._import_lock = asyncio.Lock()
        self._organize_lock = asyncio.Lock()
        self._sheet_write_lock = asyncio.Lock()

        # token -> PendingImport。不需要鎖：所有變動都在同一個 event loop 執行緒上，
        # 不像 Flask 每個請求各跑一條工作執行緒（chat_import_gui.py 才需要 _lock）。
        self._pending: Dict[str, PendingImport] = {}

        self._import_started_at: Optional[float] = None

    # ─────────────────────── 權限 ───────────────────────

    def is_authorized(self, user_id: int) -> bool:
        """比照 order_handler.py:65 的寫法，同樣支援 '*' 萬用字元"""
        return str(user_id) in self.authorized_users or '*' in self.authorized_users

    def is_allowed_context(self, channel_id: Optional[int], is_dm: bool) -> bool:
        """私訊一律放行；伺服器裡只認設定的那一個頻道

        私訊本來就只有你和機器人兩個人，等於天然的隔離，而且 Discord 的
        message content 限制不管私訊——純私訊用法可以完全不用開特權 intent。
        DISCORD_ORDER_CHANNEL_ID 沒設定時（=0），就只走私訊。
        """
        if is_dm:
            return True
        return bool(self.order_channel_id) and channel_id == self.order_channel_id

    # ─────────────────────── 阻塞呼叫的橋接 ───────────────────────

    def _blocking_parse(self, chat_log: str) -> List[ParsedOrder]:
        """在 import 執行緒上跑，絕不在 coroutine 裡呼叫"""
        if self._importer is None:
            self._importer = ChatLogImporter(
                api_key=self.api_key,
                sheet_id=self.sheet_id,
                credentials_path=self.credentials_path,
                model=self.model,
                normalize_addresses=self.normalize_addresses,
            )
        # use_network=False 跳過 worldtimeapi 那個 HTTP 呼叫，但保留 BASE_YEAR 檢查。
        # 這個時間會餵給模型解「這週三」之類的相對日期，錯了會靜默算出錯的出貨日。
        now = time_utils.get_current_time(use_network=False)
        return self._importer.parse(chat_log, now=now)

    def _blocking_write(self, parsed_orders: List[ParsedOrder],
                        include_review: bool) -> Dict[str, Any]:
        if self._importer is None:
            raise RuntimeError('尚未解析過任何聊天紀錄')
        return self._importer.write(parsed_orders, include_review=include_review)

    def _blocking_audit_offday(self, include_past: bool,
                               source_sheet: Optional[str]) -> Dict[str, Any]:
        auditor = OffdayOrderAuditor(
            credentials_path=self.credentials_path,
            sheet_id=self.sheet_id,
            source_sheet=source_sheet,
        )
        return auditor.audit(include_past=include_past)

    def _blocking_organize(self, dry_run: bool, source_sheet: Optional[str]) -> Dict[str, Any]:
        organizer = SheetDateOrganizer(
            credentials_path=self.credentials_path,
            sheet_id=self.sheet_id,
            source_sheet=source_sheet,
        )
        result = organizer.organize(dry_run=dry_run)
        result.setdefault('source_sheet', organizer.source_sheet)
        return result

    async def _run(self, pool: ThreadPoolExecutor, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(pool, fn, *args)

    async def write_orders(self, parsed_orders: List[ParsedOrder],
                           include_review: bool) -> Dict[str, Any]:
        """給 ImportConfirmView 呼叫"""
        async with self._import_lock, self._sheet_write_lock:
            return await self._run(self._import_pool, self._blocking_write,
                                   parsed_orders, include_review)

    async def audit_offday(self, include_past: bool = False,
                           source_sheet: Optional[str] = None) -> Dict[str, Any]:
        """掃描總表找出出貨日不對的訂單

        只讀不寫，所以不需要任何寫入鎖；借用 organize 的執行緒池是為了
        沿用「googleapiclient 只在固定執行緒上跑」這個前提。
        """
        return await self._run(self._organize_pool, self._blocking_audit_offday,
                               include_past, source_sheet)

    async def organize(self, dry_run: bool,
                       source_sheet: Optional[str] = None) -> Dict[str, Any]:
        """給 /organize 和 OrganizeConfirmView 呼叫

        organize(dry_run=False) 是先清空再重寫，兩個並行會把日期分頁弄成
        空的或重複，所以寫入路徑一定要同時拿到 _organize_lock 和 _sheet_write_lock。
        """
        if dry_run:
            async with self._organize_lock:
                return await self._run(self._organize_pool, self._blocking_organize,
                                       True, source_sheet)

        async with self._organize_lock, self._sheet_write_lock:
            return await self._run(self._organize_pool, self._blocking_organize,
                                   False, source_sheet)

    # ─────────────────────── 待確認狀態 ───────────────────────

    def drop_pending(self, token: str) -> None:
        self._pending.pop(token, None)

    async def _evict_channel_pending(self, channel_id: int) -> None:
        """同一個頻道只留一批待確認的預覽

        這不是潔癖，是正確性問題：parse() 會在 chat_log_importer.py:140 抓一次
        existing_keys() 快照。如果 A 解析完還沒寫入就解析 B，B 看不到 A 的訂單、
        不會標成 duplicate，兩批都確認就會重複寫入同一筆。
        Flask GUI 用單一個 _state dict 得到的正是這個保證。
        """
        stale = [p for p in self._pending.values() if p.channel_id == channel_id]
        for pending in stale:
            self._pending.pop(pending.token, None)
            view = pending.view
            if view is None:
                continue
            view.stop()
            for item in view.children:
                item.disabled = True
            if view.message is None:
                continue
            try:
                await view.message.edit(
                    content='（已被新的匯入取代，請確認下方最新的預覽）', view=view)
            except discord.HTTPException:
                logger.debug('停用舊預覽的按鈕失敗，略過', exc_info=True)

    def evict_expired(self) -> int:
        """掃掉逾時後沒被 on_timeout 清乾淨的殘留

        訊息被刪掉、edit 失敗時 on_timeout 可能不會把 token 拿掉，
        那批含個資的訂單就會一直留在記憶體裡。
        """
        deadline = time.monotonic() - self.confirm_timeout * 1.5
        expired = [t for t, p in self._pending.items() if p.created_at < deadline]
        for token in expired:
            self._pending.pop(token, None)
        return len(expired)

    def has_pending(self) -> bool:
        return bool(self._pending)

    # ─────────────────────── 訊息進場 ───────────────────────

    async def handle_message(self, message: discord.Message) -> None:
        """頻道裡有新訊息時的進入點

        檢查順序是刻意的：先擋自己，再擋頻道，最後才是權限。
        """
        # 沒有這行，bot 自己貼的預覽會再觸發一次解析，LLM 費用會燒到見底
        if message.author.bot:
            return

        # 不是私訊、也不是指定頻道就完全安靜：bot 可能合理地待在其他頻道裡
        if not self.is_allowed_context(message.channel.id, message.guild is None):
            return

        if not self.is_authorized(message.author.id):
            logger.warning('未授權的使用者嘗試匯入：%s (%s)', message.author, message.author.id)
            try:
                await message.add_reaction('🚫')
            except discord.HTTPException:
                pass
            return

        chat_log, source_label = await self._extract_chat_log(message)
        if chat_log is None:
            return

        if self._import_lock.locked():
            elapsed = int(time.monotonic() - (self._import_started_at or time.monotonic()))
            await message.reply(
                f'目前正在解析另一批聊天紀錄（已跑 {elapsed} 秒），請等這批完成再貼。')
            return

        # 檢查和取鎖之間刻意沒有任何 await：asyncio.Lock 在沒被佔用時會直接取得、
        # 不讓出控制權，所以這兩步是不可分割的。中間若插入 await（例如先送訊息再取鎖），
        # 第二則訊息會通過上面的檢查然後排隊等鎖，變成「排隊」而不是「拒絕」。
        async with self._import_lock:
            self._import_started_at = time.monotonic()
            try:
                await self._parse_and_preview(message, chat_log, source_label)
            finally:
                self._import_started_at = None

    async def _extract_chat_log(self, message: discord.Message):
        """從訊息或附件取出聊天紀錄，回傳 (內容, 來源說明)

        取不到（或刻意略過）時回傳 (None, None)。頻道裡每一則閒聊都可能觸發
        一次數分鐘、要花錢的解析，所以這裡的過濾就是費用防線。
        """
        text_files = [a for a in message.attachments if a.filename.lower().endswith('.txt')]

        if text_files:
            attachment = text_files[0]
            if attachment.size > self.max_upload_bytes:
                await message.reply(
                    f'檔案太大（{attachment.size:,} bytes），上限是 {self.max_upload_bytes:,} bytes。')
                return None, None

            raw = await attachment.read()
            chat_log, encoding = _decode(raw)
            logger.info('讀取附件 %s（%s bytes，編碼 %s）', attachment.filename, attachment.size, encoding)

            label = f'{attachment.filename}（{len(chat_log):,} 字元）'
            if len(text_files) > 1:
                label += f'／另外 {len(text_files) - 1} 個檔案已略過'
            return chat_log, label

        content = (message.content or '').strip()

        if not content:
            # 附件不受 message_content intent 管制，但文字受。沒開 intent 的話
            # 這裡永遠是空字串，症狀是「丟檔案正常、貼文字沒反應」。
            return None, None

        if content.startswith(self.ignore_prefix):
            return None, None

        if len(content) < self.min_chat_log_chars:
            return None, None

        return content, f'貼上的訊息（{len(content):,} 字元）'

    async def _parse_and_preview(self, message: discord.Message,
                                 chat_log: str, source_label: str) -> None:
        channel = message.channel

        try:
            await message.add_reaction('⏳')
        except discord.HTTPException:
            pass

        status = await channel.send(f'🤖 解析中…（{source_label}，模型 {self.model}）')
        started = time.monotonic()
        ticker = asyncio.create_task(self._tick_progress(status, source_label, started))

        # 呼叫端（handle_message）已經持有 _import_lock
        try:
            # 刻意不用 asyncio.wait_for：它取消的是 await 不是執行緒，
            # max_workers=1 之下後續的匯入會全部卡在殭屍工作後面。
            async with channel.typing():
                parsed_orders = await self._run(self._import_pool, self._blocking_parse, chat_log)
        except Exception as error:
            logger.exception('解析聊天紀錄失敗')
            await status.edit(content=f'❌ 解析失敗：{fmt.truncate(str(error), 500)}')
            return
        finally:
            ticker.cancel()

        elapsed = time.monotonic() - started

        if not parsed_orders:
            await status.edit(content='這段對話裡沒有解析出任何訂單。')
            return

        await status.edit(content=f'✅ 解析完成（{elapsed:.0f} 秒）')
        await self._send_preview(channel, message.author.id, parsed_orders, source_label, elapsed)

    async def _tick_progress(self, status: discord.Message, source_label: str,
                             started: float) -> None:
        """每 30 秒更新一次耗時，讓人知道還活著"""
        try:
            while True:
                await asyncio.sleep(30)
                elapsed = int(time.monotonic() - started)
                await status.edit(
                    content=f'🤖 解析中…（{source_label}，模型 {self.model}）已跑 {elapsed} 秒')
        except asyncio.CancelledError:
            raise
        except discord.HTTPException:
            logger.debug('更新進度訊息失敗，略過', exc_info=True)

    async def _send_preview(self, channel, user_id: int, parsed_orders: List[ParsedOrder],
                            source_label: str, elapsed: float) -> None:
        await self._evict_channel_pending(channel.id)

        counts = fmt.count_statuses(parsed_orders)
        pending = PendingImport(
            token=uuid.uuid4().hex,
            orders=parsed_orders,
            user_id=user_id,
            channel_id=channel.id,
            created_at=time.monotonic(),
            counts=counts,
        )

        summary = fmt.summary_embed(parsed_orders, counts, source_label, self.model, elapsed)
        if fmt.needs_attachment(parsed_orders):
            summary.add_field(name='明細', value=fmt.overflow_note(parsed_orders), inline=False)
        await channel.send(embed=summary)

        # 依序送出，不要 asyncio.gather：每頻道 5 則/5 秒的 rate limit 會被撞到，
        # discord.py 會退避重送，結果還是序列化，只是時間變得不可預測。
        for embeds in fmt.order_embeds(parsed_orders):
            await channel.send(embeds=embeds)

        attachment = None
        if fmt.needs_attachment(parsed_orders):
            data = fmt.preview_text(parsed_orders).encode('utf-8')
            attachment = discord.File(io.BytesIO(data), filename='匯入預覽.txt')

        view = ImportConfirmView(self, pending, timeout=self.confirm_timeout)
        pending.view = view
        self._pending[pending.token] = pending

        kwargs = {'content': '請確認要寫入哪些訂單。', 'view': view}
        if attachment is not None:
            kwargs['file'] = attachment
        view.message = await channel.send(**kwargs)

    # ─────────────────────── 收尾 ───────────────────────

    def shutdown(self) -> None:
        self._import_pool.shutdown(wait=False)
        self._organize_pool.shutdown(wait=False)


def _decode(raw: bytes):
    """依序試幾種常見編碼，回傳 (文字, 用了哪個編碼)"""
    for encoding in TEXT_ENCODINGS[:-1]:
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 最後一關不讓它失敗：寧可有幾個字變成 �，也好過整批讀不進來
    return raw.decode('utf-8', errors='replace'), 'utf-8 (replace)'


def setup_discord_handlers(bot, handler: DiscordOrderHandler) -> None:
    """把事件與斜線指令掛到 bot 上

    比照 liff_handler.py:270 的 setup_liff_routes(app, liff_handler)。
    """

    @bot.event
    async def on_ready():
        logger.info('已登入 Discord：%s (%s)', bot.user, bot.user.id)
        if handler.order_channel_id:
            logger.info('可用範圍：私訊，以及頻道 ID %s', handler.order_channel_id)
        else:
            logger.info('可用範圍：只有私訊（未設定 DISCORD_ORDER_CHANNEL_ID）')
        if handler.order_channel_id and not bot.intents.message_content:
            logger.warning('未啟用 message_content intent，在頻道裡貼上的文字會讀不到內容'
                           '（丟 .txt 附件、以及私訊都仍然正常）')
        if not _evict_loop.is_running():
            _evict_loop.start()

    @bot.event
    async def on_message(message: discord.Message):
        try:
            await handler.handle_message(message)
        except Exception:
            logger.exception('處理訊息時發生未預期的錯誤')

    @tasks.loop(minutes=10)
    async def _evict_loop():
        removed = handler.evict_expired()
        if removed:
            logger.info('清掉 %s 批逾時未確認的匯入預覽', removed)

    def _guard():
        async def predicate(interaction: discord.Interaction) -> bool:
            # guild_id 是 None 就代表這是私訊
            if not handler.is_allowed_context(interaction.channel_id, interaction.guild_id is None):
                raise app_commands.CheckFailure('CHANNEL')
            if not handler.is_authorized(interaction.user.id):
                raise app_commands.CheckFailure('AUTH')
            return True
        return app_commands.check(predicate)

    # 沒有 @app_commands.guild_only()：加了的話這個指令在私訊裡就會消失
    @bot.tree.command(name='organize', description='把訂單總表依出貨日拆成日期分頁（先預覽）')
    @app_commands.describe(source='來源分頁名稱（預設「表單回覆 1」）')
    @_guard()
    async def organize_command(interaction: discord.Interaction, source: Optional[str] = None):
        if handler._organize_lock.locked():
            await interaction.response.send_message(
                '日期分頁整理正在執行中，請稍候。', ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            result = await handler.organize(dry_run=True, source_sheet=source)
        except Exception as error:
            logger.exception('日期分頁預覽失敗')
            await interaction.followup.send(f'❌ 預覽失敗：{fmt.truncate(str(error), 500)}')
            return

        if not result.get('success'):
            await interaction.followup.send(f'❌ {result.get("error")}')
            return

        if not (result.get('groups') or {}):
            await interaction.followup.send(result.get('message', '沒有可分類的訂單'))
            return

        embed, overflow = fmt.organize_preview_embed(result)
        view = OrganizeConfirmView(handler, interaction.user.id, source,
                                   timeout=handler.confirm_timeout)

        kwargs = {'embed': embed, 'view': view}
        if overflow:
            kwargs['file'] = discord.File(
                io.BytesIO(overflow.encode('utf-8')), filename='日期分頁預覽.txt')

        view.message = await interaction.followup.send(**kwargs)

    @bot.tree.command(name='offday', description='列出出貨日不是週三或週日的訂單')
    @app_commands.describe(
        all='連已經過去的出貨日一起列（預設只列今天以後）',
        source='來源分頁名稱（預設「表單回覆 1」）',
    )
    @_guard()
    async def offday_command(interaction: discord.Interaction,
                             all: bool = False, source: Optional[str] = None):
        await interaction.response.defer(thinking=True)

        try:
            result = await handler.audit_offday(include_past=all, source_sheet=source)
        except Exception as error:
            logger.exception('掃描非出貨日訂單失敗')
            await interaction.followup.send(f'❌ 掃描失敗：{fmt.truncate(str(error), 500)}')
            return

        if not result.get('success'):
            await interaction.followup.send(f'❌ {result.get("error")}')
            return

        embed, overflow = fmt.offday_embed(result)
        kwargs = {'embed': embed}
        if overflow:
            kwargs['file'] = discord.File(
                io.BytesIO(overflow.encode('utf-8')), filename='非出貨日訂單.txt')
        await interaction.followup.send(**kwargs)

    @bot.tree.error
    async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            text = ('請私訊我，或在指定的訂單頻道使用這個指令。' if str(error) == 'CHANNEL'
                    else '你沒有使用這個指令的權限。')
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
            return

        logger.exception('斜線指令發生錯誤', exc_info=error)
        text = f'❌ 指令執行失敗：{fmt.truncate(str(error), 500)}'
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
