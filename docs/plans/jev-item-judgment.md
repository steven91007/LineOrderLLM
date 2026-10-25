# Switching Item Judgment to TypeSafe Jev: Implementation and A/B Evaluation Plan

Status: Implemented, first round of A/B testing complete (2026-09-28, baseline commit `754253d`)
Scope: originally planning only; implemented as described. All file names, function names, and field names are meant to be copied verbatim by the implementer.

---

## 0. Background and Summary

Currently, "item judgment" (what the customer actually ordered: category × spec × quantity) is produced as a side effect of GPT (DSPy `ChatLogParser`, `gpt-5.6-luna`) extracting the entire order JSON in one pass — it yields five fields:
`giftbox_spec / giftbox_boxes / family_spec / family_boxes / shuangshuang_sets`.
`ChatLogImporter._build_order` then uses `form_options` to turn them into Google Form dropdown option strings (column I for gift box, column J for family pack).

This plan covers four things:

1. Add a **Jev item judgment module** `src/utils/jev_modules/item_judge.py`: split item judgment into 7 independent Choice/Noul questions, send them all to Jev in one call, and have the code recombine the answers into `form_options` option strings.
2. **Langfuse tracing**: add a `generation()` helper to `src/utils/langfuse_tracing.py` so Jev calls are recorded as generations (model, usage, cost, latency, answers, and probabilities).
3. A **feature flag** `ITEM_JUDGE_BACKEND=gpt|jev|shadow` to switch between backends, defaulting to `gpt` so the existing flow is unchanged.
4. **A/B experiment**: a 50-item dataset `evals/item_judge/dataset.jsonl` → uploaded to the Langfuse dataset `item-judge-v1` → `scripts/run_item_judge_ab.py --backend gpt|jev` run once per backend → item-level evaluators (gift box column, family pack column, whole order) + run-level evaluators (accuracy, latency, tokens, cost) → compared in the Langfuse UI.

Key design principles (from the TypeSafe docs): **Select, don't generate** (every output is a choice among options), **one judgment per question**, **send all independent questions in a single call** (12.2× cheaper, 10× faster, answers are independent of each other), and **confidence-based routing** (low-confidence answers are not used; fall back to GPT's answer).

---

## 1. Current State (Facts the Implementer Needs to Know)

### 1.1 Relevant Code

| File | Current state | What this plan changes |
|---|---|---|
| `src/utils/form_options.py` | `GIFTBOX_OPTIONS` (18A/20A × 1–8), `FAMILY_OPTIONS` (18A/20A × 1–3), `SHUANGSHUANG_OPTIONS` (1–4), `giftbox_option()`, `family_option()`, `shuangshuang_option()`, `MAX_*` | Untouched. All option strings are always looked up from here |
| `src/utils/dspy_modules/chat_log_parser.py` | `ChatLogParser.forward(chat_log, current_date) -> List[dict]`, two-stage (extraction + re-check). The five item fields plus `source_quote` | Untouched. The GPT-side A/B task function calls it directly |
| `src/services/chat_log_importer.py` | `_build_order()` calls `_resolve_item()` twice plus `_resolve_shuangshuang()`, recorded via `tracing.trace('resolve-item-…')` | Extract the pure logic into `src/utils/item_resolver.py`; `_build_order` decides the source of the item fields based on the flag |
| `src/utils/langfuse_tracing.py` | `setup()`, `trace()` (span), `score()`, `flush()`, `_NullSpan` | Add `generation()` |
| `config.py` | Already has `TYPESAFE_API_KEY`, `TYPESAFE_MODEL` | Add `ITEM_JUDGE_BACKEND`, `JEV_CONFIDENCE_FLOOR`, `JEV_CONFIDENCE_REVIEW`, `JEV_TIMEOUT_SECONDS` |
| The three places that construct `ChatLogImporter` | `import_chat_log.py:62`, `chat_import_gui.py:57`, `src/handlers/discord_handler.py:121` | Don't change the caller signatures; the flag is read from `config` in `ChatLogImporter.__init__` and can be overridden by a parameter |
| `tests/` | `test_discord_format.py`, `test_offday_orders.py`, `test_sheet_locking.py`; the convention is to substitute a fake client for a real connection | Add 4 new test files (see §7) |

### 1.2 Verified SDK Facts (No Need to Re-check During Implementation)

**typesafe-sdk 0.7.2** (inspected inside `.venv`)
- `TypeSafeClient(api_key=, model=None, retry=RetryPolicy(max_retries=2, timeout=30.0), timeout=…)`; there's also `AsyncTypeSafeClient`.
- `client.system_one(state, questions, *, model=None, timeout=None) -> SystemOneResponse`
  - `response.model: str` (the actual model name, e.g. `jev-1.13.0`, not an alias)
  - `response.usage.input_tokens / output_tokens` (`int | None`)
  - `response.answers[name]`; `response.choices[name].choice / .confidence / .probabilities: dict[str, float]`
  - `response.nouls[name].noul: float` (probability of yes; Noul **has no** confidence field)
- `Choice(instructions=, criteria={name: description|None})`: up to 255 options.
- `Noul(instructions=, criteria={'true': …, 'false': …})`.
- Exception hierarchy: `TypeSafeError` ← `TypeSafeAPIError` (including `TypeSafeRateLimitError`, `TypeSafeAuthenticationError`, …), `TypeSafeAPIConnectionError`, `TypeSafeAPITimeoutError`.
- Model: `jev-latest` = `jev-preview` = `jev-1.13.0`. Pricing: **$0.042 per million input tokens, output is free**. Limits: 64k tokens/request, state capped at 32k. **Text only; English has the highest accuracy, other languages are lower** (a risk, see §9).
- Confidence definition: computed from the distribution of probabilities (for three options, `(3×max−1)/2`), ranging 0–1. The docs recommend: >0.9 auto-adopt, 0.5–0.9 adopt but flag, <0.5 don't adopt and take a different path.

**langfuse 4.14.4** (inspected inside `.venv`)
- `Langfuse.create_dataset(name=, description=, metadata=)`
- `Langfuse.create_dataset_item(dataset_name=, input=, expected_output=, metadata=, id=)`: passing a fixed `id` lets repeated runs upsert.
- `Langfuse.get_dataset(name) -> DatasetClient`; `DatasetClient.run_experiment(name=, run_name=, description=, task=, evaluators=[], run_evaluators=[], max_concurrency=50, metadata=) -> ExperimentResult`
- Task function: `def task(*, item, **kwargs)`, with `item.input / item.expected_output / item.metadata`.
- Item evaluator: `def ev(*, input, output, expected_output, metadata, **kwargs) -> Evaluation | list[Evaluation]`; `from langfuse import Evaluation` (`name, value, comment, metadata, data_type`).
- Run evaluator: `def ev(*, item_results: list[ExperimentItemResult], **kwargs)`; each `ExperimentItemResult` has `.item .output .evaluations .trace_id .dataset_run_id`.
- Each item's task runs wrapped inside an `experiment-item-run` → `experiment-item-task` span; **any generation created inside the task with `start_as_current_observation`, and any span produced by the DSPy instrumentor, are automatically attached under this trace** (via OTel context propagation), so there's no need to pass a trace id manually.
- `run_experiment`'s `metadata` is also attached to the dataset run.
- `Langfuse.start_as_current_observation(as_type='generation', name=, model=, input=, metadata=, model_parameters=, usage_details=, cost_details=)`; the span object can be updated with `.update(output=, usage_details=, cost_details=, metadata=, level=, status_message=)`.

**dspy 2.6.27**
- `ChatLogParser.forward` returns a `list`, not a `Prediction`, so `get_lm_usage()` isn't available. Read `lm.history` instead: each entry has `usage` (dict), `cost` (computed by litellm; `None` for unknown models), `model`, `timestamp`. The A/B task function sums all the LM calls for this item using the difference in `len(lm.history)` before and after the call.

### 1.3 Are There Real Chat Logs in the Project?

**No, nothing usable directly.** `.gitignore` excludes `*.txt`, `*.csv`, `*.xlsx` (explicitly noting "customer order data contains personal information and must not be committed"), and `find` inside the repo turns up no `.txt`/`.jsonl` data files. The only sample dialogue is the 4 few-shot examples in `chat_log_parser.py` (which contain what look like real names and phone numbers).

Therefore the 50 items in §5 are primarily **synthetic**, with an optional masking script provided so the user can locally turn their own exported LINE chat logs into a dataset (not committed to version control).

---

## 2. Design of Jev Item Judgment

### 2.1 What Question Does This Module Answer

Input: **a chat log + the recipient to focus on (optional) + today's date**.
Output: **the final items for one recipient** (order amendments take the last stated value), typed:

```python
@dataclass(frozen=True)
class ItemFields:                      # Exact same names as GPT's five fields, shared by both sides
    giftbox_spec: Optional[str]        # '18A' | '20A' | None
    giftbox_boxes: Optional[int]       # 1..8; over the limit still gives the actual count (e.g. 9), the resolver decides it's over the limit
    family_spec: Optional[str]
    family_boxes: Optional[int]
    shuangshuang_sets: Optional[int]
```

Jev is **not responsible** for the orderer / recipient / address / phone / last 5 digits of the transfer / date — those are still extracted by GPT's `ChatLogParser`. In the production flow, GPT always runs first (since it needs to split out each recipient), and Jev then performs an independent item judgment for each order.

### 2.2 Contents of the state

```python
state = {
    "chat_log": chat_log,                       # the full original chat log text (emoji already stripped via strip_emoji), not just the source_quote
    "focus_receiver": receiver_name or "（整段對話只有一位客人）",
    "current_date": current_date,               # e.g. "2026-09-28 (Monday)", for context only
    "catalog": {                                # generated from form_options, not hand-written
        "精選禮盒": "一盒 6 顆，規格 18A 或 20A，表單可選 1 到 8 盒。客人常寫「禮盒」「盒」。",
        "家庭號":   "一箱兩層 12 顆，規格 18A 或 20A，表單可選 1 到 3 箱。客人常寫「家庭號」「箱」。",
        "雙雙對對": "固定組合的獨立品項，不分規格，表單可選 1 到 4 組。客人常寫「雙雙對對」「雙雙」。",
    },
    "rules": [
        "同一位收件人若後來改數量或改品項，以最後一次的說法為準。",
        "明確說取消的訂單視為沒有訂購。",
        "只是詢價、還在考慮、說再想想，都不算訂購。",
        "「兩盒」「2盒」「二盒」「x2」「*2」都是 2。",
    ],
}
```

Why give the full chat log instead of GPT's `source_quote`: for the A/B test to be fair, Jev must be able to operate independently of GPT; also, `source_quote` is generated by GPT, so if GPT picks the wrong quote, Jev would inherit that mistake. `focus_receiver` is how we handle "one conversation, multiple recipients" — the state tells Jev to look only at this recipient's items.

### 2.3 Questions (7 Questions, Sent in One Call)

| id | Type | instructions (Chinese; see §9 for the English-variant experiment) | criteria |
|---|---|---|---|
| `is_order` | Noul | 「針對 `focus_receiver`，客人有沒有明確說出要買什麼（不是只問價格或還在考慮）？」 (For `focus_receiver`, did the customer clearly say what they want to buy, not just ask prices or still be considering?) | true: 已講出品項或數量 (stated an item or quantity); false: 只詢價、考慮中、已取消 (only asked prices, considering, or cancelled) |
| `giftbox_boxes` | Choice | 「客人最終要訂幾盒**精選禮盒**？改單以最後一次為準。沒有訂禮盒選 `none`。」 (How many boxes of gift box does the customer finally order? Amendments: the last statement wins. Choose `none` if no gift box.) | `none`, `1`…`8`, `more_than_8` |
| `giftbox_spec` | Choice | 「精選禮盒的規格是哪一個？沒訂禮盒或沒講規格選 `unspecified`。」 (Which spec is the gift box? Choose `unspecified` if none ordered or no spec given.) | `18A`, `20A`, `unspecified` |
| `family_boxes` | Choice | 「客人最終要訂幾箱**家庭號**？不包含雙雙對對。沒有訂家庭號選 `none`。」 (How many cases of family pack does the customer finally order? Excludes 雙雙對對. Choose `none` if no family pack.) | `none`, `1`, `2`, `3`, `more_than_3` |
| `family_spec` | Choice | 「家庭號的規格是哪一個？沒訂家庭號或沒講規格選 `unspecified`。」 (Which spec is the family pack? Choose `unspecified` if none ordered or no spec given.) | `18A`, `20A`, `unspecified` |
| `shuangshuang_sets` | Choice | 「客人最終要訂幾組**雙雙對對**？沒有訂選 `none`。」 (How many sets of 雙雙對對 does the customer finally order? Choose `none` if not ordered.) | `none`, `1`, `2`, `3`, `4`, `more_than_4` |
| `amended` | Noul | 「客人有沒有在對話中改過數量或品項？」 (Did the customer change the quantity or item during the conversation?) | Only used to populate issues/metadata; doesn't affect the answer |

Design rationale:
- Each question judges exactly one thing, with a closed set of options; `none` / `unspecified` / `more_than_N` are the catch-alls TypeSafe recommends, letting the model "decline to answer" instead of being forced into a choice.
- Quantities use a small fixed set like `1`…`8`, rather than the cookbook pattern of "pre-extract candidate snippets with regex, then choose among them": the answer space is already closed and small, so a fixed set maps directly onto `form_options` keys and can also express being over the limit (`more_than_8`). The pre-extracted-snippet approach is kept as a v2 option (it could be used to produce `source_quote`).
- Spec questions and quantity questions are kept separate: the spec is often stated in a different message (「都是 20A」, meaning "all 20A"), so asking separately lets each have its own confidence.
- The `criteria` keys use ASCII (`none`, `18A`), while the descriptions are in Chinese, so the code can match against them easily.

### 2.4 Rules for Combining Answers into `ItemFields` (Pure Code, `JevItemJudge._compose`)

```
if nouls.is_order < IS_ORDER_THRESHOLD(0.5):  → everything becomes None, issues += ['Jev 判定不是訂單']  ("Jev judged this is not an order"; the code now uses the English text)

giftbox:
  boxes = choices.giftbox_boxes.choice
  if boxes == 'none'        → giftbox_spec=None, giftbox_boxes=None
  elif boxes == 'more_than_8' → giftbox_boxes=9 (so the resolver takes its existing "超過上限需拆單" (over the limit, split the order) path)
  else                      → giftbox_boxes=int(boxes)
  spec = choices.giftbox_spec.choice; 'unspecified' → None (the resolver will report "有數量但沒有規格" (quantity but no spec))
family / shuangshuang follow the same logic (more_than_3 → 4; more_than_4 → 5)
```

**Confidence calculation**: `judgment.confidence = min(the confidence of every Choice that "affects the answer")`, including only the questions actually used (e.g. if giftbox chooses `none`, `giftbox_spec` is not included). Noul has no confidence; `is_order` is converted to 0–1 via `abs(noul − 0.5) × 2` and included in the min as well.

**Routing thresholds** (configurable):
- `confidence < JEV_CONFIDENCE_FLOOR (0.5)` → `judgment.usable = False`; production falls back to the GPT fields, and issues gets "Jev 信心不足，採用 GPT 判斷" (Jev confidence too low, using GPT's judgment) added.
- `0.5 ≤ confidence < JEV_CONFIDENCE_REVIEW (0.8)` → adopted, but `problems` gets "Jev 品項判斷信心 0.xx，請人工確認" (Jev item judgment confidence 0.xx, please confirm manually) added, and the order moves to `review` status.
- `≥ 0.8` → adopted directly.
- One more hard rule: whenever Jev's and GPT's `ItemFields` disagree (regardless of confidence), a problem "品項判斷兩模型不一致：GPT=…，Jev=…" (item judgment disagreement between the two models: GPT=…, Jev=…) is added — this is the most valuable signal for manual review.

The thresholds initially follow the conservative values from the TypeSafe docs; once the A/B test is done, they'll be tuned using "confidence vs. accuracy" (§6.5's `confidence_bucket_accuracy`).

### 2.5 Module Interface

`src/utils/jev_modules/__init__.py` (empty)
`src/utils/jev_modules/item_judge.py`:

```python
IS_ORDER_THRESHOLD = 0.5
GIFTBOX_BOXES_CRITERIA = {'none': '沒有訂精選禮盒', '1': None, …, '8': None, 'more_than_8': '超過 8 盒'}
… (the rest of the criteria constants)

def build_state(chat_log: str, receiver_name: Optional[str], current_date: str) -> dict
def build_questions(lang: str = 'zh') -> dict[str, Choice | Noul]     # lang is for the §9 English-variant experiment

@dataclass(frozen=True)
class ItemJudgment:
    fields: ItemFields
    confidence: float
    usable: bool                     # confidence >= floor
    is_order: float                  # the raw noul value
    amended: float
    answers: dict[str, dict]         # per question: {'choice'|'noul', 'confidence', 'probabilities'}, for tracing and the dataset
    issues: list[str]
    model: str
    usage: dict[str, Optional[int]]  # {'input_tokens':…, 'output_tokens':…}
    latency_ms: float
    cost_usd: float

class ItemJudgeError(Exception): ...   # wraps TypeSafeError / timeouts, so the caller only needs to catch this one

class JevItemJudge:
    def __init__(self, api_key: str, model: Optional[str] = None,
                 client: Optional[TypeSafeClient] = None,    # a fake client can be injected for testing
                 timeout_seconds: float = 10.0,
                 confidence_floor: float = 0.5)
    def judge(self, chat_log: str, receiver_name: Optional[str] = None,
              current_date: str = '') -> ItemJudgment
    def close(self)
```

Inside `judge()`: `build_state` → `build_questions` → `with tracing.generation(...)` → `client.system_one(...)` → `_compose` → `span.update(...)` → return. **The module does not import langfuse directly**; it only uses `tracing.generation`.

### 2.6 A Shared Resolver (So GPT and Jev Take the Same "Fields → Option String" Path)

A new file `src/utils/item_resolver.py` moves `ChatLogImporter._resolve_item_inner`, `_resolve_shuangshuang_inner`, and the "family pack vs. 雙雙對對 (pair set), pick one" section into pure functions (behavior stays exactly the same, including all problem message text):

```python
@dataclass(frozen=True)
class ResolvedItems:
    giftbox: Optional[str]     # column I option string, or None
    family: Optional[str]      # column J option string, or None (family pack or 雙雙對對)
    problems: list[str]

def fields_from_raw(raw: dict) -> ItemFields          # reads the five fields from GPT's dict (tolerates stringified numbers)
def resolve_items(fields: ItemFields) -> ResolvedItems # the original logic of _resolve_item_inner
```

`ChatLogImporter._resolve_item / _resolve_shuangshuang` become thin wrappers: they keep the `tracing.trace('resolve-item-…')` span and call `resolve_items` internally. Both A/B task functions also call `resolve_items`, ensuring the output format is consistent.

---

## 3. Architectural Positioning and the Feature Flag

### 3.1 Positioning Under the CLAUDE.md Guidelines

CLAUDE.md says "all AI/LLM functionality is implemented with DSPy." Jev is not a generative LLM (it doesn't produce text, has no prompt/completion concept, and DSPy has no corresponding adapter), so forcing it into DSPy wouldn't make sense. The proposal is to change the guideline to "**two kinds of AI calls, two directories**":

- Generative LLM (extraction, normalization, text generation) → DSPy, under `src/utils/dspy_modules/`
- Decision-type judgment (Choice / Noul / Score, returning typed answers and probabilities) → TypeSafe Jev, under `src/utils/jev_modules/`
- Both route tracing uniformly through `src/utils/langfuse_tracing.py`; DSPy is captured automatically by the instrumentor, while Jev is recorded manually with `tracing.generation()` (still centralized in the tracing module; the modules themselves don't touch langfuse).
- Both need a fallback: Jev's fallback is GPT's fields (always available in production).

**Specific changes to CLAUDE.md** (implementation step 0):
1. In the "AI/LLM Implementation Guidelines" section, change the first bullet to the two-call split described above, and add a line: "Jev modules go under `src/utils/jev_modules/`; each module should have two pure functions, `build_state()` and `build_questions()`, to make testing and dataset replay easy."
2. Add to "Implementation Notes": "Jev calls are recorded with `tracing.generation()` and must include `model`, `usage_details`, and `cost_details`."
3. Add a section to "Development Log": "2026-09 Item Judgment Jev A/B," listing the flag, dataset, and script locations.

**ADR**: add `docs/adr/0001-jev-for-item-judgment.md` (`docs/agents/domain.md` expects this directory to exist; it currently doesn't). Contents: the decision "switch item judgment to a decision model + GPT fallback," alternatives considered (pure GPT, pure rules, Jev with pre-extracted candidates), and consequences (one more vendor, Chinese-accuracy risk, near-zero cost).
**CONTEXT.md**: add a term to the Language section: "**品項判斷 (item judgment)**: inferring a recipient's final category/spec/quantity from the conversation; the output must fall within the Google Form's options. _Avoid_: 品項辨識 (item recognition), 商品抽取 (product extraction)."

### 3.2 Feature Flag

Add to `config.py`:
```python
ITEM_JUDGE_BACKEND = os.getenv('ITEM_JUDGE_BACKEND', 'gpt')      # 'gpt' | 'jev' | 'shadow'
JEV_CONFIDENCE_FLOOR = float(os.getenv('JEV_CONFIDENCE_FLOOR', '0.5'))
JEV_CONFIDENCE_REVIEW = float(os.getenv('JEV_CONFIDENCE_REVIEW', '0.8'))
JEV_TIMEOUT_SECONDS = float(os.getenv('JEV_TIMEOUT_SECONDS', '10'))
```
`.env.example` gets the same additions (with comments explaining the three modes).

Behavior of the three modes in `ChatLogImporter._build_order`:

| Mode | Source of item fields | Is Jev called | Purpose |
|---|---|---|---|
| `gpt` (default) | GPT's five fields | No | Current behavior, zero risk |
| `shadow` | GPT's five fields | Yes, but the result is only recorded: Langfuse score `item_judge_agreement` (1/0) + a problem added on disagreement | Accumulate comparison data for free on real traffic before going live |
| `jev` | Jev's five fields (when `usable`); otherwise GPT's five fields | Yes | The actual switch-over |

`ChatLogImporter.__init__` gets a new parameter `item_judge_backend: Optional[str] = None` (None → read from config); if it's `jev`/`shadow` and `TYPESAFE_API_KEY` is set, it builds `self.item_judge = JevItemJudge(...)`; without a key it logs a warning and falls back to `gpt`. None of the three construction sites need to change (they all use the default). `import_chat_log.py` gets a `--item-judge gpt|jev|shadow` argument for easy manual testing.

Sketch of the new code added to `_build_order`:
```python
gpt_fields = fields_from_raw(raw)
fields, judgment = gpt_fields, None
if self.item_judge is not None:
    try:
        judgment = self.item_judge.judge(self._current_chat_log, receiver_name, self._current_date)
    except ItemJudgeError as error:
        problems.append(f'Jev 品項判斷失敗，採用 GPT 判斷（{error}）')
    else:
        agree = judgment.fields == gpt_fields
        tracing.score('item_judge_agreement', 1.0 if agree else 0.0, comment=…)
        if not agree: problems.append('品項判斷兩模型不一致：…')
        if self.item_judge_backend == 'jev' and judgment.usable:
            fields = judgment.fields
            if judgment.confidence < self.confidence_review: problems.append('Jev 品項判斷信心 …，請人工確認')
        elif self.item_judge_backend == 'jev':
            problems.append('Jev 信心不足，採用 GPT 判斷')
resolved = resolve_items(fields)
problems.extend(resolved.problems)
giftbox, family = resolved.giftbox, resolved.family
```
`_build_order` currently has no access to the full chat_log or current_date, so they need to be stored on `self._current_chat_log / self._current_date` inside `parse()` (or the signature could be changed to `_build_order(raw, moment, chat_log, current_date)` — the latter is cleaner and recommended). The Jev call falls inside the `order-build` span, so it's automatically attached to that order's session.

---

## 4. Langfuse Tracing

### 4.1 Adding `generation()` to `langfuse_tracing.py`

```python
@contextmanager
def generation(name: str, *, model: Optional[str] = None, input_data: Any = None,
               metadata: Optional[Dict[str, Any]] = None,
               model_parameters: Optional[Dict[str, Any]] = None):
    """Create a generation observation (for LLM / decision-model calls the DSPy instrumentor can't capture).

    The only differences from trace() are as_type='generation' and the extra model/model_parameters;
    the caller fills in the rest before exiting with span.update(output=…, usage_details={'input': n, 'output': m},
    cost_details={'input': usd, 'total': usd}, metadata={…}).
    When tracing isn't enabled, yields _NullSpan, same as trace().
    """
```
Implemented the same way as `trace()` (ExitStack + `start_as_current_observation(as_type='generation', ...)`), with identical error-handling logic (swallow only a creation failure; exceptions from the body propagate unchanged).

### 4.2 How the Jev Module Records Tracing

```python
with tracing.generation(
    'jev-item-judge',
    model=self.model or 'jev-latest',          # write the alias going in
    input_data={'state': state, 'questions': questions_as_dict},
    metadata={'backend': 'jev', 'receiver_name': receiver_name, 'question_ids': [...]},
) as span:
    started = perf_counter()
    response = self._client.system_one(state=state, questions=questions, timeout=self.timeout)
    latency_ms = (perf_counter() - started) * 1000
    judgment = self._compose(response, latency_ms)
    span.update(
        model=response.model,                   # the actual model, jev-1.13.0
        output={'fields': asdict(judgment.fields), 'confidence': judgment.confidence,
                'usable': judgment.usable, 'answers': judgment.answers, 'issues': judgment.issues},
        usage_details={'input': response.usage.input_tokens or 0, 'output': response.usage.output_tokens or 0},
        cost_details={'input': judgment.cost_usd, 'total': judgment.cost_usd},
        metadata={'latency_ms': latency_ms, 'confidence': judgment.confidence, 'usable': judgment.usable},
        level='WARNING' if not judgment.usable else None,
    )
```
On exception: `span.update(level='ERROR', status_message=str(error))`, then `raise ItemJudgeError(...) from error`.

Cost: `JEV_USD_PER_INPUT_TOKEN = 0.042 / 1_000_000` (a constant in item_judge.py, noting the source as docs.typesafe.ai/models). Also add a `jev` pricing entry in Langfuse project settings → Models (match pattern `(?i)^jev`, input $0.042/M, output $0), so the UI can still compute cost even if someone forgets to pass `cost_details`.

### 4.3 What You'll See in Langfuse

- Production: under `order-build` (session = recipient | phone | date) there's now an extra `jev-item-judge` generation, with state+questions as input, answers and probabilities as output, and usage/cost/latency; the same trace also has existing spans like `resolve-item-禮盒` (resolve-item-gift box). `shadow`/`jev` modes will have an `item_judge_agreement` score.
- Experiments: one trace per dataset item (`experiment-item-run`), with `experiment-item-task` underneath → either the `jev-item-judge` generation inside the task function, or DSPy's `ChainOfThought` span (captured automatically by the instrumentor, provided `tracing.setup()` was called before the task function runs).

---

## 5. A/B Dataset

### 5.1 File and Schema

File: `evals/item_judge/dataset.jsonl` (committed to version control; purely synthetic data). One item per line:

```json
{
  "id": "ij-007",
  "input": {
    "chat_log": "2026/09/21 09:14\t周香香\t我要訂18A兩盒\n2026/09/21 09:40\t周香香\t不好意思改成四盒好了",
    "current_date": "2026-09-21 (星期一)",
    "receiver_name": null
  },
  "expected_output": {
    "giftbox": "18A 四盒 $3,700",
    "family": null,
    "fields": {"giftbox_spec": "18A", "giftbox_boxes": 4, "family_spec": null, "family_boxes": null, "shuangshuang_sets": null}
  },
  "metadata": {
    "category": "amended",
    "difficulty": "medium",
    "note": "改單以最後一次為準",
    "source": "synthetic"
  }
}
```

- `input.receiver_name`: only has a value for the multi-recipient category; both backends use it to pick the order.
- `expected_output.giftbox / family`: **must be a string that exists verbatim in the `form_options` tables, or null** (verified by tests).
- `expected_output.fields`: the original five fields, so "over the limit" and "no order" can be distinguished (over the limit: `giftbox_boxes: 9`, `giftbox: null`).
- `metadata.category` enum (verified by tests): `simple`, `amended`, `numeral`, `multi_item`, `shuangshuang`, `no_order`, `over_limit`, `spec_missing`, `multi_receiver`.

### 5.2 Distribution and Content Direction of the 50 Items

| category | Count | Content direction |
|---|---|---|
| `simple` | 10 | Single item, spec and quantity in the same message or two adjacent messages: 「20A兩盒」("two boxes of 20A") 「家庭號18A一箱」("one case of 18A family pack") 「禮盒 20a x3」("gift box 20a x3") |
| `amended` | 8 | Quantity changes (2→4), spec changes (18A→20A), category changes (gift box→family pack), additive top-ups (「先1盒…再加1盒」("1 box first... then 1 more") = 2), changed and then changed back |
| `numeral` | 6 | Chinese numerals and colloquial phrasing: 「兩盒」("two boxes") 「三箱」("three cases") 「四組」("four sets") 「一共六盒」("six boxes in total") 「十盒」("ten boxes", over the limit), 「盒數: 貳」("quantity: two" in formal numeral) |
| `multi_item` | 6 | Gift box + family pack together: 「18A禮盒兩盒和家庭號一箱」("two boxes of 18A gift box and one case of family pack"); spec stated separately: 「禮盒20A、家庭號18A」("gift box 20A, family pack 18A") |
| `shuangshuang` | 5 | 「雙雙對對兩組」("two sets of 雙雙對對 (pair set)") 「雙雙*2」("pair set x2") 「雙雙對對一組加20A禮盒一盒」("one set of pair set plus one box of 20A gift box") (column J picks only one → expected family=雙雙對對, with a problem added) |
| `no_order` | 5 | Price inquiries, 「再想想」("let me think about it"), 「先取消」("cancel for now"), small talk between the shop owner and the customer, only the address mentioned with no items |
| `over_limit` | 3 | 「禮盒9盒」("9 boxes of gift box") 「家庭號4箱」("4 cases of family pack") 「雙雙對對5組」("5 sets of pair set") → both columns expected to be null, with fields carrying the actual count |
| `spec_missing` | 3 | 「我要三盒」("I want three boxes") with no spec mentioned → expected giftbox null, fields.giftbox_boxes=3, spec null |
| `multi_receiver` | 4 | One conversation with two recipients, each with different items; `receiver_name` specifies one of them |

Total: 50. Difficulty is tagged `easy/medium/hard`, to make filtering in the UI easy.

**How to generate**: written by hand by the implementer (or drafted by an LLM and then manually checked item by item); names always use obviously fake names (王小明, 陳小美, …), phone numbers always `09xx000xxx`, and addresses use made-up street names like 「台北市信義區測試路 1 號」("No. 1, Test Rd., Xinyi Dist., Taipei City"). The format mimics a LINE export (`date\ttime\tspeaker\tcontent`, consistent with the few-shot examples). **Each item's expected_output is labeled once by two people (or by the same person on two different days), and any mismatches are discussed and settled on**, to avoid incorrectly labeled ground truth skewing the A/B test.

**Optional: a real-log masking script** `scripts/mask_chat_log.py <in.txt> <out.jsonl>`: replaces phone numbers, addresses (anything below the county/district level that `taiwan_address` can recognize), and speakers that look like real names with fake values, outputting an unlabeled jsonl for manual completion of expected_output. Output files go in `evals/item_judge/private/` (added to `.gitignore`). This is not required for the first round.

### 5.3 Upload Script `scripts/upload_item_judge_dataset.py`

```
uv run python scripts/upload_item_judge_dataset.py --file evals/item_judge/dataset.jsonl --name item-judge-v1
```
- First runs `evals/item_judge/schema.py::validate_items()` (shared with pytest).
- `langfuse.create_dataset(name, description='品項判斷 A/B（GPT vs Jev）', metadata={'version': 'v1', 'items': 50, 'git_sha': …})` (skipped if it already exists).
- For each item, `create_dataset_item(dataset_name, id=item['id'], input=…, expected_output=…, metadata=…)` — the fixed `id` makes re-runs an upsert.
- Finishes with `flush()`, printing the item count and the dataset URL.
- If the dataset changes, bump the name (`item-judge-v2`) rather than editing v1 in place, otherwise the comparison baseline for old runs will drift.

---

## 6. A/B Experiment Design

### 6.1 Two Task Functions, Same Input and Output

File: `evals/item_judge/tasks.py`

Shared output format (a dict; evaluators only recognize these keys):
```python
{
  'giftbox': Optional[str], 'family': Optional[str],           # option strings
  'fields': {five fields},                                     # ItemFields
  'problems': [str],
  'backend': 'gpt' | 'jev', 'model': str,
  'latency_ms': float, 'input_tokens': int, 'output_tokens': int, 'cost_usd': Optional[float],
  'confidence': Optional[float],   # jev only
  'usable': Optional[bool],        # jev only
  'order_count': Optional[int],    # gpt only: how many orders ChatLogParser extracted
  'error': Optional[str],          # filled in on an exception from either side, so the run doesn't abort
}
```

**GPT task** `make_gpt_task(lm, parser, stage='full')`:
- Runs the **full `ChatLogParser.forward`** (extraction + re-check), because that's exactly how production's item fields are produced; cost and latency must also be the full amount, since that's what's actually "being replaced." `--gpt-stage parse` can run only the first stage (for anyone who wants to know how much the re-check adds to cost).
- Picking the order: if `input.receiver_name` has a value, take the one matching `receiver_name`; otherwise take the first one; 0 matches → all five fields None.
- `fields_from_raw(order)` → `resolve_items(fields)`.
- Latency: wrap `forward` with `perf_counter`. Tokens/cost: record `n = len(lm.history)` before the call, then sum `usage.prompt_tokens / completion_tokens / cost` over `lm.history[n:]` after the call; when `cost` is None, compute it manually with `--gpt-price-in/--gpt-price-out` (USD/M tokens), and if those aren't given either, `cost_usd=None`.
- `dspy.context(lm=lm)` is wrapped inside the task function (each item runs in its own thread).

**Jev task** `make_jev_task(judge)`:
- `judge.judge(chat_log, receiver_name, current_date)` → `resolve_items(judgment.fields)`.
- `ItemJudgeError` → the `error` field is set and all five fields are None (this is recorded as an error, which is correct: production would fail here too).
- Note: this run measures "Jev alone"'s accuracy, not including production's GPT fallback. To see the cascade effect, a third run `--backend jev-cascade` (falls back to the GPT task's result when confidence is low, with cost = both added together) is left for v2.

### 6.2 Item-Level Evaluators (`evals/item_judge/evaluators.py`)

| name | value | Description |
|---|---|---|
| `giftbox_exact` | 0/1 | `output['giftbox'] == expected['giftbox']` (None==None counts as correct) |
| `family_exact` | 0/1 | Same as above, for column J |
| `order_exact` | 0/1 | Both columns correct = this order would be written into the spreadsheet correctly |
| `fields_exact` | 0/1 | All five fields exactly equal `expected['fields']` (distinguishes "correctly judged as over the limit" from "missed judgment") |
| `latency_ms` | float | Copied directly from `output['latency_ms']` |
| `cost_usd` | float | Copied directly (None → 0, with a comment noting it's unknown) |
| `input_tokens` | int | Copied |
| `errored` | 0/1 | Whether `output['error']` has a value |
| `confidence` | float | Only returned for jev (gpt doesn't return this evaluation) |

Each evaluator's `comment` is written as "expected=… got=…", so it's immediately visible in the UI where it went wrong.

### 6.3 Run-Level Evaluators

| name | Computation |
|---|---|
| `accuracy_order` | mean(order_exact) |
| `accuracy_giftbox` / `accuracy_family` / `accuracy_fields` | mean of each respectively |
| `accuracy_by_category:<cat>` | mean(order_exact) per category, 9 evaluations in total |
| `latency_ms_mean` / `latency_ms_p95` | Distribution |
| `cost_usd_total` / `cost_usd_per_item` | Sum, average |
| `input_tokens_mean` | Average |
| `error_rate` | mean(errored) |
| `unusable_rate` | Jev only: the proportion where confidence < floor (= the proportion production would fall back to GPT) |
| `accuracy_when_usable` | Jev only: the order accuracy counting only usable items (the ceiling for the cascade) |
| `confidence_bucket_accuracy:<0.5 / 0.5-0.8 / >=0.8` | Used to tune the thresholds in §2.4 |

### 6.4 Execution Script `scripts/run_item_judge_ab.py`

```
uv run python scripts/run_item_judge_ab.py --backend gpt --dataset item-judge-v1 [--model gpt-5.6-luna] [--gpt-stage full|parse] [--concurrency 3] [--tag a]
uv run python scripts/run_item_judge_ab.py --backend jev --dataset item-judge-v1 [--model jev-latest] [--lang zh|en] [--concurrency 8] [--tag a]
```
- Starts with `tracing.setup()` (otherwise neither the DSPy spans nor the Jev generation would end up in the experiment trace).
- `run_name = f'{backend}__{model}__{YYYY-MM-DD}{tag}'`, e.g. `gpt__gpt-5.6-luna__2026-09-28a`, `jev__jev-1.13.0__2026-09-28a`.
- `metadata={'backend', 'model', 'gpt_stage', 'lang', 'confidence_floor', 'git_sha', 'dataset'}` (attached to the dataset run).
- `dataset.run_experiment(name='item-judge', run_name=…, description=…, task=…, evaluators=…, run_evaluators=…, max_concurrency=…, metadata=…)`.
- Finishes by printing `result.dataset_run_url` and the run-level score table (plain text, one per line), then `flush()`.
- GPT `--concurrency` defaults to 3 (the reasoning model takes 20–60 seconds per item; avoids rate limits); Jev defaults to 8.
- Since GPT uses `temperature=1.0` (forced for reasoning models), **GPT must be run at least twice** (`--tag a`, `--tag b`) to see the variance; otherwise a single-run difference might just be noise.

### 6.5 Comparing in the Langfuse UI

1. Datasets → `item-judge-v1` → Runs: one row per run, with run-level scores (`accuracy_order`, `latency_ms_mean`, `cost_usd_total`, …) side by side.
2. Select two runs → Compare: one row per item, showing both sides' output and item-level scores; you can filter by `giftbox_exact=0` to find the wrong ones.
3. Click into an item's trace: Jev's generation has the full probabilities; GPT's has the prompt/completion, letting you compare why it went wrong.
4. 50 items has limited statistical power: the accuracy gap needs to be ≥ 15 percentage points to be meaningful (the binomial distribution's 95% interval is roughly ±14%). If the gap is small, expand the dataset to 100–150 items before drawing conclusions.

---

## 7. Tests (pytest, all mocked, no network access)

`tests/test_item_resolver.py`
- Carries over every existing branch of `_resolve_item_inner`: quantity without spec, spec without quantity, non-numeric quantity, over the limit, option not found, 雙雙對對 and family pack both present (pick one and add a problem), `18 a`→`18A`.
- `fields_from_raw` tolerates the strings `"2"`, `None`, `""`.

`tests/test_item_judge.py`
- `FakeTypeSafeClient.system_one(state, questions, **kw)` returns an object assembled from `ChoiceAnswer(choice=…, confidence=…, probabilities=…)`, `NoulAnswer(noul=…)`, `Usage(input_tokens=…)`, `SystemOneResponse(model='jev-test', usage=…, answers=…)`; it also records the state/questions it received.
- `build_state`: includes chat_log, focus_receiver (the fallback text when None), catalog sourced from form_options (stays in sync if the option tables change).
- `build_questions`: all 7 ids present; every Choice has a `none`/`unspecified`-type catch-all; quantity criteria match `MAX_*` (8/3/4).
- `_compose`: `none` → None; `more_than_8` → 9; spec `unspecified` → None; is_order < 0.5 → all None + issue; confidence takes the min over only the questions actually used; usable depends on the floor.
- `judge`: exceptions (`TypeSafeAPIConnectionError`, `TypeSafeRateLimitError`) → `ItemJudgeError`; on success, `tracing.generation` is called and `span.update` receives `usage_details`/`cost_details`/`model` (monkeypatch `tracing.generation` with a recording context manager).
- Cost calculation: 1000 tokens → 0.000042 USD.

`tests/test_langfuse_tracing_generation.py`
- When not enabled, `generation()` yields `_NullSpan`, and `update` doesn't blow up.
- When enabled (monkeypatch `get_client` to return a fake client), `start_as_current_observation` is called with `as_type='generation'`; exceptions from the body propagate unchanged.

`tests/test_chat_log_importer_item_judge.py`
- Uses `ChatLogImporter.__new__` to bypass construction (following the pattern in `test_offday_orders.py`), injecting a fake `item_judge` and a fake `sheet_client`.
- `gpt` mode: judge is not called.
- `shadow` mode: GPT's fields win; problems contains "兩模型不一致" (models disagree) on disagreement, and doesn't when they agree.
- `jev` mode: usable → Jev's fields; not usable → GPT's fields + problem; `ItemJudgeError` → GPT's fields + problem; confidence between floor and review → adds "請人工確認" (please confirm manually).

`tests/test_item_judge_eval.py`
- `dataset.jsonl`: exactly 50 items, unique ids, category within the enum, `expected_output.giftbox/family` exists verbatim in the values of `GIFTBOX_OPTIONS/FAMILY_OPTIONS/SHUANGSHUANG_OPTIONS` or is null, all five `fields` keys present, `over_limit`'s two columns must be null, `multi_receiver` must have `receiver_name`, and each category's count matches the §5.2 table.
- evaluators: None==None counts as correct, a one-comma difference in the string counts as wrong, `order_exact` requires both columns to be correct.
- run evaluators: feed in 3–4 fake `ExperimentItemResult`s (using `SimpleNamespace` or directly constructing `ExperimentItemResult(item=…, output=…, evaluations=…, trace_id=None, dataset_run_id=None)`) to verify mean/p95/grouping by category.
- tasks: the GPT task's order-picking logic (matching receiver_name, taking the first when there are multiple, all None when there are 0), using a fake parser; the Jev task using a fake judge; exceptions → the `error` field is set instead of raising.

---

## 8. Implementation Steps (in order, each verifiable)

| # | Step | Output | Verification |
|---|---|---|---|
| 0 | Docs first: update CLAUDE.md (§3.1), add `docs/adr/0001-jev-for-item-judgment.md`, add "品項判斷 (item judgment)" to CONTEXT.md | 3 documents | review |
| 1 | Extract `src/utils/item_resolver.py` (`ItemFields`, `ResolvedItems`, `fields_from_raw`, `resolve_items`); `ChatLogImporter` is changed to call it, with the span and message text unchanged | New file + importer changes | `tests/test_item_resolver.py` passes; the existing 3 test files still pass; the preview `import_chat_log.py` produces for a chat log is byte-identical to before the change |
| 2 | `langfuse_tracing.generation()` | Tracing changes | `tests/test_langfuse_tracing_generation.py` passes |
| 3 | `src/utils/jev_modules/item_judge.py` (`build_state`, `build_questions`, `JevItemJudge`, `ItemJudgment`, `ItemJudgeError`) | New file | `tests/test_item_judge.py` passes; `scripts/judge_item.py "我要訂20A兩盒"` (a small CLI that prints fields/confidence/probabilities/latency) can connect and answer, and the `jev-item-judge` generation shows up in Langfuse with model/usage/cost |
| 4 | Add 4 variables to config + `.env.example`; `ChatLogImporter.__init__` accepts `item_judge_backend`, `_build_order` routes by mode; `import_chat_log.py` gets `--item-judge` | config/importer/CLI changes | `tests/test_chat_log_importer_item_judge.py` passes; running a chat log with `ITEM_JUDGE_BACKEND=shadow` shows the generation and the `item_judge_agreement` score inside the `order-build` trace in Langfuse |
| 5 | Write `evals/item_judge/dataset.jsonl` (50 items) + `evals/item_judge/schema.py` | Dataset | the dataset tests in `tests/test_item_judge_eval.py` pass |
| 6 | `scripts/upload_item_judge_dataset.py` | Script | the Langfuse UI shows `item-judge-v1` with 50 items; re-running doesn't turn it into 100 |
| 7 | `evals/item_judge/evaluators.py`, `evals/item_judge/tasks.py` | Modules | `tests/test_item_judge_eval.py` passes entirely |
| 8 | `scripts/run_item_judge_ab.py` | Script | first use `--limit 3` (a new argument: only run the first N items locally, without creating a dataset run) to confirm the trace structure is correct |
| 9 | The real runs: `gpt` ×2 (tag a/b), `jev` ×1 (zh), `jev` ×1 (`--lang en`, see §9) | 4 dataset runs | compare in the UI; paste the run URLs and run-level score table into the "Results" section at the end of this document |
| 10 | Decide based on the results: tune `JEV_CONFIDENCE_FLOOR/REVIEW`, whether the default should switch to `shadow`, whether a v2 is needed (cascade run, pre-extracted candidates, a larger dataset) | Record the decision in the ADR's Consequences | — |

Steps 1–2 and 3 can run in parallel; 4 depends on 1–3; 5–7 can run in parallel with 3–4; 8 depends on 3 and 7; 9 depends on 6 and 8.

---

## 9. Risks and Open Questions

**Risks**

1. **Chinese-language accuracy**: TypeSafe explicitly states English is most accurate and other languages are lower. Mitigation: `build_questions(lang='en')` provides English instructions/criteria descriptions (the state content is still the Chinese conversation); the A/B test runs an extra `jev --lang en` run for comparison, and the default switches if the English version is clearly better.
2. **Order amendments require cross-message temporal reasoning**: this is the category where System One "fast thinking" is most likely to lose to GPT. The `amended` category is specifically given 8 items just to measure this. If Jev is noticeably worse on `amended` but wins everywhere else, v2 could add a `"messages"` array to the state (each message numbered), or use a cascade (fall back to GPT when the `amended` noul is high).
3. **Focusing on multiple recipients**: `focus_receiver` is just a field in the state, and Jev may not necessarily respect it. The 4 `multi_receiver` items will expose this; if it fails, production could also put GPT's `source_quote` into the state as a `focus_hint` (though the experiment run would still keep its input independent).
4. **GPT cost unknown**: if `gpt-5.6-luna` isn't in litellm's price table, `lm.history[].cost` is None. Either ask the user for the actual unit price, or add an entry to Langfuse's Models settings; the script provides `--gpt-price-in/--gpt-price-out` as a fallback.
5. **GPT is non-deterministic**: the reasoning model forces temperature 1.0, so GPT needs to run twice to estimate variance.
6. **50 items has insufficient statistical power**: see §6.5; treat it as a smoke-level comparison first, and expand to 100+ if the gap is small.
7. **`run_experiment` concurrency and DSPy**: tasks run across multiple threads; `dspy.context(lm=…)` is thread-local, so it must be wrapped inside the task function; sharing a single `ChatLogParser` instance (stateless) is fine. `TypeSafeClient` is a synchronous httpx client and is thread-safe, so a single shared instance is fine.
8. **Family pack / 雙雙對對 option strings haven't been checked against the Google Form yet** (per a comment in `form_options.py`): this doesn't affect the A/B test (both sides use the same table), but the existing problem message text must be kept before writing for real.
9. **Jev's rate limit** of 1,200 rpm is far beyond what's needed; GPT is the actual bottleneck.

**Open Questions (for the user to answer)**

1. What's the input/output unit price for `gpt-5.6-luna`? (Without it, the cost comparison can only list token counts.)
2. Is there a local LINE export that could be masked to build a second "real-distribution" dataset (`item-judge-real-v1`, not committed to version control)? The category distribution in the synthetic data is a guess; the real distribution might be 80% `simple`.
3. In `jev` mode, should Jev/GPT disagreement always force a `review` status (the current plan: always add a problem → review)? This would lower the ready_ratio, but it's safer before trust is established.
4. Should the dataset also cover scenarios where "the sender ≠ the recipient, and one orderer has multiple orders that are all the same item" — a case GPT often misses? This falls under "order extraction" rather than "item judgment"; I'd suggest not including it in this A/B test and opening a separate issue instead.
5. Do you agree with relaxing CLAUDE.md's "all AI unified under DSPy" to "generation uses DSPy, judgment uses Jev"?

---

## 10. File List (New/Modified Overview)

Added
- `src/utils/jev_modules/__init__.py`
- `src/utils/jev_modules/item_judge.py`
- `src/utils/item_resolver.py`
- `evals/item_judge/__init__.py`, `schema.py`, `tasks.py`, `evaluators.py`, `dataset.jsonl`
- `scripts/judge_item.py`, `scripts/upload_item_judge_dataset.py`, `scripts/run_item_judge_ab.py`, (optional) `scripts/mask_chat_log.py`
- `tests/test_item_resolver.py`, `tests/test_item_judge.py`, `tests/test_langfuse_tracing_generation.py`, `tests/test_chat_log_importer_item_judge.py`, `tests/test_item_judge_eval.py`
- `docs/adr/0001-jev-for-item-judgment.md`

Modified
- `src/utils/langfuse_tracing.py` (+`generation()`)
- `src/services/chat_log_importer.py` (resolver extracted, flag-based routing, `_build_order` signature gains chat_log/current_date)
- `config.py`, `.env.example` (+4 variables)
- `import_chat_log.py` (+`--item-judge`)
- `CLAUDE.md`, `CONTEXT.md`
- `.gitignore` (+`evals/item_judge/private/`)

Unchanged
- `src/utils/form_options.py`, `src/utils/dspy_modules/chat_log_parser.py`, the three `ChatLogImporter` construction sites

---

## Results (2026-09-28, dataset `item-judge-v1`, 50 synthetic items)

| run | accuracy_order | accuracy_giftbox | accuracy_family | accuracy_fields | latency_ms_mean | latency_ms_p95 | cost_usd_total |
|---|---|---|---|---|---|---|---|
| `gpt__gpt-5.6-luna__2026-09-28a` | 0.98 | 0.98 | 1.00 | 0.94 | 6,541 | 9,361 | $0.0793 |
| `gpt__gpt-5.6-luna__2026-09-28b` | 0.98 | 0.98 | 1.00 | 0.98 | 5,924 | 8,193 | $0.0771 |
| `jev__jev-latest-zh__2026-09-28a` | **1.00** | 1.00 | 1.00 | 0.98 | **237** | 264 | **$0.0034** |
| `jev__jev-latest-en__2026-09-28a` | **1.00** | 1.00 | 1.00 | 0.98 | 244 | 275 | $0.0033 |

- GPT cost is computed using litellm's price table (gpt-5.6-luna: input $0.20/M, output $1.20/M) and includes the full ChatLogParser (extraction + re-check); Jev is computed at $0.042/M input and only does item judgment. So the cost and latency comparison is of "the part being replaced in production," not of equal workloads.
- **GPT's only mistake (wrong both times)**: `ij-023`, 「18A十盒」("10 boxes of 18A"); after the shop owner said 「表單最多選到8盒」("the form only goes up to 8 boxes"), GPT output 8 boxes → which would be written as `18A 八盒 $7400`, **2 boxes short, and without being flagged for manual confirmation**. Jev chose `more_than_8`, and the resolver flagged "超過上限需拆單" (over the limit, needs to be split), correctly.
- Jev's `fields_exact` miss is also on `ij-023`: `more_than_8` is fixed to compose into 9 boxes, so the problem message text says "9盒" (9 boxes) instead of "10盒" (10 boxes). The written result is correct, but the message text is imprecise (a known limitation).
- Jev's confidence distribution: 46 items ≥0.8, 2 items 0.5–0.8 (`ij-029`), 2 items <0.5 (`ij-036`, `ij-037`, both `no_order`, correct answer but low confidence → production would fall back to GPT). `unusable_rate` = 4%.
- No difference between the zh / en question language; the default stays zh.

**Interpretation and Limitations**
1. Both sides score close to perfect on this dataset (a ceiling effect); 50 items can't distinguish a 98% from a 100% gap (see §6.5). The conclusion is "Jev is at least no worse than GPT at item judgment, and about 27× faster," not "Jev is more accurate."
2. The data is synthetic and cleaner than real LINE conversations. The next step should be accumulating `item_judge_agreement` on real traffic with `ITEM_JUDGE_BACKEND=shadow`, or building `item-judge-real-v1` from masked real logs.
3. The dataset labels have only gone through one round of writing plus one round of item-by-item review; independent double-labeling by two people hasn't been done yet.
