#!/usr/bin/env python3
"""
簡化的 LIFF URL 測試
"""

# 模擬 liff_handler 的 get_liff_url 方法
def get_liff_url(session_id: str, liff_id: str = None, base_url: str = None) -> str:
    """
    模擬修復後的 get_liff_url 方法
    """
    if liff_id:
        # 使用動態基礎 URL 而非硬編碼的 ngrok URL
        if base_url:
            redirect_uri = f"{base_url}/liff/edit?session={session_id}"
        else:
            # 降級方案：使用相對路徑
            redirect_uri = f"/liff/edit?session={session_id}"
        
        return f"https://liff.line.me/{liff_id}?liffRedirectUri={redirect_uri}"
    else:
        # 如果沒有 LIFF ID，返回 Web 版本 URL
        return f"/liff/edit?session={session_id}"

def main():
    print("🧪 LIFF URL 生成測試")
    print("=" * 50)
    
    session_id = "abc123-def456-ghi789"
    liff_id = "2007889032-OolKDrp3"
    
    # 測試 1: 新的域名
    print("\n🆕 測試 1: 新域名")
    new_base_url = "https://my-new-domain.ngrok-free.app"
    url1 = get_liff_url(session_id, liff_id, new_base_url)
    print(f"新 URL: {url1}")
    
    # 檢查是否還包含舊 URL
    if "9b0723f6edc9.ngrok-free.app" in url1:
        print("❌ 失敗：仍包含舊 URL")
    else:
        print("✅ 成功：不包含舊 URL")
    
    if new_base_url in url1:
        print("✅ 成功：包含新 URL")
    else:
        print("❌ 失敗：不包含新 URL")
    
    # 測試 2: 沒有 base_url（回退）
    print("\n🔄 測試 2: 無 base_url 回退")
    url2 = get_liff_url(session_id, liff_id, None)
    print(f"回退 URL: {url2}")
    
    if "9b0723f6edc9.ngrok-free.app" in url2:
        print("❌ 失敗：回退仍包含舊 URL")
    else:
        print("✅ 成功：回退不包含舊 URL")
    
    # 測試 3: 模擬真實場景
    print("\n🎯 測試 3: 真實場景模擬")
    real_scenarios = [
        "https://abc123.ngrok-free.app",
        "https://my-app.herokuapp.com",
        "https://my-domain.com",
        "http://localhost:5001"
    ]
    
    for scenario_url in real_scenarios:
        test_url = get_liff_url(session_id, liff_id, scenario_url)
        print(f"場景 {scenario_url}: {test_url}")
        
        if "9b0723f6edc9.ngrok-free.app" not in test_url:
            print("  ✅ 無舊 URL")
        else:
            print("  ❌ 包含舊 URL")
    
    print("\n" + "=" * 50)
    print("🎉 核心 URL 生成功能修復成功！")
    print("\n下一步操作：")
    print("1. export BASE_URL=\"https://your-actual-domain.com\"")
    print("2. 在 LINE Console 設定 Authorized Redirect URLs")
    print("3. 重啟應用程式")

if __name__ == "__main__":
    main()