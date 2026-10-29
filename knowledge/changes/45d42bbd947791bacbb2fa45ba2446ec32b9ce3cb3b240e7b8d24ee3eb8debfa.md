---
kind: "change"
sha256: "45d42bbd947791bacbb2fa45ba2446ec32b9ce3cb3b240e7b8d24ee3eb8debfa"
git_sha: "a9c75c1d76b4426ae94906070557f6e8803fedba"
commit_note_sha256: "2ddabbcf5bfc3be464b1e023c90dec5ac3683963a64ad80dc2ac85f9dbebac99"
path: "test_liff_url_fix.py"
old_path: null
status: "D"
insertions: 0
deletions: 92
binary: false
truncated: false
truncation_reason: null
change_kind: "test"
notable_symbols:
  - "test_liff_url_generation"
model: "claude-code/claude-opus-5-5"
hash_recipe: "gitkb-canonical-v1;diff=-c core.quotePath=false -c diff.renames=true diff-tree -r --no-commit-id --no-color --no-ext-diff --no-textconv --full-index --find-renames=50% -U3 --src-prefix=a/ --dst-prefix=b/;per_file_cap=65536;total_cap=400000;exclude=knowledge/**"
created_at: "2026-10-29T13:37:07+00:00"
---

# test_liff_url_fix.py @ a9c75c1

Part of commit [a9c75c1 Add order summary and learning system, and stop tracking .env](../commits/2ddabbcf5bfc3be464b1e023c90dec5ac3683963a64ad80dc2ac85f9dbebac99.md) (D, +0/-92, kind: test)

## Summary
Deleted root-level ad-hoc script checking LIFF URL generation via HTTP requests.

## Notable symbols
- `test_liff_url_generation`
