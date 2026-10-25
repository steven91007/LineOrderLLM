"""Unit tests for the Jev item judge, the shared resolver, and the A/B evaluation

No network: a fake TypeSafe client returns prebuilt SystemOneResponse objects.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from typesafe_sdk import (
    ChoiceAnswer,
    NoulAnswer,
    SystemOneResponse,
    TypeSafeAPIConnectionError,
    Usage,
)

from evals.item_judge import evaluators
from evals.item_judge.schema import CATEGORY_COUNTS, load_items, validate_items
from evals.item_judge.tasks import make_jev_task, pick_order
from src.services.chat_log_importer import ChatLogImporter
from src.utils import langfuse_tracing
from src.utils.form_options import MAX_FAMILY_BOXES, MAX_GIFTBOX_BOXES, MAX_SHUANGSHUANG_SETS
from src.utils.item_resolver import ItemFields, fields_from_raw, resolve_items
from src.utils.jev_modules import item_judge as item_judge_module
from src.utils.jev_modules.item_judge import (
    ItemJudgeError,
    JevItemJudge,
    build_questions,
    build_state,
)

DATASET = 'evals/item_judge/dataset.jsonl'


# ---------- Fake TypeSafe client ----------

def choice(value, confidence=0.95):
    return ChoiceAnswer(choice=value, confidence=confidence, probabilities={value: confidence})


def make_response(is_order=0.97, amended=0.1, giftbox=('none', 'unspecified'),
                  family=('none', 'unspecified'), shuangshuang='none',
                  confidence=0.95, input_tokens=1000):
    return SystemOneResponse(
        model='jev-test',
        usage=Usage(input_tokens=input_tokens, output_tokens=20),
        answers={
            'is_order': NoulAnswer(noul=is_order),
            'amended': NoulAnswer(noul=amended),
            'giftbox_boxes': choice(giftbox[0], confidence),
            'giftbox_spec': choice(giftbox[1], confidence),
            'family_boxes': choice(family[0], confidence),
            'family_spec': choice(family[1], confidence),
            'shuangshuang_sets': choice(shuangshuang, confidence),
        },
    )


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def system_one(self, state, questions, **kwargs):
        self.calls.append((state, questions))
        if self.error:
            raise self.error
        return self.response

    def close(self):
        pass


def make_judge(response=None, error=None, floor=0.5):
    return JevItemJudge(client=FakeClient(response, error), confidence_floor=floor)


# ---------- item_resolver ----------

def test_resolve_items_maps_fields_to_form_options():
    resolved = resolve_items(ItemFields(giftbox_spec='20a', giftbox_boxes=2,
                                        family_spec='18A', family_boxes=1))
    assert resolved.giftbox == '20A 兩盒 $2,170'
    assert resolved.family == '18A 1箱 $1,850'
    assert resolved.problems == []


@pytest.mark.parametrize('fields, problem', [
    (ItemFields(giftbox_boxes=3), '禮盒有數量但沒有規格'),
    (ItemFields(giftbox_spec='18A'), '禮盒有規格但沒有數量'),
    (ItemFields(giftbox_spec='18A', giftbox_boxes='兩'), '禮盒數量無法辨識（兩）'),
    (ItemFields(giftbox_spec='18A', giftbox_boxes=9), '禮盒 9盒超過表單選項上限（最多 8盒），需拆單或人工處理'),
    (ItemFields(shuangshuang_sets=5), '雙雙對對 5組超過表單選項上限（最多 4組），需拆單或人工處理'),
])
def test_resolve_items_reports_problems(fields, problem):
    resolved = resolve_items(fields)
    assert resolved.giftbox is None
    assert problem in resolved.problems


def test_family_and_shuangshuang_conflict_keeps_family():
    resolved = resolve_items(ItemFields(family_spec='20A', family_boxes=1, shuangshuang_sets=1))
    assert resolved.family == '20A 1箱 $2,110'
    assert '家庭號與雙雙對對同時出現，J 欄只能擇一寫入，請人工確認' in resolved.problems


def test_fields_from_raw_tolerates_strings():
    fields = fields_from_raw({'giftbox_spec': ' 20A ', 'giftbox_boxes': '2',
                              'family_spec': '', 'shuangshuang_sets': None})
    assert fields == ItemFields(giftbox_spec='20A', giftbox_boxes=2)


def test_normalized_ignores_case_and_numeric_type():
    assert ItemFields(giftbox_spec='20a', giftbox_boxes='2').normalized() == \
        ItemFields(giftbox_spec='20A', giftbox_boxes=2)


# ---------- Jev module ----------

def test_build_state_and_questions_follow_form_options():
    state = build_state('聊天', None, '2026-09-28 (星期一)')
    assert state['chat_log'] == '聊天' and state['focus_receiver']

    questions = build_questions()
    assert set(questions) == {'is_order', 'giftbox_boxes', 'giftbox_spec', 'family_boxes',
                              'family_spec', 'shuangshuang_sets', 'amended'}
    assert f'more_than_{MAX_GIFTBOX_BOXES}' in questions['giftbox_boxes']['criteria']
    assert f'more_than_{MAX_FAMILY_BOXES}' in questions['family_boxes']['criteria']
    assert f'more_than_{MAX_SHUANGSHUANG_SETS}' in questions['shuangshuang_sets']['criteria']
    for key in ('giftbox_boxes', 'family_boxes', 'shuangshuang_sets'):
        assert 'none' in questions[key]['criteria']
    assert set(build_questions('en')) == set(questions)


def test_judge_composes_fields():
    judge = make_judge(make_response(giftbox=('2', '20A'), shuangshuang='1'))
    judgment = judge.judge('我要20A兩盒 雙雙對對一組', None, '2026-09-28')
    assert judgment.fields == ItemFields(giftbox_spec='20A', giftbox_boxes=2, shuangshuang_sets=1)
    assert judgment.usable
    assert judgment.model == 'jev-test'
    assert judgment.cost_usd == pytest.approx(1000 * 0.042 / 1_000_000)


def test_judge_over_limit_and_unspecified_spec():
    judgment = make_judge(make_response(giftbox=('more_than_8', 'unspecified'))).judge('x')
    assert judgment.fields == ItemFields(giftbox_spec=None, giftbox_boxes=MAX_GIFTBOX_BOXES + 1)


def test_judge_not_an_order_clears_fields():
    judgment = make_judge(make_response(is_order=0.1, giftbox=('2', '20A'))).judge('多少錢')
    assert judgment.fields == ItemFields()
    assert 'Jev judged this is not an order' in judgment.issues


def test_judge_confidence_uses_only_relevant_questions():
    response = make_response(giftbox=('2', '20A'), confidence=0.9)
    # No family pack ordered, so a low-confidence family spec answer must not lower the overall confidence
    response.answers['family_spec'] = choice('unspecified', 0.1)
    judgment = make_judge(response).judge('x')
    assert judgment.confidence == pytest.approx(0.9)


def test_judge_low_confidence_is_not_usable():
    judgment = make_judge(make_response(giftbox=('2', '20A'), confidence=0.3)).judge('x')
    assert not judgment.usable


def test_judge_wraps_sdk_errors():
    judge = make_judge(error=TypeSafeAPIConnectionError('boom'))
    with pytest.raises(ItemJudgeError):
        judge.judge('x')


def test_judge_records_generation(monkeypatch):
    recorded = {}

    class Span:
        def update(self, **kwargs):
            recorded.update(kwargs)

    @contextmanager
    def fake_generation(name, **kwargs):
        recorded['name'] = name
        yield Span()

    monkeypatch.setattr(item_judge_module.tracing, 'generation', fake_generation)
    make_judge(make_response(giftbox=('1', '18A'))).judge('x')
    assert recorded['name'] == 'jev-item-judge'
    assert recorded['model'] == 'jev-test'
    assert recorded['usage_details'] == {'input': 1000, 'output': 20}
    assert 'total' in recorded['cost_details']


def test_generation_is_noop_when_tracing_disabled(monkeypatch):
    monkeypatch.setattr(langfuse_tracing, '_enabled', False)
    with langfuse_tracing.generation('x', model='m') as span:
        span.update(output=1)


# ---------- ChatLogImporter backend routing ----------

def make_importer(backend, judgment=None, error=None):
    importer = ChatLogImporter.__new__(ChatLogImporter)
    importer.item_judge_backend = backend
    importer.item_judge = None
    if backend != 'gpt':
        importer.item_judge = SimpleNamespace(
            judge=lambda *a, **k: (_ for _ in ()).throw(error) if error else judgment)
    return importer


def fake_judgment(fields, confidence=0.95, usable=True):
    return SimpleNamespace(fields=fields, confidence=confidence, usable=usable)


GPT_RAW = {'giftbox_spec': '20A', 'giftbox_boxes': 2}
JEV_FIELDS = ItemFields(giftbox_spec='20A', giftbox_boxes=3)


def test_gpt_backend_ignores_jev():
    problems = []
    fields = make_importer('gpt')._judge_items(GPT_RAW, '王小明', problems, '聊天', '')
    assert fields == fields_from_raw(GPT_RAW) and problems == []


def test_shadow_backend_keeps_gpt_and_flags_disagreement():
    problems = []
    importer = make_importer('shadow', fake_judgment(JEV_FIELDS))
    fields = importer._judge_items(GPT_RAW, '王小明', problems, '聊天', '')
    assert fields == fields_from_raw(GPT_RAW)
    assert any('兩模型不一致' in p for p in problems)


def test_jev_backend_uses_jev_when_confident():
    problems = []
    importer = make_importer('jev', fake_judgment(JEV_FIELDS))
    assert importer._judge_items(GPT_RAW, '王小明', problems, '聊天', '') == JEV_FIELDS


def test_jev_backend_falls_back_when_not_usable():
    problems = []
    importer = make_importer('jev', fake_judgment(JEV_FIELDS, confidence=0.3, usable=False))
    assert importer._judge_items(GPT_RAW, '王小明', problems, '聊天', '') == fields_from_raw(GPT_RAW)
    assert any('信心不足' in p for p in problems)


def test_jev_backend_flags_medium_confidence_for_review():
    problems = []
    importer = make_importer('jev', fake_judgment(JEV_FIELDS, confidence=0.6))
    importer._judge_items(GPT_RAW, '王小明', problems, '聊天', '')
    assert any('請人工確認' in p for p in problems)


def test_jev_backend_falls_back_on_error():
    problems = []
    importer = make_importer('jev', error=ItemJudgeError('timeout'))
    assert importer._judge_items(GPT_RAW, '王小明', problems, '聊天', '') == fields_from_raw(GPT_RAW)
    assert any('Jev 品項判斷失敗' in p for p in problems)


# ---------- A/B dataset and evaluation ----------

def test_dataset_is_valid():
    items = load_items(DATASET)
    validate_items(items)
    assert len(items) == sum(CATEGORY_COUNTS.values()) == 50


def test_pick_order():
    orders = [{'receiver_name': '李範例'}, {'receiver_name': '黃範例'}]
    assert pick_order(orders, '黃範例') is orders[1]
    assert pick_order(orders, None) is orders[0]
    assert pick_order(orders, '不存在') is None
    assert pick_order([], None) is None


def test_item_evaluator_scores():
    expected = {'giftbox': '20A 兩盒 $2,170', 'family': None,
                'fields': {'giftbox_spec': '20A', 'giftbox_boxes': 2, 'family_spec': None,
                           'family_boxes': None, 'shuangshuang_sets': None}}
    output = {'giftbox': '20A 兩盒 $2,170', 'family': None,
              'fields': ItemFields(giftbox_spec='20A', giftbox_boxes=2).to_dict(),
              'latency_ms': 10.0, 'input_tokens': 5, 'cost_usd': None, 'error': None}
    scores = {e.name: e.value for e in evaluators.item_evaluator(
        input={}, output=output, expected_output=expected)}
    assert scores['order_exact'] == scores['fields_exact'] == 1.0

    output['family'] = '18A 1箱 $1,850'
    scores = {e.name: e.value for e in evaluators.item_evaluator(
        input={}, output=output, expected_output=expected)}
    assert scores['giftbox_exact'] == 1.0 and scores['order_exact'] == 0.0


def test_summarize_groups_by_category_and_confidence():
    rows = [
        {'category': 'simple', 'scores': {'order_exact': 1.0, 'giftbox_exact': 1.0,
                                          'family_exact': 1.0, 'fields_exact': 1.0},
         'output': {'latency_ms': 100, 'cost_usd': 0.1, 'confidence': 0.9, 'usable': True}},
        {'category': 'amended', 'scores': {'order_exact': 0.0, 'giftbox_exact': 0.0,
                                           'family_exact': 1.0, 'fields_exact': 0.0},
         'output': {'latency_ms': 300, 'cost_usd': 0.1, 'confidence': 0.3, 'usable': False}},
    ]
    summary = evaluators.summarize(rows)
    assert summary['accuracy_order'] == 0.5
    assert summary['accuracy_by_category:simple'] == 1.0
    assert summary['accuracy_by_category:amended'] == 0.0
    assert summary['latency_ms_p95'] == 300
    assert summary['cost_usd_total'] == pytest.approx(0.2)
    assert summary['unusable_rate'] == 0.5
    assert summary['accuracy_when_usable'] == 1.0


def test_jev_task_reports_errors_without_raising():
    task = make_jev_task(make_judge(error=TypeSafeAPIConnectionError('boom')))
    output = task(item={'input': {'chat_log': 'x', 'current_date': '', 'receiver_name': None}})
    assert output['error'] and output['giftbox'] is None
