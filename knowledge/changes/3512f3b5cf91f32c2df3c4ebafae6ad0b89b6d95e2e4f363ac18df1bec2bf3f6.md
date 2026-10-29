---
kind: "change"
sha256: "3512f3b5cf91f32c2df3c4ebafae6ad0b89b6d95e2e4f363ac18df1bec2bf3f6"
git_sha: "f7d98b745876f153fb5b16cd634ecda9d3fb035f"
commit_note_sha256: "96bd462d1e4531533e6ba8009b63d60332c55134346f0c85c33bd8ce8f1a93c2"
path: "src/utils/order_schemas.py"
old_path: null
status: "A"
insertions: 156
deletions: 0
binary: false
truncated: false
truncation_reason: null
change_kind: "feature"
notable_symbols:
  - "SINGLE_ORDER_SCHEMA"
  - "MULTI_ORDER_SCHEMA"
  - "ERROR_SCHEMA"
  - "ORDER_RESPONSE_SCHEMA"
model: "claude-code/claude-opus-5-5"
hash_recipe: "gitkb-canonical-v1;diff=-c core.quotePath=false -c diff.renames=true diff-tree -r --no-commit-id --no-color --no-ext-diff --no-textconv --full-index --find-renames=50% -U3 --src-prefix=a/ --dst-prefix=b/;per_file_cap=65536;total_cap=400000;exclude=knowledge/**"
created_at: "2026-10-29T13:37:03+00:00"
---

# src/utils/order_schemas.py @ f7d98b7

Part of commit [f7d98b7 Merge pull request #6 from steven91007/feature/google-sheets-api-fixes](../commits/96bd462d1e4531533e6ba8009b63d60332c55134346f0c85c33bd8ce8f1a93c2.md) (A, +156/-0, kind: feature)

## Summary
New JSON Schema definitions: SINGLE_ORDER_SCHEMA, MULTI_ORDER_SCHEMA (2-5 orders with order_index), ERROR_SCHEMA and a oneOf ORDER_RESPONSE_SCHEMA.

## Notable symbols
- `SINGLE_ORDER_SCHEMA`
- `MULTI_ORDER_SCHEMA`
- `ERROR_SCHEMA`
- `ORDER_RESPONSE_SCHEMA`
