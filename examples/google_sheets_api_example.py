#!/usr/bin/env python3
"""
Google Sheets API example program

This example shows how to use GoogleSheetsClient for various operations:
- Test the connection
- Add a single order
- Add orders in batch
- Get recent orders
- Validate the setup

Before running, make sure:
1. The Google Service Account credentials file is set up
2. A Google Sheet has been created and shared with the service account
3. The relevant environment variables are set in the .env file
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.google_sheets_client import GoogleSheetsClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def print_section(title: str):
    """Print a section title."""
    print(f"\n{'='*50}")
    print(f" {title}")
    print(f"{'='*50}")

def print_result(result: Dict[str, Any], operation: str):
    """Print a formatted result."""
    if result.get('success'):
        print(f"✅ {operation} succeeded!")
        if 'message' in result:
            print(f"   Message: {result['message']}")
        if 'updated_rows' in result:
            print(f"   Rows updated: {result['updated_rows']}")
        if 'total_processed' in result:
            print(f"   Processed: {result['total_processed']}")
    else:
        print(f"❌ {operation} failed!")
        print(f"   Error: {result.get('error', 'Unknown error')}")
        if 'details' in result:
            print(f"   Details: {result['details']}")

def create_sample_order(order_id: str = None) -> Dict[str, Any]:
    """Build sample order data."""
    if not order_id:
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        order_id = f"DEMO-{timestamp}"
    
    return {
        'order_id': order_id,
        'sender_name': '測試寄件人',
        'sender_phone': '0912-345-678',
        'receiver_name': '測試收件人',
        'receiver_phone': '0987-654-321',
        'shipping_address': '台北市信義區信義路五段7號',
        'shipping_date': (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'),
        'items': [
            {'name': '18A禮盒', 'quantity': 2},
            {'name': '16A蛋糕', 'quantity': 1}
        ],
        'status': '待處理',  # sample data ("pending")
        'notes': '這是一個範例訂單'  # sample data ("this is a sample order")
    }

def create_sample_batch_orders(count: int = 3) -> List[Dict[str, Any]]:
    """Build sample batch order data."""
    orders = []
    base_timestamp = datetime.now()
    
    for i in range(count):
        timestamp = (base_timestamp + timedelta(minutes=i)).strftime('%Y%m%d%H%M%S')
        order_id = f"BATCH-{timestamp}-{i+1}"
        
        order = {
            'order_id': order_id,
            'sender_name': f'批量測試寄件人{i+1}',
            'sender_phone': f'0912-345-{678+i:03d}',
            'receiver_name': f'批量測試收件人{i+1}',
            'receiver_phone': f'0987-654-{321+i:03d}',
            'shipping_address': f'台北市信義區信義路五段{7+i}號',
            'shipping_date': (datetime.now() + timedelta(days=2+i)).strftime('%Y-%m-%d'),
            'items': [
                {'name': f'{18+i}A禮盒', 'quantity': i+1},
                {'name': f'{16+i}A蛋糕', 'quantity': 2}
            ],
            'status': '待處理',
            'notes': f'這是批量範例訂單 #{i+1}'
        }
        orders.append(order)
    
    return orders

def demo_validation(client: GoogleSheetsClient):
    """Demonstrate setup validation."""
    print_section("Setup validation")
    
    validation_result = client.validate_setup()
    
    print(f"Overall status: {validation_result['overall_status']}")
    print("\nCheck results:")
    
    for check_name, check_result in validation_result['checks'].items():
        status_icon = "✅" if check_result['status'] == 'pass' else "❌"
        print(f"  {status_icon} {check_name}: {check_result['message']}")
        
        if 'details' in check_result and check_result['details']:
            for key, value in check_result['details'].items():
                print(f"    - {key}: {value}")
    
    if validation_result['recommendations']:
        print("\nRecommendations:")
        for recommendation in validation_result['recommendations']:
            print(f"  💡 {recommendation}")

def demo_connection_test(client: GoogleSheetsClient):
    """Demonstrate the connection test."""
    print_section("Connection test")
    
    result = client.test_connection()
    print_result(result, "Connection test")
    
    if result.get('success'):
        print(f"   Spreadsheet title: {result.get('spreadsheet_title')}")
        print(f"   Worksheet count: {result.get('sheet_count')}")

def demo_single_order(client: GoogleSheetsClient):
    """Demonstrate adding a single order."""
    print_section("Add single order")
    
    sample_order = create_sample_order()
    print("Sample order data:")
    print(f"  Order ID: {sample_order['order_id']}")
    print(f"  Receiver: {sample_order['receiver_name']}")
    print(f"  Address: {sample_order['shipping_address']}")
    items_str = ', '.join([f"{item['name']} x{item['quantity']}" for item in sample_order['items']])
    print(f"  Items: {items_str}")
    
    result = client.append_order(sample_order)
    print_result(result, "Add single order")

def demo_batch_orders(client: GoogleSheetsClient):
    """Demonstrate adding orders in batch."""
    print_section("Add batch orders")
    
    sample_orders = create_sample_batch_orders(3)
    print(f"Adding {len(sample_orders)} orders:")
    
    for i, order in enumerate(sample_orders, 1):
        print(f"  {i}. {order['order_id']} - {order['receiver_name']}")
    
    result = client.append_multiple_orders(sample_orders)
    print_result(result, "Add batch orders")
    
    if result.get('success') and result.get('order_ids'):
        print("   Added order IDs:")
        for order_id in result['order_ids']:
            print(f"     - {order_id}")

def demo_get_recent_orders(client: GoogleSheetsClient):
    """Demonstrate fetching recent orders."""
    print_section("Get recent orders")
    
    result = client.get_recent_orders(limit=5)
    print_result(result, "Get recent orders")
    
    if result.get('success'):
        orders = result.get('orders', [])
        if orders:
            print(f"   Found {len(orders)} recent orders:")
            for i, order in enumerate(orders, 1):
                print(f"     {i}. {order['order_id']} - {order['receiver_name']} ({order['order_time']})")
        else:
            print("   No order data yet")

def main():
    """Main program."""
    print("🚀 Google Sheets API example program")
    print("This program demonstrates the features of GoogleSheetsClient")
    
    # Check environment variables
    credentials_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH')
    sheet_id = os.getenv('GOOGLE_SHEETS_ID')
    
    if not credentials_path:
        print("❌ Error: GOOGLE_SHEETS_CREDENTIALS_PATH environment variable is not set")
        print("Set it in the .env file: GOOGLE_SHEETS_CREDENTIALS_PATH=path/to/credentials.json")
        return
    
    if not sheet_id:
        print("❌ Error: GOOGLE_SHEETS_ID environment variable is not set")
        print("Set it in the .env file: GOOGLE_SHEETS_ID=your_spreadsheet_id")
        return
    
    print(f"Using credentials file: {credentials_path}")
    print(f"Using spreadsheet ID: {sheet_id}")
    
    # Initialize the client
    client = GoogleSheetsClient(credentials_path, sheet_id)
    
    try:
        # 1. Setup validation
        demo_validation(client)
        
        # Don't continue if the basic setup has problems
        validation_result = client.validate_setup()
        if validation_result['overall_status'] == 'failed':
            print("\n❌ Setup validation failed; fix the issues above before running the example")
            return
        
        # 2. Connection test
        demo_connection_test(client)
        
        # 3. Make sure the spreadsheet has the correct headers
        print_section("Initialize spreadsheet")
        if client.create_sheet_if_not_exists():
            print("✅ Spreadsheet header row initialized")
        else:
            print("⚠️  Spreadsheet header row initialization may have failed")
        
        # 4. Demonstrate the features
        demo_single_order(client)
        demo_batch_orders(client)
        demo_get_recent_orders(client)
        
        print_section("Example finished")
        print("🎉 All feature demos completed!")
        print("Check Google Sheets to confirm the data was added correctly")
        
    except Exception as e:
        print(f"\n❌ An error occurred during execution: {e}")
        print("Check the setup and run again")

if __name__ == "__main__":
    main()