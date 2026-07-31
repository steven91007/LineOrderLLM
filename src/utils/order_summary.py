#!/usr/bin/env python3
"""
訂單匯總工具 - 處理品項統計和匯總報告
"""
import re
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class OrderSummaryGenerator:
    """訂單匯總生成器"""
    
    def __init__(self):
        self.item_patterns = [
            # 標準格式: 18A禮盒 x2, 16A蛋糕 x1
            r'([^,\n]+?)\s*x\s*(\d+)',
            # 中文格式: 18A禮盒 兩個, 16A蛋糕 一個
            r'([^,\n]+?)\s*([一二三四五六七八九十\d]+)\s*個',
            # 括號格式: 18A禮盒(2), 16A蛋糕(1)
            r'([^,\n]+?)\s*\(\s*(\d+)\s*\)',
            # 數量在前: 2 x 18A禮盒, 1 x 16A蛋糕
            r'(\d+)\s*x\s*([^,\n]+)',
        ]
        
        # 中文數字轉換對照表
        self.chinese_numbers = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
            '兩': 2, '三': 3
        }
    
    def generate_summary_report(self, orders: List[Dict[str, Any]], target_date: str) -> Dict[str, Any]:
        """生成完整的匯總報告
        
        Args:
            orders: 訂單列表
            target_date: 目標日期
            
        Returns:
            Dict containing summary report data
        """
        try:
            # 解析所有品項
            item_summary = self._parse_and_summarize_items(orders)
            
            # 生成報告
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
                'error': f'生成匯總報告時發生錯誤: {e}',
                'target_date': target_date,
                'total_orders': 0,
                'item_summary': {},
                'formatted_report': '',
                'orders_processed': []
            }
    
    def _parse_and_summarize_items(self, orders: List[Dict[str, Any]]) -> Dict[str, int]:
        """解析並統計所有品項
        
        Args:
            orders: 訂單列表
            
        Returns:
            Dict mapping item names to total quantities
        """
        item_counts = defaultdict(int)
        
        for order in orders:
            items_text = order.get('items_text', '')
            if not items_text:
                continue
            
            # 解析該訂單的品項
            items = self._parse_items_from_text(items_text)
            
            # 累加到總計
            for item_name, quantity in items:
                # 標準化品項名稱（去除多餘空格）
                normalized_name = self._normalize_item_name(item_name)
                item_counts[normalized_name] += quantity
        
        # 轉換為普通字典並排序
        return dict(sorted(item_counts.items()))
    
    def _parse_items_from_text(self, items_text: str) -> List[Tuple[str, int]]:
        """從商品文字中解析品項和數量
        
        Args:
            items_text: 商品明細文字
            
        Returns:
            List of (item_name, quantity) tuples
        """
        items = []
        
        # 清理文字
        cleaned_text = items_text.strip()
        if not cleaned_text:
            return items
        
        # 嘗試不同的解析模式
        for pattern in self.item_patterns:
            matches = re.findall(pattern, cleaned_text, re.IGNORECASE)
            
            if matches:
                for match in matches:
                    if len(match) == 2:
                        item_name, quantity_str = match
                        
                        # 處理數量
                        quantity = self._parse_quantity(quantity_str)
                        if quantity > 0:
                            # 清理品項名稱
                            clean_name = self._clean_item_name(item_name)
                            if clean_name:
                                items.append((clean_name, quantity))
                
                # 如果找到匹配，就不再嘗試其他模式
                if items:
                    break
        
        # 如果所有模式都無法解析，嘗試簡單分割
        if not items:
            items = self._fallback_parse(cleaned_text)
        
        return items
    
    def _parse_quantity(self, quantity_str: str) -> int:
        """解析數量字串
        
        Args:
            quantity_str: 數量字串（可能是數字或中文）
            
        Returns:
            int: 解析後的數量
        """
        quantity_str = quantity_str.strip()
        
        # 嘗試直接轉換為數字
        if quantity_str.isdigit():
            return int(quantity_str)
        
        # 嘗試中文數字轉換
        if quantity_str in self.chinese_numbers:
            return self.chinese_numbers[quantity_str]
        
        # 處理包含中文數字的字串（如"兩個"中的"兩"）
        for chinese, num in self.chinese_numbers.items():
            if chinese in quantity_str:
                return num
        
        # 預設為1
        return 1
    
    def _clean_item_name(self, item_name: str) -> str:
        """清理品項名稱
        
        Args:
            item_name: 原始品項名稱
            
        Returns:
            str: 清理後的品項名稱
        """
        # 移除前後空格
        cleaned = item_name.strip()
        
        # 移除常見的前綴（如"商品："）
        prefixes_to_remove = ['商品:', '商品：', '產品:', '產品：', '•', '-', '*']
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        
        return cleaned
    
    def _normalize_item_name(self, item_name: str) -> str:
        """標準化品項名稱（用於統計時去重）
        
        Args:
            item_name: 品項名稱
            
        Returns:
            str: 標準化後的品項名稱
        """
        # 轉換為統一的大小寫和格式
        normalized = item_name.strip()
        
        # 移除多餘的空格
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized
    
    def _fallback_parse(self, items_text: str) -> List[Tuple[str, int]]:
        """備用解析方法（當主要模式都失敗時使用）
        
        Args:
            items_text: 商品明細文字
            
        Returns:
            List of (item_name, quantity) tuples
        """
        items = []
        
        # 按逗號或換行分割
        parts = re.split(r'[,\n]', items_text)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 嘗試找出數字
            numbers = re.findall(r'\d+', part)
            if numbers:
                # 假設最後一個數字是數量
                quantity = int(numbers[-1])
                # 移除數字後的部分作為品項名稱
                item_name = re.sub(r'\d+', '', part).strip()
                item_name = self._clean_item_name(item_name)
                
                if item_name:
                    items.append((item_name, quantity))
            else:
                # 沒有數字，假設數量為1
                item_name = self._clean_item_name(part)
                if item_name:
                    items.append((item_name, 1))
        
        return items
    
    def _format_summary_report(self, item_summary: Dict[str, int], target_date: str, total_orders: int) -> str:
        """格式化匯總報告
        
        Args:
            item_summary: 品項統計字典
            target_date: 目標日期
            total_orders: 總訂單數
            
        Returns:
            str: 格式化的報告文字
        """
        if not item_summary:
            return f"📊 {target_date} 品項匯總報告\n\n❌ 該日期沒有找到任何訂單資料。"
        
        # 計算總品項數量
        total_items = sum(item_summary.values())
        
        # 構建報告
        report_lines = [
            f"📊 {target_date} 品項匯總報告",
            "=" * 30,
            f"📋 總訂單數：{total_orders} 份",
            f"📦 總品項數：{total_items} 個",
            f"🏷️ 品項種類：{len(item_summary)} 種",
            "",
            "📈 品項明細："
        ]
        
        # 按數量排序（從大到小）
        sorted_items = sorted(item_summary.items(), key=lambda x: x[1], reverse=True)
        
        for i, (item_name, quantity) in enumerate(sorted_items, 1):
            report_lines.append(f"  {i:2d}. {item_name} × {quantity}")
        
        # 添加統計摘要
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