"""
DSPy 學習樣本管理系統
負責管理訓練樣本、模型訓練和性能評估
"""
import json
import uuid
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
import mlflow
import mlflow.dspy
import dspy
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging

from ..database.models import (
    db_manager, LearningSample, DSPyTrainingLog, 
    AIParseResult, RawOrderInput, ConfirmedOrder
)
from ..utils.dspy_modules.unified_parser import UnifiedOrderParser
from .order_data_collector import order_data_collector

logger = logging.getLogger(__name__)


class DSPyLearningManager:
    """
    DSPy 學習樣本管理器
    
    功能：
    1. 訓練樣本管理和品質控制
    2. DSPy 模型訓練和評估
    3. 持續學習和模型改進
    4. 樣本有效性分析
    """
    
    def __init__(self):
        """初始化學習管理器"""
        self.unified_parser = UnifiedOrderParser()
        
        # 設置MLflow實驗
        try:
            mlflow.set_experiment("dspy_learning_experiment")
        except Exception as e:
            logger.warning(f"Failed to set MLflow experiment: {e}")
    
    def collect_training_samples_from_confirmed_orders(
        self, 
        days: int = 30,
        min_quality_threshold: float = 0.8
    ) -> int:
        """
        從確認訂單中收集訓練樣本
        
        Args:
            days: 收集過去多少天的數據
            min_quality_threshold: 最低品質閾值
            
        Returns:
            int: 收集到的樣本數量
        """
        session = db_manager.get_session()
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # 查詢最近的確認訂單，且沒有對應學習樣本的
            confirmed_orders_query = session.query(ConfirmedOrder).filter(
                ConfirmedOrder.created_at >= cutoff_date
            ).join(RawOrderInput).filter(
                ~RawOrderInput.id.in_(
                    session.query(LearningSample.raw_input_id).filter(
                        LearningSample.raw_input_id.isnot(None)
                    )
                )
            )
            
            collected_count = 0
            
            for confirmed_order in confirmed_orders_query:
                try:
                    # 獲取同一原始輸入的所有確認訂單
                    all_orders_for_input = session.query(ConfirmedOrder).filter_by(
                        raw_input_id=confirmed_order.raw_input_id
                    ).all()
                    
                    # 構建期望輸出
                    expected_output = []
                    quality_factors = []
                    tags = set()
                    
                    for order in all_orders_for_input:
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
                        
                        # 分析品質因素
                        if order.user_modified:
                            quality_factors.append(0.7)  # 用戶修改降低品質
                            tags.add('user_modified')
                        else:
                            quality_factors.append(1.0)
                        
                        # 添加標籤
                        if len(all_orders_for_input) > 1:
                            tags.add('multi_order')
                        if order.shipping_date:
                            tags.add('date_parsing')
                        if order.sender_name or order.sender_phone:
                            tags.add('sender_info')
                    
                    # 計算品質分數
                    quality_score = sum(quality_factors) / len(quality_factors)
                    
                    # 只有高品質樣本才收集
                    if quality_score >= min_quality_threshold:
                        raw_input = session.query(RawOrderInput).filter_by(
                            id=confirmed_order.raw_input_id
                        ).first()
                        
                        if raw_input:
                            learning_sample = LearningSample(
                                raw_input_id=raw_input.id,
                                input_text=raw_input.input_text,
                                sample_type='positive',
                                quality_score=quality_score,
                                validation_status='validated',
                                notes=f"Auto-collected from confirmed orders (quality: {quality_score:.2f})"
                            )
                            
                            learning_sample.set_expected_output(expected_output)
                            
                            # 添加標籤
                            for tag in tags:
                                learning_sample.add_tag(tag)
                            
                            session.add(learning_sample)
                            collected_count += 1
                    
                except Exception as e:
                    logger.error(f"Error processing confirmed order {confirmed_order.id}: {e}")
                    continue
            
            session.commit()
            logger.info(f"Collected {collected_count} training samples from confirmed orders")
            return collected_count
            
        except SQLAlchemyError as e:
            logger.error(f"Database error collecting training samples: {e}")
            session.rollback()
            return 0
        finally:
            db_manager.close_session(session)
    
    def create_negative_samples(
        self, 
        count: int = 50,
        error_types: List[str] = None
    ) -> int:
        """
        創建負面樣本（用於改進模型）
        
        Args:
            count: 要創建的負面樣本數量
            error_types: 錯誤類型列表
            
        Returns:
            int: 創建的負面樣本數量
        """
        if error_types is None:
            error_types = [
                'incomplete_info',
                'wrong_format', 
                'ambiguous_content',
                'mixed_languages',
                'invalid_dates'
            ]
        
        session = db_manager.get_session()
        try:
            created_count = 0
            
            # 獲取一些正面樣本作為基礎
            positive_samples = session.query(LearningSample).filter_by(
                sample_type='positive'
            ).limit(20).all()
            
            for error_type in error_types:
                samples_for_type = min(count // len(error_types), 10)
                
                for i in range(samples_for_type):
                    if positive_samples:
                        base_sample = random.choice(positive_samples)
                        corrupted_text = self._corrupt_text_for_error_type(
                            base_sample.input_text, error_type
                        )
                        
                        negative_sample = LearningSample(
                            input_text=corrupted_text,
                            sample_type='negative',
                            quality_score=1.0,  # 負面樣本也需要高品質
                            validation_status='validated',
                            notes=f"Auto-generated negative sample: {error_type}"
                        )
                        
                        negative_sample.set_expected_output([])  # 負面樣本期望空輸出
                        negative_sample.add_tag(f'negative_{error_type}')
                        
                        session.add(negative_sample)
                        created_count += 1
            
            session.commit()
            logger.info(f"Created {created_count} negative samples")
            return created_count
            
        except SQLAlchemyError as e:
            logger.error(f"Database error creating negative samples: {e}")
            session.rollback()
            return 0
        finally:
            db_manager.close_session(session)
    
    def _corrupt_text_for_error_type(self, original_text: str, error_type: str) -> str:
        """
        根據錯誤類型腐化文字，生成負面樣本
        
        Args:
            original_text: 原始文字
            error_type: 錯誤類型
            
        Returns:
            str: 腐化後的文字
        """
        if error_type == 'incomplete_info':
            # 移除一些關鍵信息
            text = original_text.replace('電話', '').replace('地址', '')
            return text[:len(text)//2]  # 截短文字
        
        elif error_type == 'wrong_format':
            # 打亂格式
            return original_text.replace('：', '').replace(' ', '').replace('\n', '')
        
        elif error_type == 'ambiguous_content':
            # 添加模糊信息
            return original_text + " 可能是這樣也可能是那樣不太確定"
        
        elif error_type == 'mixed_languages':
            # 添加英文
            return original_text + " Order details name phone address items"
        
        elif error_type == 'invalid_dates':
            # 添加無效日期
            return original_text + " 發貨日期：2月30日 星期八"
        
        return original_text
    
    def create_edge_case_samples(self, count: int = 30) -> int:
        """
        創建邊界案例樣本
        
        Args:
            count: 要創建的邊界案例數量
            
        Returns:
            int: 創建的邊界案例數量
        """
        session = db_manager.get_session()
        try:
            edge_cases = [
                {
                    'input': '🩷18A禮盒（100盒） 🌸寄件人：大批發商 收件人: 零售店 🌸電話：0912345678 🌸台北市中正區重慶南路100號',
                    'output': [{
                        "sender_name": "大批發商",
                        "sender_phone": None,
                        "receiver_name": "零售店",
                        "receiver_phone": "0912345678",
                        "items": [{"name": "18A禮盒", "quantity": 100}],
                        "shipping_date": None,
                        "shipping_address": "台北市中正區重慶南路100號"
                    }],
                    'tags': ['large_quantity', 'business_order']
                },
                {
                    'input': '收件人：王小明 電話：0912345678 地址：台北市信義區信義路五段7號101大樓89樓A室(靠窗戶邊的辦公桌)',
                    'output': [{
                        "sender_name": None,
                        "sender_phone": None,
                        "receiver_name": "王小明",
                        "receiver_phone": "0912345678",
                        "items": [],
                        "shipping_date": None,
                        "shipping_address": "台北市信義區信義路五段7號101大樓89樓A室(靠窗戶邊的辦公桌)"
                    }],
                    'tags': ['detailed_address', 'no_items']
                },
                {
                    'input': '明天送 18A禮盒 x1 給住在附近的老王',
                    'output': [{
                        "sender_name": None,
                        "sender_phone": None,
                        "receiver_name": "老王",
                        "receiver_phone": None,
                        "items": [{"name": "18A禮盒", "quantity": 1}],
                        "shipping_date": None,
                        "shipping_address": "附近"
                    }],
                    'tags': ['vague_info', 'relative_date']
                }
            ]
            
            created_count = 0
            
            for case in edge_cases[:count]:
                edge_sample = LearningSample(
                    input_text=case['input'],
                    sample_type='edge_case',
                    quality_score=1.0,
                    validation_status='validated',
                    notes="Hand-crafted edge case sample"
                )
                
                edge_sample.set_expected_output(case['output'])
                
                for tag in case['tags']:
                    edge_sample.add_tag(tag)
                
                session.add(edge_sample)
                created_count += 1
            
            session.commit()
            logger.info(f"Created {created_count} edge case samples")
            return created_count
            
        except SQLAlchemyError as e:
            logger.error(f"Database error creating edge case samples: {e}")
            session.rollback()
            return 0
        finally:
            db_manager.close_session(session)
    
    def prepare_training_data(
        self,
        min_quality_score: float = 0.8,
        train_ratio: float = 0.8,
        sample_types: List[str] = None
    ) -> Tuple[List[dspy.Example], List[dspy.Example]]:
        """
        準備訓練數據
        
        Args:
            min_quality_score: 最低品質分數
            train_ratio: 訓練集比例
            sample_types: 樣本類型列表
            
        Returns:
            Tuple: (訓練集, 驗證集)
        """
        if sample_types is None:
            sample_types = ['positive', 'negative', 'edge_case']
        
        session = db_manager.get_session()
        try:
            # 獲取高品質樣本
            query = session.query(LearningSample).filter(
                LearningSample.quality_score >= min_quality_score,
                LearningSample.validation_status == 'validated',
                LearningSample.sample_type.in_(sample_types)
            )
            
            all_samples = query.all()
            random.shuffle(all_samples)
            
            # 轉換為 DSPy Examples
            dspy_examples = []
            
            for sample in all_samples:
                try:
                    expected_output = sample.get_expected_output()
                    current_date = datetime.now().strftime('%Y-%m-%d (星期%s)' % 
                                                         ['一', '二', '三', '四', '五', '六', '日'][datetime.now().weekday()])
                    
                    example = dspy.Example(
                        order_text=sample.input_text,
                        current_date=current_date,
                        orders_json=json.dumps(expected_output, ensure_ascii=False)
                    ).with_inputs("order_text", "current_date")
                    
                    dspy_examples.append(example)
                    
                    # 增加使用計數
                    sample.increment_usage()
                    
                except Exception as e:
                    logger.warning(f"Failed to convert sample {sample.id} to DSPy example: {e}")
                    continue
            
            # 分割訓練集和驗證集
            split_idx = int(len(dspy_examples) * train_ratio)
            train_examples = dspy_examples[:split_idx]
            val_examples = dspy_examples[split_idx:]
            
            session.commit()
            
            logger.info(f"Prepared {len(train_examples)} training and {len(val_examples)} validation examples")
            return train_examples, val_examples
            
        except SQLAlchemyError as e:
            logger.error(f"Database error preparing training data: {e}")
            session.rollback()
            return [], []
        finally:
            db_manager.close_session(session)
    
    def train_model(
        self,
        train_examples: List[dspy.Example],
        val_examples: List[dspy.Example],
        model_name: str = "improved_unified_parser"
    ) -> Optional[str]:
        """
        訓練 DSPy 模型
        
        Args:
            train_examples: 訓練樣本
            val_examples: 驗證樣本
            model_name: 模型名稱
            
        Returns:
            str: 訓練會話ID
        """
        if not train_examples:
            logger.error("No training examples provided")
            return None
        
        training_session_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        session = db_manager.get_session()
        try:
            # 記錄訓練開始
            training_log = DSPyTrainingLog(
                training_session_id=training_session_id,
                model_name=model_name,
                training_samples_count=len(train_examples),
                validation_samples_count=len(val_examples),
                training_start_time=start_time,
                training_status='running'
            )
            
            session.add(training_log)
            session.commit()
            
            # 開始 MLflow 運行
            with mlflow.start_run(run_name=f"train_{model_name}_{training_session_id[:8]}"):
                # 記錄參數
                mlflow.log_param("model_name", model_name)
                mlflow.log_param("training_samples", len(train_examples))
                mlflow.log_param("validation_samples", len(val_examples))
                
                # 創建新的解析器實例用於訓練
                parser = UnifiedOrderParser()
                
                # 使用訓練樣本來設置 few-shot examples
                # 注意：這裡我們更新解析器的 examples
                parser.examples = train_examples
                
                # 評估模型性能
                val_predictions = []
                val_targets = []
                
                for example in val_examples:
                    try:
                        # 使用解析器進行預測
                        prediction = parser.forward(
                            order_text=example.order_text
                        )
                        
                        # 比較預測結果和期望結果
                        predicted_orders = json.loads(prediction.orders_json)
                        expected_orders = json.loads(example.orders_json)
                        
                        # 簡單的準確度計算（基於訂單數量匹配）
                        val_predictions.append(len(predicted_orders))
                        val_targets.append(len(expected_orders))
                        
                    except Exception as e:
                        logger.warning(f"Error evaluating example: {e}")
                        val_predictions.append(0)
                        val_targets.append(1)
                
                # 計算性能指標
                accuracy = accuracy_score(
                    [1 if p > 0 else 0 for p in val_targets],
                    [1 if p > 0 else 0 for p in val_predictions]
                )
                
                precision, recall, f1, _ = precision_recall_fscore_support(
                    [1 if p > 0 else 0 for p in val_targets],
                    [1 if p > 0 else 0 for p in val_predictions],
                    average='weighted',
                    zero_division=0
                )
                
                # 記錄指標
                mlflow.log_metric("accuracy", accuracy)
                mlflow.log_metric("precision", precision)
                mlflow.log_metric("recall", recall)
                mlflow.log_metric("f1_score", f1)
                
                # 更新訓練記錄
                training_log.training_end_time = datetime.utcnow()
                training_log.training_status = 'completed'
                training_log.accuracy_score = accuracy
                training_log.f1_score = f1
                training_log.notes = f"Training completed successfully with {len(train_examples)} examples"
                
                # 設置性能指標
                training_log.set_performance_metrics({
                    "accuracy": accuracy,
                    "precision": precision,
                    "recall": recall,
                    "f1_score": f1,
                    "training_duration_minutes": (training_log.training_end_time - training_log.training_start_time).total_seconds() / 60
                })
                
                session.commit()
                
                logger.info(f"Model training completed. Session ID: {training_session_id}")
                logger.info(f"Performance - Accuracy: {accuracy:.3f}, F1: {f1:.3f}")
                
                return training_session_id
        
        except Exception as e:
            logger.error(f"Error during model training: {e}")
            
            # 更新訓練記錄為失敗
            try:
                training_log.training_status = 'failed'
                training_log.training_end_time = datetime.utcnow()
                training_log.notes = f"Training failed: {str(e)}"
                session.commit()
            except:
                pass
            
            return None
        
        finally:
            db_manager.close_session(session)
    
    def evaluate_model_performance(
        self, 
        test_samples_count: int = 100
    ) -> Dict[str, Any]:
        """
        評估當前模型性能
        
        Args:
            test_samples_count: 測試樣本數量
            
        Returns:
            Dict: 性能評估結果
        """
        session = db_manager.get_session()
        try:
            # 獲取最近的高品質樣本作為測試集
            test_samples = session.query(LearningSample).filter(
                LearningSample.quality_score >= 0.9,
                LearningSample.validation_status == 'validated',
                LearningSample.sample_type == 'positive'
            ).limit(test_samples_count).all()
            
            if not test_samples:
                return {"error": "No test samples available"}
            
            correct_predictions = 0
            total_predictions = 0
            detailed_results = []
            
            parser = UnifiedOrderParser()
            
            for sample in test_samples:
                try:
                    # 使用當前模型進行預測
                    prediction = parser.forward(sample.input_text)
                    predicted_orders = json.loads(prediction.orders_json)
                    expected_orders = sample.get_expected_output()
                    
                    # 簡單評估：比較訂單數量和關鍵欄位
                    is_correct = self._compare_orders(predicted_orders, expected_orders)
                    
                    if is_correct:
                        correct_predictions += 1
                    
                    total_predictions += 1
                    
                    detailed_results.append({
                        "sample_id": sample.id,
                        "input_text": sample.input_text[:100] + "...",
                        "correct": is_correct,
                        "predicted_count": len(predicted_orders),
                        "expected_count": len(expected_orders)
                    })
                    
                except Exception as e:
                    logger.warning(f"Error evaluating sample {sample.id}: {e}")
                    total_predictions += 1
                    detailed_results.append({
                        "sample_id": sample.id,
                        "input_text": sample.input_text[:100] + "...",
                        "correct": False,
                        "error": str(e)
                    })
            
            accuracy = correct_predictions / total_predictions if total_predictions > 0 else 0
            
            return {
                "accuracy": accuracy,
                "correct_predictions": correct_predictions,
                "total_predictions": total_predictions,
                "test_samples_count": len(test_samples),
                "detailed_results": detailed_results[:10]  # 只返回前10個詳細結果
            }
            
        except SQLAlchemyError as e:
            logger.error(f"Database error evaluating model: {e}")
            return {"error": str(e)}
        finally:
            db_manager.close_session(session)
    
    def _compare_orders(
        self, 
        predicted: List[Dict[str, Any]], 
        expected: List[Dict[str, Any]]
    ) -> bool:
        """
        比較預測和期望的訂單
        
        Args:
            predicted: 預測的訂單列表
            expected: 期望的訂單列表
            
        Returns:
            bool: 是否匹配
        """
        if len(predicted) != len(expected):
            return False
        
        # 簡單比較關鍵欄位
        for pred_order, exp_order in zip(predicted, expected):
            # 比較必要欄位
            key_fields = ['receiver_name', 'receiver_phone', 'shipping_address']
            for field in key_fields:
                if pred_order.get(field) != exp_order.get(field):
                    return False
            
            # 比較商品數量
            pred_items_count = len(pred_order.get('items', []))
            exp_items_count = len(exp_order.get('items', []))
            if pred_items_count != exp_items_count:
                return False
        
        return True
    
    def get_training_statistics(self) -> Dict[str, Any]:
        """
        獲取訓練統計信息
        
        Returns:
            Dict: 統計信息
        """
        session = db_manager.get_session()
        try:
            # 樣本統計
            total_samples = session.query(LearningSample).count()
            positive_samples = session.query(LearningSample).filter_by(sample_type='positive').count()
            negative_samples = session.query(LearningSample).filter_by(sample_type='negative').count()
            edge_case_samples = session.query(LearningSample).filter_by(sample_type='edge_case').count()
            
            validated_samples = session.query(LearningSample).filter_by(validation_status='validated').count()
            
            # 品質統計
            avg_quality = session.query(LearningSample).with_entities(
                db_manager.engine.dialect.case(
                    [(LearningSample.quality_score.isnot(None), LearningSample.quality_score)],
                    else_=0
                ).label('quality')
            ).all()
            
            avg_quality_score = sum([q.quality for q in avg_quality]) / len(avg_quality) if avg_quality else 0
            
            # 訓練記錄統計
            total_trainings = session.query(DSPyTrainingLog).count()
            successful_trainings = session.query(DSPyTrainingLog).filter_by(training_status='completed').count()
            
            # 最近訓練
            latest_training = session.query(DSPyTrainingLog).filter_by(
                training_status='completed'
            ).order_by(DSPyTrainingLog.created_at.desc()).first()
            
            return {
                "samples": {
                    "total": total_samples,
                    "positive": positive_samples,
                    "negative": negative_samples,
                    "edge_case": edge_case_samples,
                    "validated": validated_samples,
                    "avg_quality_score": round(avg_quality_score, 3)
                },
                "training": {
                    "total_sessions": total_trainings,
                    "successful_sessions": successful_trainings,
                    "success_rate": round(successful_trainings / total_trainings * 100, 1) if total_trainings > 0 else 0,
                    "latest_training": {
                        "session_id": latest_training.training_session_id if latest_training else None,
                        "accuracy": latest_training.accuracy_score if latest_training else None,
                        "f1_score": latest_training.f1_score if latest_training else None,
                        "created_at": latest_training.created_at.isoformat() if latest_training else None
                    } if latest_training else None
                }
            }
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting training statistics: {e}")
            return {}
        finally:
            db_manager.close_session(session)


# 創建全域實例
dspy_learning_manager = DSPyLearningManager()