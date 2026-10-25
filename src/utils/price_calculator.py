"""
Price calculation module
Computes the total price and shipping from product information.

Note: price-list keys, product names and the detail strings returned below are Chinese on purpose
(matched against data / shown in order output) and must not be translated.
"""

import re
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)


class PriceCalculator:
    def __init__(self):
        """Initialize the price calculator"""
        self.price_list = {
            "家庭號": {  # Family pack: one case, two layers, 12 pieces
                "18A 優惠首選": {
                    "價格": 1850
                },
                "20A": {
                    "價格": 2110,
                }
            },
            "雙雙對對": {  # Fixed unit price, no size variants
                "雙雙對對": {"價格": 3400}
            },
            "精選禮盒": {  # Gift box: one layer per box, 6 pieces per box
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
        Calculate the total price of the items (prices already include shipping)
        
        Args:
            items: List of items, each with name and quantity
            
        Returns:
            tuple: (total price, detail text)
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
            
            # Parse the product info
            product_info = self._parse_product_name(name)
            if not product_info:
                details.append(f"{name} x {quantity}: 無法識別商品")
                continue
            
            # Calculate this item's price (shipping included)
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
        Parse a product name, extracting the product type and size spec
        
        Args:
            name: Product name
            
        Returns:
            dict: Parse result {type, spec}, or None
        """
        name = name.strip()
        
        # Strip whitespace so "18 A" becomes "18A"
        name = re.sub(r'\s+', '', name)

        # "雙雙對對": fixed-price product with no 18A/20A size spec
        if '雙雙對對' in name:
            return {"type": "雙雙對對", "spec": "雙雙對對"}

        # Match the 18A or 20A spec (including variants with whitespace)
        spec_match = re.search(r'(18\s*A|20\s*A)', name, re.IGNORECASE)
        if not spec_match:
            return None
        
        spec = re.sub(r'\s+', '', spec_match.group(1).upper())
        
        # Determine the product type
        if any(keyword in name for keyword in ['家庭號', '家庭', '一箱']):
            product_type = "家庭號"
        elif any(keyword in name for keyword in ['禮盒', '精選', '盒']):
            product_type = "精選禮盒"
        else:
            # Default to gift box
            product_type = "精選禮盒"
        
        # Resolve the full product spec name from the size
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
        Calculate the price of a single item (shipping included)
        
        Args:
            product_info: Product info
            quantity: Quantity
            
        Returns:
            tuple: (total price, detail text)
        """
        product_type = product_info["type"]
        spec = product_info["spec"]
        
        if product_type not in self.price_list:
            return 0, "未知產品類型"
        
        type_info = self.price_list[product_type]
        if spec not in type_info:
            return 0, "未知產品規格"
        
        spec_info = type_info[spec]
        
        if product_type == "雙雙對對":
            # Fixed unit price: just multiply by quantity
            unit_price = spec_info["價格"]
            total_price = unit_price * quantity

            detail = f"${unit_price} x {quantity}"
            return total_price, detail

        if product_type == "家庭號":
            # Family pack: just multiply by quantity (12 pieces per case)
            unit_price = spec_info["價格"]
            total_price = unit_price * quantity

            detail = f"${unit_price}/箱 x {quantity}"
            return total_price, detail

        elif product_type == "精選禮盒":
            # Gift box: priced by number of boxes
            return self._calculate_giftbox_price(spec_info, quantity)
        
        return 0, "計算錯誤"
    
    def _calculate_giftbox_price(self, spec_info: Dict[str, Any], total_quantity: int) -> Tuple[int, str]:
        """
        Calculate the best-value price combination for gift boxes (shipping included)
        
        Args:
            spec_info: Spec info
            total_quantity: Total quantity (number of pieces)
            
        Returns:
            tuple: (total price, detail text)
        """
        # New pricing structure: priced directly by number of boxes
        # total_quantity is already a box count here; no need to divide by 6
        boxes_needed = total_quantity
        
        # Pick the price matching the box count
        if str(boxes_needed) in spec_info:
            total_price = spec_info[str(boxes_needed)]["價格"]
            detail = f"{boxes_needed}盒"
        elif boxes_needed <= 4:
            # If the box count is within 1-4, use the matching price directly
            price_key = str(min(boxes_needed, 4))
            if price_key in spec_info:
                total_price = spec_info[price_key]["價格"]
                detail = f"{boxes_needed}盒"
            else:
                total_price = 0
                detail = "找不到對應價格"
        else:
            # More than 4 boxes: use the 4-box price as the base
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
        Get detailed product info
        
        Args:
            name: Product name
            
        Returns:
            dict: Product info, or an empty dict
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