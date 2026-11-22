"""Charts in the minutes (OwnMind card #20, Vin 2026-11-22): a bar, pie, flow or architecture chart under the
paragraph that talks numbers, steps or how systems connect. A comparison is a plain Markdown table, not a chart.

Who does what:
- The AI that writes the minutes may write `圖表.json` beside `紀錄.md`: at most MOST charts, each with the exact
  line of the minutes it goes under (`after`) and its data. It never draws anything itself.
- place() checks each chart, draws it here (SVG made by this file, turned into a PNG by macOS's Quick Look, so
  nothing has to be installed), keeps it beside the minutes in 「<minutes>_附件/圖表-N.png」 and puts
  `![圖 N　title](…)` under its line. The Word file and the Google Doc get the picture from there.
- The meeting keeps `圖表.json` too: each chart's data and the words above its picture when it was drawn. When the
  user saves an edit that changes those words (in the Doc or in the window), redraw() asks the AI for the chart's
  new data, draws it again and puts the new picture in the Doc in place of the old one (Vin chose 「存檔時重畫」).

Vin 2026-11-22 asked whether Google Docs' own chart could be used: a Doc's chart is a linked Sheets chart, which
the Docs API cannot insert, so the Doc gets a picture.
"""
from __future__ import annotations

import fcntl
import html
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

FILE = '圖表.json'                    # what the AI writes beside 紀錄.md, and what the meeting keeps
KINDS = ('bar', 'pie', 'flow', 'arch')
MOST = 3                              # charts in one meeting's minutes
MOST_ITEMS = {'bar': 12, 'pie': 8, 'flow': 8, 'arch': 10}
WIDTH = 1000                          # the picture's width in pixels; the Doc shows it at most WIDEST_PT wide
FONT = 'PingFang TC, Helvetica Neue, sans-serif'
COLORS = ('#2f6fd6', '#e0892b', '#2e9e6b', '#8a63d2', '#d4506b', '#2aa5b8', '#9a7b2f', '#6b7280')
INK, SOFT, LINE, BOX = '#2b2b30', '#6e6e73', '#d6d6db', '#f2f4f8'
CAPTION = {'zh-TW': '圖 {n}　{title}', 'en': 'Figure {n}. {title}'}


def text_width(text: str, size: float) -> float:
    """How wide the text draws: a CJK character is about as wide as the font is tall, others a little over half."""
    return sum(size if ord(c) > 0x2e80 else size * 0.58 for c in str(text))


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            return float(value.replace(',', '').strip())
        except ValueError:
            return None
    return None


def shown(value: float) -> str:
    return f'{value:,.0f}' if value == int(value) else f'{value:,.2f}'.rstrip('0').rstrip('.')


def label(value, limit: int = 24) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def checked(spec) -> dict | None:
    """A chart this file can draw, cleaned up; None for anything else (the minutes go out without it)."""
    if not isinstance(spec, dict) or spec.get('type') not in KINDS:
        return None
    kind = spec['type']
    out = {'type': kind, 'title': label(spec.get('title'), 40), 'after': str(spec.get('after') or '').strip()}
    if kind in ('bar', 'pie'):
        items = []
        for it in spec.get('items') or []:
            value = number(it.get('value')) if isinstance(it, dict) else None
            name = label(it.get('label')) if isinstance(it, dict) else ''
            if name and value is not None and value >= 0:
                items.append({'label': name, 'value': value})
        if len(items) < 2 or len(items) > MOST_ITEMS[kind] or not any(i['value'] for i in items):
            return None
        out.update(items=items, unit=label(spec.get('unit'), 8))
    elif kind == 'flow':
        steps = []
        for s in spec.get('steps') or []:
            s = s if isinstance(s, dict) else {'label': s}
            name = label(s.get('label'), 12)
            if name:
                steps.append({'label': name, 'note': label(s.get('note'), 14)})
        if len(steps) < 2 or len(steps) > MOST_ITEMS['flow']:
            return None
        out['steps'] = steps
    else:
        nodes = list(dict.fromkeys(label(n, 12) for n in spec.get('nodes') or [] if label(n, 12)))
        links = []
        for pair in spec.get('links') or []:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                a, b = label(pair[0], 12), label(pair[1], 12)
                if a in nodes and b in nodes and a != b and [a, b] not in links:
                    links.append([a, b])
        if len(nodes) < 2 or len(nodes) > MOST_ITEMS['arch'] or not links:
            return None
        col = layers(nodes, links)
        if max(list(col.values()).count(c) for c in set(col.values())) > 6:
            return None                               # a column taller than the picture
        out.update(nodes=nodes, links=links)
    return out


# --- drawing -------------------------------------------------------------------------------------

def bar_svg(c: dict) -> tuple[list[str], int]:
    items, unit = c['items'], c.get('unit') or ''
    size = 26
    left = min(360, max(text_width(i['label'], size) for i in items) + 40)
    top, row = 30, 64
    most = max(i['value'] for i in items)
    room = WIDTH - left - 40 - text_width(shown(most) + ' ' + unit, size - 2)
    out = []
    for k, it in enumerate(items):
        y = top + k * row
        w = max(3, room * it['value'] / most) if most else 3
        out.append(f'<text x="{left - 20}" y="{y + 32}" font-size="{size}" text-anchor="end" fill="{INK}">'
                   f'{esc(it["label"])}</text>')
        out.append(f'<rect x="{left}" y="{y + 8}" width="{w:.1f}" height="36" rx="5" fill="{COLORS[0]}"/>')
        out.append(f'<text x="{left + w + 12:.1f}" y="{y + 34}" font-size="{size - 2}" fill="{INK}">'
                   f'{esc(shown(it["value"]) + (" " + unit if unit else ""))}</text>')
    return out, top + len(items) * row + 10


def pie_svg(c: dict) -> tuple[list[str], int]:
    items, unit = c['items'], c.get('unit') or ''
    total = sum(i['value'] for i in items)
    r, cx, cy = 160, 210, 200
    out, angle = [], -math.pi / 2
    for k, it in enumerate(items):
        share = it['value'] / total
        if share >= 0.9999:
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{COLORS[k % len(COLORS)]}"/>')
            continue
        end = angle + share * 2 * math.pi
        x1, y1 = cx + r * math.cos(angle), cy + r * math.sin(angle)
        x2, y2 = cx + r * math.cos(end), cy + r * math.sin(end)
        big = 1 if share > 0.5 else 0
        if share > 0:
            out.append(f'<path d="M{cx} {cy} L{x1:.2f} {y1:.2f} A{r} {r} 0 {big} 1 {x2:.2f} {y2:.2f} Z" '
                       f'fill="{COLORS[k % len(COLORS)]}" stroke="#fff" stroke-width="2"/>')
        angle = end
    y0 = cy - len(items) * 25 + 10
    for k, it in enumerate(items):
        y = y0 + k * 50
        pct = round(it['value'] / total * 100)
        words = f'{it["label"]}　{shown(it["value"])}{(" " + unit) if unit else ""}（{pct}%）'
        out.append(f'<rect x="440" y="{y - 20}" width="22" height="22" rx="4" fill="{COLORS[k % len(COLORS)]}"/>')
        out.append(f'<text x="476" y="{y}" font-size="26" fill="{INK}">{esc(words)}</text>')
    return out, max(cy + r + 30, y0 + len(items) * 50)


def box(x: float, y: float, w: float, h: float, words: str, note: str = '') -> list[str]:
    out = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="12" fill="{BOX}" stroke="{LINE}" '
           f'stroke-width="2"/>']
    mid = x + w / 2
    if note:
        out.append(f'<text x="{mid:.1f}" y="{y + h / 2 - 4:.1f}" font-size="26" text-anchor="middle" fill="{INK}">'
                   f'{esc(words)}</text>')
        out.append(f'<text x="{mid:.1f}" y="{y + h / 2 + 26:.1f}" font-size="20" text-anchor="middle" fill="{SOFT}">'
                   f'{esc(note)}</text>')
    else:
        out.append(f'<text x="{mid:.1f}" y="{y + h / 2 + 9:.1f}" font-size="26" text-anchor="middle" fill="{INK}">'
                   f'{esc(words)}</text>')
    return out


ARROW = (f'<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
         f'orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="{SOFT}"/></marker></defs>')


def flow_svg(c: dict) -> tuple[list[str], int]:
    steps = c['steps']
    per_row = 4 if len(steps) > 5 else len(steps)
    gap = 44
    w = (WIDTH - 40 - gap * (per_row - 1)) / per_row
    h = 96
    out = [ARROW]
    for k, s in enumerate(steps):
        r, col = divmod(k, per_row)
        x, y = 20 + col * (w + gap), 20 + r * (h + 60)
        out += box(x, y, w, h, s['label'], s.get('note', ''))
        if k + 1 < len(steps):
            if col + 1 < per_row:
                out.append(f'<line x1="{x + w + 4:.1f}" y1="{y + h / 2}" x2="{x + w + gap - 4:.1f}" y2="{y + h / 2}" '
                           f'stroke="{SOFT}" stroke-width="3" marker-end="url(#head)"/>')
            else:                                     # the next row starts at the left
                out.append(f'<path d="M{x + w / 2:.1f} {y + h + 4} L{x + w / 2:.1f} {y + h + 30} L{20 + w / 2:.1f} '
                           f'{y + h + 30} L{20 + w / 2:.1f} {y + h + 56}" fill="none" stroke="{SOFT}" '
                           f'stroke-width="3" marker-end="url(#head)"/>')
    rows = math.ceil(len(steps) / per_row)
    return out, 20 + rows * h + (rows - 1) * 60 + 20


def layers(nodes: list[str], links: list[list[str]]) -> dict[str, int]:
    """Each node's column: one right of everything that points to it; a loop is cut where it closes."""
    col = {n: 0 for n in nodes}
    for _ in range(len(nodes)):
        moved = False
        for a, b in links:
            if col[b] < col[a] + 1 and col[a] + 1 < len(nodes):
                col[b] = col[a] + 1
                moved = True
        if not moved:
            break
    used = sorted(set(col.values()))                  # no empty column in between
    return {n: used.index(c) for n, c in col.items()}


def arch_svg(c: dict) -> tuple[list[str], int]:
    nodes, links = c['nodes'], c['links']
    col = layers(nodes, links)
    cols = max(col.values()) + 1
    per = [[n for n in nodes if col[n] == k] for k in range(cols)]
    w, h, vgap = 210, 80, 40
    tallest = max(len(p) for p in per)
    height = tallest * h + (tallest - 1) * vgap + 40
    hgap = (WIDTH - 40 - cols * w) / max(1, cols - 1) if cols > 1 else 0
    where = {}
    for k, group in enumerate(per):
        x = 20 + k * (w + hgap) if cols > 1 else (WIDTH - w) / 2
        span = len(group) * h + (len(group) - 1) * vgap
        for i, n in enumerate(group):
            where[n] = (x, (height - span) / 2 + i * (h + vgap))
    out = [ARROW]
    for a, b in links:
        (ax, ay), (bx, by) = where[a], where[b]
        if bx > ax:
            x1, y1, x2, y2 = ax + w, ay + h / 2, bx - 4, by + h / 2
            mid = (x1 + x2) / 2
            out.append(f'<path d="M{x1:.1f} {y1:.1f} C{mid:.1f} {y1:.1f} {mid:.1f} {y2:.1f} {x2:.1f} {y2:.1f}" '
                       f'fill="none" stroke="{SOFT}" stroke-width="3" marker-end="url(#head)"/>')
        else:                                         # a link back, or within a column: under the boxes
            x1, x2 = ax + w / 2, bx + w / 2
            y1, y2 = ay + h, by + h + 4
            low = max(y1, y2) + 30
            out.append(f'<path d="M{x1:.1f} {y1:.1f} C{x1:.1f} {low:.1f} {x2:.1f} {low:.1f} {x2:.1f} {y2:.1f}" '
                       f'fill="none" stroke="{SOFT}" stroke-width="3" stroke-dasharray="8 6" '
                       f'marker-end="url(#head)"/>')
    for n in nodes:
        out += box(*where[n], w, h, n)
    return out, height


DRAW = {'bar': bar_svg, 'pie': pie_svg, 'flow': flow_svg, 'arch': arch_svg}


def svg(c: dict, n: int, lang: str = 'zh-TW') -> tuple[str, int]:
    """The chart as a square SVG WIDTH wide with the drawing in the middle (Quick Look makes square pictures), and
    the height of the drawing with its caption."""
    parts, used = DRAW[c['type']](c)
    caption = CAPTION['en' if lang == 'en' else 'zh-TW'].format(n=n, title=c.get('title') or '').strip()
    height = min(WIDTH, int(used + 60))
    top = (WIDTH - height) // 2
    body = ''.join(parts)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{WIDTH}" viewBox="0 0 {WIDTH} {WIDTH}">'
            f'<rect width="{WIDTH}" height="{WIDTH}" fill="#ffffff"/>'
            f'<g transform="translate(0 {top})" font-family="{FONT}">{body}'
            f'<text x="{WIDTH / 2}" y="{height - 18}" font-size="24" text-anchor="middle" fill="{SOFT}">'
            f'{esc(caption)}</text></g></svg>'), height


def render(c: dict, n: int, out: Path, lang: str = 'zh-TW') -> bool:
    """The chart as a PNG at `out`; False when macOS could not draw it (the minutes then go without it)."""
    text, height = svg(c, n, lang)
    work = Path(tempfile.mkdtemp(prefix='vinutes-chart-'))
    try:
        src = work / 'chart.svg'
        src.write_text(text, encoding='utf-8')
        subprocess.run(['qlmanage', '-t', '-s', str(WIDTH), '-o', str(work), str(src)], capture_output=True,
                       timeout=60)
        square = work / 'chart.svg.png'
        if not square.is_file():
            return False
        done = subprocess.run(['sips', '-c', str(height), str(WIDTH), str(square), '--out', str(work / 'cut.png')],
                              capture_output=True, timeout=60)
        if done.returncode or not (work / 'cut.png').is_file():
            return False
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(work / 'cut.png'), out)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --- the minutes ---------------------------------------------------------------------------------

def plain_line(line: str) -> str:
    """A line of Markdown as words: no list mark, heading mark, bold or link."""
    s = re.sub(r'^\s*(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s+|>\s*)', '', line)
    s = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', s)
    return re.sub(r'\s+', '', s.replace('**', '').replace('__', '').replace('`', ''))


def picture_line(line: str, name: str | None = None) -> bool:
    found = re.match(r'^\s*!\[[^\]]*\]\(<?([^)>]*)>?\)\s*$', line)
    return bool(found) and (name is None or found.group(1).rsplit('/', 1)[-1] == name)


def where_after(lines: list[str], after: str) -> int | None:
    """The index to put the picture at: under the line the AI named, after the list or table it is part of."""
    want = plain_line(after)
    if not want:
        return None
    hit = next((i for i, line in enumerate(lines) if plain_line(line) == want), None)
    if hit is None:
        hit = next((i for i, line in enumerate(lines) if want in plain_line(line) and len(want) >= 8), None)
    if hit is None or lines[hit].lstrip().startswith('#'):
        return None if hit is None else hit + 1
    end = hit + 1
    kind = 'table' if lines[hit].lstrip().startswith('|') else 'list' if re.match(r'^\s*(?:[-*+]|\d+[.)])\s', lines[hit]) else ''
    while end < len(lines) and lines[end].strip():
        nxt = lines[end]
        if kind == 'table' and not nxt.lstrip().startswith('|'):
            break
        if kind == 'list' and not (re.match(r'^\s*(?:[-*+]|\d+[.)])\s', nxt) or nxt.startswith((' ', '\t'))):
            break
        if not kind and (nxt.lstrip().startswith(('#', '|', '- ', '* ')) or picture_line(nxt)):
            break
        end += 1
    return end


def section(md: str, name: str) -> str | None:
    """The words above the chart's picture, up to the heading before them: what the chart shows (pictures in
    between are not words). None when the picture is no longer in the minutes."""
    lines = md.split('\n')
    at = next((i for i, line in enumerate(lines) if picture_line(line, name)), None)
    if at is None:
        return None
    words = []
    for line in reversed(lines[:at]):
        if line.lstrip().startswith('#'):
            break
        if line.strip() and not picture_line(line):
            words.append(plain_line(line))
    return '\n'.join(reversed(words))


def folder_of(md_path: Path) -> Path:
    return md_path.with_name(md_path.stem + '_附件')        # attachments.keep_beside keeps pictures there too


def read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write(path: Path, data: dict):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(path)


def place(job: Path, work: Path, md_path: Path, lang: str = 'zh-TW', log=lambda s: None) -> int:
    """The AI's 圖表.json drawn and put into the minutes at md_path; how many charts went in."""
    asked = read(work / FILE).get('charts')
    if not isinstance(asked, list):
        return 0
    lines = md_path.read_text(encoding='utf-8').split('\n')
    kept, n = [], 0
    for raw in asked[:MOST]:
        c = checked(raw)
        if not c:
            log('chart left out: not one this app can draw')
            continue
        at = where_after(lines, c['after'])
        if at is None:
            log('chart left out: its line is not in the minutes')
            continue
        k = at
        while k < len(lines) and (not lines[k].strip() or picture_line(lines[k])):   # under pictures already there
            if picture_line(lines[k]):
                at = k + 1
            k += 1
        n += 1
        name = f'圖表-{n}.png'
        picture = folder_of(md_path) / name
        if not render(c, n, picture, lang):
            n -= 1
            log('chart left out: macOS could not draw it')
            continue
        caption = CAPTION['en' if lang == 'en' else 'zh-TW'].format(n=n, title=c['title']).strip()
        rel = f'{picture.parent.name}/{name}'
        lines[at:at] = ([''] if lines[at - 1].strip() else []) + [f'![{caption}](<{rel}>)', '']
        kept.append({'n': n, 'file': name, 'chart': c})
    if not kept:
        return 0
    md = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines))
    md_path.write_text(md, encoding='utf-8')
    for k in kept:
        k['words'] = section(md, k['file']) or ''
    write(job / FILE, {'charts': kept})
    return len(kept)


def settle(job: Path, md: str):
    """The words above each chart as the minutes now read: after place(), the program still names the voices
    (speakers.guesses_into), which is no edit of the user's."""
    data = read(job / FILE)
    for k in data.get('charts') or []:
        k['words'] = section(md, k.get('file', '')) or ''
    if data:
        write(job / FILE, data)


def stale(job: Path, md: str) -> list[dict]:
    """The charts whose words were changed since they were drawn (and whose picture is still in the minutes)."""
    out = []
    for k in read(job / FILE).get('charts') or []:
        now = section(md, k.get('file', ''))
        if now is not None and (now != k.get('words') or k.get('pending')):
            out.append({**k, 'now': now})
    return out


# --- drawing again after an edit -------------------------------------------------------------------

UPDATE_PROMPT = {
    'zh-TW': ('會議紀錄裡有一張圖表，圖表下面的文字被使用者改過了。`圖表.json` 是原本的圖表，`段落.txt` 是圖表上方現在的文字。'
              '照現在的文字更新圖表的數字、名稱或步驟，type 不要換，文字沒提到的不要加。只回一段 JSON，格式和 `圖表.json` 一樣，'
              '不要其他說明。文字已經沒有可以畫圖的內容時，只回 {}。'),
    'en': ('A chart in the minutes sits under words the user has just changed. `圖表.json` is the chart as it was and '
           '`段落.txt` the words above it now. Update the chart\'s numbers, names or steps to match the words; keep '
           'its type and add nothing the words do not say. Answer with one JSON object shaped like `圖表.json` and '
           'nothing else, or {} when the words no longer have anything to chart.'),
}


FAILED = 'failed'                     # the AI did not answer (offline, timed out): asked again at the next save


def updated(chart: dict, words: str, lang: str, ask):
    """The chart's new data from the AI (`ask(prompt, folder) -> text`, '' when it did not answer): the chart,
    None when the answer has nothing this file can draw, or FAILED."""
    work = Path(tempfile.mkdtemp(prefix='vinutes-chart-ai-'))
    try:
        (work / FILE).write_text(json.dumps(chart, ensure_ascii=False, indent=1), encoding='utf-8')
        (work / '段落.txt').write_text(words, encoding='utf-8')
        answer = ask(UPDATE_PROMPT['en' if lang == 'en' else 'zh-TW'], work) or ''
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not answer.strip():
        return FAILED
    found = re.search(r'\{.*\}', answer, re.S)
    try:
        data = json.loads(found.group(0)) if found else None
    except ValueError:
        return None
    if not isinstance(data, dict) or not data:
        return None
    data['type'], data['after'] = chart['type'], chart.get('after', '')
    data.setdefault('title', chart.get('title', ''))
    return checked(data)


def redraw(job: Path, md_path: Path, md: str, lang: str, ask, replace=None, log=lambda s: None) -> int:
    """Every chart whose words changed: new data from the AI, drawn again over its picture, and
    `replace(n, png) -> bool` puts it in the Doc. A chart whose Doc still has the old picture stays `pending` and is
    put in at the next save without asking the AI again. One redraw at a time per meeting: one that finds another
    running leaves it to that one, which looks at the minutes again after letting go. How many were drawn again."""
    done, tried = 0, set()
    for _ in range(4):
        lock = open(job / '.charts.lock', 'w')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.close()
            return done
        try:
            md = md_path.read_text(encoding='utf-8') if md_path.is_file() else md
            todo = [k for k in stale(job, md) if (k['file'], k['now']) not in tried]
            data = read(job / FILE)
            for k in todo:
                tried.add((k['file'], k['now']))
                entry = next(e for e in data['charts'] if e['file'] == k['file'])
                picture = folder_of(md_path) / k['file']
                if k.get('pending') and k['now'] == k.get('words'):
                    new = entry['chart']                  # drawn already; only the Doc is behind
                else:
                    new = updated(k['chart'], k['now'], lang, ask)
                    if new == FAILED:
                        log(f'chart {k["n"]}: the AI did not answer; asked again at the next save')
                        continue
                    entry['words'] = k['now']
                    if not new or new == k['chart']:      # nothing to draw, or the same chart: the picture stays
                        continue
                    if not render(new, k['n'], picture, lang):
                        log(f'chart {k["n"]}: macOS could not draw it')
                        continue
                    entry['chart'] = new
                    done += 1
                entry['pending'] = bool(replace) and not replace(k['n'], picture)
                write(job / FILE, data)
            write(job / FILE, data)
        finally:
            lock.close()
        now = md_path.read_text(encoding='utf-8') if md_path.is_file() else md
        if not [k for k in stale(job, now) if (k['file'], k['now']) not in tried]:
            break                                     # nothing saved meanwhile that this run has not looked at
    return done
