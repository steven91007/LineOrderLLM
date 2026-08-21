# Discord 訂單機器人設定

直接**私訊機器人**貼上聊天紀錄（或丟 `.txt` 檔），它會解析成訂單、顯示預覽，
按下按鈕才寫入 Google 試算表。另外提供 `/organize` 把總表依出貨日拆成日期分頁。

功能等同於原本的 `chat_import_gui.py`（本機網頁）和 `organize_by_date.py`（CLI），
差別是可以從手機操作。那兩個工具都保留，沒有被取代。

---

## 兩種用法

| | **私訊（建議）** | 指定頻道 |
|---|---|---|
| 需要開 MESSAGE CONTENT INTENT | **不用** | 要 |
| 誰看得到客戶資料 | 只有你 | 頻道成員 |
| 要設 `DISCORD_ORDER_CHANNEL_ID` | 不用 | 要 |

**私訊比較簡單也比較安全**，少一個最容易踩的設定，客戶的姓名電話地址也不會出現在頻道裡。

不管用哪一種，**都得先把機器人加進一個伺服器**——Discord 規定要和機器人有共同的伺服器
才能私訊它。伺服器只是張通行證，加完之後你可以完全不在頻道裡用。

---

## 一、建立 Discord 應用程式

1. 到 [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**
2. 左側 **Bot** → **Reset Token** → 複製 token（只會顯示一次）
3. 左側 **OAuth2 → URL Generator**：
   - Scopes 勾 **`bot`** 和 **`applications.commands`**
   - Bot Permissions 勾：View Channels、Send Messages、Embed Links、Attach Files、
     Read Message History、Add Reactions
   - 複製產生的網址，在瀏覽器打開，把機器人加進你的伺服器

> **只有要在頻道裡用才需要這一步**：Bot 頁面往下捲到 **Privileged Gateway Intents**
> → 開啟 **MESSAGE CONTENT INTENT**。
> 純私訊用法不用開，程式也不會去要求它。

## 二、取得你的使用者 ID

Discord → 使用者設定 → 進階 → 開啟**開發者模式**，然後右鍵自己的頭像 → **複製使用者 ID**。

（要在頻道用的話，順便右鍵那個頻道 → 複製頻道 ID。）

## 三、設定 `.env`

```bash
# 解析用（和現有的 LINE bot 共用）
OPENAI_API_KEY=sk-...
DSPY_MODEL=gpt-5.6-luna

# Google 試算表（和現有工具共用）
GOOGLE_SHEETS_ID=你的試算表 ID
GOOGLE_SHEETS_CREDENTIALS_PATH=credentials.json

# Discord
DISCORD_BOT_TOKEN=你的 bot token
DISCORD_AUTHORIZED_USERS=你的使用者 ID      # 逗號分隔多人
DISCORD_GUILD_ID=你的伺服器 ID              # 選填，設了斜線指令在該伺服器立即生效

# 只有想在頻道裡用才需要，留空＝只走私訊
DISCORD_ORDER_CHANNEL_ID=
```

`DISCORD_AUTHORIZED_USERS` **留空會直接拒絕啟動**，不會變成允許所有人。
這支機器人會寫進正式的訂單試算表，fail-open 等於讓任何人都能下單。
別人私訊機器人也沒用，不在名單裡就會被擋掉。

注意 `DISCORD_AUTHORIZED_USERS` 和 LINE 的 `AUTHORIZED_USERS` 是**兩個不同的變數**，
因為兩邊的使用者 ID 是不同的 ID 空間，混在一起會無法判斷某個 ID 是誰。

## 四、啟動

```bash
# 先檢查設定（不會連線），會告訴你目前是私訊模式還是頻道模式
uv run python discord_bot.py --check

# 啟動
uv run python discord_bot.py
```

---

## 怎麼用

### 匯入訂單

**私訊機器人**，直接貼上聊天紀錄，或把 LINE 匯出的 `.txt` 拖進去。

LINE 的匯出檔通常遠超過 Discord 的 2000 字訊息上限，所以檔案上傳是主要用法。
編碼會自動判斷（UTF-8-BOM／UTF-16／cp950／UTF-8），Windows 匯出的檔不用先轉檔。

機器人會回：

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

- **寫入可寫入的**：只寫沒有問題的訂單
- **含需確認**：連同被標記需人工確認的一起寫入。數字是「可寫入 + 需確認」的總和
- **已存在的訂單永遠不會被寫入**，按哪個按鈕都一樣。這是為了避免同一筆訂單重複下單；
  真的要重寫請直接編輯總表

訂單超過 10 筆時，明細只顯示前 10 筆，完整內容會以 `匯入預覽.txt` 附件送出。

### 不會觸發解析的訊息

每一則訊息都可能觸發一次數分鐘、要花錢的解析，所以有這些過濾：

| 情況 | 行為 |
|---|---|
| 機器人自己的訊息 | 忽略 |
| 未授權的使用者 | 只加上 🚫 反應 |
| 伺服器頻道，但不是指定的那個 | 完全忽略 |
| 以 `#` 開頭 | 忽略（方便你做註記） |
| 少於 20 個字 | 忽略 |
| 正在解析另一批 | 回覆「請等這批完成再貼」，不排隊 |

### 整理日期分頁

```
/organize                  # 用預設來源分頁「表單回覆 1」
/organize source:其他分頁   # 指定來源分頁
```

私訊裡也能用。會先顯示預覽（每個日期分頁的訂單數和出貨統計），確認後才寫入。
**要被清空的分頁會標成橘色並列出來**——日期分頁是總表的投影，每次執行都會整個重建，
所以這一步是破壞性的。

---

## 疑難排解

**私訊機器人沒反應**
→ 確認你和機器人有共同的伺服器（Discord 規定），以及你的 ID 有在
`DISCORD_AUTHORIZED_USERS` 裡。

**斜線指令 `/organize` 在私訊裡找不到**
→ 全域同步最多要等一小時才會出現，第一次啟動後請耐心等一下。

**在頻道貼文字沒反應，但丟 `.txt` 檔正常**
→ 這是 MESSAGE CONTENT INTENT 沒開的典型症狀（附件不受這個限制，文字受）。
到 Developer Portal → Bot → Privileged Gateway Intents 開啟它。私訊不受影響。

**啟動時報 PrivilegedIntentsRequired**
→ 你設了 `DISCORD_ORDER_CHANNEL_ID` 但沒在 Developer Portal 開啟 MESSAGE CONTENT INTENT。
要嘛去開啟，要嘛把 `DISCORD_ORDER_CHANNEL_ID` 清空改用私訊。

**啟動時說設定不完整**
→ 跑 `uv run python discord_bot.py --check`，它會列出缺哪些。

**寫入失敗，說欄位對不上**
→ Google 表單的題目被改過，總表標題列和程式預期的不一致。先核對總表再重試。

**寫入失敗，429 / Quota**
→ Google Sheets 每分鐘的寫入配額滿了，等一分鐘再重跑。日期分頁多的時候比較容易遇到。

**機器人重新啟動後，舊的預覽按鈕按不動**
→ 預覽只存在記憶體裡（裡面有客戶個資，刻意不落地），重啟就會失效。重新貼一次即可。

**解析卡住很久都沒結束**
→ 目前沒辦法中斷執行中的解析，只能重啟機器人。解析中的期間其他匯入會被擋下。

---

## 相關檔案

| 路徑 | 內容 |
|---|---|
| `discord_bot.py` | 進入點 |
| `src/handlers/discord_handler.py` | 訊息處理、併發控制、待確認狀態 |
| `src/handlers/discord_views.py` | 按鈕介面 |
| `src/handlers/discord_format.py` | embed／文字排版（純函式，可單測） |
| `tests/test_discord_format.py` | `uv run pytest` |

底層服務沒有任何改動，和以下工具共用同一套邏輯：

- `src/services/chat_log_importer.py` ← 也被 `chat_import_gui.py`、`import_chat_log.py` 使用
- `src/services/sheet_date_organizer.py` ← 也被 `organize_by_date.py` 使用
