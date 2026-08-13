# 用 Cloudflare Tunnel 取代 ngrok

ngrok 免費版每次重啟就換網址，得回 LINE 後台重設 webhook URL。Cloudflare Tunnel
給你固定網址、自動 HTTPS、不用開防火牆連接埠，而且免費。

## 前置條件

- **一個掛在 Cloudflare 的域名**（免費方案即可）。沒有域名就只能拿到隨機的
  `*.trycloudflare.com`，等於沒解決問題。域名在哪裡註冊都可以，只要 DNS 交給
  Cloudflare 管——見下面的「步驟零」。
- 應用程式跑在本機的 5001 埠（`app_with_liff.py`）。若改跑 `main.py` 則是 5000，
  下面所有 5001 都要跟著改。

## 步驟零：把 Gandi 的網域接到 Cloudflare

只是把 DNS 代管換成 Cloudflare，網域註冊仍留在 Gandi，不會產生費用。

**1. 在 Cloudflare 加入網站**

Cloudflare 儀表板 → **Add a domain** → **Connect a domain** → 輸入你的網域 →
方案選 **Free**。Cloudflare 會掃描現有的 DNS 記錄，接著給你**兩組名稱伺服器**，
長得像：

```
xxxx.ns.cloudflare.com
yyyy.ns.cloudflare.com
```

把這兩組抄下來。

**2. 在 Gandi 改名稱伺服器**

Gandi 管理後台 → 選擇網域 → 左側 **Nameservers**（名稱伺服器）→ 點 **Change**。

Gandi 預設用的是自家的 **Gandi LiveDNS**，要改成 **External**（外部），
然後把 Cloudflare 給的兩組填進去，儲存。

**3. 等待生效**

通常幾分鐘到幾小時，最長 24 小時。生效後 Cloudflare 會寄信通知，
儀表板上該網域的狀態會從 *Pending Nameserver Update* 變成 **Active**。

**必須等到 Active 才能往下做**——狀態還是 Pending 時，
下面的 `cloudflared tunnel login` 不會列出這個網域。

查詢目前生效的 NS：

```powershell
nslookup -type=NS 你的網域.com
```

## 一、安裝 cloudflared

**Windows**

```powershell
winget install --id Cloudflare.cloudflared
```

**Ubuntu / EC2**

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

裝完確認：

```powershell
cloudflared --version
```

## 二、登入並建立通道

登入會開瀏覽器要你選網域，**必須自己執行**（需要互動）：

```powershell
cloudflared tunnel login
```

成功後會在 `%USERPROFILE%\.cloudflared\` 產生 `cert.pem`。接著建立通道：

```powershell
cloudflared tunnel create lineorder
```

輸出會包含一組 **Tunnel ID**（UUID），以及憑證檔路徑
`%USERPROFILE%\.cloudflared\<TUNNEL_ID>.json`。兩者等一下都要填進設定檔。

## 三、設定 DNS

把子網域指向這個通道。`line` 可以換成你想要的名字：

```powershell
cloudflared tunnel route dns lineorder line.你的網域.com
```

這會自動在 Cloudflare 建一筆 CNAME，不需要手動去後台加。

## 四、寫設定檔

把 `cloudflared/config.example.yml` 複製到 `%USERPROFILE%\.cloudflared\config.yml`，
換掉 `<TUNNEL_ID>`、`<憑證檔路徑>`、`<你的網域>` 三處。

## 五、測試

先啟動應用：

```powershell
python app_with_liff.py
```

另開一個視窗跑通道：

```powershell
cloudflared tunnel run lineorder
```

確認健康檢查通得過（`app_with_liff.py:134` 的 `/health`）：

```powershell
curl https://line.你的網域.com/health
```

## 六、設定 LINE webhook

到 [LINE Developers Console](https://developers.line.biz/console/) → 你的 Channel →
Messaging API → Webhook URL 填：

```
https://line.你的網域.com/callback
```

按 **Verify** 確認回 200，並把 **Use webhook** 打開。

接著到 [LINE Official Account Manager](https://manager.line.biz/) →
設定 → 回應設定，確認 **Webhook 是啟用的**。這一步很常被漏掉——
切到聊天模式時若沒開 webhook，事件不會送出來。

## 七、設成常駐服務

上面是前景執行，關掉視窗就斷。要 24/7 常駐：

**Windows（跑在自己的電腦上）**

這是本專案目前採用的方式。有三件事都要做，少一件就會漏單。

**1. 把通道註冊成服務**（以系統管理員身分執行 PowerShell）

```powershell
cloudflared service install
```

**2. 讓 Flask 也開機自動啟動**

上一步只讓「通道」常駐，**Flask 應用本身還是會在關機後消失**。
用 NSSM 把它包成 Windows 服務：

```powershell
winget install NSSM.NSSM
nssm install LineOrderBot "E:\PythonProject\LineOrderLLM\.venv\Scripts\python.exe" "E:\PythonProject\LineOrderLLM\app_with_liff.py"
nssm set LineOrderBot AppDirectory "E:\PythonProject\LineOrderLLM"
nssm set LineOrderBot Start SERVICE_AUTO_START
nssm start LineOrderBot
```

**3. 關掉睡眠**

電腦睡眠時網路卡會斷電，通道跟著斷。訂單進來時沒人接，客人不會收到任何回應，
你也不會知道少了一筆。

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

螢幕可以照常關（`monitor-timeout-ac` 不用動），只要主機不進睡眠就行。

## 漏單風險與緩解

跑在自己的電腦上，停電、當機、Windows 自動更新重開機都會造成訂單漏收，
而且 **LINE 預設不會重送，你也不會收到任何通知**。至少做這兩件事：

**開啟 LINE 的 webhook 重送**

LINE Developers Console → 你的 Channel → Messaging API →
把 **Webhook redelivery** 開起來。這樣 LINE 在送不到時會重試，
短暫離線（重開機、網路閃斷）就不會直接掉單。

注意重送會造成**同一則訊息收到兩次**，所以 webhook 端必須能去重
（用 event 的 `webhookEventId` 判斷）。

**定期核對**

LINE Official Account Manager 的聊天視窗是完整的，
可以定期用它跟資料庫比對，確認沒有訊息漏接。

長期而言，若訂單量變大到漏一筆就有實際損失，還是應該搬到 EC2 那類
24 小時開機的機器上。屆時 Cloudflare Tunnel 可以直接沿用，不用重做。

**Ubuntu / EC2**

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

Flask 端建議另外寫一個 systemd unit，並改用 gunicorn 而非 Flask 開發伺服器。

## 常見問題

**`ERR_NGROK`-style 的 502 / 1033 錯誤**
通道通了但後端沒起來。先確認 `curl http://localhost:5001/health` 在本機通得過。

**LINE Verify 逾時**
LINE 對 webhook 的回應時間要求很嚴，逾時會重送導致重複訊息。webhook 應該
「收下、存檔、立刻回 200」，把 OpenAI 解析和 Google Sheets 寫入丟到背景做。
目前 `app_with_liff.py:118` 的 `handle_message` 是同步處理的，這部分需要改。

**通道會自己斷線**
設定檔裡的 `protocol: quic` 在某些網路環境會被擋，改成 `protocol: http2` 試試。
