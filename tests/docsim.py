"""A small stand-in for Google Docs' batchUpdate: a Doc from fake_doc() is flattened into one token per index,
the planned requests are applied the way Google applies them, and the result is read back as units. Enough to see
that a plan, sent for real, leaves the Doc reading exactly like the new Markdown.
"""
import doc_sync as ds


def flatten(doc: dict) -> list:
    lists = doc['lists']
    flat = []
    for el in doc['body']['content']:
        if 'sectionBreak' in el:
            flat.append(('S',))
        elif 'paragraph' in el:
            flat += _paragraph(el['paragraph'], lists)
        else:
            flat.append(('T',))
            for row in el['table']['tableRows']:
                flat.append(('R',))
                for cell in row['tableCells']:
                    flat.append(('C',))
                    for p in cell['content']:
                        flat += _paragraph(p['paragraph'], lists)
            flat.append(('E',))
    return flat


def _paragraph(par: dict, lists: dict) -> list:
    named = par.get('paragraphStyle', {}).get('namedStyleType', 'NORMAL_TEXT')
    if named == 'NORMAL_TEXT' and par.get('paragraphStyle', {}).get('alignment') == 'CENTER':
        named = 'CENTER'                             # a title line (doc_sync.title_lines)
    bullet = None
    if par.get('bullet'):
        level = lists[par['bullet']['listId']]['listProperties']['nestingLevels'][0]
        bullet = 'ol' if level.get('glyphType') == 'DECIMAL' else 'li'
    out = []
    for e in par['elements']:
        if 'textRun' not in e:
            out.append(('o',))                       # a chip, an image, a footnote mark: one index
            continue
        for ch in e['textRun']['content']:
            if ch == '\n':
                out.append(('N', named, bullet))
            else:
                out.append(('c', ch))
                if ds.u16(ch) == 2:
                    out.append(('x',))
    return out


def apply(flat: list, requests: list) -> list:
    for r in requests:
        if 'deleteContentRange' in r:
            rng = r['deleteContentRange']['range']
            s, e = rng['startIndex'], rng['endIndex']
            assert s < e and all(t[0] in 'cxN' for t in flat[s:e]), ('delete crosses structure', s, e)
            assert not (flat[e - 1][0] == 'N' and e < len(flat) and flat[e][0] == 'T'), ('the newline before a table', s, e)
            assert any(t[0] == 'N' for t in flat[e:]), ('the last newline of the Doc', s, e)
            del flat[s:e]
        elif 'insertText' in r:
            i = r['insertText']['location']['index']
            assert flat[i][0] in 'cxNo', ('insert at a structural index', i, flat[i])
            assert ds.OBJ not in r['insertText']['text'], 'a picture cannot be typed in as text'
            nxt = next(t for t in flat[i:] if t[0] == 'N')
            toks = []
            for ch in r['insertText']['text']:
                if ch == '\n':
                    toks.append(('N', nxt[1], nxt[2]))
                else:
                    toks.append(('c', ch))
                    if ds.u16(ch) == 2:
                        toks.append(('x',))
            flat[i:i] = toks
        elif any(k in r for k in ('createParagraphBullets', 'deleteParagraphBullets', 'updateParagraphStyle')):
            key = next(iter(r))
            s, e = r[key]['range']['startIndex'], r[key]['range']['endIndex']
            j = s
            while j < len(flat) and flat[j][0] != 'N':
                j += 1
            for k in [j] + [k for k in range(j + 1, max(e, j + 1)) if k < len(flat) and flat[k][0] == 'N']:
                _, named, bullet = flat[k]
                if key == 'createParagraphBullets':
                    bullet = 'ol' if 'NUMBERED' in r[key]['bulletPreset'] else 'li'
                elif key == 'deleteParagraphBullets':
                    bullet = None
                else:
                    style = r[key]['paragraphStyle']
                    named = style.get('namedStyleType', 'NORMAL_TEXT' if named == 'CENTER' else named)
                    if style.get('alignment') == 'CENTER' and named == 'NORMAL_TEXT':
                        named = 'CENTER'
                    elif 'alignment' in style and style['alignment'] != 'CENTER' and named == 'CENTER':
                        named = 'NORMAL_TEXT'
                flat[k] = ('N', named, bullet)
        elif 'updateTextStyle' in r:
            s, e = r['updateTextStyle']['range']['startIndex'], r['updateTextStyle']['range']['endIndex']
            assert s <= e <= len(flat), ('style range outside the Doc', s, e)
    return flat


def read(flat: list) -> list:
    """[(kind, text)]: paragraphs (empty ones dropped) and cells, in reading order."""
    out, cur, cell = [], '', None
    for t in flat:
        if t[0] in 'SR':
            continue
        if t[0] == 'T':
            continue
        if t[0] == 'C':
            if cell is not None:
                out.append(('cell', cell))
            cell = ''
        elif t[0] == 'E':
            if cell is not None:
                out.append(('cell', cell))
            cell = None
        elif t[0] == 'c':
            cur += t[1]
        elif t[0] == 'N':
            if cell is not None:
                cell = (cell + ' ' + cur).strip() if cell else cur
            else:
                kind = 'h1' if t[1] == 'CENTER' else f'h{t[1][-1]}' if t[1].startswith('HEADING') else (t[2] or 'p')
                if ds.norm(cur):
                    out.append((kind, ds.norm(cur)))
            cur = ''
    return out


def want(md: str) -> list:
    out = []
    for b in ds.parse(md)[1]:
        if b.kind == 'cell':
            out.append(('cell', ds.norm(b.plain)))
        elif ds.norm(b.plain):
            out.append((b.kind, ds.norm(b.plain)))
    return out


def after_push(doc: dict, plan) -> list:
    return read(apply(flatten(doc), plan.requests))
