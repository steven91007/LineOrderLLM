# Claude Development Notes

## Project Decisions and Technical Direction

### Language
- **English only** for commit messages, docs, code comments, docstrings, log messages and LLM prompt instructions.
- Keep Chinese only where it is functional: customer/staff-facing text (LINE replies, Discord messages, LIFF UI),
  Google Form/Sheet option strings and headers, item names, address data, matching keywords/regexes,
  test fixtures, and the Chinese data inside few-shot examples.

### AI/LLM Implementation Standards
- **Use the DSPy framework for everything**: all AI/LLM features are implemented with DSPy
- **Langfuse tracing**: LLM call tracing goes through `src/utils/langfuse_tracing.py` (captured automatically by the OpenInference DSPy instrumentor); DSPy modules must not add their own tracing code
- **Do not reintroduce MLflow**: fully removed on 2026-08-14 and replaced by Langfuse
- **Modular design**: every AI feature gets its own DSPy module

### Taiwan Address Normalization Design

#### Problem
- Address formats vary wildly; pure rule matching has limits
- An LLM is needed to understand complex address descriptions
- Combine the rule base with AI judgment for better accuracy

#### Approach
1. **DSPy address normalization module**
   - `AddressNormalizerSignature` defines the inputs and outputs
   - `AddressNormalizer` DSPy module
   - Existing address rules are used as few-shot examples

2. **Hybrid pipeline**
   ```
   Raw address → rule pre-processing → DSPy AI normalization → rule post-processing → normalized address
   ```

3. **Langfuse tracing**
   - Track normalization success rate
   - Record how well different address types are handled
   - Monitor the accuracy of the AI module

### Implementation Notes
- DSPy modules live in `src/utils/dspy_modules/`
- Every module has a corresponding signature
- Tracing is enabled once at the entry point via `langfuse_tracing.setup()`; modules do not set it up again
- Provide a fallback (use the rule base when the AI fails)

## Development Log

### 2025-08-01 Address normalization
- ✅ Basic rule base (county/city upgrades, district mapping)
- ✅ Address completion
- ✅ DSPy LLM assistance for complex addresses
- ✅ Tracing integration (originally MLflow; Langfuse since 2026-08-14)
- ✅ Hybrid pipeline (rules + AI + post-processing)

#### DSPy address normalization module
- `AddressNormalizerSignature`: input/output format for address normalization
- `AddressNormalizer`: DSPy module with few-shot examples
- Automatically detects complex addresses and chooses AI or rule processing
- Fallback keeps it stable
- **Preserves address notes**: parenthesized content such as `(XXX工地)` (construction site) or `(XXX公司)` (company)

#### DSPy chat log parsing module
- `ChatLogOrderSignature`: extracts every confirmed order from a LINE chat log
- `ChatLogParser`: DSPy module with two-pass parsing (extract first, then re-check for missed orders)
- Items must match the form dropdown option strings in `src/utils/form_options.py`; the model may not invent its own
- The earlier `ItemParser` / `MultiParser` / `SingleParser` / `OrderClassifier` were removed on
  2026-08-21 and replaced by `ChatLogParser`

## Agent skills

### Issue tracker

Issues live as GitHub issues in `steven91007/LineOrderLLM`, managed via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage labels, used as-is (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `CONTEXT.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.

### Git history (gitkb)

`knowledge/` holds one sha256-named note per commit and per file change, written by Claude Code via `/gitkb` and indexed by `uv run python -m gitkb`. Before changing code, check why it is the way it is with `gitkb history <path>` / `gitkb search <query>`; after new commits, run `/gitkb`. See `docs/agents/gitkb.md`.
