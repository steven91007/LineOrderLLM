# Google Sheets API Guide

## Overview

This project provides a complete Google Sheets API integration, including:
- **GoogleSheetsClient**: the core client class
- **Example program**: demonstrates the various ways to use it
- **Test program**: a full functional test suite

## Quick Start

### 1. Environment Setup

#### Required environment variables
Set the following variables in your `.env` file:

```bash
# Google Sheets settings
GOOGLE_SHEETS_CREDENTIALS_PATH=/path/to/your/credentials.json
GOOGLE_SHEETS_ID=your_spreadsheet_id_here
```

#### Getting Google Sheets credentials

1. **Create a Google Cloud project**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one

2. **Enable the Google Sheets API**
   - Under APIs & Services > Library, search for "Google Sheets API"
   - Click Enable

3. **Create a service account**
   - Go to APIs & Services > Credentials
   - Click "Create credentials" > "Service account"
   - Fill in the service account details
   - Download the JSON credentials file

4. **Set spreadsheet permissions**
   - Create or open a Google Sheets spreadsheet
   - Click the "Share" button in the top-right corner
   - Add the service account's email address (the `client_email` in the credentials file)
   - Grant it "Editor" permission

5. **Get the spreadsheet ID**
   - Copy the ID from the spreadsheet URL
   - URL format: `https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=0`

### 2. Install Dependencies

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dotenv
```

### 3. Validate the Setup

Run the setup validation to confirm everything is configured correctly:

```bash
python test_google_sheets_api.py --validation-only
```

## Usage

### Basic usage

```python
from src.utils.google_sheets_client import GoogleSheetsClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize the client
client = GoogleSheetsClient(
    credentials_path=os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH'),
    sheet_id=os.getenv('GOOGLE_SHEETS_ID')
)

# Test the connection
result = client.test_connection()
if result['success']:
    print(f"Connected: {result['message']}")
else:
    print(f"Connection failed: {result['error']}")
```

### Adding a single order

Sample values are Chinese because that is what the sheet stores (e.g. `'寄件人姓名'` = sender name placeholder, `'收件人姓名'` = receiver name placeholder, `'待處理'` = "pending" status, `'備註資訊'` = notes placeholder).

```python
order_data = {
    'order_id': 'ORD-20250804-001',
    'sender_name': '寄件人姓名',
    'sender_phone': '0912-345-678',
    'receiver_name': '收件人姓名',
    'receiver_phone': '0987-654-321',
    'shipping_address': '台北市信義區信義路五段7號',
    'shipping_date': '2025-08-07',
    'items': [
        {'name': '18A禮盒', 'quantity': 2},
        {'name': '16A蛋糕', 'quantity': 1}
    ],
    'status': '待處理',
    'notes': '備註資訊'
}

result = client.append_order(order_data)
if result['success']:
    print(f"Order added, order ID: {result['order_id']}")
else:
    print(f"Failed to add order: {result['error']}")
```

### Adding orders in bulk

```python
orders_data = [order1, order2, order3]  # list of orders

result = client.append_multiple_orders(orders_data)
if result['success']:
    print(f"Bulk add succeeded, processed {result['total_processed']} orders")
    print(f"Order IDs: {result['order_ids']}")
else:
    print(f"Bulk add failed: {result['error']}")
```

### Fetching recent orders

```python
result = client.get_recent_orders(limit=10)
if result['success']:
    orders = result['orders']
    print(f"Found {len(orders)} recent orders")
    for order in orders:
        print(f"- {order['order_id']}: {order['receiver_name']}")
else:
    print(f"Failed to fetch orders: {result['error']}")
```

## Running the Example Program

### Full feature demo

```bash
python examples/google_sheets_api_example.py
```

This example program will:
1. Validate the environment setup
2. Test the connection
3. Create the spreadsheet header row (if it does not exist)
4. Add a single sample order
5. Add several sample orders in bulk
6. Fetch the most recent order records

### Sample output

(`訂單管理系統` is the spreadsheet's title, "Order Management System".)

```
🚀 Google Sheets API example program
This program demonstrates the various features of GoogleSheetsClient
Using credentials file: /path/to/credentials.json
Using spreadsheet ID: your_spreadsheet_id

==================================================
 Setup validation
==================================================
Overall status: healthy

Check results:
  ✅ credentials_file: credentials file exists
  ✅ service_init: Google Sheets service initialized successfully
  ✅ connection: connected to spreadsheet: 訂單管理系統
    - spreadsheet_title: 訂單管理系統
    - sheet_count: 1
  ✅ headers: header row set up successfully

==================================================
 Connection test
==================================================
✅ Connection test succeeded!
   Message: connected to spreadsheet: 訂單管理系統
   Spreadsheet title: 訂單管理系統
   Sheet count: 1

... more output ...

==================================================
Example program finished
==================================================
🎉 All feature demos completed!
You can check Google Sheets to confirm the data was added correctly
```

## Running the Test Program

### Full test suite

```bash
python test_google_sheets_api.py
```

### Test options

```bash
# Run setup validation only
python test_google_sheets_api.py --validation-only

# Verbose output
python test_google_sheets_api.py -v

# Quick test (skips actual writes)
python test_google_sheets_api.py --quick
```

### Test cases

The test program includes the following tests:

1. **Environment setup test** - checks environment variables and the credentials file
2. **Client initialization test** - verifies GoogleSheetsClient initializes correctly
3. **Setup validation test** - tests `validate_setup()`
4. **Connection test** - tests `test_connection()`
5. **Sample data creation test** - verifies the test data format
6. **Header creation test** - tests `create_sheet_if_not_exists()`
7. **Single order append test** - tests `append_order()`
8. **Bulk order append test** - tests `append_multiple_orders()`
9. **Data read test** - tests `get_recent_orders()`
10. **Error handling test** - tests various error conditions
11. **Data formatting test** - tests `_format_items()`

## API Reference

### GoogleSheetsClient

#### Initialization

```python
GoogleSheetsClient(credentials_path: str, sheet_id: str)
```

- `credentials_path`: path to the Google Service Account credentials file
- `sheet_id`: the Google Sheets spreadsheet ID

#### Main methods

##### `test_connection() -> Dict[str, Any]`
Tests the connection to Google Sheets.

**Returns:**
```python
{
    'success': bool,
    'spreadsheet_title': str,  # spreadsheet title
    'sheet_count': int,        # number of sheets (tabs)
    'message': str,            # success message
    'error': str               # error message (on failure)
}
```

##### `validate_setup() -> Dict[str, Any]`
Validates the complete setup state.

**Returns:**
```python
{
    'overall_status': str,     # 'healthy', 'partial', 'failed'
    'checks': dict,            # results of each check
    'recommendations': list    # recommendations
}
```

##### `append_order(order_data: Dict[str, Any]) -> Dict[str, Any]`
Appends a single order to the spreadsheet.

**Parameters:**
```python
order_data = {
    'order_id': str,           # order ID
    'sender_name': str,        # sender name (optional)
    'sender_phone': str,       # sender phone (optional)
    'receiver_name': str,      # receiver name
    'receiver_phone': str,     # receiver phone
    'shipping_address': str,   # shipping address
    'shipping_date': str,      # expected shipping date (optional)
    'items': List[Dict],       # item list
    'status': str,             # order status (optional, default: 待處理 "pending")
    'notes': str               # notes (optional)
}
```

**Item list format:**
```python
items = [
    {'name': 'item name', 'quantity': quantity},
    ...
]
```

**Returns:**
```python
{
    'success': bool,
    'updated_rows': int,       # number of rows updated
    'updated_cells': int,      # number of cells updated
    'order_id': str,           # order ID
    'error': str               # error message (on failure)
}
```

##### `append_multiple_orders(orders_data: List[Dict[str, Any]]) -> Dict[str, Any]`
Appends multiple orders to the spreadsheet in bulk.

**Parameters:**
- `orders_data`: list of order data; each element has the same format as for `append_order`

**Returns:**
```python
{
    'success': bool,
    'total_processed': int,    # number of orders processed
    'updated_rows': int,       # number of rows updated
    'updated_cells': int,      # number of cells updated
    'order_ids': List[str],    # all order IDs
    'error': str               # error message (on failure)
}
```

##### `get_recent_orders(limit: int = 10) -> Dict[str, Any]`
Fetches the most recent order records.

**Parameters:**
- `limit`: maximum number of orders to fetch

**Returns:**
```python
{
    'success': bool,
    'orders': List[Dict],      # list of orders
    'error': str               # error message (on failure)
}
```

**Order format:**
```python
order = {
    'order_time': str,         # order time
    'order_id': str,           # order ID
    'sender_name': str,        # sender name
    'sender_phone': str,       # sender phone
    'receiver_name': str,      # receiver name
    'receiver_phone': str,     # receiver phone
    'items': str,              # item details (already formatted)
    'shipping_date': str,      # expected shipping date
    'shipping_address': str,   # shipping address
    'status': str,             # order status
    'notes': str               # notes
}
```

##### `create_sheet_if_not_exists() -> bool`
Ensures the spreadsheet exists and has the correct header row.

**Returns:**
- `True`: setup succeeded
- `False`: setup failed

## Spreadsheet Format

### Header row (first row)

The headers are written to the sheet in Chinese exactly as shown. English meanings: order time, order ID, sender, sender phone, receiver, receiver phone, item details, expected shipping date, shipping address, order status, notes.

| A | B | C | D | E | F | G | H | I | J | K |
|---|---|---|---|---|---|---|---|---|---|---|
| 訂單時間 | 訂單編號 | 寄件人 | 寄件人電話 | 收件人 | 收件人電話 | 商品明細 | 預計發貨日 | 收件地址 | 訂單狀態 | 備註 |

### Sample data row

(`待處理` = "pending", `急件` = "urgent".)

| 訂單時間 | 訂單編號 | 寄件人 | 寄件人電話 | 收件人 | 收件人電話 | 商品明細 | 預計發貨日 | 收件地址 | 訂單狀態 | 備註 |
|---------|---------|--------|-----------|--------|-----------|----------|-----------|----------|----------|------|
| 2025-08-04 14:30:15 | ORD-20250804-001 | 王小明 | 0912-345-678 | 李小華 | 0987-654-321 | 18A禮盒 x 2, 16A蛋糕 x 1 | 2025-08-07 | 台北市信義區信義路五段7號 | 待處理 | 急件 |

## FAQ

### Q: Why does the connection test fail?

**A: Possible causes:**
1. **Wrong credentials file path** - check the `GOOGLE_SHEETS_CREDENTIALS_PATH` environment variable
2. **Wrong spreadsheet ID** - check the `GOOGLE_SHEETS_ID` environment variable
3. **Insufficient permissions** - make sure the service account has edit access to the spreadsheet
4. **API not enabled** - make sure the Google Sheets API is enabled in the Google Cloud Console

### Q: How do I check the service account's permissions?

**A: Steps:**
1. Open the Google Sheets spreadsheet
2. Click the "Share" button in the top-right corner
3. Confirm the service account's email address is in the sharing list
4. Confirm its permission is set to "Editor" or "Owner"

### Q: What if I get a permission error when adding orders?

**A: Fixes:**
1. Use `validate_setup()` to check all settings
2. Confirm the service account has write access
3. Check that the credentials file is valid
4. Try downloading the credentials file again

### Q: How do I customize the spreadsheet format?

**A: To customize:**
1. Change the header definition in the `create_sheet_if_not_exists()` method
2. Adjust the column order of the data in `append_order()` and `append_multiple_orders()`
3. Update the parsing logic in `get_recent_orders()`

### Q: How do I handle large amounts of data?

**A: Performance tips:**
1. Use `append_multiple_orders()` for bulk operations
2. Avoid frequent single-row appends
3. Set an appropriate `limit` when reading data
4. Consider pagination or batch processing

## License and Support

This project follows the project's main license terms. For questions or suggestions, please report them through the project's issue tracker.

## Changelog

- **2025-08-04**: Initial release with full Google Sheets API integration
- Features: single/bulk order appends, data reads, connection testing, setup validation
- Includes a complete example program and test suite
