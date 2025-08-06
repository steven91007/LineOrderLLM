#!/usr/bin/env python3
"""
測試台灣地址標準化功能
"""
from src.utils.taiwan_address import TaiwanAddressNormalizer


def test_address_normalization():
    """測試地址標準化"""
    print("測試混合式地址標準化功能（規則 + DSPy AI）：\n")
    
    # 測試 AI 模式
    normalizer_ai = TaiwanAddressNormalizer(use_ai=True)
    
    # 測試純規則模式
    normalizer_rules = TaiwanAddressNormalizer(use_ai=False)
    
    test_cases = [
        # 簡單案例（規則可處理）
        ("新北市板橋區文化路一段100號", "新北市板橋區文化路一段100號"),
        
        # 不完整地址（需要 AI）
        ("士林區文林路100號", "臺北市士林區文林路100號"),
        ("中壢區中大路300號", "桃園市中壢區中大路300號"),
        
        # 舊地名（需要 AI）
        ("桃園縣中壢市中大路300號", "桃園市中壢區中大路300號"),
        ("台中縣豐原市中正路1號", "臺中市豐原區中正路1號"),
        
        # 複雜案例
        ("台北信義區市府路1號", "臺北市信義區市府路1號"),
        ("高雄鳳山光復路132號", "高雄市鳳山區光復路132號"),
    ]
    
    for original, expected in test_cases:
        print(f"原始地址: {original}")
        
        # AI 模式結果
        result_ai = normalizer_ai.normalize_address(original)
        status_ai = "✓" if result_ai == expected else "✗"
        print(f"  {status_ai} AI 模式: {result_ai}")
        
        # 規則模式結果
        result_rules = normalizer_rules.normalize_address(original)
        status_rules = "✓" if result_rules == expected else "✗"
        print(f"  {status_rules} 規則模式: {result_rules}")
        
        print(f"  預期結果: {expected}")
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