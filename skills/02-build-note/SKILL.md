---
name: 02-build-note
description: Use when confirmed arXiv paper metadata is ready from Gate 1 and need to fetch AlphaXiv data and construct a structured Obsidian markdown note for import.
---

# Build Note (Gate 2)

Fetch full paper data from AlphaXiv and construct a structured Obsidian markdown note.

## Process

### Step 1: Build Note

```bash
python -m alphaxiv_workflow.build "<paper title or arXiv ID>"
```

This CLI handles the full pipeline:
1. Resolves paper ID via AlphaXiv search
2. Fetches metadata + Chinese overview + English overview
3. Fetches publication info from arXiv API (multi-source fallback)
4. Fetches publication ranking from EasyScholar (if configured)
5. Builds markdown note with all frontmatter fields
6. Saves to `{vault}/300 Resources/320 References/{title}.md`

### Step 2: Handle Warnings

Common warnings from build output:

| Warning | Meaning | Action |
|---------|---------|--------|
| `blog_pending: ...` | Overview not yet available on AlphaXiv | Note saves with `blog_status: pending`. Auto-backfill (Gate 5) handles this. |
| `citation_null` | Citation field missing from API | Skip single citation, proceed |
| `empty_authors` | BibTeX missing authors | Falls back to metadata authors |

### Step 3: Title Validation

CLI handles title validation internally via `note_builder.check_title_issues()`:
- Filesystem safety: no `\ / : * ? " < > |`
- Collision check: file must not already exist
- Consistency: removes `[arxiv_id]` prefix, `... - arXiv` suffix
- Truncation: detects `...` truncated titles

BLOCK issues stop the build. WARN issues proceed with cleaned title.

## Publication Data Sources

Multi-source fallback for publication info:
1. arXiv API `<journal_ref>` (most reliable)
2. arXiv API `<comment>` (e.g. "Accepted at ICML 2023 (Oral)")
3. Abstract text parsing (e.g. "Published as a conference paper at ICLR 2024")
4. Graceful degradation — missing values left empty

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Confusing 404 with pending | `blog_pending` warning = overview not generated yet. API 404 = paper not on AlphaXiv. Different issues. |
| Re-running build for existing paper | Use Gate 3 `check_duplicates` first. Build creates new file each time. |
| Expecting EasyScholar for all papers | EasyScholar only works when venue is detected. No venue → no ranking. This is normal. |

## Handoff

Pass filepath to **03-validate-import** (REQUIRED SUB-SKILL).

## Fallback

If CLI fails, use direct Python API:
```python
from alphaxiv_workflow.api import resolve_paper_id, get_paper_metadata, get_overview, fetch_publication_info
from alphaxiv_workflow.venue import fetch_publication_rank
from alphaxiv_workflow.note_builder import build_note, sanitize_filename

arxiv_id = resolve_paper_id("query")
meta = get_paper_metadata(arxiv_id)
zh = get_overview(meta.version_id, 'zh')
en = get_overview(meta.version_id, 'en')
pub_info = fetch_publication_info(arxiv_id, abstract=meta.abstract)
pub_rank = fetch_publication_rank(pub_info.get('published_venue', '')) if pub_info.get('published_venue') else None
content, warnings = build_note(meta, zh, en, pub_info=pub_info, pub_rank=pub_rank)
```
