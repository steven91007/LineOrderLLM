"""Button UIs for import confirmation and date sheet organizing

Both Views share the same skeleton:
    double-click guard -> disable buttons and ack -> hand off to worker thread -> send result via channel.send

"Send the result via channel.send" isn't a style choice: the interaction token only lasts 15 minutes,
and an /organize write over 20+ date sheets takes 60+ Sheets calls, which can exceed that when quota
backoff kicks in. followup.send would just 404, and the operator would never know whether the destructive
rewrite actually finished. channel.send is a plain REST call and doesn't expire.
"""

import logging
from typing import TYPE_CHECKING, Optional

import discord

from . import discord_format as fmt

if TYPE_CHECKING:  # Only for type hints, to avoid a circular import with handler
    from .discord_handler import DiscordOrderHandler, PendingImport

logger = logging.getLogger(__name__)


class _ConfirmView(discord.ui.View):
    """Parts shared by both confirmation views"""

    def __init__(self, handler: 'DiscordOrderHandler', *, timeout: float):
        super().__init__(timeout=timeout)
        self.handler = handler
        self.message: Optional[discord.Message] = None
        # Double-click guard. There's no await between the check and the set, so on the
        # single-threaded event loop this is a genuine mutex.
        self._consumed = False

    def _add_button(self, label: str, style: discord.ButtonStyle, callback,
                    disabled: bool = False) -> None:
        """Button labels include numbers computed at runtime, so the @discord.ui.button decorator can't be used"""
        button = discord.ui.Button(label=label, style=style, disabled=disabled)
        button.callback = callback
        self.add_item(button)

    def _disable_all(self) -> None:
        for item in self.children:
            item.disabled = True

    async def on_timeout(self) -> None:
        self._disable_all()
        self._cleanup()
        if self.message is None:
            return
        try:
            await self.message.edit(content='（已逾時，請重新操作一次）', view=self)
        except discord.HTTPException:
            # The message may already be deleted; timeout cleanup is best-effort anyway
            logger.debug('Failed to update message after timeout, skipping', exc_info=True)

    def _cleanup(self) -> None:
        """Overridden by subclasses: remove self from the handler's pending state"""

    def _claim(self) -> bool:
        """Claim this click; returns False if it was already pressed"""
        if self._consumed:
            return False
        self._consumed = True
        return True


class ImportConfirmView(_ConfirmView):
    """The "寫入可寫入的 / 含需確認 / 取消" (write ready / include review / cancel) buttons under the import preview"""

    def __init__(self, handler: 'DiscordOrderHandler', pending: 'PendingImport',
                 *, timeout: float):
        super().__init__(handler, timeout=timeout)
        self.pending = pending

        ready = pending.counts.get('ready', 0)
        review = pending.counts.get('review', 0)

        self._add_button(
            f'寫入可寫入的 ({ready})',
            discord.ButtonStyle.success,
            self._confirm_ready,
            disabled=(ready == 0),
        )
        # The number is ready + review, not review: allowed for write(include_review=True)
        # is {'ready', 'review'} (chat_log_importer.py:364), so both get written.
        # Showing only review would make the button count never match appended_rows.
        self._add_button(
            f'含需確認 ({ready + review})',
            discord.ButtonStyle.primary,
            self._confirm_with_review,
            disabled=(review == 0),
        )
        self._add_button('取消', discord.ButtonStyle.secondary, self._cancel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.handler.is_authorized(interaction.user.id):
            await interaction.response.send_message('你沒有使用這個機器人的權限。', ephemeral=True)
            return False
        if interaction.user.id != self.pending.user_id:
            await interaction.response.send_message('這批匯入不是你發起的。', ephemeral=True)
            return False
        return True

    def _cleanup(self) -> None:
        self.handler.drop_pending(self.pending.token)

    async def _confirm_ready(self, interaction: discord.Interaction) -> None:
        await self._confirm(interaction, include_review=False)

    async def _confirm_with_review(self, interaction: discord.Interaction) -> None:
        await self._confirm(interaction, include_review=True)

    async def _confirm(self, interaction: discord.Interaction, *, include_review: bool) -> None:
        if not self._claim():
            await interaction.response.send_message('這批匯入已經處理過了。', ephemeral=True)
            return

        self._disable_all()
        # One round trip handles both the 3-second ack and disabling the buttons
        await interaction.response.edit_message(content='⏳ 寫入中…', view=self)
        self.stop()
        self._cleanup()

        # Grab the channel before awaiting the worker thread
        channel = interaction.channel
        pending = self.pending

        try:
            result = await self.handler.write_orders(pending.orders, include_review)
        except Exception as error:
            logger.exception('Failed to write to spreadsheet')
            await channel.send(f'❌ 寫入失敗：{fmt.truncate(str(error), 500)}')
            return

        await channel.send(embed=fmt.write_result_embed(result, pending.counts, include_review))

    async def _cancel(self, interaction: discord.Interaction) -> None:
        if not self._claim():
            await interaction.response.send_message('這批匯入已經處理過了。', ephemeral=True)
            return

        self._disable_all()
        await interaction.response.edit_message(content='已取消，沒有寫入任何資料。', view=self)
        self.stop()
        self._cleanup()


class OrganizeConfirmView(_ConfirmView):
    """The "確認寫入 / 取消" (confirm write / cancel) buttons under the /organize preview"""

    def __init__(self, handler: 'DiscordOrderHandler', user_id: int,
                 source_sheet: Optional[str], *, timeout: float):
        super().__init__(handler, timeout=timeout)
        self.user_id = user_id
        self.source_sheet = source_sheet

        # danger style: this action clears date sheets and rewrites them, not a simple append
        self._add_button('確認寫入', discord.ButtonStyle.danger, self._confirm)
        self._add_button('取消', discord.ButtonStyle.secondary, self._cancel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.handler.is_authorized(interaction.user.id):
            await interaction.response.send_message('你沒有使用這個機器人的權限。', ephemeral=True)
            return False
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('這次整理不是你發起的。', ephemeral=True)
            return False
        return True

    async def _confirm(self, interaction: discord.Interaction) -> None:
        if not self._claim():
            await interaction.response.send_message('這次整理已經處理過了。', ephemeral=True)
            return

        self._disable_all()
        await interaction.response.edit_message(content='⏳ 整理日期分頁中…', view=self)
        self.stop()

        channel = interaction.channel

        try:
            result = await self.handler.organize(dry_run=False, source_sheet=self.source_sheet)
        except Exception as error:
            logger.exception('Date sheet organizing failed')
            await channel.send(f'❌ 日期分頁整理失敗：{fmt.truncate(str(error), 500)}')
            return

        await channel.send(embed=fmt.organize_result_embed(result))

    async def _cancel(self, interaction: discord.Interaction) -> None:
        if not self._claim():
            await interaction.response.send_message('這次整理已經處理過了。', ephemeral=True)
            return

        self._disable_all()
        await interaction.response.edit_message(content='已取消，沒有變動任何分頁。', view=self)
        self.stop()
