import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import List, Dict, Any, Optional
from datetime import datetime
from .time_utils import time_utils
from .price_calculator import PriceCalculator
import logging

logger = logging.getLogger(__name__)


class GoogleSheetsClient:
    def __init__(self, credentials_path: str, sheet_id: str, auto_organize_by_date: bool = True):
        """初始化 Google Sheets 客戶端"""
        self.sheet_id = sheet_id
        self.credentials_path = credentials_path
        self.auto_organize_by_date = auto_organize_by_date
        self.service = self._build_service()
        self.sheet_cache = {}  # 快取已存在的 sheet 資訊
        self.price_calculator = PriceCalculator()  # 價格計算器
    
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
    
    def _get_sheet_title(self) -> str:
        """獲取第一個工作表的名稱"""
        try:
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()
            
            sheets = spreadsheet.get('sheets', [])
            if sheets:
                return sheets[0].get('properties', {}).get('title', 'Sheet1')
            else:
                return 'Sheet1'
        except Exception:
            return 'Sheet1'
    
    def _get_all_sheets(self) -> List[Dict[str, Any]]:
        """獲取所有工作表資訊"""
        try:
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()
            
            return spreadsheet.get('sheets', [])
        except Exception as e:
            logger.error(f"Error getting sheet list: {e}")
            return []
    
    def _get_sheet_by_name(self, sheet_name: str) -> Optional[Dict[str, Any]]:
        """根據名稱獲取工作表資訊"""
        sheets = self._get_all_sheets()
        for sheet in sheets:
            if sheet.get('properties', {}).get('title') == sheet_name:
                return sheet
        return None
    
    def _create_sheet_by_date(self, shipping_date: datetime) -> str:
        """根據出貨日期創建新的工作表"""
        if not self.service:
            return 'Sheet1'
        
        # 生成工作表名稱：YYYYMMDD_星期X
        sheet_name = time_utils.format_date_with_weekday(shipping_date, 'sheet_name')
        
        # 檢查是否已存在
        if self._get_sheet_by_name(sheet_name):
            return sheet_name
        
        try:
            # 創建新工作表
            request = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': sheet_name
                        }
                    }
                }]
            }
            
            response = self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id,
                body=request
            ).execute()
            
            # 為新工作表設置標題
            self._setup_sheet_headers(sheet_name)
            
            logger.info(f"Created new sheet: {sheet_name}")
            return sheet_name
            
        except Exception as e:
            logger.error(f"Error creating sheet {sheet_name}: {e}")
            return self._get_sheet_title()  # 返回默認工作表
    
    def _setup_sheet_headers(self, sheet_name: str) -> bool:
        """為指定工作表設置標題行"""
        if not self.service:
            return False
        
        try:
            # 設置標題
            headers = [[
                '訂購/寄件人',
                '收件人',
                '品項',
                '數量',
                '訂購人電話',
                '收件人電話',
                '地址',
                '總價',
                '付款狀況',
                '末5碼'
            ]]
            
            body = {
                'values': headers,
                'majorDimension': 'ROWS',
            }
            
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=f'{sheet_name}!A1:J1',
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            # 設定標題行格式（粗體）
            sheet_info = self._get_sheet_by_name(sheet_name)
            if sheet_info:
                sheet_id = sheet_info.get('properties', {}).get('sheetId', 0)
                
                requests = [{
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id,
                            'startRowIndex': 0,
                            'endRowIndex': 1
                        },
                        'cell': {
                            'userEnteredFormat': {
                                'textFormat': {
                                    'bold': True
                                },
                                'backgroundColor': {
                                    'red': 0.9,
                                    'green': 0.9,
                                    'blue': 0.9
                                }
                            }
                        },
                        'fields': 'userEnteredFormat.textFormat.bold,userEnteredFormat.backgroundColor'
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
            
        except Exception as e:
            logger.error(f"Error setting up headers for sheet {sheet_name}: {e}")
            return False
    
    def _determine_target_sheet(self, order_data: Dict[str, Any]) -> str:
        """決定訂單應該寫入哪個工作表"""
        if not self.auto_organize_by_date:
            return self._get_sheet_title()
        
        # 解析出貨日期
        shipping_date_str = order_data.get('shipping_date', '')
        if not shipping_date_str:
            # 沒有指定出貨日期，使用當天
            current_time = time_utils.get_current_time()
            return self._create_sheet_by_date(current_time)
        
        # 解析出貨日期
        shipping_date = time_utils.parse_shipping_date(shipping_date_str)
        if shipping_date:
            return self._create_sheet_by_date(shipping_date)
        else:
            # 解析失敗，使用默認工作表
            logger.warning(f"Failed to parse shipping date: {shipping_date_str}")
            return self._get_sheet_title()
    
    def append_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """將訂單資料添加到試算表（支援單一訂單和多訂單，按日期自動分組）"""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available'
            }
        
        try:
            # 決定目標工作表
            target_sheet = self._determine_target_sheet(order_data)
            
            # 格式化出貨日期（包含星期）
            shipping_date_str = order_data.get('shipping_date', '')
            formatted_shipping_date = ''
            
            if shipping_date_str:
                parsed_date = time_utils.parse_shipping_date(shipping_date_str)
                if parsed_date:
                    formatted_shipping_date = time_utils.format_date_with_weekday(parsed_date, 'standard')
                else:
                    formatted_shipping_date = shipping_date_str
            
            # 準備要寫入的資料
            values = [[
                order_data.get('sender_name', ''),  # 訂購/寄件人
                order_data.get('receiver_name', ''),  # 收件人
                self._format_items_name_only(order_data.get('items', [])),  # 品項
                self._format_items_quantity_only(order_data.get('items', [])),  # 數量
                order_data.get('sender_phone', ''),  # 訂購人電話
                order_data.get('receiver_phone', ''),  # 收件人電話
                order_data.get('shipping_address', ''),  # 地址
                self._calculate_total_price(order_data.get('items', [])),  # 總價
                order_data.get('payment_status', ''),  # 付款狀況
                order_data.get('last_5_digits', '')  # 末5碼
            ]]
            
            # 指定寫入範圍（A:J 表示從 A 欄到 J 欄）
            range_name = f'{target_sheet}!A:J'
            
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
                'order_id': order_data.get('order_id', ''),
                'target_sheet': target_sheet
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
    
    def _format_items_name_only(self, items: List[Dict[str, Any]]) -> str:
        """格式化商品名稱（僅名稱，不含數量）"""
        if not items:
            return ''
        
        names = []
        for item in items:
            name = item.get('name', '')
            if name:
                names.append(name)
        
        return ', '.join(names)
    
    def _format_items_quantity_only(self, items: List[Dict[str, Any]]) -> str:
        """格式化商品數量（僅數量）"""
        if not items:
            return ''
        
        quantities = []
        for item in items:
            quantity = item.get('quantity', 0)
            quantities.append(str(quantity))
        
        return ', '.join(quantities)
    
    def _calculate_total_price(self, items: List[Dict[str, Any]]) -> str:
        """計算商品總價（使用價格計算器）"""
        if not items:
            return '0'
        
        try:
            total_price, detail = self.price_calculator.calculate_total_price(items)
            return str(total_price)
        except Exception as e:
            logger.error(f"Error calculating price: {e}")
            return '計算錯誤'
    
    def append_multiple_orders(self, orders_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量添加多份訂單到試算表（按日期自動分組到不同 sheet）"""
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
        
        # 如果不自動分組，使用原來的批量處理方式
        if not self.auto_organize_by_date:
            return self._append_multiple_orders_to_single_sheet(orders_data)
        
        # 按日期分組訂單
        try:
            grouped_orders = {}
            order_ids = []
            current_time = time_utils.get_current_time()
            
            for order_data in orders_data:
                # 決定目標工作表
                target_sheet = self._determine_target_sheet(order_data)
                
                if target_sheet not in grouped_orders:
                    grouped_orders[target_sheet] = []
                
                # 格式化出貨日期（包含星期）
                shipping_date_str = order_data.get('shipping_date', '')
                formatted_shipping_date = ''
                
                if shipping_date_str:
                    parsed_date = time_utils.parse_shipping_date(shipping_date_str)
                    if parsed_date:
                        formatted_shipping_date = time_utils.format_date_with_weekday(parsed_date, 'standard')
                    else:
                        formatted_shipping_date = shipping_date_str
                
                # 準備該訂單的資料行
                row = [
                    order_data.get('sender_name', ''),  # 訂購/寄件人
                    order_data.get('receiver_name', ''),  # 收件人
                    self._format_items_name_only(order_data.get('items', [])),  # 品項
                    self._format_items_quantity_only(order_data.get('items', [])),  # 數量
                    order_data.get('sender_phone', ''),  # 訂購人電話
                    order_data.get('receiver_phone', ''),  # 收件人電話
                    order_data.get('shipping_address', ''),  # 地址
                    self._calculate_total_price(order_data.get('items', [])),  # 總價
                    order_data.get('payment_status', ''),  # 付款狀況
                    order_data.get('last_5_digits', '')  # 末5碼
                ]
                
                grouped_orders[target_sheet].append(row)
                order_ids.append(order_data.get('order_id', ''))
            
            # 批量寫入各個工作表
            total_processed = 0
            sheet_results = {}
            
            for sheet_name, sheet_orders in grouped_orders.items():
                range_name = f'{sheet_name}!A:J'
                
                body = {
                    'values': sheet_orders,
                    'majorDimension': 'ROWS',
                }
                
                result = self.service.spreadsheets().values().append(
                    spreadsheetId=self.sheet_id,
                    range=range_name,
                    valueInputOption='USER_ENTERED',
                    body=body
                ).execute()
                
                sheet_results[sheet_name] = {
                    'updated_rows': result.get('updates', {}).get('updatedRows', 0),
                    'order_count': len(sheet_orders)
                }
                total_processed += len(sheet_orders)
            
            return {
                'success': True,
                'total_processed': total_processed,
                'order_ids': order_ids,
                'sheet_results': sheet_results,
                'sheets_used': list(grouped_orders.keys())
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
    
    def _append_multiple_orders_to_single_sheet(self, orders_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量添加多份訂單到單一試算表（不按日期分組）"""
        try:
            # 準備批量資料
            values = []
            order_ids = []
            current_time = time_utils.get_current_time()
            
            for order_data in orders_data:
                # 格式化出貨日期（包含星期）
                shipping_date_str = order_data.get('shipping_date', '')
                formatted_shipping_date = ''
                
                if shipping_date_str:
                    parsed_date = time_utils.parse_shipping_date(shipping_date_str)
                    if parsed_date:
                        formatted_shipping_date = time_utils.format_date_with_weekday(parsed_date, 'standard')
                    else:
                        formatted_shipping_date = shipping_date_str
                
                row = [
                    order_data.get('sender_name', ''),  # 訂購/寄件人
                    order_data.get('receiver_name', ''),  # 收件人
                    self._format_items_name_only(order_data.get('items', [])),  # 品項
                    self._format_items_quantity_only(order_data.get('items', [])),  # 數量
                    order_data.get('sender_phone', ''),  # 訂購人電話
                    order_data.get('receiver_phone', ''),  # 收件人電話
                    order_data.get('shipping_address', ''),  # 地址
                    self._calculate_total_price(order_data.get('items', [])),  # 總價
                    order_data.get('payment_status', ''),  # 付款狀況
                    order_data.get('last_5_digits', '')  # 末5碼
                ]
                values.append(row)
                order_ids.append(order_data.get('order_id', ''))
            
            # 指定寫入範圍（A:K 表示從 A 欄到 K 欄）
            sheet_title = self._get_sheet_title()
            range_name = f'{sheet_title}!A:K'
            
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
            # 先獲取工作表資訊
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()
            
            sheets = spreadsheet.get('sheets', [])
            if sheets:
                sheet_title = sheets[0].get('properties', {}).get('title', 'Sheet1')
            else:
                sheet_title = 'Sheet1'
            
            # 檢查第一行是否有標題
            range_name = f'{sheet_title}!A1:K1'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            # 如果沒有標題，則添加
            if not values:
                headers = [[
                    '訂購/寄件人',
                    '寄件地址',
                    '收件人',
                    '品項',
                    '數量',
                    '訂購人電話',
                    '收件人電話',
                    '地址',
                    '總價',
                    '付款狀況',
                    '末5碼'
                ]]
                
                body = {
                    'values': headers,
                    'majorDimension': 'ROWS',
                }
                
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=f'{sheet_title}!A1:K1',
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
            sheet_title = self._get_sheet_title()
            range_name = f'{sheet_title}!A:K'
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
                    'sender_name': row[0],     # 訂購/寄件人
                    'sender_address': row[1],  # 寄件地址
                    'receiver_name': row[2],   # 收件人
                    'items_name': row[3],      # 品項
                    'items_quantity': row[4],  # 數量
                    'sender_phone': row[5],    # 訂購人電話
                    'receiver_phone': row[6],  # 收件人電話
                    'shipping_address': row[7], # 地址
                    'total_price': row[8],     # 總價
                    'payment_status': row[9],  # 付款狀況
                    'last_5_digits': row[10]   # 末5碼
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
            # 使用helper方法獲取工作表名稱
            sheet_title = self._get_sheet_title()
            range_name = f'{sheet_title}!A1:A1'
            
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
    
    def get_sheets_summary(self) -> Dict[str, Any]:
        """獲取所有工作表的摘要資訊"""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available'
            }
        
        try:
            sheets = self._get_all_sheets()
            summary = {
                'success': True,
                'total_sheets': len(sheets),
                'sheets': []
            }
            
            for sheet in sheets:
                sheet_info = sheet.get('properties', {})
                sheet_name = sheet_info.get('title', 'Unknown')
                
                # 嘗試獲取每個工作表的資料行數
                try:
                    range_name = f'{sheet_name}!A:A'
                    result = self.service.spreadsheets().values().get(
                        spreadsheetId=self.sheet_id,
                        range=range_name
                    ).execute()
                    
                    values = result.get('values', [])
                    row_count = len(values) - 1 if len(values) > 0 else 0  # 扣除標題行
                    
                except Exception:
                    row_count = 0
                
                summary['sheets'].append({
                    'name': sheet_name,
                    'sheet_id': sheet_info.get('sheetId'),
                    'row_count': row_count,
                    'is_date_sheet': self._is_date_sheet(sheet_name)
                })
            
            return summary
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Error getting sheets summary: {e}'
            }
    
    def _is_date_sheet(self, sheet_name: str) -> bool:
        """判斷工作表名稱是否為日期格式的工作表"""
        # 檢查是否符合 YYYYMMDD_星期X 格式
        if '_星期' in sheet_name and len(sheet_name.split('_')[0]) == 8:
            try:
                date_part = sheet_name.split('_')[0]
                datetime.strptime(date_part, '%Y%m%d')
                return True
            except ValueError:
                pass
        return False
    
    def organize_existing_orders_by_date(self, source_sheet: str = None) -> Dict[str, Any]:
        """將現有訂單按日期重新組織到不同的工作表"""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available'
            }
        
        try:
            # 確定來源工作表
            if not source_sheet:
                source_sheet = self._get_sheet_title()
            
            # 讀取來源工作表的所有資料
            range_name = f'{source_sheet}!A:K'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if len(values) <= 1:
                return {
                    'success': True,
                    'message': '沒有需要重新組織的訂單資料',
                    'processed_orders': 0
                }
            
            # 跳過標題行
            header_row = values[0]
            data_rows = values[1:]
            
            # 按出貨日期分組
            organized_orders = {}
            processed_count = 0
            
            for row in data_rows:
                if len(row) < 8:  # 確保有出貨日期欄位
                    continue
                
                # 解析出貨日期 (第8欄，索引7)
                shipping_date_str = row[7] if len(row) > 7 else ''
                
                if shipping_date_str:
                    # 嘗試從已格式化的日期中提取
                    parsed_date = None
                    
                    # 如果是 YYYY-MM-DD(星期X) 格式
                    if '(' in shipping_date_str and ')' in shipping_date_str:
                        date_part = shipping_date_str.split('(')[0]
                        try:
                            parsed_date = datetime.strptime(date_part, '%Y-%m-%d')
                        except ValueError:
                            pass
                    
                    # 如果是標準 YYYY-MM-DD 格式
                    if not parsed_date:
                        parsed_date = time_utils.parse_shipping_date(shipping_date_str)
                    
                    if parsed_date:
                        sheet_name = time_utils.format_date_with_weekday(parsed_date, 'sheet_name')
                        
                        if sheet_name not in organized_orders:
                            organized_orders[sheet_name] = []
                        
                        organized_orders[sheet_name].append(row)
                        processed_count += 1
            
            # 建立新的工作表並寫入資料
            created_sheets = []
            
            for sheet_name, orders in organized_orders.items():
                # 建立工作表（如果不存在）
                if not self._get_sheet_by_name(sheet_name):
                    self._create_sheet_by_date(
                        datetime.strptime(sheet_name.split('_')[0], '%Y%m%d')
                    )
                    created_sheets.append(sheet_name)
                
                # 寫入資料到目標工作表
                range_name = f'{sheet_name}!A:J'
                body = {
                    'values': orders,
                    'majorDimension': 'ROWS',
                }
                
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.sheet_id,
                    range=range_name,
                    valueInputOption='USER_ENTERED',
                    body=body
                ).execute()
            
            return {
                'success': True,
                'processed_orders': processed_count,
                'created_sheets': created_sheets,
                'organized_sheets': list(organized_orders.keys()),
                'message': f'成功重新組織 {processed_count} 份訂單到 {len(organized_orders)} 個工作表'
            }
            
        except Exception as e:
            logger.error(f"Error organizing existing orders: {e}")
            return {
                'success': False,
                'error': f'重新組織訂單時發生錯誤: {e}'
            }
    
    def get_orders_by_date(self, target_date: str) -> Dict[str, Any]:
        """根據日期獲取訂單資料
        
        Args:
            target_date: 目標日期，格式如 '08-27', '2024-08-27' 等
            
        Returns:
            Dict containing success status and orders data
        """
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available',
                'orders': []
            }
        
        try:
            from .time_utils import time_utils
            
            # 解析目標日期
            parsed_date = time_utils.parse_shipping_date(target_date)
            if not parsed_date:
                return {
                    'success': False,
                    'error': f'無法解析日期格式: {target_date}',
                    'orders': []
                }
            
            # 生成可能的工作表名稱
            target_sheet_name = time_utils.format_date_with_weekday(parsed_date, 'sheet_name')
            
            # 先嘗試從特定日期的工作表讀取
            orders = []
            found_sheet = False
            
            # 檢查是否存在對應的日期工作表
            if self._get_sheet_by_name(target_sheet_name):
                found_sheet = True
                sheet_orders = self._get_orders_from_sheet(target_sheet_name, target_date)
                orders.extend(sheet_orders)
            
            # 如果沒有找到特定工作表，或需要搜尋所有工作表
            if not found_sheet or not orders:
                # 搜尋所有工作表
                all_sheets = self._get_all_sheets()
                for sheet in all_sheets:
                    sheet_name = sheet.get('properties', {}).get('title', '')
                    if sheet_name != target_sheet_name:  # 避免重複搜尋
                        sheet_orders = self._get_orders_from_sheet(sheet_name, target_date)
                        orders.extend(sheet_orders)
            
            return {
                'success': True,
                'orders': orders,
                'target_date': target_date,
                'formatted_date': time_utils.format_date_with_weekday(parsed_date, 'standard'),
                'sheet_searched': target_sheet_name if found_sheet else 'all_sheets'
            }
            
        except Exception as e:
            logger.error(f"Error getting orders by date {target_date}: {e}")
            return {
                'success': False,
                'error': f'查詢日期訂單時發生錯誤: {e}',
                'orders': []
            }
    
    def _get_orders_from_sheet(self, sheet_name: str, target_date: str) -> List[Dict[str, Any]]:
        """從指定工作表中獲取特定日期的訂單"""
        orders = []
        
        try:
            # 讀取工作表資料
            range_name = f'{sheet_name}!A:K'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if len(values) <= 1:  # 只有標題行或空白
                return orders
            
            # 跳過標題行
            data_rows = values[1:]
            
            for row in data_rows:
                if len(row) < 8:  # 確保有足夠的欄位
                    continue
                
                # 由於新的欄位結構沒有出貨日期，我們改為檢查地址欄位來判斷是否為有效記錄
                # 如果有地址就視為有效訂單（暫時的解決方案）
                shipping_address = row[7] if len(row) > 7 else ''
                
                # 暫時移除日期匹配，因為新結構沒有日期欄位
                # TODO: 需要重新設計日期匹配邏輯
                if shipping_address:  # 有地址就算是有效訂單
                    # 解析訂單資料
                    order = {
                        'sender_name': row[0] if len(row) > 0 else '',     # 訂購/寄件人
                        'sender_address': row[1] if len(row) > 1 else '',  # 寄件地址
                        'receiver_name': row[2] if len(row) > 2 else '',   # 收件人
                        'items_name': row[3] if len(row) > 3 else '',      # 品項
                        'items_quantity': row[4] if len(row) > 4 else '',  # 數量
                        'sender_phone': row[5] if len(row) > 5 else '',    # 訂購人電話
                        'receiver_phone': row[6] if len(row) > 6 else '',  # 收件人電話
                        'shipping_address': row[7] if len(row) > 7 else '', # 地址
                        'total_price': row[8] if len(row) > 8 else '',     # 總價
                        'payment_status': row[9] if len(row) > 9 else '',  # 付款狀況
                        'last_5_digits': row[10] if len(row) > 10 else '', # 末5碼
                        'source_sheet': sheet_name
                    }
                    orders.append(order)
            
        except Exception as e:
            logger.error(f"Error reading orders from sheet {sheet_name}: {e}")
        
        return orders
    
    def _date_matches_target(self, shipping_date: str, target_date: str) -> bool:
        """檢查出貨日期是否符合目標日期"""
        if not shipping_date:
            return False
        
        try:
            from .time_utils import time_utils
            
            # 解析目標日期
            target_parsed = time_utils.parse_shipping_date(target_date)
            if not target_parsed:
                return False
            
            # 解析出貨日期
            # 處理格式如 "2024-08-27(星期二)" 的情況
            clean_shipping_date = shipping_date
            if '(' in shipping_date and ')' in shipping_date:
                clean_shipping_date = shipping_date.split('(')[0]
            
            shipping_parsed = time_utils.parse_shipping_date(clean_shipping_date)
            if not shipping_parsed:
                return False
            
            # 比較日期（只比較年月日，忽略時間）
            return (target_parsed.year == shipping_parsed.year and
                   target_parsed.month == shipping_parsed.month and
                   target_parsed.day == shipping_parsed.day)
            
        except Exception as e:
            logger.error(f"Error matching dates: {shipping_date} vs {target_date}: {e}")
            return False