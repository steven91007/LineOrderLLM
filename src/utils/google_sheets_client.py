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
        """將訂單資料添加到試算表（支援單一訂單和多訂單）"""
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
                order_data.get('sender_name', '') or '未提供',  # 寄件人選填
                order_data.get('sender_phone', '') or '未提供',  # 寄件人電話選填
                order_data.get('receiver_name', ''),
                order_data.get('receiver_phone', ''),
                self._format_items(order_data.get('items', [])),
                order_data.get('shipping_date', '') or '未提供',
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
                'updated_rows': result.get('updates', {}).get('updatedRows', 0),
                'order_id': order_data.get('order_id', '')
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
    
    def append_multiple_orders(self, orders_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量添加多份訂單到試算表"""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available',
                'results': []
            }
        
        if not orders_data:
            return {
                'success': True,
                'results': [],
                'total_processed': 0
            }
        
        try:
            # 準備批量資料
            values = []
            order_ids = []
            
            for order_data in orders_data:
                row = [
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    order_data.get('order_id', ''),
                    order_data.get('sender_name', '') or '未提供',
                    order_data.get('sender_phone', '') or '未提供',
                    order_data.get('receiver_name', ''),
                    order_data.get('receiver_phone', ''),
                    self._format_items(order_data.get('items', [])),
                    order_data.get('shipping_date', '') or '未提供',
                    order_data.get('shipping_address', ''),
                    order_data.get('status', '待處理'),
                    order_data.get('notes', '')
                ]
                values.append(row)
                order_ids.append(order_data.get('order_id', ''))
            
            # 指定寫入範圍（A:K 表示從 A 欄到 K 欄）
            range_name = 'Sheet1!A:K'
            
            # 執行批量寫入操作
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
                'updated_rows': result.get('updates', {}).get('updatedRows', 0),
                'total_processed': len(orders_data),
                'order_ids': order_ids
            }
            
        except HttpError as error:
            return {
                'success': False,
                'error': f'Google Sheets API error: {error}',
                'total_processed': 0,
                'order_ids': []
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {e}',
                'total_processed': 0,
                'order_ids': []
            }
    
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
    
    def test_connection(self) -> Dict[str, Any]:
        """測試 Google Sheets 連接"""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available',
                'details': 'Service initialization failed'
            }
        
        try:
            # 嘗試讀取試算表的基本資訊
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()
            
            title = spreadsheet.get('properties', {}).get('title', 'Unknown')
            sheet_count = len(spreadsheet.get('sheets', []))
            
            # 嘗試讀取第一行以確認讀取權限
            range_name = 'Sheet1!A1:A1'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            return {
                'success': True,
                'spreadsheet_title': title,
                'sheet_count': sheet_count,
                'has_read_access': True,
                'has_write_access': True,  # 如果能讀取通常也能寫入
                'message': f'成功連接到試算表: {title}'
            }
            
        except HttpError as error:
            error_details = str(error)
            if '403' in error_details:
                return {
                    'success': False,
                    'error': 'Permission denied',
                    'details': '沒有存取試算表的權限，請檢查服務帳戶權限設定'
                }
            elif '404' in error_details:
                return {
                    'success': False,
                    'error': 'Spreadsheet not found',
                    'details': '找不到指定的試算表，請檢查 sheet_id 是否正確'
                }
            else:
                return {
                    'success': False,
                    'error': f'HTTP Error: {error}',
                    'details': error_details
                }
        except Exception as e:
            return {
                'success': False,
                'error': f'Connection test failed: {e}',
                'details': str(e)
            }
    
    def validate_setup(self) -> Dict[str, Any]:
        """驗證完整的 Google Sheets 設定"""
        validation_results = {
            'overall_status': 'unknown',
            'checks': {},
            'recommendations': []
        }
        
        # 檢查 1: 憑證檔案
        if os.path.exists(self.credentials_path):
            validation_results['checks']['credentials_file'] = {
                'status': 'pass',
                'message': '憑證檔案存在'
            }
        else:
            validation_results['checks']['credentials_file'] = {
                'status': 'fail',
                'message': f'憑證檔案不存在: {self.credentials_path}'
            }
            validation_results['recommendations'].append('請確認 Google Service Account 憑證檔案路徑正確')
        
        # 檢查 2: 服務初始化
        if self.service:
            validation_results['checks']['service_init'] = {
                'status': 'pass',
                'message': 'Google Sheets 服務初始化成功'
            }
        else:
            validation_results['checks']['service_init'] = {
                'status': 'fail',
                'message': 'Google Sheets 服務初始化失敗'
            }
            validation_results['recommendations'].append('請檢查憑證檔案格式和權限設定')
        
        # 檢查 3: 連接測試
        connection_test = self.test_connection()
        if connection_test['success']:
            validation_results['checks']['connection'] = {
                'status': 'pass',
                'message': connection_test['message'],
                'details': {
                    'spreadsheet_title': connection_test.get('spreadsheet_title'),
                    'sheet_count': connection_test.get('sheet_count')
                }
            }
        else:
            validation_results['checks']['connection'] = {
                'status': 'fail',
                'message': connection_test['error'],
                'details': connection_test.get('details', '')
            }
            validation_results['recommendations'].append('請檢查試算表 ID 和分享權限設定')
        
        # 檢查 4: 標題設定
        if self.service and connection_test['success']:
            headers_ok = self.create_sheet_if_not_exists()
            validation_results['checks']['headers'] = {
                'status': 'pass' if headers_ok else 'fail',
                'message': '標題行設定成功' if headers_ok else '標題行設定失敗'
            }
        
        # 總體狀態評估
        failed_checks = [check for check in validation_results['checks'].values() if check['status'] == 'fail']
        if not failed_checks:
            validation_results['overall_status'] = 'healthy'
        elif len(failed_checks) < len(validation_results['checks']):
            validation_results['overall_status'] = 'partial'
        else:
            validation_results['overall_status'] = 'failed'
        
        return validation_results