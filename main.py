from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    PostbackEvent
)

# 載入環境變數
load_dotenv()

# 匯入自定義模組
from config import (
    LINE_CHANNEL_ACCESS_TOKEN,
    LINE_CHANNEL_SECRET,
    AUTHORIZED_USERS,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    GOOGLE_SHEET_ID,
    GOOGLE_CREDENTIALS_PATH
)
from src.handlers.order_handler import OrderHandler

app = Flask(__name__)

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 初始化訂單處理器
order_handler = OrderHandler(
    configuration, 
    AUTHORIZED_USERS,
    openai_api_key=OPENAI_API_KEY,
    openai_model=OPENAI_MODEL,
    google_sheet_id=GOOGLE_SHEET_ID,
    google_credentials_path=GOOGLE_CREDENTIALS_PATH
)

@app.route("/")
def index():
    return "Hello, World!"

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    # 使用訂單處理器處理訊息
    order_handler.handle_text_message(event)


@handler.add(PostbackEvent)
def handle_postback(event):
    # 處理按鈕回應
    order_handler.handle_postback(event)

if __name__ == "__main__":
    from config import PORT, DEBUG
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)