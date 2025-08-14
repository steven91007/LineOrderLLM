"""
時間處理工具 - 支援網路時間獲取和日期格式化
"""

import requests
from datetime import datetime, timedelta
import json
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class TimeUtils:
    """時間處理工具類"""
    
    # 基準年份 - 強制使用2025年
    BASE_YEAR = 2025
    
    # 中文星期對照
    WEEKDAY_CN = {
        0: '星期一',
        1: '星期二', 
        2: '星期三',
        3: '星期四',
        4: '星期五',
        5: '星期六',
        6: '星期日'
    }
    
    def __init__(self):
        self.cached_time = None
        self.cache_timestamp = None
        self.cache_duration = 300  # 5分鐘緩存
        
    def clear_cache(self):
        """清除時間緩存"""
        self.cached_time = None
        self.cache_timestamp = None
        logger.info("Time cache cleared")
        
    def get_current_time(self, use_network: bool = True) -> datetime:
        """
        獲取當前時間
        
        Args:
            use_network: 是否嘗試從網路獲取時間
            
        Returns:
            datetime: 當前時間
        """
        if use_network:
            network_time = self._get_network_time()
            if network_time and network_time.year >= self.BASE_YEAR:
                return network_time
            elif network_time:
                logger.warning(f"Network time year {network_time.year} is before base year {self.BASE_YEAR}, using system time")
        
        # 使用系統時間作為 fallback
        current = datetime.now()
        
        # 如果系統時間也不對，使用基準年份
        if current.year < self.BASE_YEAR:
            logger.warning(f"System time year {current.year} is before base year {self.BASE_YEAR}, using base year")
            current = current.replace(year=self.BASE_YEAR)
        
        return current
    
    def _get_network_time(self) -> Optional[datetime]:
        """從網路獲取準確時間"""
        # 檢查緩存
        if (self.cached_time and self.cache_timestamp and 
            datetime.now() - self.cache_timestamp < timedelta(seconds=self.cache_duration)):
            return self.cached_time + (datetime.now() - self.cache_timestamp)
        
        # 嘗試多個時間 API
        time_apis = [
            {
                'url': 'http://worldtimeapi.org/api/timezone/Asia/Taipei',
                'parser': self._parse_worldtimeapi
            },
            {
                'url': 'http://api.timezonedb.com/v2.1/get-zone?key=demo&format=json&by=zone&zone=Asia/Taipei',
                'parser': self._parse_timezonedb
            }
        ]
        
        for api in time_apis:
            try:
                response = requests.get(api['url'], timeout=5)
                if response.status_code == 200:
                    parsed_time = api['parser'](response.json())
                    if parsed_time:
                        # 更新緩存
                        self.cached_time = parsed_time
                        self.cache_timestamp = datetime.now()
                        logger.info(f"Successfully fetched network time: {parsed_time}")
                        return parsed_time
            except Exception as e:
                logger.warning(f"Failed to fetch time from {api['url']}: {e}")
                continue
        
        logger.warning("All network time sources failed, using system time")
        return None
    
    def _parse_worldtimeapi(self, data: Dict[str, Any]) -> Optional[datetime]:
        """解析 WorldTimeAPI 回應"""
        try:
            datetime_str = data.get('datetime', '')
            # 格式: 2025-08-06T10:30:45.123456+08:00
            if datetime_str:
                # 移除微秒和時區資訊，簡化解析
                datetime_str = datetime_str.split('.')[0]
                if '+' in datetime_str:
                    datetime_str = datetime_str.split('+')[0]
                return datetime.fromisoformat(datetime_str)
        except Exception as e:
            logger.error(f"Error parsing WorldTimeAPI response: {e}")
        return None
    
    def _parse_timezonedb(self, data: Dict[str, Any]) -> Optional[datetime]:
        """解析 TimezoneDB 回應"""
        try:
            timestamp = data.get('timestamp')
            if timestamp:
                return datetime.fromtimestamp(int(timestamp))
        except Exception as e:
            logger.error(f"Error parsing TimezoneDB response: {e}")
        return None
    
    def format_date_with_weekday(self, date_obj: datetime, format_type: str = 'standard') -> str:
        """
        格式化日期並包含星期
        
        Args:
            date_obj: 日期物件
            format_type: 格式類型 ('standard', 'short', 'sheet_name')
            
        Returns:
            str: 格式化後的日期字串
        """
        weekday = self.WEEKDAY_CN[date_obj.weekday()]
        
        if format_type == 'standard':
            return f"{date_obj.strftime('%Y-%m-%d')}({weekday})"
        elif format_type == 'short':
            return f"{date_obj.strftime('%m/%d')}({weekday})"
        elif format_type == 'sheet_name':
            return f"{date_obj.strftime('%Y%m%d')}_{weekday}"
        else:
            return f"{date_obj.strftime('%Y-%m-%d')}({weekday})"
    
    def parse_shipping_date(self, date_str: str) -> Optional[datetime]:
        """
        解析出貨日期字串
        
        Args:
            date_str: 日期字串 (可能格式: YYYY-MM-DD, MM-DD, 明天, 後天等)
            
        Returns:
            datetime or None: 解析後的日期物件
        """
        if not date_str or date_str.strip() == '':
            return None
        
        date_str = date_str.strip()
        current_time = self.get_current_time()
        
        try:
            # 標準日期格式: YYYY-MM-DD
            if len(date_str) == 10 and '-' in date_str:
                return datetime.strptime(date_str, '%Y-%m-%d')
            
            # 短日期格式: MM-DD
            elif len(date_str) == 5 and '-' in date_str:
                month, day = map(int, date_str.split('-'))
                year = self.BASE_YEAR  # 使用基準年份2025年
                # 如果日期已經過了，使用明年
                test_date = datetime(year, month, day)
                if test_date < current_time:
                    test_date = datetime(year + 1, month, day)
                return test_date
            
            # 相對日期
            elif date_str in ['今天', '今日']:
                return current_time
            elif date_str in ['明天', '明日']:
                return current_time + timedelta(days=1)
            elif date_str in ['後天']:
                return current_time + timedelta(days=2)
            elif date_str.endswith('天後') or date_str.endswith('日後'):
                days_str = date_str[:-2]
                if days_str.isdigit():
                    days = int(days_str)
                    return current_time + timedelta(days=days)
            
        except Exception as e:
            logger.error(f"Error parsing shipping date '{date_str}': {e}")
        
        return None
    
    def get_date_range_for_week(self, target_date: datetime) -> Dict[str, datetime]:
        """
        獲取指定日期所在週的日期範圍
        
        Args:
            target_date: 目標日期
            
        Returns:
            dict: 包含週開始和結束日期
        """
        # 找到週一
        days_since_monday = target_date.weekday()
        week_start = target_date - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)
        
        return {
            'week_start': week_start,
            'week_end': week_end,
            'week_range': f"{week_start.strftime('%m/%d')} - {week_end.strftime('%m/%d')}"
        }
    
    def validate_shipping_date(self, date_str: str) -> Dict[str, Any]:
        """
        驗證出貨日期
        
        Args:
            date_str: 出貨日期字串
            
        Returns:
            dict: 驗證結果
        """
        if not date_str:
            return {
                'is_valid': True,
                'parsed_date': None,
                'formatted_date': '',
                'message': '出貨日期為選填'
            }
        
        parsed_date = self.parse_shipping_date(date_str)
        
        if not parsed_date:
            return {
                'is_valid': False,
                'parsed_date': None,
                'formatted_date': '',
                'message': f'無法解析日期格式: {date_str}'
            }
        
        current_time = self.get_current_time()
        
        # 檢查日期是否在過去
        if parsed_date.date() < current_time.date():
            return {
                'is_valid': False,
                'parsed_date': parsed_date,
                'formatted_date': self.format_date_with_weekday(parsed_date),
                'message': '出貨日期不能是過去的日期'
            }
        
        # 檢查是否太遠的未來（例如超過1年）
        if (parsed_date - current_time).days > 365:
            return {
                'is_valid': False,
                'parsed_date': parsed_date,
                'formatted_date': self.format_date_with_weekday(parsed_date),
                'message': '出貨日期過於遙遠'
            }
        
        return {
            'is_valid': True,
            'parsed_date': parsed_date,
            'formatted_date': self.format_date_with_weekday(parsed_date),
            'message': '日期格式正確'
        }

# 全域時間工具實例
time_utils = TimeUtils()