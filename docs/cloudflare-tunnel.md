# Replacing ngrok with Cloudflare Tunnel

The free ngrok plan changes its URL on every restart, so you have to go back to the LINE console and reset the webhook URL. Cloudflare Tunnel
gives you a fixed URL and automatic HTTPS, needs no open firewall ports, and is free.

## Prerequisites

- **A domain on Cloudflare** (the free plan is fine). Without a domain you only get a random
  `*.trycloudflare.com`, which doesn't solve the problem. The domain can be registered anywhere, as long as its DNS is managed by
  Cloudflare — see "Step zero" below.
- The app runs locally on port 5001 (`app_with_liff.py`). If you run `main.py` instead, it's 5000,
  and every 5001 below must change accordingly.

## Step zero: connect the Gandi domain to Cloudflare

This only moves DNS hosting to Cloudflare; the domain registration stays at Gandi, and there's no cost.

**1. Add the site in Cloudflare**

Cloudflare dashboard → **Add a domain** → **Connect a domain** → enter your domain →
choose the **Free** plan. Cloudflare scans the existing DNS records, then gives you **two name servers**,
which look like:

```
xxxx.ns.cloudflare.com
yyyy.ns.cloudflare.com
```

Write these two down.

**2. Change the name servers at Gandi**

Gandi admin panel → select the domain → **Nameservers** on the left → click **Change**.

Gandi uses its own **Gandi LiveDNS** by default; change it to **External**,
then enter the two name servers from Cloudflare and save.

**3. Wait for it to take effect**

Usually a few minutes to a few hours, at most 24 hours. Once it takes effect Cloudflare sends an email,
and the domain's status on the dashboard changes from *Pending Nameserver Update* to **Active**.

**You must wait until it's Active before continuing** — while the status is still Pending,
`cloudflared tunnel login` below won't list this domain.

Check the currently effective NS:

```powershell
nslookup -type=NS your-domain.com
```

## 1. Install cloudflared

**Windows**

```powershell
winget install --id Cloudflare.cloudflared
```

**Ubuntu / EC2**

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb
```

Verify the install:

```powershell
cloudflared --version
```

## 2. Log in and create the tunnel

Login opens a browser asking you to pick a domain, so **you must run it yourself** (it's interactive):

```powershell
cloudflared tunnel login
```

On success it creates `cert.pem` in `%USERPROFILE%\.cloudflared\`. Then create the tunnel:

```powershell
cloudflared tunnel create lineorder
```

The output includes a **Tunnel ID** (UUID) and the credentials file path
`%USERPROFILE%\.cloudflared\<TUNNEL_ID>.json`. Both go into the config file shortly.

## 3. Configure DNS

Point a subdomain at the tunnel. `line` can be any name you like:

```powershell
cloudflared tunnel route dns lineorder line.your-domain.com
```

This automatically creates a CNAME record in Cloudflare; no need to add it manually in the dashboard.

## 4. Write the config file

Copy `cloudflared/config.example.yml` to `%USERPROFILE%\.cloudflared\config.yml`,
and replace the three placeholders `<TUNNEL_ID>`, `<CREDENTIALS_DIR>`, and `<YOUR_DOMAIN>`.

## 5. Test

Start the app first:

```powershell
python app_with_liff.py
```

Run the tunnel in another window:

```powershell
cloudflared tunnel run lineorder
```

Confirm the health check passes (`/health` at `app_with_liff.py:134`):

```powershell
curl https://line.your-domain.com/health
```

## 6. Configure the LINE webhook

Go to the [LINE Developers Console](https://developers.line.biz/console/) → your Channel →
Messaging API → set the Webhook URL to:

```
https://line.your-domain.com/callback
```

Click **Verify** to confirm it returns 200, and turn on **Use webhook**.

Then go to [LINE Official Account Manager](https://manager.line.biz/) →
Settings → Response settings, and confirm **Webhook is enabled**. This step is often missed —
if the webhook isn't on when you switch to chat mode, events won't be sent.

## 7. Run as a persistent service

The above runs in the foreground; closing the window drops it. To run 24/7:

**Windows (running on your own computer)**

This is the approach this project currently uses. All three steps are required; skip one and you'll miss orders.

**1. Register the tunnel as a service** (run PowerShell as Administrator)

```powershell
cloudflared service install
```

**2. Make Flask start at boot too**

The previous step only keeps the *tunnel* running; **the Flask app itself still disappears after a shutdown**.
Wrap it as a Windows service with NSSM:

```powershell
winget install NSSM.NSSM
nssm install LineOrderBot "E:\PythonProject\LineOrderLLM\.venv\Scripts\python.exe" "E:\PythonProject\LineOrderLLM\app_with_liff.py"
nssm set LineOrderBot AppDirectory "E:\PythonProject\LineOrderLLM"
nssm set LineOrderBot Start SERVICE_AUTO_START
nssm start LineOrderBot
```

**3. Disable sleep**

When the computer sleeps, the network adapter loses power and the tunnel drops. If an order comes in with nobody listening, the customer gets no response,
and you won't know an order was missed.

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
```

The screen can still turn off as usual (leave `monitor-timeout-ac` alone); the machine just must not go to sleep.

## Missed-order risk and mitigation

Running on your own computer, power outages, crashes, and Windows Update reboots will all cause missed orders,
and **LINE does not redeliver by default, nor will you get any notification**. At minimum, do these two things:

**Enable LINE webhook redelivery**

LINE Developers Console → your Channel → Messaging API →
turn on **Webhook redelivery**. LINE then retries when delivery fails,
so brief outages (reboots, network blips) won't drop orders outright.

Note that redelivery means **the same message can arrive twice**, so the webhook side must deduplicate
(using the event's `webhookEventId`).

**Reconcile regularly**

The chat window in LINE Official Account Manager is complete,
so compare it against the database regularly to confirm no messages were missed.

Long term, if order volume grows to the point where one missed order means real loss, you should move to a machine
that's on 24 hours a day, like EC2. Cloudflare Tunnel can be reused as-is then, with no rework.

**Ubuntu / EC2**

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

For the Flask side, write a separate systemd unit and use gunicorn instead of the Flask dev server.

## FAQ

**`ERR_NGROK`-style 502 / 1033 errors**
The tunnel is up but the backend isn't running. First confirm `curl http://localhost:5001/health` works locally.

**LINE Verify times out**
LINE is strict about webhook response time; timeouts trigger redelivery and duplicate messages. The webhook should
"accept, store, return 200 immediately" and push OpenAI parsing and Google Sheets writes to the background.
Currently `handle_message` at `app_with_liff.py:118` is synchronous, and this needs to change.

**The tunnel disconnects on its own**
`protocol: quic` in the config file is blocked in some network environments; try `protocol: http2` instead.
