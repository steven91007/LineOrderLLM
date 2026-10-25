# Discord Order Bot Setup

**DM the bot** and paste a chat log (or drop in a `.txt` file). It parses it into orders, shows a preview,
and only writes to the Google spreadsheet when you press a button. It also provides `/organize`, which splits
the master sheet into per-date tabs by shipping date.

It does the same job as the existing `chat_import_gui.py` (local web page) and `organize_by_date.py` (CLI);
the difference is that you can run it from your phone. Both of those tools are still there and have not been replaced.

---

## Two Ways to Use It

| | **DM (recommended)** | Designated channel |
|---|---|---|
| Requires MESSAGE CONTENT INTENT | **No** | Yes |
| Who can see customer data | Only you | Channel members |
| Requires `DISCORD_ORDER_CHANNEL_ID` | No | Yes |

**DMs are simpler and safer**: you skip the setting people most often get wrong, and customers' names, phone numbers and addresses never show up in a channel.

Either way, **you must first add the bot to a server**. Discord requires you to share a server with a bot
before you can DM it. The server is just a pass; once the bot is added you never have to use it in a channel.

---

## 1. Create the Discord Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**
2. In the left sidebar, **Bot** → **Reset Token** → copy the token (it is shown only once)
3. In the left sidebar, **OAuth2 → URL Generator**:
   - Under Scopes, check **`bot`** and **`applications.commands`**
   - Under Bot Permissions, check: View Channels, Send Messages, Embed Links, Attach Files,
     Read Message History, Add Reactions
   - Copy the generated URL, open it in a browser, and add the bot to your server

> **Only needed if you want to use it in a channel**: on the Bot page, scroll down to **Privileged Gateway Intents**
> → enable **MESSAGE CONTENT INTENT**.
> For DM-only use you do not need it, and the program will not request it.

## 2. Get Your User ID

Discord → User Settings → Advanced → enable **Developer Mode**, then right-click your own avatar → **Copy User ID**.

(If you want to use a channel, also right-click that channel → Copy Channel ID.)

## 3. Configure `.env`

```bash
# For parsing (shared with the existing LINE bot)
OPENAI_API_KEY=sk-...
DSPY_MODEL=gpt-5.6-luna

# Google spreadsheet (shared with the existing tools)
GOOGLE_SHEETS_ID=your spreadsheet ID
GOOGLE_SHEETS_CREDENTIALS_PATH=credentials.json

# Discord
DISCORD_BOT_TOKEN=your bot token
DISCORD_AUTHORIZED_USERS=your user ID      # comma-separated for multiple people
DISCORD_GUILD_ID=your server ID              # optional; if set, slash commands take effect immediately in that server

# Only needed if you want to use a channel; leave empty = DMs only
DISCORD_ORDER_CHANNEL_ID=
```

If `DISCORD_AUTHORIZED_USERS` is **empty, the bot refuses to start**; it does not fall back to allowing everyone.
This bot writes to the real order spreadsheet, and failing open would let anyone place orders.
Other people DMing the bot gets them nowhere either: anyone not on the list is blocked.

Note that `DISCORD_AUTHORIZED_USERS` and LINE's `AUTHORIZED_USERS` are **two separate variables**,
because the two platforms' user IDs live in different ID spaces; mixing them would make it impossible to tell whose ID is whose.

## 4. Start It

```bash
# Check the configuration first (does not connect); tells you whether it is in DM mode or channel mode
uv run python discord_bot.py --check

# Start
uv run python discord_bot.py
```

---

## How to Use It

### Importing orders

**DM the bot** and paste the chat log directly, or drag in the `.txt` exported from LINE.

LINE export files are usually far over Discord's 2000-character message limit, so file upload is the main way to use it.
The encoding is detected automatically (UTF-8-BOM / UTF-16 / cp950 / UTF-8), so Windows exports do not need converting first.

The bot replies with something like the following (the bot's actual Chinese output; roughly: "Parsing… / Parse complete / Chat log import preview / 5 orders total / Status: 3 writable, 1 needs review, 1 already exists / The 1 existing order will not be written, even if you press 'include needs-review'… / (per-order details) / Please confirm which orders to write." and the buttons "Write writable (3)", "Include needs-review (4)", "Cancel"):

```
🤖 解析中…（chat-0821.txt（8,432 字元），模型 gpt-5.6-luna）已跑 30 秒
✅ 解析完成（47 秒）

┌─ 聊天紀錄匯入預覽 ────────────────
│ 共 5 筆訂單
│ 狀態  ✅ 可寫入 3　⚠️ 需確認 1　🔁 已存在 1
│ 已存在的 1 筆不會寫入
│   即使按「含需確認」也不會寫入…
└───────────────────────────────

（逐筆明細）

請確認要寫入哪些訂單。
[ 寫入可寫入的 (3) ] [ 含需確認 (4) ] [ 取消 ]
```

If a shipping date is **earlier than today** at import time, the order is also marked 「需確認」 ("needs review") with the reason
(usually the model miscalculated a relative date such as 「上週三」, "last Wednesday"). This only warns and does not block, so backfilling old orders still works.

- **寫入可寫入的 (Write writable)**: writes only the orders with no problems
- **含需確認 (Include needs-review)**: also writes the orders flagged for manual review. The number is the sum of "writable + needs review"
- **Orders that already exist are never written**, no matter which button you press. This prevents the same order from being placed twice;
  if you really need to rewrite one, edit the master sheet directly

When there are more than 10 orders, the details show only the first 10, and the full content is sent as an attachment named `匯入預覽.txt` ("import preview").

### Messages that do not trigger parsing

Every message could trigger a parse that takes several minutes and costs money, so these filters apply:

| Case | Behavior |
|---|---|
| The bot's own messages | Ignored |
| Unauthorized user | Only a 🚫 reaction is added |
| A server channel that is not the designated one | Completely ignored |
| Starts with `#` | Ignored (handy for leaving notes) |
| Fewer than 20 characters | Ignored |
| Another batch is currently being parsed | Replies 「請等這批完成再貼」 ("please wait for this batch to finish before pasting"); no queueing |

### Organizing date tabs

```
/organize                  # uses the default source tab 「表單回覆 1」 ("Form Responses 1")
/organize source:其他分頁   # specify a source tab (其他分頁 = "another tab")
```

This also works in DMs. It first shows a preview (the order count and shipping totals for each date tab) and only writes after you confirm.
**Tabs that will be cleared are marked in orange and listed**: the date tabs are a projection of the master sheet, and every unshipped tab
is fully rebuilt on each run, so this step is destructive.

**Tabs whose shipping date has already passed are locked automatically** (marked 🔒 in the preview):

- `/organize` no longer rebuilds them, so their contents stay as they were on shipping day
- Protection is added in Google Sheets so manual edits show a warning (using warningOnly, which does not lock anyone
  out, including the service account this program uses)
- Shipped tabs are also not treated as "leftovers" to be cleared

So even if someone later edits old orders in the master sheet, the list from shipping day will not change with them.

### Finding orders with the wrong shipping date

```
/offday                # list only today and later
/offday all:true       # also list dates already past (for audits)
/offday source:其他分頁 # specify a source tab
```

Shipping days are only Wednesday and Sunday. This command scans the whole master sheet and lists three kinds of problem orders,
together with their actual row numbers in the master sheet so you can jump straight there to fix them:

| Type (as shown by the bot) | Meaning |
|---|---|
| 非出貨日 (not a shipping day) | A date is filled in, but it is not a Wednesday or Sunday |
| 日期無法辨識 (date not recognized) | The date column is empty or contains something unparseable (cannot be placed in a date tab) |
| 出貨日早於填表時間 (shipping date before form submission time) | The shipping date had already passed when the form was filled in, so it must be a mistake |

「出貨日早於填表時間」 is **not affected by the `all` parameter** and is always listed: such rows are necessarily earlier than today too,
so if they were filtered out you would never see them by default, yet they are data-entry errors rather than scheduling problems. The same row may appear in
both sections; those are two different problems.

It is read-only, so you can run it as many times as you like without touching the spreadsheet.

Sample output (the bot's Chinese output; e.g. 「第2列」 = "row 2", 「原文：下週都可以」 = "original text: any day next week works"):

```
⚠️ 出貨日需要處理的訂單
來源分頁：表單回覆 1
掃描範圍：今天以後，共 6 筆訂單
非出貨日 3 筆　日期無法辨識 1 筆

【2026-08-25（星期二）　1 筆】
第2列　王小明　0912-345-678　20A 一盒 $1,150

【2026-08-28（星期五）　2 筆】
第3列　李小華　0922-111-222　20A 一盒 $1,150
第4列　張先生　0933-444-555　20A 一盒 $1,150

【❓ 日期無法辨識　1 筆】
第6列　陳大寶　原文：下週都可以
```

Shipping days are defined in `src/utils/shipping_days.py`. If the rules change, edit that file;
the import-time check and this command both pick up the change.

---

## Troubleshooting

**The bot does not respond to DMs**
→ Make sure you share a server with the bot (a Discord requirement) and that your ID is in
`DISCORD_AUTHORIZED_USERS`.

**The `/organize` slash command does not show up in DMs**
→ Global sync can take up to an hour to appear; be patient after the first startup.

**Pasting text in a channel does nothing, but dropping in a `.txt` works**
→ This is the classic symptom of MESSAGE CONTENT INTENT not being enabled (attachments are not subject to it; text is).
Go to Developer Portal → Bot → Privileged Gateway Intents and enable it. DMs are not affected.

**PrivilegedIntentsRequired at startup**
→ You set `DISCORD_ORDER_CHANNEL_ID` but did not enable MESSAGE CONTENT INTENT in the Developer Portal.
Either enable it, or clear `DISCORD_ORDER_CHANNEL_ID` and use DMs instead.

**Startup says the configuration is incomplete**
→ Run `uv run python discord_bot.py --check`; it lists what is missing.

**Write fails, saying the columns do not match**
→ The Google Form's questions were changed, so the master sheet's header row no longer matches what the program expects. Check the master sheet, then retry.

**Write fails with 429 / Quota**
→ The Google Sheets per-minute write quota is used up; wait a minute and run it again. This is more likely when there are many date tabs.

**After the bot restarts, old preview buttons do nothing**
→ Previews are kept only in memory (they contain customer personal data and are deliberately never written to disk), so a restart invalidates them. Just paste again.

**Parsing has been stuck for a long time**
→ There is currently no way to interrupt a running parse; you can only restart the bot. While a parse is running, other imports are blocked.

---

## Related Files

| Path | Contents |
|---|---|
| `discord_bot.py` | Entry point |
| `src/handlers/discord_handler.py` | Message handling, concurrency control, pending-confirmation state |
| `src/handlers/discord_views.py` | Button UI |
| `src/handlers/discord_format.py` | Embed / text layout (pure functions, unit-testable) |
| `src/services/offday_orders.py` | Scan logic for `/offday` (read-only) |
| `src/utils/shipping_days.py` | Single source of truth for shipping days |
| `tests/test_discord_format.py` | `uv run pytest` |

The underlying services were not changed at all; they share the same logic with these tools:

- `src/services/chat_log_importer.py` ← also used by `chat_import_gui.py` and `import_chat_log.py`
- `src/services/sheet_date_organizer.py` ← also used by `organize_by_date.py`
