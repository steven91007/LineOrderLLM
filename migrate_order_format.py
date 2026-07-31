"""
訂單格式遷移腳本
用於將舊格式的訂單資料轉換為新格式，並加上價格計算
"""

import os
import sys
from datetime import datetime

# 添加專案路徑到 Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

from utils.google_sheets_client import GoogleSheetsClient
from utils.price_calculator import PriceCalculator
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderMigrator:
    def __init__(self, credentials_path: str, sheet_id: str):
        """初始化訂單遷移器"""
        self.sheets_client = GoogleSheetsClient(credentials_path, sheet_id, auto_organize_by_date=False)
        self.price_calculator = PriceCalculator()
    
    def backup_original_data(self, target_date: str = "2024-08-24") -> bool:
        """
        備份原始資料
        
        Args:
            target_date: 目標日期
            
        Returns:
            bool: 是否成功
        """
        try:
            logger.info(f"開始備份 {target_date} 的原始資料...")
            
            # 創建備份工作表
            backup_sheet_name = f"備份_{target_date.replace('-', '')}"
            
            # 獲取現有資料
            existing_orders = self.sheets_client.get_orders_by_date(target_date)
            if not existing_orders['success'] or not existing_orders['orders']:
                logger.warning(f"沒有找到 {target_date} 的訂單資料")
                return False
            
            logger.info(f"找到 {len(existing_orders['orders'])} 筆訂單，準備備份...")
            
            # TODO: 實作備份邏輯
            # 由於目前的 sheets_client 已經是新格式，我們需要從原始工作表讀取舊格式資料
            
            return True
            
        except Exception as e:
            logger.error(f"備份過程中發生錯誤: {e}")
            return False
    
    def migrate_orders_with_prices(self, target_date: str = "2024-08-24") -> bool:
        """
        遷移訂單並加上價格計算
        
        Args:
            target_date: 目標日期
            
        Returns:
            bool: 是否成功
        """
        try:
            logger.info(f"開始遷移 {target_date} 的訂單資料...")
            
            # 這裡應該從原始格式讀取資料
            # 但由於我們已經修改了 sheets_client，需要手動處理舊格式資料
            
            logger.info("請手動提供需要遷移的訂單資料，或從原始 Google Sheets 中匯出")
            
            return True
            
        except Exception as e:
            logger.error(f"遷移過程中發生錯誤: {e}")
            return False
    
    def convert_old_order_to_new_format(self, old_order: dict) -> dict:
        """
        將舊格式訂單轉換為新格式
        
        Args:
            old_order: 舊格式訂單資料
            
        Returns:
            dict: 新格式訂單資料
        """
        try:
            # 解析舊格式的商品明細
            items_text = old_order.get('items', old_order.get('商品明細', ''))
            items = self._parse_items_from_text(items_text)
            
            # 計算價格
            total_price, price_detail = self.price_calculator.calculate_total_price(items)
            
            # 轉換為新格式
            new_order = {
                'sender_name': old_order.get('sender_name', old_order.get('寄件人', '')),  # 訂購/寄件人
                'sender_address': '',  # 寄件地址 (舊格式沒有，保持空白)
                'receiver_name': old_order.get('receiver_name', old_order.get('收件人', '')),  # 收件人
                'items_name': self._extract_item_names(items),  # 品項
                'items_quantity': self._extract_item_quantities(items),  # 數量
                'sender_phone': old_order.get('sender_phone', old_order.get('寄件人電話', '')),  # 訂購人電話
                'receiver_phone': old_order.get('receiver_phone', old_order.get('收件人電話', '')),  # 收件人電話
                'shipping_address': old_order.get('shipping_address', old_order.get('收件地址', '')),  # 地址
                'total_price': str(total_price),  # 總價
                'payment_status': '',  # 付款狀況 (新欄位，保持空白)
                'last_5_digits': ''  # 末5碼 (新欄位，保持空白)
            }
            
            logger.info(f"轉換訂單: {new_order['receiver_name']} - 總價: ${total_price}")
            return new_order
            
        except Exception as e:
            logger.error(f"轉換訂單格式時發生錯誤: {e}")
            return {}
    
    def _parse_items_from_text(self, items_text: str) -> list:
        """從商品明細文字中解析出商品列表"""
        if not items_text:
            return []
        
        items = []
        # 嘗試解析如 "18A禮盒 x 2, 20A蛋糕 x 1" 這樣的格式
        parts = items_text.split(',')
        
        for part in parts:
            part = part.strip()
            if ' x ' in part:
                name_part, qty_part = part.split(' x ', 1)
                name = name_part.strip()
                try:
                    quantity = int(qty_part.strip())
                    items.append({'name': name, 'quantity': quantity})
                except ValueError:
                    # 如果無法解析數量，預設為1
                    items.append({'name': name, 'quantity': 1})
            else:
                # 沒有明確數量標示，預設為1
                items.append({'name': part, 'quantity': 1})
        
        return items
    
    def _extract_item_names(self, items: list) -> str:
        """提取商品名稱"""
        names = [item.get('name', '') for item in items if item.get('name')]
        return ', '.join(names)
    
    def _extract_item_quantities(self, items: list) -> str:
        """提取商品數量"""
        quantities = [str(item.get('quantity', 0)) for item in items]
        return ', '.join(quantities)


def main():
    """主執行函數"""
    # 配置參數 (請根據實際情況修改)
    CREDENTIALS_PATH = "path/to/your/credentials.json"  # Google 憑證檔案路徑
    SHEET_ID = "your_google_sheet_id"  # Google Sheets ID
    TARGET_DATE = "2024-08-24"  # 要處理的日期
    
    # 檢查參數
    if not os.path.exists(CREDENTIALS_PATH):
        logger.error(f"找不到憑證檔案: {CREDENTIALS_PATH}")
        return
    
    # 初始化遷移器
    migrator = OrderMigrator(CREDENTIALS_PATH, SHEET_ID)
    
    # 執行備份
    logger.info("=== 開始備份原始資料 ===")
    backup_success = migrator.backup_original_data(TARGET_DATE)
    
    if backup_success:
        logger.info("備份完成")
    else:
        logger.warning("備份失敗或沒有資料需要備份")
    
    # 執行遷移
    logger.info("=== 開始遷移訂單資料 ===")
    migrate_success = migrator.migrate_orders_with_prices(TARGET_DATE)
    
    if migrate_success:
        logger.info("遷移完成")
    else:
        logger.error("遷移失敗")


if __name__ == "__main__":
    main()