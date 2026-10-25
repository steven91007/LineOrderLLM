"""
DSPy order-parsing client.

Note: the Chinese error / error_message strings are kept as-is because they are
relayed to customers in LINE replies (see src/handlers/order_handler.py).
"""
import dspy
import json
from typing import Dict, Any, List
import re
from datetime import datetime

from .langfuse_tracing import init_tracing, observation, update_observation
from .taiwan_address import TaiwanAddressNormalizer

from .dspy_modules.unified_parser import UnifiedOrderParser
from .dspy_modules.validators import OrderValidator, JSONValidator

# Enable Langfuse tracing (DSPy LM calls automatically record model, tokens and cost)
init_tracing()

class DSPyOrderClient:
    """Order-parsing client built on DSPy"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", max_retries: int = 3):
        """
        Initialize the DSPy client
        
        Args:
            api_key: OpenAI API key
            model: name of the model to use
            max_retries: maximum number of retries
        """
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        
        # Configure DSPy
        self._configure_dspy()
        
        # Initialize modules
        self.unified_parser = UnifiedOrderParser()
        self.validator = OrderValidator()
        self.json_validator = JSONValidator()
        self.address_normalizer = TaiwanAddressNormalizer()
    
    def _configure_dspy(self):
        """Configure DSPy settings"""
        # Use OpenAI as the language model
        lm = dspy.LM(
            model=self.model,
            api_key=self.api_key,
            max_tokens=2000,
            temperature=0.1
        )
        dspy.settings.configure(lm=lm)
    
    def parse_order(self, order_text: str) -> Dict[str, Any]:
        """
        Parse order text (unified handling; always returns an array)
        
        Args:
            order_text: raw order text
            
        Returns:
            Dict: parse result with success, data, error, etc.
        """
        if not order_text or not isinstance(order_text, str):
            return {
                'success': False,
                'error': '訂單文字不能為空',
                'data': None
            }

        # Preprocess the text
        cleaned_text = self._preprocess_text(order_text)

        with observation(
            'parse-order',
            input=order_text,
            metadata={'model': self.model, 'max_retries': self.max_retries}
        ) as parse_span:
            # Run the parsing flow
            for attempt in range(self.max_retries):
                try:
                    # Parse with the unified parser, passing the current date as the reference point
                    current_date = datetime.now()
                    result = self.unified_parser(cleaned_text, reference_date=current_date)
                    parsed_orders = json.loads(result.orders_json)

                    # Make sure it is an array
                    if not isinstance(parsed_orders, list):
                        parsed_orders = []

                    # Validate the parse result
                    with observation('validate-orders', input=parsed_orders) as validate_span:
                        validation_result = self._validate_parsed_orders(parsed_orders)
                        update_observation(validate_span, output=validation_result)

                    if validation_result['is_valid']:
                        # Normalize addresses
                        with observation('normalize-addresses') as normalize_span:
                            normalized_orders = self._normalize_addresses_in_orders(parsed_orders)
                            update_observation(
                                normalize_span,
                                input=[o.get('shipping_address') for o in parsed_orders if isinstance(o, dict)],
                                output=[o.get('shipping_address') for o in normalized_orders if isinstance(o, dict)]
                            )

                        update_observation(
                            parse_span,
                            output={'orders': normalized_orders, 'total_orders': len(normalized_orders)},
                            metadata={'attempts_used': attempt + 1, 'success': True}
                        )
                        return {
                            'success': True,
                            'data': {
                                'orders': normalized_orders,
                                'total_orders': len(normalized_orders)
                            },
                            'raw_response': json.dumps(normalized_orders, ensure_ascii=False)
                        }
                    else:
                        # Validation failed; on the last attempt, return the error
                        if attempt == self.max_retries - 1:
                            error = f"驗證失敗: {validation_result.get('error_message', '未知錯誤')}"
                            update_observation(
                                parse_span,
                                output={'error': error},
                                level='ERROR',
                                status_message=error,
                                metadata={'attempts_used': attempt + 1, 'success': False}
                            )
                            return {
                                'success': False,
                                'error': error,
                                'data': None
                            }

                except Exception as e:
                    # On the last attempt, return the error
                    if attempt == self.max_retries - 1:
                        error = f'DSPy 解析失敗: {str(e)}'
                        update_observation(
                            parse_span,
                            output={'error': error},
                            level='ERROR',
                            status_message=error,
                            metadata={'attempts_used': attempt + 1, 'success': False}
                        )
                        return {
                            'success': False,
                            'error': error,
                            'data': None
                        }

            # All attempts failed
            error = '多次嘗試後仍然解析失敗，請檢查訂單格式'
            update_observation(
                parse_span,
                output={'error': error},
                level='ERROR',
                status_message=error,
                metadata={'attempts_used': self.max_retries, 'success': False}
            )
            return {
                'success': False,
                'error': error,
                'data': None
            }
    
    def _validate_parsed_orders(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate the parsed order array"""
        if not isinstance(orders, list):
            return {
                'is_valid': False,
                'error_message': '訂單資料不是陣列格式'
            }
        
        if len(orders) == 0:
            return {
                'is_valid': False,
                'error_message': '沒有找到有效的訂單'
            }
        
        if len(orders) > 5:
            return {
                'is_valid': False,
                'error_message': '訂單數量超過限制（最多5份）'
            }
        
        # Validate each order
        for i, order in enumerate(orders):
            validation = self._validate_single_order_data(order)
            if not validation['is_valid']:
                return {
                    'is_valid': False,
                    'error_message': f"第{i+1}份訂單驗證失敗: {validation.get('error_message', '未知錯誤')}"
                }
        
        return {'is_valid': True}
    
    def _validate_single_order_data(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a single order's data"""
        if not isinstance(order, dict):
            return {
                'is_valid': False,
                'error_message': '訂單資料不是字典格式'
            }
        
        # Required-field check
        required_fields = ['receiver_name', 'receiver_phone', 'shipping_address', 'items']
        missing_fields = []
        
        for field in required_fields:
            if not order.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            return {
                'is_valid': False,
                'error_message': f'缺少必填欄位: {", ".join(missing_fields)}'
            }
        
        # Validate phone number format
        phone_pattern = re.compile(r'^[\d\-\+\(\)\s]+$')
        if order.get('receiver_phone') and not phone_pattern.match(order['receiver_phone']):
            return {
                'is_valid': False,
                'error_message': '收件人電話格式不正確'
            }
        
        if order.get('sender_phone') and not phone_pattern.match(order['sender_phone']):
            return {
                'is_valid': False,
                'error_message': '寄件人電話格式不正確'
            }
        
        # Validate items
        items = order.get('items', [])
        if not isinstance(items, list) or len(items) == 0:
            return {
                'is_valid': False,
                'error_message': '商品項目不能為空'
            }
        
        for item in items:
            if not isinstance(item, dict) or 'name' not in item or 'quantity' not in item:
                return {
                    'is_valid': False,
                    'error_message': '商品項目格式不正確'
                }
            
            if not isinstance(item['quantity'], (int, float)) or item['quantity'] <= 0:
                return {
                    'is_valid': False,
                    'error_message': '商品數量必須是正數'
                }
        
        return {'is_valid': True}
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocess the order text"""
        # Collapse extra whitespace and newlines
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Normalize common order keywords
        replacements = {
            '寄件者': '寄件人',
            '收件者': '收件人', 
            '發貨日': '發貨日期',
            '出貨日': '發貨日期',
            '地址：': '地址:',
            '電話：': '電話:',
            '姓名：': '姓名:',
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text
    
    
    def validate_parsed_order(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate parsed order data (compatibility interface)
        
        Args:
            parsed_data: parsed order data (new format: {'orders': [...], 'total_orders': N})
            
        Returns:
            Dict: validation result
        """
        if not isinstance(parsed_data, dict):
            return {
                'is_valid': False,
                'error_type': 'invalid_format',
                'error_message': '訂單資料格式不正確'
            }
        
        orders = parsed_data.get('orders', [])
        total_orders = parsed_data.get('total_orders', 0)
        
        if not isinstance(orders, list):
            return {
                'is_valid': False,
                'error_type': 'invalid_format',
                'error_message': '訂單資料不是陣列格式'
            }
        
        if len(orders) != total_orders:
            return {
                'is_valid': False,
                'error_type': 'structure_error',
                'error_message': '訂單數量不一致'
            }
        
        # Use the new validation method
        validation_result = self._validate_parsed_orders(orders)
        
        if validation_result['is_valid']:
            return {
                'is_valid': True,
                'order_type': 'unified',
                'total_orders': len(orders)
            }
        else:
            return {
                'is_valid': False,
                'error_type': 'validation_error',
                'error_message': validation_result.get('error_message', '驗證失敗')
            }
    
    def _normalize_addresses_in_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize the addresses in the order array"""
        normalized_orders = []
        
        for order in orders:
            if isinstance(order, dict) and 'shipping_address' in order and order['shipping_address']:
                # Copy the order to avoid mutating the original
                normalized_order = order.copy()
                normalized_order['shipping_address'] = self.address_normalizer.normalize_address(order['shipping_address'])
                normalized_orders.append(normalized_order)
            else:
                normalized_orders.append(order)
        
        return normalized_orders
    
