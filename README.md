# LineOrderLLM

用 LLM 解析 LINE 聊天紀錄，自動整理成訂單寫進 Google 試算表。

目前**只用 Discord bot** 這個介面（LINE Bot 的 webhook 相關程式碼還在，但沒有部署使用）。

## 快速開始

1. 依照 [`DISCORD_SETUP.md`](DISCORD_SETUP.md) 設定 Discord 應用程式、取得 token、填好 `.env`
2. 本機測試：

   ```bash
   uv run python discord_bot.py --check   # 檢查設定
   uv run python discord_bot.py           # 啟動
   ```

3. 私訊機器人貼上聊天紀錄或丟 `.txt` 檔，就會解析成訂單，確認後寫入 Google 試算表

## 部署與 CI/CD

Discord bot 常駐在 GCE VM 上，push 到 `master` 會自動測試並部署，
細節見 [`docs/deploy-gcp.md`](docs/deploy-gcp.md)。

## 開發

```bash
uv sync           # 安裝依賴
uv run pytest     # 跑測試
```

其他文件：

| 文件 | 內容 |
|---|---|
| [`DISCORD_SETUP.md`](DISCORD_SETUP.md) | Discord bot 設定與使用說明 |
| [`docs/deploy-gcp.md`](docs/deploy-gcp.md) | 部署到 GCE + GitHub Actions CI/CD |
| [`CONTEXT.md`](CONTEXT.md) | 專案背景與領域知識 |
| [`CLAUDE.md`](CLAUDE.md) | 技術方針與開發記錄 |
