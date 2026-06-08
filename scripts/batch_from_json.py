"""Batch import papers from a JSON file of arXiv IDs using batch_import.py functions."""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(__file__))

from batch_import import (
    fetch_arxiv_meta, try_alphaxiv_overview, build_note_arxiv,
    check_title_issues, sanitize_filename, OUTPUT_DIR, VAULT_PATH)


def fetch_with_retry(arxiv_id: str, max_retries: int = 5) -> dict:
    """Fetch arXiv metadata with exponential backoff for 429 errors."""
    for attempt in range(max_retries):
        try:
            return fetch_arxiv_meta(arxiv_id)
        except Exception as e:
            msg = str(e)
            if '429' in msg and attempt < max_retries - 1:
                wait = (2 ** attempt) * 5
                print(f'  Rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})')
                time.sleep(wait)
                continue
            raise


def main():
    json_file = sys.argv[1] if len(sys.argv) > 1 else 'image_editing_papers.json'

    with open(json_file, 'r', encoding='utf-8') as f:
        arxiv_ids = json.load(f)

    print(f'Loading {len(arxiv_ids)} papers from {json_file}')
    print(f'Output: {OUTPUT_DIR}')

    success = 0
    skipped = 0
    failed = 0

    for i, arxiv_id in enumerate(arxiv_ids, 1):
        print(f'\n{"="*60}')
        print(f'[{i}/{len(arxiv_ids)}] Processing: {arxiv_id}')

        try:
            meta = fetch_with_retry(arxiv_id)
            title_short = meta['title'][:80]
            print(f'  Title: {title_short}')
            print(f'  Authors: {len(meta["authors"])} authors')
        except Exception as e:
            print(f'  ERROR fetching arXiv metadata: {e}')
            failed += 1
            time.sleep(3)
            continue

        filename = sanitize_filename(meta['title']) + '.md'
        filepath = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(filepath):
            print(f'  SKIP: already exists in vault')
            skipped += 1
            time.sleep(1.5)
            continue

        zh_overview, en_overview, ov_warnings = try_alphaxiv_overview(arxiv_id)
        for w in ov_warnings:
            print(f'  [AlphaXiv] {w}')

        content = build_note_arxiv(meta, zh_overview, en_overview)

        issues = check_title_issues(meta['title'], VAULT_PATH)
        blocks = [i for i in issues if i[0] == 'block']
        if blocks:
            print(f'  BLOCKED: {[b[1] for b in blocks]}')
            failed += 1
            time.sleep(1.5)
            continue

        for severity, msg in issues:
            print(f'  [{severity}] {msg}')

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        ov_tag = 'AO' if (zh_overview and zh_overview.get('overview')) else '--'
        print(f'  SAVED [{ov_tag}] {filepath}')
        success += 1

        time.sleep(1.5)

    print(f'\n{"="*60}')
    print(f'Success: {success}')
    print(f'Skipped: {skipped}')
    print(f'Failed: {failed}')
    print(f'Total: {len(arxiv_ids)}')

if __name__ == '__main__':
    main()
