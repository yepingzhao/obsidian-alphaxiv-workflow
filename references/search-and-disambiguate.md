# Search & Disambiguate (Gate 1)

Search AlphaXiv for papers, display with publication metadata, and present candidates for user confirmation.

## Contents

- [Decision flowchart](#decision-flowchart)
- [Process](#process)
- [Common mistakes](#common-mistakes)
- [Rules](#rules)
- [Handoff and cleanup](#handoff)
- [Fallback](#fallback)

## Decision Flowchart

```
User input ──┬── "import hot" ────────────> fetch_hot pipeline
             ├── "import recommend" ───────> fetch_recommend pipeline
             └── "import <query>" ─────────> search pipeline
```

## Process

### Step 1: Session Init — Create Session Directory

**CRITICAL: Never reuse the same data file path across rounds.** Create a unique working directory and retain its exact path for the whole import session:

```powershell
# PowerShell
$sessionDir = Join-Path ([IO.Path]::GetTempPath()) ("alphaxiv-session-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $sessionDir | Out-Null
Set-Content -LiteralPath (Join-Path $sessionDir 'exclude.json') -Value '{}'
```

```bash
# Bash
SESSION_DIR="$(mktemp -d -t alphaxiv-session-XXXXXXXX)"
printf '{}' > "$SESSION_DIR/exclude.json"
```

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

```text
# Round 1
<PYTHON_CMD> -m alphaxiv_workflow.search "<query>" "<VAULT_PATH>" --data-file "<SESSION_DIR>/round-1-data.json"

# Round 2 (补充搜索) — exclude papers from round 1
<PYTHON_CMD> -m alphaxiv_workflow.search "<refined query>" "<VAULT_PATH>" \
    --data-file "<SESSION_DIR>/round-2-data.json" \
    --exclude "<SESSION_DIR>/exclude.json"
```

Replace `<SESSION_DIR>` with `$sessionDir` in PowerShell or `$SESSION_DIR` in Bash. Use native path joining when direct filesystem tools are available; do not concatenate a Windows temp path into a workspace-relative filename.

### Step 3: Update Exclude Map After Each Round

```python
import json
from pathlib import Path

session_dir = Path("<SESSION_DIR>")
exclude_path = session_dir / "exclude.json"
round_path = session_dir / "round-N-data.json"
exclude = json.loads(exclude_path.read_text(encoding="utf-8"))
papers = json.loads(round_path.read_text(encoding="utf-8"))
exclude.update({paper["arxiv_id"]: True for paper in papers})
exclude_path.write_text(json.dumps(exclude), encoding="utf-8")
```

### Step 4: Hot Papers Mode

```bash
<PYTHON_CMD> -m alphaxiv_workflow.fetch_hot "<VAULT_PATH>" --data-file "<SESSION_DIR>/hot-data.json"
```

### Step 5: Recommend Papers Mode

```bash
<PYTHON_CMD> -m alphaxiv_workflow.fetch_recommend "<VAULT_PATH>" --data-file "<SESSION_DIR>/recommend-data.json"
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
Pass the confirmed selection to [Build Note](build-note.md).

## Session Cleanup

After Gate 3, delete only the exact unique directory created in Step 1. Verify that its resolved basename starts with `alphaxiv-session-`; never delete the parent temp directory or a generic shared session path.

## Fallback

If the CLI fails after `PYTHON_CMD` itself has passed its probe, use the same interpreter for the direct Python API fallback. Do not switch interpreters or create a fallback script merely because bare `python` failed.
```python
from alphaxiv_workflow.api import search_with_operators, enrich_search_results
results = search_with_operators("query")
papers = enrich_search_results(results, "VAULT_PATH")
```
