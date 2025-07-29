"""
DSPy 訂單解析客戶端
"""
import dspy
import json
from typing import Dict, Any, List
import re

from .dspy_modules.order_classifier import OrderTypeClassifier
from .dspy_modules.single_parser import SingleOrderParser
from .dspy_modules.multi_parser import MultiOrderParser
from .dspy_modules.validators import OrderValidator, JSONValidator


class DSPyOrderClient:
    """使用 DSPy 的訂單解析客戶端"""
    
    def __init__(self, api_key: str, model: str = "gpt-4-0125-preview", max_retries: int = 3):
        """
        初始化 DSPy 客戶端
        
        Args:
            api_key: OpenAI API 金鑰
            model: 使用的模型名稱
            max_retries: 最大重試次數
        """
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        
        # 配置 DSPy
        self._configure_dspy()
        
        # 初始化模組
        self.classifier = OrderTypeClassifier()
        self.single_parser = SingleOrderParser()
        self.multi_parser = MultiOrderParser()
        self.validator = OrderValidator()
        self.json_validator = JSONValidator()
    
    def _configure_dspy(self):
        """配置 DSPy 設定"""
        # 設定 OpenAI 作為語言模型
        lm = dspy.OpenAI(
            model=self.model,
            api_key=self.api_key,
            max_tokens=2000,
            temperature=0.1
        )
        dspy.settings.configure(lm=lm)
    
    def parse_order(self, order_text: str) -> Dict[str, Any]:
        """
        解析訂單文字（支援單一和多訂單）
        
        Args:
            order_text: 原始訂單文字
            
        Returns:
            Dict: 解析結果，包含 success, data, error 等欄位
        """
        if not order_text or not isinstance(order_text, str):
            return {
                'success': False,
                'error': '訂單文字不能為空',
                'data': None,
                'suggestion': 'single_order'
            }
        
        # 預處理文字
        cleaned_text = self._preprocess_text(order_text)
        
        # 執行解析流程
        for attempt in range(self.max_retries):
            try:
                # 步驟 1: 識別訂單類型
                order_type = self._classify_order_type(cleaned_text)
                
                # 步驟 2: 根據類型進行解析
                if order_type == 'single':
                    parsed_data = self._parse_single_order(cleaned_text)
                elif order_type == 'multiple':
                    parsed_data = self._parse_multiple_orders(cleaned_text)
                else:
                    # 預設為單一訂單
                    parsed_data = self._parse_single_order(cleaned_text)
                
                # 步驟 3: 驗證解析結果
                validation_result = self._validate_parsed_data(parsed_data)
                
                if validation_result['is_valid']:
                    return {
                        'success': True,
                        'data': parsed_data,
                        'raw_response': json.dumps(parsed_data, ensure_ascii=False)
                    }
                else:
                    # 驗證失敗，但如果是最後一次嘗試，回傳錯誤
                    if attempt == self.max_retries - 1:
                        return {
                            'success': False,
                            'error': f"驗證失敗: {validation_result.get('error_message', '未知錯誤')}",
                            'data': None,
                            'suggestion': 'single_order'
                        }
                
            except Exception as e:
                # 如果是最後一次嘗試，回傳錯誤
                if attempt == self.max_retries - 1:
                    return {
                        'success': False,
                        'error': f'DSPy 解析失敗: {str(e)}',
                        'data': None,
                        'suggestion': 'single_order'
                    }
        
        # 所有嘗試都失敗
        return {
            'success': False,
            'error': '多次嘗試後仍然解析失敗，請嘗試單筆輸入',
            'data': None,
            'suggestion': 'single_order'
        }
    
    def _classify_order_type(self, order_text: str) -> str:
        """分類訂單類型"""
        try:
            result = self.classifier(order_text)
            return result.order_type
        except Exception:
            # 分類失敗時的後備邏輯
            return 'single' if not self._contains_multiple_indicators(order_text) else 'multiple'
    
    def _parse_single_order(self, order_text: str) -> Dict[str, Any]:
        """解析單一訂單"""
        result = self.single_parser(order_text)
        return result.order_json
    
    def _parse_multiple_orders(self, order_text: str) -> Dict[str, Any]:
        """解析多訂單"""
        result = self.multi_parser(order_text)
        return result.orders_json
    
    def _validate_parsed_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證解析後的資料"""
        return self.validator.validate_order_data(data)
    
    def _preprocess_text(self, text: str) -> str:
        """預處理訂單文字"""
        # 移除多餘的空白和換行
        text = re.sub(r'\s+', ' ', text.strip())
        
        # 標準化常見的訂單關鍵字
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
    
    def _contains_multiple_indicators(self, text: str) -> bool:
        """檢查文字是否包含多訂單指標"""
        indicators = [
            r'訂單\s*[1-5]', r'order\s*[1-5]',
            r'第[一二三四五]\s*筆', r'第[1-5]\s*筆',
            r'\d+\.', r'\d+\)',
            r'[1-5]\s*[.、，]'
        ]
        
        text_lower = text.lower()
        matches = 0
        
        for pattern in indicators:
            if re.search(pattern, text_lower):
                matches += 1
        
        return matches >= 2
    
    def validate_parsed_order(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        驗證解析後的訂單資料（與 OpenAI 客戶端相容的介面）
        
        Args:
            parsed_data: 解析後的訂單資料
            
        Returns:
            Dict: 驗證結果
        """
        order_type = parsed_data.get('order_type', 'single')
        
        if order_type == 'error':
            return {
                'is_valid': False,
                'error_type': 'parsing_error',
                'error_message': parsed_data.get('error_message', '解析失敗')
            }
        
        if order_type == 'single':
            return self._validate_single_order_legacy(parsed_data)
        elif order_type == 'multiple':
            return self._validate_multiple_orders_legacy(parsed_data)
        else:
            return {
                'is_valid': False,
                'error_type': 'invalid_format',
                'error_message': '未知的訂單類型'
            }
    
    def _validate_single_order_legacy(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證單一訂單（與舊版相容）"""
        # 必填欄位（寄件人資訊改為選填）
        required_fields = [
            'receiver_name', 'receiver_phone',
            'items', 'shipping_address'
        ]
        
        missing_fields = []
        for field in required_fields:
            if not parsed_data.get(field):
                missing_fields.append(field)
        
        # 驗證電話號碼格式
        invalid_phones = self._validate_phone_numbers_legacy(parsed_data)
        
        # 驗證商品項目
        invalid_items = self._validate_items_legacy(parsed_data.get('items', []))
        
        return {
            'is_valid': len(missing_fields) == 0 and len(invalid_phones) == 0 and not invalid_items,
            'missing_fields': missing_fields,
            'invalid_phones': invalid_phones,
            'invalid_items': invalid_items,
            'order_type': 'single'
        }
    
    def _validate_multiple_orders_legacy(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證多份訂單（與舊版相容）"""
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
        
        # 驗證每份訂單
        invalid_orders = []
        for i, order in enumerate(orders):
            validation = self._validate_single_order_legacy(order)
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
    
    def _validate_phone_numbers_legacy(self, data: Dict[str, Any]) -> List[str]:
        """驗證電話號碼格式（舊版相容）"""
        phone_pattern = re.compile(r'^[\d\-\+\(\)\s]+$')
        invalid_phones = []
        
        # 寄件人電話（選填）
        if data.get('sender_phone'):
            if not phone_pattern.match(data['sender_phone']):
                invalid_phones.append('sender_phone')
        
        # 收件人電話（必填）
        if data.get('receiver_phone'):
            if not phone_pattern.match(data['receiver_phone']):
                invalid_phones.append('receiver_phone')
        
        return invalid_phones
    
    def _validate_items_legacy(self, items: List[Dict[str, Any]]) -> bool:
        """驗證商品項目（舊版相容）"""
        if not isinstance(items, list) or len(items) == 0:
            return True  # 空列表視為無效
        
        for item in items:
            if not isinstance(item, dict) or 'name' not in item or 'quantity' not in item:
                return True
        
        return False