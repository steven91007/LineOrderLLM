# gitkb: git history knowledge base

`knowledge/` holds a knowledge note for every commit: one `knowledge/commits/<sha256>.md` per commit, and one `knowledge/changes/<sha256>.md` per file change in that commit. Each file name is the sha256 of the normalized text that was summarized (commit header + diff), so a note proves by itself which change it describes. `knowledge/index.db` is a SQLite index (mappings between commits, files and notes, plus FTS5 full-text search). It is **not version-controlled** and can be rebuilt from the md files at any time.

The code lives in `gitkb/` and is the same as `gitkb/` in [Jobseekers](https://github.com/steven91007/Jobseekers-); the `gitkb_*` tools in [jobseekers-mcp](https://github.com/steven91007/jobseekers-mcp) can query this repo directly by pointing `GITKB_REPO` at it.

## Look it up before changing code

Before changing a piece of code, check why it looks the way it does:

```bash
uv run python -m gitkb history src/utils/sheet_date_organizer.py   # every change to a file
uv run python -m gitkb search "雙雙對對"                            # full-text search over summaries (FTS5 syntax)
uv run python -m gitkb show 1e454fe                                 # view a note by git sha (abbreviation OK) or note sha256
uv run python -m gitkb log                                          # indexed commits
```

On a fresh clone with no `index.db`, run `uv run python -m gitkb rebuild-index` first to rebuild it from the md files.

## Update the knowledge base after new commits

Summaries are written by Claude Code in conversation; no LLM API is called:

```bash
uv run python -m gitkb pending        # export not-yet-summarized commits to knowledge/pending.json
#  -> type /gitkb in Claude Code; it reads pending.json and writes knowledge/summaries.json
uv run python -m gitkb import knowledge/summaries.json   # generate the notes and build the index
```

`knowledge/pending.json` and `knowledge/summaries.json` are temporary files and are already in `.gitignore`. `build --dry-run` first writes placeholder notes (with the same file names as the real notes), which `import` later overwrites in place.

## Rules

- Do not hand-edit files under `knowledge/commits/` or `knowledge/changes/`; the file names are hashes of the input and the importer regenerates them.
- If `import` warns that the hash recipe changed (diff flags, size caps or `GITKB_EXCLUDE_GLOBS` changed), stop and ask a human; do not force the import.
- Write summaries in English, and never copy customer personal data (names, phone numbers, addresses, last five digits of a transfer) or secrets from a diff into a note.
- After changing code in `gitkb/`, run `uv run python tests/test_gitkb.py`.
