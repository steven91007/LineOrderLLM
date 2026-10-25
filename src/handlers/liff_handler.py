"""
LIFF (LINE Front-end Framework) handler
Handles order editing for the LIFF app.

Error strings returned in API responses below are shown to staff in the LIFF UI,
so they stay in Chinese.
"""
from flask import Flask, request, jsonify, render_template, session
import json
import uuid
from typing import Dict, Any, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class LIFFHandler:
    """Handler for the LIFF app."""
    
    def __init__(self, order_handler=None, google_sheets_client=None):
        """
        Initialize the LIFF handler.
        
        Args:
            order_handler: order handler instance
            google_sheets_client: Google Sheets client
        """
        self.order_handler = order_handler
        self.google_sheets_client = google_sheets_client
        # In-memory store for LIFF edit sessions (Redis is recommended in production)
        self.liff_sessions = {}
        
    def create_liff_session(self, user_id: str, orders_data: Dict[str, Any]) -> str:
        """
        Create a LIFF edit session.
        
        Args:
            user_id: LINE user ID
            orders_data: order data
            
        Returns:
            str: session ID
        """
        session_id = str(uuid.uuid4())
        
        self.liff_sessions[session_id] = {
            'user_id': user_id,
            'orders': orders_data.get('orders', []),
            'total_orders': orders_data.get('total_orders', 0),
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(hours=2)  # Expires after 2 hours
        }
        
        logger.info(f"Created LIFF session {session_id} for user {user_id}")
        return session_id
    
    def get_liff_session(self, session_id: str) -> Dict[str, Any]:
        """
        Get a LIFF edit session.
        
        Args:
            session_id: session ID
            
        Returns:
            Dict: session data
        """
        session_data = self.liff_sessions.get(session_id)
        
        if not session_data:
            return {'success': False, 'error': '會話不存在或已過期'}
        
        # Check whether it has expired
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
        Update the orders in a LIFF edit session.
        
        Args:
            session_id: session ID
            updated_orders: list of updated orders
            user_id: user ID (for verification)
            
        Returns:
            Dict: update result
        """
        session_data = self.liff_sessions.get(session_id)
        
        if not session_data:
            return {'success': False, 'error': '會話不存在或已過期'}
        
        # Verify the user
        if session_data['user_id'] != user_id:
            return {'success': False, 'error': '無權限修改此會話'}
        
        # Check whether it has expired
        if datetime.now() > session_data['expires_at']:
            del self.liff_sessions[session_id]
            return {'success': False, 'error': '會話已過期'}
        
        try:
            # Validate the order data
            validated_orders = self._validate_orders(updated_orders)
            
            if not validated_orders['is_valid']:
                return {'success': False, 'error': validated_orders['error']}
            
            # Update the session data
            session_data['orders'] = validated_orders['orders']
            session_data['total_orders'] = len(validated_orders['orders'])
            session_data['updated_at'] = datetime.now()
            
            # If a Google Sheets client is available, write to the spreadsheet
            if self.google_sheets_client:
                try:
                    result = self.google_sheets_client.write_orders_batch(validated_orders['orders'])
                    logger.info(f"Orders written to Google Sheets: {result}")
                except Exception as e:
                    logger.error(f"Failed to write to Google Sheets: {e}")
                    # Does not affect the main flow; just log the error
            
            # Clear the session (editing is done)
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
        Validate a list of orders.
        
        Args:
            orders: list of orders
            
        Returns:
            Dict: validation result
        """
        if not isinstance(orders, list):
            return {'is_valid': False, 'error': '訂單資料格式錯誤'}
        
        if len(orders) == 0:
            return {'is_valid': False, 'error': '至少需要一筆訂單'}
        
        if len(orders) > 5:
            return {'is_valid': False, 'error': '訂單數量超過限制（最多5筆）'}
        
        validated_orders = []
        
        for i, order in enumerate(orders):
            # Validate required fields
            if not order.get('receiver_name'):
                return {'is_valid': False, 'error': f'訂單 {i+1} 缺少收件人姓名'}
            
            if not order.get('receiver_phone'):
                return {'is_valid': False, 'error': f'訂單 {i+1} 缺少收件人電話'}
            
            if not order.get('shipping_address'):
                return {'is_valid': False, 'error': f'訂單 {i+1} 缺少收件地址'}
            
            # Validate the items
            items = order.get('items', [])
            if not items or len(items) == 0:
                return {'is_valid': False, 'error': f'訂單 {i+1} 至少需要一個商品項目'}
            
            # Clean up and validate the items
            validated_items = []
            for item in items:
                if not item.get('name') or not item.get('name').strip():
                    continue  # Skip blank items
                
                validated_item = {
                    'name': item['name'].strip(),
                    'quantity': max(1, int(item.get('quantity', 1)))
                }
                validated_items.append(validated_item)
            
            if not validated_items:
                return {'is_valid': False, 'error': f'訂單 {i+1} 沒有有效的商品項目'}
            
            # Validate and normalize the date
            shipping_date = order.get('shipping_date', '').strip()
            if shipping_date:
                # Validate MM-DD format
                try:
                    parts = shipping_date.split('-')
                    if len(parts) != 2:
                        return {'is_valid': False, 'error': f'訂單 {i+1} 日期格式錯誤，請使用 MM-DD 格式'}
                    
                    month, day = int(parts[0]), int(parts[1])
                    if month < 1 or month > 12 or day < 1 or day > 31:
                        return {'is_valid': False, 'error': f'訂單 {i+1} 日期數值無效'}
                    
                    # Normalize the format
                    shipping_date = f"{month:02d}-{day:02d}"
                except:
                    return {'is_valid': False, 'error': f'訂單 {i+1} 日期格式錯誤'}
            
            # Build the validated order
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
        """Remove expired sessions."""
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
        Get the LIFF app URL.
        The session ID is carried in the OAuth2 state parameter so redirectUri stays clean.
        
        Args:
            session_id: session ID (goes into the state parameter)
            liff_id: LIFF app ID
            base_url: base URL (from the request or an environment variable)
            
        Returns:
            str: LIFF URL
        """
        if liff_id:
            # Use a clean redirectUri (no session parameter)
            if base_url:
                redirect_uri = f"{base_url}/liff/edit"
            else:
                # Fallback: use a relative path
                redirect_uri = "/liff/edit"
            
            # The frontend carries the session ID via the state parameter; only the base URL is provided here
            return f"https://liff.line.me/{liff_id}?liffRedirectUri={redirect_uri}&sessionId={session_id}"
        else:
            # Without a LIFF ID, return the web version URL (keeps the original behavior)
            return f"/liff/edit?session={session_id}"

# Flask route setup
def setup_liff_routes(app: Flask, liff_handler: LIFFHandler):
    """Register the LIFF-related routes."""
    
    @app.route('/liff/edit')
    def liff_edit_page():
        """LIFF edit page."""
        session_id = request.args.get('session')
        if not session_id:
            return "缺少會話 ID", 400
        
        # Get the LIFF ID from the environment or parameters
        import os
        liff_id = os.getenv('LIFF_ID', '')
        return render_template('liff_order_edit.html', session_id=session_id, LIFF_ID=liff_id)
    
    @app.route('/liff/simple')
    def liff_simple_page():
        """Simplified edit page - no LIFF login required."""
        session_id = request.args.get('session')
        if not session_id:
            return "缺少會話 ID", 400
        
        return render_template('liff_simple.html', session_id=session_id)
    
    @app.route('/api/liff/orders/<session_id>', methods=['GET'])
    def get_liff_orders(session_id):
        """Get the orders in a LIFF session."""
        result = liff_handler.get_liff_session(session_id)
        return jsonify(result)
    
    @app.route('/api/liff/orders/<session_id>', methods=['PUT'])
    def update_liff_orders(session_id):
        """Update the orders in a LIFF session."""
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
        """Remove expired sessions (can be called periodically)."""
        liff_handler.cleanup_expired_sessions()
        return jsonify({'success': True, 'message': '清理完成'})