"""
Utilities for converting weekday descriptions into dates
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple


class WeekdayConverter:
    """Convert weekday descriptions into actual dates"""
    
    # Weekday lookup table
    WEEKDAY_MAP = {
        '星期一': 0, '週一': 0, '禮拜一': 0, 'monday': 0, 'mon': 0,
        '星期二': 1, '週二': 1, '禮拜二': 1, 'tuesday': 1, 'tue': 1,
        '星期三': 2, '週三': 2, '禮拜三': 2, 'wednesday': 2, 'wed': 2,
        '星期四': 3, '週四': 3, '禮拜四': 3, 'thursday': 3, 'thu': 3,
        '星期五': 4, '週五': 4, '禮拜五': 4, 'friday': 4, 'fri': 4,
        '星期六': 5, '週六': 5, '禮拜六': 5, 'saturday': 5, 'sat': 5,
        '星期日': 6, '週日': 6, '禮拜日': 6, '星期天': 6, '週末': 6,
        'sunday': 6, 'sun': 6
    }
    
    @classmethod
    def get_next_weekday_date(cls, weekday_str: str, from_date: Optional[datetime] = None) -> Optional[str]:
        """
        Get the date of the next occurrence of the given weekday
        
        Args:
            weekday_str: Weekday description (e.g. 星期三, 星期天)
            from_date: Reference date, defaults to today
            
        Returns:
            Date string (MM-DD format) or None
        """
        if not weekday_str:
            return None
            
        # Clean the input
        weekday_str = weekday_str.strip().lower()
        
        # Look up the corresponding weekday number
        target_weekday = cls.WEEKDAY_MAP.get(weekday_str)
        if target_weekday is None:
            return None
        
        # Get the reference date
        if from_date is None:
            from_date = datetime.now()
        
        # Compute the target date
        current_weekday = from_date.weekday()
        
        # Compute the difference in days
        days_ahead = (target_weekday - current_weekday) % 7
        
        # If it is today, it usually means next week
        if days_ahead == 0:
            days_ahead = 7
        
        # Compute the target date
        target_date = from_date + timedelta(days=days_ahead)
        
        # Return in MM-DD format
        return target_date.strftime('%m-%d')
    
    @classmethod
    def parse_shipping_date(cls, date_str: str, from_date: Optional[datetime] = None) -> Optional[str]:
        """
        Parse a shipping date description
        
        Args:
            date_str: Date description (either a weekday or a specific date)
            from_date: Reference date
            
        Returns:
            Normalized date string (MM-DD format) or None
        """
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Try absolute date formats first
        absolute_date = cls.parse_absolute_date(date_str)
        if absolute_date:
            return absolute_date
        
        # Check whether it is a weekday
        for weekday_name in cls.WEEKDAY_MAP.keys():
            if weekday_name in date_str.lower():
                return cls.get_next_weekday_date(weekday_name, from_date)
        
        return None
    
    @classmethod
    def parse_absolute_date(cls, date_str: str) -> Optional[str]:
        """
        Parse absolute date formats and return MM-DD
        
        Args:
            date_str: Date string (e.g. 9/20, 9-20, 9月20日)
            
        Returns:
            Normalized date string (MM-DD format) or None
        """
        if not date_str:
            return None
        
        import re
        date_str = date_str.strip()
        
        # Absolute date format patterns
        absolute_patterns = [
            (r'(\d{1,2})/(\d{1,2})號?', lambda m: f"{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),    # 9/20號 or 9/20
            (r'(\d{1,2})-(\d{1,2})號?', lambda m: f"{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),    # 9-20號 or 9-20
            (r'(\d{1,2})月(\d{1,2})日?號?', lambda m: f"{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"), # 9月20日號
            (r'(\d{1,2})\.(\d{1,2})號?', lambda m: f"{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),   # 9.20號 or 9.20
            (r'(\d{2})-(\d{2})', lambda m: f"{m.group(1)}-{m.group(2)}"),                             # 09-20
            (r'(\d{2})/(\d{2})', lambda m: f"{m.group(1)}-{m.group(2)}"),                             # 09/20
        ]
        
        for pattern, formatter in absolute_patterns:
            match = re.search(pattern, date_str)
            if match:
                try:
                    result = formatter(match)
                    # Validate that the month and day are reasonable
                    month, day = result.split('-')
                    if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                        return result
                except:
                    continue
        
        return None
    
    @classmethod
    def get_weekday_name(cls, date: datetime) -> str:
        """
        Get the Chinese weekday name for a date
        
        Args:
            date: Date object
            
        Returns:
            Chinese weekday name
        """
        weekday_names = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
        return weekday_names[date.weekday()]
    
    @classmethod
    def format_date_with_weekday(cls, date_str: str) -> str:
        """
        Format a date string with its weekday appended
        
        Args:
            date_str: Date string in MM-DD format
            
        Returns:
            Formatted string (e.g. 01-15 (星期三))
        """
        if not date_str or '-' not in date_str:
            return date_str
        
        try:
            # Assume the current year
            current_year = datetime.now().year
            month, day = date_str.split('-')
            date_obj = datetime(current_year, int(month), int(day))
            weekday_name = cls.get_weekday_name(date_obj)
            return f"{date_str} ({weekday_name})"
        except:
            return date_str


# For manual testing
if __name__ == "__main__":
    converter = WeekdayConverter()
    
    # Test weekday conversion
    test_cases = [
        "星期天",
        "星期三",
        "星期日",
        "週一",
        "禮拜五"
    ]
    
    print("Testing weekday conversion:")
    for test in test_cases:
        result = converter.get_next_weekday_date(test)
        print(f"  {test} -> {result}")
    
    # Test date parsing
    print("\nTesting date parsing:")
    test_dates = [
        "星期天",
        "1/15",
        "01-20",
        "3月5日",
        "下星期三"
    ]
    
    for test in test_dates:
        result = converter.parse_shipping_date(test)
        formatted = converter.format_date_with_weekday(result) if result else "unparseable"
        print(f"  {test} -> {formatted}")