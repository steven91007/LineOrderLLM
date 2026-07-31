"""
從原始備份恢復並轉換為正確的新格式
"""

import os
import sys

# 添加專案路徑到 Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from utils.price_calculator import PriceCalculator
import re

def restore_and_convert():
    """從原始備份恢復並轉換"""
    
    # 設定參數
    CREDENTIALS_PATH = 'aesthetic-rush-323802-7f5591bc4a1c_1.json'
    SHEET_ID = '1i7wDoTR50lIwnlY53u6jBbJ_ZgbREuyj2MWX6lHkjxw'
    BACKUP_SHEET = "備份_20250824_星期日_20250820_211153"  # 原始備份
    TARGET_SHEET = "20250824_星期日"
    
    try:
        # 建立服務
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        credentials = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=credentials)
        calculator = PriceCalculator()
        
        print(f"從 {BACKUP_SHEET} 恢復並轉換到 {TARGET_SHEET}")
        
        # 讀取備份資料
        range_name = f'{BACKUP_SHEET}!A:K'
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=range_name
        ).execute()
        
        values = result.get('values', [])
        
        if not values:
            print("備份工作表沒有資料")
            return
        
        print(f"找到 {len(values)} 行資料（包含標題）")
        
        # 原始格式標題: 訂單時間, 訂單編號, 寄件人, 寄件人電話, 收件人, 收件人電話, 商品明細, 預計發貨日, 收件地址, 訂單狀態, 備註
        original_headers = values[0]
        print(f"原始標題: {original_headers}")
        
        # 新格式標題（移除寄件地址）
        new_headers = [
            '訂購/寄件人', '收件人', '品項', '數量', 
            '訂購人電話', '收件人電話', '地址', '總價', '付款狀況', '末5碼'
        ]
        
        converted_data = [new_headers]
        
        # 轉換每一行資料（跳過標題）
        for i, row in enumerate(values[1:], 1):
            if len(row) < 9:  # 至少要有主要欄位
                print(f"第 {i+1} 行資料欄位不足，跳過")
                continue
            
            try:
                # 原始格式解析
                sender_name = row[2] if len(row) > 2 else ""
                sender_phone = row[3] if len(row) > 3 else ""
                receiver_name = row[4] if len(row) > 4 else ""
                receiver_phone = row[5] if len(row) > 5 else ""
                items_text = row[6] if len(row) > 6 else ""
                shipping_address = row[8] if len(row) > 8 else ""
                
                # 解析商品
                items = parse_items(items_text)
                
                # 計算價格
                total_price, price_detail = calculator.calculate_total_price(items)
                
                # 格式化商品資訊
                items_names = ', '.join([item['name'] for item in items])
                items_quantities = ', '.join([str(item['quantity']) for item in items])
                
                # 新格式行
                new_row = [
                    sender_name,        # 訂購/寄件人
                    receiver_name,      # 收件人
                    items_names,        # 品項
                    items_quantities,   # 數量
                    sender_phone,       # 訂購人電話
                    receiver_phone,     # 收件人電話
                    shipping_address,   # 地址
                    str(total_price),   # 總價
                    "",                 # 付款狀況（新欄位）
                    ""                  # 末5碼（新欄位）
                ]
                
                converted_data.append(new_row)
                print(f"[OK] 轉換第 {i} 筆: {receiver_name} - {items_names} - ${total_price}")
                
            except Exception as e:
                print(f"轉換第 {i+1} 行時發生錯誤: {e}")
                continue
        
        print(f"\n成功轉換 {len(converted_data)-1} 筆訂單")
        
        # 計算統計
        if len(converted_data) > 1:
            total_amount = sum(int(row[7]) for row in converted_data[1:] if row[7].isdigit())
            print(f"總金額: ${total_amount:,}")
        
        # 清除目標工作表並寫入新資料
        print(f"\n更新工作表 {TARGET_SHEET}...")
        
        # 清除舊資料
        clear_request = service.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID,
            range=f'{TARGET_SHEET}!A:Z'
        ).execute()
        
        # 寫入新資料
        body = {
            'values': converted_data,
            'majorDimension': 'ROWS',
        }
        
        result = service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f'{TARGET_SHEET}!A1',
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        
        print(f"[完成] 更新完成！寫入 {len(converted_data)} 行資料")
        print(f"[完成] 工作表 {TARGET_SHEET} 已更新為新格式（無寄件地址欄位）")
        print("[完成] 所有訂單已自動計算價格")
        
    except Exception as e:
        print(f"錯誤: {e}")


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
        
        # 嘗試匹配各種格式
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


if __name__ == "__main__":
    restore_and_convert()