#!/usr/bin/env python3
"""
測試 LIFF URL 修復是否成功
"""
import os
import sys
sys.path.append('/home/ubuntu/LineOrderLLM/src')

from handlers.liff_handler import LIFFHandler

def test_url_generation():
    """測試 URL 生成功能"""
    print("🧪 測試 LIFF URL 生成功能")
    print("=" * 50)
    
    # 創建 LIFF Handler
    liff_handler = LIFFHandler()
    
    # 測試場景 1：有 base_url 的情況
    print("\n📋 測試場景 1: 有 base_url")
    session_id = "test-session-123"
    liff_id = "2007889032-OolKDrp3"
    base_url = "https://new-domain.ngrok-free.app"
    
    liff_url = liff_handler.get_liff_url(session_id, liff_id, base_url)
    print(f"Session ID: {session_id}")
    print(f"LIFF ID: {liff_id}")
    print(f"Base URL: {base_url}")
    print(f"生成的 LIFF URL: {liff_url}")
    
    # 驗證 URL 不包含舊的 ngrok URL
    if "9b0723f6edc9.ngrok-free.app" in liff_url:
        print("❌ 失敗：仍然包含舊的 ngrok URL！")
        return False
    else:
        print("✅ 成功：不包含舊的 ngrok URL")
    
    # 驗證 URL 包含新的 base_url
    if base_url in liff_url:
        print("✅ 成功：包含新的 base URL")
    else:
        print("❌ 失敗：不包含新的 base URL")
        return False
    
    # 測試場景 2：沒有 base_url 的情況（降級）
    print("\n📋 測試場景 2: 沒有 base_url（降級處理）")
    liff_url_fallback = liff_handler.get_liff_url(session_id, liff_id, None)
    print(f"降級的 LIFF URL: {liff_url_fallback}")
    
    # 驗證降級 URL 不包含舊的 ngrok URL
    if "9b0723f6edc9.ngrok-free.app" in liff_url_fallback:
        print("❌ 失敗：降級 URL 仍然包含舊的 ngrok URL！")
        return False
    else:
        print("✅ 成功：降級 URL 不包含舊的 ngrok URL")
    
    # 測試場景 3：沒有 LIFF ID 的情況
    print("\n📋 測試場景 3: 沒有 LIFF ID")
    web_url = liff_handler.get_liff_url(session_id, None, base_url)
    print(f"Web 版本 URL: {web_url}")
    
    if "9b0723f6edc9.ngrok-free.app" in web_url:
        print("❌ 失敗：Web URL 包含舊的 ngrok URL！")
        return False
    else:
        print("✅ 成功：Web URL 不包含舊的 ngrok URL")
    
    return True

def test_order_handler_integration():
    """測試與 OrderHandler 的整合"""
    print("\n🔗 測試 OrderHandler 整合")
    print("=" * 50)
    
    try:
        from handlers.order_handler import OrderHandler
        
        # 創建測試配置
        class MockConfiguration:
            pass
        
        config = MockConfiguration()
        
        # 測試 OrderHandler 初始化
        order_handler = OrderHandler(
            configuration=config,
            authorized_users=['test_user'],
            client_type='dspy',
            openai_api_key='test_key',
            liff_id="2007889032-OolKDrp3",
            base_url="https://new-domain.ngrok-free.app"
        )
        
        print("✅ OrderHandler 初始化成功")
        print(f"Base URL: {order_handler.base_url}")
        print(f"LIFF ID: {order_handler.liff_id}")
        
        return True
        
    except Exception as e:
        print(f"❌ OrderHandler 測試失敗: {e}")
        return False

def check_hardcoded_urls():
    """檢查是否還有硬編碼的舊 URL"""
    print("\n🔍 檢查硬編碼 URL")
    print("=" * 50)
    
    import subprocess
    
    try:
        result = subprocess.run([
            'grep', '-r', '9b0723f6edc9.ngrok-free.app', 'src/'
        ], capture_output=True, text=True, cwd='/home/ubuntu/LineOrderLLM')
        
        if result.returncode == 0:
            print("❌ 發現硬編碼的舊 URL:")
            print(result.stdout)
            return False
        else:
            print("✅ src/ 目錄中沒有發現硬編碼的舊 URL")
            return True
            
    except Exception as e:
        print(f"檢查時發生錯誤: {e}")
        return False

def main():
    """主測試函數"""
    print("🚀 開始測試 LIFF URL 修復")
    print("=" * 60)
    
    all_tests_passed = True
    
    # 測試 1: URL 生成
    if not test_url_generation():
        all_tests_passed = False
    
    # 測試 2: OrderHandler 整合
    if not test_order_handler_integration():
        all_tests_passed = False
    
    # 測試 3: 硬編碼 URL 檢查
    if not check_hardcoded_urls():
        all_tests_passed = False
    
    print("\n" + "=" * 60)
    if all_tests_passed:
        print("🎉 所有測試通過！LIFF URL 修復成功！")
        print("\n下一步：")
        print("1. 設定正確的 BASE_URL 環境變數")
        print("2. 在 LINE Developers Console 設定 Authorized Redirect URLs")
        print("3. 重啟應用程式")
    else:
        print("❌ 部分測試失敗，需要進一步修復")
    
    return all_tests_passed

if __name__ == "__main__":
    main()