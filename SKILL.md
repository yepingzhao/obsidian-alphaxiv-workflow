---
name: obsidian-alphaxiv-workflow
description: Use when user wants to save a paper to Obsidian, mentions AlphaXiv or arXiv papers, paper blog, literature notes, or asks to capture paper summaries and overviews. Also use when user wants to analyze or synthesize saved papers by topic or author.
argument-hint: 'import "query" | import hot | import recommend | analyze "topic" | analyze author "name" | backfill-overviews'
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

## Sub-Commands

| Command | Pipeline | Purpose |
|---------|----------|---------|
| `import "<query>"` | Gate 1 → 2 → 3 → Auto-Backfill | Search, fetch, save, then auto-fetch overviews |
| `import hot` | Gate 1h → 2 → 3 → Auto-Backfill | Scrape AlphaXiv trending papers, then import |
| `import recommend` | Gate 1r → 2 → 3 → Auto-Backfill | Scrape AlphaXiv recommended papers, then import |
| `analyze "topic"` | Gate 4 | LLM five-chapter synthesis: search, extract, generate, iterate |
| `analyze author "name"` | Gate 4 | LLM five-chapter author analysis: search, extract, generate, iterate |
| `backfill-overviews` | Backfill Pipeline (manual) | Manual batch fetch of all pending papers + Playwright trigger |

## Import Pipeline

```
User input → 01-search-disambiguate → 02-build-note (auto-gen) → 03-validate-import → auto-backfill
```

**REQUIRED SUB-SKILL:** Load `skills/01-search-disambiguate/SKILL.md` — Gate 1: Search AlphaXiv with boolean operators (AND/OR/NOT/-/parens), present candidates, support single/multi selection.

**REQUIRED SUB-SKILL:** Load `skills/02-build-note/SKILL.md` — Gate 2: Fetch metadata + AI overview from AlphaXiv. If overview unavailable, auto-trigger generation via Playwright, wait, then retry API. Construct markdown note.

**REQUIRED SUB-SKILL:** Load `skills/03-validate-import/SKILL.md` — Gate 3: Validate frontmatter + heading hierarchy, generate intelligent tags, check duplicates.

### Post-Import Auto-Backfill

After ALL papers complete Gates 2-3, automatically run the backfill pipeline to catch any `blog_status: pending` papers:

```bash
# Step 1: Fetch existing overviews via public API
python -m alphaxiv_workflow.backfill --workers 3

# Step 2: Check for remainders
python -m alphaxiv_workflow.backfill --dry-run
```

If papers remain pending, use Playwright (already started) to trigger overview generation, then re-run Step 1. Full Playwright trigger details in `skills/05-backfill-overviews/SKILL.md`.

After backfill completes:
```bash
python -m alphaxiv_workflow.unify --phase 2
```

**Skip conditions:** no pending papers → skip entire auto-backfill. No Playwright → skip trigger, still run API fetch.

### Hot Papers (`import hot`)

Scrapes AlphaXiv trending page, presents candidates, feeds selection through Import Pipeline.

```bash
python -m alphaxiv_workflow.fetch_hot "VAULT_PATH" --data-file /tmp/alphaxiv_hot_papers.json
```

Same selection logic as Gate 1. Options: `--limit 5`, `--skip-existing`.

### Recommend Papers (`import recommend`)

Scrapes AlphaXiv recommended page, same flow as hot papers.

```bash
python -m alphaxiv_workflow.fetch_recommend "VAULT_PATH" --data-file /tmp/alphaxiv_recommend_papers.json
```

## Analyze Pipeline

```
User query → 04-literature-synthesis (LLM-driven)
1. Weighted search (title → tags → content) with relevance ranking
2. Three-tier content extraction per paper
3. LLM generates five-chapter synthesis inline
4. Natural language iteration (up to 3 rounds)
5. Save with wikilink citations
```

**REQUIRED SUB-SKILL:** Load `skills/04-literature-synthesis/SKILL.md` — Gate 4: Search vault papers by topic/author. Generate five-chapter LLM synthesis: 方法分类与对比 → 演进脉络 → 共识与矛盾 → 空白与机会 → 关键论文推荐.

Output: `200 Areas/深度学习/AI 综述 {topic/author} {YYYY-MM-DD}.md`. Quick mode: `analyze "topic" --quick`.

## Overview Backfill Pipeline (Manual)

Auto-triggered after every import. Use manual `backfill-overviews` only for batch processing pre-existing pending papers.

**REQUIRED SUB-SKILL:** Load `skills/05-backfill-overviews/SKILL.md` — Scan vault for `blog_status: pending`, fetch overviews via public API, Playwright-trigger remainders (3 papers per batch hard limit, 3 min between batches).

## Shared Modules

All modules live in the `alphaxiv_workflow/` package. Install with `pip install -e .`

| Module | Package Path | Purpose |
|--------|-------------|---------|
| `api.py` | `alphaxiv_workflow/` | AlphaXiv + arXiv API: search, metadata, overview |
| `note_builder.py` | `alphaxiv_workflow/` | Markdown construction, title cleaning, citation formatting |
| `query_parser.py` | `alphaxiv_workflow/` | Boolean query parser (AND/OR/NOT/-/parentheses) |
| `venue.py` | `alphaxiv_workflow/` | Venue extraction + EasyScholar CCF/SCI/CAS ranking |
| `search.py` | `alphaxiv_workflow/` | Gate 1: async search pipeline → batch arXiv → table output |
| `build.py` | `alphaxiv_workflow/` | Single-paper note construction CLI |
| `validate.py` | `alphaxiv_workflow/` | Frontmatter validation, heading check, duplicates, tags |
| `synthesis.py` | `alphaxiv_workflow/` | Gate 4: vault search, extraction, LLM synthesis |
| `backfill.py` | `alphaxiv_workflow/` | Scan vault, fetch overviews via public API, update notes |
| `import_papers.py` | `alphaxiv_workflow/` | Batch arXiv import (--workers for ThreadPoolExecutor) |
| `fetch_hot.py` | `alphaxiv_workflow/` | Scrape AlphaXiv trending papers, enrich via arXiv API |
| `fetch_recommend.py` | `alphaxiv_workflow/` | Scrape AlphaXiv recommended papers, enrich via arXiv API |
| `trigger.py` | `alphaxiv_workflow/` | Print pending arxiv_ids in Playwright-ready batch arrays |
| `unify.py` | `alphaxiv_workflow/` | Normalize YAML frontmatter field order + H2 headings |
| `fixups.py` | `alphaxiv_workflow/` | add_missing_sections, fix_quotes, fix_placeholder_citations |
| `config.py` | `alphaxiv_workflow/` | Unified config: vault path + API keys |

## Known Pitfalls

Critical issues across the codebase are documented in **[references/known-pitfalls.md](references/known-pitfalls.md)**. Key categories:

- AlphaXiv API: citations in TWO places (structured field often empty, embedded in markdown)
- YAML frontmatter: quote hygiene, inline list handling, quoted `blog_status` detection
- Playwright: 3-papers-per-batch hard server limit, multi-pattern button detection
- Script execution order: `python -m alphaxiv_workflow.backfill` → `python -m alphaxiv_workflow.fixups add-summaries` → `python -m alphaxiv_workflow.unify --phase 2`
- `zh.summary` is a Pydantic model — use `format_ai_summary_from_model()` from `note_builder.py`

## Fallback

If a Python script is unavailable or fails, execute the equivalent logic directly using Read/Write/Edit tools against the vault filesystem.

## Configuration

Vault path via `OBSIDIAN_VAULT_PATH` env var or `~/.alphaxiv-to-obsidian.json`. Default: workspace vault.
Papers saved to `300 Resources/320 References/`. Synthesis to `200 Areas/深度学习/`.

## Prerequisites

`pip install -e .`

Batch arXiv import (`import_papers.py`) additionally requires: `pip install alphaxiv-workflow[batch]`

Publication ranking (EasyScholar) requires `easyscholar_secret_key` in `~/.alphaxiv-to-obsidian.json`. Without it, venue info still works but CCF/SCI/CAS rankings are skipped.

Playwright overview generation requires a logged-in AlphaXiv browser session. The Startup section auto-navigates; if the session expires, re-login via Playwright before triggering generation.
