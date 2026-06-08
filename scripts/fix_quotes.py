"""Fix quote bugs in YAML frontmatter — normalize all scalar values."""
import os, re, sys
from config import PAPERS_DIR
PAPERS = PAPERS_DIR

# Fields that should have unquoted values
UNQUOTED = ['date', 'tags', 'sci_cas_top', 'utd24', 'ft50']
# Boolean-like values
BOOLS = {'true', 'false'}

def clean_value(field: str, raw: str) -> str:
    """Clean a raw YAML value from frontmatter parsing."""
    val = raw.strip()

    # Remove all layers of wrapping quotes
    while (val.startswith('"') and val.endswith('"')) or \
          (val.startswith("'") and val.endswith("'")):
        val = val[1:-1].strip()

    # Fields that should be unquoted
    if field in UNQUOTED:
        return val

    # Booleans unquoted
    if val.lower() in BOOLS:
        return val

    # List values (from tags field)
    if field == 'tags':
        return val  # Already stripped quotes, e.g. [paper, alphaxiv, ...]

    # Everything else: quote the value
    return f'"{val}"'


if __name__ == '__main__':
    total = fixed = 0

    for f in sorted(os.listdir(PAPERS)):
        if not f.endswith('.md'): continue
        fp = os.path.join(PAPERS, f)
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
        in_list = False

        for line in lines:
            kv = re.match(r'^(\w[\w-]*):\s*(.*)', line)
            li = re.match(r'^\s+-\s+(.+)', line)

            if kv:
                cur_key = kv.group(1)
                if kv.group(2).strip():  # Has inline value
                    new_lines.append(f'{cur_key}: {clean_value(cur_key, kv.group(2))}')
                    in_list = False
                else:  # Empty — list follows
                    new_lines.append(f'{cur_key}:')
                    in_list = True
            elif li and cur_key:
                # List item — keep as-is
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
