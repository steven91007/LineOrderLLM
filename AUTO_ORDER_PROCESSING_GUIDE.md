# Automatic Order Processing Guide

## 📋 Overview

The system now supports smart order processing that **automatically groups orders by ship date**, with these core features:

### ⭐ Key features
- 🕒 **Network time sync** - automatically fetches accurate time from the network so dates and weekdays are correct
- 📅 **Smart date parsing** - supports many date formats (`2025-08-07`, `明天` (tomorrow), `後天` (day after tomorrow), `3天後` (in 3 days))
- 🗂️ **Automatic grouping** - automatically creates and assigns Google Sheets worksheets by ship date
- ⚡ **Batch processing** - handles multiple orders at once, assigning each to the matching date worksheet
- 📊 **Smart statistics** - detailed per-group statistics and management info

## 🚀 Quick Start

### 1. Environment setup

Make sure the following environment variables are set correctly:

```bash
# .env file
GOOGLE_SHEETS_CREDENTIALS_PATH=/path/to/your/credentials.json
GOOGLE_SHEETS_ID=your_spreadsheet_id_here
```

### 2. Enabling the feature

Automatic grouping is enabled by default. It is turned on automatically when `OrderHandler` is initialized:

```python
# src/handlers/order_handler.py
self.sheets_client = GoogleSheetsClient(
    google_credentials_path, 
    google_sheet_id, 
    auto_organize_by_date=True  # Automatically group by date
)
```

## 📊 Worksheet Organization

### Worksheet naming

The system creates worksheets automatically from the ship date, named in the format `YYYYMMDD_星期X` (星期X = weekday X):

**Examples:**
- `20250807_星期四` - orders for August 7, 2025 (Thursday)
- `20250808_星期五` - orders for August 8, 2025 (Friday)
- `20250809_星期六` - orders for August 9, 2025 (Saturday)

### Grouping logic

1. **Ship date given** → assigned to the worksheet for that ship date
2. **No ship date** → a worksheet is created using today's date
3. **Worksheet doesn't exist** → a new worksheet is created automatically with a header row

## 🎯 Usage

### LINE Bot flow

1. The user sends the `#訂單` (order) command
2. Choose "開始建立訂單" (start creating an order)
3. Enter the order content (may contain multiple orders)
4. The system parses it automatically and shows a confirmation screen
5. After confirmation, the system **automatically groups orders by ship date** and writes them to the matching worksheets

### Supported date formats

Users can specify the ship date in any of these formats:

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
(標準格式 = standard format, 簡化格式 = short format, 自然語言 = natural language: 今天 today, 明天 tomorrow, 後天 day after tomorrow, 3天後 in 3 days, 一週後 in one week.)

## 📈 System Feedback

### Batch order success message

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
(This is the message shown to the user: batch submission succeeded, 5 orders created, auto-grouped into 3 worksheets with per-date counts, the order numbers, and a note that all orders were recorded to Google Sheets grouped by ship date.)

## 🔧 Advanced Features

### 1. Manually reorganize existing orders

If you have old data in a single worksheet, use the reorganize feature:

```python
from utils.google_sheets_client import GoogleSheetsClient

client = GoogleSheetsClient(credentials_path, sheet_id, auto_organize_by_date=True)

# Reorganize existing orders
result = client.organize_existing_orders_by_date()
print(result['message'])
```

### 2. Get worksheet statistics

```python
# Get a summary of all worksheets
summary = client.get_sheets_summary()

for sheet in summary['sheets']:
    if sheet['is_date_sheet']:
        print(f"📅 {sheet['name']}: {sheet['row_count']} 份訂單")
    else:
        print(f"📋 {sheet['name']}: {sheet['row_count']} 份訂單")
```

### 3. Disable automatic grouping

To go back to single-worksheet mode:

```python
# Set auto_organize_by_date=False at initialization
client = GoogleSheetsClient(
    credentials_path, 
    sheet_id, 
    auto_organize_by_date=False
)
```

## 🧪 Testing

Run the full feature test:

```bash
python test_auto_order_processing.py
```

The tests cover:
- ⏰ Network time fetching
- 📅 Date parsing and formatting
- 🗂️ Automatic grouped writes
- 📊 Batch processing
- 📋 Worksheet management

## ⚠️ Notes

### 1. Network time fetching

The system tries to get accurate time from these sources:
- WorldTimeAPI (primary)
- TimezoneDB (backup)
- System time (last resort)

### 2. Time zone handling

The system uses the `Asia/Taipei` time zone so weekday calculations are correct.

### 3. Worksheet limits

- A single Google Sheets spreadsheet supports at most 200 worksheets
- Archive old date worksheets regularly

### 4. Performance

- Batch processing is more efficient than one order at a time
- The system caches worksheet info automatically to improve performance
- Network time fetching is cached for 5 minutes

## 📞 FAQ

### Q: How do I see which date worksheets currently exist?

A: Use the `get_sheets_summary()` method to get the full worksheet list and statistics.

### Q: What happens if an order has no ship date?

A: The system uses today's date and assigns the order to today's worksheet.

### Q: Can I change the worksheet naming format?

A: Yes — modify the `format_date_with_weekday()` method in `time_utils.py` to customize the format.

### Q: What if network time fetching fails?

A: The system automatically falls back to system time and logs a warning.

### Q: How do I back up and restore data?

A: Regularly use Google Sheets' export feature to back up important data.

## 🔮 Roadmap

- [ ] Support more natural-language date formats
- [ ] Automatic worksheet archiving
- [ ] Order statistics and analytics dashboard
- [ ] Custom worksheet grouping rules
- [ ] Order status tracking

---

**💡 Tip:** This feature is fully integrated into your LINE Bot system; users get the convenience of smart grouping automatically, with no extra setup!
