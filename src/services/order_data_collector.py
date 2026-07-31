"""
訂單資料收集服務
記錄所有訂單處理過程的輸入輸出，為機器學習提供訓練數據
"""
import json
import time
import traceback
import psutil
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import logging
import mlflow
import mlflow.dspy

from ..database.models import (
    db_manager, RawOrderInput, AIParseResult, ConfirmedOrder, 
    LearningSample, MLflowExperimentLog, SystemPerformanceLog
)

logger = logging.getLogger(__name__)


class OrderDataCollector:
    """
    訂單資料收集器
    
    職責：
    1. 記錄原始訂單輸入
    2. 記錄AI解析結果和性能指標
    3. 記錄最終確認訂單
    4. 生成學習樣本
    5. 整合MLflow追蹤
    6. 性能監控
    """
    
    def __init__(self, enable_mlflow: bool = True):
        """
        初始化資料收集器
        
        Args:
            enable_mlflow: 是否啟用MLflow追蹤
        """
        self.enable_mlflow = enable_mlflow
        
        # 確保資料庫表已創建
        try:
            db_manager.create_tables()
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
        
        # 設置MLflow
        if self.enable_mlflow:
            try:
                mlflow.set_experiment("line_order_data_collection")
            except Exception as e:
                logger.warning(f"Failed to set MLflow experiment: {e}")
                self.enable_mlflow = False
    
    def record_raw_input(
        self, 
        user_id: str, 
        input_text: str, 
        session_id: Optional[str] = None
    ) -> Optional[int]:
        """
        記錄原始訂單輸入
        
        Args:
            user_id: 用戶ID
            input_text: 原始輸入文字
            session_id: 會話ID
            
        Returns:
            int: 記錄ID，失敗時返回None
        """
        session = db_manager.get_session()
        try:
            # 檢查是否已存在相同的輸入（基於hash）
            raw_input = RawOrderInput(user_id, input_text, session_id)
            
            existing = session.query(RawOrderInput).filter_by(
                input_hash=raw_input.input_hash
            ).first()
            
            if existing:
                logger.info(f"Duplicate input detected, using existing record ID: {existing.id}")
                return existing.id
            
            session.add(raw_input)
            session.commit()
            
            logger.info(f"Raw input recorded with ID: {raw_input.id}")
            return raw_input.id
            
        except SQLAlchemyError as e:
            logger.error(f"Database error recording raw input: {e}")
            session.rollback()
            return None
        finally:
            db_manager.close_session(session)
    
    def record_ai_parse_result(
        self,
        raw_input_id: int,
        parser_type: str,
        parser_version: str,
        raw_output: str,
        parsed_orders: List[Dict[str, Any]],
        parsing_success: bool,
        parsing_time_ms: int,
        error_message: Optional[str] = None,
        confidence_score: Optional[float] = None
    ) -> Optional[int]:
        """
        記錄AI解析結果
        
        Args:
            raw_input_id: 原始輸入記錄ID
            parser_type: 解析器類型 (dspy, openai等)
            parser_version: 解析器版本
            raw_output: AI原始輸出
            parsed_orders: 解析後的訂單列表
            parsing_success: 解析是否成功
            parsing_time_ms: 解析耗時(毫秒)
            error_message: 錯誤訊息
            confidence_score: 信心度分數
            
        Returns:
            int: 解析結果記錄ID
        """
        session = db_manager.get_session()
        try:
            parse_result = AIParseResult(
                raw_input_id=raw_input_id,
                parser_type=parser_type,
                parsing_success=parsing_success
            )
            
            parse_result.parser_version = parser_version
            parse_result.raw_output = raw_output
            parse_result.set_parsed_orders(parsed_orders)
            parse_result.parsing_time_ms = parsing_time_ms
            parse_result.error_message = error_message
            parse_result.confidence_score = confidence_score
            
            session.add(parse_result)
            session.commit()
            
            # MLflow 追蹤
            if self.enable_mlflow:
                self._log_parse_result_to_mlflow(parse_result, session)
            
            logger.info(f"AI parse result recorded with ID: {parse_result.id}")
            return parse_result.id
            
        except SQLAlchemyError as e:
            logger.error(f"Database error recording parse result: {e}")
            session.rollback()
            return None
        finally:
            db_manager.close_session(session)
    
    def record_confirmed_order(
        self,
        raw_input_id: int,
        parse_result_id: Optional[int],
        order_data: Dict[str, Any],
        user_modifications: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        記錄最終確認的訂單
        
        Args:
            raw_input_id: 原始輸入記錄ID
            parse_result_id: 解析結果記錄ID
            order_data: 訂單資料
            user_modifications: 用戶修改記錄
            
        Returns:
            str: 訂單編號
        """
        session = db_manager.get_session()
        try:
            confirmed_order = ConfirmedOrder(
                raw_input_id=raw_input_id,
                parse_result_id=parse_result_id,
                order_id=order_data['order_id'],
                sender_name=order_data.get('sender_name'),
                sender_phone=order_data.get('sender_phone'),
                receiver_name=order_data['receiver_name'],
                receiver_phone=order_data['receiver_phone'],
                shipping_address=order_data['shipping_address'],
                shipping_date=order_data.get('shipping_date')
            )
            
            confirmed_order.set_items(order_data.get('items', []))
            
            if user_modifications:
                confirmed_order.set_modifications(user_modifications)
            
            session.add(confirmed_order)
            session.commit()
            
            logger.info(f"Confirmed order recorded: {order_data['order_id']}")
            return order_data['order_id']
            
        except SQLAlchemyError as e:
            logger.error(f"Database error recording confirmed order: {e}")
            session.rollback()
            return None
        finally:
            db_manager.close_session(session)
    
    def record_multiple_confirmed_orders(
        self,
        raw_input_id: int,
        parse_result_id: Optional[int],
        orders_data: List[Dict[str, Any]],
        user_modifications: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        批量記錄多個確認訂單
        
        Args:
            raw_input_id: 原始輸入記錄ID
            parse_result_id: 解析結果記錄ID
            orders_data: 訂單資料列表
            user_modifications: 用戶修改記錄
            
        Returns:
            List[str]: 成功記錄的訂單編號列表
        """
        recorded_order_ids = []
        
        for order_data in orders_data:
            order_id = self.record_confirmed_order(
                raw_input_id=raw_input_id,
                parse_result_id=parse_result_id,
                order_data=order_data,
                user_modifications=user_modifications
            )
            if order_id:
                recorded_order_ids.append(order_id)
        
        return recorded_order_ids
    
    def create_learning_sample(
        self,
        raw_input_id: int,
        input_text: str,
        expected_output: List[Dict[str, Any]],
        sample_type: str = 'positive',
        quality_score: float = 1.0,
        tags: List[str] = None,
        notes: str = None
    ) -> Optional[int]:
        """
        創建學習樣本
        
        Args:
            raw_input_id: 原始輸入記錄ID
            input_text: 輸入文字
            expected_output: 期望的輸出
            sample_type: 樣本類型 (positive, negative, edge_case)
            quality_score: 品質分數
            tags: 標籤列表
            notes: 備註
            
        Returns:
            int: 學習樣本ID
        """
        session = db_manager.get_session()
        try:
            learning_sample = LearningSample(
                raw_input_id=raw_input_id,
                input_text=input_text,
                sample_type=sample_type,
                quality_score=quality_score,
                notes=notes
            )
            
            learning_sample.set_expected_output(expected_output)
            
            if tags:
                for tag in tags:
                    learning_sample.add_tag(tag)
            
            session.add(learning_sample)
            session.commit()
            
            logger.info(f"Learning sample created with ID: {learning_sample.id}")
            return learning_sample.id
            
        except SQLAlchemyError as e:
            logger.error(f"Database error creating learning sample: {e}")
            session.rollback()
            return None
        finally:
            db_manager.close_session(session)
    
    def auto_create_learning_sample_from_confirmed_order(
        self, 
        raw_input_id: int
    ) -> Optional[int]:
        """
        根據確認訂單自動創建學習樣本
        
        Args:
            raw_input_id: 原始輸入記錄ID
            
        Returns:
            int: 創建的學習樣本ID
        """
        session = db_manager.get_session()
        try:
            # 獲取原始輸入和確認訂單
            raw_input = session.query(RawOrderInput).filter_by(id=raw_input_id).first()
            confirmed_orders = session.query(ConfirmedOrder).filter_by(
                raw_input_id=raw_input_id
            ).all()
            
            if not raw_input or not confirmed_orders:
                logger.warning(f"Cannot create learning sample: missing data for input ID {raw_input_id}")
                return None
            
            # 構建期望輸出
            expected_output = []
            sample_tags = []
            
            for order in confirmed_orders:
                order_dict = {
                    "sender_name": order.sender_name,
                    "sender_phone": order.sender_phone,
                    "receiver_name": order.receiver_name,
                    "receiver_phone": order.receiver_phone,
                    "items": order.get_items(),
                    "shipping_date": order.shipping_date,
                    "shipping_address": order.shipping_address
                }
                expected_output.append(order_dict)
                
                # 自動添加標籤
                if len(confirmed_orders) > 1:
                    sample_tags.append('multi_order')
                
                if order.shipping_date:
                    sample_tags.append('date_parsing')
                
                if order.user_modified:
                    sample_tags.append('user_modified')
            
            # 確定樣本類型
            sample_type = 'positive'
            quality_score = 1.0
            
            # 如果有用戶修改，降低品質分數
            if any(order.user_modified for order in confirmed_orders):
                quality_score = 0.8
                sample_type = 'positive'  # 仍然是正面樣本，但品質較低
            
            # 創建學習樣本
            return self.create_learning_sample(
                raw_input_id=raw_input_id,
                input_text=raw_input.input_text,
                expected_output=expected_output,
                sample_type=sample_type,
                quality_score=quality_score,
                tags=list(set(sample_tags)),  # 去重
                notes="Auto-generated from confirmed order"
            )
            
        except SQLAlchemyError as e:
            logger.error(f"Database error auto-creating learning sample: {e}")
            return None
        finally:
            db_manager.close_session(session)
    
    def record_system_performance(
        self,
        operation_type: str,
        operation_id: str,
        start_time: datetime,
        end_time: datetime,
        success: bool,
        error_details: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        記錄系統性能指標
        
        Args:
            operation_type: 操作類型
            operation_id: 操作ID
            start_time: 開始時間
            end_time: 結束時間
            success: 操作是否成功
            error_details: 錯誤詳情
            metadata: 額外元數據
            
        Returns:
            int: 性能記錄ID
        """
        session = db_manager.get_session()
        try:
            # 計算性能指標
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            # 獲取系統資源使用情況
            process = psutil.Process(os.getpid())
            memory_usage_mb = process.memory_info().rss / 1024 / 1024
            cpu_usage_percent = process.cpu_percent()
            
            perf_log = SystemPerformanceLog(
                operation_type=operation_type,
                operation_id=operation_id,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                memory_usage_mb=memory_usage_mb,
                cpu_usage_percent=cpu_usage_percent,
                success=success,
                error_details=error_details
            )
            
            if metadata:
                perf_log.set_metadata(metadata)
            
            session.add(perf_log)
            session.commit()
            
            logger.debug(f"Performance log recorded for {operation_type}: {duration_ms}ms")
            return perf_log.id
            
        except SQLAlchemyError as e:
            logger.error(f"Database error recording performance: {e}")
            session.rollback()
            return None
        finally:
            db_manager.close_session(session)
    
    def _log_parse_result_to_mlflow(self, parse_result: AIParseResult, session: Session):
        """記錄解析結果到MLflow"""
        try:
            with mlflow.start_run(nested=True):
                # 記錄參數
                mlflow.log_param("parser_type", parse_result.parser_type)
                mlflow.log_param("parser_version", parse_result.parser_version)
                
                # 記錄指標
                mlflow.log_metric("parsing_success", 1 if parse_result.parsing_success else 0)
                mlflow.log_metric("parsing_time_ms", parse_result.parsing_time_ms or 0)
                
                if parse_result.confidence_score:
                    mlflow.log_metric("confidence_score", parse_result.confidence_score)
                
                # 記錄解析結果數量
                parsed_orders = parse_result.get_parsed_orders()
                mlflow.log_metric("parsed_orders_count", len(parsed_orders))
                
                # 記錄到資料庫
                mlflow_log = MLflowExperimentLog(
                    experiment_id=mlflow.active_run().info.experiment_id,
                    run_id=mlflow.active_run().info.run_id,
                    experiment_name="line_order_data_collection",
                    raw_input_id=parse_result.raw_input_id,
                    parse_result_id=parse_result.id,
                    status="FINISHED" if parse_result.parsing_success else "FAILED"
                )
                
                session.add(mlflow_log)
                session.commit()
                
        except Exception as e:
            logger.warning(f"Failed to log to MLflow: {e}")
    
    def get_learning_samples(
        self, 
        sample_type: Optional[str] = None,
        min_quality_score: float = 0.0,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        獲取學習樣本
        
        Args:
            sample_type: 樣本類型過濾
            min_quality_score: 最低品質分數
            tags: 標籤過濾
            limit: 返回數量限制
            
        Returns:
            List[Dict]: 學習樣本列表
        """
        session = db_manager.get_session()
        try:
            query = session.query(LearningSample).filter(
                LearningSample.quality_score >= min_quality_score
            )
            
            if sample_type:
                query = query.filter(LearningSample.sample_type == sample_type)
            
            if tags:
                for tag in tags:
                    query = query.filter(LearningSample.tags.contains(tag))
            
            if limit:
                query = query.limit(limit)
            
            samples = query.all()
            return [sample.to_dict() for sample in samples]
            
        except SQLAlchemyError as e:
            logger.error(f"Database error fetching learning samples: {e}")
            return []
        finally:
            db_manager.close_session(session)
    
    def get_processing_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        獲取處理統計數據
        
        Args:
            days: 統計天數
            
        Returns:
            Dict: 統計數據
        """
        session = db_manager.get_session()
        try:
            from datetime import timedelta
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # 基本統計
            total_inputs = session.query(RawOrderInput).filter(
                RawOrderInput.created_at >= cutoff_date
            ).count()
            
            successful_parses = session.query(AIParseResult).filter(
                AIParseResult.created_at >= cutoff_date,
                AIParseResult.parsing_success == True
            ).count()
            
            total_parses = session.query(AIParseResult).filter(
                AIParseResult.created_at >= cutoff_date
            ).count()
            
            confirmed_orders = session.query(ConfirmedOrder).filter(
                ConfirmedOrder.created_at >= cutoff_date
            ).count()
            
            learning_samples = session.query(LearningSample).filter(
                LearningSample.created_at >= cutoff_date
            ).count()
            
            # 計算成功率
            parse_success_rate = (successful_parses / total_parses * 100) if total_parses > 0 else 0
            
            return {
                "period_days": days,
                "total_inputs": total_inputs,
                "total_parses": total_parses,
                "successful_parses": successful_parses,
                "parse_success_rate": round(parse_success_rate, 2),
                "confirmed_orders": confirmed_orders,
                "learning_samples": learning_samples,
                "orders_per_input": round(confirmed_orders / total_inputs, 2) if total_inputs > 0 else 0
            }
            
        except SQLAlchemyError as e:
            logger.error(f"Database error fetching statistics: {e}")
            return {}
        finally:
            db_manager.close_session(session)


# 創建全域實例
order_data_collector = OrderDataCollector()