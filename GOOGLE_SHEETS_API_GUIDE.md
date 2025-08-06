# Google Sheets API 使用指南

## 概述

此專案提供了完整的 Google Sheets API 整合方案，包括：
- **GoogleSheetsClient**: 核心客戶端類別
- **範例程式**: 展示各種使用方法
- **測試程式**: 完整的功能測試套件

## 快速開始

### 1. 環境設定

#### 必要環境變數
在 `.env` 檔案中設定以下變數：

```bash
# Google Sheets 設定
GOOGLE_SHEETS_CREDENTIALS_PATH=/path/to/your/credentials.json
GOOGLE_SHEETS_ID=your_spreadsheet_id_here
```

#### 取得 Google Sheets 憑證

1. **建立 Google Cloud 專案**
   - 前往 [Google Cloud Console](https://console.cloud.google.com/)
   - 建立新專案或選擇現有專案

2. **啟用 Google Sheets API**
   - 在 API 與服務 > 程式庫中搜尋 "Google Sheets API"
   - 點擊啟用

3. **建立服務帳戶**
   - 前往 API 與服務 > 憑證
   - 點擊 "建立憑證" > "服務帳戶"
   - 填寫服務帳戶詳細資料
   - 下載 JSON 憑證檔案

4. **設定試算表權限**
   - 建立或開啟 Google Sheets 試算表
   - 點擊右上角 "共用" 按鈕
   - 新增服務帳戶的電子郵件地址（在憑證檔案中的 `client_email`）
   - 給予 "編輯者" 權限

5. **取得試算表 ID**
   - 從試算表 URL 中複製 ID
   - URL 格式：`https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid=0`

### 2. 安裝相依套件

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dotenv
```

### 3. 驗證設定

執行設定驗證來確認所有配置正確：

```bash
python test_google_sheets_api.py --validation-only
```

## 使用方法

### 基本使用

```python
from src.utils.google_sheets_client import GoogleSheetsClient
import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 初始化客戶端
client = GoogleSheetsClient(
    credentials_path=os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH'),
    sheet_id=os.getenv('GOOGLE_SHEETS_ID')
)

# 測試連接
result = client.test_connection()
if result['success']:
    print(f"連接成功：{result['message']}")
else:
    print(f"連接失敗：{result['error']}")
```

### 新增單一訂單

```python
order_data = {
    'order_id': 'ORD-20250804-001',
    'sender_name': '寄件人姓名',
    'sender_phone': '0912-345-678',
    'receiver_name': '收件人姓名',
    'receiver_phone': '0987-654-321',
    'shipping_address': '台北市信義區信義路五段7號',
    'shipping_date': '2025-08-07',
    'items': [
        {'name': '18A禮盒', 'quantity': 2},
        {'name': '16A蛋糕', 'quantity': 1}
    ],
    'status': '待處理',
    'notes': '備註資訊'
}

result = client.append_order(order_data)
if result['success']:
    print(f"訂單新增成功，訂單編號：{result['order_id']}")
else:
    print(f"訂單新增失敗：{result['error']}")
```

### 批量新增訂單

```python
orders_data = [order1, order2, order3]  # 訂單列表

result = client.append_multiple_orders(orders_data)
if result['success']:
    print(f"批量新增成功，處理了 {result['total_processed']} 筆訂單")
    print(f"訂單編號：{result['order_ids']}")
else:
    print(f"批量新增失敗：{result['error']}")
```

### 獲取最近訂單

```python
result = client.get_recent_orders(limit=10)
if result['success']:
    orders = result['orders']
    print(f"找到 {len(orders)} 筆最近訂單")
    for order in orders:
        print(f"- {order['order_id']}: {order['receiver_name']}")
else:
    print(f"獲取訂單失敗：{result['error']}")
```

## 執行範例程式

### 完整功能展示

```bash
python examples/google_sheets_api_example.py
```

這個範例程式會：
1. 驗證環境設定
2. 測試連接
3. 建立試算表標題（如果不存在）
4. 新增單一範例訂單
5. 批量新增多筆範例訂單
6. 獲取最近的訂單記錄

### 範例輸出

```
🚀 Google Sheets API 範例程式
這個程式將示範 GoogleSheetsClient 的各種功能
使用憑證檔案：/path/to/credentials.json
使用試算表 ID：your_spreadsheet_id

==================================================
 設定驗證
==================================================
整體狀態：healthy

檢查結果：
  ✅ credentials_file：憑證檔案存在
  ✅ service_init：Google Sheets 服務初始化成功
  ✅ connection：成功連接到試算表: 訂單管理系統
    - spreadsheet_title：訂單管理系統
    - sheet_count：1
  ✅ headers：標題行設定成功

==================================================
 連接測試
==================================================
✅ 連接測試 成功！
   訊息：成功連接到試算表: 訂單管理系統
   試算表標題：訂單管理系統
   工作表數量：1

... 更多輸出 ...

==================================================
範例程式執行完成
==================================================
🎉 所有功能示範完成！
您可以查看 Google Sheets 確認資料是否正確新增
```

## 執行測試程式

### 完整測試套件

```bash
python test_google_sheets_api.py
```

### 測試選項

```bash
# 僅執行設定驗證
python test_google_sheets_api.py --validation-only

# 詳細輸出
python test_google_sheets_api.py -v

# 快速測試（跳過實際寫入）
python test_google_sheets_api.py --quick
```

### 測試項目

測試程式包含以下測試項目：

1. **環境設定測試** - 檢查環境變數和憑證檔案
2. **客戶端初始化測試** - 驗證 GoogleSheetsClient 正確初始化
3. **設定驗證測試** - 測試 `validate_setup()` 功能
4. **連接測試** - 測試 `test_connection()` 功能
5. **範例資料建立測試** - 驗證測試資料格式
6. **標題建立測試** - 測試 `create_sheet_if_not_exists()` 功能
7. **單一訂單新增測試** - 測試 `append_order()` 功能
8. **批量訂單新增測試** - 測試 `append_multiple_orders()` 功能
9. **資料讀取測試** - 測試 `get_recent_orders()` 功能
10. **錯誤處理測試** - 測試各種錯誤情況
11. **資料格式化測試** - 測試 `_format_items()` 功能

## API 參考

### GoogleSheetsClient

#### 初始化

```python
GoogleSheetsClient(credentials_path: str, sheet_id: str)
```

- `credentials_path`: Google Service Account 憑證檔案路徑
- `sheet_id`: Google Sheets 試算表 ID

#### 主要方法

##### `test_connection() -> Dict[str, Any]`
測試與 Google Sheets 的連接

**回傳值：**
```python
{
    'success': bool,
    'spreadsheet_title': str,  # 試算表標題
    'sheet_count': int,        # 工作表數量
    'message': str,            # 成功訊息
    'error': str               # 錯誤訊息（失敗時）
}
```

##### `validate_setup() -> Dict[str, Any]`
驗證完整的設定狀態

**回傳值：**
```python
{
    'overall_status': str,     # 'healthy', 'partial', 'failed'
    'checks': dict,            # 各項檢查結果
    'recommendations': list    # 建議事項
}
```

##### `append_order(order_data: Dict[str, Any]) -> Dict[str, Any]`
新增單一訂單到試算表

**參數：**
```python
order_data = {
    'order_id': str,           # 訂單編號
    'sender_name': str,        # 寄件人姓名（選填）
    'sender_phone': str,       # 寄件人電話（選填）
    'receiver_name': str,      # 收件人姓名
    'receiver_phone': str,     # 收件人電話
    'shipping_address': str,   # 收件地址
    'shipping_date': str,      # 預計發貨日期（選填）
    'items': List[Dict],       # 商品清單
    'status': str,             # 訂單狀態（選填，預設：待處理）
    'notes': str               # 備註（選填）
}
```

**商品清單格式：**
```python
items = [
    {'name': '商品名稱', 'quantity': 數量},
    ...
]
```

**回傳值：**
```python
{
    'success': bool,
    'updated_rows': int,       # 更新的行數
    'updated_cells': int,      # 更新的儲存格數
    'order_id': str,           # 訂單編號
    'error': str               # 錯誤訊息（失敗時）
}
```

##### `append_multiple_orders(orders_data: List[Dict[str, Any]]) -> Dict[str, Any]`
批量新增多筆訂單到試算表

**參數：**
- `orders_data`: 訂單資料列表，每個元素格式同 `append_order`

**回傳值：**
```python
{
    'success': bool,
    'total_processed': int,    # 處理的訂單數量
    'updated_rows': int,       # 更新的行數
    'updated_cells': int,      # 更新的儲存格數
    'order_ids': List[str],    # 所有訂單編號
    'error': str               # 錯誤訊息（失敗時）
}
```

##### `get_recent_orders(limit: int = 10) -> Dict[str, Any]`
獲取最近的訂單記錄

**參數：**
- `limit`: 獲取的訂單數量限制

**回傳值：**
```python
{
    'success': bool,
    'orders': List[Dict],      # 訂單列表
    'error': str               # 錯誤訊息（失敗時）
}
```

**訂單格式：**
```python
order = {
    'order_time': str,         # 訂單時間
    'order_id': str,           # 訂單編號
    'sender_name': str,        # 寄件人姓名
    'sender_phone': str,       # 寄件人電話
    'receiver_name': str,      # 收件人姓名
    'receiver_phone': str,     # 收件人電話
    'items': str,              # 商品明細（已格式化）
    'shipping_date': str,      # 預計發貨日期
    'shipping_address': str,   # 收件地址
    'status': str,             # 訂單狀態
    'notes': str               # 備註
}
```

##### `create_sheet_if_not_exists() -> bool`
確保試算表存在並設定正確的標題行

**回傳值：**
- `True`: 設定成功
- `False`: 設定失敗

## 試算表格式

### 標題行（第一行）

| A | B | C | D | E | F | G | H | I | J | K |
|---|---|---|---|---|---|---|---|---|---|---|
| 訂單時間 | 訂單編號 | 寄件人 | 寄件人電話 | 收件人 | 收件人電話 | 商品明細 | 預計發貨日 | 收件地址 | 訂單狀態 | 備註 |

### 資料行範例

| 訂單時間 | 訂單編號 | 寄件人 | 寄件人電話 | 收件人 | 收件人電話 | 商品明細 | 預計發貨日 | 收件地址 | 訂單狀態 | 備註 |
|---------|---------|--------|-----------|--------|-----------|----------|-----------|----------|----------|------|
| 2025-08-04 14:30:15 | ORD-20250804-001 | 王小明 | 0912-345-678 | 李小華 | 0987-654-321 | 18A禮盒 x 2, 16A蛋糕 x 1 | 2025-08-07 | 台北市信義區信義路五段7號 | 待處理 | 急件 |

## 常見問題

### Q: 為什麼連接測試失敗？

**A: 可能的原因：**
1. **憑證檔案路徑錯誤** - 檢查 `GOOGLE_SHEETS_CREDENTIALS_PATH` 環境變數
2. **試算表 ID 錯誤** - 檢查 `GOOGLE_SHEETS_ID` 環境變數
3. **權限不足** - 確保服務帳戶有試算表的編輯權限
4. **API 未啟用** - 確保 Google Sheets API 已在 Google Cloud Console 中啟用

### Q: 如何檢查服務帳戶權限？

**A: 檢查步驟：**
1. 開啟 Google Sheets 試算表
2. 點擊右上角 "共用" 按鈕
3. 確認服務帳戶電子郵件地址在共用清單中
4. 確認權限設定為 "編輯者" 或 "擁有者"

### Q: 新增訂單時出現權限錯誤怎麼辦？

**A: 解決方法：**
1. 使用 `validate_setup()` 檢查所有設定
2. 確認服務帳戶有寫入權限
3. 檢查憑證檔案是否有效
4. 嘗試重新下載憑證檔案

### Q: 如何自訂試算表格式？

**A: 自訂方法：**
1. 修改 `create_sheet_if_not_exists()` 方法中的標題定義
2. 調整 `append_order()` 和 `append_multiple_orders()` 中的資料欄位順序
3. 更新 `get_recent_orders()` 中的資料解析邏輯

### Q: 如何處理大量資料？

**A: 效能建議：**
1. 使用 `append_multiple_orders()` 進行批量操作
2. 避免頻繁的單筆新增操作
3. 設定適當的 `limit` 參數讀取資料
4. 考慮使用分頁或分批處理機制

## 授權與支援

此專案遵循專案主要授權條款。如有問題或建議，請透過專案 Issue 系統回報。

## 更新記錄

- **2025-08-04**: 初始版本發布，包含完整的 Google Sheets API 整合
- 功能包含：單一/批量訂單新增、資料讀取、連接測試、設定驗證
- 提供完整的範例程式和測試套件