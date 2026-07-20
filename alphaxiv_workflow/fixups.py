"""Paper fixup utilities: add missing sections, fix YAML quotes, fix placeholder citations."""
import os
import re
import sys
import time
import argparse

from .config import VAULT_PATH, PAPERS_DIR
from .api import get_paper_metadata, get_overview


# ── Helpers ──

def _build_ai_summary(summary_data: dict) -> str:
    if not summary_data: return None
    field_order = [
        ('summary', '摘要'), ('key_insights', '要点'),
        ('original_problem', '问题'), ('solution', '方法'), ('results', '结果'),
    ]
    parts = []
    for field, label in field_order:
        val = summary_data.get(field, [])
        if isinstance(val, list): val = [v for v in val if v]
        if not val: continue
        parts.append(f'### {label}')
        for item in (val if isinstance(val, list) else [str(val)]):
            parts.append(f'- {item}')
        parts.append('')
    return '\n'.join(parts).strip() if parts else None


def _build_citations(citations: list) -> str:
    if not citations: return None
    if len(citations) == 1 and isinstance(citations[0], dict) and 'raw' in citations[0]:
        return citations[0]['raw']
    lines = []
    for i, c in enumerate(citations, 1):
        title = c.get('title', 'Untitled') if isinstance(c, dict) else getattr(c, 'title', 'Untitled')
        link = (c.get('alphaxiv_link', '') if isinstance(c, dict) else getattr(c, 'alphaxiv_link', ''))
        link = link.replace('/paper/', '/abs/') if link else ''
        justification = c.get('justification', '') if isinstance(c, dict) else getattr(c, 'justification', '')
        lines.append(f'{i}. **{title}**')
        if link: lines.append(f'   - [AlphaXiv]({link})')
        if justification: lines.append(f'   - {justification}')
        lines.append('')
    return '\n'.join(lines).strip() if lines else None


def _extract_embedded_citations(overview_text: str) -> str:
    """Extract citation CONTENT only (strip the heading)."""
    m = re.search(
        r'#{1,}\s*(?:相关引[用文]|Reference|参考文献?)\s*\n(.*?)\Z',
        overview_text, re.DOTALL)
    if m and len(m.group(1).strip()) > 20:
        raw = m.group(1).strip()
        raw = re.sub(r'^\[本节.*?\]\s*\n*', '', raw)
        return raw
    return None


def _resolve_papers_dir(vault_path):
    if vault_path:
        return os.path.join(vault_path, '300 Resources', '320 References')
    return PAPERS_DIR


# ── Public functions ──

def add_missing_sections(vault_path: str = None):
    """Add missing ### AI 摘要 and ## 相关引用 sections from AlphaXiv API."""
    papers = _resolve_papers_dir(vault_path)
    results = []
    for f in sorted(os.listdir(papers)):
        if not f.endswith('.md'): continue
        fp = os.path.join(papers, f)
        with open(fp, 'r', encoding='utf-8') as fh:
            content = fh.read()
        has_ai_summary = bool(re.search(
            r'^#{2,3}\s+(?:AI 摘要|摘要|核心总结)\s*$', content, re.MULTILINE))
        needs_summary = not has_ai_summary
        needs_cit = '## 相关引用\n' not in content
        if not needs_summary and not needs_cit: continue
        aid_m = re.search(r'arxiv_id:\s*"(.+?)"', content[:500])
        if aid_m: results.append({'fp': fp, 'aid': aid_m.group(1), 'ns': needs_summary, 'nc': needs_cit})

    if not results: print('All notes complete!'); return
    n_sum = sum(1 for r in results if r['ns'])
    n_cit = sum(1 for r in results if r['nc'])
    print(f'Need AI 摘要: {n_sum} | Need 相关引用: {n_cit} | Total: {len(results)}\n')

    ai_ok = cit_ok = ai_pl = cit_pl = 0
    for i, r in enumerate(results, 1):
        aid, fp = r['aid'], r['fp']
        try:
            meta = get_paper_metadata(aid)
            vid = meta.version_id if hasattr(meta, 'version_id') else ''
            if not vid: print(f'  [{i}/{len(results)}] ⚠️ {aid}: no vid'); continue
            zh = get_overview(vid, 'zh')
            en = get_overview(vid, 'en') if not zh else None
            d = zh.model_dump() if zh else (en.model_dump() if en else {})
            if not d: print(f'  [{i}/{len(results)}] ⚠️ {aid}: no data'); continue

            summary = d.get('summary', {})
            citations = d.get('citations', [])
            if not citations:
                ov_text = d.get('overview', '')
                cit_match = re.search(
                    r'#{1,}\s*(?:相关引[用文]|Reference|参考文献?)\s*\n(.*?)\Z',
                    ov_text, re.DOTALL | re.MULTILINE)
                if cit_match:
                    raw_cit = cit_match.group(1).strip()
                    citations = [{'title': 'Embedded citation block', 'raw': raw_cit}]

            with open(fp, 'r', encoding='utf-8') as fh:
                content = fh.read()

            if r['ns']:
                ai = _build_ai_summary(summary)
                ins = content.find('\n---\n', content.find('## 摘要'))
                if ins > 0:
                    end = ins + 5
                    sec = f'\n### AI 摘要\n\n{ai}\n' if ai else '\n### AI 摘要\n\n*暂无 AI 摘要数据*\n'
                    content = content[:end] + sec + '\n---\n' + content[end:]
                    if ai: ai_ok += 1
                    else: ai_pl += 1

            if r['nc']:
                cit = _build_citations(citations)
                ovm = re.search(r'## AI 综述 \(中文\).*?\n---\n', content, re.DOTALL)
                if ovm:
                    ins = ovm.end()
                    sec = f'\n## 相关引用\n\n{cit}\n' if cit else '\n## 相关引用\n\n*暂无相关引用*\n'
                    content = content[:ins] + sec + '\n---\n' + content[ins:]
                    if cit: cit_ok += 1
                    else: cit_pl += 1

            with open(fp, 'w', encoding='utf-8') as fh:
                fh.write(content)

            tags = []
            if r['ns'] and ai: tags.append('摘要')
            if r['nc'] and cit: tags.append('引用')
            print(f'  [{i}/{len(results)}] ✅ {aid} ({", ".join(tags) if tags else "placeholder"})')
        except Exception as e:
            print(f'  [{i}/{len(results)}] ❌ {aid}: {str(e)[:80]}')
        time.sleep(0.3)

    print(f'\nAI 摘要: {ai_ok} data + {ai_pl} placeholder')
    print(f'相关引用: {cit_ok} data + {cit_pl} placeholder')


def fix_quotes(vault_path: str = None):
    """Fix malformed YAML quotes in paper notes."""
    papers = _resolve_papers_dir(vault_path)
    unquoted = ['date', 'tags', 'sci_cas_top', 'utd24', 'ft50']
    bools = {'true', 'false'}

    def _clean_value(field: str, raw: str) -> str:
        val = raw.strip()
        while (val.startswith('"') and val.endswith('"')) or \
              (val.startswith("'") and val.endswith("'")):
            val = val[1:-1].strip()
        if field in unquoted:
            return val
        if val.lower() in bools:
            return val
        if field == 'tags':
            return val
        return f'"{val}"'

    total = fixed = 0
    for f in sorted(os.listdir(papers)):
        if not f.endswith('.md'): continue
        fp = os.path.join(papers, f)
        total += 1
        with open(fp, 'r', encoding='utf-8') as fh:
            content = fh.read()
        fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
        if not fm_match:
            print(f'SKIP {f}: no frontmatter')
            continue
        fm_text = fm_match.group(1)
        body = content[fm_match.end():]
        original = fm_text
        lines = fm_text.split('\n')
        new_lines = []
        cur_key = None
        for line in lines:
            kv = re.match(r'^(\w[\w-]*):\s*(.*)', line)
            li = re.match(r'^\s+-\s+(.+)', line)
            if kv:
                cur_key = kv.group(1)
                if kv.group(2).strip():
                    new_lines.append(f'{cur_key}: {_clean_value(cur_key, kv.group(2))}')
                else:
                    new_lines.append(f'{cur_key}:')
            elif li and cur_key:
                new_lines.append(line)
            else:
                new_lines.append(line)
        new_fm = '\n'.join(new_lines)
        if new_fm == original:
            continue
        final = f'---\n{new_fm}\n---{body}'
        with open(fp, 'w', encoding='utf-8') as fh:
            fh.write(final)
        fixed += 1
    print(f'Fixed: {fixed}/{total} notes')


def fix_placeholder_citations(vault_path: str = None):
    """Replace *暂无相关引用* placeholders with real citations."""
    papers = _resolve_papers_dir(vault_path)
    fix_list = []
    for f in sorted(os.listdir(papers)):
        if not f.endswith('.md'): continue
        fp = os.path.join(papers, f)
        with open(fp, 'r', encoding='utf-8') as fh:
            c = fh.read()
        if '暂无相关引用' not in c: continue
        aid_m = re.search(r'arxiv_id:\s*"(.+?)"', c[:500])
        if aid_m: fix_list.append({'fp': fp, 'aid': aid_m.group(1)})
    if not fix_list: print('No placeholders!'); return
    print(f'Papers with placeholder: {len(fix_list)}\n')

    fixed = empty = 0
    for i, r in enumerate(fix_list, 1):
        aid, fp = r['aid'], r['fp']
        try:
            meta = get_paper_metadata(aid)
            vid = meta.version_id if hasattr(meta, 'version_id') else ''
            if not vid: print(f'  [{i}/{len(fix_list)}] ⚠️ {aid}: no vid'); continue
            cit = None
            for lang in ['zh', 'en']:
                ov = get_overview(vid, lang)
                if ov:
                    d = ov.model_dump() if hasattr(ov, 'model_dump') else ov
                    cit = _extract_embedded_citations(d.get('overview', ''))
                    if cit: break
            if cit:
                with open(fp, 'r', encoding='utf-8') as fh: c = fh.read()
                c = c.replace('*暂无相关引用*', cit)
                with open(fp, 'w', encoding='utf-8') as fh: fh.write(c)
                fixed += 1
                print(f'  [{i}/{len(fix_list)}] ✅ {aid} ({len(cit)}c)')
            else:
                empty += 1
                print(f'  [{i}/{len(fix_list)}] ⚠️ {aid}: none found')
        except Exception as e:
            print(f'  [{i}/{len(fix_list)}] ❌ {aid}: {str(e)[:80]}')
        time.sleep(0.3)
    print(f'\nFixed: {fixed} | Still empty: {empty}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Paper fixup utilities')
    parser.add_argument('action', choices=['add-summaries', 'fix-quotes', 'fix-citations'],
                        help='Which fixup to run')
    parser.add_argument('--vault', help='Path to Obsidian vault (uses config default if omitted)')
    args = parser.parse_args()
    vault = args.vault or VAULT_PATH
    if not vault:
        print("Error: No vault path configured. Set OBSIDIAN_VAULT_PATH or use --vault.")
        sys.exit(1)
    if args.action == 'add-summaries':
        add_missing_sections(vault)
    elif args.action == 'fix-quotes':
        fix_quotes(vault)
    elif args.action == 'fix-citations':
        fix_placeholder_citations(vault)
