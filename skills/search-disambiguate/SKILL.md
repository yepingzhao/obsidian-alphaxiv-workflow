---
name: search-disambiguate
description: Use when given a paper title or keyword and need to find the exact arXiv paper on AlphaXiv before importing to Obsidian. Supports single and multi-paper selection. Includes vault duplicate detection and paper quality assessment.
---

# Search & Disambiguate (Gate 1)

Search AlphaXiv for papers matching a query, display with publication info (venue, CCF, dates, first author), and present candidates for user confirmation.

All commands run from the `scripts/` directory: `cd scripts`

## Process

### Step 1: Search & Display

Run the Gate 1 search script with a data file for handoff:

```bash
python gate1_search.py "<query>" "<VAULT_PATH>" --data-file /tmp/alphaxiv_gate1_data.json
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

## Rules

- **Always show candidates for confirmation**, even with only 1 result
- **Table includes**: rating, status, arXiv ID, title, first author, venue, CCF, conference date, arXiv date
- **0 results**: suggest shorter query or direct arXiv ID
- **Multi-select is default behavior**
- **Already-saved papers require explicit confirmation** before overwrite
- **Quality ratings are advisory** — user always decides what to import

## Handoff

Write selected papers to `/tmp/alphaxiv_selections.json` and pass to **build-note** (REQUIRED SUB-SKILL):

```json
[{"arxiv_id": "2301.12345", "title": "Paper Title"}, ...]
```

Process each sequentially for multi-paper selection. Skip vault-duplicates unless user explicitly chose overwrite.
