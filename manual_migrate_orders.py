"""
手動訂單遷移腳本
用於手動輸入舊格式訂單資料，轉換為新格式並計算價格
"""

import os
import sys

# 添加專案路徑到 Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

from utils.price_calculator import PriceCalculator


def parse_items_from_text(items_text: str) -> list:
    """從商品明細文字中解析出商品列表"""
    if not items_text:
        return []
    
    items = []
    # 嘗試解析如 "18A禮盒 x 2, 20A蛋糕 x 1" 這樣的格式
    parts = items_text.split(',')
    
    for part in parts:
        part = part.strip()
        if ' x ' in part:
            name_part, qty_part = part.split(' x ', 1)
            name = name_part.strip()
            try:
                quantity = int(qty_part.strip())
                items.append({'name': name, 'quantity': quantity})
            except ValueError:
                # 如果無法解析數量，預設為1
                items.append({'name': name, 'quantity': 1})
        elif '×' in part:
            name_part, qty_part = part.split('×', 1)
            name = name_part.strip()
            try:
                quantity = int(qty_part.strip())
                items.append({'name': name, 'quantity': quantity})
            except ValueError:
                items.append({'name': name, 'quantity': 1})
        else:
            # 沒有明確數量標示，預設為1
            items.append({'name': part, 'quantity': 1})
    
    return items


def convert_order_to_new_format(old_order_data: str) -> dict:
    """
    將舊格式訂單字串轉換為新格式
    
    Args:
        old_order_data: 舊格式訂單資料（多行字串）
        
    Returns:
        dict: 新格式訂單資料
    """
    calculator = PriceCalculator()
    
    # 解析舊格式資料
    lines = old_order_data.strip().split('\n')
    order_info = {}
    
    for line in lines:
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            order_info[key.strip()] = value.strip()
        elif '：' in line:
            key, value = line.split('：', 1)
            order_info[key.strip()] = value.strip()
    
    # 提取商品資訊
    items_text = order_info.get('商品明細', order_info.get('商品', order_info.get('items', '')))
    items = parse_items_from_text(items_text)
    
    # 計算價格
    total_price, price_detail = calculator.calculate_total_price(items)
    
    # 轉換為新格式
    new_order = {
        '訂購/寄件人': order_info.get('寄件人', order_info.get('sender_name', '')),
        '寄件地址': '',  # 舊格式沒有，保持空白
        '收件人': order_info.get('收件人', order_info.get('receiver_name', '')),
        '品項': ', '.join([item['name'] for item in items]),
        '數量': ', '.join([str(item['quantity']) for item in items]),
        '訂購人電話': order_info.get('寄件人電話', order_info.get('sender_phone', '')),
        '收件人電話': order_info.get('收件人電話', order_info.get('receiver_phone', '')),
        '地址': order_info.get('收件地址', order_info.get('shipping_address', '')),
        '總價': str(total_price),
        '付款狀況': '',  # 新欄位，保持空白
        '末5碼': ''  # 新欄位，保持空白
    }
    
    return new_order, price_detail


def main():
    """主執行函數"""
    print("=== 訂單格式轉換工具 ===")
    print("請輸入舊格式的訂單資料，每行一個欄位，格式如：")
    print("寄件人: 張三")
    print("收件人: 李四")
    print("商品明細: 18A禮盒 x 2, 20A家庭號 x 1")
    print("收件地址: 台北市信義區...")
    print("(輸入完成後，輸入空行結束)")
    print()
    
    order_lines = []
    while True:
        line = input().strip()
        if not line:  # 空行結束輸入
            break
        order_lines.append(line)
    
    if not order_lines:
        print("沒有輸入任何資料")
        return
    
    # 轉換格式
    old_order_data = '\n'.join(order_lines)
    try:
        new_order, price_detail = convert_order_to_new_format(old_order_data)
        
        print("\n=== 轉換結果 ===")
        print("新格式訂單資料：")
        for key, value in new_order.items():
            print(f"{key}: {value}")
        
        print(f"\n價格計算詳情：")
        print(price_detail)
        
        print(f"\n=== Google Sheets 格式 ===")
        print("可直接複製到 Google Sheets 的資料（用 Tab 分隔）：")
        values = list(new_order.values())
        print('\t'.join(values))
        
    except Exception as e:
        print(f"轉換過程中發生錯誤: {e}")


def batch_convert_example():
    """批量轉換範例"""
    print("=== 批量轉換範例 ===")
    
    # 範例資料
    example_orders = [
        """
寄件人: 王小明
收件人: 陳大華  
商品明細: 18A禮盒 x 2
寄件人電話: 0912345678
收件人電話: 0987654321
收件地址: 台北市中正區重慶南路一段122號
        """,
        """
寄件人: 李美麗
收件人: 張志明
商品明細: 20A家庭號 x 1, 18A禮盒 x 1  
寄件人電話: 0923456789
收件人電話: 0976543210
收件地址: 新北市板橋區中山路一段50號2樓
        """
    ]
    
    for i, order_data in enumerate(example_orders, 1):
        print(f"\n--- 範例訂單 {i} ---")
        try:
            new_order, price_detail = convert_order_to_new_format(order_data)
            
            print("轉換結果：")
            for key, value in new_order.items():
                print(f"{key}: {value}")
            
            print(f"價格詳情: {price_detail}")
            
        except Exception as e:
            print(f"轉換範例 {i} 時發生錯誤: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='訂單格式轉換工具')
    parser.add_argument('--example', action='store_true', help='顯示批量轉換範例')
    
    args = parser.parse_args()
    
    if args.example:
        batch_convert_example()
    else:
        main()