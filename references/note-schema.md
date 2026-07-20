# Paper Note Schema

Treat this file as the single source of truth for imported paper-note structure.

## Frontmatter Contract

- Require non-empty `title` and `arxiv_id`.
- Preserve `version`, `date`, `source`, `authors`, `aliases`, and `created` when available.
- Store tags as a YAML list. Generate 5-8 meaningful tags before completing an import.
- Add publication and ranking fields only when supported by source data; leave unknown values absent instead of guessing.
- Keep `blog_status: pending` only while an overview is unavailable. Remove it after a successful backfill.
- Quote string values safely, especially titles containing `:` or `"` and numeric-looking arXiv IDs.

## Canonical Body

```markdown
# <title>

> <paper metadata line>

## 摘要

<paper abstract>

---

### AI 摘要

<structured summary>

### 要点

- <insight>

### 问题

- <problem>

### 方法

- <method>

### 结果

- <result>

---

## AI 综述 (中文)

> *由 AlphaXiv 生成*

<detailed overview with nested headings demoted>

---

## 相关引用

<citations>
```

## Heading Rules

- Keep exactly one H1 title.
- Keep `摘要`, `AI 综述 (中文)`, and `相关引用` at H2.
- Keep `AI 摘要` and its structured summary subsections at H3.
- Use horizontal rules to separate the source abstract, generated summary, detailed overview, and citations.
- Do not duplicate placeholders when replacing pending content.
- Do not promote headings embedded in an AlphaXiv overview above their containing H2 section.
