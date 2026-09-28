---
kind: "change"
sha256: "61e0aed66a6d8efd7a28b4cf7dd3e2af8f8dfbb1405ad1b31bc66be8a331a35e"
git_sha: "84bd69a9b089ed44de31af63b16b5db6f658e3e0"
commit_note_sha256: "93e25065e3691494b9fd8e6a977e5f152705633ec6620baa937bd83ad30656c2"
path: "config.py"
old_path: null
status: "M"
insertions: 2
deletions: 2
binary: false
truncated: false
truncation_reason: null
change_kind: "config"
notable_symbols:
  - "GOOGLE_SHEET_ID"
  - "GOOGLE_CREDENTIALS_PATH"
model: "claude-code/claude-fable-5-1"
hash_recipe: "gitkb-canonical-v1;diff=-c core.quotePath=false -c diff.renames=true diff-tree -r --no-commit-id --no-color --no-ext-diff --no-textconv --full-index --find-renames=50% -U3 --src-prefix=a/ --dst-prefix=b/;per_file_cap=65536;total_cap=400000;exclude=knowledge/**"
created_at: "2026-09-28T10:05:40+00:00"
---

# config.py @ 84bd69a

Part of commit [84bd69a Merge feature/liff-integration-v2 into master](../commits/93e25065e3691494b9fd8e6a977e5f152705633ec6620baa937bd83ad30656c2.md) (M, +2/-2, kind: config)

## Summary
Google Sheets settings now read the GOOGLE_SHEETS_ID and GOOGLE_SHEETS_CREDENTIALS_PATH environment variables instead of GOOGLE_SHEET_ID / GOOGLE_CREDENTIALS_PATH.

## Notable symbols
- `GOOGLE_SHEET_ID`
- `GOOGLE_CREDENTIALS_PATH`
