from typing import Dict, Any, Optional, List
import json
import re

from .langfuse_tracing import init_tracing, observation, update_observation
from .taiwan_address import TaiwanAddressNormalizer

# Enable Langfuse tracing; the import must happen before the OpenAI client is created so LLM calls are recorded automatically
init_tracing()
try:
    # drop-in replacement: automatically records prompt/completion, model, tokens and cost
    from langfuse.openai import openai
except ImportError:  # still works when langfuse is not installed
    import openai


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4-0125-preview"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.address_normalizer = TaiwanAddressNormalizer()
    
    def parse_order(self, order_text: str) -> Dict[str, Any]:
        """Parse order text with OpenAI (supports multiple orders)"""
        prompt = self._create_order_parsing_prompt(order_text)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_multi_order_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            # Parse the response
            result = json.loads(response.choices[0].message.content)
            
            # Validate the multi-order format
            if not self._validate_multi_order_format(result):
                return {
                    'success': False,
                    'error': '多訂單解析失敗，請嘗試單筆輸入或檢查訂單格式',
                    'data': None,
                    'suggestion': 'single_order'
                }
            
            result = self._normalize_addresses_in_result(result)
            return {
                'success': True,
                'data': result,
                'raw_response': response.choices[0].message.content
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'data': None,
                'suggestion': 'single_order'
            }
    
    def _get_multi_order_system_prompt(self) -> str:
        """Return the multi-order system prompt"""
        return """You are a professional order-parsing assistant. Carefully analyze the text the user provides and determine whether it contains multiple orders.

**Important rules:**
1. Sender information (sender_name, sender_phone) is optional and may be null
2. Receiver information (receiver_name, receiver_phone) is required
3. Items (items) and the receiver address (shipping_address) are required
4. Parse at most 5 orders at a time
5. If there are more than 5 orders, return an error

**Output format:**
- Single order: return the single_order format
- Multiple orders: return the multi_order format

**Single-order format:**
{
  "order_type": "single",
  "sender_name": "王小明", // may be null
  "sender_phone": "0912-345-678", // may be null
  "receiver_name": "李大華",
  "receiver_phone": "0923-456-789",
  "items": [{"name": "產品A", "quantity": 2}],
  "shipping_date": "2024-01-20", // may be null
  "shipping_address": "台北市..."
}

**Multi-order format:**
{
  "order_type": "multiple",
  "total_orders": 2,
  "orders": [
    {
      "order_index": 1,
      "sender_name": null, // optional
      "sender_phone": null, // optional
      "receiver_name": "李大華",
      "receiver_phone": "0923-456-789",
      "items": [{"name": "產品A", "quantity": 2}],
      "shipping_date": "2024-01-20",
      "shipping_address": "台北市..."
    },
    {
      "order_index": 2,
      "sender_name": null,
      "sender_phone": null,
      "receiver_name": "陳小美",
      "receiver_phone": "0934-567-890",
      "items": [{"name": "產品B", "quantity": 1}],
      "shipping_date": null,
      "shipping_address": "新北市..."
    }
  ]
}

**Error handling:**
If there are more than 5 orders or the text cannot be parsed, return (keep error_message in Traditional Chinese, as below):
{
  "order_type": "error",
  "error_message": "訂單數量超過限制（最多5份）或解析失敗"
}"""
    
    def _create_order_parsing_prompt(self, order_text: str) -> str:
        """Build the order-parsing prompt"""
        return f"""Parse the following order content:

{order_text}

Determine whether this is a single order or multiple orders, and respond in the format given in the system prompt. Remember:
- Sender information is optional
- Receiver information, items and address are required
- Handle at most 5 orders"""
    
    def validate_parsed_order(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parsed order data (supports multiple orders)"""
        order_type = parsed_data.get('order_type', 'single')
        
        if order_type == 'error':
            return {
                'is_valid': False,
                'error_type': 'parsing_error',
                'error_message': parsed_data.get('error_message', '解析失敗')
            }
        
        if order_type == 'single':
            return self._validate_single_order(parsed_data)
        elif order_type == 'multiple':
            return self._validate_multiple_orders(parsed_data)
        else:
            return {
                'is_valid': False,
                'error_type': 'invalid_format',
                'error_message': '未知的訂單類型'
            }
    
    def _validate_single_order(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a single order"""
        # Required fields (sender information is now optional)
        required_fields = [
            'receiver_name', 'receiver_phone',
            'items', 'shipping_address'
        ]
        
        missing_fields = []
        for field in required_fields:
            if not parsed_data.get(field):
                missing_fields.append(field)
        
        # Validate phone number format
        invalid_phones = self._validate_phone_numbers(parsed_data)
        
        # Validate items
        invalid_items = self._validate_items(parsed_data.get('items', []))
        
        return {
            'is_valid': len(missing_fields) == 0 and len(invalid_phones) == 0 and not invalid_items,
            'missing_fields': missing_fields,
            'invalid_phones': invalid_phones,
            'invalid_items': invalid_items,
            'order_type': 'single'
        }
    
    def _validate_multiple_orders(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate multiple orders"""
        orders = parsed_data.get('orders', [])
        total_orders = parsed_data.get('total_orders', 0)
        
        if not orders or len(orders) != total_orders:
            return {
                'is_valid': False,
                'error_type': 'structure_error',
                'error_message': '訂單數量不一致'
            }
        
        if total_orders > 5:
            return {
                'is_valid': False,
                'error_type': 'limit_exceeded',
                'error_message': '訂單數量超過限制（最多5份）'
            }
        
        # Validate each order
        invalid_orders = []
        for i, order in enumerate(orders):
            validation = self._validate_single_order(order)
            if not validation['is_valid']:
                invalid_orders.append({
                    'index': i + 1,
                    'errors': validation
                })
        
        return {
            'is_valid': len(invalid_orders) == 0,
            'invalid_orders': invalid_orders,
            'total_orders': total_orders,
            'order_type': 'multiple'
        }
    
    def _validate_phone_numbers(self, data: Dict[str, Any]) -> List[str]:
        """Validate phone number format"""
        phone_pattern = re.compile(r'^[\d\-\+\(\)\s]+$')
        invalid_phones = []
        
        # Sender phone (optional)
        if data.get('sender_phone'):
            if not phone_pattern.match(data['sender_phone']):
                invalid_phones.append('sender_phone')
        
        # Receiver phone (required)
        if data.get('receiver_phone'):
            if not phone_pattern.match(data['receiver_phone']):
                invalid_phones.append('receiver_phone')
        
        return invalid_phones
    
    def _validate_items(self, items: List[Dict[str, Any]]) -> bool:
        """Validate items"""
        if not isinstance(items, list) or len(items) == 0:
            return True  # an empty list counts as invalid
        
        for item in items:
            if not isinstance(item, dict) or 'name' not in item or 'quantity' not in item:
                return True
        
        return False
    
    def _normalize_addresses_in_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize the addresses in the parse result"""
        order_type = result.get('order_type', 'single')
        
        if order_type == 'single':
            # Handle the single order's address
            if 'shipping_address' in result and result['shipping_address']:
                result['shipping_address'] = self.address_normalizer.normalize_address(result['shipping_address'])
                
        elif order_type == 'multiple':
            # Handle the addresses of multiple orders
            orders = result.get('orders', [])
            for order in orders:
                if 'shipping_address' in order and order['shipping_address']:
                    order['shipping_address'] = self.address_normalizer.normalize_address(order['shipping_address'])
        
        return result
    
    def _validate_multi_order_format(self, result: Dict[str, Any]) -> bool:
        """Validate the multi-order format"""
        order_type = result.get('order_type')
        
        if order_type == 'error':
            return False
        elif order_type == 'single':
            return 'receiver_name' in result and 'items' in result
        elif order_type == 'multiple':
            orders = result.get('orders', [])
            total_orders = result.get('total_orders', 0)
            
            if len(orders) != total_orders or total_orders > 5:
                return False
            
            for order in orders:
                if not ('receiver_name' in order and 'items' in order):
                    return False
            
            return True
        
        return False
    
    def _normalize_addresses_in_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize the addresses in the parse result"""
        order_type = result.get('order_type', 'single')
        
        if order_type == 'single':
            # Handle the single order's address
            if 'shipping_address' in result and result['shipping_address']:
                result['shipping_address'] = self.address_normalizer.normalize_address(result['shipping_address'])
                
        elif order_type == 'multiple':
            # Handle the addresses of multiple orders
            orders = result.get('orders', [])
            for order in orders:
                if 'shipping_address' in order and order['shipping_address']:
                    order['shipping_address'] = self.address_normalizer.normalize_address(order['shipping_address'])
        
        return result