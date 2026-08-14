"""
台灣地址標準化 DSPy 模組
"""
import dspy
import json
from typing import Dict, Any


class AddressNormalizerSignature(dspy.Signature):
    """台灣地址標準化 Signature
    
    將各種格式的台灣地址標準化為統一格式：
    - 補全不完整地址（如：士林區 → 臺北市士林區）
    - 更新舊地名（如：桃園縣中壢市 → 桃園市中壢區）
    - 統一用字（如：台北 → 臺北）
    - 修正錯別字和格式問題
    - 保留地址備註（如：(XXX工地)、(XXX公司)等括號內容）
    """
    original_address = dspy.InputField(desc="原始地址文字，可能不完整或格式不標準")
    normalized_address = dspy.OutputField(desc="標準化後的完整台灣地址，格式：縣市+區域+詳細地址，必須保留原有的括號備註信息")


class AddressNormalizer(dspy.Module):
    """台灣地址標準化模組"""
    
    def __init__(self):
        super().__init__()
        self.normalize = dspy.ChainOfThought(AddressNormalizerSignature)
        
        # 建立 Few-shot 範例
        self.examples = [
            dspy.Example(
                original_address="士林區文林路100號",
                normalized_address="臺北市士林區文林路100號"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="桃園縣中壢市中大路300號",
                normalized_address="桃園市中壢區中大路300號"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="台中縣豐原市中正路1號",
                normalized_address="臺中市豐原區中正路1號"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="高雄縣鳳山市光復路二段132號",
                normalized_address="高雄市鳳山區光復路二段132號"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="台北市信義區信義路五段7號",
                normalized_address="臺北市信義區信義路五段7號"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="中壢區中大路300號",
                normalized_address="桃園市中壢區中大路300號"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="板橋區文化路一段100號",
                normalized_address="新北市板橋區文化路一段100號"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="台南縣永康市中正路529號",
                normalized_address="臺南市永康區中正路529號"
            ).with_inputs("original_address"),
            
            # 包含備註的範例
            dspy.Example(
                original_address="士林區文林路100號(台積電工地)",
                normalized_address="臺北市士林區文林路100號(台積電工地)"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="桃園縣中壢市中大路300號(中原大學)",
                normalized_address="桃園市中壢區中大路300號(中原大學)"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="板橋區文化路100號(遠東百貨)",
                normalized_address="新北市板橋區文化路100號(遠東百貨)"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="信義區市府路1號(台北101大樓)",
                normalized_address="臺北市信義區市府路1號(台北101大樓)"
            ).with_inputs("original_address"),
            
            dspy.Example(
                original_address="高雄縣鳳山市光復路132號(建築工地)",
                normalized_address="高雄市鳳山區光復路132號(建築工地)"
            ).with_inputs("original_address")
        ]
        
        # 注意：Few-shot 範例會在訓練時使用，這裡先初始化模組
    
    def forward(self, original_address: str) -> dspy.Prediction:
        """
        標準化地址
        
        Args:
            original_address: 原始地址字串
            
        Returns:
            dspy.Prediction: 包含 normalized_address
        """
        if not original_address or not isinstance(original_address, str):
            return dspy.Prediction(normalized_address=original_address)
        
        # 預處理：移除多餘空白
        cleaned_address = ' '.join(original_address.split())
        
        try:
            # 使用 DSPy 進行地址標準化
            result = self.normalize(original_address=cleaned_address)
            
            # 後處理：確保結果合理
            normalized = result.normalized_address.strip()
            
            # 基本檢查：確保有縣市資訊
            if not self._has_city_info(normalized):
                # 如果 AI 沒有補全縣市，嘗試手動補全
                normalized = self._fallback_completion(cleaned_address)
            
            return dspy.Prediction(normalized_address=normalized)
            
        except Exception as e:
            # AI 失敗時的 fallback
            return dspy.Prediction(normalized_address=self._fallback_completion(cleaned_address))
    
    def _has_city_info(self, address: str) -> bool:
        """檢查地址是否包含縣市資訊"""
        city_indicators = ['市', '縣']
        return any(indicator in address for indicator in city_indicators)
    
    def _fallback_completion(self, address: str) -> str:
        """簡單的 fallback 地址補全（保留備註）"""
        # 如果已經有縣市，直接返回  
        if self._has_city_info(address):
            return address
        
        # 提取備註（括號內容）
        import re
        note_pattern = r'\([^)]+\)$'
        note_match = re.search(note_pattern, address)
        note = note_match.group(0) if note_match else ''
        address_without_note = re.sub(note_pattern, '', address).strip()
        
        # 簡單的區域對應
        district_mapping = {
            '士林': '臺北市士林區',
            '中正': '臺北市中正區',
            '大安': '臺北市大安區',
            '信義': '臺北市信義區',
            '中山': '臺北市中山區',
            '松山': '臺北市松山區',
            '萬華': '臺北市萬華區',
            '大同': '臺北市大同區',
            '北投': '臺北市北投區',
            '內湖': '臺北市內湖區',
            '南港': '臺北市南港區',
            '文山': '臺北市文山區',
            
            '板橋': '新北市板橋區',
            '三重': '新北市三重區',
            '中和': '新北市中和區',
            '永和': '新北市永和區',
            '新莊': '新北市新莊區',
            '新店': '新北市新店區',
            '淡水': '新北市淡水區',
            
            '桃園': '桃園市桃園區',
            '中壢': '桃園市中壢區',
            '平鎮': '桃園市平鎮區',
            '八德': '桃園市八德區',
            '楊梅': '桃園市楊梅區'
        }
        
        result = address_without_note
        for district, full_name in district_mapping.items():
            if f"{district}區" in result:
                result = result.replace(f"{district}區", full_name)
                break
            elif district in result and not f"{district}區" in result:
                result = result.replace(district, full_name)
                break
        
        # 重新加上備註
        if note:
            result = f"{result}{note}"
        
        return result if result != address_without_note + note else address


# 建立全域實例供其他模組使用
address_normalizer = AddressNormalizer()