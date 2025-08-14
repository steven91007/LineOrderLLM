#!/usr/bin/env python3
"""
測試 LIFF 編輯器完整流程
"""
import requests
import json
import time

BASE_URL = "http://localhost:5001"

def test_liff_flow():
    print("🧪 開始測試 LIFF 編輯器流程")
    
    # Step 1: 創建一個demo會話
    print("\n1️⃣ 創建 Demo 會話...")
    response = requests.get(f"{BASE_URL}/liff/demo")
    
    # 從HTML中提取session ID
    import re
    session_match = re.search(r'session=([a-f0-9-]+)', response.text)
    if not session_match:
        print("❌ 無法從demo頁面獲取session ID")
        return False
    
    session_id = session_match.group(1)
    print(f"✅ 獲得會話ID: {session_id}")
    
    # Step 2: 驗證會話存在
    print(f"\n2️⃣ 驗證會話 {session_id}...")
    api_response = requests.get(f"{BASE_URL}/api/liff/orders/{session_id}")
    api_data = api_response.json()
    
    if not api_data.get('success'):
        print(f"❌ 會話驗證失敗: {api_data.get('error')}")
        return False
    
    print(f"✅ 會話驗證成功，包含 {api_data.get('total_orders', 0)} 筆訂單")
    print(f"   原始訂單: {api_data['orders'][0]['receiver_name']} - {api_data['orders'][0]['shipping_address']}")
    
    # Step 3: 模擬編輯訂單
    print(f"\n3️⃣ 模擬編輯訂單...")
    original_orders = api_data['orders']
    
    # 修改訂單資料
    modified_orders = []
    for order in original_orders:
        modified_order = order.copy()
        modified_order['receiver_name'] = "李小華"
        modified_order['receiver_phone'] = "0987654321"
        modified_order['shipping_address'] = "新北市板橋區文化路一段100號"
        modified_order['items'] = [
            {"name": "20A花束", "quantity": 1},
            {"name": "16A蛋糕", "quantity": 2}
        ]
        modified_order['shipping_date'] = "08-20"
        modified_orders.append(modified_order)
    
    # Step 4: 發送更新請求
    print(f"\n4️⃣ 發送訂單更新...")
    update_data = {
        "user_id": api_data.get('user_id', 'test_user'),
        "orders": modified_orders
    }
    
    update_response = requests.put(
        f"{BASE_URL}/api/liff/orders/{session_id}",
        headers={'Content-Type': 'application/json'},
        data=json.dumps(update_data)
    )
    
    update_result = update_response.json()
    
    if not update_result.get('success'):
        print(f"❌ 訂單更新失敗: {update_result.get('error')}")
        return False
    
    print(f"✅ 訂單更新成功!")
    print(f"   更新後訂單: {modified_orders[0]['receiver_name']} - {modified_orders[0]['shipping_address']}")
    
    # Step 5: 驗證LIFF編輯頁面可以載入
    print(f"\n5️⃣ 測試 LIFF 編輯頁面載入...")
    
    # 創建新的會話用於測試頁面載入
    demo_response = requests.get(f"{BASE_URL}/liff/demo")
    new_session_match = re.search(r'session=([a-f0-9-]+)', demo_response.text)
    
    if new_session_match:
        new_session_id = new_session_match.group(1)
        edit_response = requests.get(f"{BASE_URL}/liff/edit?session={new_session_id}")
        
        if edit_response.status_code == 200 and "訂單編輯" in edit_response.text:
            print(f"✅ LIFF 編輯頁面載入成功")
        else:
            print(f"❌ LIFF 編輯頁面載入失敗")
            return False
    
    print(f"\n🎉 所有測試通過！LIFF 編輯器流程正常運作")
    return True

def create_simple_test_session():
    """創建一個簡單的測試會話，繞過LIFF登入問題"""
    print("\n🔧 創建簡化測試會話...")
    
    # 直接通過Flask應用創建會話
    import sys
    import os
    sys.path.append('/home/ubuntu/LineOrderLLM')
    
    from src.handlers.liff_handler import LIFFHandler
    
    liff_handler = LIFFHandler()
    
    # 創建測試訂單數據
    test_orders = {
        'orders': [
            {
                'receiver_name': '測試用戶',
                'receiver_phone': '0912345678',
                'shipping_address': '台北市中正區重慶南路一段122號',
                'items': [
                    {'name': '18A禮盒', 'quantity': 1}
                ],
                'shipping_date': '08-15',
                'sender_name': None,
                'sender_phone': None
            }
        ],
        'total_orders': 1
    }
    
    session_id = liff_handler.create_liff_session('test_user_direct', test_orders)
    
    print(f"✅ 直接創建會話成功: {session_id}")
    
    # 生成測試URL
    test_url = f"http://localhost:5001/liff/edit?session={session_id}"
    print(f"🔗 測試URL: {test_url}")
    
    # 生成LIFF URL
    liff_url = f"https://liff.line.me/2007889032-OolKDrp3?session={session_id}&state=session_{session_id}"
    print(f"🌐 LIFF URL: {liff_url}")
    
    return session_id

if __name__ == "__main__":
    print("=" * 50)
    print("LIFF 編輯器完整流程測試")
    print("=" * 50)
    
    # 基礎流程測試
    success = test_liff_flow()
    
    if success:
        # 創建簡化測試會話
        test_session = create_simple_test_session()
        print(f"\n✨ 你可以使用這個會話ID進行測試: {test_session}")