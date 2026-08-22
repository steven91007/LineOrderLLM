# 部署 Discord bot 到 GCE + GitHub Actions CI/CD

`git push` 到 `master` 會自動：先跑 `pytest`，過了才 SSH 進 VM 拉最新程式碼、
重啟 `discord-order-bot` 這個 systemd service。

對應的檔案：

| 路徑 | 內容 |
|---|---|
| `.github/workflows/deploy.yml` | CI/CD workflow：test → deploy |
| `deploy/discord-order-bot.service` | systemd unit 範本，要複製到 VM 上並替換使用者名稱 |

---

## 一、VM 上的一次性設定

以下都在 VM 上執行（`gcloud compute ssh` 或直接在 Console 用瀏覽器 SSH）。

**1. 安裝 uv 和 git**

```bash
sudo apt-get update && sudo apt-get install -y git
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

**2. clone 專案**

```bash
cd ~
git clone https://github.com/steven91007/LineOrderLLM.git
cd LineOrderLLM
uv sync
```

**3. 放上 `.env` 和 Google 服務帳號 JSON**

這兩個檔案 `.gitignore` 擋著不會進版控，要手動搬上去（用 `scp` 或直接在 VM 上貼）：

```bash
scp .env credentials.json your-vm-user@VM_EXTERNAL_IP:~/LineOrderLLM/
```

`.env` 內容照 `DISCORD_SETUP.md` 的「三、設定 `.env`」那節填。

**4. 裝 systemd service**

```bash
sudo cp ~/LineOrderLLM/deploy/discord-order-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/discord-order-bot.service   # 把 YOUR_VM_USER 換成實際帳號
sudo systemctl daemon-reload
sudo systemctl enable --now discord-order-bot
sudo journalctl -u discord-order-bot -f    # 確認正常啟動，Ctrl+C 離開
```

**5.（選填）開啟 LINE 客戶訊息即時推播，需要再裝 Cloudflare Tunnel**

這個功能讓 LINE 官方帳號收到客戶訊息時即時解析、私訊到 Discord 確認，
細節見 `DISCORD_SETUP.md` 的「LINE 客戶訊息即時轉推播」。webhook 是跟
discord bot 同一個行程、同一個 port（`config.PORT`，預設 5000），要讓 LINE
連得到，照 `docs/cloudflare-tunnel.md` 裝 `cloudflared`，步驟跟 EC2 完全一樣
（那份文件本來就是為這種常駐主機寫的）：

```bash
# 在 VM 上
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
sudo cloudflared service install   # 這步之前要先在本機做完 tunnel login / create / route dns
sudo systemctl enable --now cloudflared
```

`cloudflared tunnel login` / `create` / `route dns` 這幾步需要互動登入，
在自己電腦上做（見 `docs/cloudflare-tunnel.md` 步驟二、三），VM 上只需要
`cloudflared/config.yml`（複製 `cloudflared/config.example.yml` 改好）和
上面這幾行安裝／啟動指令。

`.env` 記得補上 `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`、
`DISCORD_LINE_NOTIFY_USER_ID`。裝好後到 LINE Developers Console 把 Webhook URL
設成 `https://你的網域/callback`，按 Verify 應該要回 200。

---

## 二、讓 GitHub Actions 能 SSH 進 VM

**1. 產生一組專用的 deploy key（在自己電腦上，不要用你平常的私鑰）**

```bash
ssh-keygen -t ed25519 -f deploy_key -N "" -C "github-actions-deploy"
```

會產生 `deploy_key`（私鑰）和 `deploy_key.pub`（公鑰）。

**2. 把公鑰加到 VM**

GCP Console → Compute Engine → 該 VM → Edit → **SSH Keys** → Add item，
貼上 `deploy_key.pub` 的內容。GCP 會自動在 VM 上建對應的使用者帳號。

（或者直接把公鑰內容 append 進 VM 上的 `~/.ssh/authorized_keys`，效果一樣。）

**3. 確認防火牆允許 SSH**

GCP 預設網路通常已經有 `default-allow-ssh`（允許 0.0.0.0/0 的 tcp:22）。
沒有的話：VPC network → Firewall → Create firewall rule，允許 tcp:22。
簡單版本靠 SSH key 擋人，不用額外限制來源 IP（GitHub Actions runner 的 IP 不固定）。

**4. 到 GitHub repo 設定 Secrets**

Settings → Secrets and variables → Actions → New repository secret，新增三個：

| Secret 名稱 | 值 |
|---|---|
| `GCP_VM_HOST` | VM 的外部 IP |
| `GCP_VM_USER` | 步驟 2 裡 GCP 產生（或你自己設）的使用者名稱 |
| `GCP_VM_SSH_KEY` | `deploy_key` 私鑰的完整內容 |

---

## 三、測試

改一行程式碼、push 到 master，去 GitHub repo 的 **Actions** tab 看 workflow 有沒有跑過，
`test` 過了才會進 `deploy`。VM 上跑：

```bash
sudo journalctl -u discord-order-bot -f
```

確認重啟時間點跟 push 的時間對得上。

## 疑難排解

**`Permission denied (publickey)`**
→ 公鑰沒加對，或 `GCP_VM_USER` 跟公鑰對應的使用者名稱不一致（GCP 用公鑰 comment
的最後一段當使用者名稱，用 `ssh-keygen -C` 指定的那串）。

**deploy 成功但 bot 沒重啟**
→ 先確認 `GCP_VM_USER` 有 sudo 權限可以 `systemctl restart`，且不用密碼
（GCP 建立的使用者預設在 sudoers，免密碼）。

**`git pull` 卡住問帳密**
→ VM 上用 HTTPS clone 私有 repo才會這樣；這個 repo 是公開的話不會遇到，
私有的話要改用 deploy key 或 `gh auth` 設定好認證。
