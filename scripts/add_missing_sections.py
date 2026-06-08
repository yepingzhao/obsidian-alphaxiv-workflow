"""
Add missing H2 sections from AlphaXiv API:
- ## AI 摘要 (from overview.summary)
- ## 相关引用 (from overview.citations)
"""
import sys, os, re, time
sys.path.insert(0, os.path.dirname(__file__))
from alphaxiv_client import get_paper_metadata, get_overview

from config import PAPERS_DIR
PAPERS = PAPERS_DIR


def build_ai_summary(summary_data: dict) -> str:
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


def build_citations(citations: list) -> str:
    if not citations: return None

    # Check if this is raw embedded citation text
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


def main():
    results = []
    for f in sorted(os.listdir(PAPERS)):
        if not f.endswith('.md'): continue
        fp = os.path.join(PAPERS, f)
        with open(fp, 'r', encoding='utf-8') as fh:
            content = fh.read()
        # Check for AI 摘要 - detect any existing summary sub-heading
        has_ai_summary = ('## AI 摘要\n' in content or
                          '### 摘要\n' in content or
                          '### 核心总结\n' in content)
        needs_summary = not has_ai_summary
        needs_cit = '## 相关引用\n' not in content
        if not needs_summary and not needs_cit: continue
        aid_m = re.search(r'arxiv_id:\s*"(.+?)"', content[:500])
        if aid_m: results.append({'fp': fp, 'aid': aid_m.group(1), 'ns': needs_summary, 'nc': needs_cit})

    if not results:
        print('All notes complete!'); return

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
            # Fallback: extract citations from overview markdown text
            # (AlphaXiv API sometimes stores citations in overview text, not structured field)
            if not citations:
                ov_text = d.get('overview', '')
                cit_match = re.search(
                    r'##\s*(?:相关引[用文]|Reference|参考文献?)\s*\n(.*?)\Z',
                    ov_text, re.DOTALL | re.MULTILINE)
                if cit_match:
                    raw_cit = cit_match.group(1).strip()
                    # Parse as markdown list: each citation is a paragraph block
                    # Simple approach: use the raw text directly (already markdown formatted)
                    citations = [{'title': 'Embedded citation block', 'raw': raw_cit}]

            with open(fp, 'r', encoding='utf-8') as fh:
                content = fh.read()

            # ── Insert AI 摘要 ──
            if r['ns']:
                ai = build_ai_summary(summary)
                ins = content.find('\n---\n', content.find('## 摘要'))
                if ins > 0:
                    end = ins + 5
                    sec = f'\n## AI 摘要\n\n{ai}\n' if ai else '\n## AI 摘要\n\n*暂无 AI 摘要数据*\n'
                    content = content[:end] + sec + '\n---\n' + content[end:]
                    if ai: ai_ok += 1
                    else: ai_pl += 1

            # ── Insert 相关引用 ──
            if r['nc']:
                cit = build_citations(citations)
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


if __name__ == '__main__':
    main()
