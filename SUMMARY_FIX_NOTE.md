# 訂單匯總功能修復說明

## 問題描述

收到錯誤訊息：`Invalid reply token`

發生在用戶輸入 `#匯總 8/24` 時。

## 問題原因

LINE Bot API 的 `reply_token` 只能使用一次。原本的實作中：

1. 第一次使用 `_reply_text()` 發送 "🔍 正在查詢..." 訊息
2. 第二次嘗試使用同一個 `reply_token` 發送查詢結果
3. 導致第二次發送失敗，出現 "Invalid reply token" 錯誤

## 解決方案

### 已實施的修復

1. **移除第一次回覆**：刪除了 "正在查詢..." 的訊息，避免重複使用 reply_token

2. **合併狀態和結果**：將處理狀態資訊併入最終結果中一次發送
   ```python
   full_message = f"🔍 已完成 {target_date} 的查詢\n\n{formatted_report}"
   ```

3. **簡化長訊息處理**：因為 reply_token 限制，移除了分段發送的邏輯

### 修改的檔案

- `src/handlers/order_handler.py`
  - 第 906 行：移除了先發送處理中訊息的邏輯
  - 第 943-951 行：修改為合併狀態和結果一次發送
  - 第 997-1009 行：將 `_send_long_message` 改為備用方法

## 使用說明

### 正常使用方式

```
用戶: #匯總 8/24
系統: 🔍 已完成 8/24 的查詢

📊 2024-08-24 品項匯總報告
==============================
[詳細統計資料...]
```

### 支援的指令格式

- `#匯總 8/24` - 查詢 8月24日
- `#匯總 08-24` - 查詢 8月24日
- `#匯總 2024-08-24` - 查詢 2024年8月24日
- `#匯總 星期二` - 查詢本週星期二
- `#匯總` - 查詢今天

## 技術限制

### LINE Bot API 限制

1. **Reply Token**
   - 每個 reply_token 只能使用一次
   - 必須在收到 webhook 後立即回覆
   - 無法發送多個回覆訊息

2. **訊息長度**
   - 單一訊息最大 5000 字符
   - 超過 2000 字符時建議精簡內容

### 建議的改進方案（未來）

如果需要更好的使用體驗，可以考慮：

1. **使用 Push Message**
   - 需要付費的 LINE Official Account
   - 可以主動發送多則訊息
   - 不受 reply_token 限制

2. **使用 Loading Animation**
   - LINE 支援的 loading indicator
   - 但仍受 reply_token 限制

3. **優化查詢速度**
   - 快取常用查詢結果
   - 優化 Google Sheets API 調用

## 測試確認

✅ 功能已測試並確認正常運作：

1. 日期解析正常
2. Google Sheets 查詢正常
3. 品項統計正常
4. 報告生成正常
5. 單次回覆正常（無 Invalid reply token 錯誤）

## 注意事項

- 匯總功能需要 Google Sheets 整合正常運作
- 確保環境變數 `GOOGLE_SHEET_ID` 和 `GOOGLE_CREDENTIALS_PATH` 已正確設定
- 訂單必須已上傳到 Google Sheets 才能查詢到