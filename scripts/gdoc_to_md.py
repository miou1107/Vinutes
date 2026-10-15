"""Pull a Google Doc back as Markdown.

Usage: gdoc_to_md.py <doc-id-or-url> <out.md> [--record <minutes.md>] [--force]

Writes to <out.md>; refuses to overwrite an existing file unless --force (use a separate file such as
<name>.remote.md when merging, and --force only when the Doc is the final version).
--record <minutes.md> notes the Doc's modifiedTime in that minutes' .gdoc.json, which md_to_gdoc.py
--accept-current needs to prove nobody edited the Doc between this pull and the merge.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from md_to_gdoc import AUTH, access_token, export_text, modified_time, sha, sidecar_for  # noqa: E402


def restore_headings(md: str) -> str:
    """Docs uploaded before 2026-10-14 had headings as bold paragraphs; turn them back into # headings."""
    out, seen_body, title_lines = [], False, 0
    for line in md.split('\n'):                 # not splitlines(): \x0b and U+2028 are soft breaks inside a line
        m = re.fullmatch(r'\*\*(.+?)\*\*\s*', line)
        if m and re.match(r'[一二三四五六七八九十]+、', m.group(1)):
            line, seen_body = '## ' + m.group(1), True
        elif m and re.match(r'（[一二三四五六七八九十]+）', m.group(1)):
            line = '### ' + m.group(1)
        elif m and not seen_body and title_lines < 2:
            line, title_lines = '# ' + m.group(1), title_lines + 1   # the two centred title lines on top
        elif line.strip():
            seen_body = True                       # anything else ends the title zone
        out.append(line)
    return '\n'.join(out).rstrip('\n') + '\n'


def main():
    doc_id = re.search(r'[-\w]{25,}', sys.argv[1]).group(0)
    out = Path(sys.argv[2])
    if out.exists() and '--force' not in sys.argv:
        sys.exit(f'STOP: {out} exists; pull into a separate file, or add --force if the Doc is the final version')
    AUTH['Authorization'] = 'Bearer ' + access_token()
    pulled_at, pulled_text = modified_time(doc_id), export_text(doc_id)
    url = f'https://www.googleapis.com/drive/v3/files/{doc_id}/export?mimeType=text/markdown'
    md = urllib.request.urlopen(urllib.request.Request(url, headers=AUTH)).read().decode('utf-8').lstrip('﻿')
    # Google's export wraps indented lists in blockquotes and bolds every heading; undo both.
    md = re.sub(r'(?m)^> ', '', md)
    md = re.sub(r'(?m)^(#+) \*\*(.+?)\*\*\s*$', r'\1 \2', md)
    md = re.sub(r'(?m)  $', '', md)
    md = restore_headings(md)
    out.write_text(md, encoding='utf-8')
    if '--record' in sys.argv:
        sidecar = sidecar_for(Path(sys.argv[sys.argv.index('--record') + 1]))
        rec = json.loads(sidecar.read_text())
        rec['pulled_modifiedTime'] = pulled_at
        rec['pulled_sha256'] = sha(pulled_text)   # Drive's modifiedTime can lag behind an edit by seconds
        sidecar.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    print(out, len(md), 'chars')


if __name__ == '__main__':
    main()
