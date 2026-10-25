# Limitations of Using the EC2 IP Directly

## Problem: LINE requires HTTPS

LINE webhooks **must use HTTPS**, but:

1. **LINE does not accept self-signed certificates**
   - LINE validates the SSL certificate
   - Self-signed certificates are rejected

2. **Let's Encrypt requires a domain name**
   - You cannot get a Let's Encrypt certificate for a bare IP address
   - You need a domain name to apply

## Solutions

### Option 1: Use ngrok (simplest)
```bash
ngrok http 5001
```
- Provides HTTPS automatically
- No domain or certificate needed
- Good for development and testing

### Option 2: Buy a domain + Let's Encrypt
1. Buy a domain (e.g. mybot.com)
2. Point the domain at the EC2 IP: 35.78.109.166
3. Use certbot to get a free SSL certificate:
   ```bash
   sudo apt-get install certbot
   sudo certbot certonly --standalone -d mybot.com
   ```

### Option 3: Use AWS services
- Use an Application Load Balancer (ALB) + AWS Certificate Manager
- Use a CloudFront distribution
- These incur extra cost, though

## EC2 security group settings

Make sure your EC2 security group allows:
- Inbound rule: HTTPS (443) or the port you configured (5001)
- Source: 0.0.0.0/0 (allow all IPs)

## Conclusion

Although EC2 has a public IP, because of LINE's HTTPS requirement you still need to either:
- Use ngrok or a similar service (simplest)
- Or buy a domain and set up a real SSL certificate
