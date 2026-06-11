---
name: 03-validate-import
description: Use when a paper note has been saved to the Obsidian vault from Gate 2 and needs frontmatter validation, heading hierarchy check, duplicate detection, and intelligent tag generation.
---

# Validate Import (Gate 3)

Post-save validation and enrichment of imported paper notes.

## Process

### Step 1: Run Full Validation

```bash
python -m alphaxiv_workflow.validate "FILEPATH"
```

This runs all checks: frontmatter, heading hierarchy, duplicates, and tag count. Use `--step` for single checks:

```bash
python -m alphaxiv_workflow.validate "FILEPATH" --step frontmatter
python -m alphaxiv_workflow.validate "FILEPATH" --step headings
python -m alphaxiv_workflow.validate "FILEPATH" --step duplicates
python -m alphaxiv_workflow.validate "FILEPATH" --step tags
```

### Step 2: Understand Validation Levels

| Severity | Check | Action |
|----------|-------|--------|
| **BLOCK** | YAML parse error | Stop, report error |
| **BLOCK** | Missing title or arxiv_id | Stop, report error |
| **BLOCK** | Missing required H2 (`摘要`, `AI 摘要`, `AI 综述 (中文)`, `相关引用`) | Must be added before proceeding |
| **WARN** | Authors list empty | Save with warning |
| **WARN** | Tags count < 5 | Flag for tag generation |
| **WARN** | Skipped heading level (H2→H4 without H3) | Fix heading hierarchy |
| **INFO** | No published_venue | Publication venue unknown (normal for preprints) |
| **INFO** | No published_date | Publication date unknown |

### Step 3: Handle Duplicates

If duplicates found for the same `arxiv_id`:
- Report to user with file paths
- Do NOT overwrite without confirmation
- User chooses: skip / overwrite / open existing

### Step 4: Generate Tags

Tag generation requires LLM analysis. Use Claude inline:
1. Read note content: `alphaxiv_workflow.validate.read_note_content(filepath)` → `{title, abstract, overview}`
2. Generate 5-8 tags covering: research area, task, method, key concepts, model/architecture
3. Tags: lowercase, kebab-case, English
4. Merge: `alphaxiv_workflow.validate.merge_tags(filepath, new_tags)`

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Running `merge_tags` on notes that already have good tags | `merge_tags` is additive — never removes existing tags. Only run for notes with <5 tags. |
| Assuming BLOCK means paper is broken | Most BLOCKs are fixable: add missing H2 sections, fix YAML quotes. |
| Skipping validation for "simple" papers | Every import gets validated. Even clean-looking notes can have hidden YAML issues. |

## Rules

- BLOCK issues must be resolved before completion
- Duplicates require user confirmation
- Tag generation is mandatory for every import
- Tags are additive: never remove existing tags
- Validation does NOT modify the note (except `merge_tags`)

## Handoff

After all papers pass validation, the main skill automatically triggers **Post-Import Auto-Backfill** (see `skills/05-backfill-overviews/SKILL.md`).

## Fallback

If CLI fails, use direct Python API:
```python
from alphaxiv_workflow.validate import validate_frontmatter, check_heading_hierarchy, check_duplicates, merge_tags, read_note_content
result = validate_frontmatter("FILEPATH")
headings = check_heading_hierarchy("FILEPATH")
dups = check_duplicates("ARXIV_ID", "VAULT_PATH")
content = read_note_content("FILEPATH")  # for tag generation
```
