"""Keep the minutes Markdown and its Google Doc in step, paragraph by paragraph, never by re-uploading the Doc.

Re-uploading a whole Doc detaches every comment from its text and throws away what colleagues typed into it.
So the recorder app works the other way round:

  pull   on opening a meeting: the Doc's current paragraphs (Google Docs API) are compared with the Markdown;
         paragraphs a colleague changed are written into the Markdown, and the changed words come back as marks
         for the preview (who changed what).
  push   after an edit in the app (typed in the preview, or rewritten by Claude): only the paragraphs that differ
         between the Markdown before and after the edit are changed in the Doc, with the smallest text
         replacement inside each paragraph. A paragraph a colleague changed in the meantime is left alone and
         reported as a conflict instead of being overwritten.
  carry  what the user typed in the preview, carried onto the Markdown: the preview's HTML loses things on its
         way back to Markdown (loose lists, quotes, escapes), so the edit is the difference between the preview as
         it was opened and as it is now, both read back the same way, and only those paragraphs are replaced.

Both directions use the same picture of a document: a list of units in reading order. A heading, a list item or
a paragraph is one unit; every table cell is one unit, matched by its position. Markdown side: parse(); Doc
side: units(). A person chip or a rich link in the Doc reads as its name and can only be removed as a whole; an
edit that would cut into one is a conflict. Changes the paragraph model cannot express (a table gains a row or a
column) raise Structural; the caller then rebuilds the Markdown from the Doc (doc_to_md) or uploads the whole Doc,
which md_to_gdoc.py refuses while comments are open.

Usage (for checking by hand):
  doc_sync.py units <doc-id>                     print the Doc's units
  doc_sync.py plan <doc-id> <base.md> <new.md>   print the requests a push would send, without sending them
"""
from __future__ import annotations

import difflib
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

OBJ = '\ufffc'                  # stands for an inline image or any other Doc element that has no text
DOCS = 'https://docs.googleapis.com/v1/documents/'
DRIVE = 'https://www.googleapis.com/drive/v3/files/'
AUTH: dict = {}

ORDERED_GLYPHS = {'DECIMAL', 'ZERO_DECIMAL', 'UPPER_ALPHA', 'ALPHA', 'UPPER_ROMAN', 'ROMAN'}
# h1: the two title lines on top, large centred normal text rather than a heading, so that Google Docs leaves
# them out of its outline (title_requests)
NAMED = {'h1': 'NORMAL_TEXT', 'h2': 'HEADING_2', 'h3': 'HEADING_3', 'h4': 'HEADING_4', 'h5': 'HEADING_5',
         'h6': 'HEADING_6', 'p': 'NORMAL_TEXT', 'li': 'NORMAL_TEXT', 'ol': 'NORMAL_TEXT'}
PRESET = {'li': 'BULLET_DISC_CIRCLE_SQUARE', 'ol': 'NUMBERED_DECIMAL_ALPHA_ROMAN'}
LOOK = ('weightedFontFamily', 'fontSize', 'foregroundColor')     # copied onto inserted text from its neighbours
CJK = re.compile(r'[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]')
BUSY = '同事正在 Google 文件上修改，你改的內容先存在這台電腦，下次存檔時會一起存回。'


class Structural(Exception):
    """The edit changes the shape of the document (table rows or columns), which only a full upload can do."""


def u16(text: str) -> int:
    """Length in UTF-16 code units, the unit of every Google Docs index."""
    return len(text.encode('utf-16-le')) // 2


def norm(text: str) -> str:
    text = text.replace(OBJ, '').replace('\x0b', ' ').replace('\u00a0', ' ').replace('\u200b', '')
    return re.sub(r'\s+', ' ', text).strip()


def join_lines(a: str, b: str) -> str:
    """Two lines of one paragraph, the way Word and Google Docs join them: no space between Chinese characters."""
    if a and b and CJK.match(a[-1]) and CJK.match(b[0]):
        return a + b
    return a + ' ' + b


# --- Markdown side ---------------------------------------------------------------------------

HEAD = re.compile(r'^(#{1,6})\s+(.*?)\s*#*\s*$')
BULLET = re.compile(r'^(\s*)[-*+]\s+(.*)$')
NUMBER = re.compile(r'^(\s*)(\d+)[.)]\s+(.*)$')
QUOTE = re.compile(r'^(\s*>\s?)(.*)$')
RULE = re.compile(r'^\s*([-*_])(\s*\1){2,}\s*$')
TABLE_SEP = re.compile(r'^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$')


@dataclass
class Block:
    kind: str                   # h1..h6, li, ol, p, cell
    md: str                     # the inline Markdown of the unit
    first: int                  # first line index in the file
    last: int                   # last line index (a paragraph may span lines)
    level: int = 0              # list nesting
    number: int = 0             # the number an ordered item was written with
    table: int = -1
    row: int = -1
    col: int = -1
    lead: str = ''              # a paragraph's own line prefix, kept when it is rewritten ("> " for a quote)

    @property
    def plain(self) -> str:
        return plain(self.md)

    @property
    def key(self):
        return ('C', self.table, self.row, self.col) if self.kind == 'cell' else ('P', norm(self.plain))


def split_row(line: str) -> list[str]:
    cells = re.split(r'(?<!\\)\|', line.strip())
    if cells and cells[0].strip() == '':
        cells = cells[1:]
    if cells and cells[-1].strip() == '':
        cells = cells[:-1]
    return [c.strip() for c in cells]


def starts_block(line: str) -> bool:
    s = line.strip()
    return (not s or s.startswith('|') or bool(HEAD.match(line) or BULLET.match(line) or NUMBER.match(line)
                                                or QUOTE.match(line) or RULE.match(line)))


def parse(md: str) -> tuple[list[str], list[Block]]:
    lines = md.split('\n')
    blocks: list[Block] = []
    table, row, i = -1, -1, 0
    in_table = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith('|'):
            if TABLE_SEP.match(stripped):
                i += 1
                continue
            if not in_table:
                in_table, table, row = True, table + 1, -1
            row += 1
            for c, cell in enumerate(split_row(line)):
                blocks.append(Block('cell', cell, i, i, table=table, row=row, col=c))
            i += 1
            continue
        in_table = False
        if not stripped or RULE.match(line):            # a rule has no paragraph of its own in the Doc
            i += 1
            continue
        m = HEAD.match(line)
        if m:
            blocks.append(Block(f'h{len(m.group(1))}', m.group(2), i, i))
            i += 1
            continue
        m, n = BULLET.match(line), NUMBER.match(line)
        if m or n:
            indent = (m or n).group(1).replace('\t', '    ')
            text = m.group(2) if m else n.group(3)
            last = i
            # a following indented line that is not a new item continues this item
            while last + 1 < len(lines) and lines[last + 1].startswith('  ') and lines[last + 1].strip() \
                    and not BULLET.match(lines[last + 1]) and not NUMBER.match(lines[last + 1]):
                last += 1
                text = join_lines(text, lines[last].strip())
            blocks.append(Block('li' if m else 'ol', text, i, last, level=len(indent) // 2,
                                number=int(n.group(2)) if n else 0))
            i = last + 1
            continue
        q = QUOTE.match(line)
        lead = q.group(1) if q else ''
        text = q.group(2).strip() if q else stripped
        last = i
        while last + 1 < len(lines):
            nxt = lines[last + 1]
            nq = QUOTE.match(nxt)
            if q and nq:
                text = join_lines(text, nq.group(2).strip())
            elif not q and not starts_block(nxt):
                text = join_lines(text, nxt.strip())
            else:
                break
            last += 1
        blocks.append(Block('p', text, i, last, lead=lead))
        i = last + 1
    return lines, blocks


_INLINE: list = []


def inline_tokens(md: str) -> list:
    """markdown-it's reading of one paragraph's inline Markdown: the reading md_to_docx (and so the Doc) and the
    window's preview use, so `請**「行銷部」**提供` is literal asterisks everywhere, here too."""
    if not _INLINE:
        from markdown_it import MarkdownIt
        _INLINE.append(MarkdownIt('commonmark'))
    tokens = _INLINE[0].parseInline(md)
    return (tokens[0].children or []) if tokens else []


def spans(md: str) -> tuple[str, list[tuple[int, int, bool, str | None]]]:
    """Inline Markdown -> (plain text, [(start, end, bold, link url)]) with offsets into the plain text."""
    out: list[str] = []
    marks: list = []
    bold, links = 0, []

    def emit(text: str):
        start = sum(len(t) for t in out)
        out.append(text)
        link = links[-1] if links else None
        if text and (bold or link):
            marks.append((start, start + len(text), bool(bold), link))

    for t in inline_tokens(md):
        if t.type == 'strong_open':
            bold += 1
        elif t.type == 'strong_close':
            bold = max(0, bold - 1)
        elif t.type == 'link_open':
            links.append(t.attrGet('href'))
        elif t.type == 'link_close':
            if links:
                links.pop()
        elif t.type in ('text', 'text_special', 'code_inline'):
            emit(t.content)
        elif t.type == 'image':
            emit(OBJ)
        elif t.type in ('softbreak', 'hardbreak'):
            emit(' ')
    return ''.join(out), marks


MARKUP = re.compile(r'[\\`*_]')
LEADING = re.compile(r'^(\s*)(?:([#+>-])|(\d+)([.)]))(\s|$)')


def escape_md(text: str) -> str:
    """Text typed in the Doc, written into the Markdown so that it reads back as the same text: a typed * or `
    stays a character (the blanks [__] stay as they are)."""
    return MARKUP.sub(lambda m: '\\' + m.group(0), text.replace('[__]', '\0')).replace('\0', '[__]')


def escape_lead(text: str) -> str:
    """A paragraph whose text starts like a heading, a list item or a quote stays a paragraph."""
    m = LEADING.match(text)
    if not m:
        return text
    if m.group(2):
        return m.group(1) + '\\' + text[len(m.group(1)):]
    at = m.start(4)
    return text[:at] + '\\' + text[at:]


def plain(md: str) -> str:
    return spans(md)[0]


def prefix(block: Block) -> str:
    if block.kind.startswith('h'):
        return '#' * int(block.kind[1]) + ' '
    if block.kind == 'li':
        return '  ' * block.level + '- '
    if block.kind == 'ol':
        return '  ' * block.level + f'{block.number or 1}. '
    return block.lead


def escape_cell(text: str) -> str:
    return text.replace('|', '\\|').replace('\n', ' ')


def rewrite(lines: list[str], edits: list[tuple[int, str, Block]]) -> str:
    """Apply (line, action, block) edits to the Markdown lines, bottom-up so earlier line numbers stay valid.
    replace / delete use block.first..block.last; cell rewrites one cell of the row at `line`; insert puts the
    block after `line` (-1: at the top), several inserts after the same line keep their order."""
    order = {'cell': 2, 'replace': 2, 'delete': 2, 'insert': 1}
    for _, (line, action, block) in sorted(enumerate(edits), key=lambda e: (e[1][0], order[e[1][1]], e[0]),
                                           reverse=True):
        if action == 'cell':
            cells = split_row(lines[line])
            cells[block.col] = escape_cell(block.md)
            lines[line] = '| ' + ' | '.join(cells) + ' |'
        elif action == 'replace':
            lines[block.first:block.last + 1] = [prefix(block) + block.md]
        elif action == 'delete':
            del lines[block.first:block.last + 1]
        else:
            lines[line + 1:line + 1] = ['', prefix(block) + block.md] if block.kind not in ('li', 'ol') \
                else [prefix(block) + block.md]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines))


# --- Google Doc side -------------------------------------------------------------------------

@dataclass
class Unit:
    kind: str
    text: str                   # what the unit reads as; a chip as its name, an image as OBJ, '\n' between cell paragraphs
    start: int
    end: int                    # one past the final newline
    level: int = 0
    runs: list = field(default_factory=list)      # [(text, textStyle)] in order; textStyle may carry 'object'
    table: int = -1
    row: int = -1
    col: int = -1
    pos: list = field(default_factory=list)       # Doc index where each character of `text` starts
    ext: list = field(default_factory=list)       # Doc index where each character ends
    locked: set = field(default_factory=set)      # characters of a chip, rich link or image: never cut into

    @property
    def key(self):
        return ('C', self.table, self.row, self.col) if self.kind == 'cell' else ('P', norm(self.text))

    @property
    def tail(self) -> int:
        """The index right after the unit's text (where its final newline sits)."""
        return self.ext[-1] if self.ext else self.start

    def at(self, k: int) -> int:
        return self.pos[k] if k < len(self.pos) else self.tail


def element_text(el: dict) -> tuple[str, dict, bool]:
    """(text, textStyle, locked) for one paragraph element."""
    if 'textRun' in el:
        return el['textRun'].get('content', ''), el['textRun'].get('textStyle', {}), False
    if 'person' in el:
        props = el['person'].get('personProperties', {})
        return props.get('name') or props.get('email') or OBJ, el['person'].get('textStyle', {}), True
    if 'richLink' in el:
        props = el['richLink'].get('richLinkProperties', {})
        return props.get('title') or props.get('uri') or OBJ, el['richLink'].get('textStyle', {}), True
    return OBJ, {}, True                             # image, footnote mark, page break, equation


def read_paragraph(par: dict, u: Unit):
    """Append one paragraph's characters to the unit, with the Doc index of each."""
    for el in par.get('elements', []):
        text, style, locked = element_text(el)
        start, end = el.get('startIndex', 0), el.get('endIndex', 0)
        u.runs.append((text, {**style, **({'object': True} if locked else {})}))
        at = start
        for ch in text:
            if locked:
                u.locked.add(len(u.text))
            u.pos.append(start if locked else at)
            at = end if locked else at + u16(ch)
            u.ext.append(at)
            u.text += ch


def paragraph_kind(par: dict, lists: dict, title: bool = False) -> tuple[str, int]:
    """`title`: the paragraph is among the first lines of the Doc, where a centred one is a title line (h1)."""
    style = par.get('paragraphStyle', {}).get('namedStyleType', 'NORMAL_TEXT')
    if title and style == 'NORMAL_TEXT' and not par.get('bullet') \
            and par.get('paragraphStyle', {}).get('alignment') == 'CENTER':
        return 'h1', 0
    if style.startswith('HEADING_'):
        return f'h{min(int(style[-1]), 6)}', 0
    if style == 'TITLE':
        return 'h1', 0
    if style == 'SUBTITLE':
        return 'h2', 0
    bullet = par.get('bullet')
    if bullet:
        level = bullet.get('nestingLevel', 0)
        levels = lists.get(bullet['listId'], {}).get('listProperties', {}).get('nestingLevels', [])
        glyph = levels[level].get('glyphType', '') if level < len(levels) else ''
        return ('ol' if glyph in ORDERED_GLYPHS else 'li'), level
    return 'p', 0


def trim_newline(u: Unit) -> Unit:
    if u.text.endswith('\n'):
        u.text, u.pos, u.ext = u.text[:-1], u.pos[:-1], u.ext[:-1]
        u.locked.discard(len(u.text))
    return u


TITLE_STYLES = ('HEADING_1', 'TITLE', 'SUBTITLE')


def title_lines(doc: dict) -> list:
    """The paragraphs of the two title lines on top (topic, 會議紀錄): at most two, before anything else."""
    found = []
    for el in doc.get('body', {}).get('content', []):
        if 'table' in el or len(found) == 2:
            break
        if 'paragraph' not in el:
            continue
        par = el['paragraph']
        text = ''.join(e.get('textRun', {}).get('content', '') for e in par.get('elements', []))
        if not text.strip():
            continue
        st = par.get('paragraphStyle', {})
        if par.get('bullet') or not (st.get('namedStyleType') in TITLE_STYLES
                                     or (st.get('namedStyleType', 'NORMAL_TEXT') == 'NORMAL_TEXT'
                                         and st.get('alignment') == 'CENTER')):
            break
        found.append(el)
    return found


def title_requests(doc: dict) -> list:
    """The title lines of a Doc made before 2026-10-15 are headings, which Google Docs lists in its outline on the
    left above 「一、」; they become centred normal text. Changing the paragraph's style clears the size, colour and
    bold of its text (seen 2026-10-15), so those are given again, as md_to_docx writes them; a line left without
    them by that first change gets them here too. Not the font: the Docs API takes Microsoft JhengHei without an
    error and keeps nothing (tried 2026-10-15), and the Doc shows its own font instead."""
    from md_to_docx import HEADING
    size, colour = HEADING['h1'][:2]
    look = {'bold': True, 'fontSize': {'magnitude': size, 'unit': 'PT'},
            'foregroundColor': {'color': {'rgbColor': {k: int(str(colour)[i:i + 2], 16) / 255
                                                       for k, i in (('red', 0), ('green', 2), ('blue', 4))}}}}
    reqs = []
    for el in title_lines(doc):
        par = el['paragraph']
        heading = par.get('paragraphStyle', {}).get('namedStyleType') in TITLE_STYLES
        runs = [e['textRun'] for e in par.get('elements', []) if e.get('textRun', {}).get('content', '').strip()]
        bare = any(not r.get('textStyle', {}).get('fontSize') for r in runs)
        rng = {'startIndex': el['startIndex'], 'endIndex': el['endIndex'] - 1}       # the newline keeps its own
        if heading:
            reqs.append({'updateParagraphStyle': {'range': {'startIndex': el['startIndex'], 'endIndex': el['endIndex']},
                                                  'paragraphStyle': {'namedStyleType': 'NORMAL_TEXT', 'alignment': 'CENTER'},
                                                  'fields': 'namedStyleType,alignment'}})
        if (heading or bare) and rng['endIndex'] > rng['startIndex']:
            reqs.append({'updateTextStyle': {'range': rng, 'textStyle': look,
                                             'fields': 'bold,fontSize,foregroundColor'}})
    return reqs


def units(doc: dict) -> list[Unit]:
    out: list[Unit] = []
    lists = doc.get('lists', {})
    table = -1
    titles = {el['startIndex'] for el in title_lines(doc)}
    for el in doc.get('body', {}).get('content', []):
        if 'paragraph' in el:
            kind, level = paragraph_kind(el['paragraph'], lists, el['startIndex'] in titles)
            u = Unit(kind, '', el['startIndex'], el['endIndex'], level)
            read_paragraph(el['paragraph'], u)
            out.append(trim_newline(u))
        elif 'table' in el:
            table += 1
            for r, row in enumerate(el['table'].get('tableRows', [])):
                for c, cell in enumerate(row.get('tableCells', [])):
                    pars = [p for p in cell.get('content', []) if 'paragraph' in p]
                    u = Unit('cell', '', pars[0]['startIndex'], pars[-1]['endIndex'], table=table, row=r, col=c)
                    for p in pars:
                        read_paragraph(p['paragraph'], u)
                    out.append(trim_newline(u))
    return out


def worded(blocks: list) -> list:
    """The Markdown's blocks that have words. A paragraph holding only a picture (「八、補充資訊」, attachments.py)
    is kept for the Word file; in the Doc the picture is placed by itself and takes no part in syncing."""
    return [b for b in blocks if b.kind == 'cell' or norm(b.plain)]


def comparable(us: list) -> list:
    """Empty paragraphs (a colleague pressing Enter twice) take no part in matching; empty cells do."""
    return [u for u in us if u.kind == 'cell' or norm(u.text)]


def shapes(items) -> list[tuple[int, int]]:
    """(rows, columns) of every table, from Blocks or Units."""
    found: dict[int, list[int]] = {}
    for it in items:
        if it.kind == 'cell':
            rows, cols = found.setdefault(it.table, [0, 0])
            found[it.table] = [max(rows, it.row + 1), max(cols, it.col + 1)]
    return [tuple(found[t]) for t in sorted(found)]


def runs_to_md(u: Unit, header: bool = False) -> str:
    """A Doc unit as inline Markdown. Headings and table header cells are bold by layout, not by markup; a chip
    keeps its name; an image has no Markdown here and drops out."""
    whole_bold = u.kind.startswith('h') or header
    merged: list[list] = []
    for t, style in u.runs:
        t = t.replace(OBJ, '').replace('\x0b', ' ').replace('\n', ' ')
        if not t:
            continue
        bold = bool(style.get('bold')) and not whole_bold and not style.get('object')
        link = (style.get('link') or {}).get('url') if not style.get('object') else None
        if merged and merged[-1][1] == bold and merged[-1][2] == link:
            merged[-1][0] += t
        else:
            merged.append([t, bold, link])
    out = ''
    for t, bold, link in merged:
        lead, trail, core = t[:len(t) - len(t.lstrip())], t[len(t.rstrip()):], t.strip()
        if not core:
            out += t
            continue
        core = escape_md(core)
        if link:
            core = f'[{core}]({link})'
        if bold:
            core = f'**{core}**'
        out += lead + core + trail
    out = out.strip()
    return escape_lead(out) if u.kind == 'p' else out


def doc_to_md(doc: dict) -> str:
    """The whole Doc as minutes Markdown, for when its tables changed shape and paragraphs cannot be matched."""
    out: list[str] = []
    rows: dict = {}
    number = 0

    def flush_table():
        if not rows:
            return
        width = max(len(r) for r in rows.values())
        for r in sorted(rows):
            cells = rows[r] + [''] * (width - len(rows[r]))
            out.append('| ' + ' | '.join(cells) + ' |')
            if r == 0:
                out.append('|' + '---|' * width)
        out.append('')
        rows.clear()

    prev = ''
    for u in units(doc):
        if u.kind == 'cell':
            if not rows and out and out[-1] != '':
                out.append('')
            rows.setdefault(u.row, []).append(escape_cell(runs_to_md(u, header=u.row == 0)))
            prev = 'cell'
            continue
        flush_table()
        if not norm(u.text):
            continue
        number = number + 1 if u.kind == 'ol' and prev == 'ol' else 1
        block = Block(u.kind, runs_to_md(u), 0, 0, level=u.level, number=number)
        if out and out[-1] != '' and not (u.kind in ('li', 'ol') and prev in ('li', 'ol')):
            out.append('')
        out.append(prefix(block) + block.md)
        prev = u.kind
    flush_table()
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(out)).strip('\n') + '\n'


# --- matching ---------------------------------------------------------------------------------

def match(a_keys: list, b_keys: list) -> dict[int, int]:
    """Index in a -> index in b for every unit both sides have unchanged."""
    found = {}
    for i, j, size in difflib.SequenceMatcher(None, a_keys, b_keys, autojunk=False).get_matching_blocks():
        for k in range(size):
            found[i + k] = j + k
    return found


def edit_span(old: str, new: str) -> tuple[int, int, int]:
    """Shared prefix length and the old / new suffix starts: old[p:os] becomes new[p:ns]."""
    p = 0
    while p < len(old) and p < len(new) and old[p] == new[p]:
        p += 1
    s = 0
    while s < len(old) - p and s < len(new) - p and old[len(old) - 1 - s] == new[len(new) - 1 - s]:
        s += 1
    return p, len(old) - s, len(new) - s


def changed_words(old: str, new: str) -> tuple[str, str]:
    """The words that differ, widened to whole Latin words and numbers ("10 萬" -> "12 萬" reads 10 -> 12)."""
    p, oe, ne = edit_span(old, new)
    word = re.compile(r'[A-Za-z0-9]')
    while p > 0 and word.match(old[p - 1]):
        p -= 1
    while oe < len(old) and ne < len(new) and word.match(old[oe]):
        oe, ne = oe + 1, ne + 1
    tidy = lambda t: re.sub(r'^[，。、；,.;\s]+|[，。、；,.;\s]+$', '', t)   # noqa: E731
    return tidy(old[p:oe]), tidy(new[p:ne])


def similar(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.5


# --- carry: what the user typed, onto the Markdown -------------------------------------------

def carry(base_md: str, before_md: str, after_md: str) -> tuple[str, list[tuple[str, str]]]:
    """Apply the change before_md -> after_md to base_md. before_md is base_md as some lossy path read it (the
    preview read back, Claude's draft); paragraphs it did not change keep base_md's own Markdown, so nothing the
    path lost is lost from the minutes. Returns the new Markdown and, for every changed paragraph that base_md no
    longer has as before_md had it, (its text in before_md, its text in after_md): those are left alone."""
    lines, base = parse(base_md)
    _, before = parse(before_md)
    _, after = parse(after_md)
    if shapes(before) != shapes(after):
        raise Structural('the edit adds or removes table rows or columns')
    to_base = match([b.key for b in before], [b.key for b in base])
    edits: list[tuple[int, str, Block]] = []
    skipped: list[tuple[str, str]] = []
    # cells are matched by position, which only means the same cell while the table has the same rows
    steady = shapes(before) == shapes(base)

    def placed(i: int) -> Block | None:
        j = to_base.get(i)
        return base[j] if j is not None else None

    def anchor_line(i: int) -> int:
        """The Markdown line after which something that came after before[i] goes."""
        while i >= 0:
            b = placed(i)
            if b is not None:
                return b.last
            i -= 1
        return -1

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [b.key for b in before], [b.key for b in after],
                                                       autojunk=False).get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                old, new = before[i1 + k], after[j1 + k]
                b = placed(i1 + k)
                if old.kind != 'cell' or norm(old.plain) == norm(new.plain):
                    continue
                if b is None or not steady or norm(b.plain) != norm(old.plain):
                    skipped.append((old.plain, new.plain))   # rows moved, or someone else changed this cell since
                    continue
                edits.append((b.first, 'cell', Block('cell', new.md, b.first, b.last, table=b.table, row=b.row,
                                                     col=b.col)))
            continue
        if any(before[i].kind == 'cell' for i in range(i1, i2)) or any(after[j].kind == 'cell' for j in range(j1, j2)):
            raise Structural('table cells moved')
        pairs = min(i2 - i1, j2 - j1)
        for k in range(pairs):
            b, new = placed(i1 + k), after[j1 + k]
            if b is None:
                skipped.append((before[i1 + k].plain, new.plain))
                continue
            edits.append((b.first, 'replace', Block(new.kind, new.md, b.first, b.last, level=new.level,
                                                    number=b.number or new.number, lead=b.lead if new.kind == 'p' else '')))
        line = anchor_line(i1 + pairs - 1)
        for k in range(pairs, j2 - j1):
            new = after[j1 + k]
            edits.append((line, 'insert', Block(new.kind, new.md, line, line, level=new.level, number=new.number)))
        for k in range(pairs, i2 - i1):
            b = placed(i1 + k)
            if b is not None:
                edits.append((b.first, 'delete', b))
    return rewrite(lines, edits), skipped


# --- pull: the Doc's current state into the Markdown -------------------------------------------

@dataclass
class Change:
    kind: str                   # 'edit', 'add', 'remove'
    before: str                 # the words that were there ('' for add)
    after: str                  # the words now there ('' for remove)
    context: str                # the whole unit's text afterwards, to find the words in the preview
    block: int                  # index of the unit in the merged Markdown's blocks (-1 for remove)


def merge_remote(md: str, doc: dict) -> tuple[str, list[Change]]:
    """Write every paragraph the Doc has differently into the Markdown. Raises Structural when tables changed shape."""
    lines, blocks = parse(md)
    blocks = worded(blocks)
    us = comparable(units(doc))
    if shapes(blocks) != shapes(us):
        raise Structural('the tables in the Doc have a different number of rows or columns')
    bk, uk = [b.key for b in blocks], [u.key for u in us]
    changes: list[Change] = []
    edits: list[tuple[int, str, Block]] = []

    def unit_md(u: Unit) -> str:
        return runs_to_md(u, u.kind == 'cell' and u.row == 0)

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, bk, uk, autojunk=False).get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                b, u = blocks[i1 + k], us[j1 + k]
                if b.kind == 'cell' and norm(b.plain) != norm(u.text):
                    edits.append((b.first, 'cell', Block('cell', unit_md(u), b.first, b.last, table=b.table,
                                                         row=b.row, col=b.col)))
                    before, after = changed_words(b.plain, u.text)
                    changes.append(Change('edit', before, after, u.text, i1 + k))
            continue
        if any(blocks[i].kind == 'cell' for i in range(i1, i2)) or any(us[j].kind == 'cell' for j in range(j1, j2)):
            raise Structural('table cells moved')
        pairs = min(i2 - i1, j2 - j1)
        for k in range(pairs):
            b, u = blocks[i1 + k], us[j1 + k]
            edits.append((b.first, 'replace', Block(u.kind, unit_md(u), b.first, b.last, level=u.level,
                                                    number=b.number, lead=b.lead if u.kind == 'p' else '')))
            before, after = changed_words(b.plain, u.text)
            changes.append(Change('edit', before, after, u.text, i1 + k))
        anchor = i1 + pairs - 1 if pairs else i1 - 1
        after = blocks[anchor].last if anchor >= 0 else -1
        for k in range(pairs, j2 - j1):
            u = us[j1 + k]
            edits.append((after, 'insert', Block(u.kind, unit_md(u), after, after, level=u.level,
                                                 number=1 if u.kind == 'ol' else 0)))
            changes.append(Change('add', '', norm(u.text), u.text, -1))
        for k in range(pairs, i2 - i1):
            b = blocks[i1 + k]
            edits.append((b.first, 'delete', b))
            changes.append(Change('remove', b.plain, '', '', -1))
    merged = rewrite(lines, edits)
    _, merged_blocks = parse(merged)                 # block indexes in the merged file, for the preview marks
    for ch in changes:
        if ch.kind != 'remove':
            ch.block = next((i for i, b in enumerate(merged_blocks) if norm(b.plain) == norm(ch.context)), -1)
    return merged, changes


# --- push: the edit between two Markdown versions into the Doc --------------------------------

@dataclass
class Plan:
    requests: list
    conflicts: list[str]        # units the user changed that a colleague changed first, or that hold a chip; left alone
    expected: list[tuple[bool, str]]   # (is a cell, text) of the Doc's units once the requests ran


def look_of(style: dict | None) -> dict:
    """The look inserted text copies from its neighbour; never a blank's red (see blank_requests)."""
    keys = [k for k in LOOK if not (k == 'foregroundColor' and blank_look(style))]
    return {k: style[k] for k in keys if style and k in style}


def style_requests(at: int, text: str, marks: list, bold_all: bool, look: dict | None) -> list:
    """Inserted text takes the look of the text it joins (font, size, colour), bold and links from the Markdown."""
    text = text.replace(OBJ, '')
    end = at + u16(text)
    base = {**look_of(look), 'bold': bold_all}
    fields = ['bold', 'link'] + [k for k in LOOK if look is not None]
    if blank_look(look):                             # next to a blank, Google gives inserted text its pale red too
        fields.append('backgroundColor')
    reqs = [{'updateTextStyle': {'range': {'startIndex': at, 'endIndex': end}, 'textStyle': base,
                                 'fields': ','.join(fields)}}]
    for s, e, bold, link in marks:
        s, e = max(s, 0), min(e, len(text))
        if e <= s:
            continue
        rng = {'startIndex': at + u16(text[:s]), 'endIndex': at + u16(text[:e])}
        style, keys = {}, []
        if bold and not bold_all:
            style['bold'], keys = True, keys + ['bold']
        if link:
            style['link'], keys = {'url': link}, keys + ['link']
        if keys:
            reqs.append({'updateTextStyle': {'range': rng, 'textStyle': style, 'fields': ','.join(keys)}})
    return reqs


def run_style_at(u: Unit, k: int) -> dict | None:
    """The textStyle of the run holding character k of the unit (or the last one before it), chips skipped."""
    seen, found = 0, None
    for text, style in u.runs:
        if not style.get('object'):
            found = style
        if seen + len(text) > k and not style.get('object'):
            return style
        seen += len(text)
    return found


def bold_requests(u: Unit, marks: list) -> list:
    """Same words, different bold: change only the characters whose weight differs."""
    want = [False] * len(u.text)
    for s, e, bold, _ in marks:
        for k in range(max(s, 0), min(e, len(want))):
            want[k] = want[k] or bold
    have: list[bool] = []
    for text, style in u.runs:
        have += [bool(style.get('bold'))] * len(text)
    have = (have + [False] * len(want))[:len(want)]
    reqs, k = [], 0
    while k < len(want):
        if k in u.locked or want[k] == have[k]:
            k += 1
            continue
        j = k
        while j < len(want) and j not in u.locked and want[j] == want[k] and want[j] != have[j]:
            j += 1
        reqs.append({'updateTextStyle': {'range': {'startIndex': u.pos[k], 'endIndex': u.ext[j - 1]},
                                         'textStyle': {'bold': want[k]}, 'fields': 'bold'}})
        k = j
    return reqs


def text_requests(u: Unit, new_md: str, bold_all: bool) -> list | None:
    """Replace the differing middle of one unit's text; None when that would cut into a chip or an image."""
    new, marks = spans(new_md)
    # images and footnote marks are never typed: compare both sides without them, then map back to Doc positions
    if OBJ in new:
        before = [0]
        for ch in new:
            before.append(before[-1] + (ch != OBJ))
        marks = [(before[s], before[e], b, link) for s, e, b, link in marks if before[e] > before[s]]
        new = new.replace(OBJ, '')
    seen = [k for k, ch in enumerate(u.text) if ch != OBJ]
    old = ''.join(u.text[k] for k in seen)
    p, oe, ne = edit_span(old, new)
    first = seen[p] if p < len(seen) else len(u.text)
    last = seen[oe - 1] + 1 if oe > p else first
    if any(k in u.locked for k in range(first, last)) or (oe == p and first in u.locked and first - 1 in u.locked):
        return None
    start = u.at(first)
    end = u.ext[last - 1] if last > first else start
    reqs = []
    if end > start:
        reqs.append({'deleteContentRange': {'range': {'startIndex': start, 'endIndex': end}}})
    inserted = new[p:ne]
    if inserted:
        reqs.append({'insertText': {'location': {'index': start}, 'text': inserted}})
        look = run_style_at(u, first if first < len(u.text) else max(first - 1, 0))
        reqs += style_requests(start, inserted, [(s - p, e - p, b, l) for s, e, b, l in marks if e > p and s < ne],
                               bold_all, look)
    elif old == new and not bold_all:
        to_doc = lambda k: seen[k] if k < len(seen) else len(u.text)   # noqa: E731
        reqs += bold_requests(u, [(to_doc(s), to_doc(e - 1) + 1 if e > s else to_doc(s), b, l)
                                  for s, e, b, l in marks])
    return reqs


def kind_requests(start: int, end: int, have: str, want: str) -> list:
    """Paragraph style and bullets for the paragraphs in [start, end) that are `have` and should be `want`."""
    if have == want:
        return []
    rng = {'startIndex': start, 'endIndex': end}
    reqs = []
    if have in PRESET:
        reqs.append({'deleteParagraphBullets': {'range': rng}})
        reqs.append({'updateParagraphStyle': {'range': rng, 'paragraphStyle': {
            'indentStart': {'magnitude': 0, 'unit': 'PT'}, 'indentFirstLine': {'magnitude': 0, 'unit': 'PT'}},
            'fields': 'indentStart,indentFirstLine'}})
    if NAMED.get(have) != NAMED.get(want):
        reqs.append({'updateParagraphStyle': {'range': rng, 'paragraphStyle': {'namedStyleType': NAMED[want]},
                                              'fields': 'namedStyleType'}})
    if (have == 'h1') != (want == 'h1'):                 # a title line is told apart by being centred
        reqs.append({'updateParagraphStyle': {'range': rng, 'paragraphStyle': {
            'alignment': 'CENTER' if want == 'h1' else 'START'}, 'fields': 'alignment'}})
    if want in PRESET:
        reqs.append({'createParagraphBullets': {'range': rng, 'bulletPreset': PRESET[want]}})
    return reqs


def plan_push(doc: dict, base_md: str, new_md: str) -> Plan:
    """What to send so the Doc gets every change between base_md and new_md, and nothing else."""
    base = worded(parse(base_md)[1])
    new = worded(parse(new_md)[1])
    every = units(doc)
    us = comparable(every)
    if shapes(base) != shapes(new):
        raise Structural('the edit adds or removes table rows or columns')
    if shapes(us) != shapes(base):
        raise Structural('a table in the Doc changed shape since the last sync')
    to_doc = match([b.key for b in base], [u.key for u in us])
    header_rows = {(b.table, 0) for b in new if b.kind == 'cell'}
    ops: list[tuple[int, int, list]] = []           # (anchor index, priority, requests)
    conflicts: list[str] = []
    expected = [(u.kind == 'cell', u.text) for u in us]    # simulated as the plan grows
    sim_insert: dict[int, list] = {}                 # unit index -> units inserted before it
    sim_after: dict[int, list] = {}                  # unit index -> units inserted after it
    removed: set[int] = set()

    def look_for(kind: str) -> dict | None:
        """The look of text in an existing paragraph of this kind (or any body paragraph)."""
        for want in (kind, 'p', 'li'):
            u = next((x for x in us if x.kind == want and x.runs), None)
            if u is not None:
                return run_style_at(u, 0)
        return None

    def unit_for(i: int) -> Unit | None:
        j = to_doc.get(i)
        return us[j] if j is not None else None

    def same(i: int) -> bool:
        u = unit_for(i)
        return u is not None and norm(u.text) == norm(base[i].plain)

    def replace(i: int, nb: Block):
        u = unit_for(i)
        if u is None or norm(u.text) != norm(base[i].plain):
            conflicts.append(base[i].plain)
            return
        bold_all = nb.kind.startswith('h') or (nb.kind == 'cell' and (nb.table, nb.row) in header_rows)
        reqs = text_requests(u, nb.md, bold_all)
        if reqs is None:
            conflicts.append(base[i].plain)
            return
        if u.kind != 'cell' and u.kind != nb.kind:
            reqs += kind_requests(u.start, u.start + 1, u.kind, nb.kind)
        if reqs:
            ops.append((u.start, 2, reqs))
            expected[to_doc[i]] = (nb.kind == 'cell', plain(nb.md))

    def past_pictures(u: Unit) -> Unit:
        """The paragraphs holding only a picture right after `u` belong to it (「八、補充資訊」 puts a picture under
        its line): text added after `u` goes after them."""
        k = next(i for i, x in enumerate(every) if x is u)
        while k + 1 < len(every) and every[k + 1].kind != 'cell' and every[k + 1].text \
                and not every[k + 1].text.replace(OBJ, '').strip():
            k += 1
        return every[k]

    def insert(blocks_new: list[Block], before: int | None, after: int | None):
        """New units between base unit `after` and base unit `before` (either may be None)."""
        nxt = unit_for(before) if before is not None else None
        prv = unit_for(after) if after is not None else None
        texts = [plain(b.md).replace(OBJ, '') for b in blocks_new]
        # after a list item of the same kind, so the new item joins that list (numbering continues)
        if prv is not None and prv.kind == blocks_new[0].kind and prv.kind in PRESET:
            nxt = None
        if nxt is not None and nxt.kind != 'cell':
            at, payload, anchor_kind, first = nxt.start, '\n'.join(texts) + '\n', nxt.kind, nxt.start
            sim_insert.setdefault(to_doc[before], []).extend((False, t) for t in texts)
        elif prv is not None and prv.kind != 'cell':
            anchor = past_pictures(prv)
            at, payload, anchor_kind = anchor.end - 1, '\n' + '\n'.join(texts), anchor.kind
            first = at + 1
            sim_after.setdefault(to_doc[after], []).extend((False, t) for t in texts)
        elif nxt is None and prv is None and (before is not None or not us):
            conflicts.extend(texts)                 # both neighbours were changed by a colleague
            return
        elif nxt is None and prv is None:
            # at the very end of the minutes, after a paragraph a colleague changed: still the end of the Doc
            last = us[-1]
            if last.kind == 'cell':
                spare = next((x for x in every if x.kind != 'cell' and not norm(x.text) and x.start >= last.end), None)
                if spare is None:
                    conflicts.extend(texts)
                    return
                at, payload, anchor_kind, first = spare.start, '\n'.join(texts) + '\n', spare.kind, spare.start
            else:
                last = past_pictures(last)
                at, payload, anchor_kind = last.end - 1, '\n' + '\n'.join(texts), last.kind
                first = at + 1
            sim_after.setdefault(len(us) - 1, []).extend((False, t) for t in texts)
        else:
            # right after a table: Google keeps an empty paragraph there (always at the end of a Doc); write into it
            low = prv.end if prv is not None else 0
            high = nxt.start if nxt is not None else float('inf')
            spare = next((x for x in every if x.kind != 'cell' and not norm(x.text) and low <= x.start < high), None)
            if spare is None:
                raise Structural('new paragraphs right next to a table')
            at, payload, anchor_kind, first = spare.start, '\n'.join(texts) + '\n', spare.kind, spare.start
            if prv is not None:
                sim_after.setdefault(to_doc[after], []).extend((False, t) for t in texts)
            else:
                sim_insert.setdefault(to_doc[before], []).extend((False, t) for t in texts)
        reqs = [{'insertText': {'location': {'index': at}, 'text': payload}}]
        pos = first
        for b, t in zip(blocks_new, texts):
            reqs += kind_requests(pos, pos + u16(t) + 1, anchor_kind, b.kind)
            _, marks = spans(b.md)
            if t:
                reqs += style_requests(pos, t, marks, b.kind.startswith('h'), look_for(b.kind))
            pos += u16(t) + 1
        ops.append((at, 1, reqs))

    def delete(i: int):
        if not same(i):
            conflicts.append(base[i].plain)
            return
        j = to_doc[i]
        u = us[j]
        if u.kind == 'cell':
            raise Structural('a table cell would be removed')
        body_end = max(x.end for x in every)
        following = next((x for x in every if x.start >= u.end), None)
        if following is not None and following.kind == 'cell':
            # the newline right before a table cannot be deleted: empty the paragraph and make it plain instead
            reqs = [{'deleteContentRange': {'range': {'startIndex': u.start, 'endIndex': u.end - 1}}}] \
                if u.end - 1 > u.start else []
            reqs += kind_requests(u.start, u.start + 1, u.kind, 'p')
            ops.append((u.start, 2, reqs))
            removed.add(j)
            return
        if u.end >= body_end:                        # the Doc's last newline cannot go; take the one before it
            prev = us[j - 1] if j > 0 else None
            if prev is None or prev.kind == 'cell':
                ops.append((u.start, 2, [{'deleteContentRange': {'range': {'startIndex': u.start,
                                                                           'endIndex': u.end - 1}}}]))
            else:
                ops.append((prev.end - 1, 2, [{'deleteContentRange': {'range': {'startIndex': prev.end - 1,
                                                                                'endIndex': u.end - 1}}}]))
        else:
            ops.append((u.start, 2, [{'deleteContentRange': {'range': {'startIndex': u.start, 'endIndex': u.end}}}]))
        removed.add(j)

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [b.key for b in base], [b.key for b in new],
                                                       autojunk=False).get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                b, n = base[i1 + k], new[j1 + k]
                if b.md != n.md and (b.kind == 'cell' or norm(b.plain) == norm(n.plain)):
                    replace(i1 + k, n)               # a cell's words, or only the bold, changed
            continue
        if any(base[i].kind == 'cell' for i in range(i1, i2)) or any(new[j].kind == 'cell' for j in range(j1, j2)):
            raise Structural('table cells moved')
        pairs = min(i2 - i1, j2 - j1)
        for k in range(pairs):
            replace(i1 + k, new[j1 + k])
        if j2 - j1 > pairs:
            after = i1 + pairs - 1 if pairs else (i1 - 1 if i1 > 0 else None)
            insert(new[j1 + pairs:j2], i2 if i2 < len(base) else None, after)
        for k in range(pairs, i2 - i1):
            delete(i1 + k)

    # bottom-up: an operation only moves text after its anchor, so lower anchors stay valid
    requests = [r for _, _, reqs in sorted(ops, key=lambda o: (o[0], o[1]), reverse=True) for r in reqs]
    sim: list = []
    for j, unit in enumerate(expected):
        sim += sim_insert.get(j, [])
        if j not in removed:
            sim.append(unit)
        sim += sim_after.get(j, [])
    return Plan(requests, conflicts, sim)


def reads_as(doc: dict, md: str) -> bool:
    """The Doc has exactly the words of this Markdown, unit by unit."""
    got = [norm(u.text) for u in comparable(units(doc))]
    want = [norm(b.plain) for b in parse(md)[1] if b.kind == 'cell' or norm(b.plain)]
    return got == want


def tables_changed(doc: dict, md: str) -> bool:
    """Someone added or removed table rows or columns in the Doc since it matched this Markdown."""
    return shapes(comparable(units(doc))) != shapes(parse(md)[1])


# --- blanks ----------------------------------------------------------------------------------------------------
# Every [__] in the Doc stands out: red letters on a pale red ground, and the window makes that colour blink
# (recorder/app/docblink.js). Letters typed into a blank take its look in Google Docs; once they no longer read
# [__], they go back to plain text.
BLANK = '[__]'
BLANK_INK = {'red': 0.773, 'green': 0.133, 'blue': 0.122}           # #C5221F
BLANK_GROUND = {'red': 0.992, 'green': 0.878, 'blue': 0.863}        # #FDE0DC


def blank_look(style: dict | None) -> bool:
    """Text painted as a blank: the blank's red letters or its pale red ground."""
    def near(key, want):
        rgb = (((style or {}).get(key) or {}).get('color') or {}).get('rgbColor')
        return rgb is not None and all(abs(rgb.get(k, 0) - v) < 0.02 for k, v in want.items())
    return near('foregroundColor', BLANK_INK) or near('backgroundColor', BLANK_GROUND)


def blank_requests(doc: dict) -> list:
    """The style changes that give every [__] in the Doc the blank's look, and take it off everything else."""
    paint, plain = [], []

    def paragraph(par: dict):
        chars = []                                   # (character, Doc index or None for a chip or image, painted)
        for el in par.get('elements', []):
            run = el.get('textRun')
            if run is None:
                chars.append((OBJ, None, False))
                continue
            at, painted = el.get('startIndex', 0), blank_look(run.get('textStyle'))
            for ch in run.get('content', ''):
                chars.append((ch, at, painted))
                at += u16(ch)
        text = ''.join(c for c, _, _ in chars)
        wanted = set()
        i = text.find(BLANK)
        while i >= 0:
            wanted.update(range(i, i + len(BLANK)))
            i = text.find(BLANK, i + len(BLANK))
        for k, (ch, at, painted) in enumerate(chars):
            if at is None or (k in wanted) == painted:
                continue
            (paint if k in wanted else plain).append((at, at + u16(ch)))

    def walk(content: list):
        for el in content:
            if 'paragraph' in el:
                paragraph(el['paragraph'])
            for row in el.get('table', {}).get('tableRows', []):
                for cell in row.get('tableCells', []):
                    walk(cell.get('content', []))

    walk(doc.get('body', {}).get('content', []))

    def ranges(spans: list) -> list:
        merged: list[list[int]] = []
        for a, b in sorted(spans):
            if merged and merged[-1][1] == a:
                merged[-1][1] = b
            else:
                merged.append([a, b])
        return merged

    look = {'foregroundColor': {'color': {'rgbColor': BLANK_INK}},
            'backgroundColor': {'color': {'rgbColor': BLANK_GROUND}}}
    fields = 'foregroundColor,backgroundColor'
    return ([{'updateTextStyle': {'range': {'startIndex': a, 'endIndex': b}, 'textStyle': look, 'fields': fields}}
             for a, b in ranges(paint)]
            + [{'updateTextStyle': {'range': {'startIndex': a, 'endIndex': b}, 'textStyle': {}, 'fields': fields}}
               for a, b in ranges(plain)])


def check_result(doc: dict, plan: Plan) -> bool:
    """The Doc after the push reads exactly as planned (paragraphs emptied by the edit drop out on both sides)."""
    got = [norm(u.text) for u in comparable(units(doc))]
    want = [norm(t) for cell, t in plan.expected if cell or norm(t)]
    return got == want


# --- Google calls ----------------------------------------------------------------------------

def authorize():
    if not AUTH:
        sys.path.insert(0, str(Path(__file__).parent))
        from google_setup import access_token
        AUTH['Authorization'] = 'Bearer ' + access_token()


def call(url: str, body: dict | None = None, method: str | None = None):
    authorize()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ('POST' if data else 'GET'),
                                 headers={**AUTH, **({'Content-Type': 'application/json'} if data else {})})
    try:
        raw = urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as err:
        text = err.read().decode(errors='replace')
        if 'SERVICE_DISABLED' in text or 'has not been used' in text:
            raise SystemExit('GOOGLE DOCS API DISABLED: turn on the Google Docs API in the Cloud project') from None
        raise SystemExit(f'HTTP {err.code} from Google: {text[:300]}') from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as err:
        raise SystemExit(f'OFFLINE: Google did not answer ({err})') from None
    return json.loads(raw) if raw else {}


def get_doc(doc_id: str) -> dict:
    return call(DOCS + doc_id + '?suggestionsViewMode=PREVIEW_WITHOUT_SUGGESTIONS')


def get_doc_inline(doc_id: str) -> dict:
    """The Doc with colleagues' suggestions in place: the positions a style change or a picture is sent with."""
    return call(DOCS + doc_id + '?suggestionsViewMode=SUGGESTIONS_INLINE')


def has_suggestions(doc: dict) -> bool:
    """A colleague's suggested insertion or deletion is waiting: positions in the Doc may still move."""
    text = json.dumps(doc.get('body', {}))
    return '"suggestedInsertionIds"' in text or '"suggestedDeletionIds"' in text


def batch_update(doc_id: str, requests: list, revision: str | None) -> dict:
    body = {'requests': requests}
    if revision:
        body['writeControl'] = {'requiredRevisionId': revision}
    return call(DOCS + doc_id + ':batchUpdate', body)


def push(doc_id: str, base_md: str, new_md: str, tries: int = 2) -> tuple[Plan, dict, bool]:
    """Send the edit; (plan, the Doc afterwards, whether it reads as planned). A colleague typing at the same
    moment makes the revision check fail; then plan again."""
    for attempt in range(tries):
        doc = get_doc(doc_id)
        if reads_as(doc, new_md) and not reads_as(doc, base_md):
            return Plan([], [], []), doc, True       # an earlier push got there although its answer was lost
        plan = plan_push(doc, base_md, new_md)
        if not plan.requests:
            return plan, doc, True
        try:
            batch_update(doc_id, plan.requests, doc.get('revisionId'))
        except SystemExit as err:
            if 'HTTP 400' in str(err) and 'revision' in str(err).lower() and attempt + 1 < tries:
                continue
            if str(err).startswith('OFFLINE'):       # sent, but did it arrive? the next save must not send it twice
                try:
                    after = get_doc(doc_id)
                except SystemExit:
                    raise err from None
                if check_result(after, plan):
                    return plan, after, True
            raise
        after = get_doc(doc_id)
        return plan, after, check_result(after, plan)
    raise SystemExit(BUSY)


def paint_blanks(doc_id: str, doc: dict) -> str:
    """Give the Doc's blanks their look (blank_requests), and the title lines of an older Doc theirs
    (title_requests). The Doc's revision afterwards; '' when nothing needed
    changing, or when someone typed since `doc` was read (the next sync paints them), or the Doc cannot be edited."""
    requests = title_requests(doc) + blank_requests(doc)
    if not requests:
        return ''
    try:
        done = batch_update(doc_id, requests, doc.get('revisionId'))
    except SystemExit:
        return ''
    return (done.get('writeControl') or {}).get('requiredRevisionId', '')


def revisions_since(doc_id: str, since: str) -> list[dict]:
    """Who changed the Doc after `since` (RFC 3339), oldest first."""
    out, token = [], ''
    while True:
        page = call(DRIVE + doc_id + '/revisions?pageSize=200&fields=nextPageToken,revisions(id,modifiedTime,'
                    'lastModifyingUser(displayName,emailAddress,me))' + (f'&pageToken={urllib.parse.quote(token)}'
                                                                         if token else ''))
        out += [r for r in page.get('revisions', []) if r.get('modifiedTime', '') > since]
        token = page.get('nextPageToken')
        if not token:
            return out


def modified_time(doc_id: str) -> str:
    """When the Doc last changed (RFC 3339), as Drive reports it."""
    return call(DRIVE + doc_id + '?fields=modifiedTime').get('modifiedTime', '')


def comments(doc_id: str) -> list[dict]:
    out, token = [], ''
    fields = ('nextPageToken,comments(id,content,createdTime,modifiedTime,resolved,deleted,'
              'quotedFileContent(value),author(displayName,emailAddress,me),'
              'replies(id,content,createdTime,action,deleted,author(displayName,emailAddress,me)))')
    while True:
        page = call(DRIVE + doc_id + f'/comments?pageSize=100&includeDeleted=false&fields={fields}'
                    + (f'&pageToken={urllib.parse.quote(token)}' if token else ''))
        out += page.get('comments', [])
        token = page.get('nextPageToken')
        if not token:
            return out


def reply(doc_id: str, comment_id: str, text: str) -> dict:
    cid = urllib.parse.quote(comment_id, safe='')
    return call(DRIVE + f'{doc_id}/comments/{cid}/replies?fields=id,content,createdTime,author(displayName,me)',
                {'content': text})


def resolve(doc_id: str, comment_id: str) -> dict:
    cid = urllib.parse.quote(comment_id, safe='')
    return call(DRIVE + f'{doc_id}/comments/{cid}/replies?fields=id,action', {'action': 'resolve'})


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == 'units':
        for u in units(get_doc(sys.argv[2])):
            print(f'[{u.start}-{u.end}] {u.kind}{u.level or ""} {u.table if u.kind == "cell" else ""} {u.text!r}')
    elif len(sys.argv) >= 5 and sys.argv[1] == 'plan':
        plan = plan_push(get_doc(sys.argv[2]), Path(sys.argv[3]).read_text(encoding='utf-8'),
                         Path(sys.argv[4]).read_text(encoding='utf-8'))
        print(json.dumps({'requests': plan.requests, 'conflicts': plan.conflicts}, ensure_ascii=False, indent=1))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
