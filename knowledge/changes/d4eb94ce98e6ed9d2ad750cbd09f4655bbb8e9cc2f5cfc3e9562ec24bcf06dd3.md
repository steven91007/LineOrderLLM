---
kind: "change"
sha256: "d4eb94ce98e6ed9d2ad750cbd09f4655bbb8e9cc2f5cfc3e9562ec24bcf06dd3"
git_sha: "9767874a29bbe1dbf446b01cf0633a4f3aef7ac8"
commit_note_sha256: "629443e6d5434408dfa428992d9d863744cc971d55dad9889930d8ad1cb000aa"
path: "src/utils/order_schemas.py"
old_path: null
status: "M"
insertions: 4
deletions: 4
binary: false
truncated: false
truncation_reason: null
change_kind: "config"
notable_symbols:
  - "SINGLE_ORDER_SCHEMA"
  - "MULTI_ORDER_SCHEMA"
  - "shipping_date"
model: "claude-code/claude-fable-5-1"
hash_recipe: "gitkb-canonical-v1;diff=-c core.quotePath=false -c diff.renames=true diff-tree -r --no-commit-id --no-color --no-ext-diff --no-textconv --full-index --find-renames=50% -U3 --src-prefix=a/ --dst-prefix=b/;per_file_cap=65536;total_cap=400000;exclude=knowledge/**"
created_at: "2026-09-28T10:05:40+00:00"
---

# src/utils/order_schemas.py @ 9767874

Part of commit [9767874 feat: 增強 LIFF 整合與 Google Sheets 自動分組功能](../commits/629443e6d5434408dfa428992d9d863744cc971d55dad9889930d8ad1cb000aa.md) (M, +4/-4, kind: config)

## Summary
Changes the shipping_date JSON-schema pattern in both order schemas from YYYY-MM-DD to MM-DD (still allowing empty/null) and updates the descriptions accordingly.

## Notable symbols
- `SINGLE_ORDER_SCHEMA`
- `MULTI_ORDER_SCHEMA`
- `shipping_date`
