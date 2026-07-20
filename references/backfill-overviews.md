# Backfill Overviews

Fetch missing AI overviews from the AlphaXiv public API and update paper notes. For papers without existing overviews, use authenticated, Playwright-compatible browser automation when available.

Preserve the structure defined in [note-schema.md](note-schema.md) when replacing placeholders.

## Contents

- [Fetch process](#process)
- [Browser trigger](#browser-trigger-for-papers-without-overviews)
- [Common mistakes](#common-mistakes)
- [Fallback](#fallback)

## Process

### Step 1: Scan for Pending Papers

```bash
<PYTHON_CMD> -m alphaxiv_workflow.backfill --dry-run
```

Shows papers with `blog_status: pending` in `300 Resources/320 References/`.

### Step 2: Fetch Existing Overviews

```bash
<PYTHON_CMD> -m alphaxiv_workflow.backfill --workers 3
```

For each pending paper:
1. Gets `version_id` from AlphaXiv metadata (public API, no auth needed)
2. Fetches both `get_overview(version_id, 'zh')` and `get_overview(version_id, 'en')`
3. Prefers ZH for the detailed overview and uses EN summary data when the ZH summary is empty
4. Updates note: replaces placeholder, removes `blog_status: pending`

### Step 3: Handle Remainders

Papers still returning 404 stay `blog_status: pending`. These need generation triggered.

## Browser Trigger (for papers without overviews)

### Startup

Use an available Playwright-compatible browser tool with the user's authenticated profile. Navigate to `https://alphaxiv.org` and verify that the session is logged in before triggering generation. If no authenticated browser automation is available, preserve pending state and tell the user how to trigger the overview manually.

### List Pending Papers

```bash
<PYTHON_CMD> -m alphaxiv_workflow.trigger --batch
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
| At most 3 per batch | **NEVER exceed 3.** The server limits parallel generations; a final batch may contain 1-2 papers. |
| Wait 3 min between batches | Generation takes ~1-2 min, wait buffer for completion |
| Retry stubborn papers | Some papers need 2-3 retriggers before generation succeeds |

### Full Workflow

1. Navigate to `https://alphaxiv.org` (ensure logged in)
2. Run `<PYTHON_CMD> -m alphaxiv_workflow.trigger --batch` to get batch arrays
3. Trigger up to 3 papers, then **wait 3 minutes**
4. Run `<PYTHON_CMD> -m alphaxiv_workflow.backfill --workers 3` to fetch and save
5. Repeat until 0 pending

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using `networkidle` waitUntil | Always use `waitUntil: 'load'`. AlphaXiv has persistent WebSocket connections that never idle. |
| Triggering more than 3 at once | Server hard limit. Error: "You are generating blogs too quickly." |
| Not waiting between batches | Generation takes 1-2 min. Backfill will return 404 if run too early. |
| Assuming no button = broken | Paper may be transferring on AlphaXiv. Wait hours/days and retry. |

## Fallback

If CLI fails, use direct Python API:
```python
from alphaxiv_workflow.backfill import scan_pending, backfill_paper
pending = scan_pending("VAULT_PATH")
for p in pending:
    backfill_paper(p, "VAULT_PATH")
```
