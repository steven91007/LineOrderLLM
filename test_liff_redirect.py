#!/usr/bin/env python3
"""
測試 LIFF 重定向修復
"""
import requests
import re

def test_liff_redirect_fix():
    """測試 LIFF OAuth 重定向修復"""
    
    print("🧪 測試 LIFF OAuth 重定向修復")
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
    
    # 2. 測試原始 LIFF URL（模擬從 LINE 點擊）
    liff_url = f"https://liff.line.me/2007889032-OolKDrp3?session={session_id}&state=session_{session_id}"
    print(f"\n2️⃣ LIFF URL (在 LINE 中使用):")
    print(f"   {liff_url}")
    
    # 3. 測試重定向後的 URL（模擬 OAuth 回調）
    redirect_url = f"https://9b0723f6edc9.ngrok-free.app/liff/edit?code=test&state=session_{session_id}&liffClientId=2007889032"
    print(f"\n3️⃣ OAuth 重定向後 URL:")
    print(f"   {redirect_url}")
    
    # 4. 測試前端頁面載入
    print(f"\n4️⃣ 測試前端頁面...")
    edit_response = requests.get(f"http://localhost:5001/liff/edit?session={session_id}")
    
    if edit_response.status_code == 200:
        # 檢查是否包含修復代碼
        if "preserveSessionId" in edit_response.text and "localStorage.setItem" in edit_response.text:
            print("✅ 前端修復代碼已部署")
        else:
            print("❌ 前端修復代碼未找到")
            
        # 檢查是否包含 redirectUri 修復
        if "redirectUri" in edit_response.text and "liff.login" in edit_response.text:
            print("✅ LIFF 登入重定向修復已部署")
        else:
            print("❌ LIFF 登入重定向修復未找到")
    else:
        print(f"❌ 前端頁面載入失敗: HTTP {edit_response.status_code}")
        
    # 5. 測試 API 端點
    print(f"\n5️⃣ 測試會話 API...")
    api_response = requests.get(f"http://localhost:5001/api/liff/orders/{session_id}")
    api_data = api_response.json()
    
    if api_data.get('success'):
        print(f"✅ 會話 API 正常: {api_data.get('total_orders', 0)} 筆訂單")
    else:
        print(f"❌ 會話 API 失敗: {api_data.get('error')}")
    
    print(f"\n🎯 **重要提醒**:")
    print(f"1. 請在 LINE Developers Console 設定 Authorized Redirect URLs:")
    print(f"   - https://9b0723f6edc9.ngrok-free.app/liff/edit")
    print(f"   - https://9b0723f6edc9.ngrok-free.app/liff/edit?*")
    print(f"   - https://liff.line.me/2007889032-OolKDrp3")
    print(f"")
    print(f"2. 測試方式:")
    print(f"   - 在 LINE 中輸入 #訂單 測試完整流程")
    print(f"   - 點擊編輯按鈕應該能正確保持會話ID")
    print(f"")
    print(f"3. 替代測試連結（無需登入）:")
    print(f"   https://9b0723f6edc9.ngrok-free.app/liff/simple?session={session_id}")
    
    return True

if __name__ == "__main__":
    test_liff_redirect_fix()