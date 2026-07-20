---
name: obsidian-alphaxiv-workflow
description: Import and manage arXiv or AlphaXiv papers in an Obsidian vault, including search and disambiguation, structured note creation, validation, pending-overview backfill, literature synthesis, and research-plan brainstorming grounded in saved papers. Use when the user mentions importing papers, AlphaXiv blogs or overviews, Obsidian literature notes, analyzing papers by topic or author, filling pending paper notes, or drafting a cited research plan from the vault. Route `import`, `analyze`, `backfill-overviews`, and `plan` requests to the matching sub-skill.
---

# AlphaXiv to Obsidian

Route the request to one workflow. Load only the listed sub-skills and references; do not preload every pipeline.

## Establish Context

1. Resolve `SKILL_ROOT` as the directory containing this file.
2. Resolve `PYTHON_CMD` once for the session. Probe the interpreter with `<candidate> -c "print('ok')"` and require exit code 0. On Windows, if bare `python` fails, enumerate candidates with `Get-Command python -All` or `where.exe python`, probe each exact executable path, and use the first working Python 3.11+ interpreter. Also try `py -3` when available. On other platforms, try `python3` after `python`. A WindowsApps alias that returns nonzero is not a package or AlphaXiv failure; do not install or debug the package through it.
3. Resolve `VAULT_PATH` from the explicit user value, then `OBSIDIAN_VAULT_PATH`, then `~/.alphaxiv-to-obsidian.json`.
4. Before writing, verify that `VAULT_PATH` exists. Never treat a missing or malformed Windows path as workspace-relative.

Keep the verified invocation as `PYTHON_CMD` and substitute it for every `<PYTHON_CMD>` below and in workflow references. Use the same interpreter for package installation so `pip` and runtime cannot diverge. Run all module commands with `SKILL_ROOT` as the working directory.

Install only when a required import is unavailable:

```bash
<PYTHON_CMD> -m pip install -e .
<PYTHON_CMD> -m pip install -e ".[batch]"  # only for batch arXiv import
```

## Route the Request

| Intent or command | Load | Completion condition |
|---|---|---|
| `import "<query>"` | Load [Search & Disambiguate](references/search-and-disambiguate.md) first. After selection, load [Build Note](references/build-note.md) and [Validate Import](references/validate-import.md). Load [Backfill Overviews](references/backfill-overviews.md) only if pending remains. | Confirmed papers saved and validated; remaining pending overviews reported |
| `import hot` / `import recommend` | Same import pipeline with the matching Gate 1 mode | Same as import |
| `analyze "<topic>"` / `analyze author "<name>"` | [Literature Synthesis](references/literature-synthesis.md) | User-approved synthesis saved |
| `backfill-overviews` | [Backfill Overviews](references/backfill-overviews.md) | Available overviews fetched; unresolved papers reported without false success |
| `plan "<direction>"` | [Research Plan](references/research-plan.md) | User-approved, cited plan and index saved |

Route natural-language requests by intent; do not require the literal command syntax.

## Import Contract

Do not read downstream import references before their checkpoint.

1. Load only Search & Disambiguate. Let Gate 1 create one unique session directory and keep every search round separate.
2. Show candidates and obtain selection before writing notes. Never overwrite an existing paper without confirmation.
3. After selection, load Build Note and Validate Import. Run both for every selected paper and resolve all `BLOCK` findings before declaring success.
4. After validation, run:

```bash
<PYTHON_CMD> -m alphaxiv_workflow.backfill --workers 3
<PYTHON_CMD> -m alphaxiv_workflow.backfill --dry-run
```

5. If pending papers remain and authenticated browser automation is available, follow Gate 5. Otherwise preserve `blog_status: pending` and report the limitation.
6. Finish normalization with:

```bash
<PYTHON_CMD> -m alphaxiv_workflow.fixups add-summaries
<PYTHON_CMD> -m alphaxiv_workflow.unify --phase 2
```

## Shared Invariants

- Keep `### AI 摘要` at H3 under `## 摘要`; keep `## AI 综述 (中文)` and `## 相关引用` at H2.
- Save paper notes under `300 Resources/320 References/`.
- Keep generated claims grounded in selected notes and cite them with Obsidian wikilinks.
- Treat external APIs and browser generation as fallible. Preserve partial state and identify the exact failed stage.
- Prefer the CLI path. Use a sub-skill's direct Python fallback only when its CLI fails.
- Keep temporary search state outside the workspace and delete only the exact session directory created for the current import.

## Conditional References

- Read [references/note-schema.md](references/note-schema.md) whenever building, validating, backfilling, or normalizing paper notes.
- Read [references/known-pitfalls.md](references/known-pitfalls.md) only when debugging or modifying import, note-format, API, YAML, or backfill behavior.
- Read [references/research-plan-output.md](references/research-plan-output.md) only when Gate 6 reaches drafting, refinement, or saving.
