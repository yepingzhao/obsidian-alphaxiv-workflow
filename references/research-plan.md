# Research Plan (Gate 6)

Develop a research direction from saved evidence, confirm the evidence set, brainstorm interactively, and save only a user-approved plan.

Use vault file operations and LLM reasoning. Do not call the AlphaXiv API in this gate.

## Contents

- [Resolve scope](#1-resolve-scope)
- [Search the vault](#2-search-the-vault)
- [Confirm evidence](#3-confirm-the-evidence-set)
- [Brainstorm](#4-brainstorm-interactively)
- [Interaction commands](#5-handle-interaction-commands)
- [Draft and refine](#6-draft-and-refine)
- [Save safely](#7-save-safely)
- [Failure handling](#failure-handling)

## 1. Resolve Scope

Search only `300 Resources/320 References/` unless the user explicitly expands the scope. Resolve the vault as specified by the root skill.

Extract 5-10 Chinese and English search terms from:

- domain;
- task;
- method family;
- datasets or evaluation setting;
- constraints such as latency, data, compute, or deployment.

If the request is broad, start searching with reasonable terms and ask a focusing question after presenting evidence instead of blocking before search.

## 2. Search the Vault

Use available filesystem tools; prefer `rg`/`rg --files` when a shell is available. Search in this order:

1. frontmatter tags and filenames;
2. `### AI 摘要` and `## AI 综述 (中文)`;
3. `## 摘要` as fallback.

Use two-stage retrieval instead of opening every note. Collect filenames and match counts first, then read the strongest candidates. If more than 50 files match, refine with the highest-precision terms or ask one narrowing question; do not silently scan the entire vault. Inspect up to 20 candidates before presenting the first evidence set, and disclose when additional matches remain.

Do not infer relevance from a filename alone. Read enough of every candidate to extract:

- `arxiv_id`, title, first author, and year;
- tags and `blog_status`;
- method, result, and limitation relevant to the requested direction;
- one-sentence relevance justification.

Score each paper:

- **high**: directly studies the target task or method;
- **medium**: supplies an adjacent method, dataset, or transferable idea;
- **low**: only tangentially mentions the topic;
- **pending**: lacks an overview; use its abstract and lower confidence accordingly.

## 3. Confirm the Evidence Set

Present candidates grouped by relevance with one stable number per paper. Support:

| Input | Action |
|---|---|
| `y` | Use all displayed papers |
| `high` | Use high-relevance papers only |
| `1,2,5` | Use only listed papers |
| `y -3,-5` | Exclude listed papers |
| `add <keyword>` | Search another round and retain prior selections |

Do not draft before the user confirms the evidence set. If no papers match, suggest broader terms or the root `import` workflow.

## 4. Brainstorm Interactively

Act as a research partner, not a summarizer. Complete at least two focusing rounds unless the user already supplied a precise question, method, baselines, and constraints.

### Round A: Map the Landscape

Present:

- method families with representative wikilinks;
- findings shared across multiple papers;
- disagreements or unresolved limitations;
- cross-domain transfer opportunities;
- evidence gaps caused by pending or missing papers.

Ask one specific focusing question with 2-4 materially different options.

### Round B: Deepen One Direction

For the chosen direction, present:

- the most relevant papers and their exact limitations;
- low-risk, solid, and high-risk contribution paths;
- the proposed causal mechanism or design rationale;
- alternatives rejected and why;
- a preliminary data, compute, and implementation assessment.

Ask one question that resolves the largest remaining design choice.

### Round C: Check Feasibility

Before drafting, identify:

- datasets, splits, baselines, and primary metrics;
- the minimum experiment that could falsify the idea;
- required ablations;
- compute and time estimates with assumptions;
- likely failure modes and a concrete fallback.

Do not invent SOTA values, paper results, dataset properties, or resource estimates. Cite facts from selected notes. Mark estimates as estimates. If recent competition matters, verify it with an available current literature-search capability; otherwise label the analysis as vault-limited.

## 5. Handle Interaction Commands

| Command | Action |
|---|---|
| `深入 <aspect>` | Analyze one gap, mechanism, or experiment more deeply |
| `换个角度` | Reframe the same evidence set |
| `补充文献 <keyword>` | Search and reconfirm added papers |
| `挑战` | Attack the current direction with counterarguments and failure cases |
| `回到上一步` | Restore the prior decision point |
| `起草计划` / `draft` / `写出来吧` | Move to drafting |

Continue brainstorming until the user signals readiness. Preserve prior decisions so a pivot does not silently erase constraints.

## 6. Draft and Refine

Read [research-plan-output.md](research-plan-output.md) now; do not load it during search or early brainstorming.

Draft in Chinese, retaining English method, metric, and dataset names. Apply these rules:

- cite every claim about prior work with an absolute vault-root wikilink;
- make each novelty claim specific and falsifiable;
- distinguish sourced facts, inferences, and estimates;
- define in-scope and out-of-scope work;
- connect each ablation to the design choice it isolates;
- mark immature sections `*(初稿，待细化)*` instead of filling them with generic prose.

Present the draft without saving. Support natural-language feedback plus `重写 <section>`, `深入 <section>`, `精简`, `补充 <aspect>`, and `回到头脑风暴`.

After each revision, summarize only the affected sections. After three revision rounds, ask whether to save, continue, or return to brainstorming; do not silently stop or auto-save.

## 7. Save Safely

Save only after explicit approval:

- plan: `100 Projects/研究计划合集/{研究方向}.md`;
- index: `100 Projects/研究计划合集/研究计划合集.md`;
- optional transcript: `100 Projects/研究计划合集/对话记录/{研究方向}-对话.md`.

Sanitize the filename and check for an existing plan. Ask before overwriting. Update the existing index row rather than appending a duplicate. Save the transcript only when the user opts in.

Report the exact saved paths and whether the transcript was saved.

## Failure Handling

- If the vault path is missing, stop before writes and request the correct path.
- If reading one note fails, report it and continue with the remaining confirmed set only after disclosing the omission.
- If the evidence is too weak for a defensible plan, produce a literature-acquisition plan instead of fabricating a research contribution.
