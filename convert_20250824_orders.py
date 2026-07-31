"""
直接轉換 2025-08-24 訂單資料的腳本
"""

import os
import sys
from datetime import datetime

# 添加專案路徑到 Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

from utils.google_sheets_client import GoogleSheetsClient
from utils.price_calculator import PriceCalculator
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def convert_orders_20250824():
    """轉換 2025-08-24 的訂單資料"""
    
    # 初始化價格計算器
    calculator = PriceCalculator()
    
    # 這裡我會根據常見的訂單格式來處理
    # 請提供您的實際訂單資料，或從 Google Sheets 中讀取
    
    print("=== 2025-08-24 訂單轉換 ===")
    print("\n請提供要轉換的訂單資料")
    print("您可以：")
    print("1. 直接從 Google Sheets 複製貼上")
    print("2. 手動輸入訂單資訊")
    print("\n請選擇 (1 或 2): ", end="")
    
    choice = input().strip()
    
    if choice == "1":
        print("\n請貼上從 Google Sheets 複製的資料（完成後輸入空行）：")
        order_lines = []
        while True:
            line = input()
            if not line:
                break
            order_lines.append(line)
        
        # 處理 Google Sheets 資料
        process_sheets_data(order_lines, calculator)
        
    else:
        print("\n請輸入訂單資料，格式範例：")
        print("寄件人: XXX")
        print("收件人: YYY")
        print("商品: 18A禮盒 x 2")
        print("地址: ...")
        print("（輸入空行結束）\n")
        
        order_data = []
        while True:
            line = input()
            if not line:
                break
            order_data.append(line)
        
        # 處理手動輸入的資料
        process_manual_data(order_data, calculator)


def process_sheets_data(lines, calculator):
    """處理從 Google Sheets 複製的資料"""
    
    converted_orders = []
    
    for line in lines:
        # 假設是 Tab 分隔的資料
        fields = line.split('\t')
        
        if len(fields) >= 9:  # 至少要有主要欄位
            # 舊格式欄位順序（假設）：
            # 訂單時間, 訂單編號, 寄件人, 寄件人電話, 收件人, 收件人電話, 商品明細, 預計發貨日, 收件地址
            
            items_text = fields[6] if len(fields) > 6 else ""
            items = parse_items(items_text)
            
            # 計算價格
            total_price, price_detail = calculator.calculate_total_price(items)
            
            # 新格式
            new_order = [
                fields[2] if len(fields) > 2 else "",  # 訂購/寄件人
                "",  # 寄件地址（新欄位）
                fields[4] if len(fields) > 4 else "",  # 收件人
                format_items_names(items),  # 品項
                format_items_quantities(items),  # 數量
                fields[3] if len(fields) > 3 else "",  # 訂購人電話
                fields[5] if len(fields) > 5 else "",  # 收件人電話
                fields[8] if len(fields) > 8 else "",  # 地址
                str(total_price),  # 總價
                "",  # 付款狀況（新欄位）
                ""  # 末5碼（新欄位）
            ]
            
            converted_orders.append(new_order)
            print(f"✓ 轉換訂單: {new_order[2]} - 總價: ${total_price}")
    
    # 輸出結果
    print("\n=== 轉換完成 ===")
    print("\n新格式資料（可直接貼到 Google Sheets）：")
    print("訂購/寄件人\t寄件地址\t收件人\t品項\t數量\t訂購人電話\t收件人電話\t地址\t總價\t付款狀況\t末5碼")
    
    for order in converted_orders:
        print('\t'.join(order))
    
    # 產生備份檔案
    with open('backup_20250824_original.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    with open('converted_20250824_orders.txt', 'w', encoding='utf-8') as f:
        for order in converted_orders:
            f.write('\t'.join(order) + '\n')
    
    print(f"\n✓ 已備份原始資料到: backup_20250824_original.txt")
    print(f"✓ 已儲存轉換結果到: converted_20250824_orders.txt")


def process_manual_data(lines, calculator):
    """處理手動輸入的資料"""
    
    order_info = {}
    
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            order_info[key.strip()] = value.strip()
        elif '：' in line:
            key, value = line.split('：', 1)
            order_info[key.strip()] = value.strip()
    
    # 解析商品
    items_text = order_info.get('商品', order_info.get('商品明細', ''))
    items = parse_items(items_text)
    
    # 計算價格
    total_price, price_detail = calculator.calculate_total_price(items)
    
    # 轉換為新格式
    new_order = {
        '訂購/寄件人': order_info.get('寄件人', ''),
        '寄件地址': '',
        '收件人': order_info.get('收件人', ''),
        '品項': format_items_names(items),
        '數量': format_items_quantities(items),
        '訂購人電話': order_info.get('寄件人電話', order_info.get('訂購人電話', '')),
        '收件人電話': order_info.get('收件人電話', ''),
        '地址': order_info.get('地址', order_info.get('收件地址', '')),
        '總價': str(total_price),
        '付款狀況': '',
        '末5碼': ''
    }
    
    print("\n=== 轉換結果 ===")
    for key, value in new_order.items():
        print(f"{key}: {value}")
    
    print(f"\n價格計算詳情：")
    print(price_detail)
    
    print("\n=== Google Sheets 格式（Tab 分隔）===")
    print('\t'.join(new_order.values()))


def parse_items(items_text):
    """解析商品文字"""
    if not items_text:
        return []
    
    items = []
    
    # 處理各種可能的分隔符
    parts = items_text.replace('，', ',').split(',')
    
    for part in parts:
        part = part.strip()
        
        # 處理各種數量標記
        quantity = 1
        name = part
        
        # 嘗試匹配 "x 數字" 或 "× 數字"
        import re
        
        # 匹配 x2, x 2, ×2, × 2 等格式
        patterns = [
            r'(.+?)\s*[xX×]\s*(\d+)',  # 商品名 x 數量
            r'(.+?)\s*\*\s*(\d+)',      # 商品名 * 數量
            r'(.+?)\s+(\d+)\s*個',      # 商品名 數量個
            r'(.+?)\s+(\d+)\s*盒',      # 商品名 數量盒
            r'(.+?)\s+(\d+)\s*箱',      # 商品名 數量箱
        ]
        
        matched = False
        for pattern in patterns:
            match = re.match(pattern, part)
            if match:
                name = match.group(1).strip()
                quantity = int(match.group(2))
                matched = True
                break
        
        if not matched:
            # 檢查是否有數字在最後
            match = re.match(r'(.+?)\s+(\d+)$', part)
            if match:
                name = match.group(1).strip()
                quantity = int(match.group(2))
        
        if name:
            items.append({'name': name, 'quantity': quantity})
    
    return items


def format_items_names(items):
    """格式化商品名稱"""
    return ', '.join([item['name'] for item in items])


def format_items_quantities(items):
    """格式化商品數量"""
    return ', '.join([str(item['quantity']) for item in items])


if __name__ == "__main__":
    convert_orders_20250824()