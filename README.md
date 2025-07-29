# LINE Bot 配置說明

## 設置步驟

### 1. 啟動應用程式和 ngrok 隧道

```bash
# 方法一：使用腳本啟動
./start_ngrok.sh

# 方法二：分別啟動
# 終端1：啟動 Flask 應用
python main.py

# 終端2：啟動 ngrok
ngrok http 5000
```

### 2. 設定 LINE Bot Webhook URL

1. 啟動 ngrok 後，會看到類似這樣的輸出：
   ```
   Forwarding: https://xxxx-xx-xx-xx-xx.ngrok-free.app -> http://localhost:5000
   ```

2. 登入 [LINE Developers Console](https://developers.line.biz/)

3. 選擇您的 Channel

4. 在 Messaging API 標籤下找到 Webhook settings

5. 設定 Webhook URL 為：
   ```
   https://xxxx-xx-xx-xx-xx.ngrok-free.app/callback
   ```
   （將 xxxx-xx-xx-xx-xx 替換為您的 ngrok URL）

6. 啟用 "Use webhook"

7. 點擊 "Verify" 測試連接

### 3. 測試 LINE Bot

1. 掃描 QR code 將 Bot 加為好友
2. 發送訊息測試回音功能

## 環境變數設定

請確保 `.env` 檔案包含正確的設定：

```
LINE_CHANNEL_ACCESS_TOKEN=您的Channel Access Token
LINE_CHANNEL_SECRET=您的Channel Secret
```

## 注意事項

- ngrok 免費版的 URL 會在每次重啟時改變
- 需要在 LINE Developers Console 更新新的 Webhook URL
- 建議申請 ngrok 付費版以獲得固定 URL