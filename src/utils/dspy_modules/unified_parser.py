"""
統一訂單解析 DSPy 模組
統一處理單一和多訂單，都以陣列格式返回
"""
import dspy
import json
import re
from typing import Dict, Any, List
import mlflow
# 設定 MLflow 實驗名稱
mlflow.set_experiment("line_order_experiment")
mlflow.dspy.autolog()


class UnifiedOrderSignature(dspy.Signature):
    """統一訂單解析 Signature
    
    統一處理所有類型的訂單，輸出格式：
    - 永遠返回訂單陣列格式
    - 單一訂單：[{訂單1}]
    - 多訂單：[{訂單1}, {訂單2}, ...]
    - 包含改進的商品解析邏輯，保留產品編號
    """
    order_text = dspy.InputField(desc="原始訂單文字，可能包含單一或多個訂單")
    orders_json = dspy.OutputField(desc="解析後的訂單陣列 JSON，格式：[{\"sender_name\": null, \"sender_phone\": null, \"receiver_name\": \"收件人\", \"receiver_phone\": \"電話\", \"items\": [{\"name\": \"商品名稱\", \"quantity\": 數量}], \"shipping_date\": null, \"shipping_address\": \"地址\"}]")


class UnifiedOrderParser(dspy.Module):
    """統一訂單解析模組"""
    
    def __init__(self):
        super().__init__()
        self.parse = dspy.ChainOfThought(UnifiedOrderSignature)
        
        # 建立 Few-shot 範例
        self.examples = [
            # 單一訂單範例
            dspy.Example(
                order_text="收件人：王小明 電話：0912345678 地址：台北市中正區重慶南路一段122號 商品：18A禮盒 x2",
                orders_json='[{"sender_name": null, "sender_phone": null, "receiver_name": "王小明", "receiver_phone": "0912345678", "items": [{"name": "18A禮盒", "quantity": 2}], "shipping_date": null, "shipping_address": "台北市中正區重慶南路一段122號"}]'
            ).with_inputs("order_text"),
            
            # 多商品單一訂單範例
            dspy.Example(
                order_text="收件人：李美華 電話：0987654321 地址：高雄市前金區中正四路211號 商品：16A蛋糕 x1, 20A花束 x3",
                orders_json='[{"sender_name": null, "sender_phone": null, "receiver_name": "李美華", "receiver_phone": "0987654321", "items": [{"name": "16A蛋糕", "quantity": 1}, {"name": "20A花束", "quantity": 3}], "shipping_date": null, "shipping_address": "高雄市前金區中正四路211號"}]'
            ).with_inputs("order_text"),
            
            # 多訂單範例
            dspy.Example(
                order_text="1. 收件人：張三 電話：0911111111 地址：台中市西區民權路100號 商品：12A巧克力禮盒 x1 2. 收件人：李四 電話：0922222222 地址：台南市東區東門路200號 商品：24A生日蛋糕 x2",
                orders_json='[{"sender_name": null, "sender_phone": null, "receiver_name": "張三", "receiver_phone": "0911111111", "items": [{"name": "12A巧克力禮盒", "quantity": 1}], "shipping_date": null, "shipping_address": "台中市西區民權路100號"}, {"sender_name": null, "sender_phone": null, "receiver_name": "李四", "receiver_phone": "0922222222", "items": [{"name": "24A生日蛋糕", "quantity": 2}], "shipping_date": null, "shipping_address": "台南市東區東門路200號"}]'
            ).with_inputs("order_text"),
            
            # 包含寄件人資訊的範例
            dspy.Example(
                order_text="寄件人：ABC公司 電話：02-12345678 收件人：陳小姐 電話：0933333333 地址：新北市板橋區文化路300號 商品：18A特製禮盒(客製包裝) x1 發貨日期：2025-01-15",
                orders_json='[{"sender_name": "ABC公司", "sender_phone": "02-12345678", "receiver_name": "陳小姐", "receiver_phone": "0933333333", "items": [{"name": "18A特製禮盒(客製包裝)", "quantity": 1}], "shipping_date": "2025-01-15", "shipping_address": "新北市板橋區文化路300號"}]'
            ).with_inputs("order_text"),
            
            # 沒有產品編號的商品範例
            dspy.Example(
                order_text="收件人：劉先生 電話：0944444444 地址：桃園市中壢區中正路500號 商品：鳳梨酥禮盒 x2, 牛軋糖 x1",
                orders_json='[{"sender_name": null, "sender_phone": null, "receiver_name": "劉先生", "receiver_phone": "0944444444", "items": [{"name": "鳳梨酥禮盒", "quantity": 2}, {"name": "牛軋糖", "quantity": 1}], "shipping_date": null, "shipping_address": "桃園市中壢區中正路500號"}]'
            ).with_inputs("order_text"),
            
            # 使用 emoji 分隔符的多訂單範例
            dspy.Example(
                order_text="🩷18A禮盒（2盒） 🌸寄件人：王小明 收件人: 李大華 🌸寄件人電話：0912345678 收件人電話: 0987654321 🌸台北市中正區重慶南路100號 送貨日期：1/15號 🩷20A蛋糕（1個） 🌸寄件人：張三 收件人: 李四 🌸寄件人電話：0911111111 收件人電話: 0922222222 🌸台中市西區民權路200號 送貨日期：1/16號",
                orders_json='[{"sender_name": "王小明", "sender_phone": "0912345678", "receiver_name": "李大華", "receiver_phone": "0987654321", "items": [{"name": "18A禮盒", "quantity": 2}], "shipping_date": null, "shipping_address": "台北市中正區重慶南路100號"}, {"sender_name": "張三", "sender_phone": "0911111111", "receiver_name": "李四", "receiver_phone": "0922222222", "items": [{"name": "20A蛋糕", "quantity": 1}], "shipping_date": null, "shipping_address": "台中市西區民權路200號"}]'
            ).with_inputs("order_text"),
            
            # 收件人姓名缺失的範例（智能推斷收件人）
            dspy.Example(
                order_text="🩷12A巧克力禮盒（3盒） 🌸寄件人：陳老師 🌸收件人電話：0933333333 🌸新北市板橋區文化路300號 🩷16A花束（1束） 🌸寄件人：林同學 🌸收件人電話：0944444444 🌸桃園市中壢區中正路400號",
                orders_json='[{"sender_name": "陳老師", "sender_phone": null, "receiver_name": "收件人", "receiver_phone": "0933333333", "items": [{"name": "12A巧克力禮盒", "quantity": 3}], "shipping_date": null, "shipping_address": "新北市板橋區文化路300號"}, {"sender_name": "林同學", "sender_phone": null, "receiver_name": "收件人", "receiver_phone": "0944444444", "items": [{"name": "16A花束", "quantity": 1}], "shipping_date": null, "shipping_address": "桃園市中壢區中正路400號"}]'
            ).with_inputs("order_text"),
            
            # 真實案例：類似用戶提供的格式
            dspy.Example(
                order_text="🩷18A禮盒（8盒） 🌸寄件人：姜正君 收件人: 徐長宏 🌸寄件人電話：0910020932 收件人電話: 091578456 🌸士林福林路377號（溪泊林工地） 送貨日期：9/11號（星期三） 🩷20A禮盒（8盒） 🌸寄件人：徐奇異 🌸收件人電話：0910020932 🌸中壢區文化路123號 送貨日期：9/11號（星期三）",
                orders_json='[{"sender_name": "姜正君", "sender_phone": "0910020932", "receiver_name": "徐長宏", "receiver_phone": "091578456", "items": [{"name": "18A禮盒", "quantity": 8}], "shipping_date": null, "shipping_address": "士林福林路377號（溪泊林工地）"}, {"sender_name": "徐奇異", "sender_phone": null, "receiver_name": "收件人", "receiver_phone": "0910020932", "items": [{"name": "20A禮盒", "quantity": 8}], "shipping_date": null, "shipping_address": "中壢區文化路123號"}]'
            ).with_inputs("order_text")
        ]
    
    def forward(self, order_text: str) -> dspy.Prediction:
        """
        統一解析訂單文字
        
        Args:
            order_text: 原始訂單文字
            
        Returns:
            dspy.Prediction: 包含 orders_json (string)，永遠是陣列格式
        """
        if not order_text or not isinstance(order_text, str):
            return dspy.Prediction(orders_json='[]')
        
        # 預處理：移除多餘空白
        cleaned_text = self._preprocess_text(order_text)
        
        try:
            # 建立詳細的解析提示
            enhanced_prompt = self._create_parsing_prompt(cleaned_text)
            
            # 使用 DSPy 進行解析
            result = self.parse(order_text=enhanced_prompt)
            
            # 驗證和處理 JSON
            parsed_json = result.orders_json
            if isinstance(parsed_json, str):
                orders = json.loads(parsed_json)
            else:
                orders = parsed_json
            
            # 確保返回的是陣列
            if not isinstance(orders, list):
                # 如果不是陣列，嘗試轉換
                if isinstance(orders, dict):
                    orders = [orders]
                else:
                    raise ValueError("Invalid format: not a list or dict")
            
            # 清理和驗證每個訂單
            cleaned_orders = []
            for order in orders:
                if isinstance(order, dict):
                    cleaned_order = self._clean_order_data(order)
                    # 只保留有效的訂單（至少要有收件人和地址）
                    if (cleaned_order.get('receiver_name') and 
                        cleaned_order.get('shipping_address')):
                        cleaned_orders.append(cleaned_order)
            
            # 如果沒有有效訂單，使用 fallback
            if not cleaned_orders:
                return dspy.Prediction(orders_json=self._fallback_parse(cleaned_text))
            
            return dspy.Prediction(orders_json=json.dumps(cleaned_orders, ensure_ascii=False))
            
        except Exception as e:
            # AI 失敗時的 fallback
            return dspy.Prediction(orders_json=self._fallback_parse(cleaned_text))
    
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
    
    def _create_parsing_prompt(self, order_text: str) -> str:
        """建立詳細的解析提示"""
        return f"""請解析以下訂單內容並輸出 JSON 陣列格式：

{order_text}

解析規則：
1. 永遠返回陣列格式，單一訂單也要包在陣列中：[{{訂單1}}] 或 [{{訂單1}}, {{訂單2}}, ...]
2. 每個訂單包含以下欄位：
   - sender_name: 寄件人姓名（選填，沒有時設為 null）
   - sender_phone: 寄件人電話（選填，沒有時設為 null）
   - receiver_name: 收件人姓名（必填）
   - receiver_phone: 收件人電話（必填）
   - items: 商品陣列，格式 [{{"name": "商品名稱", "quantity": 數量}}]
   - shipping_date: 發貨日期（選填，格式 YYYY-MM-DD 或 null）
   - shipping_address: 收件地址（必填）

3. 商品解析特別規則：
   - 保留所有數字編號（如 18A、16A、20A 等）
   - 保留括號內容（如 (客製包裝)、(工地) 等）
   - 識別各種數量表達：x2、兩個、3盒、一束等
   - 多商品用逗號分隔

4. 多訂單判斷：
   - 有多個不同的收件人 = 多訂單
   - 有多個不同的收件地址 = 多訂單
   - 有序號標記（1. 2. 或 一、二、）= 多訂單
   - 有多個商品區塊（🩷 或其他分隔符）= 多訂單
   - 有多個寄件人 = 多訂單

5. 特殊處理規則：
   - 如果缺少收件人姓名，使用"收件人"作為預設值
   - emoji 符號（🩷🌸等）用作訂單和欄位分隔符
   - 每個 🩷 標記一個新訂單的開始
   - 地址可能沒有"地址:"前綴，要從上下文推斷

輸出必須是有效的 JSON 陣列格式。"""
    
    def _clean_order_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """清理和標準化訂單資料"""
        return {
            "sender_name": self._clean_string(data.get('sender_name')),
            "sender_phone": self._clean_phone(data.get('sender_phone')),
            "receiver_name": self._clean_string(data.get('receiver_name')),
            "receiver_phone": self._clean_phone(data.get('receiver_phone')),
            "items": self._clean_items(data.get('items', [])),
            "shipping_date": self._clean_date(data.get('shipping_date')),
            "shipping_address": self._clean_string(data.get('shipping_address'))
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
        """清理商品清單，包含改進的商品解析"""
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
    
    def _fallback_parse(self, order_text: str) -> str:
        """簡單的 fallback 解析"""
        try:
            # 基本的規則解析
            fallback_order = {
                "sender_name": None,
                "sender_phone": None,
                "receiver_name": self._extract_receiver_name(order_text),
                "receiver_phone": self._extract_phone(order_text),
                "items": self._extract_items_fallback(order_text),
                "shipping_date": None,
                "shipping_address": self._extract_address(order_text)
            }
            
            # 確保至少有收件人和地址
            if fallback_order['receiver_name'] and fallback_order['shipping_address']:
                return json.dumps([fallback_order], ensure_ascii=False)
            else:
                return '[]'
                
        except Exception:
            return '[]'
    
    def _extract_receiver_name(self, text: str) -> str:
        """提取收件人姓名"""
        patterns = [
            r'收件人[:：]\s*([^\s電話地址]+)',
            r'收件人\s+([^\s電話地址]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_phone(self, text: str) -> str:
        """提取電話號碼"""
        patterns = [
            r'電話[:：]\s*([\d\-\+\(\)\s]+)',
            r'手機[:：]\s*([\d\-\+\(\)\s]+)',
            r'(09\d{8})',
            r'(\d{2,3}-\d{6,8})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                phone = match.group(1).strip()
                if len(phone) >= 8:
                    return phone
        
        return None
    
    def _extract_address(self, text: str) -> str:
        """提取地址"""
        patterns = [
            r'地址[:：]\s*([^商品發貨電話]+)',
            r'收件地址[:：]\s*([^商品發貨電話]+)',
            r'送到[:至]\s*([^商品發貨電話]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                address = match.group(1).strip()
                if len(address) > 5:  # 地址長度合理檢查
                    return address
        
        return None
    
    def _extract_items_fallback(self, text: str) -> List[Dict[str, Any]]:
        """提取商品項目（fallback）"""
        items = []
        
        # 尋找商品相關文字
        item_patterns = [
            r'商品[:：]\s*([^發貨地址電話]+)',
            r'物品[:：]\s*([^發貨地址電話]+)',
        ]
        
        item_text = ""
        for pattern in item_patterns:
            match = re.search(pattern, text)
            if match:
                item_text = match.group(1).strip()
                break
        
        if not item_text:
            # 如果沒找到，使用原始文字作為商品名稱
            items.append({"name": "訂單商品", "quantity": 1})
            return items
        
        # 簡單解析商品項目
        parts = re.split(r'[,，;；]', item_text)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 提取數量
            quantity = 1
            quantity_patterns = [
                r'x\s*(\d+)',
                r'(\d+)\s*[個盒束份張袋包]',
                r'(\d+)\s*$',
            ]
            
            for qpattern in quantity_patterns:
                qmatch = re.search(qpattern, part, re.IGNORECASE)
                if qmatch:
                    try:
                        quantity = int(qmatch.group(1))
                        part = re.sub(qpattern, '', part, flags=re.IGNORECASE).strip()
                        break
                    except:
                        pass
            
            # 清理商品名稱
            name = part.strip()
            if name:
                items.append({"name": name, "quantity": quantity})
        
        # 如果沒有解析出任何商品，使用原始文字
        if not items:
            items.append({"name": item_text, "quantity": 1})
        
        return items


# 建立全域實例供其他模組使用
unified_parser = UnifiedOrderParser()