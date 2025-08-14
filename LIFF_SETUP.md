# 🌐 LIFF 訂單編輯器設定指南

## 📋 概述

LIFF (LINE Front-end Framework) 訂單編輯器讓用戶可以在類似原生 APP 的網頁介面中編輯訂單，提供比 Flex Message 按鈕更豐富的編輯體驗。

## 🚀 功能特色

### ✨ 用戶體驗升級
- **表格式編輯介面**：類似 Excel 的直觀編輯體驗
- **即時內容驗證**：前端即時檢查格式錯誤
- **批量編輯支援**：可同時修改多筆訂單
- **響應式設計**：手機、平板、桌面都完美適配

### 🔧 技術特色
- **無縫整合**：與現有 LINE Bot 完美整合
- **安全會話管理**：2小時自動過期的編輯會話
- **智能解析**：DSPy 引擎支援的商品項目解析
- **自動儲存**：編輯完成後自動更新 Google Sheets

## 📦 安裝與設定

### 1. 建立 LIFF 應用程式

1. 前往 [LINE Developers Console](https://developers.line.biz/)
2. 選擇你的 Provider 和 Channel
3. 進入 **LIFF** 頁籤
4. 點擊 **Add** 新增 LIFF app
5. 設定如下：
   ```
   LIFF app name: 訂單編輯器
   Size: Full
   Endpoint URL: https://your-domain.com/liff/edit
   Scope: profile, openid
   Bot link feature: On (Aggressive)
   ```

### 2. 環境變數設定

在 `.env` 檔案中添加：

```bash
# 現有的設定...
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token
LINE_CHANNEL_SECRET=your_channel_secret
OPENAI_API_KEY=your_openai_api_key
GOOGLE_SHEET_ID=your_sheet_id
GOOGLE_CREDENTIALS_PATH=credentials.json

# 新增 LIFF 設定
LIFF_ID=your_liff_id_here
FLASK_SECRET_KEY=your_flask_secret_key
```

### 3. 啟動應用程式

```bash
# 使用 LIFF 版本的應用程式
python app_with_liff.py
```

## 🔄 用戶使用流程

### 方案一：完整 LIFF 體驗 (推薦)
1. 用戶在 LINE 中輸入 `#訂單`
2. 輸入訂單文字，DSPy 解析
3. 在 Flex Message 確認頁面點擊 **🌐 網頁編輯**
4. 開啟 LIFF 編輯器進行詳細修改
5. 點擊 **💾 儲存所有變更**
6. 自動回傳 LINE 並更新 Google Sheets

### 方案二：按鈕編輯 (Fallback)
1. 用戶在 Flex Message 中點擊具體編輯按鈕
2. 在 LINE 對話中輸入修改內容
3. 系統更新並重新顯示確認介面

## 🎨 LIFF 編輯器功能

### 📝 編輯功能
- **收件人資訊**：姓名和電話的實時編輯
- **收件地址**：多行文字區域，支援長地址
- **商品管理**：
  - 動態添加/刪除商品項目
  - 數量調整 (滑桿/數字輸入)
  - DSPy 智能解析支援
- **發貨日期**：MM-DD 格式，內建驗證
- **寄件人資訊**：可摺疊的選填區域

### 🔍 驗證機制
- **必填欄位檢查**：收件人、電話、地址、商品
- **格式驗證**：電話號碼、日期格式
- **邏輯檢查**：商品數量、日期合理性
- **即時提示**：錯誤欄位高亮顯示

### 💾 儲存流程
1. 前端收集並驗證所有資料
2. 發送 PUT 請求到 `/api/liff/orders/{session_id}`
3. 後端驗證資料格式和邏輯
4. 寫入 Google Sheets (按日期分組)
5. 發送確認訊息到 LINE
6. 自動關閉 LIFF 視窗

## 🔧 API 端點

### GET `/liff/edit?session={session_id}`
LIFF 編輯頁面

### GET `/api/liff/orders/{session_id}`
獲取編輯會話資料
```json
{
  "success": true,
  "orders": [...],
  "total_orders": 2,
  "user_id": "U..."
}
```

### PUT `/api/liff/orders/{session_id}`
更新訂單資料
```json
{
  "user_id": "U...",
  "orders": [...]
}
```

### POST `/api/liff/cleanup`
清理過期會話 (定時任務)

## 🛠️ 部署注意事項

### HTTPS 需求
LIFF 應用程式**必須**使用 HTTPS，可使用：
- **Ngrok**: 開發環境快速 HTTPS tunnel
- **Cloudflare**: 免費 SSL 代理
- **Let's Encrypt**: 免費 SSL 憑證

### Webhook URL 更新
確保 LINE Channel 的 Webhook URL 指向你的 HTTPS 域名：
```
https://your-domain.com/callback
```

### 安全性設定
- 設定強密碼的 `FLASK_SECRET_KEY`
- 限制 `AUTHORIZED_USERS` 清單
- 定期清理過期會話 (自動每小時執行)

## 🚀 進階功能

### 自訂 LIFF 外觀
編輯 `templates/liff_order_edit.html`：
- 調整 Tailwind CSS 樣式
- 修改色彩主題
- 添加動畫效果

### 批量處理
LIFF 編輯器支援同時編輯最多 5 筆訂單，適合：
- 大量訂單修改
- 統一發貨日期調整
- 地址批量更新

### 資料持久化
可將 `liff_sessions` 改為使用 Redis：
```python
# 在 liff_handler.py 中
import redis
self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
```

## 🐛 疑難排解

### LIFF 無法開啟
1. 檢查 LIFF ID 是否正確
2. 確認 Endpoint URL 使用 HTTPS
3. 驗證 Bot link feature 已啟用

### 會話過期問題
- 會話預設 2 小時過期
- 可在 `liff_handler.py` 中調整 `timedelta(hours=2)`

### 資料不同步
1. 檢查 Google Sheets API 權限
2. 確認試算表 ID 正確
3. 查看伺服器日誌錯誤訊息

## 📊 監控與分析

查看使用狀況：
```bash
# 檢查健康狀態
curl https://your-domain.com/health

# 查看示範功能
curl https://your-domain.com/liff/demo
```

## 🎯 未來擴展

可考慮新增：
- **拖拽排序**：商品項目順序調整
- **範本功能**：常用訂單範本
- **匯入匯出**：CSV/Excel 檔案支援
- **多語言**：國際化支援
- **深色模式**：夜間使用體驗

---

🎉 現在你擁有了功能強大的 LIFF 訂單編輯系統！用戶可以選擇快速按鈕編輯或深度網頁編輯，滿足各種使用場景需求。