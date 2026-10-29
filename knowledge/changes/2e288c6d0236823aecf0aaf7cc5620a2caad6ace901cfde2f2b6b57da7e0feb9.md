---
kind: "change"
sha256: "2e288c6d0236823aecf0aaf7cc5620a2caad6ace901cfde2f2b6b57da7e0feb9"
git_sha: "dabdedb44a647747432d53de25a49b36ce836eec"
commit_note_sha256: "03fae25b14df09b2ac24c769efba0ba8d253906adec898b0f23d10dd0abe9a91"
path: "src/utils/dspy_modules/single_parser.py"
old_path: null
status: "D"
insertions: 0
deletions: 133
binary: false
truncated: false
truncation_reason: null
change_kind: "chore"
notable_symbols:
  - "SingleOrderParser"
  - "_create_parsing_prompt"
  - "_clean_order_data"
model: "claude-code/claude-opus-5-5"
hash_recipe: "gitkb-canonical-v1;diff=-c core.quotePath=false -c diff.renames=true diff-tree -r --no-commit-id --no-color --no-ext-diff --no-textconv --full-index --find-renames=50% -U3 --src-prefix=a/ --dst-prefix=b/;per_file_cap=65536;total_cap=400000;exclude=knowledge/**"
created_at: "2026-10-29T13:37:13+00:00"
---

# src/utils/dspy_modules/single_parser.py @ dabdedb

Part of commit [dabdedb Remove unused one-off scripts, the learning system and old DSPy modules](../commits/03fae25b14df09b2ac24c769efba0ba8d253906adec898b0f23d10dd0abe9a91.md) (D, +0/-133, kind: chore)

## Summary
Deleted: SingleOrderParser DSPy module built on SingleOrderSignature with prompt construction and field cleaning helpers.

## Notable symbols
- `SingleOrderParser`
- `_create_parsing_prompt`
- `_clean_order_data`
