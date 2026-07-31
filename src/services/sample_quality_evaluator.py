"""
樣本品質評估機制
自動和人工評估學習樣本的品質
"""
import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..database.models import (
    db_manager, LearningSample, SampleQualityEvaluation,
    RawOrderInput, ConfirmedOrder
)

logger = logging.getLogger(__name__)


class SampleQualityEvaluator:
    """
    樣本品質評估器
    
    功能：
    1. 自動評估樣本品質（語法、語義、完整性）
    2. 人工評估支援
    3. 品質維度分析
    4. 樣本改進建議
    5. 品質趨勢分析
    """
    
    def __init__(self):
        """初始化品質評估器"""
        self.quality_dimensions = {
            'completeness': '完整性',
            'accuracy': '準確性', 
            'clarity': '清晰度',
            'consistency': '一致性',
            'complexity': '複雜度',
            'representativeness': '代表性'
        }
    
    def evaluate_sample_auto(
        self, 
        sample_id: int,
        evaluator_id: str = 'auto_evaluator'
    ) -> Optional[Dict[str, Any]]:
        """
        自動評估單個學習樣本
        
        Args:
            sample_id: 樣本ID
            evaluator_id: 評估者ID
            
        Returns:
            Dict: 評估結果
        """
        session = db_manager.get_session()
        try:
            sample = session.query(LearningSample).filter_by(id=sample_id).first()
            if not sample:
                return None
            
            # 執行各維度評估
            dimensions_scores = {}
            feedback_parts = []
            
            # 1. 完整性評估
            completeness_score, completeness_feedback = self._evaluate_completeness(
                sample.input_text, 
                sample.get_expected_output()
            )
            dimensions_scores['completeness'] = completeness_score
            feedback_parts.append(f"完整性: {completeness_feedback}")
            
            # 2. 準確性評估
            accuracy_score, accuracy_feedback = self._evaluate_accuracy(
                sample.input_text,
                sample.get_expected_output()
            )
            dimensions_scores['accuracy'] = accuracy_score
            feedback_parts.append(f"準確性: {accuracy_feedback}")
            
            # 3. 清晰度評估
            clarity_score, clarity_feedback = self._evaluate_clarity(sample.input_text)
            dimensions_scores['clarity'] = clarity_score
            feedback_parts.append(f"清晰度: {clarity_feedback}")
            
            # 4. 一致性評估
            consistency_score, consistency_feedback = self._evaluate_consistency(
                sample.get_expected_output()
            )
            dimensions_scores['consistency'] = consistency_score
            feedback_parts.append(f"一致性: {consistency_feedback}")
            
            # 5. 複雜度評估
            complexity_score, complexity_feedback = self._evaluate_complexity(
                sample.input_text,
                sample.get_expected_output()
            )
            dimensions_scores['complexity'] = complexity_score
            feedback_parts.append(f"複雜度: {complexity_feedback}")
            
            # 6. 代表性評估
            representativeness_score, representativeness_feedback = self._evaluate_representativeness(
                sample.input_text,
                sample.get_tags()
            )
            dimensions_scores['representativeness'] = representativeness_score
            feedback_parts.append(f"代表性: {representativeness_feedback}")
            
            # 計算總體品質分數
            overall_score = sum(dimensions_scores.values()) / len(dimensions_scores)
            
            # 創建評估記錄
            evaluation = SampleQualityEvaluation(
                sample_id=sample_id,
                evaluator_type='auto',
                evaluator_id=evaluator_id,
                overall_quality_score=overall_score,
                feedback_text='; '.join(feedback_parts)
            )
            
            evaluation.set_quality_dimensions(dimensions_scores)
            
            session.add(evaluation)
            
            # 更新樣本的品質分數
            sample.quality_score = overall_score
            
            session.commit()
            
            result = {
                'evaluation_id': evaluation.id,
                'sample_id': sample_id,
                'overall_score': overall_score,
                'dimensions_scores': dimensions_scores,
                'feedback': '; '.join(feedback_parts),
                'quality_grade': self._get_quality_grade(overall_score)
            }
            
            logger.info(f"Auto-evaluated sample {sample_id} with score {overall_score:.3f}")
            return result
            
        except SQLAlchemyError as e:
            logger.error(f"Database error evaluating sample {sample_id}: {e}")
            session.rollback()
            return None
        finally:
            db_manager.close_session(session)
    
    def _evaluate_completeness(
        self, 
        input_text: str, 
        expected_output: List[Dict[str, Any]]
    ) -> Tuple[float, str]:
        """
        評估完整性
        
        Args:
            input_text: 輸入文字
            expected_output: 期望輸出
            
        Returns:
            Tuple[float, str]: (分數, 反饋)
        """
        score = 0.0
        feedback_parts = []
        
        # 檢查輸入文字長度
        if len(input_text.strip()) < 10:
            score += 0.0
            feedback_parts.append("輸入過短")
        elif len(input_text.strip()) < 30:
            score += 0.3
            feedback_parts.append("輸入較短")
        else:
            score += 0.6
            feedback_parts.append("輸入長度適當")
        
        # 檢查期望輸出完整性
        if not expected_output:
            score += 0.0
            feedback_parts.append("無期望輸出")
        else:
            for order in expected_output:
                order_score = 0.0
                
                # 檢查必要欄位
                required_fields = ['receiver_name', 'receiver_phone', 'shipping_address']
                present_fields = sum(1 for field in required_fields if order.get(field))
                order_score += present_fields / len(required_fields) * 0.4
                
                # 檢查商品信息
                if order.get('items'):
                    order_score += 0.2
                    items = order['items']
                    if all(item.get('name') and item.get('quantity') for item in items):
                        order_score += 0.2
                
                # 檢查可選欄位
                optional_fields = ['sender_name', 'sender_phone', 'shipping_date']
                present_optional = sum(1 for field in optional_fields if order.get(field))
                order_score += present_optional / len(optional_fields) * 0.2
                
                score += order_score / len(expected_output)
        
        # 正規化分數
        score = min(score, 1.0)
        
        feedback = f"完整性 {score:.1%} - " + ", ".join(feedback_parts)
        return score, feedback
    
    def _evaluate_accuracy(
        self, 
        input_text: str, 
        expected_output: List[Dict[str, Any]]
    ) -> Tuple[float, str]:
        """
        評估準確性
        
        Args:
            input_text: 輸入文字
            expected_output: 期望輸出
            
        Returns:
            Tuple[float, str]: (分數, 反饋)
        """
        score = 1.0  # 預設滿分
        issues = []
        
        # 檢查電話號碼格式
        for order in expected_output:
            if order.get('receiver_phone'):
                phone = order['receiver_phone']
                if not re.match(r'^\d{8,12}$|^\d{2,3}-\d{6,8}$|^09\d{8}$', phone):
                    score -= 0.1
                    issues.append("電話格式可能不正確")
            
            if order.get('sender_phone'):
                phone = order['sender_phone']
                if not re.match(r'^\d{8,12}$|^\d{2,3}-\d{6,8}$|^09\d{8}$', phone):
                    score -= 0.1
                    issues.append("寄件人電話格式可能不正確")
        
        # 檢查地址合理性
        for order in expected_output:
            address = order.get('shipping_address', '')
            if address:
                # 台灣地址基本檢查
                taiwan_regions = ['台北', '新北', '桃園', '台中', '台南', '高雄', '基隆', '新竹', '苗栗', 
                                '彰化', '南投', '雲林', '嘉義', '屏東', '宜蘭', '花蓮', '台東', '澎湖']
                
                if not any(region in address for region in taiwan_regions):
                    score -= 0.05
                    issues.append("地址可能不是台灣地址")
                
                if len(address) < 8:
                    score -= 0.1
                    issues.append("地址過短")
        
        # 檢查商品數量合理性
        for order in expected_output:
            items = order.get('items', [])
            for item in items:
                quantity = item.get('quantity', 0)
                if quantity <= 0:
                    score -= 0.2
                    issues.append("商品數量不合理")
                elif quantity > 1000:  # 異常大的數量
                    score -= 0.1
                    issues.append("商品數量異常大")
        
        # 檢查日期格式
        for order in expected_output:
            shipping_date = order.get('shipping_date')
            if shipping_date:
                if not re.match(r'^\d{2}-\d{2}$', shipping_date):
                    score -= 0.1
                    issues.append("日期格式不正確")
        
        score = max(score, 0.0)
        
        feedback = f"準確性 {score:.1%}"
        if issues:
            feedback += f" - 問題: {', '.join(set(issues))}"
        else:
            feedback += " - 無明顯錯誤"
            
        return score, feedback
    
    def _evaluate_clarity(self, input_text: str) -> Tuple[float, str]:
        """
        評估清晰度
        
        Args:
            input_text: 輸入文字
            
        Returns:
            Tuple[float, str]: (分數, 反饋)
        """
        score = 0.5  # 基礎分數
        feedback_parts = []
        
        # 檢查文字結構
        if '收件人' in input_text and ('電話' in input_text or '手機' in input_text):
            score += 0.2
            feedback_parts.append("包含基本聯絡信息")
        
        if '地址' in input_text or '住址' in input_text:
            score += 0.2
            feedback_parts.append("包含地址信息")
        
        if '商品' in input_text or '物品' in input_text or '禮盒' in input_text:
            score += 0.1
            feedback_parts.append("包含商品信息")
        
        # 檢查格式清晰度
        if '：' in input_text or ':' in input_text:
            score += 0.1
            feedback_parts.append("使用冒號分隔")
        
        # 檢查是否有混亂的格式
        emoji_count = len(re.findall(r'[🩷🌸📦👤📞📅📋]', input_text))
        if emoji_count > 0:
            if emoji_count < 10:
                score += 0.1
                feedback_parts.append("適度使用表情符號")
            else:
                score -= 0.1
                feedback_parts.append("過度使用表情符號")
        
        # 檢查重複信息
        words = input_text.split()
        unique_ratio = len(set(words)) / len(words) if words else 1
        if unique_ratio < 0.5:
            score -= 0.2
            feedback_parts.append("有重複信息")
        
        score = min(max(score, 0.0), 1.0)
        
        feedback = f"清晰度 {score:.1%}"
        if feedback_parts:
            feedback += f" - {', '.join(feedback_parts)}"
            
        return score, feedback
    
    def _evaluate_consistency(
        self, 
        expected_output: List[Dict[str, Any]]
    ) -> Tuple[float, str]:
        """
        評估一致性
        
        Args:
            expected_output: 期望輸出
            
        Returns:
            Tuple[float, str]: (分數, 反饋)
        """
        if not expected_output:
            return 0.0, "無輸出數據"
        
        score = 1.0
        issues = []
        
        # 檢查多個訂單間的格式一致性
        if len(expected_output) > 1:
            # 檢查必要欄位一致性
            field_presence = {}
            for order in expected_output:
                for field in ['receiver_name', 'receiver_phone', 'shipping_address', 
                            'sender_name', 'sender_phone', 'shipping_date']:
                    if field not in field_presence:
                        field_presence[field] = []
                    field_presence[field].append(order.get(field) is not None)
            
            # 檢查可選欄位的一致性
            for field, presence_list in field_presence.items():
                if field in ['sender_name', 'sender_phone', 'shipping_date']:
                    # 可選欄位不要求100%一致，但偏差太大會扣分
                    consistency_ratio = sum(presence_list) / len(presence_list)
                    if 0.2 < consistency_ratio < 0.8:  # 部分有部分沒有
                        score -= 0.1
                        issues.append(f"{field}欄位不一致")
        
        # 檢查商品格式一致性
        item_formats = []
        for order in expected_output:
            items = order.get('items', [])
            for item in items:
                if 'name' in item and 'quantity' in item:
                    item_formats.append(True)
                else:
                    item_formats.append(False)
        
        if item_formats and not all(item_formats):
            score -= 0.2
            issues.append("商品格式不一致")
        
        # 檢查日期格式一致性
        date_formats = []
        for order in expected_output:
            date = order.get('shipping_date')
            if date:
                if re.match(r'^\d{2}-\d{2}$', date):
                    date_formats.append('MM-DD')
                else:
                    date_formats.append('other')
        
        if len(set(date_formats)) > 1:
            score -= 0.1
            issues.append("日期格式不一致")
        
        score = max(score, 0.0)
        
        feedback = f"一致性 {score:.1%}"
        if issues:
            feedback += f" - 問題: {', '.join(issues)}"
        else:
            feedback += " - 格式一致"
            
        return score, feedback
    
    def _evaluate_complexity(
        self, 
        input_text: str, 
        expected_output: List[Dict[str, Any]]
    ) -> Tuple[float, str]:
        """
        評估複雜度
        
        Args:
            input_text: 輸入文字
            expected_output: 期望輸出
            
        Returns:
            Tuple[float, str]: (分數, 反饋)
        """
        complexity_score = 0.0
        complexity_factors = []
        
        # 訂單數量複雜度
        order_count = len(expected_output)
        if order_count == 1:
            complexity_score += 0.2
            complexity_factors.append("單一訂單")
        elif order_count <= 3:
            complexity_score += 0.5
            complexity_factors.append(f"{order_count}個訂單")
        else:
            complexity_score += 0.8
            complexity_factors.append(f"多訂單({order_count}個)")
        
        # 商品複雜度
        total_items = sum(len(order.get('items', [])) for order in expected_output)
        if total_items <= 2:
            complexity_score += 0.1
            complexity_factors.append("商品簡單")
        elif total_items <= 5:
            complexity_score += 0.3
            complexity_factors.append("商品中等")
        else:
            complexity_score += 0.5
            complexity_factors.append("商品複雜")
        
        # 地址複雜度
        for order in expected_output:
            address = order.get('shipping_address', '')
            if '(' in address or '（' in address:
                complexity_score += 0.1
                complexity_factors.append("包含地址註記")
                break
        
        # 日期解析複雜度
        has_dates = any(order.get('shipping_date') for order in expected_output)
        if has_dates:
            complexity_score += 0.2
            complexity_factors.append("包含日期信息")
        
        # 寄件人信息複雜度
        has_sender_info = any(
            order.get('sender_name') or order.get('sender_phone') 
            for order in expected_output
        )
        if has_sender_info:
            complexity_score += 0.1
            complexity_factors.append("包含寄件人信息")
        
        # 正規化分數 (複雜度高的樣本更有價值)
        normalized_score = min(complexity_score, 1.0)
        
        feedback = f"複雜度 {normalized_score:.1%} - {', '.join(complexity_factors)}"
        return normalized_score, feedback
    
    def _evaluate_representativeness(
        self, 
        input_text: str, 
        tags: List[str]
    ) -> Tuple[float, str]:
        """
        評估代表性
        
        Args:
            input_text: 輸入文字
            tags: 樣本標籤
            
        Returns:
            Tuple[float, str]: (分數, 反饋)
        """
        score = 0.5  # 基礎分數
        factors = []
        
        # 基於標籤的代表性
        valuable_tags = ['multi_order', 'date_parsing', 'sender_info', 'user_modified']
        tag_score = len(set(tags) & set(valuable_tags)) / len(valuable_tags)
        score += tag_score * 0.3
        
        if tag_score > 0:
            factors.append(f"包含{len(set(tags) & set(valuable_tags))}個重要特徵")
        
        # 文字長度代表性
        text_length = len(input_text)
        if 50 <= text_length <= 300:  # 適中長度最有代表性
            score += 0.2
            factors.append("文字長度適中")
        elif text_length > 300:
            score += 0.1
            factors.append("文字較長")
        else:
            factors.append("文字較短")
        
        # 檢查是否包含常見模式
        common_patterns = ['收件人', '電話', '地址', '商品', '禮盒', '蛋糕', '花束']
        pattern_count = sum(1 for pattern in common_patterns if pattern in input_text)
        pattern_ratio = pattern_count / len(common_patterns)
        score += pattern_ratio * 0.2
        
        if pattern_ratio > 0.5:
            factors.append("包含常見模式")
        
        score = min(score, 1.0)
        
        feedback = f"代表性 {score:.1%}"
        if factors:
            feedback += f" - {', '.join(factors)}"
            
        return score, feedback
    
    def _get_quality_grade(self, score: float) -> str:
        """
        根據分數獲取品質等級
        
        Args:
            score: 品質分數
            
        Returns:
            str: 品質等級
        """
        if score >= 0.9:
            return "優秀"
        elif score >= 0.8:
            return "良好"
        elif score >= 0.7:
            return "中等"
        elif score >= 0.6:
            return "及格"
        else:
            return "需改進"
    
    def batch_evaluate_samples(
        self, 
        sample_ids: List[int] = None,
        sample_type: str = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        批量評估樣本
        
        Args:
            sample_ids: 指定樣本ID列表
            sample_type: 樣本類型過濾
            limit: 評估數量限制
            
        Returns:
            Dict: 評估結果統計
        """
        session = db_manager.get_session()
        try:
            # 獲取要評估的樣本
            if sample_ids:
                samples = session.query(LearningSample).filter(
                    LearningSample.id.in_(sample_ids)
                ).limit(limit).all()
            else:
                query = session.query(LearningSample)
                if sample_type:
                    query = query.filter_by(sample_type=sample_type)
                
                # 優先評估未評估的樣本
                samples = query.filter(
                    ~LearningSample.id.in_(
                        session.query(SampleQualityEvaluation.sample_id)
                    )
                ).limit(limit).all()
            
            results = {
                'evaluated_count': 0,
                'failed_count': 0,
                'average_score': 0.0,
                'score_distribution': {'優秀': 0, '良好': 0, '中等': 0, '及格': 0, '需改進': 0},
                'dimension_averages': {},
                'failed_samples': []
            }
            
            total_score = 0.0
            dimension_totals = {dim: 0.0 for dim in self.quality_dimensions.keys()}
            
            for sample in samples:
                try:
                    eval_result = self.evaluate_sample_auto(sample.id)
                    if eval_result:
                        results['evaluated_count'] += 1
                        score = eval_result['overall_score']
                        total_score += score
                        
                        # 統計分數分佈
                        grade = eval_result['quality_grade']
                        results['score_distribution'][grade] += 1
                        
                        # 累計各維度分數
                        for dim, score_val in eval_result['dimensions_scores'].items():
                            dimension_totals[dim] += score_val
                    else:
                        results['failed_count'] += 1
                        results['failed_samples'].append(sample.id)
                        
                except Exception as e:
                    logger.error(f"Error evaluating sample {sample.id}: {e}")
                    results['failed_count'] += 1
                    results['failed_samples'].append(sample.id)
            
            # 計算平均值
            if results['evaluated_count'] > 0:
                results['average_score'] = total_score / results['evaluated_count']
                results['dimension_averages'] = {
                    dim: total / results['evaluated_count'] 
                    for dim, total in dimension_totals.items()
                }
            
            logger.info(f"Batch evaluation completed: {results['evaluated_count']} samples evaluated")
            return results
            
        except SQLAlchemyError as e:
            logger.error(f"Database error in batch evaluation: {e}")
            return {'error': str(e)}
        finally:
            db_manager.close_session(session)
    
    def get_quality_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        獲取品質評估統計信息
        
        Args:
            days: 統計天數
            
        Returns:
            Dict: 統計信息
        """
        session = db_manager.get_session()
        try:
            from datetime import timedelta
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # 基本統計
            total_evaluations = session.query(SampleQualityEvaluation).filter(
                SampleQualityEvaluation.evaluation_time >= cutoff_date
            ).count()
            
            auto_evaluations = session.query(SampleQualityEvaluation).filter(
                SampleQualityEvaluation.evaluation_time >= cutoff_date,
                SampleQualityEvaluation.evaluator_type == 'auto'
            ).count()
            
            # 平均品質分數
            avg_scores = session.query(SampleQualityEvaluation).filter(
                SampleQualityEvaluation.evaluation_time >= cutoff_date
            ).with_entities(SampleQualityEvaluation.overall_quality_score).all()
            
            avg_score = sum(s.overall_quality_score for s in avg_scores) / len(avg_scores) if avg_scores else 0
            
            # 分數分佈
            score_ranges = {'0.9-1.0': 0, '0.8-0.9': 0, '0.7-0.8': 0, '0.6-0.7': 0, '0.0-0.6': 0}
            for score_record in avg_scores:
                score = score_record.overall_quality_score
                if score >= 0.9:
                    score_ranges['0.9-1.0'] += 1
                elif score >= 0.8:
                    score_ranges['0.8-0.9'] += 1
                elif score >= 0.7:
                    score_ranges['0.7-0.8'] += 1
                elif score >= 0.6:
                    score_ranges['0.6-0.7'] += 1
                else:
                    score_ranges['0.0-0.6'] += 1
            
            return {
                'period_days': days,
                'total_evaluations': total_evaluations,
                'auto_evaluations': auto_evaluations,
                'human_evaluations': total_evaluations - auto_evaluations,
                'average_quality_score': round(avg_score, 3),
                'score_distribution': score_ranges,
                'high_quality_ratio': round(
                    (score_ranges['0.8-0.9'] + score_ranges['0.9-1.0']) / total_evaluations * 100, 1
                ) if total_evaluations > 0 else 0
            }
            
        except SQLAlchemyError as e:
            logger.error(f"Database error getting quality statistics: {e}")
            return {}
        finally:
            db_manager.close_session(session)


# 創建全域實例
sample_quality_evaluator = SampleQualityEvaluator()