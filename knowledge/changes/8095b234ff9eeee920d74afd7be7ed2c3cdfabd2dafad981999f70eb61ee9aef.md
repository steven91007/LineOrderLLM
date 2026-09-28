---
kind: "change"
sha256: "8095b234ff9eeee920d74afd7be7ed2c3cdfabd2dafad981999f70eb61ee9aef"
git_sha: "87410af5a9ea9858ba4c74f9b6bc8e4242d43447"
commit_note_sha256: "789a33c3369f7c1be02cd5999d92d69f557db79f638fa55cc9e678e965dc2664"
path: ".env.example"
old_path: null
status: "M"
insertions: 8
deletions: 0
binary: false
truncated: false
truncation_reason: null
change_kind: "config"
notable_symbols:
  - "DSPY_API_KEY"
  - "DSPY_MODEL"
  - "DSPY_MAX_RETRIES"
  - "ORDER_CLIENT_TYPE"
model: "claude-code/claude-fable-5-1"
hash_recipe: "gitkb-canonical-v1;diff=-c core.quotePath=false -c diff.renames=true diff-tree -r --no-commit-id --no-color --no-ext-diff --no-textconv --full-index --find-renames=50% -U3 --src-prefix=a/ --dst-prefix=b/;per_file_cap=65536;total_cap=400000;exclude=knowledge/**"
created_at: "2026-09-28T09:56:53+00:00"
---

# .env.example @ 87410af

Part of commit [87410af feat: 新增 DSPy 模組支援與強制 JSON 輸出](../commits/789a33c3369f7c1be02cd5999d92d69f557db79f638fa55cc9e678e965dc2664.md) (M, +8/-0, kind: config)

## Summary
Adds DSPY_API_KEY, DSPY_MODEL, DSPY_MAX_RETRIES and ORDER_CLIENT_TYPE (set to dspy) entries.

## Notable symbols
- `DSPY_API_KEY`
- `DSPY_MODEL`
- `DSPY_MAX_RETRIES`
- `ORDER_CLIENT_TYPE`
