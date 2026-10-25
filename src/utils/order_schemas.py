"""
JSON Schema definitions for order data
"""

# Single-order schema
SINGLE_ORDER_SCHEMA = {
    "type": "object",
    "properties": {
        "order_type": {
            "type": "string",
            "enum": ["single"]
        },
        "sender_name": {
            "type": ["string", "null"],
            "description": "Sender name (optional)"
        },
        "sender_phone": {
            "type": ["string", "null"],
            "description": "Sender phone (optional)"
        },
        "receiver_name": {
            "type": "string",
            "description": "Receiver name (required)"
        },
        "receiver_phone": {
            "type": "string",
            "description": "Receiver phone (required)"
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
            "description": "Item list (required)"
        },
        "shipping_date": {
            "type": ["string", "null"],
            "pattern": "^\\d{2}-\\d{2}$|^$",
            "description": "Expected shipping date (optional, format: MM-DD, without the year)"
        },
        "shipping_address": {
            "type": "string",
            "minLength": 5,
            "description": "Receiver address (required)"
        }
    },
    "required": ["order_type", "receiver_name", "receiver_phone", "items", "shipping_address"],
    "additionalProperties": False
}

# Multi-order schema
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
            "description": "Total number of orders (2-5)"
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
                        "description": "Sender name (optional)"
                    },
                    "sender_phone": {
                        "type": ["string", "null"],
                        "description": "Sender phone (optional)"
                    },
                    "receiver_name": {
                        "type": "string",
                        "description": "Receiver name (required)"
                    },
                    "receiver_phone": {
                        "type": "string",
                        "description": "Receiver phone (required)"
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
                        "description": "Item list (required)"
                    },
                    "shipping_date": {
                        "type": ["string", "null"],
                        "pattern": "^\\d{2}-\\d{2}$|^$",
                        "description": "Expected shipping date (optional, format: MM-DD, without the year)"
                    },
                    "shipping_address": {
                        "type": "string",
                        "minLength": 5,
                        "description": "Receiver address (required)"
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

# Error-response schema
ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "order_type": {
            "type": "string",
            "enum": ["error"]
        },
        "error_message": {
            "type": "string",
            "description": "Error message"
        }
    },
    "required": ["order_type", "error_message"],
    "additionalProperties": False
}

# Full order-response schema (covers every possible type)
ORDER_RESPONSE_SCHEMA = {
    "oneOf": [
        SINGLE_ORDER_SCHEMA,
        MULTI_ORDER_SCHEMA,
        ERROR_SCHEMA
    ]
}