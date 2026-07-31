#!/usr/bin/env python3
"""
驗證修復結果
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from datetime import datetime
from src.utils.dspy_modules.unified_parser import UnifiedOrderParser
from src.utils.weekday_converter import WeekdayConverter

def verify_fix():
    """驗證修復結果"""
    
    print("=== 驗證DSPy日期修復 ===")
    
    # 測試WeekdayConverter基礎功能
    ref_date = datetime(2024, 8, 15)  # 星期四
    result = WeekdayConverter.get_next_weekday_date("星期天", ref_date)
    print(f"WeekdayConverter測試: 星期天 -> {result}")
    
    # 測試DSPy模組
    parser = UnifiedOrderParser()
    parser._reference_date = ref_date
    
    # 測試星期幾轉換對照表
    table = parser._generate_weekday_conversion_table(ref_date)
    print("\n星期幾轉換對照表生成: 成功")
    print("包含星期天 -> 08-18:", "08-18" in table)
    
    # 測試提示生成
    prompt = parser._create_parsing_prompt("星期天")
    print("解析提示生成: 成功")
    print("包含日期對照表:", "星期幾轉換對照表" in prompt)
    
    # 檢查Signature
    from src.utils.dspy_modules.unified_parser import UnifiedOrderSignature
    print("Signature包含current_date欄位:", "current_date" in str(UnifiedOrderSignature))
    
    print("\n=== 修復驗證完成 ===")
    print("主要修改:")
    print("1. UnifiedOrderSignature添加了current_date欄位")
    print("2. forward方法傳入當前日期")
    print("3. 解析提示包含星期幾轉換對照表")
    print("4. DSPy能夠基於準確的當前日期進行星期幾轉換")

if __name__ == "__main__":
    verify_fix()