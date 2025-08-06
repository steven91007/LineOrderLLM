#!/usr/bin/env python3
"""
Google Sheets API 範例程式

此範例展示如何使用 GoogleSheetsClient 進行各種操作：
- 測試連接
- 新增單一訂單
- 批量新增訂單  
- 獲取最近訂單
- 驗證設定狀態

使用前請確保：
1. 已設定 Google Service Account 憑證檔案
2. 已建立 Google Sheets 並分享給服務帳戶
3. 已在 .env 檔案中設定相關環境變數
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List

# 將專案根目錄加入 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.google_sheets_client import GoogleSheetsClient
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

def print_section(title: str):
    """列印區段標題"""
    print(f"\n{'='*50}")
    print(f" {title}")
    print(f"{'='*50}")

def print_result(result: Dict[str, Any], operation: str):
    """格式化輸出結果"""
    if result.get('success'):
        print(f"✅ {operation} 成功！")
        if 'message' in result:
            print(f"   訊息：{result['message']}")
        if 'updated_rows' in result:
            print(f"   更新列數：{result['updated_rows']}")
        if 'total_processed' in result:
            print(f"   處理數量：{result['total_processed']}")
    else:
        print(f"❌ {operation} 失敗！")
        print(f"   錯誤：{result.get('error', '未知錯誤')}")
        if 'details' in result:
            print(f"   詳細資訊：{result['details']}")

def create_sample_order(order_id: str = None) -> Dict[str, Any]:
    """建立範例訂單資料"""
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
        'status': '待處理',
        'notes': '這是一個範例訂單'
    }

def create_sample_batch_orders(count: int = 3) -> List[Dict[str, Any]]:
    """建立批量範例訂單資料"""
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
    """示範設定驗證功能"""
    print_section("設定驗證")
    
    validation_result = client.validate_setup()
    
    print(f"整體狀態：{validation_result['overall_status']}")
    print("\n檢查結果：")
    
    for check_name, check_result in validation_result['checks'].items():
        status_icon = "✅" if check_result['status'] == 'pass' else "❌"
        print(f"  {status_icon} {check_name}：{check_result['message']}")
        
        if 'details' in check_result and check_result['details']:
            for key, value in check_result['details'].items():
                print(f"    - {key}：{value}")
    
    if validation_result['recommendations']:
        print("\n建議：")
        for recommendation in validation_result['recommendations']:
            print(f"  💡 {recommendation}")

def demo_connection_test(client: GoogleSheetsClient):
    """示範連接測試功能"""
    print_section("連接測試")
    
    result = client.test_connection()
    print_result(result, "連接測試")
    
    if result.get('success'):
        print(f"   試算表標題：{result.get('spreadsheet_title')}")
        print(f"   工作表數量：{result.get('sheet_count')}")

def demo_single_order(client: GoogleSheetsClient):
    """示範單一訂單新增功能"""
    print_section("單一訂單新增")
    
    sample_order = create_sample_order()
    print("範例訂單資料：")
    print(f"  訂單編號：{sample_order['order_id']}")
    print(f"  收件人：{sample_order['receiver_name']}")
    print(f"  地址：{sample_order['shipping_address']}")
    items_str = ', '.join([f"{item['name']} x{item['quantity']}" for item in sample_order['items']])
    print(f"  商品：{items_str}")
    
    result = client.append_order(sample_order)
    print_result(result, "單一訂單新增")

def demo_batch_orders(client: GoogleSheetsClient):
    """示範批量訂單新增功能"""
    print_section("批量訂單新增")
    
    sample_orders = create_sample_batch_orders(3)
    print(f"準備新增 {len(sample_orders)} 份訂單：")
    
    for i, order in enumerate(sample_orders, 1):
        print(f"  {i}. {order['order_id']} - {order['receiver_name']}")
    
    result = client.append_multiple_orders(sample_orders)
    print_result(result, "批量訂單新增")
    
    if result.get('success') and result.get('order_ids'):
        print("   已新增的訂單編號：")
        for order_id in result['order_ids']:
            print(f"     - {order_id}")

def demo_get_recent_orders(client: GoogleSheetsClient):
    """示範獲取最近訂單功能"""
    print_section("獲取最近訂單")
    
    result = client.get_recent_orders(limit=5)
    print_result(result, "獲取最近訂單")
    
    if result.get('success'):
        orders = result.get('orders', [])
        if orders:
            print(f"   找到 {len(orders)} 份最近訂單：")
            for i, order in enumerate(orders, 1):
                print(f"     {i}. {order['order_id']} - {order['receiver_name']} ({order['order_time']})")
        else:
            print("   目前沒有訂單資料")

def main():
    """主程式"""
    print("🚀 Google Sheets API 範例程式")
    print("這個程式將示範 GoogleSheetsClient 的各種功能")
    
    # 檢查環境變數
    credentials_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH')
    sheet_id = os.getenv('GOOGLE_SHEETS_ID')
    
    if not credentials_path:
        print("❌ 錯誤：未設定 GOOGLE_SHEETS_CREDENTIALS_PATH 環境變數")
        print("請在 .env 檔案中設定：GOOGLE_SHEETS_CREDENTIALS_PATH=path/to/credentials.json")
        return
    
    if not sheet_id:
        print("❌ 錯誤：未設定 GOOGLE_SHEETS_ID 環境變數")
        print("請在 .env 檔案中設定：GOOGLE_SHEETS_ID=your_spreadsheet_id")
        return
    
    print(f"使用憑證檔案：{credentials_path}")
    print(f"使用試算表 ID：{sheet_id}")
    
    # 初始化客戶端
    client = GoogleSheetsClient(credentials_path, sheet_id)
    
    try:
        # 1. 設定驗證
        demo_validation(client)
        
        # 如果基本設定有問題，不繼續執行
        validation_result = client.validate_setup()
        if validation_result['overall_status'] == 'failed':
            print("\n❌ 設定驗證失敗，請先解決上述問題後再執行範例")
            return
        
        # 2. 連接測試
        demo_connection_test(client)
        
        # 3. 確保試算表有正確的標題
        print_section("初始化試算表")
        if client.create_sheet_if_not_exists():
            print("✅ 試算表標題行初始化成功")
        else:
            print("⚠️  試算表標題行初始化可能有問題")
        
        # 4. 示範各種功能
        demo_single_order(client)
        demo_batch_orders(client)
        demo_get_recent_orders(client)
        
        print_section("範例程式執行完成")
        print("🎉 所有功能示範完成！")
        print("您可以查看 Google Sheets 確認資料是否正確新增")
        
    except Exception as e:
        print(f"\n❌ 執行過程中發生錯誤：{e}")
        print("請檢查設定並重新執行")

if __name__ == "__main__":
    main()