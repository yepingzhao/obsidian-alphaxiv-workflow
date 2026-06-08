"""
Parallel batch import - imports arXiv papers with AlphaXiv overviews in parallel.
Reuses Gate 1 data (overview status, CCF) to avoid redundant API calls.
"""
import sys
import os
import re
import json
import time
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import arxiv

sys.path.insert(0, os.path.dirname(__file__))

ALPHAXIV_AVAILABLE = False
try:
    from alphaxiv_client import get_paper_metadata, get_overview
    ALPHAXIV_AVAILABLE = True
except Exception:
    pass

from note_builder import (
    clean_title, sanitize_filename, check_title_issues,
    demote_headings, format_citations, extract_tags, CATEGORY_MAP
)
from publication_rank import get_venue_ranking

# ─── Config ───
from config import VAULT_PATH

OUTPUT_DIR = os.path.join(VAULT_PATH, '300 Resources', '320 References') if VAULT_PATH else ''

print_lock = Lock()

# ─── arXiv API Rate Limiter ───
# arXiv API allows ~1 req/sec. Use Semaphore to serialize calls.
arxiv_semaphore = Lock()
_last_arxiv_call = 0
_ARXIV_MIN_INTERVAL = 5.0  # seconds between arXiv API calls (conservative)

def log(msg: str):
    with print_lock:
        print(msg, flush=True)


def rate_limited_arxiv_call(arxiv_id: str) -> dict:
    """Fetch arXiv metadata with rate limiting and retry for 429 errors."""
    global _last_arxiv_call
    max_retries = 5
    for attempt in range(max_retries):
        with arxiv_semaphore:
            # Enforce minimum interval
            elapsed = time.time() - _last_arxiv_call
            if elapsed < _ARXIV_MIN_INTERVAL:
                time.sleep(_ARXIV_MIN_INTERVAL - elapsed)
            try:
                client = arxiv.Client()
                search = arxiv.Search(id_list=[arxiv_id])
                paper = next(client.results(search))
                _last_arxiv_call = time.time()

                authors = [a.name for a in paper.authors]
                categories = list(paper.categories)
                pub_date = paper.published.strftime('%Y-%m-%d') if paper.published else 'Unknown'

                return {
                    'title': paper.title,
                    'arxiv_id': arxiv_id,
                    'authors': authors,
                    'abstract': re.sub(r'\s+', ' ', paper.summary.replace('\n', ' ')).strip(),
                    'categories': categories,
                    'published': pub_date,
                    'arxiv_url': f'https://arxiv.org/abs/{arxiv_id}',
                    'alphaxiv_url': f'https://alphaxiv.org/abs/{arxiv_id}',
                    'comment': paper.comment or '',
                    'journal_ref': paper.journal_ref or '',
                    'entry_id': paper.entry_id,
                }
            except Exception as e:
                _last_arxiv_call = time.time()
                msg = str(e)
                retryable = '429' in msg or 'SSL' in msg or 'ConnectTimeout' in msg or 'ConnectionError' in msg or 'RemoteDisconnected' in msg
                if retryable and attempt < max_retries - 1:
                    wait = (2 ** attempt) * 10  # 10s, 20s, 40s, 80s
                    log(f'  ⏳ Retrying ({msg[:40]}...), waiting {wait}s (attempt {attempt+1}/{max_retries})')
                    time.sleep(wait)
                    continue
                raise


# ─── Note builder (arXiv-based, with optional AlphaXiv) ───

def build_note_arxiv(meta: dict, zh_overview: dict = None, en_overview: dict = None,
                     ccf: str = '') -> str:
    """Build Obsidian markdown note from arXiv metadata."""
    title = clean_title(meta['title'])
    arxiv_id = meta['arxiv_id']
    authors = meta['authors']
    categories = meta.get('categories', [])
    tags = ['paper', 'alphaxiv']
    for cat in categories:
        if cat in CATEGORY_MAP:
            tags.append(CATEGORY_MAP[cat])
    tags = list(dict.fromkeys(tags))
    tags_str = ', '.join(tags)
    pub_date = meta['published']
    abstract = meta['abstract']

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

    authors_yaml = '\n  - '.join(authors)

    # Build frontmatter
    frontmatter = f'''---
title: "{title}"
arxiv_id: "{arxiv_id}"
date: {pub_date}
tags: [{tags_str}]
source: "{meta['alphaxiv_url']}"
authors:
  - {authors_yaml}
aliases:
  - {title}
created: {now_str}
'''

    # Publication venue
    journal_ref = meta.get('journal_ref', '')
    if journal_ref:
        frontmatter += f'published_venue: "{journal_ref}"\n'

    # CCF ranking
    if ccf:
        frontmatter += f'ccf: "{ccf}"\n'

    # Blog status
    blog_pending = False
    has_overview = False
    if zh_overview and zh_overview.get('overview'):
        has_overview = True
    elif en_overview and en_overview.get('overview'):
        has_overview = True
    else:
        blog_pending = True

    if blog_pending:
        frontmatter += 'blog_status: pending\n'

    frontmatter += '---\n'

    # Body
    parts = [frontmatter]
    parts.append(f'# {title}\n')
    parts.append(f'> **arXiv**: [{arxiv_id}]({meta["arxiv_url"]}) | **Published**: {pub_date}')

    # Info bar
    info = parts[-1]
    if journal_ref:
        info += f' | **Venue**: {journal_ref}'
    if ccf:
        info += f' | **CCF**: {ccf}'
    info += '\n'
    parts[-1] = info

    parts.append(f'''## 摘要

{abstract}

---''')

    # AI overview
    if zh_overview and zh_overview.get('overview'):
        overview_text = zh_overview['overview']
        overview_text = re.sub(
            r'\n##\s*(?:相关引[用文]|Reference|参考文献?).*$',
            '', overview_text, flags=re.DOTALL
        ).strip()
        parts.append(f'''## AI 综述 (中文)

> *由 AlphaXiv 生成*

{demote_headings(overview_text)}

---''')
    elif en_overview and en_overview.get('overview'):
        overview_text = en_overview['overview']
        overview_text = re.sub(
            r'\n##\s*(?:相关引[用文]|Reference|参考文献?).*$',
            '', overview_text, flags=re.DOTALL
        ).strip()
        parts.append(f'''## AI 综述 (English)

> *Generated by AlphaXiv*

{demote_headings(overview_text)}

---''')
    else:
        parts.append('''## AI 综述

*AI overview not available. To be updated via backfill-overviews.*

---''')

    # Citations
    if zh_overview and zh_overview.get('citations'):
        parts.append(f'''## 相关引用

{format_citations(zh_overview['citations'])}

---''')

    parts.append(f'*Fetched from arXiv + AlphaXiv on {now_str}*')

    return '\n'.join(parts)


# ─── Single paper import ───

def import_paper(arxiv_id: str, idx: int, total: int,
                 gate1_data: dict = None) -> dict:
    """Import a single paper: fetch metadata, overview, build & save note."""
    result = {'arxiv_id': arxiv_id, 'ok': False}

    try:
        # Step 1: arXiv metadata with rate limiting + retry
        meta = rate_limited_arxiv_call(arxiv_id)
        title = clean_title(meta['title'])
    except Exception as e:
        log(f'  ❌ [{idx}/{total}] {arxiv_id}: arXiv fetch failed: {e}')
        result['error'] = str(e)
        return result

    # Step 2: AlphaXiv overview (if available)
    zh_data, en_data = {}, {}
    ccf = ''
    if gate1_data:
        ccf = gate1_data.get('ccf', '') or ''
        ov_status = gate1_data.get('overview')
        if ov_status and ALPHAXIV_AVAILABLE:
            try:
                alpha_meta = get_paper_metadata(arxiv_id)
                version_id = alpha_meta.version_id if hasattr(alpha_meta, 'version_id') else alpha_meta.get('version_id', '')
                if ov_status in ('zh', 'enzh'):
                    zh = get_overview(version_id, 'zh')
                    if zh:
                        zh_data = zh.model_dump() if hasattr(zh, 'model_dump') else zh
                if ov_status in ('en', 'enzh'):
                    en = get_overview(version_id, 'en')
                    if en:
                        en_data = en.model_dump() if hasattr(en, 'model_dump') else en
            except Exception:
                pass  # AlphaXiv fetch is best-effort

    # Step 3: Build note
    try:
        content = build_note_arxiv(meta, zh_data, en_data, ccf)
    except Exception as e:
        log(f'  ❌ [{idx}/{total}] {arxiv_id}: Note build failed: {e}')
        result['error'] = str(e)
        return result

    # Step 4: Save
    filename = sanitize_filename(meta['title']) + '.md'
    filepath = os.path.join(OUTPUT_DIR, filename)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    ov_tag = '⚡' if (zh_data.get('overview') or en_data.get('overview')) else '  '
    log(f'  ✅ [{idx}/{total}] {arxiv_id} {ov_tag} {title[:60]}')

    result['ok'] = True
    result['filepath'] = filepath
    result['title'] = title
    return result


# ─── Main ───

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Parallel batch import papers')
    parser.add_argument('arxiv_ids', nargs='*', help='arXiv IDs to import')
    parser.add_argument('--from-json', help='JSON file with arxiv_ids to import')
    parser.add_argument('--gate1-data', help='Merged Gate 1 data JSON for overview/CCF reuse')
    parser.add_argument('--workers', type=int, default=2, help='Parallel workers (default: 2, max 3 for arXiv rate limits)')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                        help='Skip papers already in vault (default: True)')
    args = parser.parse_args()

    # Collect arXiv IDs
    arxiv_ids = list(args.arxiv_ids)
    if args.from_json:
        with open(args.from_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            arxiv_ids.extend([item if isinstance(item, str) else item['arxiv_id'] for item in data])

    if not arxiv_ids:
        print("Usage: python parallel_batch_import.py ARXIV_ID [...] [--from-json FILE]")
        sys.exit(1)

    # Load Gate 1 data for reuse
    gate1_map = {}
    if args.gate1_data:
        with open(args.gate1_data, 'r', encoding='utf-8') as f:
            gate1_list = json.load(f)
        gate1_map = {p['arxiv_id']: p for p in gate1_list}

    # Filter out already-saved papers
    new_ids = []
    skipped = 0
    for aid in arxiv_ids:
        if args.skip_existing:
            g1 = gate1_map.get(aid, {})
            if g1.get('in_vault'):
                skipped += 1
                continue
        new_ids.append(aid)

    if skipped:
        log(f'⏭️  Skipped {skipped} already-saved papers')
    log(f'📄 Importing {len(new_ids)} papers to {OUTPUT_DIR}')
    log(f'🔧 Using {args.workers} parallel workers')

    # Import in parallel
    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for i, aid in enumerate(new_ids, 1):
            g1 = gate1_map.get(aid)
            future = executor.submit(import_paper, aid, i, len(new_ids), g1)
            futures[future] = aid

        for future in as_completed(futures):
            aid = futures[future]
            try:
                r = future.result()
                results.append(r)
            except Exception as e:
                log(f'  ❌ {aid}: Exception: {e}')
                results.append({'arxiv_id': aid, 'ok': False, 'error': str(e)})

    elapsed = time.time() - t0
    ok_count = sum(1 for r in results if r['ok'])
    fail_count = len(results) - ok_count

    log(f'\n{"="*60}')
    log(f'✅ Completed: {ok_count}/{len(results)} imported in {elapsed:.1f}s')
    if fail_count:
        log(f'❌ Failed: {fail_count}')
        for r in results:
            if not r['ok']:
                log(f'   - {r["arxiv_id"]}: {r.get("error", "unknown")}')

    # Print failures for retry
    if fail_count:
        failed_ids = [r['arxiv_id'] for r in results if not r['ok']]
        log(f'\nFailed IDs for retry:')
        log(' '.join(failed_ids))


if __name__ == '__main__':
    main()
