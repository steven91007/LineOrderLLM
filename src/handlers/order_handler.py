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
import logging
from typing import Dict, Any, List
import uuid
from datetime import datetime
from ..utils.openai_client import OpenAIClient
from ..utils.dspy_client import DSPyOrderClient
from ..utils.google_sheets_client import GoogleSheetsClient
from ..utils.order_summary import OrderSummaryGenerator
from .liff_handler import LIFFHandler

logger = logging.getLogger(__name__)


class OrderHandler:
    def __init__(self, configuration, authorized_users, client_type='dspy', openai_api_key=None, openai_model=None, dspy_api_key=None, dspy_model=None, dspy_max_retries=3, google_sheet_id=None, google_credentials_path=None, liff_id=None, base_url=None):
        self.configuration = configuration
        self.authorized_users = authorized_users
        self.order_sessions = {}  # Per-user order processing state
        self.client_type = client_type
        self.liff_id = liff_id or '2007889032-OolKDrp3'  # LIFF app ID
        self.base_url = base_url  # Server base URL
        
        # Initialize the order parsing client
        if client_type == 'dspy' and openai_api_key:
            self.order_client = DSPyOrderClient(openai_api_key)
        elif openai_api_key:
            self.order_client = OpenAIClient(openai_api_key, openai_model)
        else:
            self.order_client = None
        
        # Google Sheets client (with automatic grouping by date enabled)
        self.sheets_client = GoogleSheetsClient(
            google_credentials_path, 
            google_sheet_id, 
            auto_organize_by_date=True
        ) if google_sheet_id and google_credentials_path else None
        
        # Initialize Google Sheets (create the header row)
        if self.sheets_client:
            self.sheets_client.create_sheet_if_not_exists()
        
        # Initialize the LIFF handler
        self.liff_handler = LIFFHandler(
            order_handler=self,
            google_sheets_client=self.sheets_client
        )
        
        # Initialize the order summary generator
        self.summary_generator = OrderSummaryGenerator()
    
    def is_authorized(self, user_id: str) -> bool:
        """Check whether the user is allowed to use the order features."""
        return user_id in self.authorized_users or '*' in self.authorized_users
    
    def handle_text_message(self, event: MessageEvent) -> None:
        """Handle a text message."""
        user_id = event.source.user_id
        text = event.message.text
        
        # Check for an order keyword
        if text.strip() in ['#訂單', '#order', '訂單處理']:
            if not self.is_authorized(user_id):
                self._reply_text(event, "抱歉，您沒有權限使用此功能。")
                return
            
            # Show the order menu
            self._show_order_menu(event)
        elif text.strip().startswith('#匯總') or text.strip().startswith('#summary'):
            # Handle the summary command
            if not self.is_authorized(user_id):
                self._reply_text(event, "抱歉，您沒有權限使用此功能。")
                return
            
            self._handle_summary_request(event, text.strip())
        elif user_id in self.order_sessions and self.order_sessions[user_id].get('status') == 'waiting_order_text':
            # The user is entering order text
            self._process_order_text(event)
    
    def handle_postback(self, event: PostbackEvent) -> None:
        """Handle button (postback) responses."""
        user_id = event.source.user_id
        data = json.loads(event.postback.data)
        action = data.get('action')
        
        if action == 'start_order':
            # Start the order flow
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
            # Cancel order processing
            if user_id in self.order_sessions:
                del self.order_sessions[user_id]
            self._reply_text(event, "已取消訂單處理。")
        elif action == 'show_orders_confirmation':
            # Show the order confirmation view
            self._show_orders_confirmation_from_postback(event)
        elif action == 'confirm_all_orders_batch':
            # Batch-confirm all orders (new version)
            self._confirm_all_orders_batch(event)
        elif action == 'edit_order_liff':
            # Edit a specific order via LIFF
            order_index = data.get('order_index', 1)
            self._edit_order_with_liff(event, order_index)
        elif action == 'open_liff_editor':
            # Open the LIFF editor (edit all orders)
            self._open_liff_editor(event)
        elif action == 'retry_single_order':
            # Suggest entering one order at a time
            self._reply_text_with_retry_option(event, 
                "💡 建議您將訂單分開，逐筆輸入以確保解析準確性。\n\n"
                "請重新輸入單一訂單內容："
            )
    
    def _show_order_menu(self, event: MessageEvent) -> None:
        """Show the order menu."""
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
        """Process the order text."""
        user_id = event.source.user_id
        order_text = event.message.text
        
        # Store the raw order text
        self.order_sessions[user_id]['data']['raw_text'] = order_text
        self.order_sessions[user_id]['status'] = 'parsing'
        
        if self.order_client:
            # Use the order parsing client (OpenAI or DSPy)
            result = self.order_client.parse_order(order_text)
            
            if result['success']:
                parsed_data = result['data']
                validation = self.order_client.validate_parsed_order(parsed_data)
                
                if validation['is_valid']:
                    # Store the parse result
                    self.order_sessions[user_id]['data']['parsed'] = parsed_data
                    
                    # Always show the confirmation view (Flex Message carousel)
                    self.order_sessions[user_id]['status'] = 'confirming'
                    self._show_orders_confirmation(event, parsed_data)
                else:
                    # Show the validation error
                    self._handle_validation_error(event, validation)
            else:
                # Handle a parse failure
                error_message = result.get('error', '未知錯誤')
                suggestion = result.get('suggestion', '')
                
                if suggestion == 'single_order':
                    self._show_parsing_failure_with_suggestion(event, error_message)
                else:
                    self._reply_text(event, f"解析訂單時發生錯誤：{error_message}\n\n請稍後再試或聯絡管理員。")
        else:
            # No order parsing client configured
            client_name = self.client_type.upper() if self.client_type else 'AI'
            self._reply_text(event, 
                f"已收到您的訂單資訊：\n\n{order_text}\n\n"
                f"（目前尚未啟用 {client_name} 自動解析功能）"
            )
        
        # Clear the session unless it is in the confirming state
        if (user_id in self.order_sessions and 
            self.order_sessions[user_id]['status'] not in ['confirming']):
            del self.order_sessions[user_id]
    
    def _show_orders_confirmation(self, event: MessageEvent, parsed_data: Dict[str, Any]) -> None:
        """Show the order confirmation view (Flex Message carousel)."""
        orders = parsed_data.get('orders', [])
        total_orders = len(orders)
        user_id = event.source.user_id
        
        if total_orders == 0:
            self._reply_text(event, "沒有找到有效的訂單資料。")
            return
        
        # Build the Flex Message carousel
        flex_bubbles = []
        for i, order in enumerate(orders, 1):
            bubble = self._create_order_flex_bubble(order, i, total_orders)
            flex_bubbles.append(bubble)
        
        # Add the last page: confirm all orders
        confirm_all_bubble = self._create_confirm_all_bubble(total_orders, user_id)
        flex_bubbles.append(confirm_all_bubble)
        
        # Assemble the Flex carousel
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
        """Build the Flex bubble for a single order."""
        # Format the item list
        items_text = ""
        for item in order.get('items', []):
            items_text += f"• {item['name']} x{item['quantity']}\n"
        
        # Optional sender info (shown on separate lines)
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
                        "text": f"{sender_info}收件人: {order.get('receiver_name', '')}\n收件人電話: {order.get('receiver_phone', '')}\n\n商品:\n{items_text.strip()}\n\n地址: {order.get('shipping_address', '')}",
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
                        "style": "secondary",
                        "height": "sm",
                        "color": "#2563EB",
                        "action": {
                            "type": "postback",
                            "label": "✏️ 編輯此訂單",
                            "data": json.dumps({
                                "action": "edit_order_liff",
                                "order_index": order_index
                            })
                        }
                    }
                ]
            }
        }
        
        # If there is a shipping date, add it to the content
        if order.get('shipping_date'):
            bubble["body"]["contents"][0]["text"] = bubble["body"]["contents"][0]["text"].replace(
                f"\n\n地址: {order.get('shipping_address', '')}",
                f"\n\n發貨日期: {order['shipping_date']}\n地址: {order.get('shipping_address', '')}"
            )
        
        return bubble
    
    def _create_confirm_all_bubble(self, total_orders: int, user_id: str = None) -> Dict[str, Any]:
        """Build the "confirm all orders" Flex bubble."""
        
        # Base buttons
        buttons = [
            {
                "type": "button",
                "style": "primary",
                "height": "sm",
                "color": "#1DB446",
                "action": {
                    "type": "postback",
                    "label": "✅ 確認全部訂單",
                    "data": json.dumps({
                        "action": "confirm_all_orders_batch"
                    })
                }
            }
        ]
        
        # If a LIFF ID is set, add the LIFF edit button
        if self.liff_id and user_id:
            buttons.insert(0, {
                "type": "button",
                "style": "secondary",
                "height": "sm",
                "color": "#2563EB",
                "action": {
                    "type": "postback",
                    "label": "🌐 網頁編輯",
                    "data": json.dumps({
                        "action": "open_liff_editor",
                        "user_id": user_id
                    })
                }
            })
        
        # Add the "re-check" button
        buttons.append({
            "type": "button",
            "style": "secondary",
            "height": "sm",
            "action": {
                "type": "postback",
                "label": "🔄 重新檢查",
                "data": json.dumps({
                    "action": "start_order"
                })
            }
        })
        
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
                        "text": f"📋 共 {total_orders} 份訂單\n\n📱 快速確認：點擊「確認全部訂單」直接提交\n🌐 詳細編輯：點擊「網頁編輯」開啟編輯器\n\n⚠️ 提交後將寫入系統，請仔細核對。",
                        "wrap": True,
                        "size": "sm"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": buttons
            }
        }
        
        return bubble
    
    def _show_orders_confirmation_from_postback(self, event: PostbackEvent) -> None:
        """Show the order confirmation view from a postback."""
        user_id = event.source.user_id
        
        if (user_id not in self.order_sessions or 
            'parsed' not in self.order_sessions[user_id].get('data', {})):
            self._reply_text(event, "找不到訂單資料，請重新開始。")
            return
        
        parsed_data = self.order_sessions[user_id]['data']['parsed']
        self._show_orders_confirmation(event, parsed_data)
    
    def _edit_order_with_liff(self, event: PostbackEvent, order_index: int) -> None:
        """Edit a specific order via LIFF."""
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
        
        if not self.liff_id:
            # LIFF is not configured; show a friendly error message
            self._reply_text(event, 
                "🌐 網頁編輯功能需要管理員設定 LIFF 應用程式。\n\n"
                f"目前訂單 {order_index} 的資訊：\n"
                f"收件人：{orders[order_index-1].get('receiver_name', '')}\n"
                f"電話：{orders[order_index-1].get('receiver_phone', '')}\n"
                f"地址：{orders[order_index-1].get('shipping_address', '')}\n\n"
                "請聯絡管理員啟用網頁編輯功能，或使用「確認全部訂單」直接提交。"
            )
            return
        
        try:
            # Create a LIFF session (with all orders)
            session_id = self.liff_handler.create_liff_session(user_id, parsed_data)
            
            # Build the LIFF URL
            liff_url = self.liff_handler.get_liff_url(f"{session_id}&focus={order_index}", self.liff_id, self.base_url)
            
            # Send the LIFF message
            with ApiClient(self.configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                
                current_order = orders[order_index - 1]
                flex_message_content = {
                    "type": "bubble",
                    "header": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"✏️ 編輯訂單 {order_index}",
                                "weight": "bold",
                                "size": "lg",
                                "color": "#2563EB"
                            }
                        ]
                    },
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"📝 即將編輯：\n收件人：{current_order.get('receiver_name', '')}\n地址：{current_order.get('shipping_address', '')}\n\n🌐 將開啟網頁編輯器，您可以：\n• 編輯此訂單的所有資訊\n• 同時修改其他訂單\n• 一次儲存所有變更\n\n點擊下方按鈕開始：",
                                "wrap": True,
                                "size": "sm"
                            }
                        ]
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#2563EB",
                                "action": {
                                    "type": "uri",
                                    "label": "🌐 開啟編輯器",
                                    "uri": liff_url
                                }
                            }
                        ]
                    }
                }
                
                flex_message = FlexMessage(
                    alt_text=f"編輯訂單 {order_index}",
                    contents=FlexContainer.from_dict(flex_message_content)
                )
                
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[flex_message]
                    )
                )
                
                logger.info(f"LIFF editor opened for user {user_id}, focusing on order {order_index}")
                
        except Exception as e:
            logger.error(f"Error opening LIFF editor for order {order_index}: {e}")
            self._reply_text(event, f"❌ 開啟編輯器失敗，請稍後重試。\n\n錯誤：{str(e)}")
    
    
    
    
    def _open_liff_editor(self, event: PostbackEvent) -> None:
        """Open the LIFF editor."""
        user_id = event.source.user_id
        
        if (user_id not in self.order_sessions or 
            'parsed' not in self.order_sessions[user_id].get('data', {})):
            self._reply_text(event, "找不到訂單資料，請重新開始。")
            return
        
        if not self.liff_id:
            self._reply_text(event, "LIFF 編輯器尚未設定，請使用按鈕編輯功能。")
            return
        
        try:
            # Create a LIFF session
            parsed_data = self.order_sessions[user_id]['data']['parsed']
            session_id = self.liff_handler.create_liff_session(user_id, parsed_data)
            
            # Build the LIFF URL
            liff_url = self.liff_handler.get_liff_url(session_id, self.liff_id, self.base_url)
            
            # Send the LIFF message
            with ApiClient(self.configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                
                # Open LIFF with a URI action
                flex_message_content = {
                    "type": "bubble",
                    "header": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🌐 訂單網頁編輯器",
                                "weight": "bold",
                                "size": "lg",
                                "color": "#2563EB"
                            }
                        ]
                    },
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"📝 將開啟網頁編輯器\n📊 共 {parsed_data.get('total_orders', 0)} 筆訂單\n\n✨ 功能特色：\n• 表格式編輯介面\n• 即時內容驗證\n• 批量修改支援\n• 一鍵儲存更新\n\n點擊下方按鈕開始編輯：",
                                "wrap": True,
                                "size": "sm"
                            }
                        ]
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#2563EB",
                                "action": {
                                    "type": "uri",
                                    "label": "🌐 開啟編輯器",
                                    "uri": liff_url
                                }
                            }
                        ]
                    }
                }
                
                flex_message = FlexMessage(
                    alt_text="訂單網頁編輯器",
                    contents=FlexContainer.from_dict(flex_message_content)
                )
                
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[flex_message]
                    )
                )
                
                logger.info(f"LIFF editor opened for user {user_id}, session {session_id}")
                
        except Exception as e:
            logger.error(f"Error opening LIFF editor: {e}")
            self._reply_text(event, "❌ 開啟編輯器失敗，請稍後重試或使用按鈕編輯功能。")
    
    def _format_single_order_summary(self, order_data: Dict[str, Any]) -> str:
        """Format a single-order summary."""
        summary = "📦 訂單資訊：\n\n"
        
        # Sender info (optional)
        if order_data.get('sender_name') or order_data.get('sender_phone'):
            if order_data.get('sender_name'):
                summary += f"👤 寄件人：{order_data['sender_name']}\n"
            if order_data.get('sender_phone'):
                summary += f"📞 寄件人電話：{order_data['sender_phone']}\n"
            summary += "\n"
        
        # Receiver info
        summary += f"👥 收件人：{order_data.get('receiver_name', '')}\n"
        summary += f"📞 收件人電話：{order_data.get('receiver_phone', '')}\n\n"
        
        # Item details
        if order_data.get('items'):
            summary += "📋 商品明細：\n"
            for item in order_data['items']:
                summary += f"  • {item['name']} x {item['quantity']}\n"
            summary += "\n"
        
        # Shipping date
        if order_data.get('shipping_date'):
            summary += f"📅 預計發貨日：{order_data['shipping_date']}\n"
        
        # Shipping address
        summary += f"📦 收件地址：{order_data.get('shipping_address', '')}\n\n"
        summary += "請確認以上資訊是否正確？"
        
        return summary
    
    def _show_parsing_failure_with_suggestion(self, event: MessageEvent) -> None:
        """Show a parse failure and suggest entering one order at a time."""
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
        """Handle a validation error."""
        error_type = validation.get('error_type', 'validation_error')
        error_message = validation.get('error_message', '驗證失敗')
        
        if error_type == 'parsing_error':
            self._show_parsing_failure_with_suggestion(event)
        else:
            self._reply_text(event, f"❌ {error_message}\n\n請重新輸入訂單資訊。")
    
    def _reply_text(self, event, text: str) -> None:
        """Reply with a text message."""
        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=text)]
                )
            )
    
    def _reply_text_with_retry_option(self, event: PostbackEvent, text: str) -> None:
        """Reply with text and put the session back into the retry state."""
        user_id = event.source.user_id
        
        # Reset the state to waiting for input
        if user_id in self.order_sessions:
            self.order_sessions[user_id]['status'] = 'waiting_order_text'
        
        self._reply_text(event, text)
    
    
    
    
    def _save_order_to_sheets(self, event: PostbackEvent, order_data: Dict[str, Any], order_index: int = 1) -> None:
        """Save the order to Google Sheets and reply with the result."""
        # Generate the order ID
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
            # Google Sheets is not configured
            success_message = (
                f"📦 訂單資訊已確認\n\n"
                f"🆔 訂單編號：{order_id}\n"
                f"👥 收件人：{order_data.get('receiver_name')}\n\n"
                "（目前未啟用 Google Sheets 儲存功能）"
            )
            self._reply_text(event, success_message)
    
    def _save_order_to_sheets_silent(self, order_data: Dict[str, Any], order_index: int = 1) -> bool:
        """Save the order to Google Sheets silently (no reply)."""
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        order_data['order_id'] = order_id
        
        if self.sheets_client:
            result = self.sheets_client.append_order(order_data)
            return result['success']
        
        return True  # Treat as success when Google Sheets is not configured
    
    def _confirm_all_orders_batch(self, event: PostbackEvent) -> None:
        """Batch-confirm all orders (new version)."""
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
        
        # Generate IDs for all orders
        for i, order_data in enumerate(orders, 1):
            order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
            order_data['order_id'] = order_id
        
        if self.sheets_client:
            # Use the batch write
            result = self.sheets_client.append_multiple_orders(orders)
            success_count = result.get('total_processed', 0)
            order_ids = result.get('order_ids', [])
            
            if not result['success']:
                failed_orders = [f"訂單 {i}" for i in range(1, len(orders) + 1)]
            else:
                failed_orders = []
        else:
            # Google Sheets is not configured; treat everything as successful
            success_count = len(orders)
            order_ids = [order['order_id'] for order in orders]
            failed_orders = []
            result = {'success': True}  # Initialize the result variable
        
        total_orders = len(orders)
        
        if success_count == total_orders:
            # All succeeded
            success_message = (
                f"🎉 批量提交成功！\n\n"
                f"✅ 已成功建立 {total_orders} 份訂單\n\n"
            )
            
            # Show the per-sheet grouping info
            if isinstance(result, dict) and result.get('sheet_results'):
                sheet_results = result.get('sheet_results', {})
                sheets_used = result.get('sheets_used', [])
                
                success_message += f"📊 已自動分組到 {len(sheets_used)} 個工作表：\n\n"
                
                for sheet_name in sheets_used:
                    sheet_info = sheet_results.get(sheet_name, {})
                    order_count = sheet_info.get('order_count', 0)
                    
                    # Parse the date and weekday out of the sheet name
                    if '_星期' in sheet_name:
                        date_part, weekday_part = sheet_name.split('_', 1)
                        try:
                            date_obj = datetime.strptime(date_part, '%Y%m%d')
                            formatted_date = date_obj.strftime('%Y-%m-%d')
                            success_message += f"📅 {formatted_date}({weekday_part}): {order_count} 份訂單\n"
                        except ValueError:
                            success_message += f"📋 {sheet_name}: {order_count} 份訂單\n"
                    else:
                        success_message += f"📋 {sheet_name}: {order_count} 份訂單\n"
                
                success_message += f"\n📋 訂單編號：\n"
                for i, (order_id, order) in enumerate(zip(order_ids, orders), 1):
                    receiver_name = order.get('receiver_name', '')
                    success_message += f"• {order_id} ({receiver_name})\n"
            else:
                success_message += f"📋 訂單編號：\n"
                for i, (order_id, order) in enumerate(zip(order_ids, orders), 1):
                    receiver_name = order.get('receiver_name', '')
                    success_message += f"• {order_id} ({receiver_name})\n"
            
            success_message += f"\n🗂️ 所有訂單已自動按出貨日期分組記錄到 Google Sheets。"
            
            self._reply_text(event, success_message)
        else:
            # Partial failure
            error_message = (
                f"⚠️ 批量提交結果\n\n"
                f"✅ 成功：{success_count}/{total_orders} 份訂單\n"
                f"❌ 失敗：{', '.join(failed_orders)}\n\n"
                f"請檢查失敗的訂單並重新提交。"
            )
            
            self._reply_text(event, error_message)
        
        # Clear the session state
        if user_id in self.order_sessions:
            del self.order_sessions[user_id]
    
    def _handle_summary_request(self, event: MessageEvent, command_text: str) -> None:
        """Handle a summary request.
        
        Args:
            event: LINE message event
            command_text: the full command text (e.g. "#匯總 8/27")
        """
        try:
            # Parse the date argument
            target_date = self._parse_summary_command(command_text)
            
            if not target_date:
                self._reply_text(event, 
                    "❌ 日期格式錯誤\n\n"
                    "正確格式範例：\n"
                    "• #匯總 8/27\n"
                    "• #匯總 08-27\n"
                    "• #匯總 2024-08-27\n"
                    "• #匯總 星期二\n\n"
                    "請重新輸入正確的日期格式。"
                )
                return
            
            # Check that a Google Sheets client is available
            if not self.sheets_client:
                self._reply_text(event, 
                    "❌ Google Sheets 功能未啟用\n\n"
                    "匯總功能需要存取 Google Sheets 資料，\n"
                    "請聯絡管理員設定相關權限。"
                )
                return
            
            # Query orders for the given date (no "processing" message first, since a reply_token can only be used once)
            query_result = self.sheets_client.get_orders_by_date(target_date)
            
            if not query_result['success']:
                self._reply_text(event, 
                    f"❌ 查詢失敗\n\n"
                    f"錯誤訊息：{query_result.get('error', '未知錯誤')}\n\n"
                    "請稍後再試或聯絡管理員。"
                )
                return
            
            orders = query_result.get('orders', [])
            formatted_date = query_result.get('formatted_date', target_date)
            
            if not orders:
                self._reply_text(event, 
                    f"📋 {formatted_date} 匯總結果\n\n"
                    f"❌ 該日期沒有找到任何訂單資料。\n\n"
                    "請確認：\n"
                    "• 日期格式是否正確\n"
                    "• 該日期是否有訂單\n"
                    "• 訂單是否已上傳到 Google Sheets"
                )
                return
            
            # Generate the summary report
            summary_report = self.summary_generator.generate_summary_report(orders, formatted_date)
            
            if not summary_report['success']:
                self._reply_text(event, 
                    f"❌ 生成匯總報告失敗\n\n"
                    f"錯誤訊息：{summary_report.get('error', '未知錯誤')}\n\n"
                    "請稍後再試或聯絡管理員。"
                )
                return
            
            # Send the summary report (with a status prefix)
            formatted_report = summary_report.get('formatted_report', '')
            full_message = f"🔍 已完成 {target_date} 的查詢\n\n{formatted_report}"
            
            # If the report is too long, send the bare report instead (a reply_token can only be used once)
            if len(full_message) > 2000:
                # Too long: send only the report body
                self._reply_text(event, formatted_report)
            else:
                self._reply_text(event, full_message)
            
            logger.info(f"Successfully generated summary for {target_date}: {summary_report['total_orders']} orders, {summary_report['total_items']} items")
            
        except Exception as e:
            logger.error(f"Error handling summary request: {e}")
            self._reply_text(event, 
                f"❌ 處理匯總請求時發生錯誤\n\n"
                f"錯誤訊息：{str(e)}\n\n"
                "請稍後再試或聯絡管理員。"
            )
    
    def _parse_summary_command(self, command_text: str) -> str:
        """Parse the date argument from a summary command.
        
        Args:
            command_text: the command text (e.g. "#匯總 8/27")
            
        Returns:
            str: the parsed date string, or None on failure
        """
        import re
        
        # Strip the command prefix
        date_part = re.sub(r'^#(匯總|summary)\s*', '', command_text, flags=re.IGNORECASE).strip()
        
        if not date_part:
            # No date given; use today
            from datetime import datetime
            return datetime.now().strftime('%m-%d')
        
        # Basic date format check
        date_patterns = [
            r'^\d{1,2}/\d{1,2}$',        # 8/27
            r'^\d{1,2}-\d{1,2}$',        # 8-27
            r'^\d{4}-\d{1,2}-\d{1,2}$',  # 2024-08-27
            r'^星期[一二三四五六日天]$',      # 星期二
            r'^週[一二三四五六日天]$',       # 週二
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, date_part):
                return date_part
        
        return None
    
    def _send_long_message_as_push(self, user_id: str, long_text: str) -> None:
        """Send a long message (split into several push messages).
        
        Note: this method has to use push messages instead of reply,
        because a reply_token can only be used once.
        
        Args:
            user_id: user ID
            long_text: the long text
        """
        # Kept as a stub for now, since it needs push message permission
        # The current workaround is to truncate the message to fit a single reply
        pass