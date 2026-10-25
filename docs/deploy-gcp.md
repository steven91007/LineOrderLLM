# Deploying the Discord bot to GCE + GitHub Actions CI/CD

A `git push` to `master` automatically runs `pytest` first; only if it passes does it SSH into the VM, pull the latest code,
and restart the `discord-order-bot` systemd service.

Related files:

| Path | Contents |
|---|---|
| `.github/workflows/deploy.yml` | CI/CD workflow: test → deploy |
| `deploy/discord-order-bot.service` | systemd unit template; copy it to the VM and replace the user name |

---

## 1. One-time setup on the VM

Run all of the following on the VM (`gcloud compute ssh`, or browser SSH from the Console).

**1. Install uv and git**

```bash
sudo apt-get update && sudo apt-get install -y git
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

**2. Clone the project**

```bash
cd ~
git clone https://github.com/steven91007/LineOrderLLM.git
cd LineOrderLLM
uv sync
```

**3. Upload `.env` and the Google service account JSON**

`.gitignore` keeps these two files out of version control, so copy them up manually (with `scp`, or paste them directly on the VM):

```bash
scp .env credentials.json your-vm-user@VM_EXTERNAL_IP:~/LineOrderLLM/
```

Fill in `.env` following the "3. Configure `.env`" section of `DISCORD_SETUP.md`.

**4. Install the systemd service**

```bash
sudo cp ~/LineOrderLLM/deploy/discord-order-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/discord-order-bot.service   # Replace YOUR_VM_USER with the actual account
sudo systemctl daemon-reload
sudo systemctl enable --now discord-order-bot
sudo journalctl -u discord-order-bot -f    # Confirm it starts normally; Ctrl+C to exit
```

---

## 2. Letting GitHub Actions SSH into the VM

**1. Generate a dedicated deploy key (on your own machine; don't use your everyday private key)**

```bash
ssh-keygen -t ed25519 -f deploy_key -N "" -C "github-actions-deploy"
```

This produces `deploy_key` (private key) and `deploy_key.pub` (public key).

**2. Add the public key to the VM**

GCP Console → Compute Engine → the VM → Edit → **SSH Keys** → Add item,
and paste the contents of `deploy_key.pub`. GCP automatically creates the matching user account on the VM.

(Alternatively, append the public key to `~/.ssh/authorized_keys` on the VM; same effect.)

**3. Make sure the firewall allows SSH**

The GCP default network usually already has `default-allow-ssh` (allows tcp:22 from 0.0.0.0/0).
If not: VPC network → Firewall → Create firewall rule, allowing tcp:22.
The simple setup relies on the SSH key to keep people out, with no source-IP restriction (GitHub Actions runner IPs aren't fixed).

**4. Configure Secrets in the GitHub repo**

Settings → Secrets and variables → Actions → New repository secret, and add three:

| Secret name | Value |
|---|---|
| `GCP_VM_HOST` | The VM's external IP |
| `GCP_VM_USER` | The user name GCP generated in step 2 (or one you set yourself) |
| `GCP_VM_SSH_KEY` | The full contents of the `deploy_key` private key |

---

## 3. Testing

Change a line of code, push to master, and check the **Actions** tab of the GitHub repo to see whether the workflow ran;
`deploy` only runs after `test` passes. On the VM run:

```bash
sudo journalctl -u discord-order-bot -f
```

Confirm the restart time matches the push time.

## Troubleshooting

**`Permission denied (publickey)`**
→ The public key wasn't added correctly, or `GCP_VM_USER` doesn't match the user name tied to the public key (GCP uses the last part of the public key comment
as the user name — the string you passed to `ssh-keygen -C`).

**Deploy succeeds but the bot doesn't restart**
→ First confirm `GCP_VM_USER` has sudo rights to run `systemctl restart` without a password
(users created by GCP are in sudoers by default, passwordless).

**`git pull` hangs asking for credentials**
→ This only happens if the VM cloned a private repo over HTTPS; if this repo is public you won't hit it.
If it's private, switch to a deploy key or set up authentication with `gh auth`.
