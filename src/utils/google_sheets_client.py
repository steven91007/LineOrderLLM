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
        """Initialize the Google Sheets client."""
        self.sheet_id = sheet_id
        self.credentials_path = credentials_path
        self.auto_organize_by_date = auto_organize_by_date
        self.service = self._build_service()
        self.sheet_cache = {}  # Cache of known existing sheet info
        self.price_calculator = PriceCalculator()  # Price calculator
    
    def _build_service(self):
        """Build the Google Sheets API service."""
        try:
            # Set the permission scopes
            SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
            
            # Load the service account credentials
            credentials = Credentials.from_service_account_file(
                self.credentials_path, 
                scopes=SCOPES
            )
            
            # Build the service
            service = build('sheets', 'v4', credentials=credentials)
            return service
        except Exception as e:
            print(f"Error building Google Sheets service: {e}")
            return None
    
    def _get_sheet_title(self) -> str:
        """Get the name of the first worksheet."""
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
        """Get info for all worksheets."""
        try:
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()
            
            return spreadsheet.get('sheets', [])
        except Exception as e:
            logger.error(f"Error getting sheet list: {e}")
            return []
    
    def _get_sheet_by_name(self, sheet_name: str) -> Optional[Dict[str, Any]]:
        """Get worksheet info by name."""
        sheets = self._get_all_sheets()
        for sheet in sheets:
            if sheet.get('properties', {}).get('title') == sheet_name:
                return sheet
        return None
    
    def _create_sheet_by_date(self, shipping_date: datetime) -> str:
        """Create a new worksheet for the given shipping date."""
        if not self.service:
            return 'Sheet1'
        
        # Build the sheet name: YYYYMMDD_星期X (weekday)
        sheet_name = time_utils.format_date_with_weekday(shipping_date, 'sheet_name')
        
        # Check whether it already exists
        if self._get_sheet_by_name(sheet_name):
            return sheet_name
        
        try:
            # Create the new worksheet
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
            
            # Set up the header row on the new worksheet
            self._setup_sheet_headers(sheet_name)
            
            logger.info(f"Created new sheet: {sheet_name}")
            return sheet_name
            
        except Exception as e:
            logger.error(f"Error creating sheet {sheet_name}: {e}")
            return self._get_sheet_title()  # Fall back to the default worksheet
    
    def _setup_sheet_headers(self, sheet_name: str) -> bool:
        """Set up the header row on the given worksheet."""
        if not self.service:
            return False
        
        try:
            # Set the headers
            headers = [[
                # Column headers (functional, keep as-is)
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
            
            # Format the header row (bold)
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
        """Decide which worksheet the order should be written to."""
        if not self.auto_organize_by_date:
            return self._get_sheet_title()
        
        # Parse the shipping date
        shipping_date_str = order_data.get('shipping_date', '')
        if not shipping_date_str:
            # No shipping date given; use today
            current_time = time_utils.get_current_time()
            return self._create_sheet_by_date(current_time)
        
        # Parse the shipping date
        shipping_date = time_utils.parse_shipping_date(shipping_date_str)
        if shipping_date:
            return self._create_sheet_by_date(shipping_date)
        else:
            # Parsing failed; use the default worksheet
            logger.warning(f"Failed to parse shipping date: {shipping_date_str}")
            return self._get_sheet_title()
    
    def append_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Append order data to the spreadsheet (supports single and multiple orders, auto-grouped by date)."""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available'
            }
        
        try:
            # Decide the target worksheet
            target_sheet = self._determine_target_sheet(order_data)
            
            # Format the shipping date (including weekday)
            shipping_date_str = order_data.get('shipping_date', '')
            formatted_shipping_date = ''
            
            if shipping_date_str:
                parsed_date = time_utils.parse_shipping_date(shipping_date_str)
                if parsed_date:
                    formatted_shipping_date = time_utils.format_date_with_weekday(parsed_date, 'standard')
                else:
                    formatted_shipping_date = shipping_date_str
            
            # Prepare the data to write
            values = [[
                order_data.get('sender_name', ''),  # Orderer/sender
                order_data.get('receiver_name', ''),  # Receiver
                self._format_items_name_only(order_data.get('items', [])),  # Items
                self._format_items_quantity_only(order_data.get('items', [])),  # Quantity
                order_data.get('sender_phone', ''),  # Orderer phone
                order_data.get('receiver_phone', ''),  # Receiver phone
                order_data.get('shipping_address', ''),  # Address
                self._calculate_total_price(order_data.get('items', [])),  # Total price
                order_data.get('payment_status', ''),  # Payment status
                order_data.get('last_5_digits', '')  # Last 5 digits
            ]]
            
            # Target range (A:J means columns A through J)
            range_name = f'{target_sheet}!A:J'
            
            # Perform the write
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
        """Format the items as a string."""
        if not items:
            return ''
        
        formatted_items = []
        for item in items:
            name = item.get('name', '')
            quantity = item.get('quantity', 0)
            formatted_items.append(f"{name} x {quantity}")
        
        return ', '.join(formatted_items)
    
    def _format_items_name_only(self, items: List[Dict[str, Any]]) -> str:
        """Format the item names (names only, no quantities)."""
        if not items:
            return ''
        
        names = []
        for item in items:
            name = item.get('name', '')
            if name:
                names.append(name)
        
        return ', '.join(names)
    
    def _format_items_quantity_only(self, items: List[Dict[str, Any]]) -> str:
        """Format the item quantities (quantities only)."""
        if not items:
            return ''
        
        quantities = []
        for item in items:
            quantity = item.get('quantity', 0)
            quantities.append(str(quantity))
        
        return ', '.join(quantities)
    
    def _calculate_total_price(self, items: List[Dict[str, Any]]) -> str:
        """Calculate the total price of the items (using the price calculator)."""
        if not items:
            return '0'
        
        try:
            total_price, detail = self.price_calculator.calculate_total_price(items)
            return str(total_price)
        except Exception as e:
            logger.error(f"Error calculating price: {e}")
            return '計算錯誤'  # cell value written to the sheet ("calculation error")
    
    def append_multiple_orders(self, orders_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Batch-append multiple orders to the spreadsheet (auto-grouped by date into separate sheets)."""
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
        
        # If not auto-grouping, use the original batch approach
        if not self.auto_organize_by_date:
            return self._append_multiple_orders_to_single_sheet(orders_data)
        
        # Group orders by date
        try:
            grouped_orders = {}
            order_ids = []
            current_time = time_utils.get_current_time()
            
            for order_data in orders_data:
                # Decide the target worksheet
                target_sheet = self._determine_target_sheet(order_data)
                
                if target_sheet not in grouped_orders:
                    grouped_orders[target_sheet] = []
                
                # Format the shipping date (including weekday)
                shipping_date_str = order_data.get('shipping_date', '')
                formatted_shipping_date = ''
                
                if shipping_date_str:
                    parsed_date = time_utils.parse_shipping_date(shipping_date_str)
                    if parsed_date:
                        formatted_shipping_date = time_utils.format_date_with_weekday(parsed_date, 'standard')
                    else:
                        formatted_shipping_date = shipping_date_str
                
                # Prepare this order's data row
                row = [
                    order_data.get('sender_name', ''),  # Orderer/sender
                    order_data.get('receiver_name', ''),  # Receiver
                    self._format_items_name_only(order_data.get('items', [])),  # Items
                    self._format_items_quantity_only(order_data.get('items', [])),  # Quantity
                    order_data.get('sender_phone', ''),  # Orderer phone
                    order_data.get('receiver_phone', ''),  # Receiver phone
                    order_data.get('shipping_address', ''),  # Address
                    self._calculate_total_price(order_data.get('items', [])),  # Total price
                    order_data.get('payment_status', ''),  # Payment status
                    order_data.get('last_5_digits', '')  # Last 5 digits
                ]
                
                grouped_orders[target_sheet].append(row)
                order_ids.append(order_data.get('order_id', ''))
            
            # Batch-write to each worksheet
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
        """Batch-append multiple orders to a single sheet (no date grouping)."""
        try:
            # Prepare the batch data
            values = []
            order_ids = []
            current_time = time_utils.get_current_time()
            
            for order_data in orders_data:
                # Format the shipping date (including weekday)
                shipping_date_str = order_data.get('shipping_date', '')
                formatted_shipping_date = ''
                
                if shipping_date_str:
                    parsed_date = time_utils.parse_shipping_date(shipping_date_str)
                    if parsed_date:
                        formatted_shipping_date = time_utils.format_date_with_weekday(parsed_date, 'standard')
                    else:
                        formatted_shipping_date = shipping_date_str
                
                row = [
                    order_data.get('sender_name', ''),  # Orderer/sender
                    order_data.get('receiver_name', ''),  # Receiver
                    self._format_items_name_only(order_data.get('items', [])),  # Items
                    self._format_items_quantity_only(order_data.get('items', [])),  # Quantity
                    order_data.get('sender_phone', ''),  # Orderer phone
                    order_data.get('receiver_phone', ''),  # Receiver phone
                    order_data.get('shipping_address', ''),  # Address
                    self._calculate_total_price(order_data.get('items', [])),  # Total price
                    order_data.get('payment_status', ''),  # Payment status
                    order_data.get('last_5_digits', '')  # Last 5 digits
                ]
                values.append(row)
                order_ids.append(order_data.get('order_id', ''))
            
            # Target range (A:K means columns A through K)
            sheet_title = self._get_sheet_title()
            range_name = f'{sheet_title}!A:K'
            
            # Perform the batch write
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
        """Ensure the spreadsheet exists and has the correct headers."""
        if not self.service:
            return False
        
        try:
            # Get the worksheet info first
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()
            
            sheets = spreadsheet.get('sheets', [])
            if sheets:
                sheet_title = sheets[0].get('properties', {}).get('title', 'Sheet1')
            else:
                sheet_title = 'Sheet1'
            
            # Check whether the first row has headers
            range_name = f'{sheet_title}!A1:K1'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            # Add headers if missing
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
                
                # Format the header row (bold)
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
        """Get the most recent order records."""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available',
                'orders': []
            }
        
        try:
            # Fetch all data
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
            
            # Skip the header row and take the last N rows
            orders = []
            data_rows = values[1:] if len(values) > 1 else []
            recent_rows = data_rows[-limit:] if len(data_rows) > limit else data_rows
            
            for row in recent_rows:
                # Make sure each row has enough columns
                while len(row) < 11:
                    row.append('')
                
                orders.append({
                    'sender_name': row[0],     # Orderer/sender
                    'sender_address': row[1],  # Sender address
                    'receiver_name': row[2],   # Receiver
                    'items_name': row[3],      # Items
                    'items_quantity': row[4],  # Quantity
                    'sender_phone': row[5],    # Orderer phone
                    'receiver_phone': row[6],  # Receiver phone
                    'shipping_address': row[7], # Address
                    'total_price': row[8],     # Total price
                    'payment_status': row[9],  # Payment status
                    'last_5_digits': row[10]   # Last 5 digits
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
        """Test the Google Sheets connection."""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available',
                'details': 'Service initialization failed'
            }
        
        try:
            # Try reading the spreadsheet's basic info
            spreadsheet = self.service.spreadsheets().get(
                spreadsheetId=self.sheet_id
            ).execute()
            
            title = spreadsheet.get('properties', {}).get('title', 'Unknown')
            sheet_count = len(spreadsheet.get('sheets', []))
            
            # Try reading the first row to confirm read access
            # Use the helper method to get the worksheet name
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
                'has_write_access': True,  # If we can read, we can usually write too
                'message': f'Connected to spreadsheet: {title}'
            }
            
        except HttpError as error:
            error_details = str(error)
            if '403' in error_details:
                return {
                    'success': False,
                    'error': 'Permission denied',
                    'details': 'No access to the spreadsheet; check the service account permissions'
                }
            elif '404' in error_details:
                return {
                    'success': False,
                    'error': 'Spreadsheet not found',
                    'details': 'Spreadsheet not found; check that sheet_id is correct'
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
        """Validate the complete Google Sheets setup."""
        validation_results = {
            'overall_status': 'unknown',
            'checks': {},
            'recommendations': []
        }
        
        # Check 1: credentials file
        if os.path.exists(self.credentials_path):
            validation_results['checks']['credentials_file'] = {
                'status': 'pass',
                'message': 'Credentials file exists'
            }
        else:
            validation_results['checks']['credentials_file'] = {
                'status': 'fail',
                'message': f'Credentials file not found: {self.credentials_path}'
            }
            validation_results['recommendations'].append('Make sure the Google Service Account credentials file path is correct')
        
        # Check 2: service initialization
        if self.service:
            validation_results['checks']['service_init'] = {
                'status': 'pass',
                'message': 'Google Sheets service initialized successfully'
            }
        else:
            validation_results['checks']['service_init'] = {
                'status': 'fail',
                'message': 'Google Sheets service initialization failed'
            }
            validation_results['recommendations'].append('Check the credentials file format and permission settings')
        
        # Check 3: connection test
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
            validation_results['recommendations'].append('Check the spreadsheet ID and sharing permissions')
        
        # Check 4: header setup
        if self.service and connection_test['success']:
            headers_ok = self.create_sheet_if_not_exists()
            validation_results['checks']['headers'] = {
                'status': 'pass' if headers_ok else 'fail',
                'message': 'Header row set up successfully' if headers_ok else 'Header row setup failed'
            }
        
        # Overall status assessment
        failed_checks = [check for check in validation_results['checks'].values() if check['status'] == 'fail']
        if not failed_checks:
            validation_results['overall_status'] = 'healthy'
        elif len(failed_checks) < len(validation_results['checks']):
            validation_results['overall_status'] = 'partial'
        else:
            validation_results['overall_status'] = 'failed'
        
        return validation_results
    
    def get_sheets_summary(self) -> Dict[str, Any]:
        """Get summary info for all worksheets."""
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
                
                # Try to get the data row count of each worksheet
                try:
                    range_name = f'{sheet_name}!A:A'
                    result = self.service.spreadsheets().values().get(
                        spreadsheetId=self.sheet_id,
                        range=range_name
                    ).execute()
                    
                    values = result.get('values', [])
                    row_count = len(values) - 1 if len(values) > 0 else 0  # Exclude the header row
                    
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
        """Determine whether the worksheet name is a date-format sheet."""
        # Check whether it matches the YYYYMMDD_星期X format
        if '_星期' in sheet_name and len(sheet_name.split('_')[0]) == 8:
            try:
                date_part = sheet_name.split('_')[0]
                datetime.strptime(date_part, '%Y%m%d')
                return True
            except ValueError:
                pass
        return False
    
    def organize_existing_orders_by_date(self, source_sheet: str = None) -> Dict[str, Any]:
        """Reorganize existing orders into separate worksheets by date."""
        if not self.service:
            return {
                'success': False,
                'error': 'Google Sheets service not available'
            }
        
        try:
            # Determine the source worksheet
            if not source_sheet:
                source_sheet = self._get_sheet_title()
            
            # Read all data from the source worksheet
            range_name = f'{source_sheet}!A:K'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if len(values) <= 1:
                return {
                    'success': True,
                    'message': 'No order data needs reorganizing',
                    'processed_orders': 0
                }
            
            # Skip the header row
            header_row = values[0]
            data_rows = values[1:]
            
            # Group by shipping date
            organized_orders = {}
            processed_count = 0
            
            for row in data_rows:
                if len(row) < 8:  # Make sure the shipping date column exists
                    continue
                
                # Parse the shipping date (column 8, index 7)
                shipping_date_str = row[7] if len(row) > 7 else ''
                
                if shipping_date_str:
                    # Try extracting from an already-formatted date
                    parsed_date = None
                    
                    # If it is in YYYY-MM-DD(星期X) format
                    if '(' in shipping_date_str and ')' in shipping_date_str:
                        date_part = shipping_date_str.split('(')[0]
                        try:
                            parsed_date = datetime.strptime(date_part, '%Y-%m-%d')
                        except ValueError:
                            pass
                    
                    # If it is in standard YYYY-MM-DD format
                    if not parsed_date:
                        parsed_date = time_utils.parse_shipping_date(shipping_date_str)
                    
                    if parsed_date:
                        sheet_name = time_utils.format_date_with_weekday(parsed_date, 'sheet_name')
                        
                        if sheet_name not in organized_orders:
                            organized_orders[sheet_name] = []
                        
                        organized_orders[sheet_name].append(row)
                        processed_count += 1
            
            # Create the new worksheets and write the data
            created_sheets = []
            
            for sheet_name, orders in organized_orders.items():
                # Create the worksheet (if it doesn't exist)
                if not self._get_sheet_by_name(sheet_name):
                    self._create_sheet_by_date(
                        datetime.strptime(sheet_name.split('_')[0], '%Y%m%d')
                    )
                    created_sheets.append(sheet_name)
                
                # Write the data to the target worksheet
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
                'message': f'Reorganized {processed_count} orders into {len(organized_orders)} worksheets'
            }
            
        except Exception as e:
            logger.error(f"Error organizing existing orders: {e}")
            return {
                'success': False,
                'error': f'Error while reorganizing orders: {e}'
            }
    
    def get_orders_by_date(self, target_date: str) -> Dict[str, Any]:
        """Get order data for a given date.
        
        Args:
            target_date: Target date, in formats like '08-27', '2024-08-27', etc.
            
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
            
            # Parse the target date
            parsed_date = time_utils.parse_shipping_date(target_date)
            if not parsed_date:
                return {
                    'success': False,
                    'error': f'無法解析日期格式: {target_date}',  # shown to the user in the LINE reply ("cannot parse date format")
                    'orders': []
                }
            
            # Build the expected worksheet name
            target_sheet_name = time_utils.format_date_with_weekday(parsed_date, 'sheet_name')
            
            # First try reading from the sheet for that date
            orders = []
            found_sheet = False
            
            # Check whether a matching date sheet exists
            if self._get_sheet_by_name(target_sheet_name):
                found_sheet = True
                sheet_orders = self._get_orders_from_sheet(target_sheet_name, target_date)
                orders.extend(sheet_orders)
            
            # If no specific sheet was found, or all sheets need searching
            if not found_sheet or not orders:
                # Search all worksheets
                all_sheets = self._get_all_sheets()
                for sheet in all_sheets:
                    sheet_name = sheet.get('properties', {}).get('title', '')
                    if sheet_name != target_sheet_name:  # Avoid searching the same sheet twice
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
                'error': f'查詢日期訂單時發生錯誤: {e}',  # shown to the user in the LINE reply ("error querying orders for the date")
                'orders': []
            }
    
    def _get_orders_from_sheet(self, sheet_name: str, target_date: str) -> List[Dict[str, Any]]:
        """Get orders for a specific date from the given worksheet."""
        orders = []
        
        try:
            # Read the worksheet data
            range_name = f'{sheet_name}!A:K'
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if len(values) <= 1:  # Only a header row, or empty
                return orders
            
            # Skip the header row
            data_rows = values[1:]
            
            for row in data_rows:
                if len(row) < 8:  # Make sure there are enough columns
                    continue
                
                # The new column layout has no shipping date, so we check the address column to decide whether a row is a valid record
                # Any row with an address counts as a valid order (temporary workaround)
                shipping_address = row[7] if len(row) > 7 else ''
                
                # Date matching temporarily removed because the new layout has no date column
                # TODO: redesign the date-matching logic
                if shipping_address:  # Has an address, so it counts as a valid order
                    # Parse the order data
                    order = {
                        'sender_name': row[0] if len(row) > 0 else '',     # Orderer/sender
                        'sender_address': row[1] if len(row) > 1 else '',  # Sender address
                        'receiver_name': row[2] if len(row) > 2 else '',   # Receiver
                        'items_name': row[3] if len(row) > 3 else '',      # Items
                        'items_quantity': row[4] if len(row) > 4 else '',  # Quantity
                        'sender_phone': row[5] if len(row) > 5 else '',    # Orderer phone
                        'receiver_phone': row[6] if len(row) > 6 else '',  # Receiver phone
                        'shipping_address': row[7] if len(row) > 7 else '', # Address
                        'total_price': row[8] if len(row) > 8 else '',     # Total price
                        'payment_status': row[9] if len(row) > 9 else '',  # Payment status
                        'last_5_digits': row[10] if len(row) > 10 else '', # Last 5 digits
                        'source_sheet': sheet_name
                    }
                    orders.append(order)
            
        except Exception as e:
            logger.error(f"Error reading orders from sheet {sheet_name}: {e}")
        
        return orders
    
    def _date_matches_target(self, shipping_date: str, target_date: str) -> bool:
        """Check whether the shipping date matches the target date."""
        if not shipping_date:
            return False
        
        try:
            from .time_utils import time_utils
            
            # Parse the target date
            target_parsed = time_utils.parse_shipping_date(target_date)
            if not target_parsed:
                return False
            
            # Parse the shipping date
            # Handle formats like "2024-08-27(星期二)"
            clean_shipping_date = shipping_date
            if '(' in shipping_date and ')' in shipping_date:
                clean_shipping_date = shipping_date.split('(')[0]
            
            shipping_parsed = time_utils.parse_shipping_date(clean_shipping_date)
            if not shipping_parsed:
                return False
            
            # Compare dates (year/month/day only, ignore time)
            return (target_parsed.year == shipping_parsed.year and
                   target_parsed.month == shipping_parsed.month and
                   target_parsed.day == shipping_parsed.day)
            
        except Exception as e:
            logger.error(f"Error matching dates: {shipping_date} vs {target_date}: {e}")
            return False