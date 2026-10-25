# 🔧 LIFF Redirect Setup Guide

## Problem analysis
The LIFF OAuth login flow drops URL parameters, so the Redirect URI has to be configured correctly.

## LINE Developers Console settings

### 1. LIFF app settings
```
LIFF app name: 訂單編輯器
Size: Full
Endpoint URL: https://9b0723f6edc9.ngrok-free.app/liff/edit
Scope: profile, openid
Bot link feature: On (Aggressive)
```
(`訂單編輯器` = "Order Editor", the app name shown to users.)

### 2. ⚠️ Important: Authorized Redirect URLs
The following redirect URLs must be configured in the LINE Developers Console:

```
https://9b0723f6edc9.ngrok-free.app/liff/edit
https://9b0723f6edc9.ngrok-free.app/liff/edit?*
https://liff.line.me/2007889032-OolKDrp3
```

## Front-end code fixes

### Option A: use the redirectUri parameter (recommended)
```javascript
liff.init({
    liffId: '2007889032-OolKDrp3'
}).then(() => {
    if (!liff.isLoggedIn()) {
        // Key point: specify the URL to return to after login, including the original parameters
        const currentUrl = new URL(window.location.href);
        const sessionId = currentUrl.searchParams.get('session');
        
        if (sessionId) {
            // Build a redirect URL that includes the session parameter
            const redirectUrl = `${window.location.origin}/liff/edit?session=${sessionId}`;
            liff.login({ redirectUri: redirectUrl });
        } else {
            liff.login();
        }
        return;
    }
    // Already logged in; continue loading the order
    loadOrderData();
});
```

### Option B: persist the session in localStorage
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

### Option C: encode the URL parameters into state
When generating the LIFF URL, encode the session parameter into state:
```
https://liff.line.me/2007889032-OolKDrp3?state=session_${sessionId}&session=${sessionId}
```

Then parse it from state in the OAuth callback:
```javascript
const urlParams = new URLSearchParams(window.location.search);
const state = urlParams.get('state');
if (state && state.startsWith('session_')) {
    const sessionId = state.replace('session_', '');
    // Use the recovered sessionId
}
```
