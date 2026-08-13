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