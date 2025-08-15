"""
測試 postback 處理修復
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.handlers.order_handler import OrderHandler
from unittest.mock import Mock, MagicMock
import json

# 建立模擬的 OrderHandler
configuration = Mock()
order_handler = OrderHandler(
    configuration=configuration,
    authorized_users=['test_user'],
    client_type='dspy',
    openai_api_key='test_key'
)

# 模擬 postback 事件
mock_event = Mock()
mock_event.source.user_id = 'test_user'
mock_event.postback.data = json.dumps({"action": "confirm_all_orders_batch"})
mock_event.reply_token = 'test_token'

# 設置測試訂單資料
test_orders = {
    'orders': [
        {
            'sender_name': '徐奇檍',
            'sender_phone': '091767778',
            'receiver_name': '張志文',
            'receiver_phone': '0981768',
            'items': [{'name': '18A禮盒', 'quantity': 4}],
            'shipping_address': '桃園市中壢區文化二路273巷'
        }
    ]
}

# 模擬 session 資料
order_handler.order_sessions = {
    'test_user': {
        'status': 'confirming',
        'data': {
            'parsed': test_orders
        }
    }
}

# 模擬 _reply_text 方法
order_handler._reply_text = Mock()

print("測試 confirm_all_orders_batch 方法...")
print("=" * 50)

try:
    # 測試沒有 Google Sheets 客戶端的情況
    order_handler.sheets_client = None
    order_handler._confirm_all_orders_batch(mock_event)
    
    print("測試成功！沒有發生 'result' 變數錯誤")
    
    # 檢查是否有呼叫 reply_text
    if order_handler._reply_text.called:
        print("成功回覆訊息")
        call_args = order_handler._reply_text.call_args
        if call_args:
            message = call_args[0][1] if len(call_args[0]) > 1 else "無訊息"
            print(f"回覆內容預覽：{message[:100]}...")
    
    # 檢查 session 是否被清除
    if 'test_user' not in order_handler.order_sessions:
        print("會話狀態已正確清除")
    
except Exception as e:
    print(f"測試失敗：{e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 50)
print("測試完成！")