import openai
from typing import Dict, Any, Optional, List
import json
import re


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4-0125-preview"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
    
    def parse_order(self, order_text: str) -> Dict[str, Any]:
        """使用 OpenAI 解析訂單文字（支援多訂單）"""
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
            
            # 解析回應
            result = json.loads(response.choices[0].message.content)
            
            # 驗證多訂單格式
            if not self._validate_multi_order_format(result):
                return {
                    'success': False,
                    'error': '多訂單解析失敗，請嘗試單筆輸入或檢查訂單格式',
                    'data': None,
                    'suggestion': 'single_order'
                }
            
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
        """取得多訂單系統提示詞"""
        return """你是一個專業的訂單解析助手。請仔細分析用戶提供的文字，判斷是否包含多份訂單。

**重要規則：**
1. 寄件人資訊 (sender_name, sender_phone) 為選填，可以為 null
2. 收件人資訊 (receiver_name, receiver_phone) 為必填
3. 商品品項 (items) 和 收件地址 (shipping_address) 為必填
4. 單次最多解析 5 份訂單
5. 如果超過 5 份訂單，返回錯誤

**輸出格式：**
- 單一訂單：返回 single_order 格式
- 多份訂單：返回 multi_order 格式

**單一訂單格式：**
{
  "order_type": "single",
  "sender_name": "王小明", // 可為 null
  "sender_phone": "0912-345-678", // 可為 null
  "receiver_name": "李大華",
  "receiver_phone": "0923-456-789",
  "items": [{"name": "產品A", "quantity": 2}],
  "shipping_date": "2024-01-20", // 可為 null
  "shipping_address": "台北市..."
}

**多份訂單格式：**
{
  "order_type": "multiple",
  "total_orders": 2,
  "orders": [
    {
      "order_index": 1,
      "sender_name": null, // 選填
      "sender_phone": null, // 選填
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

**錯誤處理：**
如果訂單數量超過 5 份或無法解析，返回：
{
  "order_type": "error",
  "error_message": "訂單數量超過限制（最多5份）或解析失敗"
}"""
    
    def _create_order_parsing_prompt(self, order_text: str) -> str:
        """建立訂單解析的提示詞"""
        return f"""請解析以下訂單內容：

{order_text}

請判斷這是單一訂單還是多份訂單，並按照系統提示的格式回應。記住：
- 寄件人資訊為選填
- 收件人資訊、商品、地址為必填
- 最多處理 5 份訂單"""
    
    def validate_parsed_order(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證解析後的訂單資料（支援多訂單）"""
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
        """驗證單一訂單"""
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
        invalid_phones = self._validate_phone_numbers(parsed_data)
        
        # 驗證商品項目
        invalid_items = self._validate_items(parsed_data.get('items', []))
        
        return {
            'is_valid': len(missing_fields) == 0 and len(invalid_phones) == 0 and not invalid_items,
            'missing_fields': missing_fields,
            'invalid_phones': invalid_phones,
            'invalid_items': invalid_items,
            'order_type': 'single'
        }
    
    def _validate_multiple_orders(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證多份訂單"""
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
        """驗證電話號碼格式"""
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
    
    def _validate_items(self, items: List[Dict[str, Any]]) -> bool:
        """驗證商品項目"""
        if not isinstance(items, list) or len(items) == 0:
            return True  # 空列表視為無效
        
        for item in items:
            if not isinstance(item, dict) or 'name' not in item or 'quantity' not in item:
                return True
        
        return False
    
    def _validate_multi_order_format(self, result: Dict[str, Any]) -> bool:
        """驗證多訂單格式"""
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