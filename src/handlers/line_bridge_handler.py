"""LINE 官方帳號 webhook → Discord 推播確認的橋接

跑在跟 Discord bot 同一個 Python 行程裡（discord_bot.py 用背景執行緒啟動這個
Flask app），這樣才能共用 DiscordOrderHandler 的狀態（_import_lock、
ChatLogImporter 實例、待確認的 PendingImport）。

Flask 的請求處理是同步、跑在自己的執行緒上，跟 bot 的 asyncio event loop
不是同一條執行緒，所以真正的解析工作要用 asyncio.run_coroutine_threadsafe()
丟回 bot 的 loop，而且刻意不等結果——LINE 對 webhook 的回應時間要求嚴格，
LLM 解析要幾十秒，必須「收下、立刻回 200」，解析在背景做。
"""

import asyncio
import logging

from flask import Flask, abort, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent

import config
from .discord_handler import DiscordOrderHandler

logger = logging.getLogger(__name__)


def create_line_bridge_app(order_handler: DiscordOrderHandler,
                           loop: asyncio.AbstractEventLoop) -> Flask:
    app = Flask(__name__)
    line_handler = WebhookHandler(config.LINE_CHANNEL_SECRET)

    @app.route('/health')
    def health():
        return 'OK'

    @app.route('/callback', methods=['POST'])
    def callback():
        signature = request.headers.get('X-Line-Signature', '')
        body = request.get_data(as_text=True)

        try:
            line_handler.handle(body, signature)
        except InvalidSignatureError:
            logger.warning('LINE webhook 簽章驗證失敗')
            abort(400)

        return 'OK'

    @line_handler.add(MessageEvent, message=TextMessageContent)
    def on_message(event):
        text = (event.message.text or '').strip()
        if len(text) < config.LINE_MIN_MESSAGE_CHARS:
            return

        user_id = event.source.user_id
        asyncio.run_coroutine_threadsafe(
            order_handler.handle_line_message(user_id, text), loop)

    return app
