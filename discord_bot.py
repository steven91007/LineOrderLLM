#!/usr/bin/env python
"""Discord order bot

Paste a chat log (or upload a .txt file) in the configured Discord channel and the bot parses it into orders,
shows a preview, and only writes to the Google spreadsheet once a button is pressed. It also provides an
/organize command that splits the master sheet into per-shipping-date sheets.

Usage:
    # Check configuration only, without connecting
    python discord_bot.py --check

    # Start the bot
    python discord_bot.py

See DISCORD_SETUP.md for setup. The most commonly missed step is the MESSAGE CONTENT INTENT
in the Developer Portal -- without it, "uploading a .txt works, pasting text does nothing".
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
    """Return the names of missing settings

    A missing DISCORD_AUTHORIZED_USERS must be blocked: this bot writes to the production
    order spreadsheet, and failing open would let anyone in the server place orders.
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
    # DISCORD_ORDER_CHANNEL_ID is optional: if unset, only DMs are used
    if not config.DISCORD_AUTHORIZED_USERS:
        missing.append('DISCORD_AUTHORIZED_USERS')
    return missing


def build_bot():
    intents = discord.Intents.default()
    # message_content is a privileged intent; it must first be enabled under Developer Portal -> Bot ->
    # Privileged Gateway Intents, otherwise requesting it here fails to connect (PrivilegedIntentsRequired).
    #
    # DMs to the bot aren't subject to this restriction, though, so it's only needed when we actually
    # read text in a server channel. DM-only usage never needs that Developer Portal toggle.
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
        # Must sync globally: only global commands are visible in DMs; syncing only to the server
        # would make /organize vanish from DMs entirely.
        await bot.tree.sync()
        logger.info('Slash commands synced globally (available in DMs; may take up to an hour to appear in servers)')

        # If a server is specified, sync an extra copy there so it takes effect immediately
        if config.DISCORD_GUILD_ID:
            guild = discord.Object(id=config.DISCORD_GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            logger.info('Slash commands synced to server %s (effective immediately)', config.DISCORD_GUILD_ID)

    bot.setup_hook = setup_hook
    bot._order_handler = handler
    return bot


def main():
    parser = argparse.ArgumentParser(description='Discord order import bot')
    parser.add_argument('--check', action='store_true',
                        help='Only check that the configuration is complete, without connecting to Discord')
    args = parser.parse_args()

    missing = _check_config()
    if missing:
        print('❌ Configuration incomplete, missing: ' + ', '.join(missing))
        return 1

    if args.check:
        print('✅ Configuration complete')
        if config.DISCORD_ORDER_CHANNEL_ID:
            print(f'   Scope: DMs, plus channel {config.DISCORD_ORDER_CHANNEL_ID}')
            print('   MESSAGE CONTENT INTENT must be enabled in the Developer Portal')
        else:
            print('   Scope: DMs only')
            print('   MESSAGE CONTENT INTENT not required')
        print(f'   Authorized users: {len(config.DISCORD_AUTHORIZED_USERS)}')
        print(f'   Model: {config.DSPY_MODEL}')
        return 0

    # CLAUDE.md: tracing is enabled once at the entry point, before any DSPy module is created.
    # There's an extra reason here -- langfuse_tracing's _initialized is an unlocked module-level flag,
    # and the importer is built on a worker thread; running it first on the main thread avoids a race.
    tracing.setup()

    bot = build_bot()
    try:
        bot.run(config.DISCORD_BOT_TOKEN, log_handler=None)
    finally:
        bot._order_handler.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
