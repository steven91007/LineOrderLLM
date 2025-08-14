"""
LIFF (LINE Front-end Framework) 處理器
用於處理 LIFF 應用程式的訂單編輯功能
"""
from flask import Flask, request, jsonify, render_template, session
import json
import uuid
from typing import Dict, Any, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class LIFFHandler:
    """LIFF 應用程式處理器"""
    
    def __init__(self, order_handler=None, google_sheets_client=None):
        """
        初始化 LIFF 處理器
        
        Args:
            order_handler: 訂單處理器實例
            google_sheets_client: Google Sheets 客戶端
        """
        self.order_handler = order_handler
        self.google_sheets_client = google_sheets_client
        # 暫存 LIFF 編輯會話（生產環境建議使用 Redis）
        self.liff_sessions = {}
        
    def create_liff_session(self, user_id: str, orders_data: Dict[str, Any]) -> str:
        """
        建立 LIFF 編輯會話
        
        Args:
            user_id: LINE 用戶 ID
            orders_data: 訂單資料
            
        Returns:
            str: 會話 ID
        """
        session_id = str(uuid.uuid4())
        
        self.liff_sessions[session_id] = {
            'user_id': user_id,
            'orders': orders_data.get('orders', []),
            'total_orders': orders_data.get('total_orders', 0),
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(hours=2)  # 2小時過期
        }
        
        logger.info(f"Created LIFF session {session_id} for user {user_id}")
        return session_id
    
    def get_liff_session(self, session_id: str) -> Dict[str, Any]:
        """
        獲取 LIFF 編輯會話
        
        Args:
            session_id: 會話 ID
            
        Returns:
            Dict: 會話資料
        """
        session_data = self.liff_sessions.get(session_id)
        
        if not session_data:
            return {'success': False, 'error': '會話不存在或已過期'}
        
        # 檢查是否過期
        if datetime.now() > session_data['expires_at']:
            del self.liff_sessions[session_id]
            return {'success': False, 'error': '會話已過期'}
        
        return {
            'success': True,
            'orders': session_data['orders'],
            'total_orders': session_data['total_orders'],
            'user_id': session_data['user_id']
        }
    
    def update_liff_session(self, session_id: str, updated_orders: List[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
        """
        更新 LIFF 編輯會話中的訂單
        
        Args:
            session_id: 會話 ID
            updated_orders: 更新後的訂單列表
            user_id: 用戶 ID (驗證用)
            
        Returns:
            Dict: 更新結果
        """
        session_data = self.liff_sessions.get(session_id)
        
        if not session_data:
            return {'success': False, 'error': '會話不存在或已過期'}
        
        # 驗證用戶
        if session_data['user_id'] != user_id:
            return {'success': False, 'error': '無權限修改此會話'}
        
        # 檢查是否過期
        if datetime.now() > session_data['expires_at']:
            del self.liff_sessions[session_id]
            return {'success': False, 'error': '會話已過期'}
        
        try:
            # 驗證訂單資料
            validated_orders = self._validate_orders(updated_orders)
            
            if not validated_orders['is_valid']:
                return {'success': False, 'error': validated_orders['error']}
            
            # 更新會話資料
            session_data['orders'] = validated_orders['orders']
            session_data['total_orders'] = len(validated_orders['orders'])
            session_data['updated_at'] = datetime.now()
            
            # 如果有 Google Sheets 客戶端，寫入試算表
            if self.google_sheets_client:
                try:
                    result = self.google_sheets_client.write_orders_batch(validated_orders['orders'])
                    logger.info(f"Orders written to Google Sheets: {result}")
                except Exception as e:
                    logger.error(f"Failed to write to Google Sheets: {e}")
                    # 不影響主要流程，僅記錄錯誤
            
            # 清除會話（編輯完成）
            del self.liff_sessions[session_id]
            
            return {
                'success': True,
                'message': '訂單更新成功',
                'total_orders': len(validated_orders['orders'])
            }
            
        except Exception as e:
            logger.error(f"Error updating LIFF session {session_id}: {e}")
            return {'success': False, 'error': f'更新失敗: {str(e)}'}
    
    def _validate_orders(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        驗證訂單列表
        
        Args:
            orders: 訂單列表
            
        Returns:
            Dict: 驗證結果
        """
        if not isinstance(orders, list):
            return {'is_valid': False, 'error': '訂單資料格式錯誤'}
        
        if len(orders) == 0:
            return {'is_valid': False, 'error': '至少需要一筆訂單'}
        
        if len(orders) > 5:
            return {'is_valid': False, 'error': '訂單數量超過限制（最多5筆）'}
        
        validated_orders = []
        
        for i, order in enumerate(orders):
            # 驗證必填欄位
            if not order.get('receiver_name'):
                return {'is_valid': False, 'error': f'訂單 {i+1} 缺少收件人姓名'}
            
            if not order.get('receiver_phone'):
                return {'is_valid': False, 'error': f'訂單 {i+1} 缺少收件人電話'}
            
            if not order.get('shipping_address'):
                return {'is_valid': False, 'error': f'訂單 {i+1} 缺少收件地址'}
            
            # 驗證商品項目
            items = order.get('items', [])
            if not items or len(items) == 0:
                return {'is_valid': False, 'error': f'訂單 {i+1} 至少需要一個商品項目'}
            
            # 清理和驗證商品項目
            validated_items = []
            for item in items:
                if not item.get('name') or not item.get('name').strip():
                    continue  # 跳過空白商品
                
                validated_item = {
                    'name': item['name'].strip(),
                    'quantity': max(1, int(item.get('quantity', 1)))
                }
                validated_items.append(validated_item)
            
            if not validated_items:
                return {'is_valid': False, 'error': f'訂單 {i+1} 沒有有效的商品項目'}
            
            # 驗證和標準化日期
            shipping_date = order.get('shipping_date', '').strip()
            if shipping_date:
                # 驗證 MM-DD 格式
                try:
                    parts = shipping_date.split('-')
                    if len(parts) != 2:
                        return {'is_valid': False, 'error': f'訂單 {i+1} 日期格式錯誤，請使用 MM-DD 格式'}
                    
                    month, day = int(parts[0]), int(parts[1])
                    if month < 1 or month > 12 or day < 1 or day > 31:
                        return {'is_valid': False, 'error': f'訂單 {i+1} 日期數值無效'}
                    
                    # 標準化格式
                    shipping_date = f"{month:02d}-{day:02d}"
                except:
                    return {'is_valid': False, 'error': f'訂單 {i+1} 日期格式錯誤'}
            
            # 建立驗證後的訂單
            sender_name = order.get('sender_name') or ''
            sender_phone = order.get('sender_phone') or ''
            
            validated_order = {
                'sender_name': sender_name.strip() if sender_name else None,
                'sender_phone': sender_phone.strip() if sender_phone else None,
                'receiver_name': order['receiver_name'].strip(),
                'receiver_phone': order['receiver_phone'].strip(),
                'items': validated_items,
                'shipping_date': shipping_date if shipping_date else None,
                'shipping_address': order['shipping_address'].strip()
            }
            
            validated_orders.append(validated_order)
        
        return {'is_valid': True, 'orders': validated_orders}
    
    def cleanup_expired_sessions(self):
        """清理過期的會話"""
        expired_sessions = []
        current_time = datetime.now()
        
        for session_id, session_data in self.liff_sessions.items():
            if current_time > session_data['expires_at']:
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del self.liff_sessions[session_id]
            logger.info(f"Cleaned up expired LIFF session: {session_id}")
    
    def get_liff_url(self, session_id: str, liff_id: str = None, base_url: str = None) -> str:
        """
        獲取 LIFF 應用程式 URL
        使用 OAuth2 state 參數攜帶 session ID，保持 redirectUri 乾淨
        
        Args:
            session_id: 會話 ID（將放入 state 參數）
            liff_id: LIFF 應用程式 ID
            base_url: 基礎 URL（從 request 或環境變數取得）
            
        Returns:
            str: LIFF URL
        """
        if liff_id:
            # 使用乾淨的 redirectUri（不包含 session 參數）
            if base_url:
                redirect_uri = f"{base_url}/liff/edit"
            else:
                # 降級方案：使用相對路徑
                redirect_uri = "/liff/edit"
            
            # session ID 會在前端透過 state 參數攜帶，這裡只提供基礎 URL
            return f"https://liff.line.me/{liff_id}?liffRedirectUri={redirect_uri}&sessionId={session_id}"
        else:
            # 如果沒有 LIFF ID，返回 Web 版本 URL（保持原有功能）
            return f"/liff/edit?session={session_id}"

# Flask 路由設定
def setup_liff_routes(app: Flask, liff_handler: LIFFHandler):
    """設定 LIFF 相關路由"""
    
    @app.route('/liff/edit')
    def liff_edit_page():
        """LIFF 編輯頁面"""
        session_id = request.args.get('session')
        if not session_id:
            return "缺少會話 ID", 400
        
        # 從環境變數或參數取得 LIFF ID
        import os
        liff_id = os.getenv('LIFF_ID', '')
        return render_template('liff_order_edit.html', session_id=session_id, LIFF_ID=liff_id)
    
    @app.route('/liff/simple')
    def liff_simple_page():
        """簡化版編輯頁面 - 無需 LIFF 登入"""
        session_id = request.args.get('session')
        if not session_id:
            return "缺少會話 ID", 400
        
        return render_template('liff_simple.html', session_id=session_id)
    
    @app.route('/api/liff/orders/<session_id>', methods=['GET'])
    def get_liff_orders(session_id):
        """獲取 LIFF 會話中的訂單"""
        result = liff_handler.get_liff_session(session_id)
        return jsonify(result)
    
    @app.route('/api/liff/orders/<session_id>', methods=['PUT'])
    def update_liff_orders(session_id):
        """更新 LIFF 會話中的訂單"""
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': '請求資料格式錯誤'}), 400
        
        user_id = data.get('user_id')
        orders = data.get('orders', [])
        
        if not user_id:
            return jsonify({'success': False, 'error': '缺少用戶 ID'}), 400
        
        result = liff_handler.update_liff_session(session_id, orders, user_id)
        
        return jsonify(result)
    
    @app.route('/api/liff/cleanup', methods=['POST'])
    def cleanup_liff_sessions():
        """清理過期會話（可定期呼叫）"""
        liff_handler.cleanup_expired_sessions()
        return jsonify({'success': True, 'message': '清理完成'})