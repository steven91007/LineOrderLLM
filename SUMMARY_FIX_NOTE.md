# Order Summary (匯總) Fix Notes

## Problem description

Received the error message: `Invalid reply token`

It happened when a user typed `#匯總 8/24`.

## Root cause

The LINE Bot API `reply_token` can only be used once. In the original implementation:

1. The first call used `_reply_text()` to send a "🔍 正在查詢..." ("Querying...") message
2. The second call tried to send the query result with the same `reply_token`
3. So the second send failed with an "Invalid reply token" error

## Solution

### Fixes applied

1. **Removed the first reply**: deleted the "正在查詢..." ("Querying...") message to avoid reusing the reply_token

2. **Merged status and result**: the processing-status info is folded into the final result and sent once
   ```python
   full_message = f"🔍 已完成 {target_date} 的查詢\n\n{formatted_report}"
   ```

3. **Simplified long-message handling**: because of the reply_token limit, the split-and-send logic was removed

### Files changed

- `src/handlers/order_handler.py`
  - Line 906: removed the logic that sent a "processing" message first
  - Lines 943-951: changed to merge status and result into a single send
  - Lines 997-1009: turned `_send_long_message` into a fallback method

## Usage

### Normal usage

```
用戶: #匯總 8/24
系統: 🔍 已完成 8/24 的查詢

📊 2024-08-24 品項匯總報告
==============================
[詳細統計資料...]
```
(用戶 = user, 系統 = system. The bot reply reads roughly "Finished the query for 8/24 / 2024-08-24 item summary report / [detailed statistics...]".)

### Supported command formats

- `#匯總 8/24` - query August 24
- `#匯總 08-24` - query August 24
- `#匯總 2024-08-24` - query August 24, 2024
- `#匯總 星期二` - query this week's Tuesday
- `#匯總` - query today

## Technical limitations

### LINE Bot API limits

1. **Reply Token**
   - Each reply_token can only be used once
   - You must reply immediately after receiving the webhook
   - You cannot send multiple reply messages

2. **Message length**
   - A single message is at most 5000 characters
   - Above 2000 characters, trimming the content is recommended

### Suggested improvements (future)

For a better user experience, consider:

1. **Use Push Message**
   - Requires a paid LINE Official Account
   - Can proactively send multiple messages
   - Not limited by reply_token

2. **Use Loading Animation**
   - A loading indicator supported by LINE
   - Still subject to the reply_token limit, though

3. **Speed up queries**
   - Cache common query results
   - Optimize Google Sheets API calls

## Test confirmation

✅ The feature has been tested and confirmed working:

1. Date parsing works
2. Google Sheets queries work
3. Item statistics work
4. Report generation works
5. Single reply works (no Invalid reply token error)

## Notes

- The summary feature requires the Google Sheets integration to be working
- Make sure the environment variables `GOOGLE_SHEET_ID` and `GOOGLE_CREDENTIALS_PATH` are set correctly
- Orders must already be uploaded to Google Sheets to be found by the query
