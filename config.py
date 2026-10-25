import os
from dotenv import load_dotenv

load_dotenv()

# LINE Bot settings
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

# OpenAI settings
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4-0125-preview')

# DSPy settings
DSPY_API_KEY = os.getenv('DSPY_API_KEY', OPENAI_API_KEY)  # Defaults to the OpenAI API key
DSPY_MODEL = os.getenv('DSPY_MODEL', 'gpt-5.6-luna')
DSPY_MAX_RETRIES = int(os.getenv('DSPY_MAX_RETRIES', 3))

# TypeSafe Jev (decision model: choices, yes/no, scores; it does not generate text)
TYPESAFE_API_KEY = os.getenv('TYPESAFE_API_KEY')
TYPESAFE_MODEL = os.getenv('TYPESAFE_MODEL') or None  # None = use the API's default model

# Item judgment backend: 'gpt' (current behavior), 'shadow' (use GPT, also record whether Jev agrees), 'jev'
ITEM_JUDGE_BACKEND = os.getenv('ITEM_JUDGE_BACKEND', 'gpt')
JEV_CONFIDENCE_FLOOR = float(os.getenv('JEV_CONFIDENCE_FLOOR', '0.5'))    # below this, Jev's answer is not used
JEV_CONFIDENCE_REVIEW = float(os.getenv('JEV_CONFIDENCE_REVIEW', '0.8'))  # below this, used but flagged for manual review
JEV_TIMEOUT_SECONDS = float(os.getenv('JEV_TIMEOUT_SECONDS', '10'))

# Order client type selection
ORDER_CLIENT_TYPE = os.getenv('ORDER_CLIENT_TYPE', 'openai')  # 'openai' or 'dspy'

# Google Sheets settings
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEETS_ID')
GOOGLE_CREDENTIALS_PATH = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH', 'credentials.json')

# Authorized user list
AUTHORIZED_USERS = os.getenv('AUTHORIZED_USERS', '').split(',')

# Flask settings
PORT = int(os.getenv('PORT', 5000))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

def _int_env(name: str, default: int = 0) -> int:
    """Read an integer setting; fall back to the default if it is malformed.

    config.py is imported directly by main.py, so if a module-level int() raised ValueError
    the LINE bot would fail to start too. That is why format errors are swallowed here.
    """
    try:
        return int(os.getenv(name, '') or default)
    except ValueError:
        return default


# Discord Bot settings
# Deliberately kept separate from AUTHORIZED_USERS above: those are LINE user IDs, a different ID space from Discord;
# mixing them in one variable would make it impossible to tell whose ID is whose.
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_ORDER_CHANNEL_ID = _int_env('DISCORD_ORDER_CHANNEL_ID')
DISCORD_GUILD_ID = _int_env('DISCORD_GUILD_ID')  # Optional; when set, slash commands take effect immediately
# Empty strings are filtered out here, so when unset this is [] (unlike AUTHORIZED_USERS, which becomes ['']),
# which lets _check_config() in discord_bot.py block startup on the rule "empty means not configured".
DISCORD_AUTHORIZED_USERS = [
    user_id.strip()
    for user_id in os.getenv('DISCORD_AUTHORIZED_USERS', '').split(',')
    if user_id.strip()
]
DISCORD_CONFIRM_TIMEOUT = _int_env('DISCORD_CONFIRM_TIMEOUT', 3600)  # How many seconds the preview buttons stay valid
DISCORD_MAX_UPLOAD_BYTES = _int_env('DISCORD_MAX_UPLOAD_BYTES', 1_048_576)
DISCORD_IGNORE_PREFIX = os.getenv('DISCORD_IGNORE_PREFIX', '#')  # Messages starting with this prefix are not parsed
DISCORD_MIN_CHAT_LOG_CHARS = _int_env('DISCORD_MIN_CHAT_LOG_CHARS', 20)
