-- 訂單資料收集與學習系統資料庫架構

-- 1. 原始訂單輸入記錄表
CREATE TABLE raw_order_inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,                    -- LINE 用戶 ID
    input_text TEXT NOT NULL,                 -- 原始輸入文字
    input_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    input_hash TEXT UNIQUE,                   -- 輸入文字的 hash，避免重複
    session_id TEXT,                          -- 會話 ID
    processing_status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. AI 解析結果記錄表
CREATE TABLE ai_parse_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_input_id INTEGER REFERENCES raw_order_inputs(id),
    parser_type TEXT NOT NULL,                -- dspy, openai 等
    parser_version TEXT,                      -- 解析器版本
    raw_output TEXT,                          -- AI 原始輸出
    parsed_orders_json TEXT,                  -- 解析後的 JSON 格式訂單
    parsing_success BOOLEAN NOT NULL,         -- 是否解析成功
    parsing_time_ms INTEGER,                  -- 解析耗時(毫秒)
    error_message TEXT,                       -- 錯誤訊息
    confidence_score REAL,                    -- 解析信心度(0-1)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. 最終確認訂單表
CREATE TABLE confirmed_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_input_id INTEGER REFERENCES raw_order_inputs(id),
    parse_result_id INTEGER REFERENCES ai_parse_results(id),
    order_id TEXT UNIQUE NOT NULL,           -- 訂單編號 (ORD-20240101-ABC12345)
    sender_name TEXT,
    sender_phone TEXT,
    receiver_name TEXT NOT NULL,
    receiver_phone TEXT NOT NULL,
    shipping_address TEXT NOT NULL,
    shipping_date TEXT,                      -- MM-DD 格式
    items_json TEXT NOT NULL,                -- 商品列表 JSON
    total_items INTEGER,                     -- 商品總數量
    user_modified BOOLEAN DEFAULT FALSE,     -- 是否被用戶修改過
    modifications_json TEXT,                 -- 用戶修改記錄 JSON
    google_sheets_synced BOOLEAN DEFAULT FALSE,
    google_sheets_sync_time DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 4. 學習樣本表
CREATE TABLE learning_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_input_id INTEGER REFERENCES raw_order_inputs(id),
    input_text TEXT NOT NULL,                -- 標準化後的輸入文字
    expected_output_json TEXT NOT NULL,      -- 期望的輸出 JSON
    sample_type TEXT NOT NULL,               -- positive, negative, edge_case
    quality_score REAL DEFAULT 1.0,         -- 樣本品質分數 (0-1)
    validation_status TEXT DEFAULT 'pending', -- pending, validated, rejected
    validator_id TEXT,                       -- 驗證者 ID
    tags TEXT,                              -- 標籤，用逗號分隔 (multi_order, date_parsing, address_parsing)
    notes TEXT,                             -- 備註
    usage_count INTEGER DEFAULT 0,          -- 被用於訓練的次數
    effectiveness_score REAL,               -- 樣本有效性分數
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 5. DSPy 模型訓練記錄表
CREATE TABLE dspy_training_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    training_session_id TEXT NOT NULL,       -- 訓練會話 ID
    model_name TEXT NOT NULL,                -- 模型名稱
    training_samples_count INTEGER,          -- 訓練樣本數
    validation_samples_count INTEGER,        -- 驗證樣本數
    training_start_time DATETIME,
    training_end_time DATETIME,
    training_status TEXT,                    -- running, completed, failed
    accuracy_score REAL,                     -- 準確率
    f1_score REAL,                          -- F1 分數
    model_config_json TEXT,                  -- 模型配置 JSON
    performance_metrics_json TEXT,           -- 詳細性能指標
    model_path TEXT,                        -- 訓練後模型保存路徑
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 6. MLflow 實驗追蹤記錄表
CREATE TABLE mlflow_experiment_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL,             -- MLflow 實驗 ID
    run_id TEXT NOT NULL,                    -- MLflow 運行 ID
    experiment_name TEXT NOT NULL,           -- 實驗名稱
    raw_input_id INTEGER REFERENCES raw_order_inputs(id),
    parse_result_id INTEGER REFERENCES ai_parse_results(id),
    parameters_json TEXT,                    -- 實驗參數
    metrics_json TEXT,                       -- 實驗指標
    artifacts_json TEXT,                     -- 實驗產出物
    status TEXT,                            -- RUNNING, FINISHED, FAILED
    start_time DATETIME,
    end_time DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 7. 樣本品質評估記錄表
CREATE TABLE sample_quality_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id INTEGER REFERENCES learning_samples(id),
    evaluator_type TEXT NOT NULL,            -- human, auto, ai
    evaluator_id TEXT,                       -- 評估者 ID
    quality_dimensions_json TEXT,            -- 評估維度分數 JSON
    overall_quality_score REAL NOT NULL,     -- 總體品質分數
    feedback_text TEXT,                      -- 評估反饋
    evaluation_time DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 8. 系統性能監控表
CREATE TABLE system_performance_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL,            -- parse_order, train_model, sync_sheets
    operation_id TEXT,                       -- 操作相關 ID
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    duration_ms INTEGER,                     -- 操作耗時
    memory_usage_mb REAL,                    -- 記憶體使用量
    cpu_usage_percent REAL,                 -- CPU 使用率
    success BOOLEAN,                         -- 操作是否成功
    error_details TEXT,                      -- 錯誤詳情
    metadata_json TEXT,                      -- 額外元數據
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 創建索引以提升查詢性能
CREATE INDEX idx_raw_inputs_user_timestamp ON raw_order_inputs(user_id, input_timestamp);
CREATE INDEX idx_raw_inputs_hash ON raw_order_inputs(input_hash);
CREATE INDEX idx_parse_results_input_id ON ai_parse_results(raw_input_id);
CREATE INDEX idx_confirmed_orders_input_id ON confirmed_orders(raw_input_id);
CREATE INDEX idx_confirmed_orders_order_id ON confirmed_orders(order_id);
CREATE INDEX idx_learning_samples_type ON learning_samples(sample_type);
CREATE INDEX idx_learning_samples_quality ON learning_samples(quality_score);
CREATE INDEX idx_mlflow_experiment_run ON mlflow_experiment_logs(experiment_id, run_id);
CREATE INDEX idx_system_perf_operation ON system_performance_logs(operation_type, start_time);

-- 創建視圖方便查詢
CREATE VIEW order_processing_summary AS
SELECT 
    ri.id as input_id,
    ri.user_id,
    ri.input_text,
    ri.input_timestamp,
    apr.parser_type,
    apr.parsing_success,
    apr.confidence_score,
    co.order_id,
    co.user_modified,
    co.google_sheets_synced
FROM raw_order_inputs ri
LEFT JOIN ai_parse_results apr ON ri.id = apr.raw_input_id
LEFT JOIN confirmed_orders co ON ri.id = co.raw_input_id
ORDER BY ri.input_timestamp DESC;

-- 學習樣本統計視圖
CREATE VIEW learning_samples_stats AS
SELECT 
    sample_type,
    validation_status,
    COUNT(*) as sample_count,
    AVG(quality_score) as avg_quality,
    AVG(effectiveness_score) as avg_effectiveness
FROM learning_samples 
GROUP BY sample_type, validation_status;