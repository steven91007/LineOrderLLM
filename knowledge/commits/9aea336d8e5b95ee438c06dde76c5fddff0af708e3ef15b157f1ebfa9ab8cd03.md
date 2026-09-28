---
kind: "commit"
sha256: "9aea336d8e5b95ee438c06dde76c5fddff0af708e3ef15b157f1ebfa9ab8cd03"
git_sha: "2c92f904a6ec6cdae8bdf25c20294fc2ee674514"
tree_sha: "0059de27e30b2d792dc44ab055090589e1f7d973"
parents:
  - {"git_sha": "bb0d143354fa8d0256dc0b933dc68f2eea004a74", "note_sha256": "5b408acfc63db935496414141c48088d19f034393fbe785a0c4b9383f196e854"}
  - {"git_sha": "8d3298989c6730c48118fbc7f4c42efde4903d71", "note_sha256": "de081838764799bada3c297175dd126de09dbb379236d04b4033434dc3c8acf8"}
author: "DESKTOP-HTC5RQI\\chi <steven91007@gmail.com>"
authored_at: "2026-09-04T08:02:24+08:00"
committer: "DESKTOP-HTC5RQI\\chi <steven91007@gmail.com>"
committed_at: "2026-09-04T08:02:24+08:00"
subject: "Merge branch 'feature/price-list-add-shuangshuangduidui' into master"
model: "claude-code/claude-fable-5-1"
hash_recipe: "gitkb-canonical-v1;diff=-c core.quotePath=false -c diff.renames=true diff-tree -r --no-commit-id --no-color --no-ext-diff --no-textconv --full-index --find-renames=50% -U3 --src-prefix=a/ --dst-prefix=b/;per_file_cap=65536;total_cap=400000;exclude=knowledge/**"
patch_bytes: 2650
truncated: false
tags:
  - "merge"
  - "pricing"
  - "product"
files:
  - {"path": "src/utils/price_calculator.py", "old_path": null, "status": "M", "insertions": 18, "deletions": 3, "binary": false, "truncated": false, "note_sha256": "761ce8769b7388ceff415d79ad2cc025d80dc9accab172b8ee7ab66c3fb8fabe"}
created_at: "2026-09-28T09:56:55+00:00"
gitkb_version: "0.1.0"
---

# 2c92f90 Merge branch 'feature/price-list-add-shuangshuangduidui' into master

## Summary
Merge commit bringing branch feature/price-list-add-shuangshuangduidui (single commit 8d32989) into master. The diff against the first parent repeats that commit: PriceCalculator gains the 雙雙對對 flat-price product (3400 per set), a name-parsing short-circuit for it, and a dedicated pricing branch.

## Why
Integrates the new price-list item into master; no extra changes beyond the merged branch.

## Risks
Same as 8d32989: substring matching on the product name takes precedence over spec parsing, and the rest of the order pipeline did not yet know about the item.

## Files
- `src/utils/price_calculator.py` (M, +18/-3): Via merge: adds the 雙雙對對 price-table entry, the early return in product-name parsing, and the fixed-unit-price calculation branch. [note](../changes/761ce8769b7388ceff415d79ad2cc025d80dc9accab172b8ee7ab66c3fb8fabe.md)

## Parents
- [bb0d143 修正 deploy workflow 找不到 uv 指令](../commits/5b408acfc63db935496414141c48088d19f034393fbe785a0c4b9383f196e854.md)
- [8d32989 新增「雙雙對對」品項至價目表，固定單價 $3,400](../commits/de081838764799bada3c297175dd126de09dbb379236d04b4033434dc3c8acf8.md)

## Commit message
```text
Merge branch 'feature/price-list-add-shuangshuangduidui' into master

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019CningJZ8Z1RbrBHypCVNF
```
