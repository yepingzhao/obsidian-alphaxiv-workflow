---
name: 05-backfill-overviews
description: Use when paper notes have blog_status: pending and need AI overview content fetched or generated. Auto-triggered after every import; manual invocation for batch processing pre-existing pending papers.
---

# Backfill Overviews

Fetch missing AI overviews from AlphaXiv public API and update paper notes. For papers without existing overviews, trigger generation via Playwright browser automation.

## Process

### Step 1: Scan for Pending Papers

```bash
python -m alphaxiv_workflow.backfill --dry-run
```

Shows papers with `blog_status: pending` in `300 Resources/320 References/`.

### Step 2: Fetch Existing Overviews

```bash
python -m alphaxiv_workflow.backfill --workers 3
```

For each pending paper:
1. Gets `version_id` from AlphaXiv metadata (public API, no auth needed)
2. Tries `get_overview(version_id, 'zh')` for Chinese overview
3. Falls back to `get_overview(version_id, 'en')` if Chinese unavailable
4. Updates note: replaces placeholder, removes `blog_status: pending`

### Step 3: Handle Remainders

Papers still returning 404 stay `blog_status: pending`. These need generation triggered.

## Playwright Trigger (for papers without overviews)

### Startup

Navigate to AlphaXiv to ensure logged-in browser session:
```
mcp__playwright__browser_navigate → https://alphaxiv.org
```

### List Pending Papers

```bash
python -m alphaxiv_workflow.trigger --batch
```

### Trigger Generation (per batch of 3)

```javascript
// Use waitUntil: 'load' (NOT 'networkidle' — times out on persistent connections)
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
| Exactly 3 per batch | **NEVER exceed.** Server limit: 3 parallel generations. Exceeding triggers rate-limit error. |
| Wait 3 min between batches | Generation takes ~1-2 min, wait buffer for completion |
| Retry stubborn papers | Some papers need 2-3 retriggers before generation succeeds |

### Full Workflow

1. Navigate to `https://alphaxiv.org` (ensure logged in)
2. Run `python -m alphaxiv_workflow.trigger --batch` to get batch arrays
3. Trigger exactly 3 papers, then **wait 3 minutes**
4. Run `python -m alphaxiv_workflow.backfill --workers 3` to fetch and save
5. Repeat until 0 pending

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using `networkidle` waitUntil | Always use `waitUntil: 'load'`. AlphaXiv has persistent WebSocket connections that never idle. |
| Triggering more than 3 at once | Server hard limit. Error: "You are generating blogs too quickly." |
| Not waiting between batches | Generation takes 1-2 min. Backfill will return 404 if run too early. |
| Assuming no button = broken | Paper may be transferring on AlphaXiv. Wait hours/days and retry. |

## Standard Note Structure

After import + backfill, every note should have:
```
## 摘要
## AI 摘要          (from API overview.summary)
## AI 综述 (中文)    (from API overview.overview)
## 相关引用         (from API overview.citations OR overview.overview tail)
```

## Fallback

If CLI fails, use direct Python API:
```python
from alphaxiv_workflow.backfill import scan_pending, backfill_paper
pending = scan_pending("VAULT_PATH")
for p in pending:
    backfill_paper(p, "VAULT_PATH")
```
