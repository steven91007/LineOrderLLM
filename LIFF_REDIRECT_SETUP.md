# 🔧 LIFF 重定向設定指南

## 問題分析
LIFF OAuth 登入過程會導致 URL 參數丟失，需要正確設定 Redirect URI。

## LINE Developers Console 設定

### 1. LIFF 應用程式設定
```
LIFF app name: 訂單編輯器
Size: Full
Endpoint URL: https://9b0723f6edc9.ngrok-free.app/liff/edit
Scope: profile, openid
Bot link feature: On (Aggressive)
```

### 2. ⚠️ 重要：Authorized Redirect URLs
必須在 LINE Developers Console 中設定以下重定向 URL：

```
https://9b0723f6edc9.ngrok-free.app/liff/edit
https://9b0723f6edc9.ngrok-free.app/liff/edit?*
https://liff.line.me/2007889032-OolKDrp3
```

## 前端代碼修正

### 方案A：使用 redirectUri 參數（推薦）
```javascript
liff.init({
    liffId: '2007889032-OolKDrp3'
}).then(() => {
    if (!liff.isLoggedIn()) {
        // 關鍵：指定登入後返回的 URL，包含原始參數
        const currentUrl = new URL(window.location.href);
        const sessionId = currentUrl.searchParams.get('session');
        
        if (sessionId) {
            // 建構包含 session 參數的重定向 URL
            const redirectUrl = `${window.location.origin}/liff/edit?session=${sessionId}`;
            liff.login({ redirectUri: redirectUrl });
        } else {
            liff.login();
        }
        return;
    }
    // 已登入，繼續載入訂單
    loadOrderData();
});
```

### 方案B：使用 localStorage 持久化會話
```javascript
function saveSessionToStorage() {
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session');
    if (sessionId) {
        localStorage.setItem('liff_session_id', sessionId);
    }
}

function loadSessionFromStorage() {
    return localStorage.getItem('liff_session_id');
}
```

### 方案C：URL 參數編碼到 state
在生成 LIFF URL 時，將會話參數編碼到 state：
```
https://liff.line.me/2007889032-OolKDrp3?state=session_${sessionId}&session=${sessionId}
```

然後在 OAuth 回調中從 state 解析：
```javascript
const urlParams = new URLSearchParams(window.location.search);
const state = urlParams.get('state');
if (state && state.startsWith('session_')) {
    const sessionId = state.replace('session_', '');
    // 使用恢復的 sessionId
}
```