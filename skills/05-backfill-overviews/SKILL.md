---
name: 05-backfill-overviews
description: Use when paper notes have blog_status: pending and need AI overview content. Fetches existing overviews from AlphaXiv public API — no API key required.
---

# Backfill Overviews

Fetch missing AI overviews from AlphaXiv public API and update paper notes in the vault.

**No API key required.** AlphaXiv public API serves overviews via `get_overview(version_id, language)` with an unauthenticated `AlphaxivCat()` client.

**This pipeline is auto-triggered after every import** (see main SKILL.md Post-Import Auto-Backfill). Manual invocation is for batch processing of pre-existing pending papers or reprocessing after AlphaXiv outages.

All commands run from the project root. Ensure `pip install -e .` has been run first.

## Process

### Step 1: Scan

```bash
python -m alphaxiv_workflow.backfill --dry-run
```

Shows papers with `blog_status: pending` in `300 Resources/320 References/`.

### Step 2: Backfill

```bash
python -m alphaxiv_workflow.backfill --workers 3
```

For each pending paper:
1. Gets `version_id` from AlphaXiv metadata (public API)
2. Tries `get_overview(version_id, 'zh')` for Chinese overview
3. Falls back to `get_overview(version_id, 'en')` if Chinese unavailable
4. Updates note: replaces placeholder `## AI 综述` section, removes `blog_status: pending`

### Step 3: Handle Remainders

Papers that still return 404 (no overview exists on AlphaXiv) stay `blog_status: pending`. These need generation to be triggered first.

## Generating New Overviews (Playwright)

For papers without existing overviews, use Playwright browser automation:

### Triggering (per batch of 3)

```javascript
// Critical: use waitUntil: 'load' (NOT 'networkidle' — times out on persistent connections)
// Wait 4-5s after navigation for React to render the Generate/Retry button
// Use DOM search to find the button (text-based selectors are unreliable)
// Matches BOTH "Generate Overview" (fresh) AND "Try Again"/"Retry" (error recovery)
for (const aid of ['id1', 'id2', 'id3']) {
  try { await page.goto(`https://alphaxiv.org/overview/${aid}`, { waitUntil: 'load', timeout: 20000 }); } catch(e) {}
  await page.waitForTimeout(4000);
  await page.evaluate(() => {
    const TRIGGER_TEXTS = ['Generate Overview', 'Try Again', 'try again', 'Try again', 'Retry', 'Regenerate'];
    const btn = [...document.querySelectorAll('button')]
      .find(b => TRIGGER_TEXTS.some(t => b.textContent.trim().includes(t)));
    if (btn) btn.click();
  });
  await page.waitForTimeout(2000);
}
```

### Critical Rules

| Rule | Why |
|------|-----|
| `waitUntil: 'load'` only | `networkidle` times out on pages with persistent WS/analytics connections |
| Wait 4-5s after navigation | AlphaXiv is a React SPA — the Generate section renders asynchronously |
| Use `evaluate()` to find button | `getByText()`, `getByRole()` selectors are unreliable for this button |
| Exactly 3 per batch | **NEVER exceed.** AlphaXiv server limit: 3 parallel generations. Exceeding triggers: `You are generating blogs too quickly. Please wait a moment before trying again.` |
| Wait 3 min between batches | Generation takes ~1-2 min, wait buffer for completion |
| Retry stubborn papers | Some papers need 2-3 retriggers before generation succeeds |
| No button found (no Generate/Retry) | Paper may be **transferring** on AlphaXiv, or already has an overview. Wait hours/days and retry — overview becomes available after transfer completes. |

### Full Workflow

1. Navigate to `https://alphaxiv.org/overview/{arxiv_id}` (requires AlphaXiv login)
2. Ensure language is set to "zh" (Chinese)
3. Click the trigger button ("Generate Overview" / "Try Again" / "Retry") using the DOM search pattern above
4. Trigger exactly 3 papers, then **wait 3 minutes**
5. Run `python -m alphaxiv_workflow.backfill --workers 3` to fetch and save
6. Repeat for remaining papers until 0 pending

## How It Works

- Reads existing overviews from AlphaXiv API (no auth needed for GET)
- LaTeX math (`\frac`, `\mathcal`, etc.) in overviews is handled safely
- **Citations**: extracted from BOTH `overview.citations` (structured) AND `overview.overview` markdown text (embedded `## 相关引用`/`## 相关引文` section). Structured field is often empty.
- Citation regex: `r'##\s*(?:相关引[用文]|Reference|参考文献?)\s*\n(.*?)\Z'` — uses `\Z` (NOT `$`) to avoid MULTILINE truncation

## Rules

- Only processes papers with `blog_status: pending` in frontmatter
- Chinese (zh) preferred, English (en) as fallback
- Papers already with `## AI 综述` content are skipped
- Failed papers (404) remain `blog_status: pending`

## Standard Note Structure

After import + backfill, every note should have:
```
## 摘要
## AI 摘要          (from API overview.summary)
## AI 综述 (中文)    (from API overview.overview)
## 相关引用         (from API overview.citations OR overview.overview tail)
```

Use `alphaxiv_workflow/fixups.py` to fill gaps from API. Use `alphaxiv_workflow/fixups.py` for `*暂无相关引用*` placeholders.
