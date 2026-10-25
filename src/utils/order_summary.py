#!/usr/bin/env python3
"""
Order summary tool - item statistics and summary reports

Note: the formatted report text is staff-facing output and stays Chinese.
"""
import re
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class OrderSummaryGenerator:
    """Order summary generator"""
    
    def __init__(self):
        self.item_patterns = [
            # Standard format: 18A禮盒 x2, 16A蛋糕 x1
            r'([^,\n]+?)\s*x\s*(\d+)',
            # Chinese numeral format: 18A禮盒 兩個, 16A蛋糕 一個
            r'([^,\n]+?)\s*([一二三四五六七八九十\d]+)\s*個',
            # Parenthesized format: 18A禮盒(2), 16A蛋糕(1)
            r'([^,\n]+?)\s*\(\s*(\d+)\s*\)',
            # Quantity first: 2 x 18A禮盒, 1 x 16A蛋糕
            r'(\d+)\s*x\s*([^,\n]+)',
        ]
        
        # Chinese numeral -> int lookup table
        self.chinese_numbers = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
            '兩': 2, '三': 3
        }
    
    def generate_summary_report(self, orders: List[Dict[str, Any]], target_date: str) -> Dict[str, Any]:
        """Generate the full summary report
        
        Args:
            orders: List of orders
            target_date: Target date
            
        Returns:
            Dict containing summary report data
        """
        try:
            # Parse all items
            item_summary = self._parse_and_summarize_items(orders)
            
            # Build the report
            report = {
                'success': True,
                'target_date': target_date,
                'total_orders': len(orders),
                'total_items': sum(item_summary.values()),
                'item_summary': item_summary,
                'formatted_report': self._format_summary_report(item_summary, target_date, len(orders)),
                'orders_processed': orders
            }
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating summary report: {e}")
            return {
                'success': False,
                # Kept in Chinese: may be shown to staff
                'error': f'生成匯總報告時發生錯誤: {e}',
                'target_date': target_date,
                'total_orders': 0,
                'item_summary': {},
                'formatted_report': '',
                'orders_processed': []
            }
    
    def _parse_and_summarize_items(self, orders: List[Dict[str, Any]]) -> Dict[str, int]:
        """Parse and tally all items
        
        Args:
            orders: List of orders
            
        Returns:
            Dict mapping item names to total quantities
        """
        item_counts = defaultdict(int)
        
        for order in orders:
            items_text = order.get('items_text', '')
            if not items_text:
                continue
            
            # Parse this order's items
            items = self._parse_items_from_text(items_text)
            
            # Add to the running totals
            for item_name, quantity in items:
                # Normalize the item name (collapse extra whitespace)
                normalized_name = self._normalize_item_name(item_name)
                item_counts[normalized_name] += quantity
        
        # Convert to a plain dict, sorted
        return dict(sorted(item_counts.items()))
    
    def _parse_items_from_text(self, items_text: str) -> List[Tuple[str, int]]:
        """Parse item names and quantities from the item text
        
        Args:
            items_text: Item detail text
            
        Returns:
            List of (item_name, quantity) tuples
        """
        items = []
        
        # Clean up the text
        cleaned_text = items_text.strip()
        if not cleaned_text:
            return items
        
        # Try each parsing pattern
        for pattern in self.item_patterns:
            matches = re.findall(pattern, cleaned_text, re.IGNORECASE)
            
            if matches:
                for match in matches:
                    if len(match) == 2:
                        item_name, quantity_str = match
                        
                        # Handle the quantity
                        quantity = self._parse_quantity(quantity_str)
                        if quantity > 0:
                            # Clean the item name
                            clean_name = self._clean_item_name(item_name)
                            if clean_name:
                                items.append((clean_name, quantity))
                
                # Once a pattern matches, don't try the others
                if items:
                    break
        
        # If no pattern could parse it, fall back to simple splitting
        if not items:
            items = self._fallback_parse(cleaned_text)
        
        return items
    
    def _parse_quantity(self, quantity_str: str) -> int:
        """Parse a quantity string
        
        Args:
            quantity_str: Quantity string (digits or Chinese numerals)
            
        Returns:
            int: Parsed quantity
        """
        quantity_str = quantity_str.strip()
        
        # Try converting directly to an int
        if quantity_str.isdigit():
            return int(quantity_str)
        
        # Try Chinese numeral conversion
        if quantity_str in self.chinese_numbers:
            return self.chinese_numbers[quantity_str]
        
        # Handle strings containing a Chinese numeral (e.g. "兩" in "兩個")
        for chinese, num in self.chinese_numbers.items():
            if chinese in quantity_str:
                return num
        
        # Default to 1
        return 1
    
    def _clean_item_name(self, item_name: str) -> str:
        """Clean an item name
        
        Args:
            item_name: Raw item name
            
        Returns:
            str: Cleaned item name
        """
        # Strip leading/trailing whitespace
        cleaned = item_name.strip()
        
        # Remove common prefixes (e.g. "商品：")
        prefixes_to_remove = ['商品:', '商品：', '產品:', '產品：', '•', '-', '*']
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        
        return cleaned
    
    def _normalize_item_name(self, item_name: str) -> str:
        """Normalize an item name (for de-duplication when tallying)
        
        Args:
            item_name: Item name
            
        Returns:
            str: Normalized item name
        """
        # Convert to a consistent case and format
        normalized = item_name.strip()
        
        # Collapse extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized
    
    def _fallback_parse(self, items_text: str) -> List[Tuple[str, int]]:
        """Fallback parser (used when all main patterns fail)
        
        Args:
            items_text: Item detail text
            
        Returns:
            List of (item_name, quantity) tuples
        """
        items = []
        
        # Split on commas or newlines
        parts = re.split(r'[,\n]', items_text)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Try to find numbers
            numbers = re.findall(r'\d+', part)
            if numbers:
                # Assume the last number is the quantity
                quantity = int(numbers[-1])
                # Use the text with numbers removed as the item name
                item_name = re.sub(r'\d+', '', part).strip()
                item_name = self._clean_item_name(item_name)
                
                if item_name:
                    items.append((item_name, quantity))
            else:
                # No number: assume quantity 1
                item_name = self._clean_item_name(part)
                if item_name:
                    items.append((item_name, 1))
        
        return items
    
    def _format_summary_report(self, item_summary: Dict[str, int], target_date: str, total_orders: int) -> str:
        """Format the summary report
        
        Args:
            item_summary: Item tally dict
            target_date: Target date
            total_orders: Total number of orders
            
        Returns:
            str: Formatted report text
        """
        if not item_summary:
            return f"📊 {target_date} 品項匯總報告\n\n❌ 該日期沒有找到任何訂單資料。"
        
        # Compute the total item count
        total_items = sum(item_summary.values())
        
        # Build the report
        report_lines = [
            f"📊 {target_date} 品項匯總報告",
            "=" * 30,
            f"📋 總訂單數：{total_orders} 份",
            f"📦 總品項數：{total_items} 個",
            f"🏷️ 品項種類：{len(item_summary)} 種",
            "",
            "📈 品項明細："
        ]
        
        # Sort by quantity (descending)
        sorted_items = sorted(item_summary.items(), key=lambda x: x[1], reverse=True)
        
        for i, (item_name, quantity) in enumerate(sorted_items, 1):
            report_lines.append(f"  {i:2d}. {item_name} × {quantity}")
        
        # Append the stats summary
        if len(sorted_items) > 0:
            report_lines.extend([
                "",
                "🔝 熱門品項統計：",
                f"  最多：{sorted_items[0][0]} ({sorted_items[0][1]} 個)",
            ])
            
            if len(sorted_items) > 1:
                report_lines.append(f"  次多：{sorted_items[1][0]} ({sorted_items[1][1]} 個)")
        
        report_lines.extend([
            "",
            f"📅 報告生成時間：{target_date}",
            "🎯 此報告可直接提供給主管參考"
        ])
        
        return "\n".join(report_lines)