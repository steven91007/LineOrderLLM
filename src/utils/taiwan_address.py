"""
台灣地址補全與標準化工具
"""
import re
from typing import Dict, List, Optional, Tuple
from .dspy_modules.address_normalizer import address_normalizer


class TaiwanAddressNormalizer:
    """台灣地址標準化處理器"""
    
    def __init__(self, use_ai: bool = True):
        self.use_ai = use_ai
        
        # 縣市對照表（包含直轄市）
        self.cities = {
            # 直轄市
            '台北': '臺北市', '臺北': '臺北市', '台北市': '臺北市', '臺北市': '臺北市',
            '新北': '新北市', '新北市': '新北市',
            '桃園': '桃園市', '桃園市': '桃園市', '桃園縣': '桃園市',  # 2014年升格
            '台中': '臺中市', '臺中': '臺中市', '台中市': '臺中市', '臺中市': '臺中市', '台中縣': '臺中市',  # 2010年合併升格
            '台南': '臺南市', '臺南': '臺南市', '台南市': '臺南市', '臺南市': '臺南市', '台南縣': '臺南市',  # 2010年合併升格
            '高雄': '高雄市', '高雄市': '高雄市', '高雄縣': '高雄市',  # 2010年合併
            
            # 縣
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
        
        # 區域對照表（縣市升格後的變更）
        self.district_updates = {
            # 桃園縣升格為桃園市（2014年）
            '中壢市': '中壢區',
            '平鎮市': '平鎮區',
            '龍潭鄉': '龍潭區',
            '楊梅市': '楊梅區',
            '新屋鄉': '新屋區',
            '觀音鄉': '觀音區',
            '桃園市': '桃園區',  # 原桃園市改為桃園區
            '龜山鄉': '龜山區',
            '八德市': '八德區',
            '大溪鎮': '大溪區',
            '復興鄉': '復興區',
            '大園鄉': '大園區',
            '蘆竹鄉': '蘆竹區',
            
            # 臺中縣市合併（2010年）
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
            
            # 臺南縣市合併（2010年）
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
            
            # 高雄縣市合併（2010年）
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
        
        # 常見區域名稱對照表（用於地址補全）
        self.district_mapping = {
            # 臺北市
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
            
            # 新北市
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
            
            # 桃園市
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
        標準化地址格式（混合式：規則 + AI）
        
        Args:
            address: 原始地址字串
            
        Returns:
            標準化後的地址
        """
        if not address:
            return address
        
        # 如果啟用 AI 且地址比較複雜，使用 DSPy 處理
        if self.use_ai and self._is_complex_address(address):
            try:
                result = address_normalizer(address)
                ai_normalized = result.normalized_address
                
                # AI 處理後再用規則進行後處理
                return self._post_process_with_rules(ai_normalized)
            except Exception:
                # AI 失敗時 fallback 到規則處理
                pass
        
        # 規則處理
        return self._normalize_with_rules(address)
    
    def _is_complex_address(self, address: str) -> bool:
        """判斷是否為需要 AI 處理的複雜地址"""
        complex_indicators = [
            # 包含舊地名
            '桃園縣', '台中縣', '臺中縣', '台南縣', '臺南縣', '高雄縣',
            # 不完整地址（只有區域名）
            r'^[^市縣]+區(?!.*[市縣])',
            # 包含錯別字的可能性
            '臺', '台',
            # 不標準格式
            r'^\s*[一二三四五六七八九十]+\s*[、，。]',
        ]
        
        for indicator in complex_indicators:
            if isinstance(indicator, str):
                if indicator in address:
                    return True
            else:  # regex pattern
                if re.search(indicator, address):
                    return True
        
        # 地址太短可能不完整，需要 AI 判斷
        if len(address.strip()) < 8:
            return True
            
        return False
    
    def _normalize_with_rules(self, address: str) -> str:
        """純規則處理地址標準化"""
        # 移除多餘空白
        address = ' '.join(address.split())
        
        # 先統一「台」為「臺」
        address = address.replace('台北', '臺北').replace('台中', '臺中').replace('台南', '臺南').replace('台東', '臺東')
        
        # 處理縣市
        address = self._update_city(address)
        
        # 處理區域升格
        address = self._update_district(address)
        
        # 補全地址
        address = self._complete_address(address)
        
        return address
    
    def _post_process_with_rules(self, address: str) -> str:
        """AI 處理後的規則後處理"""
        if not address:
            return address
            
        # 確保統一用字
        address = address.replace('台北', '臺北').replace('台中', '臺中').replace('台南', '臺南').replace('台東', '臺東')
        
        # 移除多餘空白
        address = ' '.join(address.split())
        
        return address
    
    def _update_city(self, address: str) -> str:
        """更新縣市名稱"""
        # 先處理縣市升格的特殊情況
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
                # 先更新區域名稱
                for old_district, new_district in self.district_updates.items():
                    if old_district in address:
                        address = address.replace(old_district, new_district)
                # 再更新縣市名稱
                address = address.replace(old_county, new_city)
                return address
        
        # 處理一般的縣市名稱
        for old_name, new_name in self.cities.items():
            # 避免重複替換（例如「台北市」變成「臺北市市」）
            if old_name in address and new_name not in address:
                address = address.replace(old_name, new_name)
                break
        
        return address
    
    def _update_district(self, address: str) -> str:
        """更新區域名稱（鄉鎮市改為區）"""
        for old_district, new_district in self.district_updates.items():
            if old_district in address:
                address = address.replace(old_district, new_district)
        
        return address
    
    def _complete_address(self, address: str) -> str:
        """補全地址（當只有區域名稱時）"""
        # 檢查是否已包含縣市
        has_city = any(city in address for city in self.cities.values())
        
        if not has_city:
            # 嘗試從區域名稱推斷縣市
            for district_name, (city, full_district) in self.district_mapping.items():
                # 檢查是否包含區域名稱
                if f"{district_name}區" in address:
                    # 已有區名，只補全縣市名
                    address = f"{city}{address}"
                    break
                elif district_name in address:
                    # 檢查後面是否緊接著是路、街等
                    import re
                    pattern = rf'{district_name}[路街道巷弄里村]'
                    if re.search(pattern, address):
                        # 補全區名和縣市名
                        address = address.replace(district_name, full_district)
                        address = f"{city}{address}"
                        break
                    # 或者是在字串結尾
                    elif address.endswith(district_name):
                        address = address.replace(district_name, full_district)
                        address = f"{city}{address}"
                        break
        
        return address
    
    def extract_components(self, address: str) -> Dict[str, Optional[str]]:
        """
        解析地址成各個組成部分
        
        Returns:
            包含 city, district, road, detail 的字典
        """
        normalized = self.normalize_address(address)
        
        # 縣市
        city = None
        for city_name in self.cities.values():
            if city_name in normalized:
                city = city_name
                break
        
        # 區域
        district = None
        district_pattern = r'([^市縣]+?[區鄉鎮市])'
        district_match = re.search(district_pattern, normalized)
        if district_match:
            district = district_match.group(1)
        
        # 路街
        road = None
        road_pattern = r'([^區鄉鎮市]+?[路街道巷弄](?:\d+段)?)'
        road_match = re.search(road_pattern, normalized)
        if road_match:
            road = road_match.group(1)
        
        # 詳細地址（門牌等）
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
        驗證地址格式是否完整
        
        Returns:
            (是否有效, 錯誤訊息)
        """
        components = self.extract_components(address)
        
        if not components['city']:
            return False, "缺少縣市資訊"
        
        if not components['district']:
            return False, "缺少區域資訊"
        
        if not components['road'] and not components['detail']:
            return False, "地址資訊不完整"
        
        return True, None