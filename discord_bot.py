#!/usr/bin/env python
"""Discord 訂單機器人

在指定的 Discord 頻道貼上聊天紀錄（或丟 .txt 檔），機器人會解析成訂單、
顯示預覽，按下按鈕才寫入 Google 試算表。另外提供 /organize 指令把總表
依出貨日拆成日期分頁。

用法：
    # 只檢查設定，不連線
    python discord_bot.py --check

    # 啟動機器人
    python discord_bot.py

設定請看 DISCORD_SETUP.md。最容易漏掉的是 Developer Portal 裡的
MESSAGE CONTENT INTENT——沒開的話「丟 .txt 檔正常、貼文字沒反應」。
"""

import argparse
import logging
import sys

import discord
from discord.ext import commands

import config
from src.handlers.discord_handler import DiscordOrderHandler, setup_discord_handlers
from src.utils import langfuse_tracing as tracing

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _check_config():
    """回傳缺少的設定名稱

    DISCORD_AUTHORIZED_USERS 沒設定時一定要擋下來：這支機器人會寫進正式的
    訂單試算表，fail-open 等於讓伺服器裡任何人都能下單。
    """
    missing = []
    if not config.DSPY_API_KEY:
        missing.append('OPENAI_API_KEY')
    if not config.GOOGLE_SHEET_ID:
        missing.append('GOOGLE_SHEETS_ID')
    if not config.GOOGLE_CREDENTIALS_PATH:
        missing.append('GOOGLE_SHEETS_CREDENTIALS_PATH')
    if not config.DISCORD_BOT_TOKEN:
        missing.append('DISCORD_BOT_TOKEN')
    # DISCORD_ORDER_CHANNEL_ID 是選填的：沒設定就只走私訊
    if not config.DISCORD_AUTHORIZED_USERS:
        missing.append('DISCORD_AUTHORIZED_USERS')
    return missing


def build_bot():
    intents = discord.Intents.default()
    # message_content 是特權 intent，要先到 Developer Portal → Bot →
    # Privileged Gateway Intents 開啟，沒開就在這裡要求會連不上（PrivilegedIntentsRequired）。
    #
    # 但私訊給機器人的訊息不受這個限制，所以只有在真的要讀「伺服器頻道」的
    # 文字時才需要它。純私訊用法就完全不用碰 Developer Portal 那個開關。
    intents.message_content = bool(config.DISCORD_ORDER_CHANNEL_ID)

    bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

    handler = DiscordOrderHandler(
        api_key=config.DSPY_API_KEY,
        sheet_id=config.GOOGLE_SHEET_ID,
        credentials_path=config.GOOGLE_CREDENTIALS_PATH,
        model=config.DSPY_MODEL,
        authorized_users=config.DISCORD_AUTHORIZED_USERS,
        order_channel_id=config.DISCORD_ORDER_CHANNEL_ID,
        confirm_timeout=config.DISCORD_CONFIRM_TIMEOUT,
        max_upload_bytes=config.DISCORD_MAX_UPLOAD_BYTES,
        ignore_prefix=config.DISCORD_IGNORE_PREFIX,
        min_chat_log_chars=config.DISCORD_MIN_CHAT_LOG_CHARS,
    )
    setup_discord_handlers(bot, handler)

    async def setup_hook():
        # 一定要全域同步：私訊裡只看得到全域指令，只同步到伺服器的話
        # /organize 在私訊裡會整個消失。
        await bot.tree.sync()
        logger.info('斜線指令已全域同步（私訊可用；伺服器內最多可能要一小時才出現）')

        # 有指定伺服器的話再多同步一份，那個伺服器裡就會立即生效
        if config.DISCORD_GUILD_ID:
            guild = discord.Object(id=config.DISCORD_GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            logger.info('斜線指令已同步到伺服器 %s（立即生效）', config.DISCORD_GUILD_ID)

    bot.setup_hook = setup_hook
    bot._order_handler = handler
    return bot


def main():
    parser = argparse.ArgumentParser(description='Discord 訂單匯入機器人')
    parser.add_argument('--check', action='store_true',
                        help='只檢查設定是否完整，不連線到 Discord')
    args = parser.parse_args()

    missing = _check_config()
    if missing:
        print('❌ 設定不完整，缺少：' + '、'.join(missing))
        return 1

    if args.check:
        print('✅ 設定完整')
        if config.DISCORD_ORDER_CHANNEL_ID:
            print(f'   可用範圍：私訊，以及頻道 {config.DISCORD_ORDER_CHANNEL_ID}')
            print('   需要在 Developer Portal 開啟 MESSAGE CONTENT INTENT')
        else:
            print('   可用範圍：只有私訊')
            print('   不需要 MESSAGE CONTENT INTENT')
        print(f'   授權使用者：{len(config.DISCORD_AUTHORIZED_USERS)} 位')
        print(f'   模型：{config.DSPY_MODEL}')
        return 0

    # CLAUDE.md：追蹤由進入點統一啟用，而且要在任何 DSPy 模組建立之前。
    # 這裡還多一層意義——langfuse_tracing 的 _initialized 是沒有鎖的模組層旗標，
    # 而 importer 是在工作執行緒上建的，先在主執行緒跑完就沒有競態。
    tracing.setup()

    bot = build_bot()
    try:
        bot.run(config.DISCORD_BOT_TOKEN, log_handler=None)
    finally:
        bot._order_handler.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
