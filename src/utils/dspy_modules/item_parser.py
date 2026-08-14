"""
商品項目解析 DSPy 模組
"""
import dspy
import json
from typing import Dict, Any, List


class ItemParserSignature(dspy.Signature):
    """商品項目解析 Signature
    
    解析商品文字為結構化的商品項目：
    - 保留產品編號（如：18A、16A、20A 等）
    - 識別商品名稱（如：禮盒、蛋糕、花束等）
    - 解析數量
    - 處理各種描述格式
    """
    item_text = dspy.InputField(desc="原始商品文字，可能包含多個商品或不同格式")
    items_json = dspy.OutputField(desc="解析後的商品陣列 JSON，格式：[{\"name\": \"商品名稱\", \"quantity\": 數量}]，必須保留數字編號如 18A、16A")


class ItemParser(dspy.Module):
    """商品項目解析模組"""
    
    def __init__(self):
        super().__init__()
        self.parse = dspy.ChainOfThought(ItemParserSignature)
        
        # 建立 Few-shot 範例
        self.examples = [
            dspy.Example(
                item_text="18A禮盒 x2",
                items_json='[{"name": "18A禮盒", "quantity": 2}]'
            ).with_inputs("item_text"),
            
            dspy.Example(
                item_text="18A禮盒 *4",
                items_json='[{"name": "18A禮盒", "quantity": 4}]'
            ).with_inputs("item_text"),
            
            dspy.Example(
                item_text="16A蛋糕一個",
                items_json='[{"name": "16A蛋糕", "quantity": 1}]'
            ).with_inputs("item_text"),
            
            dspy.Example(
                item_text="20A花束 2束",
                items_json='[{"name": "20A花束", "quantity": 2}]'
            ).with_inputs("item_text"),
            
            dspy.Example(
                item_text="18A禮盒 x1, 16A蛋糕 x3",
                items_json='[{"name": "18A禮盒", "quantity": 1}, {"name": "16A蛋糕", "quantity": 3}]'
            ).with_inputs("item_text"),
            
            dspy.Example(
                item_text="12A巧克力禮盒",
                items_json='[{"name": "12A巧克力禮盒", "quantity": 1}]'
            ).with_inputs("item_text"),
            
            dspy.Example(
                item_text="24A生日蛋糕兩個",
                items_json='[{"name": "24A生日蛋糕", "quantity": 2}]'
            ).with_inputs("item_text"),
            
            dspy.Example(
                item_text="10A小禮盒 3盒, 15A中禮盒 1盒",
                items_json='[{"name": "10A小禮盒", "quantity": 3}, {"name": "15A中禮盒", "quantity": 1}]'
            ).with_inputs("item_text"),
            
            dspy.Example(
                item_text="鳳梨酥禮盒 x2",
                items_json='[{"name": "鳳梨酥禮盒", "quantity": 2}]'
            ).with_inputs("item_text"),
            
            dspy.Example(
                item_text="18A特製禮盒(客製包裝) x1",
                items_json='[{"name": "18A特製禮盒(客製包裝)", "quantity": 1}]'
            ).with_inputs("item_text")
        ]
    
    def forward(self, item_text: str) -> dspy.Prediction:
        """
        解析商品項目
        
        Args:
            item_text: 原始商品文字
            
        Returns:
            dspy.Prediction: 包含 items_json (string)
        """
        if not item_text or not isinstance(item_text, str):
            return dspy.Prediction(items_json='[]')
        
        # 預處理：移除多餘空白
        cleaned_text = ' '.join(item_text.split())
        
        try:
            # 使用 DSPy 進行商品解析
            result = self.parse(item_text=cleaned_text)
            
            # 驗證 JSON 格式
            parsed_json = result.items_json
            if isinstance(parsed_json, str):
                # 確保是有效的 JSON
                items = json.loads(parsed_json)
                if not isinstance(items, list):
                    raise ValueError("Items should be a list")
                
                # 驗證每個項目的格式
                for item in items:
                    if not isinstance(item, dict) or 'name' not in item or 'quantity' not in item:
                        raise ValueError("Invalid item format")
                    
                    # 確保數量是數字
                    if not isinstance(item['quantity'], (int, float)) or item['quantity'] <= 0:
                        raise ValueError("Invalid quantity")
                
                return dspy.Prediction(items_json=parsed_json)
            else:
                # 如果直接返回了 list，轉為 JSON string
                return dspy.Prediction(items_json=json.dumps(parsed_json, ensure_ascii=False))
                
        except Exception as e:
            # AI 失敗時的 fallback
            return dspy.Prediction(items_json=self._fallback_parse(cleaned_text))
    
    def _fallback_parse(self, item_text: str) -> str:
        """簡單的 fallback 商品解析"""
        import re
        
        # 嘗試用規則解析
        items = []
        
        # 分割多個商品（用逗號、分號等分隔）
        parts = re.split(r'[,，;；\n]', item_text)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 提取數量
            quantity = 1
            quantity_patterns = [
                r'\*\s*(\d+)',  # 支援 *4 格式
                r'x\s*(\d+)',
                r'(\d+)\s*[個盒束份張袋包]',
                r'(\d+)\s*$',
                r'[一二三四五六七八九十]\s*[個盒束份張袋包]'
            ]
            
            for pattern in quantity_patterns:
                match = re.search(pattern, part, re.IGNORECASE)
                if match:
                    if pattern.endswith('[個盒束份張袋包]'):
                        # 中文數字轉換
                        chinese_nums = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, 
                                      '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
                        chinese_num = match.group(0).strip()[:-1]
                        quantity = chinese_nums.get(chinese_num, 1)
                    else:
                        try:
                            quantity = int(match.group(1))
                        except:
                            quantity = 1
                    # 移除數量部分
                    part = re.sub(pattern, '', part, flags=re.IGNORECASE).strip()
                    break
            
            # 清理商品名稱
            name = part.strip()
            if name:
                items.append({"name": name, "quantity": quantity})
        
        # 如果沒有解析出任何商品，使用原始文字
        if not items:
            items = [{"name": item_text, "quantity": 1}]
        
        return json.dumps(items, ensure_ascii=False)


# 建立全域實例供其他模組使用  
item_parser = ItemParser()