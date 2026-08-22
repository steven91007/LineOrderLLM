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
