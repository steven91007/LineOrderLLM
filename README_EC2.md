# 直接使用 EC2 IP 的限制

## 問題：LINE 要求 HTTPS

LINE webhook **必須使用 HTTPS**，但是：

1. **自簽名憑證不被 LINE 接受**
   - LINE 會驗證 SSL 憑證的有效性
   - 自簽名憑證會被拒絕

2. **Let's Encrypt 需要域名**
   - 無法為純 IP 地址申請 Let's Encrypt 憑證
   - 需要有域名才能申請

## 解決方案

### 方案 1：使用 ngrok（最簡單）
```bash
ngrok http 5001
```
- 自動提供 HTTPS
- 不需要域名或憑證
- 適合開發測試

### 方案 2：購買域名 + Let's Encrypt
1. 購買域名（如：mybot.com）
2. 將域名指向 EC2 IP：35.78.109.166
3. 使用 certbot 申請免費 SSL：
   ```bash
   sudo apt-get install certbot
   sudo certbot certonly --standalone -d mybot.com
   ```

### 方案 3：使用 AWS 服務
- 使用 Application Load Balancer (ALB) + AWS Certificate Manager
- 使用 CloudFront 分發
- 但這些會產生額外費用

## EC2 安全群組設定

確保您的 EC2 安全群組允許：
- 入站規則：HTTPS (443) 或您設定的 port (5001)
- 來源：0.0.0.0/0（允許所有 IP）

## 結論

雖然 EC2 有公開 IP，但因為 LINE 的 HTTPS 要求，您仍需要：
- 使用 ngrok 或類似服務（最簡單）
- 或購買域名並設定真實的 SSL 憑證