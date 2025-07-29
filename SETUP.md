# LINE Bot 訂單處理系統設置指南

## 功能概述

這是一個智能 LINE Bot 訂單處理系統，具備以下功能：

1. **訊息接收與權限控制**：私人訂單處理功能，僅授權用戶可使用
2. **智能解析**：使用 OpenAI GPT-4 自動提取訂單資訊
3. **資料整合**：自動將訂單資料寫入 Google Sheets

## 設置步驟

### 1. 環境準備

```bash
# 安裝相依套件
pip install -r requirements.txt

# 複製環境變數範本
cp .env.example .env
```

### 2. LINE Bot 設定

1. 前往 [LINE Developers Console](https://developers.line.biz/)
2. 建立新的 Provider 和 Channel
3. 取得以下資訊並填入 `.env`：
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_CHANNEL_SECRET`

### 3. OpenAI 設定

1. 前往 [OpenAI Platform](https://platform.openai.com/)
2. 建立 API Key
3. 將 API Key 填入 `.env` 的 `OPENAI_API_KEY`

### 4. Google Sheets 設定

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立新專案或選擇現有專案
3. 啟用 Google Sheets API
4. 建立服務帳戶並下載 JSON 憑證檔案
5. 將憑證檔案重新命名為 `credentials.json` 並放在專案根目錄
6. 建立 Google Sheet 並取得 Sheet ID
7. 將 Sheet ID 填入 `.env` 的 `GOOGLE_SHEET_ID`
8. 將服務帳戶的 email 加入 Google Sheet 的編輯權限

### 5. 授權用戶設定

1. 取得需要使用此功能的 LINE 用戶 ID
2. 將用戶 ID 填入 `.env` 的 `AUTHORIZED_USERS`（用逗號分隔多個 ID）
3. 或設定為 `*` 允許所有用戶使用

### 6. 啟動應用

```bash
# 開發環境
python main.py

# 生產環境
gunicorn main:app --bind 0.0.0.0:5000
```

## 使用方式

1. 在 LINE 中向 Bot 發送 `#訂單` 或 `#order`
2. 點選「開始建立訂單」按鈕
3. 輸入訂單內容（包含寄件人、收件人、商品、地址等資訊）
4. 系統自動解析並顯示結果供確認
5. 確認無誤後點選「確認訂單」完成建立

## 訂單資訊格式

系統會自動解析以下資訊：
- 寄件人姓名與電話
- 收件人姓名與電話  
- 商品品項與數量
- 預計發貨日期
- 收件地址

## 錯誤排除

### 常見問題

1. **Bot 沒有回應**
   - 確認 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 正確
   - 檢查 Webhook URL 是否正確設定

2. **OpenAI 解析失敗**
   - 確認 OPENAI_API_KEY 有效且有足夠額度
   - 檢查網路連線是否正常

3. **Google Sheets 寫入失敗**
   - 確認 credentials.json 檔案存在且格式正確
   - 檢查服務帳戶是否有 Google Sheet 的編輯權限
   - 確認 GOOGLE_SHEET_ID 正確

### 日誌查看

應用會在控制台輸出相關日誌，出現問題時可查看具體錯誤訊息。

## 安全注意事項

1. 不要將 `.env` 檔案提交到版本控制系統
2. 定期更換 API Keys
3. 限制授權用戶範圍
4. 定期檢查 Google Sheets 的存取權限