#!/usr/bin/env python3
"""
自動訂單處理功能測試程式
測試按日期分組的 Google Sheets 功能和時間工具
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 添加專案路徑
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from utils.time_utils import time_utils
from utils.google_sheets_client import GoogleSheetsClient


def test_time_utils():
    """測試時間工具功能"""
    print("🕒 測試時間工具功能")
    print("=" * 50)
    
    # 測試網路時間獲取
    print("1. 測試網路時間獲取")
    current_time = time_utils.get_current_time(use_network=True)
    print(f"   當前時間: {current_time}")
    print(f"   格式化時間: {time_utils.format_date_with_weekday(current_time)}")
    
    # 測試日期解析
    print("\n2. 測試日期解析")
    test_dates = ['2025-08-07', '08-08', '明天', '後天', '3天後']
    
    for date_str in test_dates:
        parsed = time_utils.parse_shipping_date(date_str)
        if parsed:
            formatted = time_utils.format_date_with_weekday(parsed, 'standard')
            sheet_name = time_utils.format_date_with_weekday(parsed, 'sheet_name')
            print(f"   '{date_str}' -> {formatted} (Sheet: {sheet_name})")
        else:
            print(f"   '{date_str}' -> 解析失敗")
    
    # 測試日期驗證
    print("\n3. 測試日期驗證")
    test_validation_dates = ['2025-08-07', '2025-01-01', '明天', '100天後', 'invalid']
    
    for date_str in test_validation_dates:
        validation = time_utils.validate_shipping_date(date_str)
        status = "✅" if validation['is_valid'] else "❌"
        print(f"   {status} '{date_str}': {validation['message']}")
    
    print()


def test_google_sheets_client():
    """測試 Google Sheets 客戶端"""
    print("📊 測試 Google Sheets 客戶端")
    print("=" * 50)
    
    # 檢查環境變數
    credentials_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH')
    sheet_id = os.getenv('GOOGLE_SHEETS_ID')
    
    if not credentials_path or not sheet_id:
        print("❌ 缺少環境變數:")
        if not credentials_path:
            print("   - GOOGLE_SHEETS_CREDENTIALS_PATH")
        if not sheet_id:
            print("   - GOOGLE_SHEETS_ID")
        print("   請設置環境變數後重新測試")
        return
    
    # 初始化客戶端
    print("1. 初始化 GoogleSheetsClient (自動分組模式)")
    client = GoogleSheetsClient(
        credentials_path=credentials_path,
        sheet_id=sheet_id,
        auto_organize_by_date=True
    )
    
    # 連接測試
    print("2. 連接測試")
    connection_test = client.test_connection()
    if connection_test['success']:
        print(f"   ✅ {connection_test['message']}")
    else:
        print(f"   ❌ {connection_test['error']}")
        return
    
    # 獲取工作表摘要
    print("\n3. 獲取工作表摘要")
    summary = client.get_sheets_summary()
    if summary['success']:
        print(f"   總工作表數: {summary['total_sheets']}")
        for sheet in summary['sheets']:
            sheet_type = "📅日期分組" if sheet['is_date_sheet'] else "📋一般"
            print(f"   - {sheet_type} {sheet['name']}: {sheet['row_count']} 行資料")
    else:
        print(f"   ❌ {summary['error']}")
    
    # 測試單一訂單
    print("\n4. 測試單一訂單 (自動分組)")
    tomorrow = datetime.now() + timedelta(days=1)
    tomorrow_str = tomorrow.strftime('%Y-%m-%d')
    
    test_order = {
        'order_id': f'TEST-{int(datetime.now().timestamp())}',
        'sender_name': '測試寄件人',
        'sender_phone': '0912-345-678',
        'receiver_name': '測試收件人',
        'receiver_phone': '0987-654-321',
        'items': [
            {'name': '測試商品A', 'quantity': 2},
            {'name': '測試商品B', 'quantity': 1}
        ],
        'shipping_date': tomorrow_str,
        'shipping_address': '台北市信義區信義路五段7號',
        'status': '測試中',
        'notes': '自動化測試訂單'
    }
    
    result = client.append_order(test_order)
    if result['success']:
        print(f"   ✅ 訂單寫入成功")
        print(f"      目標工作表: {result.get('target_sheet', 'N/A')}")
        print(f"      更新行數: {result['updated_rows']}")
    else:
        print(f"   ❌ 訂單寫入失敗: {result['error']}")
    
    # 測試批量訂單
    print("\n5. 測試批量訂單 (多日期分組)")
    batch_orders = []
    
    for i in range(3):
        future_date = datetime.now() + timedelta(days=i+1)
        batch_orders.append({
            'order_id': f'BATCH-{int(datetime.now().timestamp())}-{i+1}',
            'receiver_name': f'批量測試收件人{i+1}',
            'receiver_phone': f'09{i+1:02d}-000-00{i+1}',
            'items': [{'name': f'批量商品{i+1}', 'quantity': i+1}],
            'shipping_date': future_date.strftime('%Y-%m-%d'),
            'shipping_address': f'測試地址{i+1}',
            'notes': f'批量測試訂單 {i+1}'
        })
    
    batch_result = client.append_multiple_orders(batch_orders)
    if batch_result['success']:
        print(f"   ✅ 批量訂單寫入成功")
        print(f"      處理訂單數: {batch_result['total_processed']}")
        
        if 'sheets_used' in batch_result:
            print(f"      使用工作表: {', '.join(batch_result['sheets_used'])}")
            
        if 'sheet_results' in batch_result:
            for sheet, info in batch_result['sheet_results'].items():
                print(f"        - {sheet}: {info['order_count']} 份訂單")
    else:
        print(f"   ❌ 批量訂單寫入失敗: {batch_result['error']}")
    
    # 更新工作表摘要
    print("\n6. 更新後的工作表摘要")
    updated_summary = client.get_sheets_summary()
    if updated_summary['success']:
        print(f"   總工作表數: {updated_summary['total_sheets']}")
        for sheet in updated_summary['sheets']:
            sheet_type = "📅日期分組" if sheet['is_date_sheet'] else "📋一般"
            print(f"   - {sheet_type} {sheet['name']}: {sheet['row_count']} 行資料")
    
    print()


def test_manual_organization():
    """測試手動重新組織功能"""
    print("🔄 測試手動重新組織功能")
    print("=" * 50)
    
    credentials_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH')
    sheet_id = os.getenv('GOOGLE_SHEETS_ID')
    
    if not credentials_path or not sheet_id:
        print("❌ 缺少環境變數，跳過測試")
        return
    
    client = GoogleSheetsClient(
        credentials_path=credentials_path,
        sheet_id=sheet_id,
        auto_organize_by_date=True
    )
    
    # 這是一個示範性功能，實際使用需要謹慎
    print("注意: 手動重新組織會將現有訂單按日期重新分組")
    print("此功能適用於將舊的單一工作表資料遷移到新的分組系統")
    print("在生產環境中使用前請先備份資料")
    
    # 可以取消註解以下代碼進行實際測試
    # result = client.organize_existing_orders_by_date()
    # if result['success']:
    #     print(f"✅ 重新組織成功: {result['message']}")
    #     print(f"   處理訂單數: {result['processed_orders']}")
    #     print(f"   創建工作表: {result['created_sheets']}")
    # else:
    #     print(f"❌ 重新組織失敗: {result['error']}")
    
    print()


def main():
    """主測試函數"""
    print("🚀 自動訂單處理功能測試")
    print("=" * 60)
    print()
    
    # 測試時間工具
    test_time_utils()
    
    # 測試 Google Sheets 客戶端
    test_google_sheets_client()
    
    # 測試手動重新組織功能
    test_manual_organization()
    
    print("🎉 測試完成！")
    print("=" * 60)
    
    print("\n💡 功能說明:")
    print("1. ⏰ 自動從網路獲取準確時間")
    print("2. 📅 支援多種日期格式解析 (YYYY-MM-DD, MM-DD, 明天, 後天等)")
    print("3. 🗂️ 自動按出貨日期創建分組工作表")
    print("4. 📊 工作表名稱格式: YYYYMMDD_星期X")
    print("5. 🔄 支援批量訂單自動分組")
    print("6. 📋 提供工作表統計和管理功能")
    
    print("\n📝 使用方式:")
    print("在 OrderHandler 中已自動啟用日期分組功能")
    print("新訂單會自動根據出貨日期分配到對應的工作表")
    print("如果沒有指定出貨日期，會使用當天日期")


if __name__ == "__main__":
    main()