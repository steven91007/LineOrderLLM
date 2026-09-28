# gitkb：git 歷史知識庫

`knowledge/` 底下是每個 commit 的知識筆記：每個 commit 一份 `knowledge/commits/<sha256>.md`，commit 裡的每個檔案變更一份 `knowledge/changes/<sha256>.md`。檔名是「被摘要的那段標準化文字」（commit 標頭 + diff）的 sha256，所以筆記本身就能證明它描述的是哪段變更。`knowledge/index.db` 是 SQLite 索引（commit、檔案、筆記之間的對應，加上 FTS5 全文搜尋），**不進版控**、隨時可從 md 重建。

程式碼在 `gitkb/`，與 [Jobseekers](https://github.com/steven91007/Jobseekers-) 的 `gitkb/` 是同一份；[jobseekers-mcp](https://github.com/steven91007/jobseekers-mcp) 的 `gitkb_*` 工具把 `GITKB_REPO` 指到這個 repo 就能直接查。

## 改程式之前先查

要改某段程式之前，先看它為什麼長這樣：

```bash
uv run python -m gitkb history src/utils/sheet_date_organizer.py   # 某個檔案的所有變更
uv run python -m gitkb search "雙雙對對"                            # 全文搜尋摘要（FTS5 語法）
uv run python -m gitkb show 1e454fe                                 # 用 git sha（可縮寫）或筆記 sha256 看筆記
uv run python -m gitkb log                                          # 已索引的 commit
```

剛 clone 下來沒有 `index.db` 時，先 `uv run python -m gitkb rebuild-index` 從 md 重建。

## 新 commit 之後更新知識庫

摘要由 Claude Code 在對話中撰寫，不呼叫任何 LLM API：

```bash
uv run python -m gitkb pending        # 匯出還沒摘要的 commit 到 knowledge/pending.json
#  -> 在 Claude Code 裡輸入 /gitkb，它會讀 pending.json、寫 knowledge/summaries.json
uv run python -m gitkb import knowledge/summaries.json   # 產生筆記並建索引
```

`knowledge/pending.json`、`knowledge/summaries.json` 是暫存檔，已在 `.gitignore`。`build --dry-run` 會先寫出佔位筆記（檔名與正式筆記相同），之後 `import` 會原地覆蓋。

## 規則

- 不要手改 `knowledge/commits/`、`knowledge/changes/` 底下的檔案；檔名是輸入的 hash，importer 會重新產生。
- `import` 若警告 hash recipe 改變（diff 旗標、大小上限或 `GITKB_EXCLUDE_GLOBS` 變了），先停下來問人，不要硬 import。
- 摘要用英文寫，不得把客戶個資（姓名、電話、地址、匯款末五碼）或金鑰從 diff 抄進筆記。
- 改了 `gitkb/` 的程式要跑 `uv run python tests/test_gitkb.py`。
