# 🔄 LIFF 登入與轉址流程圖 (OAuth2 State 方案)

## 📋 完整流程圖

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           🚀 LIFF 登入與轉址完整流程                          │
│                        (使用 OAuth2 State 參數攜帶 Session)                  │
└─────────────────────────────────────────────────────────────────────────────┘

👤 用戶在 LINE 中輸入 "#訂單"
           │
           ▼
📱 OrderHandler 處理訂單解析
           │
           ▼
🏗️ 建立 LIFF Session
   Session ID: "abc123-def456-789"
           │
           ▼
🌐 生成 LIFF URL (後端 get_liff_url)
   ┌─────────────────────────────────────────────────────────────┐
   │ https://liff.line.me/2007889032-OolKDrp3?                   │
   │   liffRedirectUri=https://your-domain.com/liff/edit&        │
   │   sessionId=abc123-def456-789                               │
   └─────────────────────────────────────────────────────────────┘
           │
           ▼
📨 發送 FlexMessage 給用戶
   包含 "網頁編輯" 按鈕 → LIFF URL
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              📱 用戶點擊按鈕                                 │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
🌐 LINE 開啟 LIFF URL
   當前 URL: https://liff.line.me/2007889032-OolKDrp3?...&sessionId=abc123-def456-789
           │
           ▼
🔄 LIFF 前端初始化
   ┌─────────────────────────────────────────────────────────────┐
   │ 1. preserveSessionId() 執行                                 │
   │    - 從 URL 讀取 sessionId=abc123-def456-789               │
   │    - 存入 localStorage('liff_session_id', 'abc123-...')    │
   │                                                            │
   │ 2. liff.init({ liffId: "2007889032-OolKDrp3" })          │
   └─────────────────────────────────────────────────────────────┘
           │
           ▼
❓ liff.isLoggedIn() 檢查
           │
         ┌─┴─┐
         │   │
    ✅ 已登入   ❌ 未登入
         │         │
         ▼         ▼
   📋 直接載入    🔑 執行登入流程
      訂單資料        │
         │           ▼
         │      ┌─────────────────────────────────────────┐
         │      │ 🔑 OAuth2 登入 (使用 state 攜帶 session) │
         │      │                                        │
         │      │ const sessionId = localStorage.get...   │
         │      │ liff.login({                           │
         │      │   redirectUri: "https://your-domain.com/liff/edit",  │
         │      │   state: "abc123-def456-789"  // 📦 Session 放這裡 │
         │      │ })                                      │
         │      └─────────────────────────────────────────┘
         │           │
         │           ▼
         │      🔄 重定向到 LINE OAuth 伺服器
         │      ┌─────────────────────────────────────────┐
         │      │ https://access.line.me/oauth2/v2.1/login?... │
         │      │ &redirect_uri=https://your-domain.com/liff/edit │
         │      │ &state=abc123-def456-789  // 📦 State 攜帶  │
         │      └─────────────────────────────────────────┘
         │           │
         │           ▼
         │      👤 用戶在 LINE 登入頁面登入
         │           │
         │           ▼
         │      ✅ 登入成功，OAuth 回調
         │      ┌─────────────────────────────────────────┐
         │      │ https://your-domain.com/liff/edit?      │
         │      │   code=oauth_code_123&                  │
         │      │   state=abc123-def456-789&  // 📦 回傳   │
         │      │   liffClientId=2007889032               │
         │      └─────────────────────────────────────────┘
         │           │
         │           ▼
         └──────→ 🔄 頁面重新載入，再次執行 loadOrderData()
                     │
                     ▼
                ┌─────────────────────────────────────────┐
                │ 📋 載入訂單資料 (loadOrderData)          │
                │                                        │
                │ 多重來源取得 Session ID:                 │
                │ 1. URL sessionId 參數 (無)              │
                │ 2. URL session 參數 (無)               │
                │ 3. ✅ OAuth state 參數: abc123-def456-789 │
                │ 4. localStorage 備份: abc123-def456-789 │
                │                                        │
                │ sessionId = "abc123-def456-789" ✅      │
                └─────────────────────────────────────────┘
                     │
                     ▼
                🌐 呼叫後端 API 載入訂單
                ┌─────────────────────────────────────────┐
                │ GET /api/liff/orders/abc123-def456-789  │
                │                                        │
                │ Response: { success: true, orders: [...] } │
                └─────────────────────────────────────────┘
                     │
                     ▼
                📝 渲染訂單編輯表單
                     │
                     ▼
                👤 用戶編輯訂單並儲存
                     │
                     ▼
                💾 PUT /api/liff/orders/{sessionId}
                     │
                     ▼
                ✅ 儲存成功，發送確認訊息到 LINE
                     │
                     ▼
                🚪 liff.closeWindow() 關閉 LIFF
```

## 🔑 關鍵改進點

### ❌ 舊方案問題
```
❌ redirectUri 包含參數: 
   https://your-domain.com/liff/edit?session=abc123&focus=1
   
❌ 登入後參數丟失:
   https://your-domain.com/liff/edit?code=xxx&state=yyy
   (原本的 session=abc123 消失了!)
```

### ✅ 新方案解決
```
✅ 乾淨的 redirectUri: 
   https://your-domain.com/liff/edit
   
✅ OAuth state 攜帶 session:
   liff.login({ state: "abc123-def456-789" })
   
✅ 登入後取回 session:
   URL: https://your-domain.com/liff/edit?code=xxx&state=abc123-def456-789
   從 state 參數取回: abc123-def456-789 ✅
```

## 📊 URL 變化追蹤

| 步驟 | URL | Session 位置 |
|------|-----|-------------|
| 1. LIFF 初始連結 | `https://liff.line.me/{LIFF_ID}?...&sessionId=abc123` | URL 參數 |
| 2. 用戶登入前 | `https://your-domain.com/liff/edit` (重定向目標) | localStorage |
| 3. OAuth 登入 | `https://access.line.me/oauth2/...&state=abc123` | OAuth state |
| 4. 登入回調 | `https://your-domain.com/liff/edit?...&state=abc123` | OAuth state |
| 5. 載入完成 | `https://your-domain.com/liff/edit` | 內存變數 |

## 🛠️ LINE Console 設定

### ❌ 舊設定 (複雜)
```
Authorized Redirect URLs:
• https://your-domain.com/liff/edit
• https://your-domain.com/liff/edit?*
• https://your-domain.com/liff/edit?session=*
• https://your-domain.com/liff/edit?session=*&focus=*
... (更多組合)
```

### ✅ 新設定 (簡單)
```
Authorized Redirect URLs:
• https://your-domain.com/liff/edit
```
就這一個！🎉

## 🔒 安全性與可靠性

### OAuth2 State 參數的優勢：
1. **標準做法**: 符合 OAuth2 RFC 規範
2. **防 CSRF**: state 參數天然防 CSRF 攻擊
3. **可靠傳遞**: 由 OAuth 服務器保證參數傳遞
4. **不依賴 URL**: 不會因為 URL 變化而丟失
5. **簡化設定**: LINE Console 設定更簡單

### 多重備份機制：
1. **主要**: OAuth state 參數
2. **備份1**: localStorage 存儲
3. **備份2**: URL sessionId 參數 (初始)
4. **備份3**: URL session 參數 (相容舊版)

## 🎯 總結

**這個流程確保了：**
- ✅ Session ID 永遠不會丟失
- ✅ 符合 OAuth2 標準
- ✅ LINE Console 設定簡單
- ✅ 用戶體驗順暢
- ✅ 開發維護容易

**核心原則：**
> 把資料放在正確的地方 - Session ID 屬於應用狀態，應該用 OAuth state 攜帶，而不是塞在 URL 裡面！