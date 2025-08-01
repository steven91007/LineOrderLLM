#!/usr/bin/env python3
"""
測試台灣地址標準化功能
"""
from src.utils.taiwan_address import TaiwanAddressNormalizer


def test_address_normalization():
    """測試地址標準化"""
    normalizer = TaiwanAddressNormalizer()
    
    test_cases = [
        # 測試區域補全
        ("士林區文林路100號", "臺北市士林區文林路100號"),
        ("中壢區中大路300號", "桃園市中壢區中大路300號"),
        ("大安區羅斯福路四段1號", "臺北市大安區羅斯福路四段1號"),
        
        # 測試舊地名更新
        ("桃園縣中壢市中大路300號", "桃園市中壢區中大路300號"),
        ("台中縣豐原市中正路1號", "臺中市豐原區中正路1號"),
        ("台南縣永康市中正路529號", "臺南市永康區中正路529號"),
        ("高雄縣鳳山市光復路二段132號", "高雄市鳳山區光復路二段132號"),
        
        # 測試台→臺轉換
        ("台北市信義區信義路五段7號", "臺北市信義區信義路五段7號"),
        ("台中市西屯區台灣大道三段99號", "臺中市西屯區臺灣大道三段99號"),
        
        # 測試完整地址
        ("新北市板橋區文化路一段100號", "新北市板橋區文化路一段100號"),
        ("桃園市桃園區縣府路1號", "桃園市桃園區縣府路1號"),
    ]
    
    print("測試地址標準化功能：\n")
    for original, expected in test_cases:
        result = normalizer.normalize_address(original)
        status = "✓" if result == expected else "✗"
        print(f"{status} 原始: {original}")
        print(f"  預期: {expected}")
        print(f"  結果: {result}")
        print()


def test_address_extraction():
    """測試地址解析功能"""
    normalizer = TaiwanAddressNormalizer()
    
    test_addresses = [
        "臺北市士林區文林路100號",
        "桃園市中壢區中大路300號",
        "新北市淡水區英專路151號",
        "高雄市鳳山區光復路二段132號"
    ]
    
    print("\n測試地址解析功能：\n")
    for address in test_addresses:
        components = normalizer.extract_components(address)
        print(f"地址: {address}")
        print(f"  縣市: {components['city']}")
        print(f"  區域: {components['district']}")
        print(f"  路街: {components['road']}")
        print(f"  詳細: {components['detail']}")
        print()


def test_address_validation():
    """測試地址驗證功能"""
    normalizer = TaiwanAddressNormalizer()
    
    test_addresses = [
        "臺北市士林區文林路100號",  # 完整地址
        "士林區文林路100號",  # 缺縣市（會自動補全）
        "臺北市文林路100號",  # 缺區域
        "士林區",  # 只有區域
        "文林路100號",  # 只有路名
    ]
    
    print("\n測試地址驗證功能：\n")
    for address in test_addresses:
        # 先標準化
        normalized = normalizer.normalize_address(address)
        # 再驗證
        is_valid, error = normalizer.validate_address(normalized)
        status = "✓ 有效" if is_valid else f"✗ 無效 ({error})"
        print(f"{status} - 原始: {address}")
        print(f"         標準化: {normalized}")
        print()


if __name__ == "__main__":
    print("=" * 60)
    print("台灣地址標準化測試")
    print("=" * 60)
    
    test_address_normalization()
    test_address_extraction()
    test_address_validation()