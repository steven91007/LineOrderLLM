"""
訂單資料收集系統 - SQLAlchemy ORM 模型
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, Boolean, Real, 
    ForeignKey, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import json
import hashlib
from typing import Dict, Any, List, Optional

Base = declarative_base()


class RawOrderInput(Base):
    """原始訂單輸入記錄表"""
    __tablename__ = 'raw_order_inputs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    input_text = Column(Text, nullable=False)
    input_timestamp = Column(DateTime, default=datetime.utcnow)
    input_hash = Column(String(64), unique=True, index=True)
    session_id = Column(String(100))
    processing_status = Column(String(20), default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 關聯
    parse_results = relationship("AIParseResult", back_populates="raw_input")
    confirmed_orders = relationship("ConfirmedOrder", back_populates="raw_input")
    learning_samples = relationship("LearningSample", back_populates="raw_input")
    
    def __init__(self, user_id: str, input_text: str, session_id: str = None):
        self.user_id = user_id
        self.input_text = input_text
        self.session_id = session_id
        self.input_hash = self._generate_hash(input_text)
    
    def _generate_hash(self, text: str) -> str:
        """生成輸入文字的 hash"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'input_text': self.input_text,
            'input_timestamp': self.input_timestamp.isoformat() if self.input_timestamp else None,
            'session_id': self.session_id,
            'processing_status': self.processing_status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class AIParseResult(Base):
    """AI 解析結果記錄表"""
    __tablename__ = 'ai_parse_results'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_input_id = Column(Integer, ForeignKey('raw_order_inputs.id'), nullable=False)
    parser_type = Column(String(50), nullable=False)
    parser_version = Column(String(20))
    raw_output = Column(Text)
    parsed_orders_json = Column(Text)
    parsing_success = Column(Boolean, nullable=False)
    parsing_time_ms = Column(Integer)
    error_message = Column(Text)
    confidence_score = Column(Real)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 關聯
    raw_input = relationship("RawOrderInput", back_populates="parse_results")
    confirmed_orders = relationship("ConfirmedOrder", back_populates="parse_result")
    
    def __init__(self, raw_input_id: int, parser_type: str, parsing_success: bool):
        self.raw_input_id = raw_input_id
        self.parser_type = parser_type
        self.parsing_success = parsing_success
    
    def set_parsed_orders(self, orders: List[Dict[str, Any]]):
        """設置解析結果"""
        self.parsed_orders_json = json.dumps(orders, ensure_ascii=False)
    
    def get_parsed_orders(self) -> List[Dict[str, Any]]:
        """獲取解析結果"""
        if self.parsed_orders_json:
            try:
                return json.loads(self.parsed_orders_json)
            except json.JSONDecodeError:
                return []
        return []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'raw_input_id': self.raw_input_id,
            'parser_type': self.parser_type,
            'parser_version': self.parser_version,
            'parsing_success': self.parsing_success,
            'parsing_time_ms': self.parsing_time_ms,
            'confidence_score': self.confidence_score,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ConfirmedOrder(Base):
    """最終確認訂單表"""
    __tablename__ = 'confirmed_orders'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_input_id = Column(Integer, ForeignKey('raw_order_inputs.id'), nullable=False)
    parse_result_id = Column(Integer, ForeignKey('ai_parse_results.id'))
    order_id = Column(String(50), unique=True, nullable=False, index=True)
    sender_name = Column(String(100))
    sender_phone = Column(String(20))
    receiver_name = Column(String(100), nullable=False)
    receiver_phone = Column(String(20), nullable=False)
    shipping_address = Column(Text, nullable=False)
    shipping_date = Column(String(10))  # MM-DD 格式
    items_json = Column(Text, nullable=False)
    total_items = Column(Integer)
    user_modified = Column(Boolean, default=False)
    modifications_json = Column(Text)
    google_sheets_synced = Column(Boolean, default=False)
    google_sheets_sync_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 關聯
    raw_input = relationship("RawOrderInput", back_populates="confirmed_orders")
    parse_result = relationship("AIParseResult", back_populates="confirmed_orders")
    
    def set_items(self, items: List[Dict[str, Any]]):
        """設置商品列表"""
        self.items_json = json.dumps(items, ensure_ascii=False)
        self.total_items = sum(item.get('quantity', 0) for item in items)
    
    def get_items(self) -> List[Dict[str, Any]]:
        """獲取商品列表"""
        if self.items_json:
            try:
                return json.loads(self.items_json)
            except json.JSONDecodeError:
                return []
        return []
    
    def set_modifications(self, modifications: Dict[str, Any]):
        """記錄用戶修改"""
        self.modifications_json = json.dumps(modifications, ensure_ascii=False)
        self.user_modified = True
    
    def get_modifications(self) -> Dict[str, Any]:
        """獲取修改記錄"""
        if self.modifications_json:
            try:
                return json.loads(self.modifications_json)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'order_id': self.order_id,
            'sender_name': self.sender_name,
            'sender_phone': self.sender_phone,
            'receiver_name': self.receiver_name,
            'receiver_phone': self.receiver_phone,
            'shipping_address': self.shipping_address,
            'shipping_date': self.shipping_date,
            'items': self.get_items(),
            'total_items': self.total_items,
            'user_modified': self.user_modified,
            'google_sheets_synced': self.google_sheets_synced,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class LearningSample(Base):
    """學習樣本表"""
    __tablename__ = 'learning_samples'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_input_id = Column(Integer, ForeignKey('raw_order_inputs.id'))
    input_text = Column(Text, nullable=False)
    expected_output_json = Column(Text, nullable=False)
    sample_type = Column(String(20), nullable=False, index=True)  # positive, negative, edge_case
    quality_score = Column(Real, default=1.0, index=True)
    validation_status = Column(String(20), default='pending')  # pending, validated, rejected
    validator_id = Column(String(100))
    tags = Column(String(500))  # 用逗號分隔的標籤
    notes = Column(Text)
    usage_count = Column(Integer, default=0)
    effectiveness_score = Column(Real)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 關聯
    raw_input = relationship("RawOrderInput", back_populates="learning_samples")
    quality_evaluations = relationship("SampleQualityEvaluation", back_populates="sample")
    
    def set_expected_output(self, orders: List[Dict[str, Any]]):
        """設置期望輸出"""
        self.expected_output_json = json.dumps(orders, ensure_ascii=False)
    
    def get_expected_output(self) -> List[Dict[str, Any]]:
        """獲取期望輸出"""
        if self.expected_output_json:
            try:
                return json.loads(self.expected_output_json)
            except json.JSONDecodeError:
                return []
        return []
    
    def add_tag(self, tag: str):
        """添加標籤"""
        if self.tags:
            tags_list = self.tags.split(',')
            if tag not in tags_list:
                tags_list.append(tag)
                self.tags = ','.join(tags_list)
        else:
            self.tags = tag
    
    def get_tags(self) -> List[str]:
        """獲取標籤列表"""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',') if tag.strip()]
        return []
    
    def increment_usage(self):
        """增加使用次數"""
        self.usage_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'input_text': self.input_text,
            'expected_output': self.get_expected_output(),
            'sample_type': self.sample_type,
            'quality_score': self.quality_score,
            'validation_status': self.validation_status,
            'tags': self.get_tags(),
            'notes': self.notes,
            'usage_count': self.usage_count,
            'effectiveness_score': self.effectiveness_score,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DSPyTrainingLog(Base):
    """DSPy 模型訓練記錄表"""
    __tablename__ = 'dspy_training_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    training_session_id = Column(String(100), nullable=False, index=True)
    model_name = Column(String(100), nullable=False)
    training_samples_count = Column(Integer)
    validation_samples_count = Column(Integer)
    training_start_time = Column(DateTime)
    training_end_time = Column(DateTime)
    training_status = Column(String(20))  # running, completed, failed
    accuracy_score = Column(Real)
    f1_score = Column(Real)
    model_config_json = Column(Text)
    performance_metrics_json = Column(Text)
    model_path = Column(String(500))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def set_model_config(self, config: Dict[str, Any]):
        """設置模型配置"""
        self.model_config_json = json.dumps(config, ensure_ascii=False)
    
    def get_model_config(self) -> Dict[str, Any]:
        """獲取模型配置"""
        if self.model_config_json:
            try:
                return json.loads(self.model_config_json)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def set_performance_metrics(self, metrics: Dict[str, Any]):
        """設置性能指標"""
        self.performance_metrics_json = json.dumps(metrics, ensure_ascii=False)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """獲取性能指標"""
        if self.performance_metrics_json:
            try:
                return json.loads(self.performance_metrics_json)
            except json.JSONDecodeError:
                return {}
        return {}


# 已移除 MLflowExperimentLog：追蹤改用 Langfuse，不再落地實驗記錄。
# 既有資料庫檔案裡的 mlflow_experiment_logs 表不會自動刪除，但已無任何程式讀寫。


class SampleQualityEvaluation(Base):
    """樣本品質評估記錄表"""
    __tablename__ = 'sample_quality_evaluations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sample_id = Column(Integer, ForeignKey('learning_samples.id'), nullable=False)
    evaluator_type = Column(String(20), nullable=False)  # human, auto, ai
    evaluator_id = Column(String(100))
    quality_dimensions_json = Column(Text)  # 各維度分數
    overall_quality_score = Column(Real, nullable=False)
    feedback_text = Column(Text)
    evaluation_time = Column(DateTime, default=datetime.utcnow)
    
    # 關聯
    sample = relationship("LearningSample", back_populates="quality_evaluations")
    
    def set_quality_dimensions(self, dimensions: Dict[str, float]):
        """設置品質評估維度分數"""
        self.quality_dimensions_json = json.dumps(dimensions, ensure_ascii=False)
    
    def get_quality_dimensions(self) -> Dict[str, float]:
        """獲取品質評估維度分數"""
        if self.quality_dimensions_json:
            try:
                return json.loads(self.quality_dimensions_json)
            except json.JSONDecodeError:
                return {}
        return {}


class SystemPerformanceLog(Base):
    """系統性能監控表"""
    __tablename__ = 'system_performance_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_type = Column(String(50), nullable=False, index=True)
    operation_id = Column(String(100))
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    duration_ms = Column(Integer)
    memory_usage_mb = Column(Real)
    cpu_usage_percent = Column(Real)
    success = Column(Boolean)
    error_details = Column(Text)
    metadata_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def set_metadata(self, metadata: Dict[str, Any]):
        """設置額外元數據"""
        self.metadata_json = json.dumps(metadata, ensure_ascii=False)
    
    def get_metadata(self) -> Dict[str, Any]:
        """獲取額外元數據"""
        if self.metadata_json:
            try:
                return json.loads(self.metadata_json)
            except json.JSONDecodeError:
                return {}
        return {}


# 資料庫連接管理類
class DatabaseManager:
    """資料庫管理器"""
    
    def __init__(self, database_url: str = "sqlite:///order_learning_system.db"):
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def create_tables(self):
        """創建所有表"""
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self):
        """獲取資料庫會話"""
        return self.SessionLocal()
    
    def close_session(self, session):
        """關閉資料庫會話"""
        session.close()


# 全域資料庫管理器實例
db_manager = DatabaseManager()