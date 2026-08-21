"""匯入確認與日期分頁整理的按鈕介面

兩個 View 的骨架一樣：
    連點防護 → 停用按鈕並 ack → 丟給工作執行緒 → 用 channel.send 送結果

「用 channel.send 送結果」不是風格問題：interaction token 只有 15 分鐘，
而 /organize 寫入在 20 個以上日期分頁時要 60+ 次 Sheets 呼叫，遇到配額退避
就可能超過。用 followup.send 會直接 404，操作者永遠不會知道那個破壞性的
重寫到底做完沒有。channel.send 是普通的 REST 呼叫，不會過期。
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

import discord

from . import discord_format as fmt

if TYPE_CHECKING:  # 只為了型別標註，避免和 handler 互相 import
    from .discord_handler import DiscordOrderHandler, PendingImport

logger = logging.getLogger(__name__)


class _ConfirmView(discord.ui.View):
    """兩個確認介面共用的部分"""

    def __init__(self, handler: 'DiscordOrderHandler', *, timeout: float):
        super().__init__(timeout=timeout)
        self.handler = handler
        self.message: Optional[discord.Message] = None
        # 連點防護。檢查和設定之間沒有 await，單執行緒的 event loop 下
        # 這就是一個貨真價實的 mutex。
        self._consumed = False

    def _add_button(self, label: str, style: discord.ButtonStyle, callback,
                    disabled: bool = False) -> None:
        """按鈕標籤要帶執行時算出來的數字，所以不能用 @discord.ui.button decorator"""
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
            # 訊息可能已經被刪掉了，逾時清理本來就是 best-effort
            logger.debug('逾時後更新訊息失敗，略過', exc_info=True)

    def _cleanup(self) -> None:
        """子類別覆寫：把自己從 handler 的暫存狀態裡移除"""

    def _claim(self) -> bool:
        """搶下這次點擊；已經被按過就回 False"""
        if self._consumed:
            return False
        self._consumed = True
        return True


class ImportConfirmView(_ConfirmView):
    """匯入預覽下方的「寫入可寫入的 / 含需確認 / 取消」"""

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
        # 數字是 ready + review，不是 review：write(include_review=True) 的
        # allowed 是 {'ready', 'review'}（chat_log_importer.py:364），兩種都會寫。
        # 只標 review 的話，按鈕上的數字每次都會和 appended_rows 對不上。
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
        # 一次往返同時做完 3 秒 ack 和停用按鈕
        await interaction.response.edit_message(content='⏳ 寫入中…', view=self)
        self.stop()
        self._cleanup()

        # 在 await 工作執行緒之前先抓好 channel
        channel = interaction.channel
        pending = self.pending

        try:
            result = await self.handler.write_orders(pending.orders, include_review)
        except Exception as error:
            logger.exception('寫入試算表失敗')
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
    """/organize 預覽下方的「確認寫入 / 取消」"""

    def __init__(self, handler: 'DiscordOrderHandler', user_id: int,
                 source_sheet: Optional[str], *, timeout: float):
        super().__init__(handler, timeout=timeout)
        self.user_id = user_id
        self.source_sheet = source_sheet

        # danger 樣式：這個動作會先清空日期分頁再重寫，不是單純的附加
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
            logger.exception('日期分頁整理失敗')
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
