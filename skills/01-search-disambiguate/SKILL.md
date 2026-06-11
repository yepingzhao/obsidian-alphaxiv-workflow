---
name: 01-search-disambiguate
description: Use when given a paper title, keyword, or `hot` directive and need to find arXiv papers on AlphaXiv before importing to Obsidian. Supports search and hot-papers modes, single and multi-paper selection. Includes vault duplicate detection and paper quality assessment.
---

# Search & Disambiguate (Gate 1)

Search AlphaXiv for papers matching a query, display with publication info (venue, CCF, dates, first author), and present candidates for user confirmation.

All commands run from the project root. Ensure `pip install -e .` has been run first.

## Process

### Step 1: Search & Display

The search supports **boolean operators** (UPPERCASE): `AND`, `OR`, `NOT`, `-word` exclusion, and `(...)` grouping.
Simple queries (no operators) pass directly to AlphaXiv `fast_search`. Complex queries are parsed by `query_parser.py` (recursive descent) with post-filtering.

| Operator | Example | Behavior |
|----------|---------|----------|
| `AND` | `diffusion AND image` | Both terms must match (default) |
| `OR` | `diffusion OR gan` | Either term matches — multi-search merged |
| `NOT` | `vision NOT detection` | Exclude papers containing the term |
| `-word` | `transformer -attention` | Shorthand for NOT |
| `(...)` | `(diffusion OR gan) AND image` | Grouping for precedence |

UPPERCASE = operator; lowercase = search keyword. Quoted phrases work: `"image generation" AND diffusion`.

Run the Gate 1 search script with a data file for handoff:

```bash
python -m alphaxiv_workflow.search "<query>" "<VAULT_PATH>" --data-file /tmp/alphaxiv_gate1_data.json
```

The script outputs:
- Progress phases (`🔍 搜索...` → `📄 批量获取 arXiv...` → `🔄 论文处理...`)
- A PrettyTable with columns: `# | 评级 | 状态 | arXiv ID | 标题 | 一作 | 发表venue | CCF | 会议日期 | arXiv日期`
- Rating legend and status key

The data file at `/tmp/alphaxiv_gate1_data.json` contains structured paper data for selection handling.

**On Windows**, use `%TEMP%\alphaxiv_gate1_data.json` instead.

### Step 2: Present Candidates

Read the script's table output and present it to the user. Add selection instructions:

```
Enter selection (1, 1-3, 1,3,5, or all):
```

### Step 3: Parse Selection

Read selections from `/tmp/alphaxiv_gate1_data.json` to map user input to paper data:

- `1` -> single paper #1
- `1,3,5` -> papers #1, #3, #5
- `1-3` -> papers #1 through #3
- `all` -> all candidates

### Step 3.5: Handle Already-Saved Papers

If user selects a paper marked `已保存 ✓`:
- Show: ⚠️ Paper already exists at `{vault_path}`
- Ask: "Skip (s), Overwrite (o), or Open existing note (open)?"
- Default: skip (exclude from import batch)

### Hot Papers Mode

When user says `import hot` or `hot`:

```bash
python -m alphaxiv_workflow.fetch_hot "VAULT_PATH" --data-file /tmp/alphaxiv_hot_papers.json
```

The script scrapes `https://alphaxiv.org/` for trending paper IDs, batch-fetches arXiv API for metadata, and outputs a PrettyTable with the same columns as the search table.

Options:
- `--limit N` — show only top N hot papers
- `--json` — machine-readable output

## Rules

- **Always show candidates for confirmation**, even with only 1 result
- **Table includes**: rating, status, arXiv ID, title, first author, venue, CCF, conference date, arXiv date
- **0 results**: suggest shorter query or direct arXiv ID
- **Multi-select is default behavior**
- **Already-saved papers require explicit confirmation** before overwrite
- **Quality ratings are advisory** — user always decides what to import

## Handoff

Write selected papers to `/tmp/alphaxiv_selections.json` and pass to **02-build-note** (REQUIRED SUB-SKILL):

```json
[{"arxiv_id": "2301.12345", "title": "Paper Title"}, ...]
```

Process each sequentially for multi-paper selection. Skip vault-duplicates unless user explicitly chose overwrite.
