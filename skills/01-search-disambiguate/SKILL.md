---
name: 01-search-disambiguate
description: Use when given a paper title, keyword, or arxiv_id and need to find matching papers on AlphaXiv before importing to Obsidian. Also use when user says "import hot" or "import recommend" to scrape AlphaXiv trending/recommended papers.
---

# Search & Disambiguate (Gate 1)

Search AlphaXiv for papers, display with publication metadata, and present candidates for user confirmation.

## Decision Flowchart

```
User input ──┬── "import hot" ────────────> fetch_hot pipeline
             ├── "import recommend" ───────> fetch_recommend pipeline
             └── "import <query>" ─────────> search pipeline
```

## Process

### Step 1: Session Init — Create Session Directory

**CRITICAL: Never reuse the same data file path across rounds.** Each import session must use a unique working directory to avoid result mixing:

- Linux/Mac: `/tmp/alphaxiv-session-<timestamp>/`
- Windows: `%TEMP%\alphaxiv-session-<timestamp>/`

Within each session directory:
- `round-1-data.json` → `round-N-data.json` — per-round data files
- `exclude.json` — accumulated `{arxiv_id: true}` map for cross-round dedup
- `selections.json` — final selected papers for Gate 2 handoff

### Step 2: Per-Round Search & Display

**Session state rules:**

1. **Each round's data file is SEPARATE** — never overwrite previous rounds
2. **`exclude.json` accumulates across rounds** — after each round, add all displayed arXiv IDs to the exclude map
3. **Pass `--exclude exclude.json` on every round after the first** — this tells the CLI to filter out papers that appeared in earlier rounds
4. **Display only current round's results** — never show a merged table mixing old and new results

```bash
# Round 1
mkdir -p /tmp/alphaxiv-session && echo '{}' > /tmp/alphaxiv-session/exclude.json
python -m alphaxiv_workflow.search "<query>" "<VAULT_PATH>" --data-file /tmp/alphaxiv-session/round-1-data.json

# Round 2 (补充搜索) — exclude papers from round 1
python -m alphaxiv_workflow.search "<refined query>" "<VAULT_PATH>" \
    --data-file /tmp/alphaxiv-session/round-2-data.json \
    --exclude /tmp/alphaxiv-session/exclude.json
```

On Windows: `%TEMP%\alphaxiv-session\round-N-data.json`.

### Step 3: Update Exclude Map After Each Round

```bash
python -c "
import json
with open('/tmp/alphaxiv-session/exclude.json') as f:
    exclude = json.load(f)
with open('/tmp/alphaxiv-session/round-N-data.json') as f:
    papers = json.load(f)
for p in papers:
    exclude[p['arxiv_id']] = True
with open('/tmp/alphaxiv-session/exclude.json', 'w') as f:
    json.dump(exclude, f)
"
```

### Step 4: Hot Papers Mode

```bash
python -m alphaxiv_workflow.fetch_hot "<VAULT_PATH>" --data-file /tmp/alphaxiv-session/hot-data.json
```

### Step 5: Recommend Papers Mode

```bash
python -m alphaxiv_workflow.fetch_recommend "<VAULT_PATH>" --data-file /tmp/alphaxiv-session/recommend-data.json
```

### Step 6: Present Candidates Per Round

Read ONLY the current round's data file. Present with selection prompt:
```
Round N results — Enter selection (1, 1-3, 1,3,5, or all):
```

**When displaying results across rounds:**
- Show each round's candidates separately under `### Round N` headings — NEVER merge
- If user says "补充搜索", start a NEW round with `--exclude`

### Step 7: Parse Selection

- `1` → single, `1,3,5` → specific, `1-3` → range, `all` → all
- Accumulate selections into `selections.json`: `[{"arxiv_id": "...", "title": "...", "round": N}, ...]`

### Step 8: Handle Already-Saved Papers

If marked `已保存 ✓`: ask skip / overwrite / open. Default: skip.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using lowercase `and`/`or` | Operators must be UPPERCASE |
| Skipping confirmation | Always show candidates, even 1 result |
| Overwriting without asking | Already-saved papers require confirmation |
| **Reusing same data file across rounds** | **Each round = new round-N-data.json** |
| **Merging old + new results in one table** | **Display per-round under separate headers** |
| **Forgetting `--exclude` on round 2+** | **Always pass `--exclude exclude.json`** |
| **Overwriting exclude.json instead of merge** | **JSON merge, not overwrite** |

## Rules

- Always show candidates for confirmation
- 0 results: suggest shorter query or direct arXiv ID
- Multi-select is default
- **Never reuse data file paths across rounds**
- **Never merge results from different queries into a single table**
- **Accumulate exclude.json across session — never reset mid-session**

## Handoff

Selected papers to `selections.json`: `[{"arxiv_id": "...", "title": "...", "round": N}, ...]`
Pass to **02-build-note**.

## Session Cleanup

After Gate 3: `rm -rf /tmp/alphaxiv-session`

## Fallback

If CLI fails, use direct Python API:
```python
from alphaxiv_workflow.api import search_with_operators, enrich_search_results
results = search_with_operators("query")
papers = enrich_search_results(results, "VAULT_PATH")
```
