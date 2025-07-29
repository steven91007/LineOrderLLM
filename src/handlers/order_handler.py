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
from typing import Dict, Any
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
                "請輸入您的訂單內容，包含：\\n"
                "1. 寄件人姓名與電話\\n"
                "2. 收件人姓名與電話\\n"
                "3. 商品品項與數量\\n"
                "4. 預計發貨日期\\n"
                "5. 收件地址\\n\\n"
                "系統會自動解析您的訊息。"
            )
        elif action == 'cancel_order':
            # 取消訂單處理
            if user_id in self.order_sessions:
                del self.order_sessions[user_id]
            self._reply_text(event, "已取消訂單處理。")
        elif action == 'confirm_order':
            # 確認訂單
            self._confirm_and_save_order(event)
    
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
                    self.order_sessions[user_id]['status'] = 'confirming'
                    
                    # 顯示解析結果供確認
                    self._show_parsed_order_confirmation(event, parsed_data)
                else:
                    # 顯示錯誤訊息
                    error_msg = "解析訂單時發現以下問題：\\n"
                    if validation['missing_fields']:
                        error_msg += f"\\n缺少欄位：{', '.join(validation['missing_fields'])}"
                    if validation['invalid_phones']:
                        error_msg += f"\\n無效電話：{', '.join(validation['invalid_phones'])}"
                    if validation['invalid_items']:
                        error_msg += "\\n商品項目格式錯誤"
                    
                    error_msg += "\\n\\n請重新輸入訂單資訊。"
                    self._reply_text(event, error_msg)
            else:
                # OpenAI 解析失敗
                self._reply_text(event, 
                    f"解析訂單時發生錯誤：{result.get('error', '未知錯誤')}\\n"
                    "請稍後再試或聯絡管理員。"
                )
        else:
            # 沒有設定 OpenAI
            self._reply_text(event, 
                f"已收到您的訂單資訊：\\n\\n{order_text}\\n\\n"
                "（目前尚未啟用自動解析功能）"
            )
        
        # 清除會話狀態（如果不是在確認狀態）
        if user_id in self.order_sessions and self.order_sessions[user_id]['status'] != 'confirming':
            del self.order_sessions[user_id]
    
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
    
    def _show_parsed_order_confirmation(self, event: MessageEvent, parsed_data: Dict[str, Any]) -> None:
        """顯示解析後的訂單資訊供確認"""
        # 整理訂單資訊
        order_summary = "📦 訂單資訊解析結果：\n\n"
        order_summary += f"👤 寄件人：{parsed_data.get('sender_name', 'N/A')}\n"
        order_summary += f"📞 寄件人電話：{parsed_data.get('sender_phone', 'N/A')}\n\n"
        order_summary += f"👥 收件人：{parsed_data.get('receiver_name', 'N/A')}\n"
        order_summary += f"📞 收件人電話：{parsed_data.get('receiver_phone', 'N/A')}\n\n"
        
        if parsed_data.get('items'):
            order_summary += "📋 商品明細：\n"
            for item in parsed_data['items']:
                order_summary += f"  • {item['name']} x {item['quantity']}\n"
            order_summary += "\n"
        
        if parsed_data.get('shipping_date'):
            order_summary += f"📅 預計發貨日：{parsed_data['shipping_date']}\n"
        
        order_summary += f"📦 收件地址：{parsed_data.get('shipping_address', 'N/A')}\n\n"
        order_summary += "請確認以上資訊是否正確？"
        
        # 建立確認按鈕
        with ApiClient(self.configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            buttons_template = ButtonsTemplate(
                text=order_summary[:300],  # LINE 有字數限制
                actions=[
                    PostbackAction(
                        label='確認訂單',
                        data=json.dumps({
                            'action': 'confirm_order',
                            'user_id': event.source.user_id
                        })
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
    
    def _confirm_and_save_order(self, event: PostbackEvent) -> None:
        """確認並儲存訂單"""
        user_id = event.source.user_id
        
        # 檢查是否有訂單資料
        if user_id not in self.order_sessions or 'parsed' not in self.order_sessions[user_id].get('data', {}):
            self._reply_text(event, "找不到訂單資料，請重新開始。")
            return
        
        parsed_data = self.order_sessions[user_id]['data']['parsed']
        
        # 產生訂單編號
        order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        parsed_data['order_id'] = order_id
        
        # 儲存到 Google Sheets
        if self.sheets_client:
            result = self.sheets_client.append_order(parsed_data)
            
            if result['success']:
                success_message = (
                    f"✅ 訂單已成功建立！\n\n"
                    f"🆔 訂單編號：{order_id}\n"
                    f"📦 收件人：{parsed_data.get('receiver_name')}\n"
                    f"📦 地址：{parsed_data.get('shipping_address')}\n\n"
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
                f"👤 寄件人：{parsed_data.get('sender_name')}\n"
                f"👥 收件人：{parsed_data.get('receiver_name')}\n\n"
                "（目前未啟用 Google Sheets 儲存功能）"
            )
            self._reply_text(event, success_message)
        
        # 清除會話狀態
        if user_id in self.order_sessions:
            del self.order_sessions[user_id]