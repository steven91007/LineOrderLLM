"""
Taiwan address completion and normalization utilities
"""
import re
from typing import Dict, List, Optional, Tuple
from .dspy_modules.address_normalizer import address_normalizer


class TaiwanAddressNormalizer:
    """Taiwan address normalizer"""
    
    def __init__(self, use_ai: bool = True):
        self.use_ai = use_ai
        
        # City/county lookup table (including special municipalities)
        self.cities = {
            # Special municipalities
            '台北': '臺北市', '臺北': '臺北市', '台北市': '臺北市', '臺北市': '臺北市',
            '新北': '新北市', '新北市': '新北市',
            '桃園': '桃園市', '桃園市': '桃園市', '桃園縣': '桃園市',  # Upgraded to a special municipality in 2014
            '台中': '臺中市', '臺中': '臺中市', '台中市': '臺中市', '臺中市': '臺中市', '台中縣': '臺中市',  # Merged and upgraded in 2010
            '台南': '臺南市', '臺南': '臺南市', '台南市': '臺南市', '臺南市': '臺南市', '台南縣': '臺南市',  # Merged and upgraded in 2010
            '高雄': '高雄市', '高雄市': '高雄市', '高雄縣': '高雄市',  # Merged in 2010
            
            # Counties (and provincial cities)
            '基隆': '基隆市', '基隆市': '基隆市',
            '新竹市': '新竹市',
            '新竹': '新竹縣', '新竹縣': '新竹縣',
            '苗栗': '苗栗縣', '苗栗縣': '苗栗縣',
            '彰化': '彰化縣', '彰化縣': '彰化縣',
            '南投': '南投縣', '南投縣': '南投縣',
            '雲林': '雲林縣', '雲林縣': '雲林縣',
            '嘉義市': '嘉義市',
            '嘉義': '嘉義縣', '嘉義縣': '嘉義縣',
            '屏東': '屏東縣', '屏東縣': '屏東縣',
            '宜蘭': '宜蘭縣', '宜蘭縣': '宜蘭縣',
            '花蓮': '花蓮縣', '花蓮縣': '花蓮縣',
            '台東': '臺東縣', '臺東': '臺東縣', '台東縣': '臺東縣', '臺東縣': '臺東縣',
            '澎湖': '澎湖縣', '澎湖縣': '澎湖縣',
            '金門': '金門縣', '金門縣': '金門縣',
            '連江': '連江縣', '連江縣': '連江縣', '馬祖': '連江縣'
        }
        
        # District lookup table (renames after city/county upgrades)
        self.district_updates = {
            # Taoyuan County upgraded to Taoyuan City (2014)
            '中壢市': '中壢區',
            '平鎮市': '平鎮區',
            '龍潭鄉': '龍潭區',
            '楊梅市': '楊梅區',
            '新屋鄉': '新屋區',
            '觀音鄉': '觀音區',
            '桃園市': '桃園區',  # The former Taoyuan City became Taoyuan District
            '龜山鄉': '龜山區',
            '八德市': '八德區',
            '大溪鎮': '大溪區',
            '復興鄉': '復興區',
            '大園鄉': '大園區',
            '蘆竹鄉': '蘆竹區',
            
            # Taichung County and City merged (2010)
            '豐原市': '豐原區',
            '東勢鎮': '東勢區',
            '大甲鎮': '大甲區',
            '清水鎮': '清水區',
            '沙鹿鎮': '沙鹿區',
            '梧棲鎮': '梧棲區',
            '后里鄉': '后里區',
            '神岡鄉': '神岡區',
            '潭子鄉': '潭子區',
            '大雅鄉': '大雅區',
            '新社鄉': '新社區',
            '石岡鄉': '石岡區',
            '外埔鄉': '外埔區',
            '大安鄉': '大安區',
            '烏日鄉': '烏日區',
            '大肚鄉': '大肚區',
            '龍井鄉': '龍井區',
            '霧峰鄉': '霧峰區',
            '太平市': '太平區',
            '大里市': '大里區',
            '和平鄉': '和平區',
            
            # Tainan County and City merged (2010)
            '永康市': '永康區',
            '歸仁鄉': '歸仁區',
            '新化鎮': '新化區',
            '左鎮鄉': '左鎮區',
            '玉井鄉': '玉井區',
            '楠西鄉': '楠西區',
            '南化鄉': '南化區',
            '仁德鄉': '仁德區',
            '關廟鄉': '關廟區',
            '龍崎鄉': '龍崎區',
            '官田鄉': '官田區',
            '麻豆鎮': '麻豆區',
            '佳里鎮': '佳里區',
            '西港鄉': '西港區',
            '七股鄉': '七股區',
            '將軍鄉': '將軍區',
            '學甲鎮': '學甲區',
            '北門鄉': '北門區',
            '新營市': '新營區',
            '後壁鄉': '後壁區',
            '白河鎮': '白河區',
            '東山鄉': '東山區',
            '六甲鄉': '六甲區',
            '下營鄉': '下營區',
            '柳營鄉': '柳營區',
            '鹽水鎮': '鹽水區',
            '善化鎮': '善化區',
            '大內鄉': '大內區',
            '山上鄉': '山上區',
            '新市鄉': '新市區',
            '安定鄉': '安定區',
            
            # Kaohsiung County and City merged (2010)
            '鳳山市': '鳳山區',
            '林園鄉': '林園區',
            '大寮鄉': '大寮區',
            '大樹鄉': '大樹區',
            '大社鄉': '大社區',
            '仁武鄉': '仁武區',
            '鳥松鄉': '鳥松區',
            '岡山鎮': '岡山區',
            '橋頭鄉': '橋頭區',
            '燕巢鄉': '燕巢區',
            '田寮鄉': '田寮區',
            '阿蓮鄉': '阿蓮區',
            '路竹鄉': '路竹區',
            '湖內鄉': '湖內區',
            '茄萣鄉': '茄萣區',
            '永安鄉': '永安區',
            '彌陀鄉': '彌陀區',
            '梓官鄉': '梓官區',
            '旗山鎮': '旗山區',
            '美濃鎮': '美濃區',
            '六龜鄉': '六龜區',
            '甲仙鄉': '甲仙區',
            '杉林鄉': '杉林區',
            '內門鄉': '內門區',
            '茂林鄉': '茂林區',
            '桃源鄉': '桃源區',
            '那瑪夏鄉': '那瑪夏區'
        }
        
        # Common district name lookup (used for address completion)
        self.district_mapping = {
            # Taipei City
            '中正': ('臺北市', '中正區'),
            '大同': ('臺北市', '大同區'),
            '中山': ('臺北市', '中山區'),
            '松山': ('臺北市', '松山區'),
            '大安': ('臺北市', '大安區'),
            '萬華': ('臺北市', '萬華區'),
            '信義': ('臺北市', '信義區'),
            '士林': ('臺北市', '士林區'),
            '北投': ('臺北市', '北投區'),
            '內湖': ('臺北市', '內湖區'),
            '南港': ('臺北市', '南港區'),
            '文山': ('臺北市', '文山區'),
            
            # New Taipei City
            '板橋': ('新北市', '板橋區'),
            '三重': ('新北市', '三重區'),
            '中和': ('新北市', '中和區'),
            '永和': ('新北市', '永和區'),
            '新莊': ('新北市', '新莊區'),
            '新店': ('新北市', '新店區'),
            '樹林': ('新北市', '樹林區'),
            '鶯歌': ('新北市', '鶯歌區'),
            '三峽': ('新北市', '三峽區'),
            '淡水': ('新北市', '淡水區'),
            '汐止': ('新北市', '汐止區'),
            '瑞芳': ('新北市', '瑞芳區'),
            '土城': ('新北市', '土城區'),
            '蘆洲': ('新北市', '蘆洲區'),
            '五股': ('新北市', '五股區'),
            '泰山': ('新北市', '泰山區'),
            '林口': ('新北市', '林口區'),
            '深坑': ('新北市', '深坑區'),
            '石碇': ('新北市', '石碇區'),
            '坪林': ('新北市', '坪林區'),
            '三芝': ('新北市', '三芝區'),
            '石門': ('新北市', '石門區'),
            '八里': ('新北市', '八里區'),
            '平溪': ('新北市', '平溪區'),
            '雙溪': ('新北市', '雙溪區'),
            '貢寮': ('新北市', '貢寮區'),
            '金山': ('新北市', '金山區'),
            '萬里': ('新北市', '萬里區'),
            '烏來': ('新北市', '烏來區'),
            
            # Taoyuan City
            '桃園': ('桃園市', '桃園區'),
            '中壢': ('桃園市', '中壢區'),
            '平鎮': ('桃園市', '平鎮區'),
            '八德': ('桃園市', '八德區'),
            '楊梅': ('桃園市', '楊梅區'),
            '蘆竹': ('桃園市', '蘆竹區'),
            '大溪': ('桃園市', '大溪區'),
            '龍潭': ('桃園市', '龍潭區'),
            '龜山': ('桃園市', '龜山區'),
            '大園': ('桃園市', '大園區'),
            '觀音': ('桃園市', '觀音區'),
            '新屋': ('桃園市', '新屋區'),
            '復興': ('桃園市', '復興區')
        }
    
    def normalize_address(self, address: str) -> str:
        """
        Normalize the address format (hybrid: rules + AI)
        
        Args:
            address: Raw address string
            
        Returns:
            The normalized address
        """
        if not address:
            return address
        
        # If AI is enabled and the address is complex, process it with DSPy
        if self.use_ai:
            try:
                result = address_normalizer(address)
                ai_normalized = result.normalized_address
                
                # After AI processing, post-process with rules
                return self._post_process_with_rules(ai_normalized)
            except Exception:
                # If AI fails, fall back to rule-based processing
                pass
        
        # Rule-based processing
        return self._normalize_with_rules(address)
    
    def _is_complex_address(self, address: str) -> bool:
        """Determine whether this is a complex address that needs AI processing"""
        complex_indicators = [
            # Contains old place names
            '桃園縣', '台中縣', '臺中縣', '台南縣', '臺南縣', '高雄縣',
            # Incomplete address (district name only)
            r'^[^市縣]+區(?!.*[市縣])',
            # Possible variant/incorrect characters
            '臺', '台',
            # Non-standard format
            r'^\s*[一二三四五六七八九十]+\s*[、，。]',
        ]
        
        for indicator in complex_indicators:
            if isinstance(indicator, str):
                if indicator in address:
                    return True
            else:  # regex pattern
                if re.search(indicator, address):
                    return True
        
        # A very short address may be incomplete; let the AI decide
        if len(address.strip()) < 8:
            return True
            
        return False
    
    def _normalize_with_rules(self, address: str) -> str:
        """Normalize the address using rules only"""
        # Remove extra whitespace
        address = ' '.join(address.split())
        
        # First normalize "台" to "臺"
        address = address.replace('台北', '臺北').replace('台中', '臺中').replace('台南', '臺南').replace('台東', '臺東')
        
        # Handle city/county
        address = self._update_city(address)
        
        # Handle district upgrades
        address = self._update_district(address)
        
        # Complete the address
        address = self._complete_address(address)
        
        return address
    
    def _post_process_with_rules(self, address: str) -> str:
        """Rule-based post-processing after AI processing"""
        if not address:
            return address
            
        # Ensure consistent characters
        address = address.replace('台北', '臺北').replace('台中', '臺中').replace('台南', '臺南').replace('台東', '臺東')
        
        # Remove extra whitespace
        address = ' '.join(address.split())
        
        return address
    
    def _update_city(self, address: str) -> str:
        """Update the city/county name"""
        # First handle the special case of upgraded cities/counties
        upgrade_mappings = [
            ('桃園縣', '桃園市'),
            ('臺中縣', '臺中市'),
            ('台中縣', '臺中市'),
            ('臺南縣', '臺南市'),
            ('台南縣', '臺南市'),
            ('高雄縣', '高雄市')
        ]
        
        for old_county, new_city in upgrade_mappings:
            if old_county in address:
                # Update the district name first
                for old_district, new_district in self.district_updates.items():
                    if old_district in address:
                        address = address.replace(old_district, new_district)
                # Then update the city/county name
                address = address.replace(old_county, new_city)
                return address
        
        # Handle ordinary city/county names
        for old_name, new_name in self.cities.items():
            # Avoid double replacement (e.g. "台北市" becoming "臺北市市")
            if old_name in address and new_name not in address:
                address = address.replace(old_name, new_name)
                break
        
        return address
    
    def _update_district(self, address: str) -> str:
        """Update district names (townships/towns/county cities become districts)"""
        for old_district, new_district in self.district_updates.items():
            if old_district in address:
                address = address.replace(old_district, new_district)
        
        return address
    
    def _complete_address(self, address: str) -> str:
        """Complete the address (when only the district name is present)"""
        # Check whether a city/county is already present
        has_city = any(city in address for city in self.cities.values())
        
        if not has_city:
            # Try to infer the city/county from the district name
            for district_name, (city, full_district) in self.district_mapping.items():
                # Check whether the district name is present
                if f"{district_name}區" in address:
                    # District already present; only prepend the city/county
                    address = f"{city}{address}"
                    break
                elif district_name in address:
                    # Check whether it is immediately followed by 路, 街, etc. (road/street)
                    import re
                    pattern = rf'{district_name}[路街道巷弄里村]'
                    if re.search(pattern, address):
                        # Complete both the district and city/county names
                        address = address.replace(district_name, full_district)
                        address = f"{city}{address}"
                        break
                    # Or it is at the end of the string
                    elif address.endswith(district_name):
                        address = address.replace(district_name, full_district)
                        address = f"{city}{address}"
                        break
        
        return address
    
    def extract_components(self, address: str) -> Dict[str, Optional[str]]:
        """
        Parse the address into its components
        
        Returns:
            A dict containing city, district, road, detail
        """
        normalized = self.normalize_address(address)
        
        # City/county
        city = None
        for city_name in self.cities.values():
            if city_name in normalized:
                city = city_name
                break
        
        # District
        district = None
        district_pattern = r'([^市縣]+?[區鄉鎮市])'
        district_match = re.search(district_pattern, normalized)
        if district_match:
            district = district_match.group(1)
        
        # Road/street
        road = None
        road_pattern = r'([^區鄉鎮市]+?[路街道巷弄](?:\d+段)?)'
        road_match = re.search(road_pattern, normalized)
        if road_match:
            road = road_match.group(1)
        
        # Detailed address (house number, etc.)
        detail = None
        detail_pattern = r'(\d+(?:之\d+)?號(?:.+)?)'
        detail_match = re.search(detail_pattern, normalized)
        if detail_match:
            detail = detail_match.group(1)
        
        return {
            'city': city,
            'district': district,
            'road': road,
            'detail': detail,
            'full_address': normalized
        }
    
    def validate_address(self, address: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that the address is complete
        
        Returns:
            (is_valid, error_message)
            Error messages are kept in Chinese because they may be shown to staff.
        """
        components = self.extract_components(address)
        
        if not components['city']:
            return False, "缺少縣市資訊"
        
        if not components['district']:
            return False, "缺少區域資訊"
        
        if not components['road'] and not components['detail']:
            return False, "地址資訊不完整"
        
        return True, None