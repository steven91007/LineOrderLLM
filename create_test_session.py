#!/usr/bin/env python3
"""
創建測試會話並生成可用的編輯連結
"""
import sys
import os
import requests

# 添加路徑以便導入模組
sys.path.append('/home/ubuntu/LineOrderLLM')

from src.handlers.liff_handler import LIFFHandler

def create_test_session():
    """創建一個測試會話"""
    
    # 初始化LIFF處理器
    liff_handler = LIFFHandler()
    
    # 創建測試訂單數據
    test_orders = {
        'orders': [
            {
                'receiver_name': '測試客戶',
                'receiver_phone': '0912345678', 
                'shipping_address': '台北市大安區敦化南路二段216號',
                'items': [
                    {'name': '18A精美禮盒', 'quantity': 2},
                    {'name': '20A花束', 'quantity': 1}
                ],
                'shipping_date': '08-25',
                'sender_name': '花店小王',
                'sender_phone': '02-12345678'
            },
            {
                'receiver_name': '另一位客戶', 
                'receiver_phone': '0987654321',
                'shipping_address': '新北市板橋區中山路一段161號',
                'items': [
                    {'name': '16A蛋糕', 'quantity': 1}
                ],
                'shipping_date': '08-26',
                'sender_name': None,
                'sender_phone': None
            }
        ],
        'total_orders': 2
    }
    
    # 創建會話
    session_id = liff_handler.create_liff_session('test_user_complete', test_orders)
    
    return session_id, test_orders

def test_api_endpoints(session_id):
    """測試API端點"""
    base_url = "http://localhost:5001"
    
    print(f"🔍 測試 API 端點...")
    
    # 測試獲取訂單
    response = requests.get(f"{base_url}/api/liff/orders/{session_id}")
    if response.status_code == 200:
        data = response.json()
        if data.get('success'):
            print(f"✅ API 獲取訂單成功: {data.get('total_orders', 0)} 筆訂單")
            return True
        else:
            print(f"❌ API 返回錯誤: {data.get('error')}")
            return False
    else:
        print(f"❌ API 請求失敗: HTTP {response.status_code}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 創建訂單編輯測試會話")
    print("=" * 60)
    
    try:
        # 創建測試會話
        session_id, test_data = create_test_session()
        print(f"✅ 測試會話創建成功!")
        print(f"📋 會話 ID: {session_id}")
        print(f"📦 包含訂單: {test_data['total_orders']} 筆")
        
        # 測試API
        if test_api_endpoints(session_id):
            print(f"\n🌐 可用的編輯連結：")
            print(f"")
            print(f"1. 💻 簡化版編輯器 (推薦):")
            print(f"   https://9b0723f6edc9.ngrok-free.app/liff/simple?session={session_id}")
            print(f"")
            print(f"2. 📱 完整版編輯器 (需LIFF登入):")
            print(f"   https://9b0723f6edc9.ngrok-free.app/liff/edit?session={session_id}")
            print(f"")
            print(f"3. 🔗 LIFF URL (在LINE中使用):")
            print(f"   https://liff.line.me/2007889032-OolKDrp3?session={session_id}&state=session_{session_id}")
            print(f"")
            print("=" * 60)
            print("📝 測試步驟:")
            print("1. 複製上面的「簡化版編輯器」連結")
            print("2. 在瀏覽器中開啟 (任何瀏覽器都可以)")
            print("3. 修改訂單資訊 (收件人、地址、商品等)")
            print("4. 點擊「💾 儲存所有變更」")
            print("5. 確認看到成功訊息")
            print("=" * 60)
            
        else:
            print("❌ API 測試失敗，請檢查伺服器狀態")
            
    except Exception as e:
        print(f"❌ 創建測試會話失敗: {e}")
        import traceback
        traceback.print_exc()