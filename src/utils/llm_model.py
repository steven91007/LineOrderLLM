"""DSPy 語言模型的建構與模型名稱處理

集中兩件跟 litellm 有關、每個進入點都會踩到的事：

1. 供應商前綴。DSPy 底層走 litellm，litellm 要靠模型名稱決定打哪家 API：
   名字在它內建的模型表裡（例如 gpt-4o-mini）才推斷得出供應商，新的或
   自訂的名字（例如 gpt-5.6-luna）不在表裡，就會拋
       litellm.BadRequestError: LLM Provider NOT provided.
   所以送進 dspy.LM 之前一律補上 `供應商/` 前綴。

2. 推理型模型（o1/o3/o4、gpt-5.x）的參數要求和一般模型不同：不接受
   max_tokens（要用 max_completion_tokens），且 temperature 必須是 1.0。
   DSPy 2.6 的偵測只認得 o1/o3/o4 開頭，gpt-5.x 得自己處理。
"""
import re

import dspy

DEFAULT_PROVIDER = 'openai'

REASONING_MODEL_PATTERN = re.compile(r'^(o[134](-mini)?|gpt-5)', re.IGNORECASE)
REASONING_MAX_TOKENS = 20000


def normalize_model_name(model: str, default_provider: str = DEFAULT_PROVIDER) -> str:
    """補上 litellm 需要的供應商前綴

    已經有前綴（含 `/`）的名字原封不動，所以要用其他供應商時，
    直接把 DSPY_MODEL 寫成 `anthropic/...`、`gemini/...` 即可。
    """
    name = (model or '').strip()
    if not name or '/' in name:
        return name
    return f'{default_provider}/{name}'


def is_reasoning_model(model: str) -> bool:
    """判斷是否為推理型模型（含供應商前綴時取最後一段）"""
    name = (model or '').split('/')[-1]
    return bool(REASONING_MODEL_PATTERN.match(name))


def build_lm(model: str, api_key: str, max_tokens: int = 4000,
             temperature: float = 0.1) -> dspy.LM:
    """建立 dspy.LM，並依模型種類套用正確的參數

    傳入的 model 應該已經過 normalize_model_name（這裡再做一次也無妨）。
    推理型模型會忽略傳入的 max_tokens / temperature，改用 REASONING_MAX_TOKENS
    與 temperature=1.0。
    """
    model = normalize_model_name(model)

    if not is_reasoning_model(model):
        return dspy.LM(model=model, api_key=api_key,
                       max_tokens=max_tokens, temperature=temperature)

    lm = dspy.LM(model=model, api_key=api_key,
                 max_tokens=REASONING_MAX_TOKENS, temperature=1.0)
    # DSPy 仍會把 max_tokens 塞進 kwargs，這裡手動換成正確的參數名。
    lm.kwargs.pop('max_tokens', None)
    lm.kwargs['max_completion_tokens'] = REASONING_MAX_TOKENS
    lm.kwargs['temperature'] = 1.0
    return lm
