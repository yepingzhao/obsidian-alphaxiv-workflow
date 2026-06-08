---
name: literature-synthesis
description: Use when user wants to analyze, summarize, or synthesize saved paper notes in the Obsidian vault by topic or author. Triggered by analyze sub-command or explicit literature review requests.
---

# Literature Synthesis (Gate 4)

Search, synthesize, and iteratively refine literature reviews using LLM generation.
Outputs structured synthesis notes to `200 Areas/深度学习/`.

All commands run from the `scripts/` directory: `cd scripts`

## Process

### Step 1: Determine Mode

| Input | Mode | Function |
|-------|------|----------|
| `analyze "topic"` | Topic | `find_notes_by_topic(topic, vault)` |
| `analyze author "name"` | Author | `find_notes_by_author(author, vault)` |

### Step 2: Search Vault

```bash
python -c "
from literature_analyzer import find_notes_by_topic
papers = find_notes_by_topic('TOPIC', 'VAULT_PATH')
print(f'Found {len(papers)} papers')
for p in papers:
    rel = p.get('relevance', '?')
    mark = ' [弱相关]' if rel == 'low' else ''
    print(f'  - [{p[\"arxiv_id\"]}] {p[\"title\"]} ({rel}){mark}')
"
```

For author mode: `find_notes_by_author('NAME', 'VAULT_PATH')`.

Results are sorted by relevance (high → medium → low).

### Step 3: Confirm

Present found papers with relevance markers:

```
Found N papers for "query":
1. [arxiv_id] Title (high)
2. [arxiv_id] Title (medium)
3. [arxiv_id] Title (low) [弱相关]

Proceed with synthesis? (y/n, or exclude specific numbers: "y -3,-5")
```

User can exclude weak-relevance papers before synthesis.

### Step 4: Generate Synthesis Note

```bash
python -c "
from literature_analyzer import build_synthesis_note, build_synthesis_prompt, extract_paper_summary

# Enrich papers with extracted summaries
for p in papers:
    p['summary'] = extract_paper_summary(p['filepath'])

prompt = build_synthesis_prompt('TOPIC', papers, 'topic')
# Prompt is now ready for Claude to generate the five-chapter synthesis
# Save the scaffold note first
content, filepath = build_synthesis_note('TOPIC', papers, 'topic', 'VAULT_PATH')
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'Scaffold saved: {filepath}')
print(f'Prompt ready ({len(prompt)} chars)')
"
```

### Step 5: LLM Synthesis Generation

Pass `prompt` to Claude inline. Claude generates the five-chapter synthesis in Chinese with wikilink citations.

**Five chapters:**
1. **方法分类与对比** — Group by approach/sub-domain, compare strengths/weaknesses
2. **演进脉络** — Timeline of breakthroughs, inheritance relationships
3. **共识与矛盾** — Community consensus + remaining disputes
4. **空白与机会** — Open problems (explicit from papers vs inferred), future directions
5. **关键论文推荐** — 3-5 must-read papers with rationale

**Output:** After Claude generates the synthesis, insert it into the scaffold note at the `<!-- LLM_SYNTHESIS_PLACEHOLDER -->` marker and save.

### Step 6: Iterative Refinement

After initial generation, present the synthesis for user feedback.

**Supported commands:**
- Natural language: "方法对比太浅，每组的优缺点写详细些" → Claude rewrites the relevant chapter
- `重写 三` → Regenerate chapter 3
- `深入 二` → Expand chapter 2 with more detail
- `精简` → Condense all chapters to key points
- `保存` / `done` → Write final version and save

**After each iteration:** Show only the changed chapter(s) (diff style), not the full text.
**Maximum 3 rounds** — after 3 rounds, prompt "已迭代3轮，建议保存后手动精修" and save.

### Step 7: Save Final

Replace the `<!-- LLM_SYNTHESIS_PLACEHOLDER -->` in the note with the final LLM-generated synthesis content.

## Quick Mode

Use `analyze "topic" --quick` to skip the confirmation and iteration steps — generate, save, done.

## Output

Saved to `200 Areas/深度学习/{topic}_文献综述.md` or `{author}_文献分析.md`.

## Rules

- Always confirm paper selection before generating (unless `--quick`)
- LLM generation uses the prompt from `build_synthesis_prompt()`
- All citations use `[[wikilink]]` format
- Chinese output, technical terms in English
- Iteration capped at 3 rounds
- `blog_status: pending` papers included with warning marker
