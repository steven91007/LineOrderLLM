"""
Unified order-parsing DSPy module.
Handles both single and multiple orders; always returns an array.
"""
import dspy
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from ..weekday_converter import WeekdayConverter


class UnifiedOrderSignature(dspy.Signature):
    """Unified order-parsing signature.
    
    Handles every kind of order. Output format:
    - Always return an array of orders
    - Single order: [{order1}]
    - Multiple orders: [{order1}, {order2}, ...]
    - Uses improved item-parsing logic and keeps product codes
    - Converts dates accurately, based on the provided current date
    """
    order_text = dspy.InputField(desc="Raw order text; may contain one or several orders")
    current_date = dspy.InputField(desc="Current date, format: YYYY-MM-DD (星期X), used as the reference point for converting weekday names")
    orders_json = dspy.OutputField(desc="Parsed orders as a JSON array, format: [{\"sender_name\": null, \"sender_phone\": null, \"receiver_name\": \"receiver name\", \"receiver_phone\": \"phone\", \"items\": [{\"name\": \"item name\", \"quantity\": quantity}], \"shipping_date\": \"MM-DD\", \"shipping_address\": \"address\"}]")


class UnifiedOrderParser(dspy.Module):
    """Unified order-parsing module."""
    
    def __init__(self):
        super().__init__()
        self.parse = dspy.ChainOfThought(UnifiedOrderSignature)
        
        # Few-shot examples
        self.examples = [
            # Single order
            dspy.Example(
                order_text="收件人：王小明 電話：0912345678 地址：台北市中正區重慶南路一段122號 商品：18A禮盒 x2",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": null, "sender_phone": null, "receiver_name": "王小明", "receiver_phone": "0912345678", "items": [{"name": "18A禮盒", "quantity": 2}], "shipping_date": null, "shipping_address": "台北市中正區重慶南路一段122號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Single order with multiple items
            dspy.Example(
                order_text="收件人：李美華 電話：0987654321 地址：高雄市前金區中正四路211號 商品：16A蛋糕 x1, 20A花束 x3",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": null, "sender_phone": null, "receiver_name": "李美華", "receiver_phone": "0987654321", "items": [{"name": "16A蛋糕", "quantity": 1}, {"name": "20A花束", "quantity": 3}], "shipping_date": null, "shipping_address": "高雄市前金區中正四路211號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Multiple orders
            dspy.Example(
                order_text="1. 收件人：張三 電話：0911111111 地址：台中市西區民權路100號 商品：12A巧克力禮盒 x1 2. 收件人：李四 電話：0922222222 地址：台南市東區東門路200號 商品：24A生日蛋糕 x2",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": null, "sender_phone": null, "receiver_name": "張三", "receiver_phone": "0911111111", "items": [{"name": "12A巧克力禮盒", "quantity": 1}], "shipping_date": null, "shipping_address": "台中市西區民權路100號"}, {"sender_name": null, "sender_phone": null, "receiver_name": "李四", "receiver_phone": "0922222222", "items": [{"name": "24A生日蛋糕", "quantity": 2}], "shipping_date": null, "shipping_address": "台南市東區東門路200號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Order with sender information
            dspy.Example(
                order_text="寄件人：ABC公司 電話：02-12345678 收件人：陳小姐 電話：0933333333 地址：新北市板橋區文化路300號 商品：18A特製禮盒(客製包裝) x1 發貨日期：01-15",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": "ABC公司", "sender_phone": "02-12345678", "receiver_name": "陳小姐", "receiver_phone": "0933333333", "items": [{"name": "18A特製禮盒(客製包裝)", "quantity": 1}], "shipping_date": "01-15", "shipping_address": "新北市板橋區文化路300號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Items without a product code
            dspy.Example(
                order_text="收件人：劉先生 電話：0944444444 地址：桃園市中壢區中正路500號 商品：鳳梨酥禮盒 x2, 牛軋糖 x1",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": null, "sender_phone": null, "receiver_name": "劉先生", "receiver_phone": "0944444444", "items": [{"name": "鳳梨酥禮盒", "quantity": 2}, {"name": "牛軋糖", "quantity": 1}], "shipping_date": null, "shipping_address": "桃園市中壢區中正路500號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Multiple orders separated by emoji
            dspy.Example(
                order_text="🩷18A禮盒（2盒） 🌸寄件人：王小明 收件人: 李大華 🌸寄件人電話：0912345678 收件人電話: 0987654321 🌸台北市中正區重慶南路100號 送貨日期：1/15號 🩷20A蛋糕（1個） 🌸寄件人：張三 收件人: 李四 🌸寄件人電話：0911111111 收件人電話: 0922222222 🌸台中市西區民權路200號 送貨日期：1/16號",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": "王小明", "sender_phone": "0912345678", "receiver_name": "李大華", "receiver_phone": "0987654321", "items": [{"name": "18A禮盒", "quantity": 2}], "shipping_date": null, "shipping_address": "台北市中正區重慶南路100號"}, {"sender_name": "張三", "sender_phone": "0911111111", "receiver_name": "李四", "receiver_phone": "0922222222", "items": [{"name": "20A蛋糕", "quantity": 1}], "shipping_date": null, "shipping_address": "台中市西區民權路200號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # "*quantity" format (also shows converting Sunday to a date)
            dspy.Example(
                order_text="訂購人：徐奇檍 訂購人電話：091767778 收件人：張志文 收件人地址：桃園市中壢區文化二路273巷 收件人電話：0981768 數量：18A禮盒 *4 預計出貨日：星期天",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": "徐奇檍", "sender_phone": "091767778", "receiver_name": "張志文", "receiver_phone": "0981768", "items": [{"name": "18A禮盒", "quantity": 4}], "shipping_date": "08-18", "shipping_address": "桃園市中壢區文化二路273巷"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Items using "*" to mark quantity
            dspy.Example(
                order_text="收件人：林小姐 電話：0955666777 地址：新北市新店區北新路100號 商品：16A蛋糕 *2, 20A花束 *1",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": null, "sender_phone": null, "receiver_name": "林小姐", "receiver_phone": "0955666777", "items": [{"name": "16A蛋糕", "quantity": 2}, {"name": "20A花束", "quantity": 1}], "shipping_date": null, "shipping_address": "新北市新店區北新路100號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Missing receiver name (receiver inferred)
            dspy.Example(
                order_text="🩷12A巧克力禮盒（3盒） 🌸寄件人：陳老師 🌸收件人電話：0933333333 🌸新北市板橋區文化路300號 🩷16A花束（1束） 🌸寄件人：林同學 🌸收件人電話：0944444444 🌸桃園市中壢區中正路400號",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": "陳老師", "sender_phone": null, "receiver_name": "收件人", "receiver_phone": "0933333333", "items": [{"name": "12A巧克力禮盒", "quantity": 3}], "shipping_date": null, "shipping_address": "新北市板橋區文化路300號"}, {"sender_name": "林同學", "sender_phone": null, "receiver_name": "收件人", "receiver_phone": "0944444444", "items": [{"name": "16A花束", "quantity": 1}], "shipping_date": null, "shipping_address": "桃園市中壢區中正路400號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Real-world case: similar to a format a user sent
            dspy.Example(
                order_text="🩷18A禮盒（8盒） 🌸寄件人：姜正君 收件人: 徐長宏 🌸寄件人電話：0910020932 收件人電話: 091578456 🌸士林福林路377號（溪泊林工地） 送貨日期：9/11號（星期三） 🩷20A禮盒（8盒） 🌸寄件人：徐奇異 🌸收件人電話：0910020932 🌸中壢區文化路123號 送貨日期：9/11號（星期三）",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": "姜正君", "sender_phone": "0910020932", "receiver_name": "徐長宏", "receiver_phone": "091578456", "items": [{"name": "18A禮盒", "quantity": 8}], "shipping_date": "09-11", "shipping_address": "士林福林路377號（溪泊林工地）"}, {"sender_name": "徐奇異", "sender_phone": null, "receiver_name": "收件人", "receiver_phone": "0910020932", "items": [{"name": "20A禮盒", "quantity": 8}], "shipping_date": "09-11", "shipping_address": "中壢區文化路123號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Weekday name (shows correct date reasoning)
            dspy.Example(
                order_text="訂購人：徐奇檍 電話：0912345678 收件人：張志文 地址：桃園市中壢區文化二路273巷 電話：0987654321 商品：18A禮盒 *4 預計出貨日：星期天",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": "徐奇檍", "sender_phone": "0912345678", "receiver_name": "張志文", "receiver_phone": "0987654321", "items": [{"name": "18A禮盒", "quantity": 4}], "shipping_date": "08-18", "shipping_address": "桃園市中壢區文化二路273巷"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Absolute date (9/20 format)
            dspy.Example(
                order_text="訂購人：李小明 電話：0911111111 收件人：王大華 地址：台北市信義區信義路100號 電話：0922222222 商品：20A花束 *2 發貨日期：9/20",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": "李小明", "sender_phone": "0911111111", "receiver_name": "王大華", "receiver_phone": "0922222222", "items": [{"name": "20A花束", "quantity": 2}], "shipping_date": "09-20", "shipping_address": "台北市信義區信義路100號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Absolute date (9-20 format)
            dspy.Example(
                order_text="訂購人：陳美麗 電話：0933333333 收件人：林志偉 地址：高雄市前鎮區民權二路250號 電話：0944444444 商品：16A蛋糕 *1 出貨日：9-20",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": "陳美麗", "sender_phone": "0933333333", "receiver_name": "林志偉", "receiver_phone": "0944444444", "items": [{"name": "16A蛋糕", "quantity": 1}], "shipping_date": "09-20", "shipping_address": "高雄市前鎮區民權二路250號"}]'
            ).with_inputs("order_text", "current_date"),
            
            # Mixed date formats
            dspy.Example(
                order_text="訂購人：張小華 電話：0955555555 收件人：劉建國 地址：新竹市東區光復路300號 電話：0966666666 商品：12A巧克力 *3 送貨日期：10/15號",
                current_date="2024-08-15 (星期四)",
                orders_json='[{"sender_name": "張小華", "sender_phone": "0955555555", "receiver_name": "劉建國", "receiver_phone": "0966666666", "items": [{"name": "12A巧克力", "quantity": 3}], "shipping_date": "10-15", "shipping_address": "新竹市東區光復路300號"}]'
            ).with_inputs("order_text", "current_date")
        ]
    
    def forward(self, order_text: str, reference_date: Optional[datetime] = None) -> dspy.Prediction:
        """
        Parse order text in a unified way.
        
        Args:
            order_text: raw order text
            reference_date: reference date for converting weekday names; defaults to now
            
        Returns:
            dspy.Prediction: contains orders_json (string), always an array
        """
        if not order_text or not isinstance(order_text, str):
            return dspy.Prediction(orders_json='[]')
        
        # Set the reference date
        if reference_date is None:
            reference_date = datetime.now()
        self._reference_date = reference_date
        
        # Preprocess: collapse extra whitespace
        cleaned_text = self._preprocess_text(order_text)
        
        try:
            # Build the detailed parsing prompt
            enhanced_prompt = self._create_parsing_prompt(cleaned_text)
            
            # Format the current date (weekday names in Chinese)
            current_date_str = reference_date.strftime('%Y-%m-%d (%A)')
            current_date_str = current_date_str.replace('Monday', '星期一').replace('Tuesday', '星期二').replace('Wednesday', '星期三').replace('Thursday', '星期四').replace('Friday', '星期五').replace('Saturday', '星期六').replace('Sunday', '星期日')
            
            # Parse with DSPy, passing the current date
            result = self.parse(order_text=enhanced_prompt, current_date=current_date_str)
            
            # Validate and process the JSON
            parsed_json = result.orders_json
            if isinstance(parsed_json, str):
                orders = json.loads(parsed_json)
            else:
                orders = parsed_json
            
            # Make sure we return a list
            if not isinstance(orders, list):
                # Not a list: try to convert
                if isinstance(orders, dict):
                    orders = [orders]
                else:
                    raise ValueError("Invalid format: not a list or dict")
            
            # Clean and validate each order
            cleaned_orders = []
            for order in orders:
                if isinstance(order, dict):
                    cleaned_order = self._clean_order_data(order)
                    
                    # Only fall back to extracting the date from the raw text when DSPy gave no valid date
                    if not cleaned_order.get('shipping_date'):
                        date_from_text = self._extract_date_from_text(cleaned_text, self._reference_date)
                        if date_from_text:
                            cleaned_order['shipping_date'] = date_from_text
                    
                    # Keep only valid orders (must have at least a receiver and an address)
                    if (cleaned_order.get('receiver_name') and 
                        cleaned_order.get('shipping_address')):
                        cleaned_orders.append(cleaned_order)
            
            # No valid orders: use the fallback
            if not cleaned_orders:
                return dspy.Prediction(orders_json=self._fallback_parse(cleaned_text))
            
            return dspy.Prediction(orders_json=json.dumps(cleaned_orders, ensure_ascii=False))
            
        except Exception as e:
            # Fallback when the AI fails
            return dspy.Prediction(orders_json=self._fallback_parse(cleaned_text))
    
    def _preprocess_text(self, text: str) -> str:
        """Preprocess the order text."""
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
    
    def _create_parsing_prompt(self, order_text: str) -> str:
        """Build the detailed parsing prompt."""
        # Get the current date and the weekday conversion table
        current_date = getattr(self, '_reference_date', datetime.now())
        weekday_map = self._generate_weekday_conversion_table(current_date)
        
        return f"""Parse the following order content and output a JSON array:

{order_text}

Important: current date information
{weekday_map}

Parsing rules:
1. Always return an array; wrap even a single order in an array: [{{order1}}] or [{{order1}}, {{order2}}, ...]
2. Each order contains these fields:
   - sender_name: sender name (optional; null if absent)
   - sender_phone: sender phone (optional; null if absent)
   - receiver_name: receiver name (required)
   - receiver_phone: receiver phone (required)
   - items: array of items, format [{{"name": "item name", "quantity": quantity}}]
   - shipping_date: shipping date (optional; format MM-DD or null)
     • If it is a weekday name, convert it precisely using the weekday conversion table (星期幾轉換對照表) provided above
     • If it is an absolute date (e.g. 9/20, 9-20, 9月20日, 10/15號), convert it directly to MM-DD (e.g. 09-20, 10-15)
     • Convert any other concrete date format to MM-DD as well
   - shipping_address: receiver address (required)

3. Special item-parsing rules:
   - Keep all numeric codes (e.g. 18A, 16A, 20A)
   - Keep parenthesized content (e.g. (客製包裝), (工地))
   - Recognize all ways of expressing quantity: x2, *2, 兩個, 3盒, 一束, etc.
   - Support "*" to mark quantity (e.g. 18A禮盒 *4)
   - Multiple items are separated by commas

4. Detecting multiple orders:
   - Several different receivers = multiple orders
   - Several different receiver addresses = multiple orders
   - Numbered markers (1. 2. or 一、二、) = multiple orders
   - Several item blocks (🩷 or another separator) = multiple orders
   - Several senders = multiple orders

5. Special handling rules:
   - If the receiver name is missing, use "收件人" as the default value
   - Emoji (🩷🌸 etc.) act as order and field separators
   - Each 🩷 marks the start of a new order
   - The address may lack an "地址:" prefix; infer it from context

The output must be a valid JSON array."""
    
    def _clean_order_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and normalize order data."""
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
        """Clean a string value."""
        if value is None or str(value).strip() == '':
            return None
        return str(value).strip()
    
    def _clean_phone(self, value: Any) -> str:
        """Clean a phone number."""
        if value is None or str(value).strip() == '':
            return None
        phone = str(value).strip()
        # Basic phone format check (shorter numbers allowed for special cases)
        if len(phone) < 7:
            return None
        return phone
    
    def _clean_items(self, items: Any) -> List[Dict[str, Any]]:
        """Clean the item list, with improved item parsing."""
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
        """Clean the date format, with weekday-name conversion."""
        if value is None or str(value).strip() == '':
            return None
        
        date_str = str(value).strip()
        
        # Already a correct MM-DD: return as-is (trust DSPy's result)
        if len(date_str) == 5 and date_str.count('-') == 1:
            try:
                # Check the format is valid (MM-DD)
                parts = date_str.split('-')
                if (len(parts) == 2 and 
                    parts[0].isdigit() and parts[1].isdigit() and
                    1 <= int(parts[0]) <= 12 and 1 <= int(parts[1]) <= 31):
                    return date_str
            except:
                pass
        
        # First try to parse as an absolute date (9/20, 9-20, etc.)
        absolute_date = WeekdayConverter.parse_absolute_date(date_str)
        if absolute_date:
            return absolute_date
        
        # Only non-MM-DD dates go through WeekdayConverter
        reference_date = getattr(self, '_reference_date', datetime.now())
        converted_date = WeekdayConverter.parse_shipping_date(date_str, reference_date)
        if converted_date:
            return converted_date
        
        # WeekdayConverter couldn't handle it: use the original logic
        # Full YYYY-MM-DD: extract month and day
        if len(date_str) == 10 and date_str.count('-') == 2:
            parts = date_str.split('-')
            if len(parts) == 3:
                # Return MM-DD
                return f"{parts[1]}-{parts[2]}"
        
        # Already MM-DD: return as-is
        if len(date_str) == 5 and date_str.count('-') == 1:
            return date_str
            
        # Handle other possible formats (e.g. 9/11, 01/15)
        import re
        patterns = [
            r'(\d{1,2})/(\d{1,2})',  # 9/11 or 01/15
            r'(\d{1,2})-(\d{1,2})',  # 9-11 or 01-15
            r'(\d{1,2})\.(\d{1,2})', # 9.11 or 01.15
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                month = match.group(1).zfill(2)  # zero-pad to two digits
                day = match.group(2).zfill(2)    # zero-pad to two digits
                return f"{month}-{day}"
        
        return None
    
    def _fallback_parse(self, order_text: str) -> str:
        """Simple fallback parse."""
        try:
            # Basic rule-based parse
            fallback_order = {
                "sender_name": None,
                "sender_phone": None,
                "receiver_name": self._extract_receiver_name(order_text),
                "receiver_phone": self._extract_phone(order_text),
                "items": self._extract_items_fallback(order_text),
                "shipping_date": None,
                "shipping_address": self._extract_address(order_text)
            }
            
            # Require at least a receiver and an address
            if fallback_order['receiver_name'] and fallback_order['shipping_address']:
                return json.dumps([fallback_order], ensure_ascii=False)
            else:
                return '[]'
                
        except Exception:
            return '[]'
    
    def _extract_receiver_name(self, text: str) -> str:
        """Extract the receiver name."""
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
        """Extract the phone number."""
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
        """Extract the address."""
        patterns = [
            r'地址[:：]\s*([^商品發貨電話]+)',
            r'收件地址[:：]\s*([^商品發貨電話]+)',
            r'送到[:至]\s*([^商品發貨電話]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                address = match.group(1).strip()
                if len(address) > 5:  # sanity check on address length
                    return address
        
        return None
    
    def _extract_items_fallback(self, text: str) -> List[Dict[str, Any]]:
        """Extract items (fallback)."""
        items = []
        
        # Look for item-related text
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
            # Nothing found: use a placeholder item name ("訂單商品" = order item)
            items.append({"name": "訂單商品", "quantity": 1})
            return items
        
        # Simple item parsing
        parts = re.split(r'[,，;；]', item_text)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Extract the quantity
            quantity = 1
            quantity_patterns = [
                r'\*\s*(\d+)',  # supports the *4 format
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
            
            # Clean the item name
            name = part.strip()
            if name:
                items.append({"name": name, "quantity": quantity})
        
        # Nothing parsed: use the raw text
        if not items:
            items.append({"name": item_text, "quantity": 1})
        
        return items
    
    def _extract_date_from_text(self, text: str, reference_date: Optional[datetime] = None) -> str:
        """Extract date information from the raw text."""
        # Look for weekday keywords
        import re
        
        if reference_date is None:
            reference_date = datetime.now()
        
        # Find text segments containing a weekday name
        weekday_patterns = [
            r'預計出貨日[：:]?\s*([星期週禮拜]+[一二三四五六七日天末])',
            r'出貨日[：:]?\s*([星期週禮拜]+[一二三四五六七日天末])',
            r'發貨日期[：:]?\s*([星期週禮拜]+[一二三四五六七日天末])',
            r'送貨日期[：:]?\s*([星期週禮拜]+[一二三四五六七日天末])',
            r'([星期週禮拜]+[一二三四五六七日天末])',
        ]
        
        for pattern in weekday_patterns:
            match = re.search(pattern, text)
            if match:
                weekday_str = match.group(1) if len(match.groups()) > 0 else match.group(0)
                date_result = WeekdayConverter.parse_shipping_date(weekday_str, reference_date)
                if date_result:
                    return date_result
        
        return None
    
    def _generate_weekday_conversion_table(self, reference_date: datetime) -> str:
        """Build the weekday conversion table."""
        from ..weekday_converter import WeekdayConverter
        
        current_weekday = WeekdayConverter.get_weekday_name(reference_date)
        current_date_str = reference_date.strftime('%Y-%m-%d')
        
        weekdays = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
        
        result = f"Current date: {current_date_str} ({current_weekday})\n"
        result += "Weekday conversion table (星期幾轉換對照表):\n"
        
        for weekday in weekdays:
            converted_date = WeekdayConverter.get_next_weekday_date(weekday, reference_date)
            if converted_date:
                result += f"- {weekday} → {converted_date}\n"
        
        result += "\nAbsolute date conversion rules:\n"
        result += "- 9/20, 9-20, 9月20日, 10/15號 → 09-20, 10-15 (always MM-DD)\n"
        result += "- For an absolute date, convert the format directly; do not use the current date\n"
        
        return result


# Global instance for other modules to use
unified_parser = UnifiedOrderParser()