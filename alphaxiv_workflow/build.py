"""
Fetch AlphaXiv paper overview (blog) and save as Obsidian markdown note.
Usage: python -m alphaxiv_workflow.build "<paper title or arXiv ID>"

Uses shared modules from the alphaxiv-to-obsidian skill pipeline.
"""
import sys
import os

from .config import VAULT_PATH, PAPERS_DIR
from .api import (
    resolve_paper_id,
    get_paper_metadata,
    get_overview,
    fetch_publication_info,
)
from .venue import fetch_publication_rank
from .note_builder import sanitize_filename, build_note, clean_title


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m alphaxiv_workflow.build '<paper title or arXiv ID>'")
        sys.exit(1)

    if not VAULT_PATH:
        print("Error: OBSIDIAN_VAULT_PATH not set and ~/.alphaxiv-to-obsidian.json not found.")
        print("Configure your vault path before importing papers.")
        sys.exit(1)

    query = sys.argv[1]
    print(f"Searching for: {query}")

    try:
        arxiv_id = resolve_paper_id(query)
    except Exception as e:
        print(f"Error: Search failed: {e}")
        print("Check your network connection and try again.")
        sys.exit(1)

    if not arxiv_id:
        print(f"Error: Paper not found: '{query}'")
        print("Check the title spelling or try the arXiv ID directly (e.g. 1706.03762).")
        sys.exit(1)
    print(f"Found: {arxiv_id}")

    try:
        print("Fetching metadata...")
        meta = get_paper_metadata(arxiv_id)
    except Exception as e:
        print(f"Error: Failed to fetch metadata for {arxiv_id}: {e}")
        print("The paper may be private or the API may be temporarily unavailable.")
        sys.exit(1)

    try:
        version_id = meta.version_id
    except AttributeError:
        print("  [warn] Metadata has no version ID — overviews unavailable.")
        version_id = None

    # Fetch Chinese overview
    zh_overview = None
    if version_id:
        try:
            print("Fetching Chinese overview...")
            zh_overview = get_overview(version_id, "zh")
        except Exception as e:
            print(f"  [warn] blog_pending: Chinese overview not available ({e})")
            print("  AlphaXiv overviews are generated asynchronously — continuing without overview.")

    # Fetch English overview as fallback (non-blocking)
    en_overview = None
    if version_id:
        try:
            en_overview = get_overview(version_id, "en")
        except Exception:
            pass

    # Fetch publication info from arXiv API (non-blocking)
    pub_info = None
    pub_rank = None
    try:
        abstract = getattr(meta, 'abstract', '')
        pub_info = fetch_publication_info(arxiv_id, abstract=abstract)
        venue = pub_info.get('published_venue') if pub_info else None
        if venue:
            print(f"  Venue: {venue}")
            pub_rank = fetch_publication_rank(venue)
    except Exception:
        pass

    print("Building note...")
    note_content, warnings = build_note(meta, zh_overview, en_overview,
                                        pub_info=pub_info, pub_rank=pub_rank)
    for w in warnings:
        print(f"  [warn] {w}")

    title = clean_title(meta.title)
    filename = sanitize_filename(title) + ".md"
    filepath = os.path.join(PAPERS_DIR, filename)

    os.makedirs(PAPERS_DIR, exist_ok=True)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(note_content)
    except OSError as e:
        print(f"Error: Cannot write to {filepath}: {e}")
        print(f"Check that the vault path is correct: {VAULT_PATH}")
        sys.exit(1)

    print(f"Saved to: {filepath}")
    print(f"Size: {len(note_content)} chars")


if __name__ == "__main__":
    main()
