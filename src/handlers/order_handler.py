from linebot.v3.messaging import (
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    TemplateMessage,
    ButtonsTemplate,
    MessageAction,
    PostbackAction,
    FlexMessage,
    FlexContainer
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, PostbackEvent
import json
from typing import Dict, Any, List
import uuid
from datetime import datetime
from ..utils.openai_client import OpenAIClient
from ..utils.dspy_client import DSPyOrderClient
from ..utils.google_sheets_client import GoogleSheetsClient


class OrderHandler:
    def __init__(self, configuration, authorized_users, client_type='dspy', openai_api_key=None, openai_model=None, dspy_api_key=None, dspy_model=None, dspy_max_retries=3, google_sheet_id=None, google_credentials_path=None):
        self.configuration = configuration
        self.authorized_users = authorized_users
        self.order_sessions = {}  # 存儲用戶的訂單處理狀態
        self.client_type = client_type
        
        # 初始化訂單解析客戶端
        if client_type == 'dspy' and openai_api_key:
            self.order_client = DSPyOrderClient(openai_api_key)
        elif openai_api_key:
            self.order_client = OpenAIClient(openai_api_key, openai_model)
        else:
            self.order_client = None
        
        # Google Sheets 客戶端
        self.sheets_client = GoogleSheetsClient(google_credentials_path, google_sheet_id) if google_sheet_id and google_credentials_path else None
        
        # 初始化 Google Sheets（建立標題）
        if self.sheets_client:
            self.sheets_client.create_sheet_if_not_exists()
    
    def is_authorized(self, user_id: str) -> bool:
        """檢查用戶是否有權限使用訂單功能"""
        return user_id in self.authorized_users or '*' in self.authorized_users
    
    def handle_text_message(self, event: MessageEvent) -> None:
        """處理文字訊息"""
        user_id = event.source.user_id
        text = event.message.text
        
        # 檢查是否為訂單關鍵字
        if text.strip() in ['#訂單', '#order', '訂單處理']:
            if not self.is_authorized(user_id):
                self._reply_text(event, "抱歉，您沒有權限使用此功能。")
                return
            
            # 顯示訂單處理選單
            self._show_order_menu(event)
        elif user_id in self.order_sessions and self.order_sessions[user_id].get('status') == 'waiting_order_text':
            # 用戶正在輸入訂單內容
            self._process_order_text(event)
    
    def handle_postback(self, event: PostbackEvent) -> None:
        """處理按鈕回應"""
        user_id = event.source.user_id
        data = json.loads(event.postback.data)
        action = data.get('action')
        
        if action == 'start_order':
            # 開始訂單處理流程
            self.order_sessions[user_id] = {
                'status': 'waiting_order_text',
                'data': {}
            }
            self._reply_text(event, 
                "請輸入您的訂單內容。系統支援：\n\n"
                "📋 單一訂單：包含收件人、電話、商品、地址\n"
                "📋 多筆訂單：最多可處理 5 份訂單\n\n"
                "💡 提醒：寄件人資訊為選填，系統會自動解析您的訊息。"
            )
        elif action == 'cancel_order':
            # 取消訂單處理
            if user_id in self.order_sessions:
                del self.order_sessions[user_id]
            self._reply_text(event, "已取消訂單處理。")
        elif action == 'confirm_order':
            # 確認訂單
            order_index = data.get('order_index', 1)
            self._confirm_order(event, order_index)
        elif action == 'show_orders_confirmation':
            # 顯示訂單確認介面
            self._show_orders_confirmation_from_postback(event)
        elif action == 'confirm_all_orders_batch':
            # 批量確認所有訂單（新版）
            self._confirm_all_orders_batch(event)
        elif action == 'retry_single_order':
            # 建議單筆輸入
            self._reply_text_with_retry_option(event, 
                "💡 建議您將訂單分開，逐筆輸入以確保解析準確性。\n\n"
                "請重新輸入單一訂單內容："
            )
    
    def _show_order_menu(self, event: MessageEvent) -> None:
        """顯示訂單處理選單"""
        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            buttons_template = ButtonsTemplate(
                title='訂單處理系統',
                text='請選擇您要進行的操作：',
                actions=[
                    PostbackAction(
                        label='開始建立訂單',
                        data=json.dumps({'action': 'start_order'})
                    ),
                    PostbackAction(
                        label='取消',
                        data=json.dumps({'action': 'cancel_order'})
                    )
                ]
            )
            
            template_message = TemplateMessage(
                alt_text='訂單處理選單',
                template=buttons_template
            )
            
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )
    
    def _process_order_text(self, event: MessageEvent) -> None:
        """處理訂單文字內容"""
        user_id = event.source.user_id
        order_text = event.message.text
        
        # 儲存原始訂單文字
        self.order_sessions[user_id]['data']['raw_text'] = order_text
        self.order_sessions[user_id]['status'] = 'parsing'
        
        if self.order_client:
            # 使用訂單解析客戶端（OpenAI 或 DSPy）
            result = self.order_client.parse_order(order_text)
            
            if result['success']:
                parsed_data = result['data']
                validation = self.order_client.validate_parsed_order(parsed_data)
                
                if validation['is_valid']:
                    # 儲存解析結果
                    self.order_sessions[user_id]['data']['parsed'] = parsed_data
                    
                    # 統一顯示訂單確認介面（使用 Flex Message 輪播）
                    self.order_sessions[user_id]['status'] = 'confirming'
                    self._show_orders_confirmation(event, parsed_data)
                else:
                    # 顯示驗證錯誤
                    self._handle_validation_error(event, validation)
            else:
                # 解析失敗處理
                error_message = result.get('error', '未知錯誤')
                suggestion = result.get('suggestion', '')
                
                if suggestion == 'single_order':
                    self._show_parsing_failure_with_suggestion(event, error_message)
                else:
                    self._reply_text(event, f"解析訂單時發生錯誤：{error_message}\n\n請稍後再試或聯絡管理員。")
        else:
            # 沒有設定訂單解析客戶端
            client_name = self.client_type.upper() if self.client_type else 'AI'
            self._reply_text(event, 
                f"已收到您的訂單資訊：\n\n{order_text}\n\n"
                f"（目前尚未啟用 {client_name} 自動解析功能）"
            )
        
        # 如果不是在確認狀態，清除會話
        if (user_id in self.order_sessions and 
            self.order_sessions[user_id]['status'] not in ['confirming']):
            del self.order_sessions[user_id]
    
    def _show_orders_confirmation(self, event: MessageEvent, parsed_data: Dict[str, Any]) -> None:
        """顯示訂單確認介面（使用 Flex Message 輪播）"""
        orders = parsed_data.get('orders', [])
        total_orders = len(orders)
        
        if total_orders == 0:
            self._reply_text(event, "沒有找到有效的訂單資料。")
            return
        
        # 創建 Flex Message 輪播
        flex_bubbles = []
        for i, order in enumerate(orders, 1):
            bubble = self._create_order_flex_bubble(order, i, total_orders)
            flex_bubbles.append(bubble)
        
        # 添加最後一頁：確認全部訂單
        confirm_all_bubble = self._create_confirm_all_bubble(total_orders)
        flex_bubbles.append(confirm_all_bubble)
        
        # 構建 Flex Carousel
        flex_carousel = {
            "type": "carousel",
            "contents": flex_bubbles
        }
        
        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            flex_message = FlexMessage(
                alt_text=f'訂單確認 ({total_orders} 份)',
                contents=FlexContainer.from_dict(flex_carousel)
            )
            
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[flex_message]
                )
            )
    
    def _create_order_flex_bubble(self, order: Dict[str, Any], order_index: int, total_orders: int) -> Dict[str, Any]:
        """創建單一訂單的 Flex Bubble"""
        # 格式化商品列表
        items_text = ""
        for item in order.get('items', []):
            items_text += f"• {item['name']} x{item['quantity']}\n"
        
        # 處理可選的寄件人資訊（分開顯示）
        sender_info = ""
        if order.get('sender_name') or order.get('sender_phone'):
            if order.get('sender_name'):
                sender_info += f"寄件人: {order['sender_name']}\n"
            if order.get('sender_phone'):
                sender_info += f"寄件人電話: {order['sender_phone']}\n"
            sender_info += "\n"
        
        bubble = {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"訂單 {order_index}/{total_orders}",
                        "weight": "bold",
                        "size": "lg",
                        "color": "#1DB446"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{sender_info}收件人: {order.get('receiver_name', 'N/A')}\n收件人電話: {order.get('receiver_phone', 'N/A')}\n\n商品:\n{items_text.strip()}\n\n地址: {order.get('shipping_address', 'N/A')}",
                        "wrap": True,
                        "size": "sm"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "確認此訂單",
                            "data": json.dumps({
                                "action": "confirm_order",
                                "order_index": order_index
                            })
                        }
                    }
                ]
            }
        }
        
        # 如果發貨日期存在，添加到內容中
        if order.get('shipping_date'):
            bubble["body"]["contents"][0]["text"] = bubble["body"]["contents"][0]["text"].replace(
                f"\n\n地址: {order.get('shipping_address', 'N/A')}",
                f"\n\n發貨日期: {order['shipping_date']}\n地址: {order.get('shipping_address', 'N/A')}"
            )
        
        return bubble
    
    def _create_confirm_all_bubble(self, total_orders: int) -> Dict[str, Any]:
        """創建確認全部訂單的 Flex Bubble"""
        bubble = {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "✅ 確認全部訂單",
                        "weight": "bold",
                        "size": "lg",
                        "color": "#1DB446"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"📋 共 {total_orders} 份訂單\n\n請確認前面所有訂單資訊無誤後，點擊下方按鈕一次性提交全部訂單到系統。\n\n⚠️ 提交後將無法修改，請仔細核對。",
                        "wrap": True,
                        "size": "sm"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "color": "#1DB446",
                        "action": {
                            "type": "postback",
                            "label": "確認全部訂單無誤",
                            "data": json.dumps({
                                "action": "confirm_all_orders_batch"
                            })
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "重新檢查",
                            "data": json.dumps({
                                "action": "start_order"
                            })
                        }
                    }
                ]
            }
        }
        
        return bubble
    
    def _show_orders_confirmation_from_postback(self, event: PostbackEvent) -> None:
        """從 postback 顯示訂單確認介面"""
        user_id = event.source.user_id
        
        if (user_id not in self.order_sessions or 
            'parsed' not in self.order_sessions[user_id].get('data', {})):
            self._reply_text(event, "找不到訂單資料，請重新開始。")
            return
        
        parsed_data = self.order_sessions[user_id]['data']['parsed']
        self._show_orders_confirmation(event, parsed_data)
    
    def _confirm_order(self, event: PostbackEvent, order_index: int) -> None:
        """統一確認訂單方法"""
        user_id = event.source.user_id
        
        if (user_id not in self.order_sessions or 
            'parsed' not in self.order_sessions[user_id].get('data', {})):
            self._reply_text(event, "找不到訂單資料，請重新開始。")
            return
        
        parsed_data = self.order_sessions[user_id]['data']['parsed']
        orders = parsed_data.get('orders', [])
        
        if order_index < 1 or order_index > len(orders):
            self._reply_text(event, "訂單索引錯誤。")
            return
        
        order_data = orders[order_index - 1]
        self._save_order_to_sheets(event, order_data, order_index)
        
        # 檢查是否還有其他訂單需要確認
        total_orders = len(orders)
        if order_index < total_orders:
            # 繼續下一份訂單
            self._reply_text(event, 
                f"✅ 訂單 {order_index} 已確認！\n\n"
                f"還有 {total_orders - order_index} 份訂單待確認。"
            )
        else:
            # 所有訂單都確認完畢
            self._reply_text(event, "🎉 所有訂單都已確認完成！")
            if user_id in self.order_sessions:
                del self.order_sessions[user_id]
    
    
    def _format_single_order_summary(self, order_data: Dict[str, Any]) -> str:
        """格式化單一訂單摘要"""
        summary = "📦 訂單資訊：\n\n"
        
        # 寄件人資訊（選填）
        if order_data.get('sender_name') or order_data.get('sender_phone'):
            if order_data.get('sender_name'):
                summary += f"👤 寄件人：{order_data['sender_name']}\n"
            if order_data.get('sender_phone'):
                summary += f"📞 寄件人電話：{order_data['sender_phone']}\n"
            summary += "\n"
        
        # 收件人資訊
        summary += f"👥 收件人：{order_data.get('receiver_name', 'N/A')}\n"
        summary += f"📞 收件人電話：{order_data.get('receiver_phone', 'N/A')}\n\n"
        
        # 商品明細
        if order_data.get('items'):
            summary += "📋 商品明細：\n"
            for item in order_data['items']:
                summary += f"  • {item['name']} x {item['quantity']}\n"
            summary += "\n"
        
        # 發貨日期
        if order_data.get('shipping_date'):
            summary += f"📅 預計發貨日：{order_data['shipping_date']}\n"
        
        # 收件地址
        summary += f"📦 收件地址：{order_data.get('shipping_address', 'N/A')}\n\n"
        summary += "請確認以上資訊是否正確？"
        
        return summary
    
    def _show_parsing_failure_with_suggestion(self, event: MessageEvent) -> None:
        """顯示解析失敗並建議單筆輸入"""
        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            buttons_template = ButtonsTemplate(
                text="❌ 多訂單解析失敗\n\n建議您將訂單分開，逐筆輸入以確保解析準確性。",
                actions=[
                    PostbackAction(
                        label='單筆輸入',
                        data=json.dumps({'action': 'retry_single_order'})
                    ),
                    PostbackAction(
                        label='重新嘗試',
                        data=json.dumps({'action': 'start_order'})
                    ),
                    PostbackAction(
                        label='取消',
                        data=json.dumps({'action': 'cancel_order'})
                    )
                ]
            )
            
            template_message = TemplateMessage(
                alt_text='解析失敗',
                template=buttons_template
            )
            
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )
    
    def _handle_validation_error(self, event: MessageEvent, validation: Dict[str, Any]) -> None:
        """處理驗證錯誤"""
        error_type = validation.get('error_type', 'validation_error')
        error_message = validation.get('error_message', '驗證失敗')
        
        if error_type == 'parsing_error':
            self._show_parsing_failure_with_suggestion(event)
        else:
            self._reply_text(event, f"❌ {error_message}\n\n請重新輸入訂單資訊。")
    
    def _reply_text(self, event, text: str) -> None:
        """回覆文字訊息"""
        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=text)]
                )
            )
    
    def _reply_text_with_retry_option(self, event: PostbackEvent, text: str) -> None:
        """回覆文字並設定重試狀態"""
        user_id = event.source.user_id
        
        # 重設狀態為等待輸入
        if user_id in self.order_sessions:
            self.order_sessions[user_id]['status'] = 'waiting_order_text'
        
        self._reply_text(event, text)
    
    
    
    
    def _save_order_to_sheets(self, event: PostbackEvent, order_data: Dict[str, Any], order_index: int = 1) -> None:
        """儲存訂單到 Google Sheets 並回覆結果"""
        # 產生訂單編號
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        order_data['order_id'] = order_id
        
        if self.sheets_client:
            result = self.sheets_client.append_order(order_data)
            
            if result['success']:
                success_message = (
                    f"✅ 訂單已成功建立！\n\n"
                    f"🆔 訂單編號：{order_id}\n"
                    f"📦 收件人：{order_data.get('receiver_name')}\n"
                    f"📦 地址：{order_data.get('shipping_address')}\n\n"
                    "訂單已記錄在 Google Sheets 中。"
                )
                self._reply_text(event, success_message)
            else:
                error_message = (
                    f"⚠️ 訂單處理失敗\n\n"
                    f"錯誤訊息：{result.get('error', '未知錯誤')}\n\n"
                    "請稍後再試或聯絡管理員。"
                )
                self._reply_text(event, error_message)
        else:
            # 沒有設定 Google Sheets
            success_message = (
                f"📦 訂單資訊已確認\n\n"
                f"🆔 訂單編號：{order_id}\n"
                f"👥 收件人：{order_data.get('receiver_name')}\n\n"
                "（目前未啟用 Google Sheets 儲存功能）"
            )
            self._reply_text(event, success_message)
    
    def _save_order_to_sheets_silent(self, order_data: Dict[str, Any], order_index: int = 1) -> bool:
        """靜默儲存訂單到 Google Sheets（不回覆訊息）"""
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        order_data['order_id'] = order_id
        
        if self.sheets_client:
            result = self.sheets_client.append_order(order_data)
            return result['success']
        
        return True  # 如果沒有設定 Google Sheets，視為成功
    
    def _confirm_all_orders_batch(self, event: PostbackEvent) -> None:
        """批量確認所有訂單（新版）"""
        user_id = event.source.user_id
        
        if (user_id not in self.order_sessions or 
            'parsed' not in self.order_sessions[user_id].get('data', {})):
            self._reply_text(event, "找不到訂單資料，請重新開始。")
            return
        
        parsed_data = self.order_sessions[user_id]['data']['parsed']
        orders = parsed_data.get('orders', [])
        
        if not orders:
            self._reply_text(event, "沒有找到有效的訂單資料。")
            return
        
        success_count = 0
        failed_orders = []
        order_ids = []
        
        # 批量處理所有訂單
        for i, order_data in enumerate(orders, 1):
            # 產生訂單編號
            order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
            order_data['order_id'] = order_id
            
            if self.sheets_client:
                result = self.sheets_client.append_order(order_data)
                if result['success']:
                    success_count += 1
                    order_ids.append(order_id)
                else:
                    failed_orders.append(f"訂單 {i}")
            else:
                # 沒有設定 Google Sheets，視為成功
                success_count += 1
                order_ids.append(order_id)
        
        total_orders = len(orders)
        
        if success_count == total_orders:
            # 全部成功
            success_message = (
                f"🎉 批量提交成功！\n\n"
                f"✅ 已成功建立 {total_orders} 份訂單\n\n"
                f"📋 訂單編號：\n"
            )
            
            for i, (order_id, order) in enumerate(zip(order_ids, orders), 1):
                receiver_name = order.get('receiver_name', 'N/A')
                success_message += f"• {order_id} ({receiver_name})\n"
            
            success_message += f"\n🗂️ 所有訂單已記錄在 Google Sheets 中。"
            
            self._reply_text(event, success_message)
        else:
            # 部分失敗
            error_message = (
                f"⚠️ 批量提交結果\n\n"
                f"✅ 成功：{success_count}/{total_orders} 份訂單\n"
                f"❌ 失敗：{', '.join(failed_orders)}\n\n"
                f"請檢查失敗的訂單並重新提交。"
            )
            
            self._reply_text(event, error_message)
        
        # 清除會話狀態
        if user_id in self.order_sessions:
            del self.order_sessions[user_id]