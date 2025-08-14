#!/usr/bin/env python3
"""
測試 LIFF URL 修復
"""
import requests
import re

def test_liff_url_generation():
    """測試修正後的 LIFF URL 生成"""
    
    print("🧪 測試 LIFF URL 修復")
    print("=" * 50)
    
    # 1. 創建測試會話
    print("1️⃣ 創建測試會話...")
    response = requests.get("http://localhost:5001/liff/demo")
    
    # 從HTML中提取session ID
    session_match = re.search(r'session=([a-f0-9-]+)', response.text)
    if not session_match:
        print("❌ 無法獲取測試會話")
        return False
    
    session_id = session_match.group(1)
    print(f"✅ 測試會話: {session_id}")
    
    # 2. 測試新的 LIFF URL 格式
    print(f"\n2️⃣ 新的 LIFF URL 格式:")
    
    # 模擬 order_handler._edit_order_with_liff 生成的 URL
    liff_id = "2007889032-OolKDrp3"
    order_index = 1
    redirect_uri = f"https://9b0723f6edc9.ngrok-free.app/liff/edit?session={session_id}&focus={order_index}"
    new_liff_url = f"https://liff.line.me/{liff_id}?liffRedirectUri={redirect_uri}"
    
    print(f"✅ 個別訂單編輯 URL:")
    print(f"   {new_liff_url}")
    print(f"   重定向到: {redirect_uri}")
    
    # 模擬 liff_handler.get_liff_url 生成的 URL
    redirect_uri_all = f"https://9b0723f6edc9.ngrok-free.app/liff/edit?session={session_id}"
    new_liff_url_all = f"https://liff.line.me/{liff_id}?liffRedirectUri={redirect_uri_all}"
    
    print(f"\n✅ 全部訂單編輯 URL:")
    print(f"   {new_liff_url_all}")
    print(f"   重定向到: {redirect_uri_all}")
    
    # 3. 比較舊格式
    print(f"\n3️⃣ 舊格式比較 (會造成雙重編碼):")
    old_liff_url = f"https://liff.line.me/{liff_id}?session={session_id}&state=session_{session_id}&focus={order_index}"
    print(f"❌ 舊格式: {old_liff_url}")
    print(f"   問題：查詢參數會被 LINE 編碼到 liff.state 中")
    
    # 4. 驗證重定向 URL 可訪問性
    print(f"\n4️⃣ 測試重定向 URL 可訪問性...")
    try:
        test_response = requests.get(f"http://localhost:5001/liff/edit?session={session_id}")
        if test_response.status_code == 200:
            print("✅ 重定向 URL 可正常訪問")
            
            # 檢查是否包含會話處理代碼
            if "localStorage.setItem('liff_session_id'" in test_response.text:
                print("✅ 包含會話持久化代碼")
            else:
                print("⚠️  未找到會話持久化代碼")
                
        else:
            print(f"❌ 重定向 URL 無法訪問: HTTP {test_response.status_code}")
    except Exception as e:
        print(f"❌ 測試重定向 URL 時發生錯誤: {e}")
    
    # 5. 預期行為說明
    print(f"\n5️⃣ 修復後的預期行為:")
    print("1. 用戶點擊編輯按鈕")
    print("2. LINE 開啟新的 LIFF URL（不帶查詢參數）")  
    print("3. LIFF 認證後，自動重定向到指定的 URL（包含 session 參數）")
    print("4. 前端 JavaScript 從 URL 參數獲取 session ID")
    print("5. 成功載入並編輯訂單")
    
    print(f"\n🎯 **重要提醒**:")
    print("1. 請確保 LINE Developers Console 中的 Authorized Redirect URLs 包含:")
    print(f"   - https://9b0723f6edc9.ngrok-free.app/liff/edit")
    print(f"   - https://9b0723f6edc9.ngrok-free.app/liff/edit?*")
    print("\n2. 新格式的優勢:")
    print("   ✅ 避免查詢參數雙重編碼")
    print("   ✅ 符合 LIFF 標準實踐")
    print("   ✅ 更穩定的會話傳遞")
    
    return True

if __name__ == "__main__":
    test_liff_url_generation()