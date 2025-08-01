# Claude 開發記錄

## 專案決策與技術方針

### AI/LLM 實作統一規範
- **統一使用 DSPy 框架**：所有 AI/LLM 相關功能都使用 DSPy 實作
- **MLflow 自動追蹤**：所有 DSPy 模組都必須加上 `mlflow.dspy.autolog()` 進行實驗追蹤
- **模組化設計**：每個 AI 功能都建立獨立的 DSPy 模組

### 台灣地址標準化系統設計

#### 問題分析
- 地址格式五花八門，單純規則匹配有限制
- 需要 LLM 協助理解複雜的地址描述
- 結合規則庫與 AI 判斷提高準確性

#### 技術方案
1. **DSPy 地址標準化模組**
   - 建立 `AddressNormalizerSignature` 定義輸入輸出
   - 建立 `AddressNormalizer` DSPy 模組
   - 整合現有的地址規則庫作為 Few-shot examples

2. **混合式處理流程**
   ```
   原始地址 → 規則預處理 → DSPy AI 標準化 → 規則後處理 → 標準化地址
   ```

3. **MLflow 追蹤**
   - 追蹤地址標準化成功率
   - 記錄不同類型地址的處理效果
   - 監控 AI 模組的準確性

### 實作要點
- DSPy 模組放在 `src/utils/dspy_modules/` 目錄
- 每個模組都要有對應的 signature
- 統一使用 `mlflow.dspy.autolog()` 進行追蹤
- 提供 fallback 機制（AI 失敗時使用規則庫）

## 開發記錄

### 2025-08-01 地址標準化功能
- ✅ 建立基礎規則庫（縣市升格、區域對照）
- ✅ 實作地址補全功能
- ✅ 加入 DSPy LLM 輔助處理複雜地址
- ✅ 整合 MLflow 追蹤 (`mlflow.dspy.autolog()`)
- ✅ 混合式處理流程（規則 + AI + 後處理）

#### DSPy 地址標準化模組
- `AddressNormalizerSignature`：定義地址標準化的輸入輸出格式
- `AddressNormalizer`：DSPy 模組，包含 Few-shot 範例
- 自動判斷複雜地址，選擇 AI 或規則處理
- Fallback 機制確保穩定性