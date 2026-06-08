---
name: literature-synthesis
description: Use when user wants to analyze, summarize, or synthesize saved paper notes in the Obsidian vault by topic or author. Triggered by analyze sub-command or explicit literature review requests.
---

# Literature Synthesis (Gate 4)

Search and synthesize saved paper notes from the vault. Outputs structured synthesis notes to `200 Areas/深度学习/`.

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
for p in papers: print(f'  - [{p[\"arxiv_id\"]}] {p[\"title\"]}')
"
```

For author mode: `find_notes_by_author('NAME', 'VAULT_PATH')`

### Step 3: Confirm

Present found papers and confirm before generating:

```
Found N papers for "query":
1. [arxiv_id] Title (authors)

Proceed with synthesis?
```

### Step 4: Generate Synthesis Note

```bash
python -c "

from literature_analyzer import build_synthesis_note
content, filepath = build_synthesis_note('TOPIC', papers, 'topic', 'VAULT_PATH')
with open(filepath, 'w', encoding='utf-8') as f: f.write(content)
print(f'Saved: {filepath}')
"
```

## Output

Saved to `200 Areas/深度学习/{topic}_文献综述.md` or `{author}_文献分析.md`.

Structure:
- YAML frontmatter with source links to original papers
- Paper list with wikilinks
- Per-paper analysis (abstract + key insights extracted from saved notes)
- Cross-reference section placeholder for manual completion

## Rules

- Always confirm with user before generating
- Extract abstracts/insights automatically from existing notes
- Cross-reference section is manually completed later
- If 0 papers found, suggest checking topic/author spelling
