#!/usr/bin/env python3
"""Merge paginated transcript HTML files into a single file."""

# /// script
# dependencies = ["beautifulsoup4"]
# ///

import re
from pathlib import Path
from bs4 import BeautifulSoup

def merge_transcripts(transcript_dir: Path, output_file: Path):
    """Merge all transcript pages into a single HTML file."""

    # Read index.html to get the head and initial structure
    index_path = transcript_dir / "index.html"
    with open(index_path, 'r', encoding='utf-8') as f:
        index_soup = BeautifulSoup(f.read(), 'html.parser')

    # Remove pagination elements from index
    for elem in index_soup.select('.pagination'):
        elem.decompose()

    # Get all page files in order
    page_files = sorted(transcript_dir.glob('page-*.html'))

    # Extract message content from each page
    container = index_soup.select_one('.container')
    if not container:
        raise ValueError("Could not find .container in index.html")

    for page_file in page_files:
        with open(page_file, 'r', encoding='utf-8') as f:
            page_soup = BeautifulSoup(f.read(), 'html.parser')

        # Find all message divs
        messages = page_soup.select('.message')

        # Append each message to the container
        for msg in messages:
            container.append(msg)

    # Update title
    title_tag = index_soup.find('title')
    if title_tag:
        title_tag.string = title_tag.string.replace(' - Index', ' - Complete')

    h1_tag = index_soup.find('h1')
    if h1_tag:
        h1_tag.string = h1_tag.string.replace('Index', 'Complete Transcript')

    # Write merged HTML
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(str(index_soup))

    print(f"✓ Merged transcript saved to: {output_file}")
    print(f"  Size: {output_file.stat().st_size / 1024:.1f} KB")

if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("Usage: merge-transcript.py <transcript_dir> <output_file>")
        sys.exit(1)

    transcript_dir = Path(sys.argv[1])
    output_file = Path(sys.argv[2])

    merge_transcripts(transcript_dir, output_file)
