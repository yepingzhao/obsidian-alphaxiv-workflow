---
name: build-note
description: Use when confirmed arXiv paper metadata is ready and need to construct a structured Obsidian markdown note with title validation and formatting from AlphaXiv data.
---

# Build Note (Gate 2)

Fetch full paper data from AlphaXiv and construct a structured Obsidian markdown note.

All commands run from the `scripts/` directory: `cd scripts`

## Process

### Step 1: Fetch Data

```bash
python -c "

from alphaxiv_client import get_paper_metadata, get_overview, fetch_publication_info, fetch_publication_rank
meta = get_paper_metadata('ARXIV_ID')
pub_info = fetch_publication_info('ARXIV_ID', abstract=meta.abstract)
pub_rank = fetch_publication_rank(pub_info.get('published_venue', ''))
en = get_overview(meta.version_id, 'en')
zh = get_overview(meta.version_id, 'zh')
from note_builder import build_note
content, warnings = build_note(meta, zh, en, pub_info=pub_info, pub_rank=pub_rank)
print(f'Warnings: {warnings}')
"
```

Publication info fetched via multi-source fallback:
1. arXiv API `<journal_ref>` (most reliable)
2. arXiv API `<comment>` (e.g. "Accepted at ICML 2023 (Oral)")
3. Abstract text parsing (e.g. "Published as a conference paper at ICLR 2024")
4. Graceful degradation — missing values left empty, note creation never blocked

### Step 1.5: Handle Missing Overview

If warnings contain `blog_pending:` → overview not yet available on AlphaXiv.

The note saves with `blog_status: pending`. Run `backfill-overviews` later:

```bash
python backfill_overviews.py --workers 3
```

This fetches overviews that already exist on AlphaXiv via public API (no key needed).
For papers needing new generation, use Playwright browser automation (see `skills/backfill-overviews/SKILL.md`).

### Step 2: Title Validation

Use `note_builder.check_title_issues(title, vault_path)` for 4-dimensional compliance:

| Dimension | Rule | Severity |
|-----------|------|----------|
| Filesystem | No `\ / : * ? " < > \|` | BLOCK |
| Collision | File must not already exist | BLOCK |
| Consistency | Remove `[arxiv_id]` prefix, `... - arXiv` suffix | warn |
| Truncation | Detect `...` truncated titles | warn |

BLOCK issues -> report and stop. Warn/info only -> proceed with cleaned title.

### Step 3: Build Note

`build_note(metadata, overview_zh, overview_en, pub_info=None, pub_rank=None)` returns `(content, warnings)`.

**Publication frontmatter fields** (from arXiv API multi-source fallback):
- `published_venue` — formal publication venue (e.g. "NeurIPS 2020"), omitted when unknown
- `presentation_type` — "Oral" or "Spotlight", omitted for regular papers
- `published_date` — formal publication date (YYYY-MM-DD), from arXiv first-published date

**Ranking frontmatter fields** (from EasyScholar, omitted when venue unknown):
- `ccf` — CCF 推荐等级 (A/B/C), e.g. "A"
- `sci_jcr` — SCI JCR 分区 (Q1-Q4), e.g. "Q1"
- `sci_cas` — 中科院升级版分区, e.g. "计算机科学1区"
- `sci_cas_top` — 中科院升级版Top期刊, boolean
- `fms` — FMS 等级
- `utd24` — UTD24 期刊, boolean
- `ft50` — FT50 期刊, boolean
- `swufe` — 西南财经大学等级

**EasyScholar configuration:** Store `easyscholar_secret_key` in `~/.alphaxiv-to-obsidian.json`.
Gracefully degrades when config missing or API unreachable — all ranking fields left empty.

**Degradation:**

| Condition | Action |
|-----------|--------|
| CN overview empty | Fallback to EN |
| Both empty | Placeholder, mark incomplete |
| Citation null fields | Skip single citation |
| BibTeX no authors | Fallback metadata authors |
| All authors fail | Empty list, report warning |
| EasyScholar unreachable | Leave ranking fields empty |
| No venue detected | Skip EasyScholar query entirely |

### Step 4: Save

Save to `{vault_path}/300 Resources/320 References/{sanitize_filename(title)}.md`.

## Handoff

Pass filepath to **validate-import** (REQUIRED SUB-SKILL).
