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
from ..utils.google_sheets_client import GoogleSheetsClient


class OrderHandler:
    def __init__(self, configuration, authorized_users, openai_api_key=None, openai_model=None, google_sheet_id=None, google_credentials_path=None):
        self.configuration = configuration
        self.authorized_users = authorized_users
        self.order_sessions = {}  # 存儲用戶的訂單處理狀態
        self.openai_client = OpenAIClient(openai_api_key, openai_model) if openai_api_key else None
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
        elif action == 'confirm_single_order':
            # 確認單一訂單
            self._confirm_single_order(event)
        elif action == 'confirm_order_at_index':
            # 確認特定索引的訂單
            order_index = data.get('order_index', 1)
            self._confirm_order_at_index(event, order_index)
        elif action == 'show_order_at_index':
            # 顯示特定索引的訂單
            order_index = data.get('order_index', 1)
            self._show_order_at_index(event, order_index)
        elif action == 'confirm_all_orders':
            # 確認所有訂單
            self._confirm_all_orders(event)
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
        
        if self.openai_client:
            # 使用 OpenAI 解析訂單
            result = self.openai_client.parse_order(order_text)
            
            if result['success']:
                parsed_data = result['data']
                validation = self.openai_client.validate_parsed_order(parsed_data)
                
                if validation['is_valid']:
                    # 儲存解析結果
                    self.order_sessions[user_id]['data']['parsed'] = parsed_data
                    
                    # 根據訂單類型顯示不同的確認介面
                    order_type = parsed_data.get('order_type', 'single')
                    if order_type == 'single':
                        self.order_sessions[user_id]['status'] = 'confirming_single'
                        self._show_single_order_confirmation(event, parsed_data)
                    elif order_type == 'multiple':
                        self.order_sessions[user_id]['status'] = 'confirming_multiple'
                        self.order_sessions[user_id]['data']['current_order_index'] = 1
                        self._show_multiple_orders_overview(event, parsed_data)
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
            # 沒有設定 OpenAI
            self._reply_text(event, 
                f"已收到您的訂單資訊：\n\n{order_text}\n\n"
                "（目前尚未啟用自動解析功能）"
            )
        
        # 如果不是在確認狀態，清除會話
        if (user_id in self.order_sessions and 
            self.order_sessions[user_id]['status'] not in ['confirming_single', 'confirming_multiple']):
            del self.order_sessions[user_id]
    
    def _show_single_order_confirmation(self, event: MessageEvent, parsed_data: Dict[str, Any]) -> None:
        """顯示單一訂單確認"""
        order_summary = self._format_single_order_summary(parsed_data)
        
        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            buttons_template = ButtonsTemplate(
                text=order_summary[:300],  # LINE 有字數限制
                actions=[
                    PostbackAction(
                        label='確認訂單',
                        data=json.dumps({'action': 'confirm_single_order'})
                    ),
                    PostbackAction(
                        label='重新輸入',
                        data=json.dumps({'action': 'start_order'})
                    ),
                    PostbackAction(
                        label='取消',
                        data=json.dumps({'action': 'cancel_order'})
                    )
                ]
            )
            
            template_message = TemplateMessage(
                alt_text='訂單確認',
                template=buttons_template
            )
            
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )
    
    def _show_multiple_orders_overview(self, event: MessageEvent, parsed_data: Dict[str, Any]) -> None:
        """顯示多訂單總覽"""
        orders = parsed_data.get('orders', [])
        total_orders = parsed_data.get('total_orders', 0)
        
        overview_text = f"🎉 發現 {total_orders} 份訂單！\n\n"
        for i, order in enumerate(orders, 1):
            receiver_name = order.get('receiver_name', 'N/A')
            items_count = len(order.get('items', []))
            overview_text += f"📋 訂單 {i}: {receiver_name} ({items_count} 項商品)\n"
        
        overview_text += "\n請選擇操作方式："
        
        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            buttons_template = ButtonsTemplate(
                text=overview_text,
                actions=[
                    PostbackAction(
                        label='逐一確認',
                        data=json.dumps({
                            'action': 'show_order_at_index',
                            'order_index': 1
                        })
                    ),
                    PostbackAction(
                        label='全部確認',
                        data=json.dumps({'action': 'confirm_all_orders'})
                    ),
                    PostbackAction(
                        label='重新輸入',
                        data=json.dumps({'action': 'start_order'})
                    )
                ]
            )
            
            template_message = TemplateMessage(
                alt_text='多訂單總覽',
                template=buttons_template
            )
            
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )
    
    def _show_order_at_index(self, event: PostbackEvent, order_index: int) -> None:
        """顯示特定索引的訂單詳情"""
        user_id = event.source.user_id
        
        if (user_id not in self.order_sessions or 
            'parsed' not in self.order_sessions[user_id].get('data', {})):
            self._reply_text(event, "找不到訂單資料，請重新開始。")
            return
        
        parsed_data = self.order_sessions[user_id]['data']['parsed']
        orders = parsed_data.get('orders', [])
        total_orders = len(orders)
        
        if order_index < 1 or order_index > total_orders:
            self._reply_text(event, "訂單索引錯誤。")
            return
        
        current_order = orders[order_index - 1]
        order_summary = f"📋 訂單 {order_index}/{total_orders}\n\n"
        order_summary += self._format_single_order_summary(current_order)
        
        # 準備按鈕
        actions = [
            PostbackAction(
                label='確認此訂單',
                data=json.dumps({
                    'action': 'confirm_order_at_index',
                    'order_index': order_index
                })
            )
        ]
        
        # 導航按鈕
        if order_index > 1:
            actions.append(PostbackAction(
                label=f'上一份 ({order_index-1})',
                data=json.dumps({
                    'action': 'show_order_at_index',
                    'order_index': order_index - 1
                })
            ))
        
        if order_index < total_orders:
            actions.append(PostbackAction(
                label=f'下一份 ({order_index+1})',
                data=json.dumps({
                    'action': 'show_order_at_index',
                    'order_index': order_index + 1
                })
            ))
        
        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            buttons_template = ButtonsTemplate(
                text=order_summary[:300],
                actions=actions[:3]  # LINE 最多 3 個按鈕
            )
            
            template_message = TemplateMessage(
                alt_text=f'訂單 {order_index} 詳情',
                template=buttons_template
            )
            
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[template_message]
                )
            )
    
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
    
    def _confirm_single_order(self, event: PostbackEvent) -> None:
        """確認單一訂單"""
        user_id = event.source.user_id
        
        if (user_id not in self.order_sessions or 
            'parsed' not in self.order_sessions[user_id].get('data', {})):
            self._reply_text(event, "找不到訂單資料，請重新開始。")
            return
        
        parsed_data = self.order_sessions[user_id]['data']['parsed']
        self._save_order_to_sheets(event, parsed_data, 1)
        
        # 清除會話狀態
        if user_id in self.order_sessions:
            del self.order_sessions[user_id]
    
    def _confirm_order_at_index(self, event: PostbackEvent, order_index: int) -> None:
        """確認特定索引的訂單"""
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
    
    def _confirm_all_orders(self, event: PostbackEvent) -> None:
        """確認所有訂單"""
        user_id = event.source.user_id
        
        if (user_id not in self.order_sessions or 
            'parsed' not in self.order_sessions[user_id].get('data', {})):
            self._reply_text(event, "找不到訂單資料，請重新開始。")
            return
        
        parsed_data = self.order_sessions[user_id]['data']['parsed']
        orders = parsed_data.get('orders', [])
        
        success_count = 0
        for i, order_data in enumerate(orders, 1):
            if self._save_order_to_sheets_silent(order_data, i):
                success_count += 1
        
        total_orders = len(orders)
        if success_count == total_orders:
            self._reply_text(event, f"🎉 已成功建立 {total_orders} 份訂單！")
        else:
            self._reply_text(event, 
                f"⚠️ 已成功建立 {success_count}/{total_orders} 份訂單。\n"
                f"部分訂單可能建立失敗，請檢查 Google Sheets。"
            )
        
        # 清除會話狀態
        if user_id in self.order_sessions:
            del self.order_sessions[user_id]
    
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