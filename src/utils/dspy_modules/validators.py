"""
訂單驗證模組
"""
import json
from typing import Dict, Any, List
from jsonschema import validate, ValidationError
from ..order_schemas import SINGLE_ORDER_SCHEMA, MULTI_ORDER_SCHEMA, ERROR_SCHEMA


class OrderValidator:
    """訂單資料驗證器"""
    
    def __init__(self):
        self.schemas = {
            'single': SINGLE_ORDER_SCHEMA,
            'multiple': MULTI_ORDER_SCHEMA,
            'error': ERROR_SCHEMA
        }
    
    def validate_order_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        驗證訂單資料是否符合 Schema
        
        Args:
            data: 訂單資料字典
            
        Returns:
            Dict: 包含驗證結果的字典
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
            # 使用對應的 Schema 進行驗證
            validate(instance=data, schema=self.schemas[order_type])
            
            # 通過基本 Schema 驗證，進行業務邏輯驗證
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
        驗證業務邏輯規則
        
        Args:
            data: 訂單資料
            
        Returns:
            Dict: 驗證結果
        """
        order_type = data['order_type']
        
        if order_type == 'single':
            return self._validate_single_order_rules(data)
        elif order_type == 'multiple':
            return self._validate_multi_order_rules(data)
        else:
            return {'is_valid': True}  # error 類型不需要業務驗證
    
    def _validate_single_order_rules(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證單一訂單的業務規則"""
        errors = []
        
        # 驗證電話號碼格式
        if data.get('receiver_phone'):
            if not self._is_valid_phone(data['receiver_phone']):
                errors.append('收件人電話格式無效')
        
        if data.get('sender_phone'):
            if not self._is_valid_phone(data['sender_phone']):
                errors.append('寄件人電話格式無效')
        
        # 驗證商品清單
        items = data.get('items', [])
        if not items:
            errors.append('商品清單不能為空')
        else:
            for i, item in enumerate(items):
                if not item.get('name') or not str(item['name']).strip():
                    errors.append(f'商品 {i+1} 缺少名稱')
                if item.get('quantity', 0) <= 0:
                    errors.append(f'商品 {i+1} 數量必須大於 0')
        
        # 驗證地址
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
        """驗證多訂單的業務規則"""
        orders = data.get('orders', [])
        total_orders = data.get('total_orders', 0)
        
        # 驗證訂單數量一致性
        if len(orders) != total_orders:
            return {
                'is_valid': False,
                'error_type': 'inconsistent_count',
                'error_message': f'訂單數量不一致：宣告 {total_orders} 份，實際 {len(orders)} 份'
            }
        
        # 驗證每份訂單
        invalid_orders = []
        for i, order in enumerate(orders, 1):
            # 為每份訂單添加 order_type 以便驗證
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
        驗證電話號碼格式
        
        Args:
            phone: 電話號碼字串
            
        Returns:
            bool: 是否為有效格式
        """
        if not phone or not isinstance(phone, str):
            return False
        
        # 移除空格和特殊字符進行基本驗證
        cleaned_phone = ''.join(char for char in phone if char.isdigit() or char in '+-()')
        
        # 基本長度檢查
        digit_count = sum(1 for char in cleaned_phone if char.isdigit())
        
        return 8 <= digit_count <= 15  # 國際電話號碼長度範圍


class JSONValidator:
    """JSON 格式驗證器"""
    
    @staticmethod
    def is_valid_json(json_string: str) -> bool:
        """檢查字串是否為有效的 JSON"""
        try:
            json.loads(json_string)
            return True
        except (json.JSONDecodeError, TypeError):
            return False
    
    @staticmethod
    def parse_json_safely(json_string: str) -> Dict[str, Any]:
        """安全地解析 JSON，失敗時返回錯誤格式"""
        try:
            return json.loads(json_string)
        except (json.JSONDecodeError, TypeError) as e:
            return {
                "order_type": "error",
                "error_message": f"JSON 格式錯誤: {str(e)}"
            }
    
    @staticmethod
    def fix_common_json_issues(json_string: str) -> str:
        """修正常見的 JSON 格式問題"""
        if not isinstance(json_string, str):
            return json_string
        
        # 移除可能的 markdown 代碼塊標記
        json_string = json_string.strip()
        if json_string.startswith('```json'):
            json_string = json_string[7:]
        if json_string.startswith('```'):
            json_string = json_string[3:]
        if json_string.endswith('```'):
            json_string = json_string[:-3]
        
        # 移除前後空白
        json_string = json_string.strip()
        
        # 嘗試修正單引號為雙引號
        json_string = json_string.replace("'", '"')
        
        return json_string