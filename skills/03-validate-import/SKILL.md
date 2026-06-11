---
name: 03-validate-import
description: Use when a newly saved paper note in Obsidian needs frontmatter validation, intelligent tag generation, and duplicate detection after import.
---

# Validate Import (Gate 3)

Post-save validation and enrichment of imported paper notes.

All commands run from the project root. Ensure `pip install -e .` has been run first.

## Process

### Step 1: Validate Frontmatter

```bash
python -c "

from alphaxiv_workflow.validate import validate_frontmatter
result = validate_frontmatter('FILEPATH')
print(result)
"
```

**Validation levels:**

| Severity | Check | Action |
|----------|-------|--------|
| **BLOCK** | YAML parse error | Stop, report error |
| **BLOCK** | Missing title or arxiv_id | Stop, report error |
| **WARN** | Authors list empty | Save with warning |
| **WARN** | Tags count < 5 | Flag needs-tags |

### Step 2: Validate Heading Hierarchy

```bash
python -c "

from alphaxiv_workflow.validate import check_heading_hierarchy
result = check_heading_hierarchy('FILEPATH')
print(result)
"
```

**Hierarchy checks:**

| Severity | Check | Rule |
|----------|-------|------|
| **BLOCK** | No H1 or multiple H1 | Exactly one `#` title heading |
| **BLOCK** | No headings in body | Frontmatter parsed but body empty |
| **WARN** | Skipped heading level | H2 -> H4 without H3 in between |
| **WARN** | Depth > H4 | `#####` and deeper not allowed |
| **BLOCK** | Missing required H2 section | All 4 must exist: `## 摘要`, `## AI 摘要`, `## AI 综述 (中文)`, `## 相关引用` |

### Step 3: Check Duplicates

```bash
python -c "

from alphaxiv_workflow.validate import check_duplicates
dups = check_duplicates('ARXIV_ID', 'VAULT_PATH')
"
```

If duplicates found, report to user. Do NOT overwrite without confirmation.

### Step 4: Generate Tags

1. Read note: `alphaxiv_workflow.validate.read_note_content(filepath)` -> `{title, abstract, overview}`
2. Analyze content and generate **5-8 tags** covering:
   - Research area (e.g., `computer-vision`, `nlp`)
   - Task (e.g., `semantic-segmentation`, `image-classification`)
   - Method (e.g., `contrastive-learning`, `attention-mechanism`)
   - Key concepts (e.g., `open-vocabulary`, `zero-shot`)
   - Model/Architecture (e.g., `vision-transformer`, `clip`)
3. Tags: lowercase, kebab-case, English
4. Merge: `alphaxiv_workflow.validate.merge_tags(filepath, new_tags)`

## Handoff

After all papers pass validation, the main skill automatically triggers **Post-Import Auto-Backfill**:
1. Runs `alphaxiv_workflow/backfill.py` to fetch overviews for any `blog_status: pending` papers
2. Uses Playwright to trigger overview generation for papers still without overviews
3. Runs `alphaxiv_workflow/backfill.py` again to save newly generated overviews
4. Runs `alphaxiv_workflow/unify.py --phase 2` to normalize structure

No manual action needed — this is fully automatic.

## Rules

- BLOCK issues must be resolved before completion
- Duplicates require user confirmation
- Tag generation is mandatory for every import
- Tags are additive: never remove existing tags
