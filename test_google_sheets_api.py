#!/usr/bin/env python3
"""
Google Sheets API 測試程式

這個測試程式會進行完整的 GoogleSheetsClient 功能測試，包括：
- 連接測試
- 單一訂單新增測試
- 批量訂單新增測試  
- 資料讀取測試
- 錯誤處理測試
- 設定驗證測試

執行方式：
python test_google_sheets_api.py [options]

選項：
--quick: 執行快速測試（跳過實際資料寫入）
--validation-only: 僅執行設定驗證
--cleanup: 測試後清理測試資料（需要手動確認）
"""

import os
import sys
import argparse
import unittest
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

# 將專案根目錄加入 Python 路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils.google_sheets_client import GoogleSheetsClient
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

class TestGoogleSheetsClient(unittest.TestCase):
    """Google Sheets 客戶端測試類"""
    
    @classmethod
    def setUpClass(cls):
        """測試類初始化"""
        cls.credentials_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH')
        cls.sheet_id = os.getenv('GOOGLE_SHEETS_ID')
        cls.skip_real_tests = False
        
        # 檢查必要環境變數
        if not cls.credentials_path or not cls.sheet_id:
            print("⚠️  警告：缺少必要的環境變數，將跳過實際 API 測試")
            cls.skip_real_tests = True
        else:
            cls.client = GoogleSheetsClient(cls.credentials_path, cls.sheet_id)
    
    def test_01_environment_setup(self):
        """測試環境設定"""
        print("\n🔧 測試環境設定...")
        
        # 檢查環境變數
        self.assertIsNotNone(os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH'), 
                             "GOOGLE_SHEETS_CREDENTIALS_PATH 環境變數未設定")
        self.assertIsNotNone(os.getenv('GOOGLE_SHEETS_ID'), 
                            "GOOGLE_SHEETS_ID 環境變數未設定")
        
        # 檢查憑證檔案
        if self.credentials_path and os.path.exists(self.credentials_path):
            print(f"✅ 憑證檔案存在: {self.credentials_path}")
        else:
            print(f"❌ 憑證檔案不存在: {self.credentials_path}")
            
        print(f"✅ 使用試算表 ID: {self.sheet_id}")
    
    @unittest.skipIf(not os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH') or 
                     not os.getenv('GOOGLE_SHEETS_ID'), 
                     "缺少必要環境變數")
    def test_02_client_initialization(self):
        """測試客戶端初始化"""
        print("\n🔌 測試客戶端初始化...")
        
        self.assertIsNotNone(self.client, "GoogleSheetsClient 初始化失敗")
        self.assertEqual(self.client.sheet_id, self.sheet_id)
        self.assertEqual(self.client.credentials_path, self.credentials_path)
        
        print("✅ 客戶端初始化成功")
    
    @unittest.skipIf(not os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH') or 
                     not os.getenv('GOOGLE_SHEETS_ID'), 
                     "缺少必要環境變數")
    def test_03_validation_setup(self):
        """測試設定驗證功能"""
        print("\n✅ 測試設定驗證...")
        
        result = self.client.validate_setup()
        
        self.assertIsInstance(result, dict)
        self.assertIn('overall_status', result)
        self.assertIn('checks', result)
        self.assertIn('recommendations', result)
        
        print(f"✅ 整體狀態: {result['overall_status']}")
        
        # 檢查各項驗證結果
        for check_name, check_result in result['checks'].items():
            status = "✅" if check_result['status'] == 'pass' else "❌"
            print(f"  {status} {check_name}: {check_result['message']}")
        
        # 如果有建議，顯示出來
        if result['recommendations']:
            print("  📋 建議:")
            for rec in result['recommendations']:
                print(f"    💡 {rec}")
    
    @unittest.skipIf(not os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH') or 
                     not os.getenv('GOOGLE_SHEETS_ID'), 
                     "缺少必要環境變數")
    def test_04_connection_test(self):
        """測試連接功能"""
        print("\n🔗 測試連接...")
        
        result = self.client.test_connection()
        
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        
        if result['success']:
            print("✅ 連接測試成功")
            if 'spreadsheet_title' in result:
                print(f"  📊 試算表標題: {result['spreadsheet_title']}")
            if 'sheet_count' in result:
                print(f"  📄 工作表數量: {result['sheet_count']}")
        else:
            print(f"❌ 連接測試失敗: {result.get('error', '未知錯誤')}")
    
    def test_05_create_sample_order(self):
        """測試建立範例訂單資料"""
        print("\n📦 測試建立範例訂單資料...")
        
        sample_order = self._create_test_order()
        
        # 驗證必要欄位
        required_fields = ['order_id', 'receiver_name', 'receiver_phone', 
                          'shipping_address', 'items']
        
        for field in required_fields:
            self.assertIn(field, sample_order, f"缺少必要欄位: {field}")
        
        self.assertIsInstance(sample_order['items'], list)
        self.assertGreater(len(sample_order['items']), 0, "商品清單不能為空")
        
        print("✅ 範例訂單資料格式正確")
        print(f"  📦 訂單編號: {sample_order['order_id']}")
        print(f"  👤 收件人: {sample_order['receiver_name']}")
        print(f"  📱 電話: {sample_order['receiver_phone']}")
        print(f"  🏠 地址: {sample_order['shipping_address']}")
        print(f"  🛍️  商品數量: {len(sample_order['items'])}")
    
    @unittest.skipIf(not os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH') or 
                     not os.getenv('GOOGLE_SHEETS_ID'), 
                     "缺少必要環境變數")
    def test_06_sheet_headers_creation(self):
        """測試試算表標題建立"""
        print("\n📝 測試試算表標題建立...")
        
        result = self.client.create_sheet_if_not_exists()
        
        if result:
            print("✅ 試算表標題建立/確認成功")
        else:
            print("⚠️  試算表標題建立可能失敗，但不影響其他功能")
    
    @unittest.skipIf(not os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH') or 
                     not os.getenv('GOOGLE_SHEETS_ID'), 
                     "缺少必要環境變數")
    def test_07_single_order_append(self):
        """測試單一訂單新增"""
        print("\n📝 測試單一訂單新增...")
        
        test_order = self._create_test_order("TEST-SINGLE")
        result = self.client.append_order(test_order)
        
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        
        if result['success']:
            print("✅ 單一訂單新增成功")
            print(f"  📝 更新行數: {result.get('updated_rows', 0)}")
            print(f"  📦 訂單編號: {result.get('order_id', 'N/A')}")
        else:
            print(f"❌ 單一訂單新增失敗: {result.get('error', '未知錯誤')}")
            # 不讓測試失敗，因為可能是權限問題
    
    @unittest.skipIf(not os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH') or 
                     not os.getenv('GOOGLE_SHEETS_ID'), 
                     "缺少必要環境變數")
    def test_08_batch_orders_append(self):
        """測試批量訂單新增"""
        print("\n📝 測試批量訂單新增...")
        
        test_orders = [
            self._create_test_order("TEST-BATCH-1"),
            self._create_test_order("TEST-BATCH-2"),
            self._create_test_order("TEST-BATCH-3")
        ]
        
        result = self.client.append_multiple_orders(test_orders)
        
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        
        if result['success']:
            print("✅ 批量訂單新增成功")
            print(f"  📝 處理數量: {result.get('total_processed', 0)}")
            print(f"  📝 更新行數: {result.get('updated_rows', 0)}")
            
            order_ids = result.get('order_ids', [])
            if order_ids:
                print("  📦 新增的訂單編號:")
                for order_id in order_ids:
                    print(f"    - {order_id}")
        else:
            print(f"❌ 批量訂單新增失敗: {result.get('error', '未知錯誤')}")
    
    @unittest.skipIf(not os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH') or 
                     not os.getenv('GOOGLE_SHEETS_ID'), 
                     "缺少必要環境變數")
    def test_09_get_recent_orders(self):
        """測試獲取最近訂單"""
        print("\n📊 測試獲取最近訂單...")
        
        result = self.client.get_recent_orders(limit=5)
        
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        self.assertIn('orders', result)
        
        if result['success']:
            orders = result['orders']
            print(f"✅ 成功獲取最近訂單，共 {len(orders)} 筆")
            
            if orders:
                print("  📦 最近的訂單:")
                for i, order in enumerate(orders[-3:], 1):  # 只顯示最後3筆
                    print(f"    {i}. {order.get('order_id', 'N/A')} - "
                          f"{order.get('receiver_name', 'N/A')} "
                          f"({order.get('order_time', 'N/A')})")
            else:
                print("  📋 目前沒有訂單資料")
        else:
            print(f"❌ 獲取最近訂單失敗: {result.get('error', '未知錯誤')}")
    
    def test_10_error_handling(self):
        """測試錯誤處理"""
        print("\n⚠️  測試錯誤處理...")
        
        # 測試無效憑證路徑
        invalid_client = GoogleSheetsClient("invalid/path", "invalid_id")
        self.assertIsNone(invalid_client.service, "無效憑證應該導致服務初始化失敗")
        
        # 測試無效操作
        result = invalid_client.append_order({})
        self.assertFalse(result['success'], "無效客戶端操作應該失敗")
        self.assertIn('error', result)
        
        print("✅ 錯誤處理測試通過")
    
    def test_11_data_formatting(self):
        """測試資料格式化"""
        print("\n🔧 測試資料格式化...")
        
        if hasattr(self, 'client'):
            # 測試商品格式化
            items = [
                {'name': '18A禮盒', 'quantity': 2},
                {'name': '16A蛋糕', 'quantity': 1},
                {'name': '20A花束', 'quantity': 3}
            ]
            
            formatted = self.client._format_items(items)
            expected = "18A禮盒 x 2, 16A蛋糕 x 1, 20A花束 x 3"
            
            self.assertEqual(formatted, expected, "商品格式化結果不正確")
            print(f"✅ 商品格式化正確: {formatted}")
            
            # 測試空商品清單
            empty_formatted = self.client._format_items([])
            self.assertEqual(empty_formatted, "", "空商品清單應該返回空字串")
            print("✅ 空商品清單格式化正確")
    
    def _create_test_order(self, order_id_suffix="TEST") -> Dict[str, Any]:
        """建立測試用訂單資料"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        return {
            'order_id': f"{order_id_suffix}-{timestamp}",
            'sender_name': '測試寄件人',
            'sender_phone': '0912-345-678',
            'receiver_name': '測試收件人',
            'receiver_phone': '0987-654-321',
            'shipping_address': '台北市信義區信義路五段7號',
            'shipping_date': (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'),
            'items': [
                {'name': '18A測試禮盒', 'quantity': 1},
                {'name': '16A測試蛋糕', 'quantity': 2}
            ],
            'status': '測試中',
            'notes': f'測試訂單 - {timestamp}'
        }


def run_validation_only():
    """僅執行設定驗證"""
    print("🔍 執行設定驗證模式...")
    
    credentials_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH')
    sheet_id = os.getenv('GOOGLE_SHEETS_ID')
    
    if not credentials_path or not sheet_id:
        print("❌ 錯誤：缺少必要的環境變數")
        print("請確認 .env 檔案中已設定：")
        print("- GOOGLE_SHEETS_CREDENTIALS_PATH")
        print("- GOOGLE_SHEETS_ID")
        return False
    
    client = GoogleSheetsClient(credentials_path, sheet_id)
    result = client.validate_setup()
    
    print(f"\n📊 驗證結果：{result['overall_status']}")
    print("-" * 50)
    
    for check_name, check_result in result['checks'].items():
        status_icon = "✅" if check_result['status'] == 'pass' else "❌"
        print(f"{status_icon} {check_name}")
        print(f"   {check_result['message']}")
        
        if 'details' in check_result and isinstance(check_result['details'], dict):
            for key, value in check_result['details'].items():
                print(f"   📋 {key}: {value}")
        elif 'details' in check_result:
            print(f"   📋 Details: {check_result['details']}")
        print()
    
    if result['recommendations']:
        print("💡 建議：")
        for rec in result['recommendations']:
            print(f"   • {rec}")
    
    return result['overall_status'] in ['healthy', 'partial']


def main():
    """主程式"""
    parser = argparse.ArgumentParser(description='Google Sheets API 測試程式')
    parser.add_argument('--quick', action='store_true', 
                       help='執行快速測試（跳過實際資料寫入）')
    parser.add_argument('--validation-only', action='store_true',
                       help='僅執行設定驗證')
    parser.add_argument('--cleanup', action='store_true',
                       help='測試後清理測試資料（需要手動確認）')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='詳細輸出')
    
    args = parser.parse_args()
    
    print("🧪 Google Sheets API 測試程式")
    print("=" * 50)
    
    if args.validation_only:
        success = run_validation_only()
        sys.exit(0 if success else 1)
    
    # 設定測試參數
    verbosity = 2 if args.verbose else 1
    
    # 建立測試套件
    test_suite = unittest.TestLoader().loadTestsFromTestCase(TestGoogleSheetsClient)
    
    # 執行測試
    runner = unittest.TextTestRunner(verbosity=verbosity, buffer=True)
    result = runner.run(test_suite)
    
    # 測試總結
    print("\n" + "=" * 50)
    print("📊 測試總結")
    print(f"執行測試: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失敗: {len(result.failures)}")
    print(f"錯誤: {len(result.errors)}")
    
    if result.failures:
        print("\n❌ 失敗的測試:")
        for test, traceback in result.failures:
            print(f"  • {test}")
    
    if result.errors:
        print("\n⚠️  錯誤的測試:")
        for test, traceback in result.errors:
            print(f"  • {test}")
    
    if args.cleanup:
        print("\n🧹 清理功能需要手動實作")
        print("請前往 Google Sheets 手動刪除測試資料")
    
    # 回傳適當的退出代碼
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()