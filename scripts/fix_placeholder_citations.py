"""Fix placeholder citations — extract from overview markdown text."""
import sys, os, re, time
sys.path.insert(0, os.path.dirname(__file__))
from alphaxiv_client import get_paper_metadata, get_overview

from config import PAPERS_DIR
PAPERS = PAPERS_DIR


def extract_embedded_citations(overview_text: str) -> str:
    """Extract citation CONTENT only (strip the heading)."""
    m = re.search(
        r'##\s*(?:相关引[用文]|Reference|参考文献?)\s*\n(.*?)\Z',
        overview_text, re.DOTALL)
    if m and len(m.group(1).strip()) > 20:
        raw = m.group(1).strip()
        # Strip any leading section note like "[本节稍后手动填充]"
        raw = re.sub(r'^\[本节.*?\]\s*\n*', '', raw)
        return raw
    return None


def main():
    fix_list = []
    for f in sorted(os.listdir(PAPERS)):
        if not f.endswith('.md'): continue
        fp = os.path.join(PAPERS, f)
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
                    cit = extract_embedded_citations(d.get('overview', ''))
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
    main()
