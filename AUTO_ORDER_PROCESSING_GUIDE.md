# 自動訂單處理功能使用指南

## 📋 功能概述

本系統現已支援**自動按出貨日期分組**的智能訂單處理，包含以下核心功能：

### ⭐ 核心特色
- 🕒 **網路時間同步** - 自動從網路獲取準確時間，確保日期和星期正確
- 📅 **智能日期解析** - 支援多種日期格式 (`2025-08-07`, `明天`, `後天`, `3天後`)
- 🗂️ **自動分組管理** - 依出貨日期自動創建和分配 Google Sheets 工作表
- ⚡ **批量處理** - 支援多筆訂單同時處理，自動分配到對應日期工作表
- 📊 **智能統計** - 提供詳細的分組統計和管理資訊

## 🚀 快速開始

### 1. 環境設置

確保以下環境變數已正確設定：

```bash
# .env 檔案
GOOGLE_SHEETS_CREDENTIALS_PATH=/path/to/your/credentials.json
GOOGLE_SHEETS_ID=your_spreadsheet_id_here
```

### 2. 功能啟用

系統已預設啟用自動分組功能。在 `OrderHandler` 初始化時會自動啟用：

```python
# src/handlers/order_handler.py
self.sheets_client = GoogleSheetsClient(
    google_credentials_path, 
    google_sheet_id, 
    auto_organize_by_date=True  # 自動按日期分組
)
```

## 📊 工作表組織結構

### 工作表命名規則

系統會根據出貨日期自動創建工作表，命名格式為：`YYYYMMDD_星期X`

**範例：**
- `20250807_星期四` - 2025年8月7日(星期四)的訂單
- `20250808_星期五` - 2025年8月8日(星期五)的訂單
- `20250809_星期六` - 2025年8月9日(星期六)的訂單

### 自動分組邏輯

1. **有指定出貨日期** → 根據出貨日期分配到對應工作表
2. **沒有出貨日期** → 使用當天日期創建工作表
3. **工作表不存在** → 自動創建新工作表並設置標題行

## 🎯 使用方式

### Line Bot 使用流程

1. 用戶發送 `#訂單` 指令
2. 選擇「開始建立訂單」
3. 輸入訂單內容（可包含多筆訂單）
4. 系統自動解析並顯示確認介面
5. 確認後系統**自動按出貨日期分組**寫入對應工作表

### 支援的日期格式

用戶可使用以下任一格式指定出貨日期：

```
標準格式：
- 2025-08-07
- 2025/08/07

簡化格式：
- 08-07
- 8/7

自然語言：
- 今天
- 明天
- 後天
- 3天後
- 一週後
```

## 📈 系統回饋資訊

### 批量訂單處理成功訊息

```
🎉 批量提交成功！

✅ 已成功建立 5 份訂單

📊 已自動分組到 3 個工作表：

📅 2025-08-07(星期四): 2 份訂單
📅 2025-08-08(星期五): 2 份訂單  
📅 2025-08-09(星期六): 1 份訂單

📋 訂單編號：
• ORD-20250807-ABC123 (張小明)
• ORD-20250807-DEF456 (李小華)
...

🗂️ 所有訂單已自動按出貨日期分組記錄到 Google Sheets。
```

## 🔧 進階功能

### 1. 手動重新組織現有訂單

如果您有舊的單一工作表資料，可使用重新組織功能：

```python
from utils.google_sheets_client import GoogleSheetsClient

client = GoogleSheetsClient(credentials_path, sheet_id, auto_organize_by_date=True)

# 重新組織現有訂單
result = client.organize_existing_orders_by_date()
print(result['message'])
```

### 2. 獲取工作表統計

```python
# 獲取所有工作表摘要
summary = client.get_sheets_summary()

for sheet in summary['sheets']:
    if sheet['is_date_sheet']:
        print(f"📅 {sheet['name']}: {sheet['row_count']} 份訂單")
    else:
        print(f"📋 {sheet['name']}: {sheet['row_count']} 份訂單")
```

### 3. 禁用自動分組

如需回到單一工作表模式：

```python
# 初始化時設定 auto_organize_by_date=False
client = GoogleSheetsClient(
    credentials_path, 
    sheet_id, 
    auto_organize_by_date=False
)
```

## 🧪 功能測試

執行完整功能測試：

```bash
python test_auto_order_processing.py
```

測試內容包括：
- ⏰ 網路時間獲取測試
- 📅 日期解析和格式化測試
- 🗂️ 自動分組寫入測試
- 📊 批量處理測試
- 📋 工作表管理測試

## ⚠️ 注意事項

### 1. 網路時間獲取

系統會嘗試從以下來源獲取準確時間：
- WorldTimeAPI (主要)
- TimezoneDB (備用)
- 系統時間 (最終備用)

### 2. 時區處理

系統使用 `Asia/Taipei` 時區，確保星期幾計算準確。

### 3. 工作表限制

- Google Sheets 單一試算表最多支援 200 個工作表
- 建議定期歸檔舊的日期工作表

### 4. 效能考量

- 批量處理比單筆處理效率更高
- 系統會自動快取工作表資訊以提升效能
- 網路時間獲取有 5 分鐘快取機制

## 📞 常見問題

### Q: 如何查看目前有哪些日期工作表？

A: 使用 `get_sheets_summary()` 方法可以獲取完整的工作表清單和統計。

### Q: 訂單沒有出貨日期會怎樣？

A: 系統會使用當天日期，將訂單分配到當天的工作表。

### Q: 可以修改工作表命名格式嗎？

A: 可以修改 `time_utils.py` 中的 `format_date_with_weekday()` 方法來自訂格式。

### Q: 網路時間獲取失敗怎麼辦？

A: 系統會自動降級使用系統時間，並在日誌中記錄警告。

### Q: 如何備份和還原資料？

A: 建議定期使用 Google Sheets 的匯出功能備份重要資料。

## 🔮 未來規劃

- [ ] 支援更多自然語言日期格式
- [ ] 加入工作表自動歸檔功能
- [ ] 提供訂單統計和分析儀表板
- [ ] 支援自訂工作表分組規則
- [ ] 加入訂單狀態追蹤功能

---

**💡 提示：** 此功能已完全整合到您的 Line Bot 系統中，用戶使用時會自動享受智能分組的便利性，無需額外設定！