"""Print pending arxiv_ids in Playwright-ready JS arrays, batched by 3."""
import os, re
from config import PAPERS_DIR
papers_dir = PAPERS_DIR

ids = []
for f in sorted(os.listdir(papers_dir)):
    if not f.endswith('.md'): continue
    fpath = os.path.join(papers_dir, f)
    with open(fpath, 'r', encoding='utf-8') as fh:
        content = fh.read(3000)
    if 'blog_status: pending' not in content: continue
    m = re.search(r'arxiv_id:\s*"(.+?)"', content)
    if m: ids.append(m.group(1))

print(f'Remaining: {len(ids)}')
for i in range(0, len(ids), 3):
    batch = ids[i:i+3]
    js = "['" + "', '".join(batch) + "']"
    print(f'Batch {i//3 + 1}: {js}')
