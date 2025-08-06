"""
訂單類型識別模組
"""
import dspy
from .signatures import OrderTypeSignature


class OrderTypeClassifier(dspy.Module):
    """識別訂單類型：單一或多訂單"""
    
    def __init__(self):
        super().__init__()
        self.classify = dspy.ChainOfThought(OrderTypeSignature)
    
    def forward(self, order_text: str) -> dspy.Prediction:
        """
        識別訂單類型
        
        Args:
            order_text: 原始訂單文字
            
        Returns:
            dspy.Prediction: 包含 order_type ('single' 或 'multiple')
        """
        # 使用 DSPy 進行推理
        result = self.classify(order_text=order_text)
        
        # 後處理：確保回應格式正確
        order_type = result.order_type.lower().strip()
        
        # 驗證回應
        if order_type not in ['single', 'multiple']:
            # 預設判斷邏輯
            if self._contains_multiple_orders(order_text):
                order_type = 'multiple'
            else:
                order_type = 'single'
        
        return dspy.Prediction(order_type=order_type)
    
    def _contains_multiple_orders(self, text: str) -> bool:
        """
        判斷是否包含多訂單（多個收件人或多個地址）
        """
        import re
        
        # 檢查關鍵字出現次數
        receiver_count = len(re.findall(r'收件人', text))
        address_count = len(re.findall(r'地址|收件地址|送[到至]', text))
        phone_count = len(re.findall(r'電話|手機|聯絡', text))
        
        # 檢查序號標記
        numbering_patterns = [
            r'^\s*[1-5][.、）]\s*',
            r'\n\s*[1-5][.、）]\s*',
            r'^\s*[一二三四五][、.）]\s*',
            r'\n\s*[一二三四五][、.）]\s*'
        ]
        has_numbering = sum(1 for pattern in numbering_patterns if re.search(pattern, text, re.MULTILINE)) >= 2
        
        # 判斷邏輯
        if receiver_count >= 2 or address_count >= 2:
            return True
            
        if has_numbering and (receiver_count >= 1 or address_count >= 1):
            return True
            
        if receiver_count >= 2 and phone_count >= 2:
            return True
        
        return False