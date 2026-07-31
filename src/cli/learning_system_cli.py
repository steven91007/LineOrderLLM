"""
學習系統命令行界面
提供系統管理和監控功能
"""
import click
import json
from datetime import datetime
from typing import Dict, Any

from ..services.order_data_collector import order_data_collector
from ..services.dspy_learning_manager import dspy_learning_manager
from ..services.sample_quality_evaluator import sample_quality_evaluator
from ..database.models import db_manager


@click.group()
def learning_cli():
    """訂單學習系統管理工具"""
    pass


@learning_cli.command()
def init_db():
    """初始化資料庫"""
    try:
        db_manager.create_tables()
        click.echo("✅ 資料庫初始化成功")
    except Exception as e:
        click.echo(f"❌ 資料庫初始化失敗: {e}")


@learning_cli.command()
@click.option('--days', default=30, help='統計天數')
def stats(days):
    """顯示系統統計信息"""
    click.echo(f"\n📊 訂單學習系統統計 (過去 {days} 天)")
    click.echo("=" * 50)
    
    # 處理統計
    processing_stats = order_data_collector.get_processing_statistics(days)
    if processing_stats:
        click.echo(f"\n🔄 處理統計:")
        click.echo(f"  總輸入: {processing_stats.get('total_inputs', 0)}")
        click.echo(f"  解析次數: {processing_stats.get('total_parses', 0)}")
        click.echo(f"  成功率: {processing_stats.get('parse_success_rate', 0)}%")
        click.echo(f"  確認訂單: {processing_stats.get('confirmed_orders', 0)}")
        click.echo(f"  學習樣本: {processing_stats.get('learning_samples', 0)}")
    
    # 訓練統計
    training_stats = dspy_learning_manager.get_training_statistics()
    if training_stats:
        click.echo(f"\n🤖 訓練統計:")
        samples = training_stats.get('samples', {})
        click.echo(f"  總樣本: {samples.get('total', 0)}")
        click.echo(f"  正面樣本: {samples.get('positive', 0)}")
        click.echo(f"  負面樣本: {samples.get('negative', 0)}")
        click.echo(f"  邊界案例: {samples.get('edge_case', 0)}")
        click.echo(f"  平均品質: {samples.get('avg_quality_score', 0):.3f}")
        
        training = training_stats.get('training', {})
        click.echo(f"  訓練會話: {training.get('total_sessions', 0)}")
        click.echo(f"  成功率: {training.get('success_rate', 0)}%")
    
    # 品質統計
    quality_stats = sample_quality_evaluator.get_quality_statistics(days)
    if quality_stats:
        click.echo(f"\n⭐ 品質統計:")
        click.echo(f"  總評估: {quality_stats.get('total_evaluations', 0)}")
        click.echo(f"  平均品質: {quality_stats.get('average_quality_score', 0):.3f}")
        click.echo(f"  高品質比例: {quality_stats.get('high_quality_ratio', 0)}%")


@learning_cli.command()
@click.option('--days', default=7, help='收集天數')
@click.option('--min-quality', default=0.8, help='最低品質閾值')
def collect_samples(days, min_quality):
    """從確認訂單收集訓練樣本"""
    click.echo(f"🔄 正在收集過去 {days} 天的訓練樣本...")
    
    try:
        count = dspy_learning_manager.collect_training_samples_from_confirmed_orders(
            days=days,
            min_quality_threshold=min_quality
        )
        click.echo(f"✅ 成功收集 {count} 個訓練樣本")
        
        if count > 0:
            click.echo("💡 提示: 使用 'evaluate-samples' 命令評估樣本品質")
    except Exception as e:
        click.echo(f"❌ 收集樣本失敗: {e}")


@learning_cli.command()
@click.option('--count', default=50, help='生成數量')
def create_negative_samples(count):
    """創建負面樣本"""
    click.echo(f"🔄 正在創建 {count} 個負面樣本...")
    
    try:
        created = dspy_learning_manager.create_negative_samples(count=count)
        click.echo(f"✅ 成功創建 {created} 個負面樣本")
    except Exception as e:
        click.echo(f"❌ 創建負面樣本失敗: {e}")


@learning_cli.command()
@click.option('--count', default=30, help='生成數量')
def create_edge_cases(count):
    """創建邊界案例樣本"""
    click.echo(f"🔄 正在創建 {count} 個邊界案例...")
    
    try:
        created = dspy_learning_manager.create_edge_case_samples(count=count)
        click.echo(f"✅ 成功創建 {created} 個邊界案例樣本")
    except Exception as e:
        click.echo(f"❌ 創建邊界案例失敗: {e}")


@learning_cli.command()
@click.option('--limit', default=100, help='評估數量限制')
@click.option('--sample-type', help='樣本類型過濾')
def evaluate_samples(limit, sample_type):
    """批量評估樣本品質"""
    click.echo(f"🔄 正在評估樣本品質...")
    
    try:
        results = sample_quality_evaluator.batch_evaluate_samples(
            sample_type=sample_type,
            limit=limit
        )
        
        click.echo(f"\n📊 評估結果:")
        click.echo(f"  評估成功: {results.get('evaluated_count', 0)}")
        click.echo(f"  評估失敗: {results.get('failed_count', 0)}")
        click.echo(f"  平均分數: {results.get('average_score', 0):.3f}")
        
        distribution = results.get('score_distribution', {})
        click.echo(f"\n  品質分佈:")
        for grade, count in distribution.items():
            click.echo(f"    {grade}: {count}")
        
        if results.get('failed_samples'):
            click.echo(f"\n⚠️  評估失敗的樣本ID: {results['failed_samples']}")
            
    except Exception as e:
        click.echo(f"❌ 評估樣本失敗: {e}")


@learning_cli.command()
@click.option('--min-quality', default=0.8, help='最低品質閾值')
@click.option('--train-ratio', default=0.8, help='訓練集比例')
def train_model(min_quality, train_ratio):
    """訓練 DSPy 模型"""
    click.echo(f"🔄 正在準備訓練數據...")
    
    try:
        # 準備訓練數據
        train_examples, val_examples = dspy_learning_manager.prepare_training_data(
            min_quality_score=min_quality,
            train_ratio=train_ratio
        )
        
        if not train_examples:
            click.echo("❌ 沒有找到符合條件的訓練樣本")
            return
        
        click.echo(f"📚 訓練樣本: {len(train_examples)}, 驗證樣本: {len(val_examples)}")
        click.echo(f"🔄 開始訓練模型...")
        
        # 開始訓練
        session_id = dspy_learning_manager.train_model(
            train_examples=train_examples,
            val_examples=val_examples,
            model_name=f"cli_trained_{datetime.now().strftime('%Y%m%d_%H%M')}"
        )
        
        if session_id:
            click.echo(f"✅ 模型訓練完成!")
            click.echo(f"   會話ID: {session_id}")
        else:
            click.echo("❌ 模型訓練失敗")
            
    except Exception as e:
        click.echo(f"❌ 模型訓練失敗: {e}")


@learning_cli.command()
@click.option('--test-count', default=50, help='測試樣本數量')
def evaluate_model(test_count):
    """評估當前模型性能"""
    click.echo(f"🔄 正在評估模型性能 (使用 {test_count} 個測試樣本)...")
    
    try:
        results = dspy_learning_manager.evaluate_model_performance(
            test_samples_count=test_count
        )
        
        if 'error' in results:
            click.echo(f"❌ 評估失敗: {results['error']}")
            return
        
        click.echo(f"\n📊 模型性能評估結果:")
        click.echo(f"  準確率: {results.get('accuracy', 0):.1%}")
        click.echo(f"  正確預測: {results.get('correct_predictions', 0)}")
        click.echo(f"  總預測: {results.get('total_predictions', 0)}")
        click.echo(f"  測試樣本: {results.get('test_samples_count', 0)}")
        
        # 顯示部分詳細結果
        detailed = results.get('detailed_results', [])
        if detailed:
            click.echo(f"\n📝 部分詳細結果:")
            for i, result in enumerate(detailed[:5]):
                status = "✅" if result.get('correct') else "❌"
                click.echo(f"  {i+1}. {status} {result.get('input_text', '')}")
                
    except Exception as e:
        click.echo(f"❌ 模型評估失敗: {e}")


@learning_cli.command()
def full_pipeline():
    """執行完整的學習管道"""
    click.echo("🚀 開始執行完整學習管道...")
    
    try:
        # 1. 收集樣本
        click.echo("\n1️⃣ 收集訓練樣本...")
        collected = dspy_learning_manager.collect_training_samples_from_confirmed_orders(
            days=30, min_quality_threshold=0.8
        )
        click.echo(f"   收集到 {collected} 個正面樣本")
        
        # 2. 創建負面樣本
        click.echo("\n2️⃣ 創建負面樣本...")
        negative = dspy_learning_manager.create_negative_samples(count=30)
        click.echo(f"   創建了 {negative} 個負面樣本")
        
        # 3. 創建邊界案例
        click.echo("\n3️⃣ 創建邊界案例...")
        edge_cases = dspy_learning_manager.create_edge_case_samples(count=15)
        click.echo(f"   創建了 {edge_cases} 個邊界案例")
        
        # 4. 評估樣本品質
        click.echo("\n4️⃣ 評估樣本品質...")
        eval_results = sample_quality_evaluator.batch_evaluate_samples(limit=200)
        click.echo(f"   評估了 {eval_results.get('evaluated_count', 0)} 個樣本")
        click.echo(f"   平均品質: {eval_results.get('average_score', 0):.3f}")
        
        # 5. 訓練模型
        total_samples = collected + negative + edge_cases
        if total_samples >= 20:
            click.echo("\n5️⃣ 訓練模型...")
            train_examples, val_examples = dspy_learning_manager.prepare_training_data(
                min_quality_score=0.7, train_ratio=0.8
            )
            
            if train_examples:
                session_id = dspy_learning_manager.train_model(
                    train_examples=train_examples,
                    val_examples=val_examples,
                    model_name=f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M')}"
                )
                
                if session_id:
                    click.echo(f"   ✅ 訓練完成! 會話ID: {session_id}")
                    
                    # 6. 評估模型
                    click.echo("\n6️⃣ 評估模型性能...")
                    performance = dspy_learning_manager.evaluate_model_performance(50)
                    if 'accuracy' in performance:
                        click.echo(f"   模型準確率: {performance['accuracy']:.1%}")
                else:
                    click.echo("   ❌ 訓練失敗")
            else:
                click.echo("   ⚠️ 沒有足夠的訓練樣本")
        else:
            click.echo("   ⚠️ 樣本數量不足，跳過訓練")
        
        click.echo(f"\n🎉 完整學習管道執行完成!")
        
    except Exception as e:
        click.echo(f"❌ 學習管道執行失敗: {e}")


@learning_cli.command()
@click.option('--output', help='輸出文件路径')
def export_samples(output):
    """匯出學習樣本"""
    click.echo("🔄 正在匯出學習樣本...")
    
    try:
        samples = order_data_collector.get_learning_samples(
            min_quality_score=0.7,
            limit=1000
        )
        
        if output:
            with open(output, 'w', encoding='utf-8') as f:
                json.dump(samples, f, ensure_ascii=False, indent=2)
            click.echo(f"✅ 樣本已匯出到: {output}")
        else:
            click.echo(f"📊 找到 {len(samples)} 個學習樣本")
            for sample in samples[:5]:  # 顯示前5個
                click.echo(f"  - ID: {sample['id']}, 類型: {sample['sample_type']}, 品質: {sample['quality_score']:.3f}")
                
    except Exception as e:
        click.echo(f"❌ 匯出樣本失敗: {e}")


@learning_cli.command()
def cleanup():
    """清理低品質樣本"""
    click.echo("🔄 正在清理低品質樣本...")
    
    try:
        from ..database.models import LearningSample
        session = db_manager.get_session()
        
        # 刪除品質分數低於0.5的樣本
        low_quality_samples = session.query(LearningSample).filter(
            LearningSample.quality_score < 0.5
        ).all()
        
        count = len(low_quality_samples)
        
        if count > 0:
            for sample in low_quality_samples:
                session.delete(sample)
            session.commit()
            click.echo(f"✅ 清理了 {count} 個低品質樣本")
        else:
            click.echo("✅ 沒有找到需要清理的低品質樣本")
            
        db_manager.close_session(session)
        
    except Exception as e:
        click.echo(f"❌ 清理失敗: {e}")


if __name__ == '__main__':
    learning_cli()