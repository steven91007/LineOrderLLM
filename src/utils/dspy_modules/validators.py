"""
Order validation module.
"""
import json
from typing import Dict, Any, List
from jsonschema import validate, ValidationError
from ..order_schemas import SINGLE_ORDER_SCHEMA, MULTI_ORDER_SCHEMA, ERROR_SCHEMA


class OrderValidator:
    """Order data validator.

    Note: the Chinese error_message strings are kept as-is because they are
    relayed to customers in LINE replies.
    """
    
    def __init__(self):
        self.schemas = {
            'single': SINGLE_ORDER_SCHEMA,
            'multiple': MULTI_ORDER_SCHEMA,
            'error': ERROR_SCHEMA
        }
    
    def validate_order_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that the order data conforms to the schema
        
        Args:
            data: order data dict
            
        Returns:
            Dict: dict with the validation result
        """
        if not isinstance(data, dict):
            return {
                'is_valid': False,
                'error_type': 'invalid_format',
                'error_message': '資料格式必須是字典類型'
            }
        
        order_type = data.get('order_type')
        if not order_type:
            return {
                'is_valid': False,
                'error_type': 'missing_order_type',
                'error_message': '缺少 order_type 欄位'
            }
        
        if order_type not in self.schemas:
            return {
                'is_valid': False,
                'error_type': 'invalid_order_type',
                'error_message': f'無效的 order_type: {order_type}'
            }
        
        try:
            # Validate against the matching schema
            validate(instance=data, schema=self.schemas[order_type])
            
            # Basic schema validation passed; now check business rules
            business_validation = self._validate_business_rules(data)
            if not business_validation['is_valid']:
                return business_validation
            
            return {
                'is_valid': True,
                'order_type': order_type
            }
            
        except ValidationError as e:
            return {
                'is_valid': False,
                'error_type': 'schema_validation',
                'error_message': f'Schema 驗證失敗: {e.message}',
                'error_path': list(e.path) if e.path else []
            }
    
    def _validate_business_rules(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate business rules
        
        Args:
            data: order data
            
        Returns:
            Dict: validation result
        """
        order_type = data['order_type']
        
        if order_type == 'single':
            return self._validate_single_order_rules(data)
        elif order_type == 'multiple':
            return self._validate_multi_order_rules(data)
        else:
            return {'is_valid': True}  # the error type needs no business validation
    
    def _validate_single_order_rules(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate business rules for a single order"""
        errors = []
        
        # Validate phone number format
        if data.get('receiver_phone'):
            if not self._is_valid_phone(data['receiver_phone']):
                errors.append('收件人電話格式無效')
        
        if data.get('sender_phone'):
            if not self._is_valid_phone(data['sender_phone']):
                errors.append('寄件人電話格式無效')
        
        # Validate the item list
        items = data.get('items', [])
        if not items:
            errors.append('商品清單不能為空')
        else:
            for i, item in enumerate(items):
                if not item.get('name') or not str(item['name']).strip():
                    errors.append(f'商品 {i+1} 缺少名稱')
                if item.get('quantity', 0) <= 0:
                    errors.append(f'商品 {i+1} 數量必須大於 0')
        
        # Validate the address
        if not data.get('shipping_address') or len(str(data['shipping_address']).strip()) < 5:
            errors.append('收件地址太短，至少需要 5 個字符')
        
        if errors:
            return {
                'is_valid': False,
                'error_type': 'business_validation',
                'error_message': '; '.join(errors)
            }
        
        return {'is_valid': True}
    
    def _validate_multi_order_rules(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate business rules for multiple orders"""
        orders = data.get('orders', [])
        total_orders = data.get('total_orders', 0)
        
        # Check the order count is consistent
        if len(orders) != total_orders:
            return {
                'is_valid': False,
                'error_type': 'inconsistent_count',
                'error_message': f'訂單數量不一致：宣告 {total_orders} 份，實際 {len(orders)} 份'
            }
        
        # Validate each order
        invalid_orders = []
        for i, order in enumerate(orders, 1):
            # Add order_type to each order so it can be validated
            order_copy = order.copy()
            order_copy['order_type'] = 'single'
            
            single_validation = self._validate_single_order_rules(order_copy)
            if not single_validation['is_valid']:
                invalid_orders.append({
                    'index': i,
                    'error': single_validation['error_message']
                })
        
        if invalid_orders:
            error_details = [f"訂單 {item['index']}: {item['error']}" for item in invalid_orders]
            return {
                'is_valid': False,
                'error_type': 'invalid_orders',
                'error_message': '; '.join(error_details),
                'invalid_orders': invalid_orders
            }
        
        return {'is_valid': True}
    
    def _is_valid_phone(self, phone: str) -> bool:
        """
        Validate phone number format
        
        Args:
            phone: phone number string
            
        Returns:
            bool: whether the format is valid
        """
        if not phone or not isinstance(phone, str):
            return False
        
        # Strip spaces and special characters for a basic check
        cleaned_phone = ''.join(char for char in phone if char.isdigit() or char in '+-()')
        
        # Basic length check
        digit_count = sum(1 for char in cleaned_phone if char.isdigit())
        
        return 8 <= digit_count <= 15  # length range of international phone numbers


class JSONValidator:
    """JSON format validator"""
    
    @staticmethod
    def is_valid_json(json_string: str) -> bool:
        """Check whether a string is valid JSON"""
        try:
            json.loads(json_string)
            return True
        except (json.JSONDecodeError, TypeError):
            return False
    
    @staticmethod
    def parse_json_safely(json_string: str) -> Dict[str, Any]:
        """Parse JSON safely; on failure return the error format"""
        try:
            return json.loads(json_string)
        except (json.JSONDecodeError, TypeError) as e:
            return {
                "order_type": "error",
                "error_message": f"JSON 格式錯誤: {str(e)}"
            }
    
    @staticmethod
    def fix_common_json_issues(json_string: str) -> str:
        """Fix common JSON formatting problems"""
        if not isinstance(json_string, str):
            return json_string
        
        # Remove any markdown code-block markers
        json_string = json_string.strip()
        if json_string.startswith('```json'):
            json_string = json_string[7:]
        if json_string.startswith('```'):
            json_string = json_string[3:]
        if json_string.endswith('```'):
            json_string = json_string[:-3]
        
        # Strip surrounding whitespace
        json_string = json_string.strip()
        
        # Try to turn single quotes into double quotes
        json_string = json_string.replace("'", '"')
        
        return json_string