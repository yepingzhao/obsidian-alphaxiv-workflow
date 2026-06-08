---
name: obsidian-alphaxiv-workflow
description: Use when user wants to save a paper to Obsidian, mentions AlphaXiv or arXiv papers, paper blog, literature notes, or asks to capture paper summaries and overviews. Also use when user wants to analyze or synthesize saved papers by topic or author.
---

# AlphaXiv to Obsidian

Dispatch entry for the skill library. Routes user intent to the appropriate sub-skill pipeline.

## Startup (CRITICAL — execute FIRST)

**ALWAYS start Playwright BEFORE any pipeline work.** This ensures the browser is ready when backfill-overviews or overview generation is needed.

```
mcp__playwright__browser_navigate → https://alphaxiv.org
```

Rationale:
- Playwright browser startup takes 2-3s — doing it upfront avoids blocking later
- All pipelines may eventually need browser access (overview generation, search verification)
- A single browser session serves the entire skill invocation
- If browser is already open, `browser_navigate` reuses the existing session

**After navigation:** keep the browser tab open. It will be used by `backfill-overviews` for overview generation.

## Sub-Commands

| Command | Pipeline | Purpose |
|---------|----------|---------|
| `import "<query>"` | Gate 1 -> 2 -> 3 | Search, fetch, and save paper(s) to vault |
| `analyze "topic"` | Gate 4 | LLM five-chapter synthesis: search, extract, generate, iterate |
| `analyze author "name"` | Gate 4 | LLM five-chapter author analysis: search, extract, generate, iterate |
| `backfill-overviews` | Backfill Pipeline | Fetch existing overviews + trigger new generation via Playwright |

## Import Pipeline

```
User input -> search-disambiguate -> build-note (auto-gen) -> validate-import
```

**REQUIRED SUB-SKILL:** Load `skills/search-disambiguate/SKILL.md` -- Gate 1: Search AlphaXiv, present candidates, support single/multi selection.

**REQUIRED SUB-SKILL:** Load `skills/build-note/SKILL.md` -- Gate 2: Fetch metadata + AI overview. If overview unavailable, **auto-trigger generation via Playwright**, wait, then retry API. Construct markdown note, validate title compliance.

**REQUIRED SUB-SKILL:** Load `skills/validate-import/SKILL.md` -- Gate 3: Validate frontmatter + heading hierarchy, generate intelligent tags, check duplicates.

**Auto-generation flow in Gate 2:** When API returns no overview, the skill automatically uses the pre-started Playwright browser to navigate to the paper's AlphaXiv page, click "Generate Overview", wait for completion, then retry the API. Only falls back to `blog_status: pending` if auto-generation fails after retries.

## Analyze Pipeline

```
User query -> literature-synthesis (LLM-driven)

1. Weighted search (title → tags → content) with relevance ranking
2. Three-tier content extraction per paper
3. LLM generates five-chapter synthesis inline
4. Natural language iteration (up to 3 rounds)
5. Save with wikilink citations
```

**REQUIRED SUB-SKILL:** Load `skills/literature-synthesis/SKILL.md` -- Gate 4: Search vault papers by topic/author with relevance scoring. Generate five-chapter LLM synthesis with iterative refinement.

**Output chapters:** 方法分类与对比 → 演进脉络 → 共识与矛盾 → 空白与机会 → 关键论文推荐

**Quick mode:** `analyze "topic" --quick` skips confirmation & iteration.

## Overview Backfill Pipeline

```
User input -> backfill-overviews
```

**REQUIRED SUB-SKILL:** Load `skills/backfill-overviews/SKILL.md` — Overview Backfill: Scan vault for `blog_status: pending` papers, fetch existing overviews via AlphaXiv public API (no auth required), update notes.

All API access is public read-only. New overview generation is triggered exclusively via Playwright browser automation.

### Playwright Trigger (for generating new overviews)

If a paper has no overview on AlphaXiv (API returns 404), use Playwright browser automation.

**Browser is already started** per the Startup section above. Use the existing `mcp__playwright__*` tools — do NOT start a new browser.

**Key technical details** (see `skills/backfill-overviews/SKILL.md` for full guide):
- Navigate with `browser_navigate` (use `waitUntil: 'load'` via `browser_evaluate` — NOT `networkidle`, which times out on persistent connections)
- Wait 4-5s after navigation for React to fully render (`browser_wait_for` with `time: 5`)
- Find button via `browser_evaluate`: `[...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Generate Overview')`
- Click via `browser_click` with the found element reference
- Strictly **3 papers per batch**, wait **3 minutes** between batches
- Some stubborn papers need 2-3 retriggers

**Auto-generation is now integrated into Gate 2 (build-note).** When importing a paper with no overview, Playwright automatically triggers generation, waits, and retries the API. The `backfill-overviews` pipeline remains available for batch processing of papers that were saved with `blog_status: pending` from earlier imports or failed auto-generation attempts.

## Shared Scripts

| Module | Path | Purpose |
|--------|------|---------|
| `gate1_search.py` | `scripts/` | Gate 1 async pipeline: search → batch arXiv → parallel enrich → table output |
| `alphaxiv_client.py` | `scripts/` | AlphaXiv API: search, metadata, overview |
| `note_builder.py` | `scripts/` | Markdown construction, title cleaning, citation formatting |
| `validator.py` | `scripts/` | Frontmatter validation, heading hierarchy check, duplicate detection, tag merge |
| `literature_analyzer.py` | `scripts/` | Vault search, paper summary extraction, synthesis generation |
| `backfill_overviews.py` | `scripts/` | Scan vault, fetch overviews via public API, update notes (no key) |
| `parallel_batch_import.py` | `scripts/` | Parallel arXiv import with rate limiting (2 workers) |
| `batch_import.py` | `scripts/` | Batch arXiv import (sequential, `arxiv` library required) |
| `batch_from_json.py` | `scripts/` | Batch import from JSON files of arXiv IDs with exponential backoff |
| `add_missing_sections.py` | `scripts/` | Add missing `## AI 摘要` + `## 相关引用` from API |
| `unify_structure.py` | `scripts/` | Normalize YAML frontmatter field order + H2 headings |
| `fix_quotes.py` | `scripts/` | Fix malformed YAML quotes (""" → ") |
| `fix_placeholder_citations.py` | `scripts/` | Replace `*暂无相关引用*` placeholders from API |
| `pw_batch_trigger.py` | `scripts/` | Print pending arxiv_ids in Playwright-ready batch arrays |

## Known Pitfalls

### AlphaXiv API: citations in TWO places
The `overview.citations` structured field is **often empty**. Citations are frequently embedded in the `overview.overview` markdown text as a trailing `## 相关引用` or `## 相关引文` section. Always check BOTH sources.

**Extraction regex** (applies to all scripts):
```
r'##\s*(?:相关引[用文]|Reference|参考文献?)\s*\n(.*?)\Z'
```
- Use `\Z` (NOT `$`) — `re.MULTILINE` makes `$` match end-of-line, truncating capture
- Match `相关引文` (引文) AND `相关引用` (引用) — AlphaXiv uses both

### YAML frontmatter: quote hygiene
When normalizing frontmatter, ALWAYS strip existing quotes before re-quoting. The regex `^(\w[\w-]*):\s*(.*)` captures the value INCLUDING quotes. Use `clean_value()` that strips all wrapping quotes, then re-adds exactly one layer.

### Note validation: read FULL file
Frontmatter can exceed 800 chars (long author lists). Validation scripts must read full file content, not truncated chunks.

### Playwright: button detection
See `skills/backfill-overviews/SKILL.md` for complete guide. Key: `waitUntil: 'load'` + 4-5s wait + JS `evaluate()` to find button.

### Duplicate detection
Import scripts must check for existing notes by `arxiv_id` frontmatter value, not just filename. Names vary (`Title` vs `Title-`).

### Citation heading: normalize to `## 相关引用`
AlphaXiv overview text uses BOTH `## 相关引用` and `## 相关引文`. All notes must use `## 相关引用` only. When extracting citations from overview:
- **Strip the heading** from extracted content (return raw citation text only, no `##` prefix)
- **Remove noise**: filter `[本节稍后手动填充]` and similar placeholder lines
- The insert point must NOT depend on `*Fetched from` (not all notes have a footer)

### Regex: avoid `re.DOTALL` over-deletion
When removing sections with `re.DOTALL`, the `.*?` can consume far more than intended if the boundary pattern (`\n---\n*Fetched`) doesn't exist. Always verify the boundary exists before using it, or use a more constrained regex with explicit section-ending markers (`\n## `).

### Script execution order: avoid `## AI 摘要` duplication

**Problem:** Running `add_missing_sections.py` → `unify_structure.py --phase 2` → `add_missing_sections.py` (re-run) creates duplicate `## AI 摘要` sections.

**Root cause:** `unify_structure.py --phase 2` merges `## AI 摘要` into `## AI 综述 (中文)` as a subheading (`### AI 摘要`), then removes the original `## AI 摘要` H2. When `add_missing_sections.py` runs again, it can't find `## AI 摘要` and adds a duplicate.

**Fix (applied):** `add_missing_sections.py` detection now also checks for `### AI 摘要` and `### 核心总结` (merged subheadings). Safe to re-run after unify.

**Correct order:** `backfill_overviews.py` → `add_missing_sections.py` → `unify_structure.py --phase 2`

### `backfill_overviews.py` re-run: avoid `## 相关引用` duplication

**Problem:** Re-running `backfill_overviews.py` on a paper that already has `## 相关引用` creates a duplicate section.

**Root cause:** The regex `## AI 综述.*?(?=\n---|\n## |\Z)` only replaces the AI overview section. If a previous run already inserted `## 相关引用` (from overview text), the old citation section falls outside the replacement boundary and survives. Then `new_section` also contains `## 相关引用`, creating a duplicate.

**Fix (applied):** Before inserting `new_section`, `update_note()` now strips any existing `## 相关引用` sections (both with and without leading `---` separator).

### AlphaXiv citation extraction: handle un-headed citation blocks

**Problem:** AlphaXiv sometimes returns citations as paragraph-style blocks at the end of the overview WITHOUT a `## 相关引用` heading. The old extraction regex only matched headed sections, silently dropping these citations.

**Example format (no heading):**
```
潦草数据库：学习检索拙劣绘制的小兔子
该引用至关重要...
Patsorn Sangkloy, Nathan Burnell, ... The Sketchy Database...

Adding Conditional Control to Text-to-Image Diffusion Models
本文介绍了 ControlNet...
Lvmin Zhang, Anyi Rao, ... In Proceedings of the IEEE/CVF ICCV, 2023.
```

**Fix (applied to `backfill_overviews.py`):** Three-stage extraction:
1. **Method 1:** Explicit heading (`## 相关引用` / `## Reference` / `## 参考文献`)
2. **Method 2 (NEW):** Un-headed paragraph block detection — scans paragraphs from end of overview for citation indicators: numbered items, author-year patterns, venue references (CVPR/ICCV/NeurIPS/arXiv), Chinese citation descriptions
3. **Method 3:** Strip any remaining heading-based references (safety net)

**Impact:** Re-running `backfill_overviews.py` on affected papers will now correctly extract and save previously-lost citations.

### `unify_structure.py`: do NOT merge `## AI 摘要` into `## AI 综述 (中文)`

**Problem:** `unify_structure.py --phase 2` merged `## AI 摘要` into `## AI 综述 (中文)` as `### AI 摘要` H3, destroying the standalone H2. These are fundamentally different sections:
- `## AI 摘要` = structured summary (核心总结, 关键洞察, 问题背景, 方法, 结果)
- `## AI 综述 (中文)` = narrative overview

**Correct structure:**
```
## 摘要
## AI 摘要
### 核心总结
### 关键洞察
### 问题背景
### 方法
### 结果
## AI 综述 (中文)
### 概述
...
## 相关引用
```

**Fix (applied to `unify_structure.py`):** Replaced merge logic with ordering logic — only reorder if `## AI 摘要` appears after `## AI 综述 (中文)`, never merge.

### `unify_structure.py`: inline YAML list gets quote-wrapped into string

**Problem:** When frontmatter has inline YAML list `tags: [paper, ai, diffusion]`, `unify_structure.py --phase 2` treats the value as an opaque string. Since it's not `true`/`false`/numeric, it wraps in double quotes: `tags: "[paper, ai, diffusion]"`. Obsidian cannot parse this as a tag list — all tags become one literal string.

**Root cause:** Frontmatter parser stores `[paper, ai, diffusion]` as a scalar string. The `kv` regex captures everything after the colon as a single value; only indented `- item` lines are detected as lists. The re-build phase then quotes any non-bool/non-numeric string.

**Fix (applied 2026-06-08):** Added inline YAML list detection after `kv` match — if value matches `"[?[...]]"?` pattern, parse as Python list. The re-build phase serializes as block list format (`tags:\n  - item`), the most Obsidian-compatible format.

**Impact:** Previously-imported papers with `tags: "[...]"` need re-unifying. Running `unify_structure.py --phase 2` after this fix converts them to proper block lists.

### `backfill_overviews.py`: blog_status detection fails on quoted values

**Problem:** `scan_pending()` checks `'blog_status: pending' not in content` (exact string). After `unify_structure.py` normalizes frontmatter, the value becomes `blog_status: "pending"` (quoted), causing false negative — pending papers are silently skipped.

**Fix (applied 2026-06-08):** Changed to regex `r'blog_status:\s*"?pending"?'` for both detection and removal. Handles quoted and unquoted variants.

### `add_missing_sections.py`: false "All notes complete!" for narrative overviews

**Problem:** The script decides a paper has AI 摘要 if `### 核心总结` or `### 摘要` exists anywhere in content. Freshly backfilled papers with narrative-style H3s (e.g. `### 控制复杂物理系统的挑战`) lack these markers, so the script incorrectly skips them while `## AI 摘要` H2 is still missing.

**Workaround:** Bypass `add_missing_sections.py` — directly call `get_overview(version_id, lang).summary` via API and insert `## AI 摘要` with structured `### 核心总结` / `### 关键洞察` sub-headings.

**TODO:** Fix detection to check for `## AI 摘要\n` H2 heading directly, independent of sub-heading content.

## Fallback

If a Python script is unavailable or fails, execute the equivalent logic directly using Read/Write/Edit tools against the vault filesystem.

## Configuration

Vault path via `OBSIDIAN_VAULT_PATH` env var or `~/.alphaxiv-to-obsidian.json`. Default: workspace vault.

Papers saved to `300 Resources/320 References/`. Synthesis to `200 Areas/深度学习/`.

## Prerequisites

`pip install alphaxiv_cat pyyaml`

**Batch arXiv import** (`batch_import.py`) additionally requires: `pip install arxiv`

**Publication ranking** (EasyScholar) requires `easyscholar_secret_key` in `~/.alphaxiv-to-obsidian.json`. Get your key from EasyScholar. Without it, publication venue info still works but CCF/SCI/CAS rankings are skipped.

**Playwright overview generation** requires a logged-in AlphaXiv browser session (login at `https://alphaxiv.org`). The Startup section auto-navigates the browser; if the session expires, re-login via Playwright before triggering generation.
