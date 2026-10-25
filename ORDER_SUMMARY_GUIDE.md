# Order Summary Guide

## 🎯 Overview

The order summary feature gives you a quick per-item tally for a given date, making it easy to report that day's orders to your manager.

## 📱 Usage

### Basic syntax
The command keyword is `#匯總` ("#summary") and must be typed as shown:
```
#匯總 [date]
```

### Supported date formats

1. **Month/day**
   - `#匯總 8/27` - August 27
   - `#匯總 08-27` - August 27

2. **Full date**
   - `#匯總 2024-08-27` - August 27, 2024

3. **Relative date** (weekday names in Chinese)
   - `#匯總 星期二` - Tuesday of this week
   - `#匯總 週三` - Wednesday of this week

4. **No date**
   - `#匯總` - today's orders

### Example

The bot replies in Chinese. The reply below shows: a "querying 8/27 order data, please wait" notice, then the "item summary report" with total orders, total items, number of item types, the per-item breakdown, the top items, the report generation time, and a note that the report can be handed straight to a manager.

```
用戶: #匯總 8/27
系統: 🔍 正在查詢 8/27 的訂單資料，請稍候...

📊 2024-08-27(星期二) 品項匯總報告
==============================
📋 總訂單數：5 份
📦 總品項數：15 個
🏷️ 品項種類：4 種

📈 品項明細：
   1. 18A禮盒 × 8
   2. 20A花束 × 4
   3. 16A蛋糕 × 2
   4. 22A巧克力 × 1

🔝 熱門品項統計：
  最多：18A禮盒 (8 個)
  次多：20A花束 (4 個)

📅 報告生成時間：2024-08-27(星期二)
🎯 此報告可直接提供給主管參考
```

## 🔧 Features

### 1. Smart item parsing
Supports several item formats (`兩個` = "two", `一個` = "one"):
- `18A禮盒 x2, 16A蛋糕 x1`
- `18A禮盒 兩個, 16A蛋糕 一個`
- `18A禮盒(2), 16A蛋糕(1)`
- `2 x 18A禮盒, 1 x 16A蛋糕`

### 2. Automatic tallying
- Automatically queries Google Sheets for orders on the given date
- Parses item details and tallies quantities
- Sorts by quantity and shows the top items

### 3. Multiple sheet support
- Searches the dedicated sheet for that date first
- If none is found, searches all sheets
- Supports the sheet structure that is automatically grouped by date

### 4. Complete report format
The generated report includes:
- Total orders and total items
- A detailed per-item list
- Top-item statistics
- A format suitable for handing straight to a manager

## ⚙️ Requirements

### Prerequisites
1. ✅ Google Sheets integration is enabled
2. ✅ Order data has been uploaded to Google Sheets
3. ✅ The user is authorized to use the system

### Data source
- The summary feature reads order data from Google Sheets
- Supports the sheet structure that is automatically grouped by date
- Compatible with the existing order upload format

## 🚨 Notes

### Date formats
- Date parsing is based on the existing weekday conversion logic
- Supports absolute dates (e.g. 8/27) and relative dates (e.g. 星期二, "Tuesday")
- Using a standard format is recommended to make sure dates parse correctly

### Item parsing
- The system tries several parsing patterns to identify items and quantities
- If parsing fails, it falls back to backup parsing logic
- Item names are normalized automatically to avoid double counting

### Error handling
- If no order data is found, a friendly error message is shown
- The system suggests possible causes and solutions
- Long messages are split and sent in parts automatically

## 📊 Real-World Scenarios

### 1. Daily operations report
```
Manager: How are today's orders looking?
You: #匯總
Bot: [shows today's full summary]
```

### 2. Specific date lookup
```
Manager: How many gift boxes did we sell last Tuesday?
You: #匯總 星期二
Bot: [shows detailed stats for last Tuesday]
```

### 3. Historical analysis
```
Need: check sales for August 27
You: #匯總 8/27
Bot: [shows the full report for that date]
```

## 🔄 Integration with Existing Features

### Existing features are unaffected
- ✅ The order creation flow is unaffected
- ✅ Google Sheets uploads work as before
- ✅ The LIFF editor works as before
- ✅ All existing commands remain available

### Compatibility guarantees
- The summary feature is implemented as a standalone module
- It uses the existing Google Sheets client
- It follows the existing date handling logic
- It does not modify any existing data structures

## 🎯 Recommendations

1. **Use it regularly**: check the day's orders with the summary feature every day
2. **Consistent formats**: use a standard date format (e.g. 8/27) to make sure it parses correctly
3. **Check the data**: make sure the relevant orders have been uploaded to Google Sheets before using it
4. **Keep the report**: you can screenshot or copy the generated report straight to your manager

## ❓ FAQ

**Q: Why can't I find orders for a certain date?**
A: Make sure that date's orders have been uploaded to Google Sheets and the date format is correct.

**Q: What if the item tally is inaccurate?**
A: Check whether the item format in the original orders is standard. The system supports several formats, but the "item name x quantity" format is recommended.

**Q: Can I get a summary for multiple dates?**
A: Currently you can only query one date at a time; for multi-date stats, query each date separately.

**Q: What if the report is too long to display in full?**
A: The system automatically splits long messages, so you will receive several messages containing the full report.
