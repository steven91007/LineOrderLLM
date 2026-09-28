---
kind: "change"
sha256: "7b1ff2488dfd5bf43e1796edffbd8d5cf0eefccf841e20ce03ce3ee141df51b8"
git_sha: "9ff66ed33c69bf3abeb0966eee52c7a690598ab7"
commit_note_sha256: "d3f39cc71868f6c2d020aa4a66c29582ab8b62bd65e4d5d003a6ba84496884b7"
path: "manual_migrate_orders.py"
old_path: null
status: "A"
insertions: 196
deletions: 0
binary: false
truncated: false
truncation_reason: null
change_kind: "chore"
notable_symbols:
  - "parse_items_from_text"
  - "convert_order_to_new_format"
  - "batch_convert_example"
model: "claude-code/claude-fable-5-1"
hash_recipe: "gitkb-canonical-v1;diff=-c core.quotePath=false -c diff.renames=true diff-tree -r --no-commit-id --no-color --no-ext-diff --no-textconv --full-index --find-renames=50% -U3 --src-prefix=a/ --dst-prefix=b/;per_file_cap=65536;total_cap=400000;exclude=knowledge/**"
created_at: "2026-09-28T09:56:54+00:00"
---

# manual_migrate_orders.py @ 9ff66ed

Part of commit [9ff66ed 新增訂單匯總與學習系統，並停止追蹤 .env](../commits/d3f39cc71868f6c2d020aa4a66c29582ab8b62bd65e4d5d003a6ba84496884b7.md) (A, +196/-0, kind: chore)

## Summary
New CLI script that takes old-format key/value order text from stdin, parses items, computes totals via PriceCalculator and prints the new-format row (tab-separated); includes an --example batch mode with sample orders.

## Notable symbols
- `parse_items_from_text`
- `convert_order_to_new_format`
- `batch_convert_example`
