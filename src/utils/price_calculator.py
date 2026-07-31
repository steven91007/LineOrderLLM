"""
價格計算模組
用於根據商品資訊計算總價格和運費
"""

import re
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class PriceCalculator:
    def __init__(self):
        """初始化價格計算器"""
        self.price_list = {
            "家庭號": {  # 一箱兩層、12顆
                "18A 優惠首選": {
                    "價格": 1850
                },
                "20A": {
                    "價格": 2110,
                }
            },
            "精選禮盒": {  # 一盒一層、每盒6顆
                "18A 優惠首選": {
                    "重量範圍": "600g ~ 635g",
                    "1": {"價格": 1020},
                    "2": {"價格": 1910},
                    "3": {"價格": 2810},
                    "4": {"價格": 3700},
                },
                "20A 大口滿足": {
                    "重量範圍": "640g ~ 710g",
                    "1": {"價格": 1150},
                    "2": {"價格": 2170},
                    "3": {"價格": 3200},
                    "4": {"價格": 4220},
                }
            }
        }
    
    def calculate_total_price(self, items: List[Dict[str, Any]]) -> Tuple[int, str]:
        """
        計算商品總價（價格已包含運費）
        
        Args:
            items: 商品列表，每個商品包含 name 和 quantity
            
        Returns:
            tuple: (總價, 詳細說明)
        """
        if not items:
            return 0, "無商品"
        
        total_price = 0
        details = []
        
        for item in items:
            name = item.get('name', '').strip()
            quantity = item.get('quantity', 0)
            
            if not name or quantity <= 0:
                continue
            
            # 解析商品資訊
            product_info = self._parse_product_name(name)
            if not product_info:
                details.append(f"{name} x {quantity}: 無法識別商品")
                continue
            
            # 計算該商品的價格（已包含運費）
            item_price, item_detail = self._calculate_item_price(
                product_info, quantity
            )
            
            total_price += item_price
            details.append(f"{name} x {quantity}: {item_detail}")
        
        summary = f"總計: ${total_price}"
        
        if details:
            full_detail = "\n".join(details) + f"\n{summary}"
        else:
            full_detail = "無可識別商品"
        
        return total_price, full_detail
    
    def _parse_product_name(self, name: str) -> Dict[str, Any]:
        """
        解析商品名稱，提取產品類型和規格
        
        Args:
            name: 商品名稱
            
        Returns:
            dict: 解析結果 {type, spec} 或 None
        """
        name = name.strip()
        
        # 去除空白字元，讓 "18 A" 變成 "18A"
        name = re.sub(r'\s+', '', name)
        
        # 匹配 18A 或 20A 規格（包含空白的情況）
        spec_match = re.search(r'(18\s*A|20\s*A)', name, re.IGNORECASE)
        if not spec_match:
            return None
        
        spec = re.sub(r'\s+', '', spec_match.group(1).upper())
        
        # 判斷產品類型
        if any(keyword in name for keyword in ['家庭號', '家庭', '一箱']):
            product_type = "家庭號"
        elif any(keyword in name for keyword in ['禮盒', '精選', '盒']):
            product_type = "精選禮盒"
        else:
            # 預設為禮盒
            product_type = "精選禮盒"
        
        # 根據規格確定完整產品名稱
        if spec == "18A":
            full_spec = "18A 優惠首選"
        elif spec == "20A":
            if product_type == "家庭號":
                full_spec = "20A"
            else:
                full_spec = "20A 大口滿足"
        else:
            return None
        
        return {
            "type": product_type,
            "spec": full_spec
        }
    
    def _calculate_item_price(self, product_info: Dict[str, Any], quantity: int) -> Tuple[int, str]:
        """
        計算單一商品的價格（已包含運費）
        
        Args:
            product_info: 商品資訊
            quantity: 數量
            
        Returns:
            tuple: (總價格, 詳細說明)
        """
        product_type = product_info["type"]
        spec = product_info["spec"]
        
        if product_type not in self.price_list:
            return 0, "未知產品類型"
        
        type_info = self.price_list[product_type]
        if spec not in type_info:
            return 0, "未知產品規格"
        
        spec_info = type_info[spec]
        
        if product_type == "家庭號":
            # 家庭號：直接按數量計算（一箱12顆）
            unit_price = spec_info["價格"]
            total_price = unit_price * quantity
            
            detail = f"${unit_price}/箱 x {quantity}"
            return total_price, detail
        
        elif product_type == "精選禮盒":
            # 精選禮盒：直接按盒數計算
            return self._calculate_giftbox_price(spec_info, quantity)
        
        return 0, "計算錯誤"
    
    def _calculate_giftbox_price(self, spec_info: Dict[str, Any], total_quantity: int) -> Tuple[int, str]:
        """
        計算精選禮盒的最優惠價格組合（已包含運費）
        
        Args:
            spec_info: 規格資訊
            total_quantity: 總數量（顆數）
            
        Returns:
            tuple: (總價格, 詳細說明)
        """
        # 新的定價結構：直接按盒數計算
        # total_quantity 在這裡已經是盒數了，不需要再除以6
        boxes_needed = total_quantity
        
        # 根據盒數選擇對應價格
        if str(boxes_needed) in spec_info:
            total_price = spec_info[str(boxes_needed)]["價格"]
            detail = f"{boxes_needed}盒"
        elif boxes_needed <= 4:
            # 如果盒數在1-4範圍內，直接使用對應價格
            price_key = str(min(boxes_needed, 4))
            if price_key in spec_info:
                total_price = spec_info[price_key]["價格"]
                detail = f"{boxes_needed}盒"
            else:
                total_price = 0
                detail = "找不到對應價格"
        else:
            # 超過4盒的情況，使用4盒價格作為基準
            if "4" in spec_info:
                base_price_per_4_boxes = spec_info["4"]["價格"]
                sets_of_4 = boxes_needed // 4
                remaining_boxes = boxes_needed % 4
                
                total_price = base_price_per_4_boxes * sets_of_4
                
                if remaining_boxes > 0 and str(remaining_boxes) in spec_info:
                    total_price += spec_info[str(remaining_boxes)]["價格"]
                
                detail = f"{boxes_needed}盒"
            else:
                total_price = 0
                detail = "找不到對應價格"
        
        return total_price, detail
    
    def get_product_info(self, name: str) -> Dict[str, Any]:
        """
        獲取商品詳細資訊
        
        Args:
            name: 商品名稱
            
        Returns:
            dict: 商品資訊或空字典
        """
        product_info = self._parse_product_name(name)
        if not product_info:
            return {}
        
        product_type = product_info["type"]
        spec = product_info["spec"]
        
        if product_type in self.price_list and spec in self.price_list[product_type]:
            return {
                "type": product_type,
                "spec": spec,
                "info": self.price_list[product_type][spec]
            }
        
        return {}