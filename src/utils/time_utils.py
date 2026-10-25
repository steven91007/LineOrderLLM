"""
Time utilities - network time fetching and date formatting
"""

import requests
from datetime import datetime, timedelta
import json
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class TimeUtils:
    """Time utility class"""
    
    # Base year - force 2025 as the minimum
    BASE_YEAR = 2025
    
    # Chinese weekday names
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
        self.cache_duration = 300  # 5-minute cache
        
    def clear_cache(self):
        """Clear the time cache"""
        self.cached_time = None
        self.cache_timestamp = None
        logger.info("Time cache cleared")
        
    def get_current_time(self, use_network: bool = True) -> datetime:
        """
        Get the current time
        
        Args:
            use_network: Whether to try fetching the time from the network
            
        Returns:
            datetime: The current time
        """
        if use_network:
            network_time = self._get_network_time()
            if network_time and network_time.year >= self.BASE_YEAR:
                return network_time
            elif network_time:
                logger.warning(f"Network time year {network_time.year} is before base year {self.BASE_YEAR}, using system time")
        
        # Fall back to the system time
        current = datetime.now()
        
        # If the system time is also wrong, use the base year
        if current.year < self.BASE_YEAR:
            logger.warning(f"System time year {current.year} is before base year {self.BASE_YEAR}, using base year")
            current = current.replace(year=self.BASE_YEAR)
        
        return current
    
    def _get_network_time(self) -> Optional[datetime]:
        """Fetch accurate time from the network"""
        # Check the cache
        if (self.cached_time and self.cache_timestamp and 
            datetime.now() - self.cache_timestamp < timedelta(seconds=self.cache_duration)):
            return self.cached_time + (datetime.now() - self.cache_timestamp)
        
        # Try several time APIs
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
                        # Update the cache
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
        """Parse a WorldTimeAPI response"""
        try:
            datetime_str = data.get('datetime', '')
            # Format: 2025-08-06T10:30:45.123456+08:00
            if datetime_str:
                # Strip microseconds and timezone info to simplify parsing
                datetime_str = datetime_str.split('.')[0]
                if '+' in datetime_str:
                    datetime_str = datetime_str.split('+')[0]
                return datetime.fromisoformat(datetime_str)
        except Exception as e:
            logger.error(f"Error parsing WorldTimeAPI response: {e}")
        return None
    
    def _parse_timezonedb(self, data: Dict[str, Any]) -> Optional[datetime]:
        """Parse a TimezoneDB response"""
        try:
            timestamp = data.get('timestamp')
            if timestamp:
                return datetime.fromtimestamp(int(timestamp))
        except Exception as e:
            logger.error(f"Error parsing TimezoneDB response: {e}")
        return None
    
    def format_date_with_weekday(self, date_obj: datetime, format_type: str = 'standard') -> str:
        """
        Format a date including its weekday
        
        Args:
            date_obj: Date object
            format_type: Format type ('standard', 'short', 'sheet_name')
            
        Returns:
            str: The formatted date string
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
        Parse a shipping date string
        
        Args:
            date_str: Date string (possible formats: YYYY-MM-DD, MM-DD, 明天 (tomorrow), 後天 (day after tomorrow), etc.)
            
        Returns:
            datetime or None: The parsed date object
        """
        if not date_str or date_str.strip() == '':
            return None
        
        date_str = date_str.strip()
        current_time = self.get_current_time()
        
        try:
            # Standard date format: YYYY-MM-DD
            if len(date_str) == 10 and '-' in date_str:
                return datetime.strptime(date_str, '%Y-%m-%d')
            
            # Short date format: MM-DD
            elif len(date_str) == 5 and '-' in date_str:
                month, day = map(int, date_str.split('-'))
                year = self.BASE_YEAR  # Use the base year (2025)
                # If the date has already passed, use next year
                test_date = datetime(year, month, day)
                if test_date < current_time:
                    test_date = datetime(year + 1, month, day)
                return test_date
            
            # Relative dates
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
        Get the date range of the week containing the given date
        
        Args:
            target_date: Target date
            
        Returns:
            dict: Containing the week's start and end dates
        """
        # Find Monday
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
        Validate a shipping date
        
        Args:
            date_str: Shipping date string
            
        Returns:
            dict: Validation result. The 'message' values are kept in Chinese
            because they may be shown to shop staff.
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
        
        # Check whether the date is in the past
        if parsed_date.date() < current_time.date():
            return {
                'is_valid': False,
                'parsed_date': parsed_date,
                'formatted_date': self.format_date_with_weekday(parsed_date),
                'message': '出貨日期不能是過去的日期'
            }
        
        # Check whether it is too far in the future (e.g. more than 1 year)
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

# Global time utility instance
time_utils = TimeUtils()