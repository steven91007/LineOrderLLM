"""
單一訂單解析模組
"""
import dspy
import json
from typing import Dict, Any
from .signatures import SingleOrderSignature
from ..order_schemas import SINGLE_ORDER_SCHEMA


class SingleOrderParser(dspy.Module):
    """解析單一訂單"""
    
    def __init__(self):
        super().__init__()
        self.parse = dspy.ChainOfThought(SingleOrderSignature)
    
    def forward(self, order_text: str) -> dspy.Prediction:
        """
        解析單一訂單文字為結構化 JSON
        
        Args:
            order_text: 訂單文字
            
        Returns:
            dspy.Prediction: 包含 order_json (dict)
        """
        # 建立詳細的解析提示
        enhanced_prompt = self._create_parsing_prompt(order_text)
        
        # 使用 DSPy 進行解析
        result = self.parse(order_text=enhanced_prompt)
        
        # 解析和驗證 JSON
        try:
            if isinstance(result.order_json, str):
                order_data = json.loads(result.order_json)
            else:
                order_data = result.order_json
            
            # 確保包含 order_type
            if 'order_type' not in order_data:
                order_data['order_type'] = 'single'
            
            # 基本驗證和清理
            cleaned_data = self._clean_order_data(order_data)
            
            return dspy.Prediction(order_json=cleaned_data)
            
        except (json.JSONDecodeError, TypeError) as e:
            # JSON 解析失敗，返回錯誤格式
            error_data = {
                "order_type": "error",
                "error_message": f"JSON 解析失敗: {str(e)}"
            }
            return dspy.Prediction(order_json=error_data)
    
    def _create_parsing_prompt(self, order_text: str) -> str:
        """建立增強的解析提示"""
        return f"""請解析以下單一訂單內容並輸出 JSON 格式：

{order_text}

解析規則：
1. 寄件人資訊（sender_name, sender_phone）為選填，可設為 null
2. 收件人資訊（receiver_name, receiver_phone）為必填
3. 商品清單（items）必須為陣列格式，包含 name 和 quantity
4. 收件地址（shipping_address）為必填
5. 發貨日期（shipping_date）為選填，格式 YYYY-MM-DD 或 null

輸出必須是有效的 JSON 格式，包含 order_type: "single"。"""
    
    def _clean_order_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """清理和標準化訂單資料"""
        cleaned = {
            "order_type": "single",
            "sender_name": self._clean_string(data.get('sender_name')),
            "sender_phone": self._clean_phone(data.get('sender_phone')),
            "receiver_name": self._clean_string(data.get('receiver_name')),
            "receiver_phone": self._clean_phone(data.get('receiver_phone')),
            "items": self._clean_items(data.get('items', [])),
            "shipping_date": self._clean_date(data.get('shipping_date')),
            "shipping_address": self._clean_string(data.get('shipping_address'))
        }
        return cleaned
    
    def _clean_string(self, value: Any) -> str:
        """清理字串值"""
        if value is None or str(value).strip() == '':
            return None
        return str(value).strip()
    
    def _clean_phone(self, value: Any) -> str:
        """清理電話號碼"""
        if value is None or str(value).strip() == '':
            return None
        phone = str(value).strip()
        # 基本電話號碼格式驗證
        if len(phone) < 8:
            return None
        return phone
    
    def _clean_items(self, items: Any) -> list:
        """清理商品清單"""
        if not isinstance(items, list):
            return []
        
        cleaned_items = []
        for item in items:
            if isinstance(item, dict) and 'name' in item and 'quantity' in item:
                try:
                    cleaned_item = {
                        'name': str(item['name']).strip(),
                        'quantity': int(item['quantity'])
                    }
                    if cleaned_item['name'] and cleaned_item['quantity'] > 0:
                        cleaned_items.append(cleaned_item)
                except (ValueError, TypeError):
                    continue
        
        return cleaned_items
    
    def _clean_date(self, value: Any) -> str:
        """清理日期格式"""
        if value is None or str(value).strip() == '':
            return None
        
        date_str = str(value).strip()
        # 簡單的日期格式驗證
        if len(date_str) == 10 and date_str.count('-') == 2:
            return date_str
        
        return None