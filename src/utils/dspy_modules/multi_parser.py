"""
多訂單解析模組
"""
import dspy
import json
from typing import Dict, Any, List
from .signatures import MultiOrderSignature
from ..order_schemas import MULTI_ORDER_SCHEMA


class MultiOrderParser(dspy.Module):
    """解析多訂單（最多5份）"""
    
    def __init__(self):
        super().__init__()
        self.parse = dspy.ChainOfThought(MultiOrderSignature)
    
    def forward(self, order_text: str) -> dspy.Prediction:
        """
        解析多訂單文字為結構化 JSON
        
        Args:
            order_text: 包含多訂單的文字
            
        Returns:
            dspy.Prediction: 包含 orders_json (dict)
        """
        # 建立詳細的解析提示
        enhanced_prompt = self._create_parsing_prompt(order_text)
        
        # 使用 DSPy 進行解析
        result = self.parse(order_text=enhanced_prompt)
        
        # 解析和驗證 JSON
        try:
            if isinstance(result.orders_json, str):
                orders_data = json.loads(result.orders_json)
            else:
                orders_data = result.orders_json
            
            # 確保包含 order_type
            if 'order_type' not in orders_data:
                orders_data['order_type'] = 'multiple'
            
            # 驗證訂單數量限制
            orders = orders_data.get('orders', [])
            if len(orders) > 5:
                return dspy.Prediction(orders_json={
                    "order_type": "error",
                    "error_message": "訂單數量超過限制（最多5份）"
                })
            
            if len(orders) < 2:
                return dspy.Prediction(orders_json={
                    "order_type": "error", 
                    "error_message": "多訂單至少需要2份訂單"
                })
            
            # 清理和標準化資料
            cleaned_data = self._clean_orders_data(orders_data)
            
            return dspy.Prediction(orders_json=cleaned_data)
            
        except (json.JSONDecodeError, TypeError) as e:
            # JSON 解析失敗，返回錯誤格式
            error_data = {
                "order_type": "error",
                "error_message": f"多訂單 JSON 解析失敗: {str(e)}"
            }
            return dspy.Prediction(orders_json=error_data)
    
    def _create_parsing_prompt(self, order_text: str) -> str:
        """建立增強的多訂單解析提示"""
        return f"""請解析以下多訂單內容並輸出 JSON 格式（最多5份訂單）：

{order_text}

多訂單定義：
- 多訂單是指文字中包含多個不同的收件人或多個不同的收件地址
- 每個收件人/地址對應一份獨立的訂單
- 如果只有一個收件人和一個地址，即使有多個商品，也是單一訂單

解析規則：
1. 每份訂單的寄件人資訊（sender_name, sender_phone）為選填，可設為 null
2. 每份訂單的收件人資訊（receiver_name, receiver_phone）為必填
3. 每份訂單的商品清單（items）必須為陣列格式，包含 name 和 quantity
4. 每份訂單的收件地址（shipping_address）為必填
5. 每份訂單的發貨日期（shipping_date）為選填，格式 YYYY-MM-DD 或 null
6. 每份訂單需要有 order_index（1-5）

輸出格式要求：
- order_type: "multiple"
- total_orders: 訂單總數（根據不同收件人或地址的數量）
- orders: 訂單陣列，每個訂單包含 order_index

輸出必須是有效的 JSON 格式。"""
    
    def _clean_orders_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """清理和標準化多訂單資料"""
        orders = data.get('orders', [])
        cleaned_orders = []
        
        for i, order in enumerate(orders, 1):
            if not isinstance(order, dict):
                continue
                
            cleaned_order = {
                "order_index": i,
                "sender_name": self._clean_string(order.get('sender_name')),
                "sender_phone": self._clean_phone(order.get('sender_phone')),
                "receiver_name": self._clean_string(order.get('receiver_name')),
                "receiver_phone": self._clean_phone(order.get('receiver_phone')),
                "items": self._clean_items(order.get('items', [])),
                "shipping_date": self._clean_date(order.get('shipping_date')),
                "shipping_address": self._clean_string(order.get('shipping_address'))
            }
            
            # 驗證必填欄位
            if (cleaned_order['receiver_name'] and 
                cleaned_order['receiver_phone'] and 
                cleaned_order['items'] and 
                cleaned_order['shipping_address']):
                cleaned_orders.append(cleaned_order)
        
        return {
            "order_type": "multiple",
            "total_orders": len(cleaned_orders),
            "orders": cleaned_orders
        }
    
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
    
    def _clean_items(self, items: Any) -> List[Dict[str, Any]]:
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