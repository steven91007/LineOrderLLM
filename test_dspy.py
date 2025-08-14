#!/usr/bin/env python3
"""
DSPy 訂單解析功能測試腳本
"""
import os
import sys
import json
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 添加專案路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils.dspy_client import DSPyOrderClient


def test_single_order():
    """測試單一訂單解析"""
    print("=== 測試單一訂單解析 ===")
    
    # 初始化客戶端
    api_key = os.getenv('DSPY_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ 找不到 API Key，請設定 DSPY_API_KEY 或 OPENAI_API_KEY")
        return False
    
    client = DSPyOrderClient(api_key=api_key)
    
    # 測試案例
    test_cases = [
        {
            "name": "完整訂單（含寄件人）",
            "text": "寄件人：王小明 0912-345-678，收件人：李大華 0923-456-789，商品：手機殼 x2，發貨日：2025-01-20，地址：台北市信義區信義路五段7號"
        },
        {
            "name": "最小訂單（無寄件人）",
            "text": "收件人：陳小美 0934-567-890，商品：耳機 x1，地址：新北市板橋區文化路一段188號"
        }
    ]
    
    success_count = 0
    for i, case in enumerate(test_cases, 1):
        print(f"\n--- 測試案例 {i}: {case['name']} ---")
        print(f"輸入: {case['text']}")
        
        result = client.parse_order(case['text'])
        
        if result['success']:
            print("✅ 解析成功")
            print(f"結果: {json.dumps(result['data'], ensure_ascii=False, indent=2)}")
            success_count += 1
        else:
            print(f"❌ 解析失敗: {result['error']}")
    
    print(f"\n單一訂單測試結果: {success_count}/{len(test_cases)} 成功")
    return success_count == len(test_cases)


def test_multiple_orders():
    """測試多訂單解析"""
    print("\n=== 測試多訂單解析 ===")
    
    api_key = os.getenv('DSPY_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ 找不到 API Key")
        return False
    
    client = DSPyOrderClient(api_key=api_key)
    
    # 測試案例
    test_cases = [
        {
            "name": "2份訂單",
            "text": """
            訂單1: 收件人李大華 0923-456-789，商品手機殼 x2，地址台北市信義區信義路五段7號
            訂單2: 收件人陳小美 0934-567-890，商品耳機 x1，地址新北市板橋區文化路一段188號
            """
        },
        {
            "name": "3份訂單",
            "text": """
            第一筆：收件人王大明 0945-678-901，商品平板保護貼 x3，地址台中市西屯區台灣大道三段99號
            第二筆：收件人張小華 0956-789-012，商品充電線 x2，地址高雄市前金區中正四路211號
            第三筆：收件人劉小芳 0967-890-123，商品藍牙喇叭 x1，地址台南市中西區民族路二段76號
            """
        }
    ]
    
    success_count = 0
    for i, case in enumerate(test_cases, 1):
        print(f"\n--- 測試案例 {i}: {case['name']} ---")
        print(f"輸入: {case['text'].strip()}")
        
        result = client.parse_order(case['text'])
        
        if result['success']:
            data = result['data']
            if data.get('order_type') == 'multiple':
                print(f"✅ 解析成功，發現 {data.get('total_orders', 0)} 份訂單")
                for j, order in enumerate(data.get('orders', []), 1):
                    print(f"  訂單 {j}: {order.get('receiver_name')} - {len(order.get('items', []))} 項商品")
                success_count += 1
            else:
                print(f"⚠️ 被識別為單一訂單而非多訂單")
        else:
            print(f"❌ 解析失敗: {result['error']}")
    
    print(f"\n多訂單測試結果: {success_count}/{len(test_cases)} 成功")
    return success_count == len(test_cases)


def test_error_handling():
    """測試錯誤處理"""
    print("\n=== 測試錯誤處理 ===")
    
    api_key = os.getenv('DSPY_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ 找不到 API Key")
        return False
    
    client = DSPyOrderClient(api_key=api_key)
    
    # 測試案例
    test_cases = [
        {
            "name": "空字串",
            "text": ""
        },
        {
            "name": "無相關資訊",
            "text": "今天天氣真好"
        },
        {
            "name": "過多訂單（6份）",
            "text": """
            訂單1: 收件人A 0911111111，商品A x1，地址地址A
            訂單2: 收件人B 0922222222，商品B x1，地址地址B
            訂單3: 收件人C 0933333333，商品C x1，地址地址C
            訂單4: 收件人D 0944444444，商品D x1，地址地址D
            訂單5: 收件人E 0955555555，商品E x1，地址地址E
            訂單6: 收件人F 0966666666，商品F x1，地址地址F
            """
        }
    ]
    
    handled_count = 0
    for i, case in enumerate(test_cases, 1):
        print(f"\n--- 錯誤測試 {i}: {case['name']} ---")
        
        result = client.parse_order(case['text'])
        
        if not result['success']:
            print(f"✅ 正確處理錯誤: {result['error']}")
            if result.get('suggestion') == 'single_order':
                print("✅ 正確建議單筆輸入")
            handled_count += 1
        else:
            print("⚠️ 意外成功解析了錯誤輸入")
    
    print(f"\n錯誤處理測試結果: {handled_count}/{len(test_cases)} 正確處理")
    return handled_count >= 2  # 至少處理大部分錯誤情況


def main():
    """主測試函數"""
    print("🧪 DSPy 訂單解析功能測試")
    print("=" * 50)
    
    # 檢查環境
    api_key = os.getenv('DSPY_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ 測試失敗：未找到 API Key")
        print("請設定環境變數 DSPY_API_KEY 或 OPENAI_API_KEY")
        return False
    
    # 執行測試
    tests = [
        ("單一訂單", test_single_order),
        ("多訂單", test_multiple_orders),
        ("錯誤處理", test_error_handling)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name}測試發生異常: {e}")
            results.append((test_name, False))
    
    # 輸出總結
    print("\n" + "=" * 50)
    print("📊 測試總結")
    print("=" * 50)
    
    success_count = sum(1 for _, success in results if success)
    total_tests = len(results)
    
    for test_name, success in results:
        status = "✅ 通過" if success else "❌ 失敗"
        print(f"{test_name}: {status}")
    
    print(f"\n總體結果: {success_count}/{total_tests} 測試通過")
    
    if success_count == total_tests:
        print("🎉 所有測試通過！DSPy 客戶端運作正常")
        return True
    else:
        print("⚠️ 部分測試失敗，請檢查實作")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)