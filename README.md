# LINE Bot Configuration

## Setup steps

### 1. Start the application and the ngrok tunnel

```bash
# Option 1: start with the script
./start_ngrok.sh

# Option 2: start them separately
# Terminal 1: start the Flask app
python main.py

# Terminal 2: start ngrok
ngrok http 5000
```

### 2. Set the LINE Bot Webhook URL

1. After starting ngrok, you will see output like this:
   ```
   Forwarding: https://xxxx-xx-xx-xx-xx.ngrok-free.app -> http://localhost:5000
   ```

2. Log in to the [LINE Developers Console](https://developers.line.biz/)

3. Select your Channel

4. Find Webhook settings under the Messaging API tab

5. Set the Webhook URL to:
   ```
   https://xxxx-xx-xx-xx-xx.ngrok-free.app/callback
   ```
   (replace xxxx-xx-xx-xx-xx with your ngrok URL)

6. Enable "Use webhook"

7. Click "Verify" to test the connection

### 3. Test the LINE Bot

1. Scan the QR code to add the Bot as a friend
2. Send a message to test the echo function

## Environment variables

Make sure the `.env` file contains the correct settings:

```
LINE_CHANNEL_ACCESS_TOKEN=your Channel Access Token
LINE_CHANNEL_SECRET=your Channel Secret
```

## Notes

- The free ngrok URL changes on every restart
- You then need to update the Webhook URL in the LINE Developers Console
- Consider a paid ngrok plan to get a fixed URL

## gitkb: git history knowledge base

`knowledge/` holds summary notes for every commit and every file change (each named by the sha256 of the summarized text). Use `uv run python -m gitkb search / show / history / log` to find out why code looks the way it does. After new commits, run `/gitkb` in Claude Code to update it. See `docs/agents/gitkb.md`.
