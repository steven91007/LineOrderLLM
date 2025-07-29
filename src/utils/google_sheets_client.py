import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict, Any, Optional
from datetime import datetime


class GoogleSheetsClient:
    def __init__(self, credentials_path: str, sheet_id: str):
        """初始化 Google Sheets 客戶端"""
        self.sheet_id = sheet_id
        self.credentials_path = credentials_path
        self.service = self._build_service()
    
    def _build_service(self):
        """建立 Google Sheets API 服務"""
        try:
            # 設定權限範圍
            SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
            
            # 載入服務帳戶憑證
            credentials = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=SCOPES
            )
            
            # 建立服務
            service = build('sheets', 'v4', credentials=credentials)
            return service
        except Exception as e:
            print(f"Error building Google Sheets service: {e}")
            return None
    
    def append_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """將訂單資料添加到試算表"""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available'
            }
        
        try:
            # 準備要寫入的資料
            values = [[
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # 訂單時間
                order_data.get('order_id', ''),
                order_data.get('sender_name', ''),
                order_data.get('sender_phone', ''),
                order_data.get('receiver_name', ''),
                order_data.get('receiver_phone', ''),
                self._format_items(order_data.get('items', [])),
                order_data.get('shipping_date', ''),
                order_data.get('shipping_address', ''),
                order_data.get('status', '待處理'),
                order_data.get('notes', '')
            ]]
            
            # 指定寫入範圍（A:K 表示從 A 欄到 K 欄）
            range_name = 'Sheet1!A:K'
            
            # 執行寫入操作
            body = {
                'values': values,
                'majorDimension': 'ROWS',
            }
            
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=range_name,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            return {
                'success': True,
                'updated_cells': result.get('updates', {}).get('updatedCells', 0),
                'updated_rows': result.get('updates', {}).get('updatedRows', 0)
            }
            
        except HttpError as error:
            return {
                'success': False,
                'error': f'Google Sheets API error: {error}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {e}'
            }
    
    def _format_items(self, items: List[Dict[str, Any]]) -> str:
        """格式化商品項目為字串"""
        if not items:
            return ''
        
        formatted_items = []
        for item in items:
            name = item.get('name', '')
            quantity = item.get('quantity', 0)
            formatted_items.append(f"{name} x {quantity}")
        
        return ', '.join(formatted_items)
    
    def create_sheet_if_not_exists(self) -> bool:
        """確保試算表存在並有正確的標題"""
        if not self.service:
            return False
        
        try:
            # 檢查第一行是否有標題
            range_name = 'Sheet1!A1:K1'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            # 如果沒有標題，則添加
            if not values:
                headers = [[
                    '訂單時間',
                    '訂單編號',
                    '寄件人',
                    '寄件人電話',
                    '收件人',
                    '收件人電話',
                    '商品明細',
                    '預計發貨日',
                    '收件地址',
                    '訂單狀態',
                    '備註'
                ]]
                
                body = {
                    'values': headers,
                    'majorDimension': 'ROWS',
                }
                
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range='Sheet1!A1:K1',
                    valueInputOption='USER_ENTERED',
                    body=body
                ).execute()
                
                # 設定標題行格式（粗體）
                requests = [{
                    'repeatCell': {
                        'range': {
                            'sheetId': 0,
                            'startRowIndex': 0,
                            'endRowIndex': 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'textFormat': {
                                    'bold': True
                                }
                            }
                        },
                        'fields': 'userEnteredFormat.textFormat.bold'
                    }
                }]
                
                body = {
                    'requests': requests
                }
                
                self.service.spreadsheets().batchUpdate(
                    spreadsheetId=self.sheet_id,
                    body=body
                ).execute()
                
                return True
            
            return True
            
        except Exception as e:
            print(f"Error creating sheet headers: {e}")
            return False
    
    def get_recent_orders(self, limit: int = 10) -> Dict[str, Any]:
        """獲取最近的訂單記錄"""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available',
                'orders': []
            }
        
        try:
            # 獲取所有資料
            range_name = 'Sheet1!A:K'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                return {
                    'success': True,
                    'orders': []
                }
            
            # 跳過標題行，取最後 N 筆資料
            orders = []
            data_rows = values[1:] if len(values) > 1 else []
            recent_rows = data_rows[-limit:] if len(data_rows) > limit else data_rows
            
            for row in recent_rows:
                # 確保每行有足夠的欄位
                while len(row) < 11:
                    row.append('')
                
                orders.append({
                    'order_time': row[0],
                    'order_id': row[1],
                    'sender_name': row[2],
                    'sender_phone': row[3],
                    'receiver_name': row[4],
                    'receiver_phone': row[5],
                    'items': row[6],
                    'shipping_date': row[7],
                    'shipping_address': row[8],
                    'status': row[9],
                    'notes': row[10]
                })
            
            return {
                'success': True,
                'orders': orders
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Error fetching orders: {e}',
                'orders': []
            }