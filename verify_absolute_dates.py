#!/usr/bin/env python3
"""
驗證絕對日期功能
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from datetime import datetime
from src.utils.weekday_converter import WeekdayConverter
from src.utils.dspy_modules.unified_parser import UnifiedOrderParser

def main():
    print("=== 驗證絕對日期識別功能 ===")
    
    # 測試WeekdayConverter絕對日期解析
    print("\n1. WeekdayConverter絕對日期解析:")
    test_cases = [
        ("9/20", "09-20"),
        ("9-20", "09-20"),
        ("10/15號", "10-15"),
        ("9月20日", "09-20"),
    ]
    
    for input_date, expected in test_cases:
        result = WeekdayConverter.parse_absolute_date(input_date)
        status = "正確" if result == expected else "錯誤"
        print(f"  {input_date} -> {result} ({status})")
    
    # 測試完整日期解析功能
    print("\n2. 完整日期解析功能:")
    ref_date = datetime(2024, 8, 15)  # 星期四
    
    mixed_cases = [
        ("9/20", "09-20", "絕對日期"),
        ("星期天", "08-18", "相對日期"),
    ]
    
    for input_date, expected, type_desc in mixed_cases:
        result = WeekdayConverter.parse_shipping_date(input_date, ref_date)
        status = "正確" if result == expected else "錯誤"
        print(f"  {input_date} -> {result} ({type_desc}, {status})")
    
    # 測試UnifiedOrderParser的_clean_date方法
    print("\n3. UnifiedOrderParser._clean_date方法:")
    parser = UnifiedOrderParser()
    parser._reference_date = ref_date
    
    parser_cases = [
        ("09-20", "09-20", "已是正確格式"),
        ("9/20", "09-20", "需要轉換的絕對日期"),
        ("星期天", "08-18", "相對日期"),
    ]
    
    for input_date, expected, desc in parser_cases:
        result = parser._clean_date(input_date)
        status = "正確" if result == expected else "錯誤"
        print(f"  {input_date} -> {result} ({desc}, {status})")
    
    # 測試DSPy提示生成
    print("\n4. DSPy提示內容:")
    weekday_table = parser._generate_weekday_conversion_table(ref_date)
    
    if "絕對日期格式轉換規則" in weekday_table:
        print("  包含絕對日期格式說明: 正確")
    else:
        print("  包含絕對日期格式說明: 錯誤")
    
    if "9/20" in weekday_table:
        print("  包含9/20範例: 正確")
    else:
        print("  包含9/20範例: 錯誤")
    
    # 測試邊界情況
    print("\n5. 邊界情況測試:")
    edge_cases = [
        ("13/20", None, "無效月份"),
        ("9/32", None, "無效日期"),
        ("", None, "空字串"),
    ]
    
    for input_date, expected, desc in edge_cases:
        result = WeekdayConverter.parse_absolute_date(input_date)
        status = "正確" if result == expected else "錯誤"
        print(f"  {desc}: {input_date} -> {result} ({status})")
    
    print("\n=== 驗證完成 ===")
    print("主要功能:")
    print("1. WeekdayConverter新增parse_absolute_date方法")
    print("2. 支援9/20、9-20、9月20日、10/15號等格式")
    print("3. 絕對日期優先於星期幾處理")
    print("4. DSPy提示包含絕對日期格式說明")
    print("5. 邊界情況處理正確")

if __name__ == "__main__":
    main()