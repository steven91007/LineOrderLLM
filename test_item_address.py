#!/usr/bin/env python3
"""
測試地址標準化和商品解析功能
"""
import os
import dspy
from src.utils.taiwan_address import TaiwanAddressNormalizer
from src.utils.dspy_modules.item_parser import item_parser

def setup_dspy():
    """設定 DSPy"""
    # 從環境變數讀取 API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("請設定 OPENAI_API_KEY 環境變數")
        return False
    
    # 配置 DSPy
    lm = dspy.LM(
        model="gpt-4o-mini",
        api_key=api_key,
        max_tokens=1000,
        temperature=0.1
    )
    dspy.settings.configure(lm=lm)
    return True

def test_address_with_notes():
    """測試帶備註的地址標準化"""
    if not setup_dspy():
        return
    
    print("=" * 60)
    print("測試地址標準化（保留備註）：")
    print("=" * 60)
    
    normalizer = TaiwanAddressNormalizer(use_ai=True)
    
    test_cases = [
        "士林區文林路100號(台積電工地)",
        "桃園縣中壢市中大路300號(中原大學)",
        "板橋區文化路100號(遠東百貨)",
        "信義區市府路1號(台北101大樓)",
        "高雄縣鳳山市光復路132號(建築工地)",
        "台中豐原中正路50號(麥當勞)",
        "中壢中大路500號(家樂福)"
    ]
    
    for address in test_cases:
        print(f"\n原始地址: {address}")
        try:
            result = normalizer.normalize_address(address)
            print(f"標準化後: {result}")
        except Exception as e:
            print(f"處理失敗: {e}")

def test_item_parsing():
    """測試商品項目解析"""
    if not setup_dspy():
        return
    
    print("\n" + "=" * 60)
    print("測試商品項目解析（保留數字編號）：")
    print("=" * 60)
    
    test_cases = [
        "18A禮盒 x2",
        "16A蛋糕一個",
        "20A花束 2束",
        "18A禮盒 x1, 16A蛋糕 x3",
        "12A巧克力禮盒",
        "24A生日蛋糕兩個",
        "10A小禮盒 3盒, 15A中禮盒 1盒",
        "18A特製禮盒(客製包裝) x1",
        "25A頂級禮盒, 12A小點心盒子三個",
        "鳳梨酥禮盒 x2",  # 沒有數字編號的情況
        "30A超大禮盒(VIP專用) 1盒"
    ]
    
    for item_text in test_cases:
        print(f"\n原始商品: {item_text}")
        try:
            result = item_parser(item_text)
            print(f"解析結果: {result.items_json}")
        except Exception as e:
            print(f"處理失敗: {e}")

def test_combined_scenario():
    """測試完整訂單場景"""
    if not setup_dspy():
        return
    
    print("\n" + "=" * 60)
    print("測試完整訂單場景：")
    print("=" * 60)
    
    normalizer = TaiwanAddressNormalizer(use_ai=True)
    
    scenarios = [
        {
            "address": "士林區文林路100號(台積電工地)",
            "items": "18A禮盒 x2, 16A蛋糕 x1"
        },
        {
            "address": "桃園縣中壢市中大路300號(中原大學)",
            "items": "24A生日蛋糕(客製化) 一個"
        },
        {
            "address": "板橋區文化路100號(遠東百貨)",
            "items": "12A小禮盒 3盒, 鳳梨酥 2盒"
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n--- 場景 {i} ---")
        print(f"原始地址: {scenario['address']}")
        print(f"原始商品: {scenario['items']}")
        
        try:
            # 處理地址
            normalized_address = normalizer.normalize_address(scenario['address'])
            print(f"標準化地址: {normalized_address}")
            
            # 處理商品
            parsed_items = item_parser(scenario['items'])
            print(f"解析商品: {parsed_items.items_json}")
            
        except Exception as e:
            print(f"處理失敗: {e}")

if __name__ == "__main__":
    test_address_with_notes()
    test_item_parsing() 
    test_combined_scenario()