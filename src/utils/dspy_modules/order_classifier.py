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
        簡單的啟發式判斷是否包含多訂單
        """
        indicators = [
            '訂單1', '訂單2', '訂單3', '訂單4', '訂單5',
            'order1', 'order2', 'order3', 'order4', 'order5',
            '第一筆', '第二筆', '第三筆', '第四筆', '第五筆',
            '1.', '2.', '3.', '4.', '5.',
            '1)', '2)', '3)', '4)', '5)',
        ]
        
        text_lower = text.lower()
        indicator_count = sum(1 for indicator in indicators if indicator.lower() in text_lower)
        
        # 如果有2個或以上的指標，可能是多訂單
        return indicator_count >= 2