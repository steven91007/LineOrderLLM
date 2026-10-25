"""
DSPy module for Taiwan address normalization
"""
import dspy
import json
from typing import Dict, Any


class AddressNormalizerSignature(dspy.Signature):
    """Taiwan address normalization signature
    
    Normalize Taiwan addresses written in any format into a single standard format:
    - Complete incomplete addresses (e.g. 士林區 → 臺北市士林區)
    - Update old place names (e.g. 桃園縣中壢市 → 桃園市中壢區)
    - Use consistent characters (e.g. 台北 → 臺北)
    - Fix typos and formatting problems
    - Keep address notes (parenthesized content such as (XXX工地) (construction site) or (XXX公司) (company))
    """
    original_address = dspy.InputField(desc="Raw address text; may be incomplete or non-standard")
    normalized_address = dspy.OutputField(desc="The normalized full Taiwan address, formatted as city/county (縣市) + district (區域) + detailed address; any original parenthesized notes must be kept")


class AddressNormalizer(dspy.Module):
    """Taiwan address normalization module"""
    
    def __init__(self):
        super().__init__()
        self.normalize = dspy.ChainOfThought(AddressNormalizerSignature)
        
        # Build the few-shot examples
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
            
            # Examples that include notes
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
        
        # Note: the few-shot examples are used during training; here we just initialize the module
    
    def forward(self, original_address: str) -> dspy.Prediction:
        """
        Normalize an address
        
        Args:
            original_address: Raw address string
            
        Returns:
            dspy.Prediction: containing normalized_address
        """
        if not original_address or not isinstance(original_address, str):
            return dspy.Prediction(normalized_address=original_address)
        
        # Pre-processing: remove extra whitespace
        cleaned_address = ' '.join(original_address.split())
        
        try:
            # Normalize the address with DSPy
            result = self.normalize(original_address=cleaned_address)
            
            # Post-processing: make sure the result is reasonable
            normalized = result.normalized_address.strip()
            
            # Basic check: make sure city/county info is present
            if not self._has_city_info(normalized):
                # If the AI did not fill in the city/county, try to complete it manually
                normalized = self._fallback_completion(cleaned_address)
            
            return dspy.Prediction(normalized_address=normalized)
            
        except Exception as e:
            # Fallback when the AI fails
            return dspy.Prediction(normalized_address=self._fallback_completion(cleaned_address))
    
    def _has_city_info(self, address: str) -> bool:
        """Check whether the address contains city/county info"""
        city_indicators = ['市', '縣']
        return any(indicator in address for indicator in city_indicators)
    
    def _fallback_completion(self, address: str) -> str:
        """Simple fallback address completion (keeps notes)"""
        # If a city/county is already present, return as-is  
        if self._has_city_info(address):
            return address
        
        # Extract the note (parenthesized content)
        import re
        note_pattern = r'\([^)]+\)$'
        note_match = re.search(note_pattern, address)
        note = note_match.group(0) if note_match else ''
        address_without_note = re.sub(note_pattern, '', address).strip()
        
        # Simple district mapping
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
        
        # Re-attach the note
        if note:
            result = f"{result}{note}"
        
        return result if result != address_without_note + note else address


# Global instance shared by other modules
address_normalizer = AddressNormalizer()