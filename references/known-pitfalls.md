# Known Pitfalls

Critical issues encountered across this codebase. Read before modifying any pipeline.

---

## AlphaXiv API

### Citations in TWO places
AlphaXiv overview responses contain citations in **both** a structured `citations` array (often empty/missing) **and** embedded in the markdown `overview` field (as "## 相关引用" / "## References" section). The `backfill.py` `update_note()` function extracts from both sources, preferring the embedded markdown block.

### summary_section_titles are inconsistent
The API returns localized section titles. For ZH papers, `summary_section_titles.summary` can be `'AI 摘要'`, `'摘要'`, `'核心总结'`, or other variants. **This is handled by `build_summary_sections()` which always outputs `### <API_title>` as H3.** The note's own `### AI 摘要` section heading should NOT conflict — the structured format replaces the note's placeholder entirely.

### English overview existence
Papers with ZH overviews (the common case) may still have EN overviews available. The backfill now fetches **both** languages and uses EN summary data as fallback when ZH summary is empty.

---

## Note Format

### Canonical note structure (post-build)
```markdown
## 摘要
[paper abstract]

---
### AI 摘要
[structured summary paragraph]

### 要点
- bullet points

### 问题
- bullet points

### 方法
- bullet points

### 结果
- bullet points

---
## AI 综述 (中文)
> *由 AlphaXiv 生成*

[detailed Chinese overview with demoted headings]
---
## 相关引用
[citations]
```

### Key rules
1. `### AI 摘要` is **always H3** — nested under `## 摘要`, never standalone H2
2. `---` separates the paper's own abstract from the AI-generated summary sections
3. `build_summary_sections()` always outputs H3 headings (`###`)
4. The first heading from `build_summary_sections()` (the `summary` field) sets the main label

### Common post-build corruptions
| Corruption | Cause | Fix |
|-----------|-------|-----|
| `### AI 摘要\n\n### 摘要` | backfill appends structured summary without removing old placeholder heading | Remove the first `### AI 摘要\n\n` |
| `### AI 摘要\n\n### AI 摘要` | `build_summary_sections` H2 output + note's existing `###` heading | `build_summary_sections` now always outputs H3 |
| Duplicate 中文综述 at end | backfill `update_note()` regex doesn't cover non-`---` boundaries | Fixed in code: `## AI 综述.*?(?=\n---|\n## |\Z)` |
| `*暂无 AI 摘要数据*` | ZH overview available but summary field empty | Backfill now fetches EN summary as fallback |
| `## AI 摘要` (H2) in older notes | Pre-H3-convention notes from older imports | `backfill.py` auto-fixes: `\n## AI 摘要\n` → `\n### AI 摘要\n` |

---

## Backfill

### Execution order
```
python -m alphaxiv_workflow.backfill --workers 3
python -m alphaxiv_workflow.fixups add-summaries
python -m alphaxiv_workflow.unify --phase 2
```

### Double-language fetch
The backfill now fetches **both** ZH and EN overviews per paper:
- ZH overview → `## AI 综述 (中文)`
- EN summary → `### AI 摘要` structured data (fallback when ZH summary empty)
- Citations merged from both responses

### Playwright overview generation
- **3 papers per batch** hard server limit
- Multi-pattern button detection (`Generate Overview`, `生成概述`, etc.)
- **3 minutes minimum** between batches to avoid rate limiting

---

## YAML Frontmatter

### Quote hygiene
- `title` values with `"` must be escaped: `title: "escaped \"quote\""`
- `blog_status` may appear as `blog_status: pending` or `blog_status: "pending"` — both handled

### blog_status detection
Frontmatter-only check — if `blog_status: pending` appears in the note body (e.g., in a code block), it's ignored. Only the YAML frontmatter `blog_status` field controls backfill targeting.

---

## zh.summary Pydantic model

`zh.summary` is a Pydantic model, not a plain dict. Use `format_ai_summary_from_model()` from `note_builder.py` to convert. **Never** use `str()` or f-string on `overview_model.summary` — the `__repr__` produces unreadable `Summary(key_insights=[...])` text.
