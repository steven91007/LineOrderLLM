"""Langfuse 追蹤設定

用 OpenInference 的 DSPy instrumentor 自動捕捉每一次 LLM 呼叫
（prompt、completion、token 數、延遲、模型參數），再由本模組補上
DSPy 看不到的那一半：品項對照、地址標準化、日期驗證、重複檢查、寫入試算表。

Session 的切法：**一筆訂單一個 session**。session_id 取「收件人｜電話｜配送日」，
這樣同一筆訂單從解析、複查到寫入試算表的所有 trace 會被串在一起，
之後客人改單再跑一次也會落進同一個 session，可以完整回放這筆訂單的來龍去脈。
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_initialized = False
_enabled = False


def is_enabled() -> bool:
    """Langfuse 是否可用。沒設金鑰時整套追蹤靜默停用，不影響主流程。"""
    return _enabled


def setup() -> bool:
    """初始化 Langfuse 與 DSPy instrumentor，回傳是否啟用成功

    重複呼叫是安全的（Flask 每個請求都會建新的 importer，但只會初始化一次）。
    """
    global _initialized, _enabled
    if _initialized:
        return _enabled

    _initialized = True

    if not (os.getenv('LANGFUSE_PUBLIC_KEY') and os.getenv('LANGFUSE_SECRET_KEY')):
        logger.info('未設定 LANGFUSE_PUBLIC_KEY／LANGFUSE_SECRET_KEY，停用 Langfuse 追蹤')
        return False

    try:
        from langfuse import get_client
        from openinference.instrumentation.dspy import DSPyInstrumentor

        client = get_client()
        if not client.auth_check():
            logger.warning('Langfuse 認證失敗，停用追蹤（請檢查金鑰與 LANGFUSE_BASE_URL）')
            return False

        DSPyInstrumentor().instrument()
        _enabled = True
        logger.info(f'Langfuse 追蹤已啟用：{os.getenv("LANGFUSE_BASE_URL")}')
    except Exception as error:
        # 追蹤壞掉絕對不能讓訂單處理跟著壞掉
        logger.warning(f'Langfuse 初始化失敗，停用追蹤：{error}')
        return False

    return _enabled


@contextmanager
def trace(name: str, session_id: Optional[str] = None,
          input_data: Any = None, metadata: Optional[Dict[str, Any]] = None):
    """建立一個 span，可選擇性掛上 session

    未啟用時是無操作的 context manager，呼叫端不需要做任何判斷。
    yield 出來的物件有 .update(output=..., metadata=...) 可以補寫結果；
    停用時 yield 的是 _NullSpan，同樣有 .update()，所以呼叫端寫法一致。
    """
    if not _enabled:
        yield _NullSpan()
        return

    try:
        from langfuse import get_client, propagate_attributes
    except ImportError:
        yield _NullSpan()
        return

    # 只有「建立 span」這段可以失敗就算了；yield 之後的錯誤是呼叫端的業務錯誤，
    # 必須原樣往外拋。
    #
    # 之前這裡是把整個 with（含 yield）包在 try/except 裡，呼叫端 body 一拋例外，
    # 就會被這裡接住然後再 yield 一次 —— contextmanager 不允許 throw 之後再 yield，
    # Python 會轉成 RuntimeError: generator didn't stop after throw()，
    # 真正的錯誤與 traceback 全部消失，非常難查。
    from contextlib import ExitStack

    stack = ExitStack()
    try:
        client = get_client()
        span = stack.enter_context(
            client.start_as_current_observation(as_type='span', name=name)
        )
        if input_data is not None:
            span.update(input=input_data)
        if metadata:
            span.update(metadata=metadata)
        if session_id:
            stack.enter_context(propagate_attributes(session_id=session_id[:200]))
    except Exception as error:
        logger.warning(f'Langfuse span「{name}」建立失敗，略過追蹤：{error}')
        stack.close()
        yield _NullSpan()
        return

    # ExitStack 會把 body 的例外正確傳給 span 收尾，同時讓例外繼續往外拋
    with stack:
        yield span


def score(name: str, value: float, comment: Optional[str] = None):
    """對目前的 trace 打分數，用來累積解析品質的長期統計"""
    if not _enabled:
        return
    try:
        from langfuse import get_client
        get_client().score_current_trace(name=name, value=value, comment=comment)
    except Exception as error:
        logger.debug(f'Langfuse 評分失敗：{error}')


def flush():
    """把緩衝中的追蹤資料送出

    CLI 這種跑完就結束的程式一定要呼叫，否則行程結束時資料還沒送出去。
    """
    if not _enabled:
        return
    try:
        from langfuse import get_client
        get_client().flush()
    except Exception as error:
        logger.debug(f'Langfuse flush 失敗：{error}')


class _NullSpan:
    """停用追蹤時的替身，讓呼叫端不必到處寫 if"""

    def update(self, **kwargs):
        pass

    def score(self, **kwargs):
        pass


# --- 相容別名 ---
# dspy_client.py 與 openai_client.py 用的是 init_tracing／observation／
# update_observation 這組命名，與本模組的 setup／trace 是同一件事。
# 保留兩套名稱，避免去改動那兩個檔案既有的呼叫方式。

init_tracing = setup


@contextmanager
def observation(name: str, input: Any = None, metadata: Optional[Dict[str, Any]] = None,
                session_id: Optional[str] = None):
    """trace() 的別名，參數名用 input（而非 input_data）"""
    with trace(name, session_id=session_id, input_data=input, metadata=metadata) as span:
        yield span


def update_observation(span, **kwargs):
    """對 observation() 產生的 span 補寫 input／output／metadata

    span 可能是 None 或 _NullSpan（追蹤停用時），一律安全略過。
    """
    if span is None:
        return
    try:
        span.update(**kwargs)
    except Exception as error:
        logger.debug(f'Langfuse observation 更新失敗：{error}')
