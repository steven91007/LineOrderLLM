#!/usr/bin/env python3
"""
測試 DSPy 地址標準化功能
"""
import os
import dspy
from src.utils.taiwan_address import TaiwanAddressNormalizer

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

def test_ai_address_normalization():
    """測試 AI 地址標準化"""
    if not setup_dspy():
        return
    
    print("測試 DSPy AI 地址標準化功能：\n")
    
    normalizer = TaiwanAddressNormalizer(use_ai=True)
    
    test_cases = [
        "士林區文林路100號",
        "桃園縣中壢市中大路300號", 
        "台北信義區市府路1號",
        "高雄鳳山光復路132號",
        "台中縣豐原市中正路1號",
        "板橋區文化路100號",
        "中壢中大路300號",  # 更簡化的格式
    ]
    
    for address in test_cases:
        print(f"原始地址: {address}")
        try:
            result = normalizer.normalize_address(address)
            print(f"標準化後: {result}")
        except Exception as e:
            print(f"處理失敗: {e}")
        print()

if __name__ == "__main__":
    test_ai_address_normalization()