"""
DSPy Signature 定義
"""
import dspy


class OrderTypeSignature(dspy.Signature):
    """識別訂單類型：單一訂單或多訂單
    
    重要判斷規則：
    - 多訂單定義：文字中包含多個不同的收件人或多個不同的收件地址
    - 如果只有一個收件人和一個地址，即使有多個商品，也是單一訂單
    - 序號標記（1. 2. 或 一、二、）通常表示多訂單
    """
    order_text = dspy.InputField(desc="原始訂單文字")
    order_type = dspy.OutputField(desc="訂單類型：'single'（單一訂單）或 'multiple'（多訂單，2-5份）。判斷標準：是否有多個收件人或多個地址")


class SingleOrderSignature(dspy.Signature):
    """解析單一訂單並輸出 JSON 格式"""
    order_text = dspy.InputField(desc="單一訂單文字")
    order_json = dspy.OutputField(desc="單一訂單的結構化 JSON 資料，必須包含 order_type: 'single'")


class MultiOrderSignature(dspy.Signature):
    """解析多訂單並輸出 JSON 格式（最多5份訂單）"""
    order_text = dspy.InputField(desc="包含多份訂單的文字")
    orders_json = dspy.OutputField(desc="多訂單的結構化 JSON 資料，必須包含 order_type: 'multiple', total_orders, orders 陣列")


class OrderValidationSignature(dspy.Signature):
    """驗證並修正訂單 JSON 格式"""
    raw_json = dspy.InputField(desc="原始 JSON 字串")
    validated_json = dspy.OutputField(desc="驗證並修正後的 JSON 字串")


class JSONFixSignature(dspy.Signature):
    """修正無效的 JSON 格式"""
    broken_json = dspy.InputField(desc="格式錯誤的 JSON 字串")
    fixed_json = dspy.OutputField(desc="修正後的有效 JSON 字串")