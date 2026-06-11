"""Batch arXiv paper import with AlphaXiv overview enrichment.

Usage:
    python -m alphaxiv_workflow.import_papers <arxiv_ids.json> [--workers N]
    python -m alphaxiv_workflow.import_papers --ids 2306.12672 1711.10136
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

from .api import get_paper_metadata, get_overview
from .note_builder import (
    clean_title, sanitize_filename, check_title_issues,
    demote_headings, format_citations, extract_tags,
)
from .venue import get_venue_ranking
from .config import VAULT_PATH

OUTPUT_DIR = os.path.join(VAULT_PATH, '300 Resources', '320 References') if VAULT_PATH else ''
print_lock = Lock()

arxiv_semaphore = Lock()
_last_arxiv_call = 0
_ARXIV_MIN_INTERVAL = 5.0


def log(msg: str):
    with print_lock:
        print(msg, flush=True)


def rate_limited_arxiv_call(arxiv_id: str) -> dict:
    """Fetch arXiv metadata with rate limiting and retry for 429 errors."""
    global _last_arxiv_call
    try:
        import arxiv
    except ImportError:
        return None
    max_retries = 5
    for attempt in range(max_retries):
        with arxiv_semaphore:
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
                }
            except Exception as e:
                msg = str(e)
                if '429' in msg and attempt < max_retries - 1:
                    wait = (2 ** attempt) * 5
                    log(f'  Rate limited for {arxiv_id}, waiting {wait}s (attempt {attempt+1}/{max_retries})')
                    time.sleep(wait)
                    continue
                raise
    return None


def build_note_arxiv(meta: dict, zh_overview, en_overview) -> tuple:
    """Build a markdown note from arXiv metadata and AlphaXiv overviews."""
    title = clean_title(meta.get('title', ''))
    arxiv_id = meta.get('arxiv_id', '')
    issues = check_title_issues(title, VAULT_PATH)
    blocks = [i for i in issues if i[0] == 'block']
    if blocks:
        return None, [f'blocked: {b[1]}' for b in blocks]
    authors = meta.get('authors', [])
    abstract = meta.get('abstract', '')
    published = meta.get('published', 'Unknown')
    categories = meta.get('categories', [])
    tags = extract_tags({'categories': categories, 'subjects': categories}) if extract_tags else categories
    tag_str = json.dumps(tags, ensure_ascii=False)
    citations_text = ''
    if zh_overview and zh_overview.get('citations'):
        citations_text = format_citations(zh_overview['citations'])
    zh_overview_text = zh_overview.get('overview', '') if zh_overview else ''
    en_overview_text = en_overview.get('overview', '') if en_overview else ''
    content = f'''---
title: "{title}"
arxiv_id: "{arxiv_id}"
version: "1"
date: {published}
tags: {tag_str}
source: "arxiv"
authors: {json.dumps(authors, ensure_ascii=False)}
created: {datetime.now().strftime('%Y-%m-%d %H:%M')}
blog_status: pending
---

# {title}

## 摘要
{abstract}

## AI 摘要
*暂无 AI 摘要数据*

## AI 综述 (中文)
{zh_overview_text}

## 相关引用
{citations_text if citations_text else '*暂无相关引用*'}
'''
    return content, []


def import_paper(arxiv_id: str) -> dict:
    """Process a single paper: fetch metadata, build note, save to vault."""
    if not OUTPUT_DIR:
        return {'arxiv_id': arxiv_id, 'status': 'failed', 'path': None,
                'error': 'No output directory configured'}
    from .config import PAPERS_DIR
    papers_dir = PAPERS_DIR or OUTPUT_DIR
    for f in os.listdir(papers_dir) if os.path.exists(papers_dir) else []:
        if arxiv_id in f:
            return {'arxiv_id': arxiv_id, 'status': 'skipped',
                    'path': os.path.join(papers_dir, f), 'error': None}
    try:
        meta = rate_limited_arxiv_call(arxiv_id)
        if meta is None:
            return {'arxiv_id': arxiv_id, 'status': 'failed', 'path': None,
                    'error': 'arXiv API unavailable (arxiv library not installed)'}
    except Exception as e:
        return {'arxiv_id': arxiv_id, 'status': 'failed', 'path': None,
                'error': f'arXiv fetch failed: {e}'}
    title_short = meta['title'][:80]
    log(f'  {arxiv_id}: {title_short}')
    zh_overview = None
    en_overview = None
    try:
        paper_meta = get_paper_metadata(arxiv_id)
        version_id = getattr(paper_meta, 'version_id', '')
        if version_id:
            try:
                zh_overview = get_overview(version_id, 'zh')
                if zh_overview:
                    zh_overview = zh_overview.model_dump() if hasattr(zh_overview, 'model_dump') else zh_overview
            except Exception:
                pass
            try:
                en_overview = get_overview(version_id, 'en')
                if en_overview:
                    en_overview = en_overview.model_dump() if hasattr(en_overview, 'model_dump') else en_overview
            except Exception:
                pass
    except Exception as e:
        log(f'    [AlphaXiv] {e}')
    content, warnings = build_note_arxiv(meta, zh_overview, en_overview)
    if content is None:
        return {'arxiv_id': arxiv_id, 'status': 'failed', 'path': None,
                'error': f'Blocked: {warnings}'}
    filename = sanitize_filename(clean_title(meta['title'])) + '.md'
    filepath = os.path.join(OUTPUT_DIR, filename)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return {'arxiv_id': arxiv_id, 'status': 'saved', 'path': filepath, 'error': None}


def import_papers(arxiv_ids: list, workers: int = 2) -> dict:
    """Import multiple papers in parallel. Returns {'success': N, 'skipped': N, 'failed': N}."""
    results = {'success': 0, 'skipped': 0, 'failed': 0}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(import_paper, aid): aid for aid in arxiv_ids}
        for future in as_completed(futures):
            r = future.result()
            if r is None:
                results['failed'] += 1
                continue
            status = r.get('status', 'failed')
            status_key = 'skipped' if status == 'skipped' else ('saved' if status == 'saved' else 'failed')
            if status_key == 'saved':
                results['success'] += 1
            else:
                results[status_key] = results.get(status_key, 0) + 1
            if status == 'saved':
                log(f'SAVED {r["arxiv_id"]} -> {r["path"]}')
            elif status == 'skipped':
                log(f'SKIP {r["arxiv_id"]} (already exists)')
            else:
                log(f'FAIL {r["arxiv_id"]}: {r.get("error", "unknown")}')
    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Batch import arXiv papers to Obsidian vault')
    parser.add_argument('json_file', nargs='?', help='JSON file with arXiv ID list')
    parser.add_argument('--ids', nargs='+', help='arXiv IDs directly on command line')
    parser.add_argument('--workers', type=int, default=2, help='Parallel workers (default: 2)')
    args = parser.parse_args()
    if args.ids:
        arxiv_ids = args.ids
    elif args.json_file:
        with open(args.json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            arxiv_ids = data if isinstance(data, list) else list(data)
    else:
        parser.print_help()
        sys.exit(1)
    if not arxiv_ids:
        print("Error: no arXiv IDs provided")
        sys.exit(1)
    print(f"Importing {len(arxiv_ids)} papers with {args.workers} workers...")
    results = import_papers(arxiv_ids, workers=args.workers)
    print(f"Done: {results['success']} success, {results['skipped']} skipped, {results['failed']} failed")
