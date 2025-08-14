"""
訂單資料的 JSON Schema 定義
"""

# 單一訂單 Schema
SINGLE_ORDER_SCHEMA = {
    "type": "object",
    "properties": {
        "order_type": {
            "type": "string",
            "enum": ["single"]
        },
        "sender_name": {
            "type": ["string", "null"],
            "description": "寄件人姓名（選填）"
        },
        "sender_phone": {
            "type": ["string", "null"],
            "description": "寄件人電話（選填）"
        },
        "receiver_name": {
            "type": "string",
            "description": "收件人姓名（必填）"
        },
        "receiver_phone": {
            "type": "string",
            "description": "收件人電話（必填）"
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1}
                },
                "required": ["name", "quantity"]
            },
            "minItems": 1,
            "description": "商品清單（必填）"
        },
        "shipping_date": {
            "type": ["string", "null"],
            "pattern": "^\\d{2}-\\d{2}$|^$",
            "description": "預計發貨日期（選填，格式：MM-DD，不含年份）"
        },
        "shipping_address": {
            "type": "string",
            "minLength": 5,
            "description": "收件地址（必填）"
        }
    },
    "required": ["order_type", "receiver_name", "receiver_phone", "items", "shipping_address"],
    "additionalProperties": False
}

# 多訂單 Schema
MULTI_ORDER_SCHEMA = {
    "type": "object",
    "properties": {
        "order_type": {
            "type": "string",
            "enum": ["multiple"]
        },
        "total_orders": {
            "type": "integer",
            "minimum": 2,
            "maximum": 5,
            "description": "訂單總數（2-5份）"
        },
        "orders": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "order_index": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5
                    },
                    "sender_name": {
                        "type": ["string", "null"],
                        "description": "寄件人姓名（選填）"
                    },
                    "sender_phone": {
                        "type": ["string", "null"],
                        "description": "寄件人電話（選填）"
                    },
                    "receiver_name": {
                        "type": "string",
                        "description": "收件人姓名（必填）"
                    },
                    "receiver_phone": {
                        "type": "string",
                        "description": "收件人電話（必填）"
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "quantity": {"type": "integer", "minimum": 1}
                            },
                            "required": ["name", "quantity"]
                        },
                        "minItems": 1,
                        "description": "商品清單（必填）"
                    },
                    "shipping_date": {
                        "type": ["string", "null"],
                        "pattern": "^\\d{2}-\\d{2}$|^$",
                        "description": "預計發貨日期（選填，格式：MM-DD，不含年份）"
                    },
                    "shipping_address": {
                        "type": "string",
                        "minLength": 5,
                        "description": "收件地址（必填）"
                    }
                },
                "required": ["order_index", "receiver_name", "receiver_phone", "items", "shipping_address"],
                "additionalProperties": False
            },
            "minItems": 2,
            "maxItems": 5
        }
    },
    "required": ["order_type", "total_orders", "orders"],
    "additionalProperties": False
}

# 錯誤回應 Schema
ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "order_type": {
            "type": "string",
            "enum": ["error"]
        },
        "error_message": {
            "type": "string",
            "description": "錯誤訊息"
        }
    },
    "required": ["order_type", "error_message"],
    "additionalProperties": False
}

# 完整的訂單回應 Schema（包含所有可能的類型）
ORDER_RESPONSE_SCHEMA = {
    "oneOf": [
        SINGLE_ORDER_SCHEMA,
        MULTI_ORDER_SCHEMA,
        ERROR_SCHEMA
    ]
}