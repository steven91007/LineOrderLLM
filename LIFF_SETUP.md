# 🌐 LIFF Order Editor Setup Guide

## 📋 Overview

The LIFF (LINE Front-end Framework) order editor lets users edit orders in a web interface that feels like a native app, offering a richer editing experience than Flex Message buttons.

## 🚀 Features

### ✨ Better user experience
- **Table-style editing interface**: an intuitive, Excel-like editing experience
- **Live input validation**: the front end checks for format errors in real time
- **Bulk editing**: edit several orders at once
- **Responsive design**: works well on phones, tablets and desktops

### 🔧 Technical features
- **Seamless integration**: fits right into the existing LINE Bot
- **Secure session management**: editing sessions expire automatically after 2 hours
- **Smart parsing**: item parsing powered by the DSPy engine
- **Auto-save**: Google Sheets is updated automatically once editing is done

## 📦 Installation and Setup

### 1. Create the LIFF app

1. Go to the [LINE Developers Console](https://developers.line.biz/)
2. Select your Provider and Channel
3. Open the **LIFF** tab
4. Click **Add** to add a LIFF app
5. Use the following settings (`訂單編輯器` = "Order Editor", the app name users see):
   ```
   LIFF app name: 訂單編輯器
   Size: Full
   Endpoint URL: https://your-domain.com/liff/edit
   Scope: profile, openid
   Bot link feature: On (Aggressive)
   ```

### 2. Environment variables

Add the following to your `.env` file:

```bash
# Existing settings...
LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token
LINE_CHANNEL_SECRET=your_channel_secret
OPENAI_API_KEY=your_openai_api_key
GOOGLE_SHEET_ID=your_sheet_id
GOOGLE_CREDENTIALS_PATH=credentials.json

# New LIFF settings
LIFF_ID=your_liff_id_here
FLASK_SECRET_KEY=your_flask_secret_key
```

### 3. Start the app

```bash
# Use the LIFF version of the app
python app_with_liff.py
```

## 🔄 User Flow

### Option 1: Full LIFF experience (recommended)
1. The user types `#訂單` ("#order") in LINE
2. They enter the order text, which DSPy parses
3. On the Flex Message confirmation screen they tap **🌐 網頁編輯** ("Web edit")
4. The LIFF editor opens for detailed changes
5. They tap **💾 儲存所有變更** ("Save all changes")
6. They are returned to LINE automatically and Google Sheets is updated

### Option 2: Button editing (fallback)
1. The user taps a specific edit button in the Flex Message
2. They type the change in the LINE conversation
3. The system updates the order and shows the confirmation screen again

## 🎨 LIFF Editor Features

### 📝 Editing
- **Receiver info**: live editing of name and phone
- **Shipping address**: multi-line text area that handles long addresses
- **Item management**:
  - Add/remove items dynamically
  - Adjust quantities (slider/number input)
  - DSPy smart-parsing support
- **Shipping date**: MM-DD format, with built-in validation
- **Sender info**: a collapsible optional section

### 🔍 Validation
- **Required-field checks**: receiver, phone, address, items
- **Format validation**: phone number and date formats
- **Logic checks**: item quantities, reasonable dates
- **Instant hints**: fields with errors are highlighted

### 💾 Save flow
1. The front end collects and validates all data
2. Sends a PUT request to `/api/liff/orders/{session_id}`
3. The back end validates the data format and logic
4. Writes to Google Sheets (grouped by date)
5. Sends a confirmation message to LINE
6. Closes the LIFF window automatically

## 🔧 API Endpoints

### GET `/liff/edit?session={session_id}`
The LIFF editing page

### GET `/api/liff/orders/{session_id}`
Fetch editing session data
```json
{
  "success": true,
  "orders": [...],
  "total_orders": 2,
  "user_id": "U..."
}
```

### PUT `/api/liff/orders/{session_id}`
Update order data
```json
{
  "user_id": "U...",
  "orders": [...]
}
```

### POST `/api/liff/cleanup`
Clean up expired sessions (scheduled task)

## 🛠️ Deployment Notes

### HTTPS requirement
LIFF apps **must** use HTTPS. Options:
- **Ngrok**: quick HTTPS tunnel for development
- **Cloudflare**: free SSL proxy
- **Let's Encrypt**: free SSL certificates

### Updating the webhook URL
Make sure the LINE Channel's webhook URL points to your HTTPS domain:
```
https://your-domain.com/callback
```

### Security settings
- Set a strong `FLASK_SECRET_KEY`
- Restrict the `AUTHORIZED_USERS` list
- Clean up expired sessions regularly (runs automatically every hour)

## 🚀 Advanced Features

### Customizing the LIFF look
Edit `templates/liff_order_edit.html`:
- Adjust the Tailwind CSS styles
- Change the color theme
- Add animations

### Bulk processing
The LIFF editor can edit up to 5 orders at once, which is useful for:
- Changing many orders
- Adjusting the shipping date for several orders at once
- Updating addresses in bulk

### Data persistence
You can switch `liff_sessions` to Redis:
```python
# In liff_handler.py
import redis
self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
```

## 🐛 Troubleshooting

### LIFF will not open
1. Check that the LIFF ID is correct
2. Make sure the Endpoint URL uses HTTPS
3. Verify that the Bot link feature is enabled

### Session expiry
- Sessions expire after 2 hours by default
- You can change `timedelta(hours=2)` in `liff_handler.py`

### Data out of sync
1. Check the Google Sheets API permissions
2. Make sure the spreadsheet ID is correct
3. Look for error messages in the server logs

## 📊 Monitoring and Analytics

Check usage:
```bash
# Check health status
curl https://your-domain.com/health

# View the demo
curl https://your-domain.com/liff/demo
```

## 🎯 Future Ideas

Possible additions:
- **Drag-and-drop ordering**: reorder items
- **Templates**: frequently used order templates
- **Import/export**: CSV/Excel file support
- **Multiple languages**: internationalization support
- **Dark mode**: a better experience at night

---

🎉 You now have a powerful LIFF order editing system! Users can choose quick button edits or in-depth web editing to fit any situation.
