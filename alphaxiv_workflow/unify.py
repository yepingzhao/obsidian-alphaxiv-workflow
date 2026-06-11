"""
Unify YAML frontmatter and H2 headings across all paper notes.
Phase 1: Fetch missing version IDs from AlphaXiv API
Phase 2: Normalize frontmatter field order + H2 structure
"""
import os, re, time
from collections import OrderedDict

from .api import get_paper_metadata

from .config import PAPERS_DIR
PAPERS = PAPERS_DIR

REQUIRED = ['title', 'arxiv_id', 'version', 'date', 'tags', 'source', 'authors', 'aliases', 'created']
REMOVE = ['published_year', 'oral_spotlight', 'eii', 'pku', 'cssci', 'cscd', 'custom_ranks']
# Fields that must always be quoted strings, even if value looks numeric
ALWAYS_QUOTE = {'arxiv_id', 'version'}


def fetch_versions():
    """Phase 1: Add version_id for notes missing it."""
    missing = []
    for f in sorted(os.listdir(PAPERS)):
        if not f.endswith('.md'): continue
        fp = os.path.join(PAPERS, f)
        with open(fp, 'r', encoding='utf-8') as fh:
            content = fh.read(5000)
        fm_end = content.find('---', 4)
        if fm_end < 0: continue
        if 'version:' not in content[:fm_end]:
            m = re.search(r'arxiv_id:\s*"(.+?)"', content)
            if m: missing.append((fp, m.group(1)))

    print(f'Missing version: {len(missing)}')
    for i, (fp, aid) in enumerate(missing, 1):
        try:
            meta = get_paper_metadata(aid)
            vid = meta.version_id if hasattr(meta, 'version_id') else ''
            if vid:
                with open(fp, 'r', encoding='utf-8') as fh:
                    c = fh.read()
                c = re.sub(r'(arxiv_id:\s*".+?")\n', f'\\1\nversion: "{vid}"\n', c, count=1)
                with open(fp, 'w', encoding='utf-8') as fh:
                    fh.write(c)
                print(f'  [{i}/{len(missing)}] ✅ {aid}')
            else:
                print(f'  [{i}/{len(missing)}] ⚠️ {aid}: no version')
        except Exception as e:
            print(f'  [{i}/{len(missing)}] ❌ {aid}: {e}')
        time.sleep(0.3)
    print()


def normalize_note(fp):
    """Phase 2: Normalize a single note. Returns True if changed."""
    with open(fp, 'r', encoding='utf-8') as fh:
        content = fh.read()

    fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not fm_match: return False

    fm_text = fm_match.group(1)
    body = content[fm_match.end():]
    changed = False

    # ── Parse frontmatter ──
    lines = fm_text.split('\n')
    fields = OrderedDict()
    cur_key = None
    buf = []

    for line in lines:
        kv = re.match(r'^(\w[\w-]*):\s*(.*)', line)
        li = re.match(r'^\s+-\s+(.+)', line)
        if kv:
            if cur_key and buf: fields[cur_key] = buf; buf = []
            cur_key, val = kv.group(1), kv.group(2).strip()
            # Detect inline YAML list: tags: [a, b, c] or tags: "[a, b, c]"
            inline_list = re.match(r'^"?\[(.+)\]"?$', val)
            if inline_list and val != '[]':
                items = [v.strip().strip('"').strip("'") for v in inline_list.group(1).split(',')]
                fields[cur_key] = [v for v in items if v]
            else:
                fields[cur_key] = val if val and val != '[]' else None
        elif li and cur_key:
            buf.append(li.group(1).strip())

    if cur_key and buf: fields[cur_key] = buf

    # ── Strip existing quotes from scalar values ──
    for k, v in fields.items():
        if isinstance(v, str):
            while (v.startswith('"') and v.endswith('"')) or \
                  (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            fields[k] = v

    # ── Clean: remove unwanted fields ──
    for fk in REMOVE:
        if fk in fields: del fields[fk]; changed = True

    # ── Reorder ──
    new = OrderedDict()
    for fk in REQUIRED:
        if fk in fields: new[fk] = fields.pop(fk)
    for fk in list(fields.keys()):
        new[fk] = fields[fk]

    # ── Rebuild frontmatter ──
    fm_lines = []
    for k, v in new.items():
        if isinstance(v, list):
            fm_lines.append(f'{k}:')
            for item in v: fm_lines.append(f'  - {item}')
        elif v is not None:
            if k not in ALWAYS_QUOTE and (v.lower() in ('true', 'false') or v.replace('.','').replace('-','').replace('/','').isdigit()):
                fm_lines.append(f'{k}: {v}')
            else:
                fm_lines.append(f'{k}: "{v}"')
    new_fm = '\n'.join(fm_lines)
    if new_fm != fm_text: changed = True

    # ── H2 ordering: ensure ## AI 摘要 is before ## AI 综述 (中文) ──
    # These are distinct sections: AI 摘要 = structured summary, AI 综述 = narrative overview.
    # They must NOT be merged. Only reorder if AI 摘要 appears after AI 综述.
    if '## AI 摘要' in body and '## AI 综述 (中文)' in body:
        ai_summary = re.search(r'\n## AI 摘要\n.*?(?=\n## |\Z)', body, re.DOTALL)
        ai_review = re.search(r'\n## AI 综述 \(中文\).*?(?=\n## |\Z)', body, re.DOTALL)
        if ai_summary and ai_review and ai_summary.start() > ai_review.start():
            # AI 摘要 is AFTER AI 综述 — swap them
            summary_text = ai_summary.group()
            review_text = ai_review.group()
            body = body[:ai_review.start()] + summary_text + '\n\n---\n\n' + review_text.strip() + body[ai_summary.end():]
            changed = True

    # ── H2: Remove blog_status:pending if overview has content ──
    if 'blog_status: pending' in new_fm and '## AI 综述 (中文)' in body:
        ovm = re.search(r'## AI 综述 \(中文\).*?\n\n(.+?)(?=\n---|\n## |\Z)', body, re.DOTALL)
        if ovm and len(ovm.group(1).strip()) > 100:
            new_fm = re.sub(r'\nblog_status:\s*pending', '', '\n' + new_fm)
            changed = True

    if not changed: return False

    final = f'---\n{new_fm}\n---{body}'
    with open(fp, 'w', encoding='utf-8') as fh:
        fh.write(final)
    return True


def normalize_all():
    total = changed = 0
    for f in sorted(os.listdir(PAPERS)):
        if not f.endswith('.md'): continue
        total += 1
        if normalize_note(os.path.join(PAPERS, f)): changed += 1
    print(f'Phase 2: {changed}/{total} notes normalized')
    return changed


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--phase', choices=['1','2','all'], default='all')
    args = p.parse_args()

    if args.phase in ('1', 'all'): fetch_versions()
    if args.phase in ('2', 'all'): normalize_all()
    print('Done!')
