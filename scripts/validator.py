"""
Validator - post-save validation for imported paper notes.
Checks frontmatter integrity, heading hierarchy, detects duplicates, generates tags.
"""
import os
import re
import yaml


def validate_frontmatter(filepath: str) -> dict:
    """
    Parse and validate YAML frontmatter of a saved note.
    Returns {'status': 'pass'|'block'|'warn', 'issues': [(severity, message)], 'frontmatter': {...}}
    """
    result = {'status': 'pass', 'issues': [], 'frontmatter': {}}
    if not os.path.exists(filepath):
        result['status'] = 'block'
        result['issues'].append(('block', f'File not found: {filepath}'))
        return result

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not fm_match:
        result['status'] = 'block'
        result['issues'].append(('block', 'No valid YAML frontmatter found'))
        return result

    try:
        fm = yaml.safe_load(fm_match.group(1))
        result['frontmatter'] = fm or {}
    except yaml.YAMLError as e:
        result['status'] = 'block'
        result['issues'].append(('block', f'YAML parse error: {e}'))
        return result

    # BLOCK checks
    if not fm.get('title'):
        result['issues'].append(('block', 'Missing required field: title'))
    if not fm.get('arxiv_id'):
        result['issues'].append(('block', 'Missing required field: arxiv_id'))

    # WARN checks
    if not fm.get('authors'):
        result['issues'].append(('warn', 'Empty author list'))
    tags = fm.get('tags', [])
    if len(tags) < 5:
        result['issues'].append(('warn', f'Only {len(tags)} tags (recommended >= 5)'))

    # INFO checks — publication metadata (desirable but not required)
    if not fm.get('published_venue'):
        result['issues'].append(('info', 'No published_venue — formal publication venue unknown'))
    if not fm.get('published_date'):
        result['issues'].append(('info', 'No published_date — formal publication date unknown'))

    has_block = any(sev == 'block' for sev, _ in result['issues'])
    has_warn = any(sev == 'warn' for sev, _ in result['issues'])
    if has_block:
        result['status'] = 'block'
    elif has_warn:
        result['status'] = 'warn'

    return result


def check_duplicates(arxiv_id: str, vault_path: str) -> list:
    """Check if paper with same arXiv ID already exists. Returns list of matching paths."""
    papers_dir = os.path.join(vault_path, '300 Resources', '320 References')
    if not os.path.exists(papers_dir):
        return []
    duplicates = []
    for f in os.listdir(papers_dir):
        if not f.endswith('.md'):
            continue
        fpath = os.path.join(papers_dir, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                head = fh.read(8000)
            fm_match = re.match(r'^---\s*\n(.*?)\n---', head, re.DOTALL)
            if fm_match:
                fm = yaml.safe_load(fm_match.group(1))
                if fm and fm.get('arxiv_id') == arxiv_id:
                    duplicates.append(fpath)
        except Exception:
            pass
    return duplicates


def read_note_content(filepath: str) -> dict:
    """Read a saved note, extract title/abstract/overview for tag generation."""
    result = {'title': '', 'abstract': '', 'overview': ''}
    if not os.path.exists(filepath):
        return result
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        try:
            fm = yaml.safe_load(fm_match.group(1))
            if fm:
                result['title'] = fm.get('title', '')
        except yaml.YAMLError:
            pass

    abstract_match = re.search(r'## 摘要\s*\n\n(.*?)(?:\n---|\n##)', content, re.DOTALL)
    if abstract_match:
        result['abstract'] = abstract_match.group(1).strip()

    overview_match = re.search(r'## AI 综述.*?\n\n(.*?)(?:\n---|\n## 相关)', content, re.DOTALL)
    if overview_match:
        result['overview'] = overview_match.group(1).strip()[:2000]

    return result


def check_heading_hierarchy(filepath: str) -> dict:
    """
    Validate markdown heading hierarchy in a paper note.

    Checks:
    - Exactly one H1 (# title)
    - No skipped heading levels (e.g., ## -> #### without ###)
    - Max depth H4 (##### and deeper flagged)
    - Required H2 sections present (摘要 + AI section)

    Returns {'status': 'pass'|'warn'|'block', 'issues': [(severity, message)]}
    """
    result = {'status': 'pass', 'issues': []}

    if not os.path.exists(filepath):
        result['status'] = 'block'
        result['issues'].append(('block', f'File not found: {filepath}'))
        return result

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Skip frontmatter (body starts after second ---)
    fm_end = 0
    fm_match = re.match(r'^---\s*\n.*?\n---', content, re.DOTALL)
    if fm_match:
        fm_end = fm_match.end()

    body = content[fm_end:]

    # Strip fenced code blocks to avoid false positives
    body = re.sub(r'```[^\n]*\n.*?```', '', body, flags=re.DOTALL)

    # Extract headings: (#+ ) Title
    heading_matches = re.findall(r'^(#{1,6})\s+(.+)', body, re.MULTILINE)
    if not heading_matches:
        result['status'] = 'block'
        result['issues'].append(('block', 'No headings found in note body'))
        return result

    levels = [len(m[0]) for m in heading_matches]
    titles = [m[1].strip() for m in heading_matches]

    # --- Check 1: Exactly one H1 ---
    h1_count = sum(1 for l in levels if l == 1)
    if h1_count == 0:
        result['issues'].append(('block', 'No H1 (# title) heading found'))
    elif h1_count > 1:
        h1_titles = [t for l, t in zip(levels, titles) if l == 1]
        result['issues'].append(('block',
            f'Multiple H1 headings ({h1_count}): {", ".join(h1_titles)}'))

    # --- Check 2: No skipped heading levels ---
    for i in range(1, len(levels)):
        if levels[i] > levels[i - 1] + 1:
            result['issues'].append(('warn',
                f'Heading level skip: H{levels[i-1]} "{titles[i-1][:50]}" '
                f'-> H{levels[i]} "{titles[i][:50]}" '
                f'(skipped H{levels[i-1]+1})'))

    # --- Check 3: Max depth H4 ---
    deep = [(l, t) for l, t in zip(levels, titles) if l >= 5]
    for l, t in deep:
        result['issues'].append(('warn', f'Heading too deep (H{l}): "{t[:50]}"'))

    # --- Check 4: Required H2 sections (BLOCK — all 4 mandatory) ---
    h2_titles = [t for l, t in zip(levels, titles) if l == 2]
    required_h2 = ['摘要', 'AI 摘要', 'AI 综述 (中文)', '相关引用']
    for req in required_h2:
        found = any(req == t for t in h2_titles)
        if not found:
            result['issues'].append(('block',
                f'Missing required H2 section: ## {req}'))

    # --- Check 5: 相关引用 must be H2 ---
    citation_headings = [(l, t) for l, t in zip(levels, titles)
                         if '相关引用' in t]
    for l, t in citation_headings:
        if l != 2:
            result['issues'].append(('warn',
                f'"相关引用" should be H2, but is H{l}: "{t[:50]}"'))

    # Determine status
    has_block = any(sev == 'block' for sev, _ in result['issues'])
    has_warn = any(sev == 'warn' for sev, _ in result['issues'])
    if has_block:
        result['status'] = 'block'
    elif has_warn:
        result['status'] = 'warn'

    return result


def merge_tags(filepath: str, new_tags: list) -> bool:
    """Merge new tags into note's frontmatter. Dedup, preserve order. Returns True if updated."""
    if not os.path.exists(filepath):
        return False
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not fm_match:
        return False
    try:
        fm = yaml.safe_load(fm_match.group(1))
    except yaml.YAMLError:
        return False

    existing = fm.get('tags', []) or []

    # Handle quoted-string contamination (unify_structure.py bug from pre-2026-06-08):
    # tags: "[paper, ai]" was written as a YAML string instead of a list.
    # yaml.safe_load parses this as a single string "[paper, ai]" instead of ['paper', 'ai'].
    if isinstance(existing, str) and existing.startswith('[') and existing.endswith(']'):
        existing = [t.strip().strip('"').strip("'") for t in existing[1:-1].split(',')]
        existing = [t for t in existing if t]

    if not isinstance(existing, list):
        existing = [existing] if existing else []

    merged= list(dict.fromkeys(existing + new_tags))
    if merged == existing:
        return False

    # Always write block list format (most Obsidian-compatible)
    indent = '  '
    tag_lines = '\n'.join(f'{indent}- {t}' for t in merged)
    updated = re.sub(
        r'(^tags:)[\s\S]*?(?=^\w|\Z)',
        rf'\1\n{tag_lines}',
        content, count=1, flags=re.MULTILINE
    )
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(updated)
    return True
