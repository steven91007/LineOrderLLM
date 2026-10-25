#!/usr/bin/env python3
"""
Flask application - with the LIFF order editor integrated
"""
import os
import logging
from flask import Flask, request, abort, render_template
from dotenv import load_dotenv

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent

from src.handlers.order_handler import OrderHandler
from src.handlers.liff_handler import setup_liff_routes

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the Flask application
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')

# LINE Bot settings
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LIFF_ID = os.getenv('LIFF_ID')  # LIFF app ID

# Server settings
BASE_URL = os.getenv('BASE_URL')  # Server base URL (e.g., https://your-domain.com)

# DSPy/OpenAI settings
DSPY_API_KEY = os.getenv('DSPY_API_KEY') or os.getenv('OPENAI_API_KEY')
DSPY_MODEL = os.getenv('DSPY_MODEL', 'gpt-4o-mini')

# Google Sheets settings
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')

# Authorized user list
AUTHORIZED_USERS = os.getenv('AUTHORIZED_USERS', '*').split(',')

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    logger.error("Missing LINE channel credentials")
    exit(1)

if not DSPY_API_KEY:
    logger.error("Missing DSPy/OpenAI API key")
    exit(1)

# Initialize the LINE Bot SDK
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# Initialize the order handler
order_handler = OrderHandler(
    configuration=configuration,
    authorized_users=AUTHORIZED_USERS,
    client_type='dspy',
    openai_api_key=DSPY_API_KEY,
    dspy_model=DSPY_MODEL,
    google_sheet_id=GOOGLE_SHEET_ID,
    google_credentials_path=GOOGLE_CREDENTIALS_PATH,
    liff_id=LIFF_ID,  # Pass in the LIFF ID
    base_url=BASE_URL  # Pass in the server base URL
)

# Register the LIFF routes
setup_liff_routes(app, order_handler.liff_handler)

@app.route("/", methods=['GET'])
def home():
    """Home page (the HTML below is user-facing and stays in Chinese)."""
    return """
    <h1>LINE 訂單處理系統</h1>
    <h2>🌐 LIFF 版本</h2>
    <p>✨ 新功能：網頁訂單編輯器</p>
    <ul>
        <li>📱 在 LINE 中輸入 <code>#訂單</code> 開始</li>
        <li>🌐 點擊「網頁編輯」開啟 LIFF 編輯器</li>
        <li>📝 表格式編輯介面，支援批量修改</li>
        <li>💾 一鍵儲存，自動更新 Google Sheets</li>
    </ul>
    <hr>
    <p>📊 系統狀態：運行中</p>
    <p>🤖 DSPy 引擎：啟用</p>
    <p>📋 Google Sheets：{}</p>
    <p>🌐 LIFF 編輯器：{}</p>
    """.format(
        "✅ 已連接" if GOOGLE_SHEET_ID else "❌ 未設定",
        "✅ 已啟用" if LIFF_ID else "❌ 未設定"
    )

@app.route("/callback", methods=['POST'])
def callback():
    """LINE webhook callback"""
    # Get the X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # Get the request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # Handle the webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    """Handle text message events."""
    try:
        order_handler.handle_text_message(event)
    except Exception as e:
        logger.error(f"Error handling text message: {e}")

@handler.add(PostbackEvent)
def handle_postback(event):
    """Handle postback events."""
    try:
        order_handler.handle_postback(event)
    except Exception as e:
        logger.error(f"Error handling postback: {e}")

@app.route('/health')
def health_check():
    """Health check."""
    return {
        'status': 'healthy',
        'features': {
            'dspy_engine': bool(DSPY_API_KEY),
            'google_sheets': bool(GOOGLE_SHEET_ID),
            'liff_editor': bool(LIFF_ID)
        }
    }

@app.route('/liff/demo')
def liff_demo():
    """LIFF demo page (for testing)."""
    demo_orders = [
        {
            'receiver_name': '王小明',
            'receiver_phone': '0912345678',
            'items': [{'name': '18A禮盒', 'quantity': 2}],
            'shipping_address': '台北市信義區信義路五段7號',
            'shipping_date': '08-15',
            'sender_name': None,
            'sender_phone': None
        }
    ]
    
    # Create a demo session
    session_id = order_handler.liff_handler.create_liff_session('demo_user', {
        'orders': demo_orders,
        'total_orders': 1
    })
    
    return f'''
    <h2>LIFF 編輯器示範</h2>
    <p>這是 LIFF 編輯器的示範版本</p>
    <a href="/liff/edit?session={session_id}" target="_blank">
        <button style="padding: 10px 20px; font-size: 16px; background: #2563EB; color: white; border: none; border-radius: 5px;">
            開啟編輯器 (示範)
        </button>
    </a>
    <br><br>
    <small>注意：這是示範版本，不會真正寫入 Google Sheets</small>
    '''

if __name__ == "__main__":
    # Periodically clean up expired LIFF sessions
    import threading
    import time
    
    def cleanup_sessions():
        while True:
            time.sleep(3600)  # Clean up once an hour
            try:
                order_handler.liff_handler.cleanup_expired_sessions()
            except Exception as e:
                logger.error(f"Error cleaning up LIFF sessions: {e}")
    
    cleanup_thread = threading.Thread(target=cleanup_sessions, daemon=True)
    cleanup_thread.start()

    app.run(debug=True, host='0.0.0.0', port=5001)