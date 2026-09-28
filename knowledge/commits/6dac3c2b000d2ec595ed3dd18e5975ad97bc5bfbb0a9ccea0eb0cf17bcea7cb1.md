---
kind: "commit"
sha256: "6dac3c2b000d2ec595ed3dd18e5975ad97bc5bfbb0a9ccea0eb0cf17bcea7cb1"
git_sha: "8fb6ad52ccd54778b8986ae8f8116747c4a09dd0"
tree_sha: "36645d60ac64e25a40ab47a78a4c9360ebfb997d"
parents:
  - {"git_sha": "a7efdef66db37069e063df345a5d9e377bed2e45", "note_sha256": "562cea37a78b8ecde8b0447a4917cab5c0c7868b8dc24b5cc98b9e3f9f19913f"}
author: "steven91007 <steven91007@gmail.com>"
authored_at: "2025-08-01T15:36:13Z"
committer: "steven91007 <steven91007@gmail.com>"
committed_at: "2025-08-01T15:41:05Z"
subject: "feat: 台灣地址標準化與補全功能"
model: "claude-code/claude-fable-5-1"
hash_recipe: "gitkb-canonical-v1;diff=-c core.quotePath=false -c diff.renames=true diff-tree -r --no-commit-id --no-color --no-ext-diff --no-textconv --full-index --find-renames=50% -U3 --src-prefix=a/ --dst-prefix=b/;per_file_cap=65536;total_cap=400000;exclude=knowledge/**"
patch_bytes: 28673
truncated: false
tags:
  - "address"
  - "taiwan"
  - "normalization"
  - "dspy"
  - "openai"
  - "rules"
files:
  - {"path": "src/utils/dspy_client.py", "old_path": null, "status": "M", "insertions": 72, "deletions": 12, "binary": false, "truncated": false, "note_sha256": "728e266f67eeb18f31163b90dade90d120e6b63be12a4b44f3a7ca5f8d7a88fc"}
  - {"path": "src/utils/openai_client.py", "old_path": null, "status": "M", "insertions": 40, "deletions": 1, "binary": false, "truncated": false, "note_sha256": "ef7247b67a55eacb30a1d832e8840d059c0dc1798735805e5ba8c4999bd73897"}
  - {"path": "src/utils/taiwan_address.py", "old_path": null, "status": "A", "insertions": 369, "deletions": 0, "binary": false, "truncated": false, "note_sha256": "8b452e38ed96337facfce7c27a61cbdc28ef5cb152e3d89a01cbf273fac2384f"}
  - {"path": "test_address_normalization.py", "old_path": null, "status": "A", "insertions": 96, "deletions": 0, "binary": false, "truncated": false, "note_sha256": "2a6f34ae38b3d0ae90ba8649e908e9fa29f1d34a78f7824c44d220a41ab7b633"}
created_at: "2026-09-28T09:56:53+00:00"
gitkb_version: "0.1.0"
---

# 8fb6ad5 feat: 台灣地址標準化與補全功能

## Summary
Adds a rule-based TaiwanAddressNormalizer that unifies 台/臺 spelling, maps county names to their post-2010/2014 municipality names, rewrites old township/town suffixes to 區 for Taoyuan, Taichung, Tainan and Kaohsiung, prepends the city when only a known district is given, and can split an address into city/district/road/detail and validate completeness. Both OpenAIClient and DSPyOrderClient now normalise every shipping_address in successful results. DSPyOrderClient also switches from dspy.OpenAI to dspy.LM and replaces its multi-order regex fallback with the receiver/address-based heuristics. A manual test script exercises the normaliser.

## Why
Users type incomplete, outdated or inconsistently spelled Taiwanese addresses; normalising them before writing to the sheet improves data quality, and dspy.LM is the current API for the DSPy version now required.

## Risks
district_updates maps '桃園市' to '桃園區' to handle the pre-2014 city, but _update_district applies it to every address, so an already-correct '桃園市桃園區...' address is likely corrupted (the test case for it will probably fail). _update_city breaks after the first matching alias, and ambiguous short names ('新竹', '嘉義') always resolve to the county. openai_client.py defines _normalize_addresses_in_result twice (identical bodies; the second silently wins). Normalisation mutates the parsed result in place. The test file is a print-based script rather than a pytest test.

## Files
- `src/utils/dspy_client.py` (M, +72/-12): Imports TaiwanAddressNormalizer and normalises shipping_address in single and multiple results before returning success; _configure_dspy now uses dspy.LM; _contains_multiple_indicators rewritten to detect multiple receivers/addresses/numbering. [note](../changes/728e266f67eeb18f31163b90dade90d120e6b63be12a4b44f3a7ca5f8d7a88fc.md)
- `src/utils/openai_client.py` (M, +40/-1): Instantiates TaiwanAddressNormalizer and applies _normalize_addresses_in_result to parsed results; the method is accidentally defined twice. [note](../changes/ef7247b67a55eacb30a1d832e8840d059c0dc1798735805e5ba8c4999bd73897.md)
- `src/utils/taiwan_address.py` (A, +369/-0): New TaiwanAddressNormalizer with city alias table, district_updates for upgraded counties, district_mapping for city inference, normalize_address pipeline (_update_city, _update_district, _complete_address), extract_components and validate_address. [note](../changes/8b452e38ed96337facfce7c27a61cbdc28ef5cb152e3d89a01cbf273fac2384f.md)
- `test_address_normalization.py` (A, +96/-0): Manual script printing normalisation results for district completion, old-name updates and 台->臺 cases, plus component extraction and validation examples. [note](../changes/2a6f34ae38b3d0ae90ba8649e908e9fa29f1d34a78f7824c44d220a41ab7b633.md)

## Parents
- [a7efdef feat: DSPy 多訂單判斷邏輯優化](../commits/562cea37a78b8ecde8b0447a4917cab5c0c7868b8dc24b5cc98b9e3f9f19913f.md)

## Commit message
```text
feat: 台灣地址標準化與補全功能

新增地址處理功能：
- 地址補全：士林區 → 臺北市士林區
- 舊地名更新：桃園縣中壢市 → 桃園市中壢區
- 統一用字：台北 → 臺北
- 處理縣市升格：台中縣、台南縣、高雄縣合併
- 自動標準化所有解析出的地址

整合到訂單解析系統：
- OpenAI 客戶端自動標準化地址
- DSPy 客戶端自動標準化地址
- 包含完整測試案例

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
```
