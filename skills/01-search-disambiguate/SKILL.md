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

### Step 1: Search & Display

Boolean operators supported (UPPERCASE): `AND`, `OR`, `NOT`, `-word` exclusion, `(...)` grouping.
Simple queries pass directly to AlphaXiv. Complex queries parsed by `query_parser.py`.

```bash
python -m alphaxiv_workflow.search "<query>" "<VAULT_PATH>" --data-file /tmp/alphaxiv_gate1_data.json
```

On Windows: `%TEMP%\alphaxiv_gate1_data.json`. The script outputs a PrettyTable with ratings, status, arXiv ID, title, first author, venue, CCF, and dates.

### Step 2: Hot Papers Mode

```bash
python -m alphaxiv_workflow.fetch_hot "<VAULT_PATH>" --data-file /tmp/alphaxiv_hot_papers.json
```

Options: `--limit N`, `--skip-existing`.

### Step 3: Recommend Papers Mode

```bash
python -m alphaxiv_workflow.fetch_recommend "<VAULT_PATH>" --data-file /tmp/alphaxiv_recommend_papers.json
```

### Step 4: Present Candidates

Read the table output and present to user with selection prompt:
```
Enter selection (1, 1-3, 1,3,5, or all):
```

### Step 5: Parse Selection

Read from the data file to map user input to paper data:
- `1` → single paper
- `1,3,5` → specific papers
- `1-3` → range
- `all` → all candidates

### Step 6: Handle Already-Saved Papers

If user selects a paper marked `已保存 ✓`:
- Show: ⚠️ Paper already exists at `{vault_path}`
- Ask: "Skip (s), Overwrite (o), or Open existing note (open)?"
- Default: skip

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using lowercase `and`/`or` | Operators must be UPPERCASE: `AND`, `OR`, `NOT` |
| Skipping confirmation for single result | Always show candidates, even with 1 result |
| Overwriting without asking | Already-saved papers require explicit confirmation |

## Rules

- Always show candidates for confirmation, even with only 1 result
- Table includes: rating, status, arXiv ID, title, first author, venue, CCF, conference date, arXiv date
- 0 results: suggest shorter query or direct arXiv ID
- Multi-select is default behavior
- Quality ratings are advisory — user always decides

## Handoff

Write selected papers to `/tmp/alphaxiv_selections.json` and pass to **02-build-note** (REQUIRED SUB-SKILL):

```json
[{"arxiv_id": "2301.12345", "title": "Paper Title"}, ...]
```

## Fallback

If CLI fails, use direct Python API:
```python
from alphaxiv_workflow.api import search_with_operators, enrich_search_results
results = search_with_operators("query")
papers = enrich_search_results(results, "VAULT_PATH")
```
