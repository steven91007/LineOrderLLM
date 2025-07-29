import openai
from typing import Dict, Any, Optional
import json
import re


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4-0125-preview"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
    
    def parse_order(self, order_text: str) -> Dict[str, Any]:
        """使用 OpenAI 解析訂單文字"""
        prompt = self._create_order_parsing_prompt(order_text)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            # 解析回應
            result = json.loads(response.choices[0].message.content)
            return {
                'success': True,
                'data': result,
                'raw_response': response.choices[0].message.content
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'data': None
            }
    
    def _get_system_prompt(self) -> str:
        """取得系統提示詞"""
        return """你是一個專業的訂單解析助手。請仔細分析用戶提供的訂單文字，並提取以下資訊：
        1. 寄件人姓名 (sender_name)
        2. 寄件人電話 (sender_phone)
        3. 收件人姓名 (receiver_name)
        4. 收件人電話 (receiver_phone)
        5. 商品品項 (items) - 陣列格式，包含 name 和 quantity
        6. 預計發貨日期 (shipping_date)
        7. 收件地址 (shipping_address)
        
        請以 JSON 格式回應，如果某些資訊無法從文字中提取，請將該欄位設為 null。
        對於電話號碼，請保留原始格式。
        對於日期，請使用 YYYY-MM-DD 格式。
        
        範例輸出格式：
        {
            "sender_name": "王小明",
            "sender_phone": "0912-345-678",
            "receiver_name": "李大華",
            "receiver_phone": "0923-456-789",
            "items": [
                {"name": "產品A", "quantity": 2},
                {"name": "產品B", "quantity": 1}
            ],
            "shipping_date": "2024-01-20",
            "shipping_address": "台北市信義區信義路五段7號"
        }"""
    
    def _create_order_parsing_prompt(self, order_text: str) -> str:
        """建立訂單解析的提示詞"""
        return f"""請解析以下訂單內容：

{order_text}

請提取所有訂單相關資訊並以 JSON 格式回應。"""
    
    def validate_parsed_order(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """驗證解析後的訂單資料"""
        required_fields = [
            'sender_name', 'sender_phone', 
            'receiver_name', 'receiver_phone',
            'items', 'shipping_address'
        ]
        
        missing_fields = []
        for field in required_fields:
            if not parsed_data.get(field):
                missing_fields.append(field)
        
        # 驗證電話號碼格式
        phone_pattern = re.compile(r'^[\d\-\+\(\)\s]+$')
        invalid_phones = []
        
        if parsed_data.get('sender_phone'):
            if not phone_pattern.match(parsed_data['sender_phone']):
                invalid_phones.append('sender_phone')
        
        if parsed_data.get('receiver_phone'):
            if not phone_pattern.match(parsed_data['receiver_phone']):
                invalid_phones.append('receiver_phone')
        
        # 驗證商品項目
        invalid_items = False
        if parsed_data.get('items'):
            if not isinstance(parsed_data['items'], list):
                invalid_items = True
            else:
                for item in parsed_data['items']:
                    if not isinstance(item, dict) or 'name' not in item or 'quantity' not in item:
                        invalid_items = True
                        break
        
        return {
            'is_valid': len(missing_fields) == 0 and len(invalid_phones) == 0 and not invalid_items,
            'missing_fields': missing_fields,
            'invalid_phones': invalid_phones,
            'invalid_items': invalid_items
        }