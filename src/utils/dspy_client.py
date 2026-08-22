"""
DSPy 訂單解析客戶端
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

# 啟用 Langfuse 追蹤（DSPy 的 LM 呼叫會自動記錄模型、token 與成本）
init_tracing()

class DSPyOrderClient:
    """使用 DSPy 的訂單解析客戶端"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", max_retries: int = 3):
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
        self.unified_parser = UnifiedOrderParser()
        self.validator = OrderValidator()
        self.json_validator = JSONValidator()
        self.address_normalizer = TaiwanAddressNormalizer()
    
    def _configure_dspy(self):
        """配置 DSPy 設定"""
        # 設定 OpenAI 作為語言模型
        lm = dspy.LM(
            model=self.model,
            api_key=self.api_key,
            max_tokens=2000,
            temperature=0.1
        )
        dspy.settings.configure(lm=lm)
    
    def parse_order(self, order_text: str) -> Dict[str, Any]:
        """
        解析訂單文字（統一處理，都返回陣列格式）
        
        Args:
            order_text: 原始訂單文字
            
        Returns:
            Dict: 解析結果，包含 success, data, error 等欄位
        """
        if not order_text or not isinstance(order_text, str):
            return {
                'success': False,
                'error': '訂單文字不能為空',
                'data': None
            }

        # 預處理文字
        cleaned_text = self._preprocess_text(order_text)

        with observation(
            'parse-order',
            input=order_text,
            metadata={'model': self.model, 'max_retries': self.max_retries}
        ) as parse_span:
            # 執行解析流程
            for attempt in range(self.max_retries):
                try:
                    # 使用統一解析器解析，傳入當前日期作為參考點
                    current_date = datetime.now()
                    result = self.unified_parser(cleaned_text, reference_date=current_date)
                    parsed_orders = json.loads(result.orders_json)

                    # 確保是陣列格式
                    if not isinstance(parsed_orders, list):
                        parsed_orders = []

                    # 驗證解析結果
                    with observation('validate-orders', input=parsed_orders) as validate_span:
                        validation_result = self._validate_parsed_orders(parsed_orders)
                        update_observation(validate_span, output=validation_result)

                    if validation_result['is_valid']:
                        # 標準化地址
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
                        # 驗證失敗，但如果是最後一次嘗試，回傳錯誤
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
                    # 如果是最後一次嘗試，回傳錯誤
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

            # 所有嘗試都失敗
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
        """驗證解析後的訂單陣列"""
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
        
        # 驗證每個訂單
        for i, order in enumerate(orders):
            validation = self._validate_single_order_data(order)
            if not validation['is_valid']:
                return {
                    'is_valid': False,
                    'error_message': f"第{i+1}份訂單驗證失敗: {validation.get('error_message', '未知錯誤')}"
                }
        
        return {'is_valid': True}
    
    def _validate_single_order_data(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """驗證單一訂單資料"""
        if not isinstance(order, dict):
            return {
                'is_valid': False,
                'error_message': '訂單資料不是字典格式'
            }
        
        # 必填欄位檢查
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
        
        # 驗證電話號碼格式
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
        
        # 驗證商品項目
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
    
    
    def validate_parsed_order(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        驗證解析後的訂單資料（相容性介面）
        
        Args:
            parsed_data: 解析後的訂單資料（新格式：{'orders': [...], 'total_orders': N}）
            
        Returns:
            Dict: 驗證結果
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
        
        # 使用新的驗證方法
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
        """標準化訂單陣列中的地址"""
        normalized_orders = []
        
        for order in orders:
            if isinstance(order, dict) and 'shipping_address' in order and order['shipping_address']:
                # 複製訂單以避免修改原始資料
                normalized_order = order.copy()
                normalized_order['shipping_address'] = self.address_normalizer.normalize_address(order['shipping_address'])
                normalized_orders.append(normalized_order)
            else:
                normalized_orders.append(order)
        
        return normalized_orders
    
