"""Discord order import handler

Wires ChatLogImporter and SheetDateOrganizer up to Discord. Both services are synchronous and blocking
(the repo currently has no asyncio at all), so every service call is pushed onto a worker thread.

setup_discord_handlers(bot, handler) follows the setup_liff_routes(app, liff_handler)
convention in liff_handler.py:270.
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

# Common encodings for LINE chat logs exported on Windows.
# import_chat_log.py uses a bare encoding='utf-8', but on the Discord path the user never sees
# a UnicodeDecodeError, only "0 orders parsed", so we need to be more forgiving.
# Decoding wrong means paying full price to send garbage to the LLM.
TEXT_ENCODINGS = ('utf-8-sig', 'utf-16', 'cp950', 'utf-8')


@dataclass
class PendingImport:
    """A batch of parsed orders waiting for the user to confirm the write

    Kept in memory only, never persisted: orders contain receiver name / phone / address / last 5 digits
    of the bank transfer. .gitignore already keeps this kind of data out of version control wholesale;
    writing it to disk is a separate decision that shouldn't be made in passing.
    """
    token: str
    orders: List[ParsedOrder]
    user_id: int
    channel_id: int
    created_at: float
    counts: Dict[str, int] = field(default_factory=dict)
    view: Optional[ImportConfirmView] = None


class DiscordOrderHandler:
    """Discord-side order import logic"""

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

        # Each gets its own dedicated max_workers=1 thread pool instead of asyncio.to_thread.
        # to_thread uses the shared executor and lands on a different thread each time, but the
        # googleapiclient service held by ChatLogImporter is not thread-safe. A single-thread pool solves
        # three things at once: thread affinity, natural serialization, and saving the 0.3-2 s of rebuilding the service each time.
        self._import_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='import')
        self._organize_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='organize')

        # Created lazily on the worker thread: __init__ reads the credentials file and may raise,
        # and we want that to become a Discord message rather than a traceback at startup.
        self._importer: Optional[ChatLogImporter] = None

        # All three locks are "reject when busy", not queued
        self._import_lock = asyncio.Lock()
        self._organize_lock = asyncio.Lock()
        self._sheet_write_lock = asyncio.Lock()

        # token -> PendingImport. No lock needed: all mutations happen on the single event loop thread,
        # unlike Flask where each request runs on its own worker thread (that's why chat_import_gui.py needs _lock).
        self._pending: Dict[str, PendingImport] = {}

        self._import_started_at: Optional[float] = None

    # ─────────────────────── Permissions ───────────────────────

    def is_authorized(self, user_id: int) -> bool:
        """Same approach as order_handler.py:65, including support for the '*' wildcard"""
        return str(user_id) in self.authorized_users or '*' in self.authorized_users

    def is_allowed_context(self, channel_id: Optional[int], is_dm: bool) -> bool:
        """DMs are always allowed; in a server only the one configured channel counts

        A DM only involves you and the bot, which is natural isolation, and Discord's
        message content restriction doesn't apply to DMs -- DM-only usage needs no privileged intent at all.
        When DISCORD_ORDER_CHANNEL_ID is unset (=0), only DMs are used.
        """
        if is_dm:
            return True
        return bool(self.order_channel_id) and channel_id == self.order_channel_id

    # ─────────────────────── Bridging blocking calls ───────────────────────

    def _blocking_parse(self, chat_log: str) -> List[ParsedOrder]:
        """Runs on the import thread; never call it from a coroutine"""
        if self._importer is None:
            self._importer = ChatLogImporter(
                api_key=self.api_key,
                sheet_id=self.sheet_id,
                credentials_path=self.credentials_path,
                model=self.model,
                normalize_addresses=self.normalize_addresses,
            )
        # use_network=False skips the worldtimeapi HTTP call but keeps the BASE_YEAR check.
        # This time is fed to the model to resolve relative dates like "這週三" (this Wednesday); if wrong, it silently yields the wrong shipping date.
        now = time_utils.get_current_time(use_network=False)
        return self._importer.parse(chat_log, now=now)

    def _blocking_write(self, parsed_orders: List[ParsedOrder],
                        include_review: bool) -> Dict[str, Any]:
        if self._importer is None:
            # Kept in Chinese: surfaces to staff via the '❌ 寫入失敗：…' Discord message
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
        """Called by ImportConfirmView"""
        async with self._import_lock, self._sheet_write_lock:
            return await self._run(self._import_pool, self._blocking_write,
                                   parsed_orders, include_review)

    async def audit_offday(self, include_past: bool = False,
                           source_sheet: Optional[str] = None) -> Dict[str, Any]:
        """Scan the master sheet for orders with a bad shipping date

        Read-only, so no write lock is needed; it borrows the organize thread pool to keep
        the "googleapiclient only runs on a fixed thread" invariant.
        """
        return await self._run(self._organize_pool, self._blocking_audit_offday,
                               include_past, source_sheet)

    async def organize(self, dry_run: bool,
                       source_sheet: Optional[str] = None) -> Dict[str, Any]:
        """Called by /organize and OrganizeConfirmView

        organize(dry_run=False) clears then rewrites; two running in parallel would leave date sheets
        empty or duplicated, so the write path must hold both _organize_lock and _sheet_write_lock.
        """
        if dry_run:
            async with self._organize_lock:
                return await self._run(self._organize_pool, self._blocking_organize,
                                       True, source_sheet)

        async with self._organize_lock, self._sheet_write_lock:
            return await self._run(self._organize_pool, self._blocking_organize,
                                   False, source_sheet)

    # ─────────────────────── Pending-confirmation state ───────────────────────

    def drop_pending(self, token: str) -> None:
        self._pending.pop(token, None)

    async def _evict_channel_pending(self, channel_id: int) -> None:
        """Keep only one pending preview per channel

        This isn't fussiness, it's correctness: parse() takes an existing_keys() snapshot at
        chat_log_importer.py:140. If B is parsed after A is parsed but before A is written, B can't see
        A's orders and won't mark them duplicate; confirming both writes the same order twice.
        The Flask GUI gets exactly this guarantee from its single _state dict.
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
                logger.debug('Failed to disable buttons on the old preview, skipping', exc_info=True)

    def evict_expired(self) -> int:
        """Sweep up leftovers that on_timeout failed to clean after expiry

        If the message was deleted or the edit failed, on_timeout may not remove the token,
        and that batch of orders containing personal data would stay in memory forever.
        """
        deadline = time.monotonic() - self.confirm_timeout * 1.5
        expired = [t for t, p in self._pending.items() if p.created_at < deadline]
        for token in expired:
            self._pending.pop(token, None)
        return len(expired)

    def has_pending(self) -> bool:
        return bool(self._pending)

    # ─────────────────────── Incoming messages ───────────────────────

    async def handle_message(self, message: discord.Message) -> None:
        """Entry point when a new message arrives in a channel

        The check order is deliberate: first filter out ourselves, then the channel, and only then permissions.
        """
        # Without this, the bot's own preview would trigger another parse and burn through the LLM budget
        if message.author.bot:
            return

        # Stay completely silent if it's neither a DM nor the configured channel: the bot may legitimately sit in other channels
        if not self.is_allowed_context(message.channel.id, message.guild is None):
            return

        if not self.is_authorized(message.author.id):
            logger.warning('Unauthorized user attempted an import: %s (%s)', message.author, message.author.id)
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

        # Deliberately no await between the check and acquiring the lock: an uncontended asyncio.Lock
        # is acquired immediately without yielding, so these two steps are atomic. If an await were inserted
        # (e.g. sending a message before taking the lock), a second message could pass the check above and
        # wait on the lock, turning "reject" into "queue".
        async with self._import_lock:
            self._import_started_at = time.monotonic()
            try:
                await self._parse_and_preview(message, chat_log, source_label)
            finally:
                self._import_started_at = None

    async def _extract_chat_log(self, message: discord.Message):
        """Extract the chat log from the message or attachment; returns (content, source label)

        Returns (None, None) when nothing is found (or it's deliberately skipped). Every bit of chatter
        in the channel could trigger a multi-minute, paid parse, so this filtering is the cost firewall.
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
            logger.info('Read attachment %s (%s bytes, encoding %s)', attachment.filename, attachment.size, encoding)

            label = f'{attachment.filename}（{len(chat_log):,} 字元）'
            if len(text_files) > 1:
                label += f'／另外 {len(text_files) - 1} 個檔案已略過'
            return chat_log, label

        content = (message.content or '').strip()

        if not content:
            # Attachments aren't gated by the message_content intent, but text is. Without the intent
            # this is always an empty string; the symptom is "uploading a file works, pasting text does nothing".
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

        # The caller (handle_message) already holds _import_lock
        try:
            # Deliberately not using asyncio.wait_for: it cancels the await, not the thread, and with
            # max_workers=1 every subsequent import would be stuck behind the zombie job.
            async with channel.typing():
                parsed_orders = await self._run(self._import_pool, self._blocking_parse, chat_log)
        except Exception as error:
            logger.exception('Failed to parse chat log')
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
        """Update the elapsed time every 30 seconds so people know it's still alive"""
        try:
            while True:
                await asyncio.sleep(30)
                elapsed = int(time.monotonic() - started)
                await status.edit(
                    content=f'🤖 解析中…（{source_label}，模型 {self.model}）已跑 {elapsed} 秒')
        except asyncio.CancelledError:
            raise
        except discord.HTTPException:
            logger.debug('Failed to update progress message, skipping', exc_info=True)

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

        # Send sequentially, not with asyncio.gather: it would hit the 5 messages / 5 s per-channel rate limit,
        # discord.py would back off and retry, and the result would still be serialized, just with unpredictable timing.
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

    # ─────────────────────── Shutdown ───────────────────────

    def shutdown(self) -> None:
        self._import_pool.shutdown(wait=False)
        self._organize_pool.shutdown(wait=False)


def _decode(raw: bytes):
    """Try several common encodings in order; returns (text, encoding used)"""
    for encoding in TEXT_ENCODINGS[:-1]:
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    # The last resort must not fail: better a few characters become � than the whole batch being unreadable
    return raw.decode('utf-8', errors='replace'), 'utf-8 (replace)'


def setup_discord_handlers(bot, handler: DiscordOrderHandler) -> None:
    """Attach events and slash commands to the bot

    Follows setup_liff_routes(app, liff_handler) in liff_handler.py:270.
    """

    @bot.event
    async def on_ready():
        logger.info('Logged in to Discord: %s (%s)', bot.user, bot.user.id)
        if handler.order_channel_id:
            logger.info('Scope: DMs, plus channel ID %s', handler.order_channel_id)
        else:
            logger.info('Scope: DMs only (DISCORD_ORDER_CHANNEL_ID not set)')
        if handler.order_channel_id and not bot.intents.message_content:
            logger.warning('message_content intent is not enabled; text pasted in the channel will be unreadable'
                           ' (.txt attachments and DMs still work)')
        if not _evict_loop.is_running():
            _evict_loop.start()

    @bot.event
    async def on_message(message: discord.Message):
        try:
            await handler.handle_message(message)
        except Exception:
            logger.exception('Unexpected error while handling message')

    @tasks.loop(minutes=10)
    async def _evict_loop():
        removed = handler.evict_expired()
        if removed:
            logger.info('Cleared %s expired unconfirmed import previews', removed)

    def _guard():
        async def predicate(interaction: discord.Interaction) -> bool:
            # guild_id being None means this is a DM
            if not handler.is_allowed_context(interaction.channel_id, interaction.guild_id is None):
                raise app_commands.CheckFailure('CHANNEL')
            if not handler.is_authorized(interaction.user.id):
                raise app_commands.CheckFailure('AUTH')
            return True
        return app_commands.check(predicate)

    # No @app_commands.guild_only(): adding it would make this command disappear from DMs
    # (Command descriptions below are shown to staff in Discord and stay Chinese.)
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
            logger.exception('Date sheet preview failed')
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
            logger.exception('Failed to scan for non-shipping-day orders')
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

        logger.exception('Slash command error', exc_info=error)
        text = f'❌ 指令執行失敗：{fmt.truncate(str(error), 500)}'
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
