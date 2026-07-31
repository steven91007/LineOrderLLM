# 訂單學習系統 (Order Learning System)

一個基於 DSPy 的智能訂單處理學習系統，能夠自動收集訓練數據、評估樣本品質，並持續改進模型性能。

## 🎯 核心功能

### 1. 資料收集與追蹤
- **自動記錄**：記錄所有訂單輸入輸出，建立完整的處理記錄
- **MLflow 集成**：實驗追蹤和性能監控
- **性能指標**：解析時間、成功率、信心度等指標統計

### 2. 學習樣本管理
- **正面樣本**：從成功處理的訂單自動生成
- **負面樣本**：系統自動生成各種錯誤場景
- **邊界案例**：手工製作的複雜場景樣本
- **品質評估**：多維度自動品質評分系統

### 3. 模型持續改進
- **自動訓練**：定期使用新樣本重新訓練模型
- **性能評估**：持續監控模型準確率和性能
- **版本管理**：模型版本控制和回滾機制

### 4. 品質保證
- **多維度評估**：完整性、準確性、清晰度、一致性、複雜度、代表性
- **自動評分**：AI 驅動的樣本品質評估
- **品質趨勢**：追蹤樣本品質變化趨勢

## 🏗️ 系統架構

```
訂單學習系統
├── 資料層 (Database Layer)
│   ├── RawOrderInput      # 原始輸入記錄
│   ├── AIParseResult      # AI 解析結果
│   ├── ConfirmedOrder     # 確認訂單
│   ├── LearningSample     # 學習樣本
│   └── QualityEvaluation  # 品質評估
├── 服務層 (Service Layer)
│   ├── OrderDataCollector     # 資料收集器
│   ├── DSPyLearningManager   # 學習管理器
│   └── SampleQualityEvaluator # 品質評估器
├── 增強客戶端 (Enhanced Client)
│   └── EnhancedDSPyOrderClient # 增強 DSPy 客戶端
└── 管理工具 (Management Tools)
    └── LearningSystemCLI      # 命令行管理工具
```

## 📦 安裝與配置

### 1. 安裝依賴
```bash
pip install -r requirements_learning.txt
```

### 2. 初始化資料庫
```bash
python -m src.cli.learning_system_cli init-db
```

### 3. 環境變量配置
```bash
# MLflow 追蹤服務器 (可選)
export MLFLOW_TRACKING_URI=http://localhost:5000

# 資料庫連接 (預設使用 SQLite)
export DATABASE_URL=sqlite:///order_learning_system.db
```

## 🚀 快速開始

### 1. 啟用學習功能
```python
from src.utils.enhanced_dspy_client import EnhancedDSPyOrderClient

# 創建增強客戶端
client = EnhancedDSPyOrderClient(
    openai_api_key="your-api-key",
    enable_data_collection=True,
    enable_mlflow_tracking=True, 
    enable_auto_learning=True
)

# 解析訂單（自動記錄和學習）
result = client.parse_order(
    order_text="收件人：王小明 電話：0912345678...",
    user_id="user123"
)
```

### 2. 記錄確認訂單
```python
# 用戶確認後記錄訂單
order_ids = client.record_confirmed_orders(
    raw_input_id=result['raw_input_id'],
    parse_result_id=result['parse_result_id'],
    confirmed_orders=confirmed_orders_list,
    user_modifications=user_changes  # 可選
)
```

### 3. 使用管理工具
```bash
# 查看系統統計
python -m src.cli.learning_system_cli stats

# 收集訓練樣本
python -m src.cli.learning_system_cli collect-samples --days 7

# 評估樣本品質
python -m src.cli.learning_system_cli evaluate-samples --limit 100

# 訓練模型
python -m src.cli.learning_system_cli train-model

# 執行完整學習管道
python -m src.cli.learning_system_cli full-pipeline
```

## 📊 監控與分析

### 1. 系統統計
```bash
python -m src.cli.learning_system_cli stats --days 30
```
輸出：
```
📊 訂單學習系統統計 (過去 30 天)
==================================================

🔄 處理統計:
  總輸入: 1,245
  解析次數: 1,198
  成功率: 96.2%
  確認訂單: 2,341
  學習樣本: 892

🤖 訓練統計:
  總樣本: 892
  正面樣本: 756
  負面樣本: 89
  邊界案例: 47
  平均品質: 0.847
  訓練會話: 12
  成功率: 100%

⭐ 品質統計:
  總評估: 892
  平均品質: 0.847
  高品質比例: 78.5%
```

### 2. MLflow 追蹤
訪問 MLflow UI 查看詳細實驗記錄：
```bash
mlflow ui
```

### 3. 模型性能評估
```python
# 評估當前模型
performance = client.evaluate_current_performance()
print(f"模型準確率: {performance['accuracy']:.1%}")
```

## 🎛️ 高級配置

### 1. 自定義品質評估器
```python
from src.services.sample_quality_evaluator import SampleQualityEvaluator

evaluator = SampleQualityEvaluator()

# 自定義評估維度權重
custom_weights = {
    'completeness': 0.3,
    'accuracy': 0.3, 
    'clarity': 0.2,
    'consistency': 0.1,
    'complexity': 0.05,
    'representativeness': 0.05
}
```

### 2. 學習策略配置
```python
# 配置自動學習觸發條件
client.auto_learning_config = {
    'trigger_probability': 0.05,  # 5% 機率觸發
    'min_samples_for_training': 50,
    'quality_threshold': 0.8,
    'retrain_interval_days': 7
}
```

### 3. 樣本過濾策略
```python
# 獲取高品質樣本
high_quality_samples = order_data_collector.get_learning_samples(
    sample_type='positive',
    min_quality_score=0.85,
    tags=['multi_order', 'date_parsing'],
    limit=500
)
```

## 📈 性能優化

### 1. 資料庫索引
系統自動創建必要索引，支持高效查詢：
```sql
CREATE INDEX idx_raw_inputs_user_timestamp ON raw_order_inputs(user_id, input_timestamp);
CREATE INDEX idx_learning_samples_quality ON learning_samples(quality_score);
```

### 2. 批量處理
```python
# 批量評估樣本
results = sample_quality_evaluator.batch_evaluate_samples(
    sample_type='positive',
    limit=1000
)
```

### 3. 內存管理
```python
# 系統自動監控內存和 CPU 使用情況
performance_log = order_data_collector.record_system_performance(
    operation_type='batch_training',
    # ... 其他參數
)
```

## 🔧 故障排除

### 常見問題

1. **資料庫連接失敗**
   ```bash
   # 檢查資料庫文件權限
   ls -la order_learning_system.db
   
   # 重新初始化
   python -m src.cli.learning_system_cli init-db
   ```

2. **MLflow 追蹤失敗**
   ```python
   # 禁用 MLflow（僅用於測試）
   client = EnhancedDSPyOrderClient(
       openai_api_key="your-key",
       enable_mlflow_tracking=False
   )
   ```

3. **樣本品質過低**
   ```bash
   # 清理低品質樣本
   python -m src.cli.learning_system_cli cleanup
   
   # 重新評估樣本
   python -m src.cli.learning_system_cli evaluate-samples --limit 200
   ```

4. **訓練失敗**
   ```bash
   # 檢查樣本數量
   python -m src.cli.learning_system_cli stats
   
   # 收集更多樣本
   python -m src.cli.learning_system_cli collect-samples --days 30
   ```

## 📚 API 參考

### OrderDataCollector
```python
# 記錄原始輸入
raw_input_id = order_data_collector.record_raw_input(
    user_id="user123",
    input_text="訂單內容...",
    session_id="session456"
)

# 記錄解析結果
parse_result_id = order_data_collector.record_ai_parse_result(
    raw_input_id=raw_input_id,
    parser_type='dspy_enhanced',
    parsing_success=True,
    # ... 其他參數
)
```

### DSPyLearningManager
```python
# 收集訓練樣本
collected_count = dspy_learning_manager.collect_training_samples_from_confirmed_orders(
    days=30,
    min_quality_threshold=0.8
)

# 訓練模型
session_id = dspy_learning_manager.train_model(
    train_examples=train_examples,
    val_examples=val_examples,
    model_name="custom_model_v1"
)
```

### SampleQualityEvaluator
```python
# 評估單個樣本
evaluation = sample_quality_evaluator.evaluate_sample_auto(
    sample_id=123,
    evaluator_id='auto_v1'
)

# 批量評估
batch_results = sample_quality_evaluator.batch_evaluate_samples(
    sample_type='positive',
    limit=100
)
```

## 📋 最佳實踐

1. **定期維護**：每週運行一次完整學習管道
2. **品質監控**：保持樣本平均品質在 0.8 以上
3. **性能追蹤**：使用 MLflow 追蹤所有實驗
4. **數據備份**：定期備份資料庫和訓練好的模型
5. **版本管理**：為每次重要的模型更新建立版本標記

## 🤝 貢獻指南

1. Fork 專案
2. 創建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交變更 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 創建 Pull Request

## 📄 許可證

本專案採用 MIT 許可證 - 詳見 [LICENSE](LICENSE) 文件。

## 📞 支援

如有問題或建議，請：
1. 查看 [FAQ](FAQ.md)
2. 搜索 [Issues](https://github.com/your-repo/issues)
3. 創建新的 Issue

---

*這個學習系統會持續改進你的訂單處理效果，讓 AI 越用越聰明！* 🚀