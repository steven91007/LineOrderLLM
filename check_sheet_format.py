"""
檢查 Google Sheets 工作表格式
"""

import os
import sys

# 添加專案路徑到 Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

def check_sheet_format():
    """檢查工作表格式"""
    
    # 設定參數
    CREDENTIALS_PATH = 'aesthetic-rush-323802-7f5591bc4a1c_1.json'
    SHEET_ID = '1i7wDoTR50lIwnlY53u6jBbJ_ZgbREuyj2MWX6lHkjxw'
    TARGET_SHEET = "20250824_星期日"
    
    try:
        # 建立服務
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        credentials = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=credentials)
        
        # 讀取工作表資料
        range_name = f'{TARGET_SHEET}!A:Z'
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=range_name
        ).execute()
        
        values = result.get('values', [])
        
        if not values:
            print("沒有找到資料")
            return
        
        print(f"工作表 {TARGET_SHEET} 格式檢查：")
        print(f"總行數: {len(values)}")
        
        # 顯示標題行
        if len(values) > 0:
            headers = values[0]
            print(f"標題行（{len(headers)} 欄）:")
            for i, header in enumerate(headers):
                print(f"  {i}: {header}")
        
        # 顯示前幾行資料
        print("\n前 3 行資料內容：")
        for i in range(min(4, len(values))):
            row = values[i]
            print(f"第 {i+1} 行（{len(row)} 欄）:")
            for j, cell in enumerate(row):
                print(f"  [{j}]: {cell}")
            print()
            
    except Exception as e:
        print(f"錯誤: {e}")

if __name__ == "__main__":
    check_sheet_format()