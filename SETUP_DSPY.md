# DSPy 整合指南

## 🎯 DSPy 整合概述

本版本新增了 DSPy (Declarative Self-improving Language Programs) 支援，提供更結構化和可靠的訂單解析功能。

### ✨ DSPy 優勢

1. **結構化推理**：使用 Signature 定義明確的輸入輸出格式
2. **強制 JSON 輸出**：確保回應格式一致性
3. **自動優化**：DSPy 可以自動優化 prompt 效果
4. **模組化設計**：解析流程分解為獨立模組
5. **更好的錯誤處理**：多層驗證機制

## 🔧 DSPy 架構設計

### 核心模組

```
DSPyOrderClient
├── OrderTypeClassifier    # 識別單一/多訂單
├── SingleOrderParser      # 單一訂單解析
├── MultiOrderParser       # 多訂單解析（最多5份）
└── OrderValidator         # 資料驗證
```

### Signature 定義

```python
class SingleOrderSignature(dspy.Signature):
    """解析單一訂單並輸出 JSON 格式"""
    order_text = dspy.InputField(desc="單一訂單文字")
    order_json = dspy.OutputField(desc="結構化 JSON 資料")

class MultiOrderSignature(dspy.Signature):
    """解析多訂單並輸出 JSON 格式"""
    order_text = dspy.InputField(desc="多訂單文字")
    orders_json = dspy.OutputField(desc="多訂單 JSON 資料")
```

### JSON Schema 驗證

系統使用嚴格的 JSON Schema 驗證：

```json
{
  "order_type": "single",
  "sender_name": null,        // 選填
  "sender_phone": null,       // 選填
  "receiver_name": "必填",
  "receiver_phone": "必填",
  "items": [
    {"name": "商品名", "quantity": 1}
  ],
  "shipping_date": null,      // 選填
  "shipping_address": "必填"
}
```

## ⚙️ 設定指南

### 1. 環境變數設定

在 `.env` 檔案中新增：

```bash
# DSPy 設定
DSPY_API_KEY=your_openai_api_key_here  # 可與 OPENAI_API_KEY 相同
DSPY_MODEL=gpt-4-0125-preview
DSPY_MAX_RETRIES=3

# 選擇訂單解析客戶端類型
ORDER_CLIENT_TYPE=dspy  # 'openai' 或 'dspy'
```

### 2. 安裝相依套件

```bash
pip install dspy-ai==2.4.9 jsonschema==4.20.0
```

### 3. 客戶端切換

系統支援在 OpenAI 和 DSPy 客戶端之間無縫切換：

- 設定 `ORDER_CLIENT_TYPE=openai` 使用原始 OpenAI 客戶端
- 設定 `ORDER_CLIENT_TYPE=dspy` 使用新的 DSPy 客戶端

## 🧪 測試 DSPy 功能

執行測試腳本驗證 DSPy 功能：

```bash
python test_dspy.py
```

測試涵蓋：
- ✅ 單一訂單解析
- ✅ 多訂單解析（2-5份）
- ✅ 錯誤處理機制
- ✅ JSON 格式驗證

## 📊 效能比較

| 特性 | OpenAI 客戶端 | DSPy 客戶端 |
|------|---------------|-------------|
| JSON 格式保證 | 基本 | 強制 |
| 錯誤處理 | 標準 | 多層驗證 |
| 模組化程度 | 低 | 高 |
| 可擴展性 | 中等 | 高 |
| 自動優化 | 無 | 支援 |

## 🔄 遷移指南

### 從 OpenAI 遷移到 DSPy

1. **無需修改現有程式碼**：兩種客戶端提供相同的介面
2. **逐步遷移**：可先測試 DSPy，確認無誤後完全切換
3. **回滾支援**：隨時可切換回 OpenAI 客戶端

### 設定步驟

```bash
# 1. 安裝 DSPy 相依套件
pip install dspy-ai jsonschema

# 2. 更新環境變數
echo "ORDER_CLIENT_TYPE=dspy" >> .env

# 3. 測試功能
python test_dspy.py

# 4. 重啟應用
python main.py
```

## 🛡️ 錯誤處理增強

DSPy 客戶端提供更完善的錯誤處理：

1. **JSON 格式驗證**：使用 JSONSchema 嚴格驗證
2. **業務邏輯驗證**：檢查必填欄位、電話格式等
3. **重試機制**：解析失敗時自動重試（最多3次）
4. **回退策略**：多訂單解析失敗時建議單筆輸入

## 📈 進階功能

### 自訂 DSPy 模組

可以擴展新的 DSPy 模組：

```python
class CustomOrderSignature(dspy.Signature):
    """自訂訂單解析邏輯"""
    order_text = dspy.InputField(desc="訂單文字")
    custom_output = dspy.OutputField(desc="自訂輸出格式")

class CustomOrderParser(dspy.Module):
    def __init__(self):
        self.parse = dspy.ChainOfThought(CustomOrderSignature)
    
    def forward(self, order_text):
        return self.parse(order_text=order_text)
```

### 模型微調支援

DSPy 支援模型微調和優化：

```python
# 未來可以加入訓練資料進行優化
trainset = [...]
teleprompter = BootstrapFewShot(metric=validate_order)
compiled_parser = teleprompter.compile(parser, trainset=trainset)
```

## 🚨 注意事項

1. **API 使用量**：DSPy 可能會產生更多 API 呼叫（重試、驗證）
2. **回應延遲**：由於多層驗證，可能略微增加處理時間
3. **相容性**：完全相容現有 LINE Bot 功能

## 🔮 未來規劃

1. **模型優化**：收集使用資料進行 DSPy 模型優化
2. **本地模型支援**：支援本地 LLM（如 Ollama）
3. **更多驗證規則**：加入更細緻的業務邏輯驗證
4. **效能監控**：新增 DSPy 效能監控儀表板

---

## 💡 最佳實踐

1. **開發環境先測試**：在正式環境前先在開發環境測試 DSPy
2. **監控 API 使用量**：注意 DSPy 的 API 呼叫次數
3. **保留 OpenAI 備案**：可隨時切換回 OpenAI 客戶端
4. **定期執行測試**：使用 `test_dspy.py` 定期驗證功能

使用 DSPy 可以獲得更穩定、可靠的訂單解析體驗！