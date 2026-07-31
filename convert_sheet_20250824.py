"""
直接從 Google Sheets 轉換 20250824_星期日 工作表的資料
"""

import os
import sys
import re
from typing import List, Dict, Any
from datetime import datetime

# 添加專案路徑到 Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

from utils.google_sheets_client import GoogleSheetsClient
from utils.price_calculator import PriceCalculator
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SheetConverter:
    def __init__(self, credentials_path: str, sheet_id: str):
        """初始化工作表轉換器"""
        self.credentials_path = credentials_path
        self.sheet_id = sheet_id
        self.service = self._build_service()
        self.price_calculator = PriceCalculator()
        
    def _build_service(self):
        """建立 Google Sheets API 服務"""
        try:
            SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
            credentials = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=SCOPES
            )
            service = build('sheets', 'v4', credentials=credentials)
            return service
        except Exception as e:
            logger.error(f"Error building Google Sheets service: {e}")
            return None
    
    def read_sheet_data(self, sheet_name: str = "20250824_星期日") -> List[List[str]]:
        """讀取指定工作表的資料"""
        try:
            logger.info(f"讀取工作表: {sheet_name}")
            
            # 讀取所有資料
            range_name = f'{sheet_name}!A:K'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                logger.warning(f"工作表 {sheet_name} 沒有資料")
                return []
            
            logger.info(f"找到 {len(values)} 行資料")
            return values
            
        except Exception as e:
            logger.error(f"讀取工作表失敗: {e}")
            return []
    
    def convert_old_to_new_format(self, old_data: List[List[str]]) -> List[List[str]]:
        """將舊格式轉換為新格式"""
        
        if not old_data:
            return []
        
        # 假設第一行是標題
        old_headers = old_data[0] if old_data else []
        logger.info(f"原始標題: {old_headers}")
        
        # 新格式的標題
        new_headers = [
            '訂購/寄件人', '收件人', '品項', '數量',
            '訂購人電話', '收件人電話', '地址', '總價', '付款狀況', '末5碼'
        ]
        
        converted_data = [new_headers]
        
        # 轉換每一行資料（跳過標題行）
        for i, row in enumerate(old_data[1:], 1):
            if len(row) < 9:  # 確保有足夠的欄位
                logger.warning(f"第 {i+1} 行資料欄位不足，跳過")
                continue
            
            # 判斷是舊格式還是新格式並解析欄位
            try:
                if len(old_headers) > 10 and '寄件地址' in old_headers:
                    # 已經是新格式（含寄件地址欄位）
                    sender_name = row[0] if len(row) > 0 else ""
                    receiver_name = row[2] if len(row) > 2 else ""  # 跳過寄件地址
                    items_text = row[3] if len(row) > 3 else ""
                    sender_phone = row[5] if len(row) > 5 else ""
                    receiver_phone = row[6] if len(row) > 6 else ""
                    shipping_address = row[7] if len(row) > 7 else ""
                elif len(old_headers) >= 10 and '訂購/寄件人' in old_headers:
                    # 新格式（無寄件地址欄位）
                    sender_name = row[0] if len(row) > 0 else ""
                    receiver_name = row[1] if len(row) > 1 else ""
                    items_text = row[2] if len(row) > 2 else ""
                    sender_phone = row[4] if len(row) > 4 else ""
                    receiver_phone = row[5] if len(row) > 5 else ""
                    shipping_address = row[6] if len(row) > 6 else ""
                else:
                    # 舊格式: 訂單時間, 訂單編號, 寄件人, 寄件人電話, 收件人, 收件人電話, 商品明細, 預計發貨日, 收件地址
                    sender_name = row[2] if len(row) > 2 else ""
                    sender_phone = row[3] if len(row) > 3 else ""
                    receiver_name = row[4] if len(row) > 4 else ""
                    receiver_phone = row[5] if len(row) > 5 else ""
                    items_text = row[6] if len(row) > 6 else ""
                    shipping_address = row[8] if len(row) > 8 else ""
                
                # 解析商品資訊
                items = self._parse_items(items_text)
                
                # 計算價格
                total_price, price_detail = self.price_calculator.calculate_total_price(items)
                
                # 格式化商品資訊
                items_names = ', '.join([item['name'] for item in items])
                items_quantities = ', '.join([str(item['quantity']) for item in items])
                
                # 創建新格式的行
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
                logger.info(f"轉換第 {i} 筆: {receiver_name} - 商品: {items_names} - 總價: ${total_price}")
                
            except Exception as e:
                logger.error(f"轉換第 {i+1} 行時發生錯誤: {e}")
                continue
        
        return converted_data
    
    def _parse_items(self, items_text: str) -> List[Dict[str, Any]]:
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
    
    def create_backup_sheet(self, sheet_name: str, data: List[List[str]]) -> bool:
        """創建備份工作表"""
        try:
            backup_sheet_name = f"備份_{sheet_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 創建新工作表
            request = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': backup_sheet_name
                        }
                    }
                }]
            }
            
            response = self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=request
            ).execute()
            
            # 寫入備份資料
            body = {
                'values': data,
                'majorDimension': 'ROWS',
            }
            
            result = self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=f'{backup_sheet_name}!A1',
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            logger.info(f"已創建備份工作表: {backup_sheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"創建備份失敗: {e}")
            return False
    
    def update_sheet_with_new_format(self, sheet_name: str, new_data: List[List[str]]) -> bool:
        """更新工作表為新格式"""
        try:
            # 清除原有資料
            clear_request = self.service.spreadsheets().values().clear(
                spreadsheetId=self.sheet_id,
                range=f'{sheet_name}!A:Z'
            ).execute()
            
            # 寫入新資料
            body = {
                'values': new_data,
                'majorDimension': 'ROWS',
            }
            
            result = self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=f'{sheet_name}!A1',
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            logger.info(f"已更新工作表 {sheet_name}，共 {len(new_data)} 行資料")
            return True
            
        except Exception as e:
            logger.error(f"更新工作表失敗: {e}")
            return False


def main():
    """主執行函數"""
    
    # 從環境變數或直接設定參數
    CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', 'aesthetic-rush-323802-7f5591bc4a1c_1.json')
    SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '1i7wDoTR50lIwnlY53u6jBbJ_ZgbREuyj2MWX6lHkjxw')
    TARGET_SHEET = "20250824_星期日"
    
    print(f"=== 轉換 Google Sheets 工作表: {TARGET_SHEET} ===\n")
    
    # 檢查憑證檔案
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"錯誤: 找不到憑證檔案 {CREDENTIALS_PATH}")
        print("請設定環境變數 GOOGLE_CREDENTIALS_PATH 或修改程式中的路徑")
        return
    
    if SHEET_ID == 'your_sheet_id':
        print("錯誤: 請設定 Google Sheet ID")
        print("請設定環境變數 GOOGLE_SHEET_ID 或修改程式中的 ID")
        return
    
    # 初始化轉換器
    converter = SheetConverter(CREDENTIALS_PATH, SHEET_ID)
    
    if not converter.service:
        print("錯誤: 無法連接到 Google Sheets")
        return
    
    # 步驟 1: 讀取原始資料
    print(f"步驟 1: 讀取工作表 {TARGET_SHEET} 的資料...")
    old_data = converter.read_sheet_data(TARGET_SHEET)
    
    if not old_data:
        print("沒有找到資料")
        return
    
    print(f"  找到 {len(old_data)} 行資料（包含標題）")
    
    # 步驟 2: 創建備份
    print("\n步驟 2: 創建備份...")
    backup_success = converter.create_backup_sheet(TARGET_SHEET, old_data)
    
    if not backup_success:
        print("警告: 備份失敗，是否繼續? (y/n): ", end="")
        if input().lower() != 'y':
            print("已取消操作")
            return
    
    # 步驟 3: 轉換格式
    print("\n步驟 3: 轉換為新格式並計算價格...")
    new_data = converter.convert_old_to_new_format(old_data)
    
    if not new_data:
        print("轉換失敗")
        return
    
    print(f"  成功轉換 {len(new_data)-1} 筆訂單")
    
    # 計算統計資訊
    if len(new_data) > 1:
        total_amount = 0
        for row in new_data[1:]:
            if len(row) > 8 and row[8]:
                try:
                    total_amount += int(row[8])
                except ValueError:
                    pass
        
        print(f"  總金額: ${total_amount:,}")
    
    # 步驟 4: 更新工作表
    print("\n步驟 4: 更新工作表為新格式...")
    update_success = converter.update_sheet_with_new_format(TARGET_SHEET, new_data)
    
    if update_success:
        print("\n[完成] 轉換完成！")
        print(f"  工作表 {TARGET_SHEET} 已更新為新格式")
        print("  所有訂單已自動計算價格")
        if backup_success:
            print("  原始資料已備份")
    else:
        print("\n[錯誤] 更新失敗")
        print("  請檢查 Google Sheets 權限設定")


if __name__ == "__main__":
    main()