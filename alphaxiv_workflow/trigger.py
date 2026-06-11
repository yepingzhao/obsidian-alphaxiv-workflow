"""Print pending arxiv_ids in batch arrays for Playwright trigger.

Usage:
    python -m alphaxiv_workflow.trigger           # List all pending papers
    python -m alphaxiv_workflow.trigger --batch   # Group by 3 for Playwright
    python -m alphaxiv_workflow.trigger --json    # JSON output
"""
import os
import re
import json
import argparse

from .config import PAPERS_DIR


def get_pending_ids(papers_dir: str = None) -> list:
    """Scan vault and return list of arxiv_ids with blog_status: pending."""
    if papers_dir is None:
        papers_dir = PAPERS_DIR
    if not papers_dir or not os.path.exists(papers_dir):
        return []

    ids = []
    for f in sorted(os.listdir(papers_dir)):
        if not f.endswith('.md'):
            continue
        fpath = os.path.join(papers_dir, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                content = fh.read(3000)
        except OSError:
            continue
        if not re.search(r'blog_status:\s*"?pending"?', content):
            continue
        m = re.search(r'arxiv_id:\s*"(.+?)"', content)
        if m:
            ids.append(m.group(1))
    return ids


def main():
    parser = argparse.ArgumentParser(
        description='List pending papers for overview generation trigger')
    parser.add_argument('--batch', action='store_true',
                        help='Group by 3 for Playwright batch trigger')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON array')
    args = parser.parse_args()

    ids = get_pending_ids()

    if args.json:
        print(json.dumps(ids, indent=2))
        return

    if args.batch:
        print(f'Remaining: {len(ids)}')
        for i in range(0, len(ids), 3):
            batch = ids[i:i + 3]
            js = "['" + "', '".join(batch) + "']"
            print(f'Batch {i // 3 + 1}: {js}')
    else:
        print(f'Pending papers: {len(ids)}')
        for aid in ids:
            print(f'  https://www.alphaxiv.org/overview/{aid}')


if __name__ == '__main__':
    main()
