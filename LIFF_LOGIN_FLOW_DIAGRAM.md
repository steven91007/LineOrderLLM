# 🔄 LIFF Login and Redirect Flow Diagram (OAuth2 State Approach)

## 📋 Full flow diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                  🚀 Full LIFF Login and Redirect Flow                        │
│              (Session carried in the OAuth2 state parameter)                 │
└─────────────────────────────────────────────────────────────────────────────┘

👤 User types "#訂單" in LINE
           │
           ▼
📱 OrderHandler parses the order
           │
           ▼
🏗️ Create LIFF Session
   Session ID: "abc123-def456-789"
           │
           ▼
🌐 Generate LIFF URL (backend get_liff_url)
   ┌─────────────────────────────────────────────────────────────┐
   │ https://liff.line.me/2007889032-OolKDrp3?                   │
   │   liffRedirectUri=https://your-domain.com/liff/edit&        │
   │   sessionId=abc123-def456-789                               │
   └─────────────────────────────────────────────────────────────┘
           │
           ▼
📨 Send FlexMessage to the user
   Contains a "網頁編輯" (Edit on web) button → LIFF URL
           │
           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         📱 User taps the button                              │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
🌐 LINE opens the LIFF URL
   Current URL: https://liff.line.me/2007889032-OolKDrp3?...&sessionId=abc123-def456-789
           │
           ▼
🔄 LIFF front end initializes
   ┌─────────────────────────────────────────────────────────────┐
   │ 1. preserveSessionId() runs                                 │
   │    - reads sessionId=abc123-def456-789 from the URL         │
   │    - stores localStorage('liff_session_id', 'abc123-...')   │
   │                                                             │
   │ 2. liff.init({ liffId: "2007889032-OolKDrp3" })             │
   └─────────────────────────────────────────────────────────────┘
           │
           ▼
❓ liff.isLoggedIn() check
           │
         ┌─┴─┐
         │   │
  ✅ Logged in  ❌ Not logged in
         │         │
         ▼         ▼
   📋 Load order   🔑 Run login flow
      data directly   │
         │           ▼
         │      ┌─────────────────────────────────────────┐
         │      │ 🔑 OAuth2 login (session carried in state) │
         │      │                                        │
         │      │ const sessionId = localStorage.get...   │
         │      │ liff.login({                           │
         │      │   redirectUri: "https://your-domain.com/liff/edit",  │
         │      │   state: "abc123-def456-789"  // 📦 Session goes here │
         │      │ })                                      │
         │      └─────────────────────────────────────────┘
         │           │
         │           ▼
         │      🔄 Redirect to the LINE OAuth server
         │      ┌─────────────────────────────────────────┐
         │      │ https://access.line.me/oauth2/v2.1/login?... │
         │      │ &redirect_uri=https://your-domain.com/liff/edit │
         │      │ &state=abc123-def456-789  // 📦 carried in state │
         │      └─────────────────────────────────────────┘
         │           │
         │           ▼
         │      👤 User logs in on the LINE login page
         │           │
         │           ▼
         │      ✅ Login succeeds, OAuth callback
         │      ┌─────────────────────────────────────────┐
         │      │ https://your-domain.com/liff/edit?      │
         │      │   code=oauth_code_123&                  │
         │      │   state=abc123-def456-789&  // 📦 returned │
         │      │   liffClientId=2007889032               │
         │      └─────────────────────────────────────────┘
         │           │
         │           ▼
         └──────→ 🔄 Page reloads and runs loadOrderData() again
                     │
                     ▼
                ┌─────────────────────────────────────────┐
                │ 📋 Load order data (loadOrderData)       │
                │                                         │
                │ Session ID from multiple sources:       │
                │ 1. URL sessionId param (none)           │
                │ 2. URL session param (none)             │
                │ 3. ✅ OAuth state param: abc123-def456-789 │
                │ 4. localStorage backup: abc123-def456-789 │
                │                                         │
                │ sessionId = "abc123-def456-789" ✅       │
                └─────────────────────────────────────────┘
                     │
                     ▼
                🌐 Call backend API to load orders
                ┌─────────────────────────────────────────┐
                │ GET /api/liff/orders/abc123-def456-789  │
                │                                         │
                │ Response: { success: true, orders: [...] } │
                └─────────────────────────────────────────┘
                     │
                     ▼
                📝 Render the order edit form
                     │
                     ▼
                👤 User edits the order and saves
                     │
                     ▼
                💾 PUT /api/liff/orders/{sessionId}
                     │
                     ▼
                ✅ Saved; send a confirmation message to LINE
                     │
                     ▼
                🚪 liff.closeWindow() closes LIFF
```

## 🔑 Key improvements

### ❌ Problems with the old approach
```
❌ redirectUri contains parameters: 
   https://your-domain.com/liff/edit?session=abc123&focus=1
   
❌ Parameters lost after login:
   https://your-domain.com/liff/edit?code=xxx&state=yyy
   (the original session=abc123 is gone!)
```

### ✅ How the new approach solves it
```
✅ Clean redirectUri: 
   https://your-domain.com/liff/edit
   
✅ OAuth state carries the session:
   liff.login({ state: "abc123-def456-789" })
   
✅ Session recovered after login:
   URL: https://your-domain.com/liff/edit?code=xxx&state=abc123-def456-789
   Recovered from the state param: abc123-def456-789 ✅
```

## 📊 URL changes, step by step

| Step | URL | Where the session lives |
|------|-----|-------------|
| 1. Initial LIFF link | `https://liff.line.me/{LIFF_ID}?...&sessionId=abc123` | URL parameter |
| 2. Before user login | `https://your-domain.com/liff/edit` (redirect target) | localStorage |
| 3. OAuth login | `https://access.line.me/oauth2/...&state=abc123` | OAuth state |
| 4. Login callback | `https://your-domain.com/liff/edit?...&state=abc123` | OAuth state |
| 5. Load complete | `https://your-domain.com/liff/edit` | In-memory variable |

## 🛠️ LINE Console settings

### ❌ Old settings (complicated)
```
Authorized Redirect URLs:
• https://your-domain.com/liff/edit
• https://your-domain.com/liff/edit?*
• https://your-domain.com/liff/edit?session=*
• https://your-domain.com/liff/edit?session=*&focus=*
... (more combinations)
```

### ✅ New settings (simple)
```
Authorized Redirect URLs:
• https://your-domain.com/liff/edit
```
Just this one! 🎉

## 🔒 Security and reliability

### Advantages of the OAuth2 state parameter:
1. **Standard practice**: conforms to the OAuth2 RFC
2. **CSRF protection**: the state parameter inherently guards against CSRF attacks
3. **Reliable delivery**: the OAuth server guarantees the parameter is passed through
4. **URL-independent**: not lost when the URL changes
5. **Simpler setup**: LINE Console configuration is simpler

### Multiple fallbacks:
1. **Primary**: OAuth state parameter
2. **Fallback 1**: localStorage
3. **Fallback 2**: URL sessionId parameter (initial)
4. **Fallback 3**: URL session parameter (legacy compatibility)

## 🎯 Summary

**This flow ensures:**
- ✅ The Session ID is never lost
- ✅ It conforms to the OAuth2 standard
- ✅ LINE Console setup is simple
- ✅ The user experience is smooth
- ✅ Development and maintenance are easy

**Core principle:**
> Put data in the right place — the Session ID is application state and should be carried in the OAuth state, not stuffed into the URL!
