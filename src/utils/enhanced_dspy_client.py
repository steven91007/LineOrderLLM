"""
增強的 DSPy 訂單解析客戶端
整合資料收集與學習功能（LLM 追蹤由 Langfuse 負責，見 langfuse_tracing.py）
"""
import time
import uuid
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import logging

from .dspy_client import DSPyOrderClient
from ..services.order_data_collector import order_data_collector
from ..services.dspy_learning_manager import dspy_learning_manager

logger = logging.getLogger(__name__)


class EnhancedDSPyOrderClient(DSPyOrderClient):
    """
    增強的 DSPy 訂單解析客戶端
    
    新增功能：
    1. 自動資料收集
    2. 性能監控
    3. 學習樣本自動生成
    4. 模型持續改進
    """

    def __init__(
        self,
        openai_api_key: str,
        enable_data_collection: bool = True,
        enable_auto_learning: bool = True
    ):
        """
        初始化增強客戶端

        Args:
            openai_api_key: OpenAI API 密鑰
            enable_data_collection: 是否啟用資料收集
            enable_auto_learning: 是否啟用自動學習
        """
        super().__init__(openai_api_key)

        self.enable_data_collection = enable_data_collection
        self.enable_auto_learning = enable_auto_learning

        self.session_id = str(uuid.uuid4())


    def parse_order(
        self, 
        order_text: str, 
        user_id: str = None,
        collect_data: bool = None
    ) -> Dict[str, Any]:
        """
        解析訂單（增強版本）
        
        Args:
            order_text: 訂單文字
            user_id: 用戶ID
            collect_data: 是否收集數據（覆蓋全域設置）
            
        Returns:
            Dict: 解析結果
        """
        start_time = datetime.utcnow()
        operation_id = str(uuid.uuid4())
        raw_input_id = None
        parse_result_id = None
        
        # 決定是否收集資料
        should_collect_data = (collect_data if collect_data is not None 
                             else self.enable_data_collection)
        
        try:
            # 記錄原始輸入
            if should_collect_data and user_id:
                raw_input_id = order_data_collector.record_raw_input(
                    user_id=user_id,
                    input_text=order_text,
                    session_id=self.session_id
                )
            
            # 調用原始解析方法
            parse_start_time = time.time()
            result = super().parse_order(order_text)
            parse_end_time = time.time()
            
            parsing_time_ms = int((parse_end_time - parse_start_time) * 1000)
            
            # 記錄解析結果
            if should_collect_data and raw_input_id:
                parse_result_id = order_data_collector.record_ai_parse_result(
                    raw_input_id=raw_input_id,
                    parser_type='dspy_enhanced',
                    parser_version='1.0',
                    raw_output=json.dumps(result, ensure_ascii=False),
                    parsed_orders=result.get('data', {}).get('orders', []) if result['success'] else [],
                    parsing_success=result['success'],
                    parsing_time_ms=parsing_time_ms,
                    error_message=result.get('error') if not result['success'] else None,
                    confidence_score=self._calculate_confidence_score(result)
                )
            
            # 自動學習觸發（成功解析的情況下）
            if (self.enable_auto_learning and result['success'] and 
                raw_input_id and should_collect_data):
                self._trigger_auto_learning_check(raw_input_id)
            
            # 添加增強資訊到結果
            result.update({
                'session_id': self.session_id,
                'operation_id': operation_id,
                'raw_input_id': raw_input_id,
                'parse_result_id': parse_result_id,
                'parsing_time_ms': parsing_time_ms
            })
            
            end_time = datetime.utcnow()
            
            # 記錄系統性能
            if should_collect_data:
                order_data_collector.record_system_performance(
                    operation_type='parse_order',
                    operation_id=operation_id,
                    start_time=start_time,
                    end_time=end_time,
                    success=result['success'],
                    error_details=result.get('error') if not result['success'] else None,
                    metadata={
                        'parser_type': 'dspy_enhanced',
                        'order_length': len(order_text),
                        'orders_parsed': len(result.get('data', {}).get('orders', [])),
                        'has_user_id': user_id is not None
                    }
                )
            
            return result
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error in enhanced parse_order: {error_message}")
            
            # 記錄失敗的解析嘗試
            if should_collect_data and raw_input_id:
                order_data_collector.record_ai_parse_result(
                    raw_input_id=raw_input_id,
                    parser_type='dspy_enhanced',
                    parser_version='1.0',
                    raw_output='',
                    parsed_orders=[],
                    parsing_success=False,
                    parsing_time_ms=0,
                    error_message=error_message
                )
            
            # 記錄系統性能
            if should_collect_data:
                order_data_collector.record_system_performance(
                    operation_type='parse_order',
                    operation_id=operation_id,
                    start_time=start_time,
                    end_time=datetime.utcnow(),
                    success=False,
                    error_details=error_message,
                    metadata={
                        'parser_type': 'dspy_enhanced',
                        'order_length': len(order_text),
                        'exception_type': type(e).__name__
                    }
                )
            
            return {
                'success': False,
                'error': error_message,
                'session_id': self.session_id,
                'operation_id': operation_id,
                'raw_input_id': raw_input_id
            }

    def record_confirmed_orders(
        self,
        raw_input_id: int,
        parse_result_id: int,
        confirmed_orders: List[Dict[str, Any]],
        user_modifications: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        記錄確認的訂單
        
        Args:
            raw_input_id: 原始輸入ID
            parse_result_id: 解析結果ID
            confirmed_orders: 確認的訂單列表
            user_modifications: 用戶修改記錄
            
        Returns:
            List[str]: 記錄的訂單編號列表
        """
        if not self.enable_data_collection:
            return []
        
        try:
            order_ids = order_data_collector.record_multiple_confirmed_orders(
                raw_input_id=raw_input_id,
                parse_result_id=parse_result_id,
                orders_data=confirmed_orders,
                user_modifications=user_modifications
            )
            
            # 自動創建學習樣本
            if self.enable_auto_learning and order_ids:
                sample_id = order_data_collector.auto_create_learning_sample_from_confirmed_order(
                    raw_input_id=raw_input_id
                )
                logger.info(f"Auto-created learning sample ID: {sample_id}")
            
            return order_ids
            
        except Exception as e:
            logger.error(f"Error recording confirmed orders: {e}")
            return []
    
    def _calculate_confidence_score(self, result: Dict[str, Any]) -> Optional[float]:
        """
        計算解析信心度分數
        
        Args:
            result: 解析結果
            
        Returns:
            float: 信心度分數 (0-1)
        """
        if not result['success']:
            return 0.0
        
        orders = result.get('data', {}).get('orders', [])
        if not orders:
            return 0.0
        
        total_score = 0.0
        total_factors = 0
        
        for order in orders:
            order_score = 0.0
            factors = 0
            
            # 必要欄位存在性檢查
            if order.get('receiver_name'):
                order_score += 1.0
                factors += 1
            
            if order.get('receiver_phone'):
                order_score += 1.0
                factors += 1
            
            if order.get('shipping_address'):
                order_score += 1.0
                factors += 1
            
            # 商品資訊完整性
            items = order.get('items', [])
            if items:
                order_score += 1.0
                factors += 1
                
                # 商品數量合理性
                for item in items:
                    if item.get('quantity', 0) > 0:
                        order_score += 0.5
                        factors += 0.5
            
            # 可選欄位額外加分
            if order.get('shipping_date'):
                order_score += 0.5
                factors += 0.5
            
            if order.get('sender_name') or order.get('sender_phone'):
                order_score += 0.5
                factors += 0.5
            
            if factors > 0:
                total_score += order_score / factors
                total_factors += 1
        
        return total_score / total_factors if total_factors > 0 else 0.0
    
    def _trigger_auto_learning_check(self, raw_input_id: int):
        """
        觸發自動學習檢查
        
        Args:
            raw_input_id: 原始輸入ID
        """
        try:
            # 每100次成功解析觸發一次學習樣本收集
            import random
            if random.randint(1, 100) == 1:  # 1% 機率觸發
                logger.info("Triggering automatic learning sample collection")
                collected_count = dspy_learning_manager.collect_training_samples_from_confirmed_orders(
                    days=7,  # 收集過去7天的數據
                    min_quality_threshold=0.8
                )
                logger.info(f"Collected {collected_count} new learning samples")
                
                # 如果收集到足夠樣本，考慮重新訓練
                if collected_count > 50:
                    logger.info("Sufficient samples collected, considering model retraining")
                    # 這裡可以添加自動重新訓練邏輯
                    
        except Exception as e:
            logger.warning(f"Auto learning check failed: {e}")
    
    def get_session_statistics(self) -> Dict[str, Any]:
        """
        獲取當前會話統計信息
        
        Returns:
            Dict: 會話統計信息
        """
        if not self.enable_data_collection:
            return {"error": "Data collection not enabled"}
        
        return order_data_collector.get_processing_statistics(days=1)
    
    def trigger_manual_learning_update(self) -> Dict[str, Any]:
        """
        手動觸發學習更新
        
        Returns:
            Dict: 更新結果
        """
        if not self.enable_auto_learning:
            return {"error": "Auto learning not enabled"}
        
        try:
            # 收集訓練樣本
            collected_samples = dspy_learning_manager.collect_training_samples_from_confirmed_orders(
                days=30, 
                min_quality_threshold=0.8
            )
            
            # 創建負面樣本
            negative_samples = dspy_learning_manager.create_negative_samples(count=20)
            
            # 創建邊界案例樣本
            edge_cases = dspy_learning_manager.create_edge_case_samples(count=10)
            
            # 如果有足夠樣本，進行訓練
            total_samples = collected_samples + negative_samples + edge_cases
            
            training_result = None
            if total_samples > 30:  # 至少需要30個樣本
                # 準備訓練數據
                train_examples, val_examples = dspy_learning_manager.prepare_training_data(
                    min_quality_score=0.8,
                    train_ratio=0.8
                )
                
                if len(train_examples) >= 20:  # 確保有足夠的訓練樣本
                    # 開始訓練
                    training_session_id = dspy_learning_manager.train_model(
                        train_examples=train_examples,
                        val_examples=val_examples,
                        model_name=f"enhanced_parser_{datetime.now().strftime('%Y%m%d_%H%M')}"
                    )
                    training_result = training_session_id
            
            return {
                "success": True,
                "collected_positive_samples": collected_samples,
                "created_negative_samples": negative_samples,
                "created_edge_cases": edge_cases,
                "total_new_samples": total_samples,
                "training_triggered": training_result is not None,
                "training_session_id": training_result
            }
            
        except Exception as e:
            logger.error(f"Manual learning update failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def evaluate_current_performance(self) -> Dict[str, Any]:
        """
        評估當前模型性能
        
        Returns:
            Dict: 性能評估結果
        """
        if not self.enable_auto_learning:
            return {"error": "Auto learning not enabled"}
        
        try:
            return dspy_learning_manager.evaluate_model_performance(test_samples_count=50)
        except Exception as e:
            logger.error(f"Performance evaluation failed: {e}")
            return {"error": str(e)}