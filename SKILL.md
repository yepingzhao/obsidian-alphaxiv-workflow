---
name: obsidian-alphaxiv-workflow
description: Use when user wants to import academic papers from arXiv/AlphaXiv into Obsidian, requests literature analysis of saved papers, mentions paper blog or literature notes, or asks to backfill overviews for pending papers.
argument-hint: 'import "<query>" | import hot | import recommend | analyze "<topic>" | analyze author "<name>" | backfill-overviews'
---

# AlphaXiv to Obsidian

Routes user intent to the appropriate sub-skill pipeline. No side effects — each sub-skill manages its own dependencies.

## Sub-Commands

| Command | Pipeline | Purpose |
|---------|----------|---------|
| `import "<query>"` | Gate 1 → 2 → 3 → Auto-Backfill | Search, fetch, save, then auto-fetch overviews |
| `import hot` | Gate 1h → 2 → 3 → Auto-Backfill | Scrape AlphaXiv trending papers, then import |
| `import recommend` | Gate 1r → 2 → 3 → Auto-Backfill | Scrape AlphaXiv recommended papers, then import |
| `analyze "<topic>"` | Gate 4 | LLM five-chapter synthesis by topic |
| `analyze author "<name>"` | Gate 4 | LLM five-chapter synthesis by author |
| `backfill-overviews` | Backfill Pipeline (manual) | Manual batch fetch of all pending papers |

## Import Pipeline

```
User input → 01-search-disambiguate → 02-build-note → 03-validate-import → auto-backfill
```

**REQUIRED SUB-SKILL:** Load `skills/01-search-disambiguate/SKILL.md` — Gate 1: Search with boolean operators, present candidates, handle selection.

**REQUIRED SUB-SKILL:** Load `skills/02-build-note/SKILL.md` — Gate 2: Fetch metadata + AI overview, construct markdown note.

**REQUIRED SUB-SKILL:** Load `skills/03-validate-import/SKILL.md` — Gate 3: Validate frontmatter + headings, generate tags, check duplicates.

**Post-Import Auto-Backfill:** After all papers pass Gate 3, automatically run:
```bash
python -m alphaxiv_workflow.backfill --workers 3
python -m alphaxiv_workflow.backfill --dry-run
```
If papers remain pending, load `skills/05-backfill-overviews/SKILL.md` for Playwright trigger workflow, then re-run backfill. Finish with:
```bash
python -m alphaxiv_workflow.unify --phase 2
```

## Analyze Pipeline

```
User query → 04-literature-synthesis (LLM-driven)
```

**REQUIRED SUB-SKILL:** Load `skills/04-literature-synthesis/SKILL.md` — Gate 4: Weighted vault search → three-tier extraction → five-chapter LLM synthesis.

## Prerequisites

```bash
pip install -e .              # Core
pip install -e ".[batch]"     # Batch arXiv import support
```

Configuration via `OBSIDIAN_VAULT_PATH` env var or `~/.alphaxiv-to-obsidian.json`.
EasyScholar ranking requires `easyscholar_secret_key` in config (optional).
Papers saved to `300 Resources/320 References/`. Synthesis to `200 Areas/深度学习/`.

## Known Pitfalls

Critical issues documented in **[references/known-pitfalls.md](references/known-pitfalls.md)**. Key categories:
- AlphaXiv API: citations in TWO places (structured field often empty, embedded in markdown)
- YAML frontmatter: quote hygiene, inline list handling, quoted `blog_status` detection
- Playwright: 3-papers-per-batch hard server limit, multi-pattern button detection
- Script execution order: `python -m alphaxiv_workflow.backfill` → `python -m alphaxiv_workflow.fixups add-summaries` → `python -m alphaxiv_workflow.unify --phase 2`

## Fallback

If a Python CLI command fails, execute equivalent logic using direct Python API calls. Key imports are documented in each sub-skill's Fallback section.
