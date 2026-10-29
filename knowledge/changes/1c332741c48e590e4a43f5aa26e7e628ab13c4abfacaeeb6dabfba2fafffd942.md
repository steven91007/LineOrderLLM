---
kind: "change"
sha256: "1c332741c48e590e4a43f5aa26e7e628ab13c4abfacaeeb6dabfba2fafffd942"
git_sha: "8aeb909af2ca30a12d7e28a2a194bfe3351d6481"
commit_note_sha256: "4454898e563372a97cbf6c719a29729775b9bfdd1c2e938ae9786335563c22e5"
path: "LIFF_SETUP.md"
old_path: null
status: "A"
insertions: 210
deletions: 0
binary: false
truncated: false
truncation_reason: null
change_kind: "docs"
notable_symbols:
  - "LIFF_ID"
  - "FLASK_SECRET_KEY"
model: "claude-code/claude-opus-5-5"
hash_recipe: "gitkb-canonical-v1;diff=-c core.quotePath=false -c diff.renames=true diff-tree -r --no-commit-id --no-color --no-ext-diff --no-textconv --full-index --find-renames=50% -U3 --src-prefix=a/ --dst-prefix=b/;per_file_cap=65536;total_cap=400000;exclude=knowledge/**"
created_at: "2026-10-29T13:37:05+00:00"
---

# LIFF_SETUP.md @ 8aeb909

Part of commit [8aeb909 Merge feature/liff-integration-v2 into master](../commits/4454898e563372a97cbf6c719a29729775b9bfdd1c2e938ae9786335563c22e5.md) (A, +210/-0, kind: docs)

## Summary
New setup guide for the LIFF order editor: creating the LIFF app, env vars (LIFF_ID, FLASK_SECRET_KEY), user flow, API endpoints, HTTPS deployment notes and troubleshooting. Still documents the old GOOGLE_SHEET_ID / GOOGLE_CREDENTIALS_PATH names.

## Notable symbols
- `LIFF_ID`
- `FLASK_SECRET_KEY`
