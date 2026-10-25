"""
DSPy signature definitions.
"""
import dspy


class OrderTypeSignature(dspy.Signature):
    """Identify the order type: single order or multiple orders.
    
    Key decision rules:
    - Multiple orders means: the text contains several different receivers or several different receiver addresses
    - If there is only one receiver and one address, it is a single order even if it has several items
    - Numbered markers (1. 2. or 一、二、) usually indicate multiple orders
    """
    order_text = dspy.InputField(desc="Raw order text")
    order_type = dspy.OutputField(desc="Order type: 'single' (one order) or 'multiple' (multiple orders, 2-5). Criterion: whether there are several receivers or several addresses")


class SingleOrderSignature(dspy.Signature):
    """Parse a single order and output JSON"""
    order_text = dspy.InputField(desc="Text of a single order")
    order_json = dspy.OutputField(desc="Structured JSON data for the single order; must include order_type: 'single'")


class MultiOrderSignature(dspy.Signature):
    """Parse multiple orders and output JSON (at most 5 orders)"""
    order_text = dspy.InputField(desc="Text containing multiple orders")
    orders_json = dspy.OutputField(desc="Structured JSON data for the multiple orders; must include order_type: 'multiple', total_orders, and an orders array")


class OrderValidationSignature(dspy.Signature):
    """Validate and fix the order JSON format"""
    raw_json = dspy.InputField(desc="Raw JSON string")
    validated_json = dspy.OutputField(desc="Validated and corrected JSON string")


class JSONFixSignature(dspy.Signature):
    """Fix invalid JSON"""
    broken_json = dspy.InputField(desc="Malformed JSON string")
    fixed_json = dspy.OutputField(desc="Corrected, valid JSON string")