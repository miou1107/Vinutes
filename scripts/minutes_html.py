"""The minutes as the recorder app's preview shows them, back into Markdown.

Usage:
  minutes_html.py back <edited.html> <minutes.md>   write what the user typed in the preview back into the Markdown

The preview (recorder/app, rendered by minutes_app.py) is one contenteditable block. A few seconds after the user
stops typing, the window hands its HTML to the app, and minutes_app.py save calls back() and sends the changed
paragraphs to the Google Doc. back() understands the tags markdown-it writes (headings, paragraphs, bold, italics,
links, images, lists, tables) plus what WebKit adds while editing (div, br, span, b, i, font); anything the
window itself added (comment numbers, marked with data-ui) is left out.
"""
from __future__ import annotations

import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


BLANK = '[__]'
MARKUP = re.compile(r'[\\`*_]')


class Back(HTMLParser):
    """Rebuilds Markdown from the edited page. Blocks are collected as lines; inline text keeps **, *, links."""

    BLOCK = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'table', 'ul', 'ol', 'br'}
    HEADS = ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.line = ''
        self.prefix = ''
        self.lists: list[list] = []       # [kind, counter]
        self.link: list[str] = []
        self.row: list[str] | None = None
        self.cell: str | None = None
        self.header_done = False
        self.in_head = False
        self.skip = 0                     # inside an element the app added (data-ui): comment numbers, marks
        self.code = False

    # text goes into the current table cell, or the current line
    def put(self, text: str):
        if self.cell is not None:
            self.cell += text
        else:
            self.line += text

    def flush(self):
        text = re.sub(r'[ \t ]+', ' ', self.line).strip()
        self.line = ''
        if text:                                     # an empty line keeps its prefix: in a loose list <li><p>
            self.out.append(self.prefix + text)      # opens with nothing written yet
            self.prefix = ''

    def blank(self):
        if self.out and self.out[-1] != '':
            self.out.append('')

    VOID = {'br', 'img', 'hr', 'input', 'wbr'}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.skip:
            self.skip += tag not in self.VOID
            return
        if 'data-ui' in a:
            self.skip = int(tag not in self.VOID)
            return
        if tag in self.HEADS:
            self.flush(); self.blank()
            self.prefix = '#' * int(tag[1]) + ' '
        elif tag in ('p', 'div'):
            if self.cell is None:
                self.flush()
        elif tag == 'br':
            if self.cell is not None:
                self.cell += ' '
            else:
                self.flush()
        elif tag in ('ul', 'ol'):
            self.flush()
            if not self.lists:
                self.blank()
            start = a.get('start') or '1'
            self.lists.append([tag, int(start) - 1 if start.isdigit() else 0])
        elif tag == 'li':
            self.flush()
            kind = self.lists[-1] if self.lists else ['ul', 0]
            kind[1] += 1
            indent = '   ' * (len(self.lists) - 1)
            self.prefix = indent + (f'{kind[1]}. ' if kind[0] == 'ol' else '- ')
        elif tag in ('strong', 'b'):
            self.put('**')
        elif tag in ('em', 'i'):
            self.put('*')
        elif tag == 'code':
            self.put('`')
            self.code = True
        elif tag == 'a':
            title = a.get('title')
            self.link.append(a.get('href', '') + (f' "{title}"' if title else ''))
            self.put('[')
        elif tag == 'img':
            src = a.get('src', '')
            self.put(f'![{a.get("alt", "")}]({"<" + src + ">" if " " in src else src})')
        elif tag == 'table':
            self.flush(); self.blank()
            self.header_done = False
        elif tag == 'thead':
            self.in_head = True
        elif tag == 'tr':
            self.row = []
        elif tag in ('td', 'th'):
            self.cell = ''

    def handle_endtag(self, tag):
        if self.skip:
            self.skip -= 1
            return
        if tag in self.HEADS:
            self.flush(); self.blank()
            self.prefix = ''
        elif tag in ('p', 'div'):
            if self.cell is None:
                self.flush()
                if not self.lists:
                    self.blank()
        elif tag == 'li':
            self.flush()
            self.prefix = ''
        elif tag in ('ul', 'ol'):
            self.flush()
            if self.lists:
                self.lists.pop()
            if not self.lists:
                self.blank()
        elif tag in ('strong', 'b'):
            self.put('**')
        elif tag in ('em', 'i'):
            self.put('*')
        elif tag == 'code':
            self.put('`')
            self.code = False
        elif tag == 'a':
            href = self.link.pop() if self.link else ''
            self.put(f']({href})')
        elif tag in ('td', 'th'):
            if self.row is not None and self.cell is not None:
                self.row.append(re.sub(r'\s+', ' ', self.cell).strip().replace('|', '｜'))
            self.cell = None
        elif tag == 'tr':
            if self.row is not None:
                self.out.append('| ' + ' | '.join(self.row) + ' |')
                if not self.header_done:
                    self.out.append('|' + '---|' * len(self.row))
                    self.header_done = True
            self.row = None
        elif tag == 'thead':
            self.in_head = False
        elif tag == 'table':
            self.blank()

    def handle_data(self, data):
        if self.skip:
            return
        if self.row is not None and self.cell is None:
            return                       # whitespace between cells
        text = data.replace('\n', ' ')
        if not self.code:                # what the user typed is text: a * or ` must not turn into formatting
            text = MARKUP.sub(lambda m: '\\' + m.group(0), text.replace(BLANK, '\0')).replace('\0', BLANK)
        self.put(text)


def back(html_text: str) -> str:
    parser = Back()
    parser.feed(html_text)
    parser.flush()
    text = '\n'.join(parser.out).strip() + '\n'
    text = re.sub(r'\n{3,}', '\n\n', text)
    return html.unescape(text).replace('****', '')


def main():
    if len(sys.argv) != 4 or sys.argv[1] != 'back':
        sys.exit(__doc__)
    Path(sys.argv[3]).write_text(back(Path(sys.argv[2]).read_text(encoding='utf-8')), encoding='utf-8')


if __name__ == '__main__':
    main()
