import os
from dotenv import load_dotenv

load_dotenv()

# LINE Bot 配置
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

# OpenAI 配置
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4-0125-preview')

# DSPy 配置
DSPY_API_KEY = os.getenv('DSPY_API_KEY', OPENAI_API_KEY)  # 預設使用 OpenAI API Key
DSPY_MODEL = os.getenv('DSPY_MODEL', 'gpt-5.6-luna')
DSPY_MAX_RETRIES = int(os.getenv('DSPY_MAX_RETRIES', 3))

# 訂單客戶端類型選擇
ORDER_CLIENT_TYPE = os.getenv('ORDER_CLIENT_TYPE', 'openai')  # 'openai' 或 'dspy'

# Google Sheets 配置
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEETS_ID')
GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH', 'credentials.json')

# 授權用戶列表
AUTHORIZED_USERS = os.getenv('AUTHORIZED_USERS', '').split(',')

# Flask 配置
PORT = int(os.getenv('PORT', 5000))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

def _int_env(name: str, default: int = 0) -> int:
    """讀整數設定，壞掉就退回預設值

    config.py 是被 main.py 直接 import 的，模組層的 int() 一旦拋 ValueError
    會連 LINE bot 一起啟動不了，所以這裡吞掉格式錯誤。
    """
    try:
        return int(os.getenv(name, '') or default)
    except ValueError:
        return default


# Discord Bot 配置
# 刻意和上面的 AUTHORIZED_USERS 分開：那是 LINE 的 user ID，和 Discord 是不同的 ID 空間，
# 混在同一個變數裡會讓「這個 ID 是誰」變得無法判斷。
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_ORDER_CHANNEL_ID = _int_env('DISCORD_ORDER_CHANNEL_ID')
DISCORD_GUILD_ID = _int_env('DISCORD_GUILD_ID')  # 選填；設了斜線指令會立即生效
# 這裡有過濾空字串，所以沒設定時是 []（不像 AUTHORIZED_USERS 會變成 ['']），
# discord_bot.py 的 _check_config() 才能靠「空的就是沒設定」擋下啟動。
DISCORD_AUTHORIZED_USERS = [
    user_id.strip()
    for user_id in os.getenv('DISCORD_AUTHORIZED_USERS', '').split(',')
    if user_id.strip()
]
DISCORD_CONFIRM_TIMEOUT = _int_env('DISCORD_CONFIRM_TIMEOUT', 3600)  # 預覽按鈕的有效秒數
DISCORD_MAX_UPLOAD_BYTES = _int_env('DISCORD_MAX_UPLOAD_BYTES', 1_048_576)
DISCORD_IGNORE_PREFIX = os.getenv('DISCORD_IGNORE_PREFIX', '#')  # 開頭是這個的訊息不解析
DISCORD_MIN_CHAT_LOG_CHARS = _int_env('DISCORD_MIN_CHAT_LOG_CHARS', 20)

# LINE 客戶訊息 → Discord 推播確認
# 0 = 沒設定，退回 DISCORD_AUTHORIZED_USERS 的第一個
DISCORD_LINE_NOTIFY_USER_ID = _int_env('DISCORD_LINE_NOTIFY_USER_ID')
LINE_MIN_MESSAGE_CHARS = _int_env('LINE_MIN_MESSAGE_CHARS', 5)
