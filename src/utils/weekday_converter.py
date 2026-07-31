"""
星期幾轉換為日期的工具模組
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple


class WeekdayConverter:
    """將星期幾描述轉換為實際日期"""
    
    # 星期對應表
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
        根據星期幾取得下一個該星期的日期
        
        Args:
            weekday_str: 星期幾的描述（如：星期三、星期天）
            from_date: 基準日期，預設為今天
            
        Returns:
            日期字串 (MM-DD 格式) 或 None
        """
        if not weekday_str:
            return None
            
        # 清理輸入
        weekday_str = weekday_str.strip().lower()
        
        # 查找對應的星期數字
        target_weekday = cls.WEEKDAY_MAP.get(weekday_str)
        if target_weekday is None:
            return None
        
        # 取得基準日期
        if from_date is None:
            from_date = datetime.now()
        
        # 計算目標日期
        current_weekday = from_date.weekday()
        
        # 計算天數差異
        days_ahead = (target_weekday - current_weekday) % 7
        
        # 如果是今天，通常指下週
        if days_ahead == 0:
            days_ahead = 7
        
        # 計算目標日期
        target_date = from_date + timedelta(days=days_ahead)
        
        # 返回 MM-DD 格式
        return target_date.strftime('%m-%d')
    
    @classmethod
    def parse_shipping_date(cls, date_str: str, from_date: Optional[datetime] = None) -> Optional[str]:
        """
        解析發貨日期描述
        
        Args:
            date_str: 日期描述（可能是星期幾或具體日期）
            from_date: 基準日期
            
        Returns:
            標準化的日期字串 (MM-DD 格式) 或 None
        """
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # 優先嘗試解析絕對日期格式
        absolute_date = cls.parse_absolute_date(date_str)
        if absolute_date:
            return absolute_date
        
        # 檢查是否為星期幾
        for weekday_name in cls.WEEKDAY_MAP.keys():
            if weekday_name in date_str.lower():
                return cls.get_next_weekday_date(weekday_name, from_date)
        
        return None
    
    @classmethod
    def parse_absolute_date(cls, date_str: str) -> Optional[str]:
        """
        解析絕對日期格式，返回 MM-DD 格式
        
        Args:
            date_str: 日期字串（如：9/20, 9-20, 9月20日等）
            
        Returns:
            標準化的日期字串 (MM-DD 格式) 或 None
        """
        if not date_str:
            return None
        
        import re
        date_str = date_str.strip()
        
        # 絕對日期格式匹配
        absolute_patterns = [
            (r'(\d{1,2})/(\d{1,2})號?', lambda m: f"{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),    # 9/20號 或 9/20
            (r'(\d{1,2})-(\d{1,2})號?', lambda m: f"{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),    # 9-20號 或 9-20
            (r'(\d{1,2})月(\d{1,2})日?號?', lambda m: f"{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"), # 9月20日號
            (r'(\d{1,2})\.(\d{1,2})號?', lambda m: f"{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),   # 9.20號 或 9.20
            (r'(\d{2})-(\d{2})', lambda m: f"{m.group(1)}-{m.group(2)}"),                             # 09-20
            (r'(\d{2})/(\d{2})', lambda m: f"{m.group(1)}-{m.group(2)}"),                             # 09/20
        ]
        
        for pattern, formatter in absolute_patterns:
            match = re.search(pattern, date_str)
            if match:
                try:
                    result = formatter(match)
                    # 驗證月份和日期是否合理
                    month, day = result.split('-')
                    if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                        return result
                except:
                    continue
        
        return None
    
    @classmethod
    def get_weekday_name(cls, date: datetime) -> str:
        """
        取得日期對應的中文星期名稱
        
        Args:
            date: 日期物件
            
        Returns:
            中文星期名稱
        """
        weekday_names = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
        return weekday_names[date.weekday()]
    
    @classmethod
    def format_date_with_weekday(cls, date_str: str) -> str:
        """
        格式化日期字串，加上星期幾
        
        Args:
            date_str: MM-DD 格式的日期字串
            
        Returns:
            格式化後的字串（如：01-15 (星期三)）
        """
        if not date_str or '-' not in date_str:
            return date_str
        
        try:
            # 假設當前年份
            current_year = datetime.now().year
            month, day = date_str.split('-')
            date_obj = datetime(current_year, int(month), int(day))
            weekday_name = cls.get_weekday_name(date_obj)
            return f"{date_str} ({weekday_name})"
        except:
            return date_str


# 測試用
if __name__ == "__main__":
    converter = WeekdayConverter()
    
    # 測試星期轉換
    test_cases = [
        "星期天",
        "星期三",
        "星期日",
        "週一",
        "禮拜五"
    ]
    
    print("測試星期轉換：")
    for test in test_cases:
        result = converter.get_next_weekday_date(test)
        print(f"  {test} -> {result}")
    
    # 測試日期解析
    print("\n測試日期解析：")
    test_dates = [
        "星期天",
        "1/15",
        "01-20",
        "3月5日",
        "下星期三"
    ]
    
    for test in test_dates:
        result = converter.parse_shipping_date(test)
        formatted = converter.format_date_with_weekday(result) if result else "無法解析"
        print(f"  {test} -> {formatted}")