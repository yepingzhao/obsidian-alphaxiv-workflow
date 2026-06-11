---
name: 04-literature-synthesis
description: Use when user wants to analyze, summarize, or synthesize saved paper notes in the Obsidian vault by topic or author. Triggered by "analyze" sub-command or explicit literature review requests.
---

# Literature Synthesis (Gate 4)

Search, synthesize, and iteratively refine literature reviews using LLM generation.
Outputs structured synthesis notes to `200 Areas/深度学习/`.

## Process

### Step 1: Determine Mode

| Input | Mode | CLI |
|-------|------|-----|
| `analyze "topic"` | Topic | `python -m alphaxiv_workflow.synthesis topic "TOPIC" "VAULT"` |
| `analyze author "name"` | Author | `python -m alphaxiv_workflow.synthesis author "NAME" "VAULT"` |

### Step 2: Search Vault

```bash
python -m alphaxiv_workflow.synthesis topic "TOPIC" "VAULT_PATH"
```

Outputs found papers with relevance markers (high/medium/low). Results sorted by relevance.

### Step 3: Confirm

Present found papers to user:
```
Found N papers for "query":
1. [arxiv_id] Title (high)
2. [arxiv_id] Title (medium)
3. [arxiv_id] Title (low) [weak]

Proceed with synthesis? (y/n, or exclude specific numbers: "y -3,-5")
```

User can exclude weak-relevance papers before synthesis.

### Step 4: Generate Synthesis

Build the prompt and scaffold note:
```python
from alphaxiv_workflow.synthesis import build_synthesis_prompt, build_synthesis_note, extract_paper_summary

for p in papers:
    p['summary'] = extract_paper_summary(p['filepath'])

prompt = build_synthesis_prompt('TOPIC', papers, 'topic')
content, filepath = build_synthesis_note('TOPIC', papers, 'topic', 'VAULT_PATH')
# Save scaffold, then pass prompt to Claude for five-chapter generation
```

### Step 5: LLM Synthesis Generation

Pass `prompt` to Claude inline. Claude generates five chapters in Chinese with wikilink citations:
1. **方法分类与对比** — Group by approach, compare strengths/weaknesses
2. **演进脉络** — Timeline of breakthroughs, inheritance relationships
3. **共识与矛盾** — Community consensus + remaining disputes
4. **空白与机会** — Open problems, future directions
5. **关键论文推荐** — 3-5 must-read papers with rationale

Insert generated content at `<!-- LLM_SYNTHESIS_PLACEHOLDER -->` marker.

### Step 6: Iterative Refinement

After initial generation, present for user feedback. Supported commands:
- Natural language: "方法对比太浅，每组的优缺点写详细些" → Claude rewrites relevant chapter
- `重写 三` → Regenerate chapter 3
- `深入 二` → Expand chapter 2
- `精简` → Condense to key points
- `保存` / `done` → Write final version

After each iteration: show only changed chapters (diff style). Max 3 rounds — after 3, prompt "已迭代3轮，建议保存后手动精修" and save.

### Quick Mode

`analyze "topic" --quick` skips confirmation and iteration — generate, save, done.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Excluding pending papers | `blog_status: pending` papers should be included with `⚠️` warning marker |
| Treating all papers as equally relevant | Low-relevance papers get `[弱相关]` marker — let user decide |
| Generating without user confirmation | Always confirm paper selection first (unless `--quick`) |
| Forgetting to replace placeholder | After LLM generation, replace `<!-- LLM_SYNTHESIS_PLACEHOLDER -->` with content |

## Rules

- LLM generation uses the prompt from `build_synthesis_prompt()`
- All citations use `[[wikilink]]` format
- Chinese output, technical terms in English
- Iteration capped at 3 rounds
- `blog_status: pending` papers included with warning marker

## Fallback

If CLI fails, use direct Python API:
```python
from alphaxiv_workflow.synthesis import find_notes_by_topic, find_notes_by_author
papers = find_notes_by_topic("TOPIC", "VAULT_PATH")
```
