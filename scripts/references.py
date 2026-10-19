"""Files and links handed to the AI with one sentence (＋ beside the box under the minutes), put in the AI's folder as
參考資料-1.pdf, 參考資料-2.txt, … for it to read before it changes the minutes. They never go into the minutes and
are not uploaded anywhere; a picture among them goes with the pasted screenshots (minutes_app.picture_copies).

The AI only reads files in its folder and cannot go online, so a link is read here first: a Google Doc, Sheet or
Slides file, or a file kept in Google Drive, through the user's Google login; any other page as its text, or a PDF as
it is. Word, Excel and PowerPoint files become text as well; a PDF or a text file is copied as it is.
"""
from __future__ import annotations

import codecs
import html.parser
import re
import shutil
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from i18n import t

NAME = '參考資料'
PICTURES = {'.png', '.jpg', '.jpeg', '.gif', '.heic', '.webp', '.tif', '.tiff', '.bmp'}
AS_IS = {'.pdf', '.txt', '.md', '.csv', '.tsv', '.json'}
TEXTUTIL = {'.doc', '.docx', '.rtf', '.odt', '.html', '.htm'}       # macOS's textutil makes these plain text
MOST = 300_000                   # characters of text from one file or page
PAGE_BYTES = 20_000_000          # the most read of a page or a PDF behind a link
# a Google file by its id: Docs, Sheets and Slides (also signed in as a second account, /u/1/), or a file in Drive
GOOGLE = re.compile(r'https://(?:docs\.google\.com/(?:document|spreadsheets|presentation)(?:/u/\d+)?/d/'
                    r'|drive\.google\.com/(?:(?:u/\d+/)?file/d/|open\?(?:[^#]*&)?id=|uc\?(?:[^#]*&)?id=))([\w-]{20,})')
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
EXPORT = {'application/vnd.google-apps.document': ('text/plain', '.txt'),
          'application/vnd.google-apps.spreadsheet': (XLSX, '.xlsx'),          # every tab, not only the first
          'application/vnd.google-apps.presentation': ('text/plain', '.txt')}
SIGN_IN = re.compile(r'accounts\.google\.com|login\.microsoftonline\.com|/(?:login|signin|sign-in|sso)\b', re.I)
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


def checked(items) -> list[dict]:
    """What the window sent ([{kind: file, path}] and [{kind: link, url}]), checked before the AI starts."""
    out = []
    for it in items if isinstance(items, list) else []:
        kind = it.get('kind') if isinstance(it, dict) else None
        if kind == 'file':
            path = Path(str(it.get('path', ''))).expanduser()
            if not path.is_file():
                raise SystemExit(t('ref_no_file', name=path.name))
            out.append({'kind': 'file', 'path': path})
        elif kind == 'link':
            url = str(it.get('url', '')).strip()
            if not re.match(r'https?://\S+$', url):
                raise SystemExit(t('attach_bad_url'))
            out.append({'kind': 'link', 'url': url})
    return out


def prepare(refs: list[dict], work: Path) -> tuple[list[Path], list[tuple[str, str]]]:
    """`refs` in the AI's folder `work`: the pictures among them (for picture_copies), and each other one as
    (its name in the folder, the file's own name or the link) for the prompt."""
    pictures, shown = [], []
    for ref in refs:
        if ref['kind'] == 'file' and ref['path'].suffix.lower() in PICTURES:
            pictures.append(ref['path'])
            continue
        n = len(shown) + 1
        if ref['kind'] == 'link':
            name = read_link(ref['url'], work, f'{NAME}-{n}')
            shown.append((name, ref['url']))
        else:
            shown.append((read_file(ref['path'], work, f'{NAME}-{n}'), ref['path'].name))
    return pictures, shown


def read_file(src: Path, work: Path, stem: str, shown_as: str = '') -> str:
    """`src` in `work` as stem.<kind> or stem.txt; `shown_as` names it in a message (a file from Drive)."""
    kind, name = src.suffix.lower(), shown_as or src.name
    if kind in AS_IS:
        shutil.copy(src, work / f'{stem}{kind}')
        return f'{stem}{kind}'
    if kind in TEXTUTIL:
        target = work / f'{stem}.txt'
        try:
            done = subprocess.run(['/usr/bin/textutil', '-convert', 'txt', '-output', str(target), str(src)],
                                  capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise SystemExit(t('ref_unreadable', name=name)) from None
        if done.returncode or not target.is_file():
            raise SystemExit(t('ref_unreadable', name=name))
        return save_text(target.read_text(encoding='utf-8', errors='replace'), work, stem)
    if kind in ('.xlsx', '.pptx'):
        try:
            text = (sheets_text if kind == '.xlsx' else slides_text)(src)
        except (zipfile.BadZipFile, ElementTree.ParseError, KeyError, ValueError):
            raise SystemExit(t('ref_unreadable', name=name)) from None
        return save_text(text, work, stem)
    raw = src.read_bytes()[:MOST * 4]            # any other text file (.log, .yaml, .py …) is read as text
    if b'\0' not in raw:
        try:
            return save_text(raw.decode('utf-8-sig'), work, stem)
        except UnicodeDecodeError:
            pass
    raise SystemExit(t('ref_kind', name=name))


def save_text(text: str, work: Path, stem: str) -> str:
    if len(text) > MOST:
        text = text[:MOST] + '\n\n' + t('ref_cut', 'en')
    (work / f'{stem}.txt').write_text(text, encoding='utf-8')
    return f'{stem}.txt'


# --- Excel and PowerPoint, read from their XML -----------------------------------------------------------------

def local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def texts(el) -> str:
    return ''.join(x.text or '' for x in el.iter() if local(x.tag) == 't')


def in_order(z: zipfile.ZipFile, book: str, kind: str, prefix: str) -> list[tuple[str, str]]:
    """(name, part) of each sheet or slide in the order the workbook or the presentation lists them (a moved or
    deleted one leaves sheet3.xml out of order); by the parts' own numbers when that list cannot be read."""
    names = set(z.namelist())
    folder = book.rsplit('/', 1)[0]
    try:
        root = ElementTree.fromstring(z.read(book))
    except (KeyError, ElementTree.ParseError):
        root = None
    try:
        rels = {r.get('Id'): r.get('Target', '')
                for r in ElementTree.fromstring(z.read(f'{folder}/_rels/{book.rsplit("/", 1)[1]}.rels'))}
    except (KeyError, ElementTree.ParseError):
        rels = {}
    found = []
    for el in root.iter() if root is not None else []:
        if local(el.tag) == kind and el.get(REL) in rels:
            target = rels[el.get(REL)]
            part = target.lstrip('/') if target.startswith('/') else f'{folder}/{target}'
            if part in names:
                found.append((el.get('name', ''), part))
    if found:
        return found
    parts = sorted((n for n in names if re.fullmatch(re.escape(prefix) + r'\d+\.xml', n)),
                   key=lambda n: int(re.search(r'(\d+)\.xml$', n).group(1)))
    titles = [el.get('name', '') for el in root.iter() if local(el.tag) == kind] if root is not None else []
    return [(titles[i] if i < len(titles) else '', p) for i, p in enumerate(parts)]


def column(ref: str) -> int:
    """B7 -> 1: the cell's column, from 0."""
    n = 0
    for ch in re.match(r'[A-Z]*', ref or '').group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def sheets_text(src: Path) -> str:
    """Each sheet as '## name' and its rows, the cells of a row split by tabs in their own columns."""
    with zipfile.ZipFile(src) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            root = ElementTree.fromstring(z.read('xl/sharedStrings.xml'))
            shared = [texts(si) for si in root if local(si.tag) == 'si']
        out = []
        for name, part in in_order(z, 'xl/workbook.xml', 'sheet', 'xl/worksheets/sheet'):
            out.append(f'## {name or Path(part).stem}')
            for row in ElementTree.fromstring(z.read(part)).iter():
                if local(row.tag) != 'row':
                    continue
                cells = []
                for c in row:
                    if local(c.tag) != 'c':
                        continue
                    v = next((x.text or '' for x in c if local(x.tag) == 'v'), '')
                    if c.get('t') == 's' and v.isdigit() and int(v) < len(shared):
                        v = shared[int(v)]
                    elif c.get('t') == 'inlineStr':
                        v = texts(c)
                    at = column(c.get('r', ''))
                    cells += [''] * max(0, at - len(cells))       # empty cells before this one keep their place
                    cells.append(v)
                if any(cells):
                    out.append('\t'.join(cells))
            out.append('')
    return '\n'.join(out)


def slides_text(src: Path) -> str:
    """Each slide as '## Slide n', in the order the presentation shows them, and its paragraphs."""
    with zipfile.ZipFile(src) as z:
        out = []
        for n, (_, part) in enumerate(in_order(z, 'ppt/presentation.xml', 'sldId', 'ppt/slides/slide'), 1):
            out.append(f'## Slide {n}')
            root = ElementTree.fromstring(z.read(part))
            out += [line for line in (texts(p).strip() for p in root.iter() if local(p.tag) == 'p') if line]
            out.append('')
    return '\n'.join(out)


# --- links ------------------------------------------------------------------------------------------------------

class PageText(html.parser.HTMLParser):
    """A page's title and words, a line for each block; scripts, styles and pictures left out."""
    SKIP = {'script', 'style', 'noscript', 'svg', 'template', 'head'}
    BLOCK = {'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'article', 'table',
             'ul', 'ol', 'header', 'footer', 'blockquote', 'pre'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skipping, self.title, self.titling = [], 0, '', False

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self.titling = True
        elif tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCK:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag == 'title':
            self.titling = False
        elif tag in self.SKIP and self.skipping:
            self.skipping -= 1
        elif tag in self.BLOCK:
            self.parts.append('\n')

    def handle_data(self, data):
        if self.titling:
            self.title += data
        elif not self.skipping:
            self.parts.append(data)

    def text(self) -> str:
        lines = (' '.join(line.split()) for line in [self.title, *''.join(self.parts).splitlines()])
        return '\n'.join(line for line in lines if line)


def page_text(raw: str) -> str:
    reader = PageText()
    reader.feed(raw)
    return reader.text()


def charset_of(raw: bytes, said: str | None) -> str:
    """The page's own encoding: the server's word, else the page's <meta charset>, else UTF-8."""
    m = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw[:4096], re.I)
    for name in (said, m and m.group(1).decode('ascii', 'ignore')):
        try:
            if name:
                return codecs.lookup(name).name
        except LookupError:
            pass
    return 'utf-8'


def read_google(url: str, fid: str, work: Path, stem: str) -> str:
    """A Google Doc, Sheet or Slides file (exported), or a file kept in Drive (downloaded), with the user's login."""
    import attachments
    import doc_sync
    try:
        meta = attachments.call(f'{doc_sync.DRIVE}{fid}?fields=name,mimeType')
        mime, name = meta.get('mimeType', ''), meta.get('name') or fid
        if mime in EXPORT:
            want, kind = EXPORT[mime]
            raw = attachments.call(f'{doc_sync.DRIVE}{fid}/export?mimeType={urllib.parse.quote(want)}', want='bytes')
        elif mime.startswith('application/vnd.google-apps'):
            raise SystemExit(t('ref_kind', name=name))
        else:
            kind = Path(name).suffix.lower()
            raw = attachments.call(f'{doc_sync.DRIVE}{fid}?alt=media', want='bytes')
    except SystemExit as err:
        text = str(err)
        if text.startswith('OFFLINE'):
            raise SystemExit(t('ref_link_failed', url=url)) from None
        if re.search(r'HTTP 40[34]', text):
            raise SystemExit(t('ref_google_right', url=url)) from None
        raise SystemExit(attachments.drive_trouble(err)) from None
    if kind == '.txt':
        return save_text(f'{url}\n\n' + raw.decode('utf-8-sig', errors='replace'), work, stem)
    if kind in PICTURES:
        (work / f'{stem}{kind}').write_bytes(raw)
        return f'{stem}{kind}'
    held = work / f'{stem}.download{kind}'
    held.write_bytes(raw)
    try:
        return read_file(held, work, stem, shown_as=name)
    finally:
        held.unlink(missing_ok=True)


def read_link(url: str, work: Path, stem: str) -> str:
    """The link's contents in `work`, as stem.txt (or stem.pdf); the first line of a text says where it is from."""
    google = GOOGLE.match(url)
    if google:
        return read_google(url, google.group(1), work, stem)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh) Vinutes',
                                               'Accept': 'text/html,application/pdf,text/plain;q=0.9,*/*;q=0.5'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            landed = resp.geturl()
            ctype = resp.headers.get_content_type()
            said = resp.headers.get_content_charset()
            raw = resp.read(PAGE_BYTES + 1)
    except urllib.error.HTTPError as err:
        raise SystemExit(t('ref_link_login' if err.code in (401, 403) else 'ref_link_failed', url=url)) from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError, ValueError):
        raise SystemExit(t('ref_link_failed', url=url)) from None
    if landed != url and SIGN_IN.search(landed):  # sent on to a sign-in page: its words are not the page asked for
        raise SystemExit(t('ref_link_login', url=url))
    if len(raw) > PAGE_BYTES:
        raise SystemExit(t('ref_link_big', url=url))
    if ctype == 'application/pdf' or raw[:5] == b'%PDF-':
        (work / f'{stem}.pdf').write_bytes(raw)
        return f'{stem}.pdf'
    if not (ctype.startswith('text/') or ctype in ('application/json', 'application/xhtml+xml', 'application/xml')):
        raise SystemExit(t('ref_link_kind', url=url))
    body = raw.decode(charset_of(raw, said), errors='replace')
    text = page_text(body) if 'html' in ctype else body
    if not text.strip():
        raise SystemExit(t('ref_link_login', url=url))
    return save_text(f'{url}\n\n{text}', work, stem)
