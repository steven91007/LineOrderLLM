# LINE Bot Smart Order Processing System Setup Guide v2.0

## Overview

This is a smart LINE Bot order processing system with the following features:

1. **Message intake and access control**: private order processing, available only to authorized users
2. **Smart parsing**: uses OpenAI GPT-4 to automatically extract single or multiple orders
3. **Flexible data structure**: sender information is optional, and multiple orders are supported
4. **One-by-one confirmation flow**: multiple orders can be confirmed one at a time or all at once
5. **Data integration**: order data is written to Google Sheets automatically

## ✨ What's New

### 🔹 Optional sender information
- Sender name and phone are now optional fields
- When not provided, the system shows 「未提供」 ("not provided")

### 🔹 Multiple order support
- Handles up to 5 orders at a time
- Automatically detects single vs. multiple orders
- Supports one-by-one or bulk confirmation

### 🔹 Smart error handling
- Suggests entering orders one at a time when multi-order parsing fails
- Provides clear error messages and solutions

## Setup Steps

### 1. Prepare the environment

```bash
# Install dependencies
uv sync

# Copy the environment variable template
cp .env.example .env
```

### 2. LINE Bot setup

1. Go to the [LINE Developers Console](https://developers.line.biz/)
2. Create a new Provider and Channel
3. Get the following values and put them in `.env`:
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `LINE_CHANNEL_SECRET`

### 3. OpenAI setup

1. Go to the [OpenAI Platform](https://platform.openai.com/)
2. Create an API key
3. Put the API key in `OPENAI_API_KEY` in `.env`

### 4. Google Sheets setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sheets API
4. Create a service account and download the JSON credentials file
5. Rename the credentials file to `credentials.json` and place it in the project root
6. Create a Google Sheet and get its Sheet ID
7. Put the Sheet ID in `GOOGLE_SHEET_ID` in `.env`
8. Give the service account's email edit access to the Google Sheet

### 5. Authorized users

1. Get the LINE user IDs of the people who need this feature
2. Put the user IDs in `AUTHORIZED_USERS` in `.env` (comma-separated for multiple IDs)
3. Or set it to `*` to allow all users (not recommended for production)

### 6. Start the app

```bash
# Development
python main.py

# Production
gunicorn main:app --bind 0.0.0.0:5000
```

## Usage

The commands, button labels and bot messages are in Chinese and are quoted here as they appear.

### Single order flow
1. Send `#訂單` or `#order` to the bot in LINE
2. Tap the 「開始建立訂單」 ("Start creating order") button
3. Enter a single order
4. The system parses it and shows the result for confirmation
5. Tap 「確認訂單」 ("Confirm order") to finish

### Multiple order flow
1. Enter a message containing several orders (up to 5)
2. The system shows 「發現 X 份訂單！」 ("Found X orders!")
3. Choose 「逐一確認」 ("Confirm one by one") or 「全部確認」 ("Confirm all")
4. When confirming one by one, you can page through each order's details
5. After confirmation, all orders are created automatically

### When parsing fails
- When multi-order parsing fails, the system suggests entering orders one at a time
- You can choose 「單筆輸入」 ("Single entry") or 「重新嘗試」 ("Retry")

## Order Information Format

### Required fields
- Receiver name and phone
- Items and quantities
- Shipping address

### Optional fields
- Sender name and phone (shows 「未提供」 "not provided" when missing)
- Expected shipping date

## Multiple Order Example

Sample input as a user would type it (roughly: "Order 1: send to 李大華 0923-456-789, address Xinyi District, Taipei..., item A x2", and so on):

```
訂單1: 寄給李大華 0923-456-789，地址台北市信義區...，商品A x2
訂單2: 寄給陳小美 0934-567-890，地址新北市...，商品B x1  
訂單3: 寄給王大明 0945-678-901，地址台中市...，商品C x3
```

## Troubleshooting

### Common problems

1. **The bot does not respond**
   - Make sure LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET are correct
   - Check that the webhook URL is set correctly

2. **OpenAI parsing problems**
   - Make sure OPENAI_API_KEY is valid and has enough quota
   - If multi-order parsing fails, try entering orders one at a time
   - Check whether the number of orders exceeds the limit of 5

3. **Google Sheets write failures**
   - Make sure credentials.json exists and is in the right format
   - Check that the service account has edit access to the Google Sheet
   - Make sure GOOGLE_SHEET_ID is correct

4. **Multi-order processing problems**
   - If parsing fails often, enter orders one at a time instead
   - Check that the order format is clear (each order needs a receiver, items and an address)

### Viewing logs

The app writes logs to the console; when something goes wrong, check them for the specific error message.

### Performance tips

1. **Prefer single entry**: to keep parsing accurate, entering one order at a time is recommended
2. **Standardize the format**: create a fixed order template for users to follow
3. **Batch processing**: for large numbers of orders, process them in batches to avoid timeouts

## Security Notes

1. Do not commit the `.env` file to version control
2. Rotate API keys regularly
3. Limit the set of authorized users (avoid using `*` to allow everyone)
4. Review Google Sheets access permissions regularly
5. Monitor OpenAI API usage (multi-order parsing uses more tokens)

## Changelog

### v2.0
- ✅ Sender information made optional
- ✅ Multiple order support (up to 5)
- ✅ New one-by-one confirmation flow
- ✅ Improved error handling
- ✅ Improved user flow

### v1.0
- ✅ Basic order processing
- ✅ OpenAI smart parsing
- ✅ Google Sheets integration
