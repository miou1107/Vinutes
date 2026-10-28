"""Checks for the recorder window's scripts that need no Google login: matching the Markdown with a Doc, planning
the paragraph edits, merging colleagues' edits, and what the window learns from the user's own edits.

Run: python3 -m unittest discover -s tests   (with the Python packages install.sh sets up, e.g. markdown-it-py)
The Docs API side is a stand-in built from Markdown the way Google lays a converted Doc out: one paragraph per
heading, list item or paragraph, one paragraph per table cell, indices counted in UTF-16 code units.
"""
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime
from pathlib import Path

# The assertions below check the Chinese wording, which must not change; the English tests at the end set 'en'
# for themselves. Set before the scripts are imported: their messages are read in the app's language then.
os.environ['VINUTES_LANG'] = 'zh-TW'
HOME = tempfile.mkdtemp(prefix='minutes-test-')
os.environ['MINUTES_HOME'] = HOME                  # nothing here touches the real settings, glossary or notes
os.environ['VINUTES_LOG_DIR'] = os.path.join(HOME, 'logs')   # nor the real logs
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import doc_sync as ds  # noqa: E402
import minutes_app  # noqa: E402
import minutes_html  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import docsim  # noqa: E402

EXAMPLE = (Path(__file__).resolve().parent.parent / 'references' / 'example-minutes.md').read_text(encoding='utf-8')

MINUTES = """# 週會

# 會議紀錄

## 一、會議基本資訊

- 會議日期：2026 年 10 月 14 日（星期三）10:30–12:30
- 主持人：[__]
- 與會人員：Amy、Ken

## 二、討論摘要

會中說明：上個月網站流量增加 **12%**，主要來自三篇文章。

### （一）社群活動

- 活動預算確定為 10 萬元。
- 主要投放在 Threads 與 Instagram。

## 三、初步共識

1. 預算 10 萬元。
2. KOL 合作先找兩位試行。

## 四、行動方案

| 編號 | 追蹤事項 | 負責 | 說明 |
|---|---|---|---|
| 1 | 社群活動執行 | [__] | 時程 [__] |
| 2 | KOL 試行合作 | Ken | 先找兩位 😀 |
"""


LISTED, CHANGED = '2026-10-15T01:48:21.451Z', '2026-10-15T01:48:21.490Z'    # Drive's newest revision, the Doc


def fake_doc(md: str) -> dict:
    """The Docs API answer for a Doc converted from this Markdown."""
    _, blocks = ds.parse(md)
    lists = {'B': {'listProperties': {'nestingLevels': [{'glyphSymbol': '●'}]}},
             'N': {'listProperties': {'nestingLevels': [{'glyphType': 'DECIMAL'}]}}}
    content = [{'startIndex': 0, 'endIndex': 1, 'sectionBreak': {}}]
    at = 1

    def paragraph(block) -> dict:
        nonlocal at
        text, marks = ds.spans(block.md)
        text = text.replace(ds.OBJ, '')
        runs, pos = [], 0
        bold_at = sorted((s, e) for s, e, b, _ in marks if b)
        link_at = [(s, e, link) for s, e, _, link in marks if link]
        cuts = sorted({0, len(text), *[x for s, e in bold_at for x in (s, e)], *[x for s, e, _ in link_at for x in (s, e)]})
        for s, e in zip(cuts, cuts[1:]):
            if e > s:
                style = {'bold': True} if any(bs <= s and e <= be for bs, be in bold_at) else {}
                link = next((url for ls, le, url in link_at if ls <= s and e <= le), None)
                if link:
                    style['link'] = {'url': link}
                runs.append((text[s:e], style))
        runs.append(('\n', {}))
        elements = []
        for t, style in runs:
            n = ds.u16(t)
            elements.append({'startIndex': at + pos, 'endIndex': at + pos + n,
                             'textRun': {'content': t, 'textStyle': style}})
            pos += n
        if block.kind == 'h1':                     # the title lines: centred normal text (md_to_docx)
            style = {'namedStyleType': 'NORMAL_TEXT', 'alignment': 'CENTER'}
        else:
            style = {'namedStyleType': f'HEADING_{block.kind[1]}' if block.kind.startswith('h') else 'NORMAL_TEXT'}
        par = {'elements': elements, 'paragraphStyle': style}
        if block.kind in ('li', 'ol'):
            par['bullet'] = {'listId': 'B' if block.kind == 'li' else 'N', 'nestingLevel': block.level}
        el = {'startIndex': at, 'endIndex': at + pos, 'paragraph': par}
        at += pos
        return el

    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.kind != 'cell':
            content.append(paragraph(b))
            i += 1
            continue
        start, rows = at, {}
        at += 1
        while i < len(blocks) and blocks[i].kind == 'cell' and blocks[i].table == b.table:
            rows.setdefault(blocks[i].row, []).append(blocks[i])
            i += 1
        table_rows = []
        for r in sorted(rows):
            at += 1
            cells = []
            for cell in rows[r]:
                at += 1
                cells.append({'content': [paragraph(cell)]})
            table_rows.append({'tableCells': cells})
        at += 1
        content.append({'startIndex': start, 'endIndex': at, 'table': {'tableRows': table_rows}})
    if 'table' in content[-1]:                    # Google always ends a Doc with a paragraph, empty after a table
        content.append({'startIndex': at, 'endIndex': at + 1, 'paragraph': {
            'elements': [{'startIndex': at, 'endIndex': at + 1, 'textRun': {'content': '\n', 'textStyle': {}}}],
            'paragraphStyle': {'namedStyleType': 'NORMAL_TEXT'}}})
    return {'revisionId': 'r1', 'lists': lists, 'body': {'content': content}}


def plains(md: str) -> list:
    return [ds.norm(b.plain) for b in ds.parse(md)[1]]


class Matching(unittest.TestCase):
    def test_markdown_and_doc_read_the_same(self):
        _, blocks = ds.parse(MINUTES)
        us = ds.comparable(ds.units(fake_doc(MINUTES)))
        self.assertEqual([b.key for b in blocks], [u.key for u in us])
        self.assertEqual(ds.shapes(blocks), [(3, 4)])

    def test_inline_markdown_becomes_plain_text_with_bold(self):
        text, marks = ds.spans('上個月增加 **12%**，見[文件](https://example.com)，[__] 不是連結')
        self.assertEqual(text, '上個月增加 12%，見文件，[__] 不是連結')
        self.assertIn((6, 9, True, None), marks)
        self.assertTrue(any(link == 'https://example.com' for *_, link in marks))

    def test_utf16_counts_emoji_as_two(self):
        self.assertEqual(ds.u16('先找兩位 😀'), 7)


SIZED_TITLE = {'fontSize': {'magnitude': 17, 'unit': 'PT'}}


class TitleLines(unittest.TestCase):
    """The two lines on top (topic, 會議紀錄) stay out of the outline Google Docs shows on the left."""

    def old_doc(self) -> dict:
        doc = fake_doc(MINUTES)
        for el in doc['body']['content'][1:3]:          # Docs made before 2026-10-15: Heading 1, centred
            el['paragraph']['paragraphStyle'] = {'namedStyleType': 'HEADING_1', 'alignment': 'CENTER'}
        return doc

    def test_the_word_file_writes_them_as_centred_normal_text(self):
        import docx
        import md_to_docx
        folder = Path(tempfile.mkdtemp(prefix='title-'))
        try:
            (folder / 'm.md').write_text(MINUTES, encoding='utf-8')
            md_to_docx.build(folder / 'm.md', folder / 'm.docx')
            pars = [p for p in docx.Document(folder / 'm.docx').paragraphs if p.text.strip()]
            self.assertEqual([(p.text, p.style.name) for p in pars[:3]],
                             [('週會', 'Normal'), ('會議紀錄', 'Normal'), ('一、會議基本資訊', 'Heading 2')])
            self.assertEqual(pars[0].alignment, md_to_docx.WD_ALIGN_PARAGRAPH.CENTER)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_title_line_left_without_its_size_gets_it_back(self):
        doc = fake_doc(MINUTES)
        bare = ds.title_requests(doc)
        self.assertEqual([next(iter(r)) for r in bare], ['updateTextStyle', 'updateTextStyle'])
        for el in doc['body']['content'][1:3]:
            el['paragraph']['elements'][0]['textRun']['textStyle'] = SIZED_TITLE
        self.assertEqual(ds.title_requests(doc), [])

    def test_a_new_doc_needs_no_change_and_reads_back_as_the_same_minutes(self):
        doc = fake_doc(MINUTES)
        for el in doc['body']['content'][1:3]:          # converted from the Word file, sized 17 pt
            el['paragraph']['elements'][0]['textRun']['textStyle'] = SIZED_TITLE
        self.assertEqual(ds.title_requests(doc), [])
        self.assertEqual([u.kind for u in ds.units(doc)[:3]], ['h1', 'h1', 'h2'])
        self.assertEqual(ds.plan_push(doc, MINUTES, MINUTES).requests, [])

    def test_an_older_doc_gets_its_two_title_lines_changed_and_nothing_else(self):
        doc = self.old_doc()
        reqs = ds.title_requests(doc)
        styles = [r['updateParagraphStyle'] for r in reqs if 'updateParagraphStyle' in r]
        looks = [r['updateTextStyle'] for r in reqs if 'updateTextStyle' in r]
        self.assertEqual([s['paragraphStyle']['namedStyleType'] for s in styles], ['NORMAL_TEXT', 'NORMAL_TEXT'])
        # the style change clears the text's size and bold in Google Docs, so they are given again
        self.assertEqual([(l['textStyle']['fontSize']['magnitude'], l['textStyle']['bold']) for l in looks],
                         [(17, True), (17, True)])
        after = docsim.read(docsim.apply(docsim.flatten(doc), reqs))
        self.assertEqual(after, docsim.want(MINUTES))

    def test_a_centred_paragraph_further_down_is_not_a_title(self):
        md = MINUTES.replace('會中說明：', '置中的一段。\n\n會中說明：')
        doc = fake_doc(md)
        for el in doc['body']['content']:
            par = el.get('paragraph')
            if par and par['elements'][0]['textRun']['content'].startswith('置中'):
                par['paragraphStyle']['alignment'] = 'CENTER'
        kinds = {u.text: u.kind for u in ds.units(doc)}
        self.assertEqual(kinds['置中的一段。'], 'p')

    def test_renaming_the_meeting_keeps_the_line_a_title(self):
        new = MINUTES.replace('# 週會', '# 社群週會')
        after = docsim.after_push(fake_doc(MINUTES), ds.plan_push(fake_doc(MINUTES), MINUTES, new))
        self.assertEqual(after, docsim.want(new))


class Push(unittest.TestCase):
    def plan(self, base, new, doc_md=None):
        return ds.plan_push(fake_doc(doc_md or base), base, new)

    def test_nothing_changed_sends_nothing(self):
        self.assertEqual(self.plan(MINUTES, MINUTES).requests, [])

    def test_one_word_changes_only_that_word(self):
        new = MINUTES.replace('Threads 與 Instagram', 'Threads 與 IG')
        plan = self.plan(MINUTES, new)
        kinds = [next(iter(r)) for r in plan.requests]
        self.assertEqual(kinds[:2], ['deleteContentRange', 'insertText'])
        self.assertEqual(plan.requests[1]['insertText']['text'], 'G')
        self.assertEqual([ds.norm(t) for _, t in plan.expected], plains(new))

    def test_filled_cell_after_an_emoji(self):
        new = MINUTES.replace('| 1 | 社群活動執行 | [__] |', '| 1 | 社群活動執行 | Amy |')
        plan = self.plan(MINUTES, new)
        self.assertEqual([ds.norm(t) for _, t in plan.expected], plains(new))
        self.assertEqual(plan.conflicts, [])

    def test_new_and_removed_paragraphs(self):
        new = MINUTES.replace('- 主要投放在 Threads 與 Instagram。', '- 主要投放在 Threads 與 Instagram。\n- 新的一條**重點**。') \
                     .replace('2. KOL 合作先找兩位試行。\n', '') + '\n最後補一段。\n'
        plan = self.plan(MINUTES, new)
        self.assertEqual([ds.norm(t) for c, t in plan.expected if c or ds.norm(t)], plains(new))
        inserted = [r['insertText']['text'] for r in plan.requests if 'insertText' in r]
        self.assertTrue(any('新的一條重點。' in t for t in inserted))
        self.assertTrue(any('最後補一段。' in t for t in inserted))

    def test_requests_run_from_the_end_of_the_doc(self):
        new = MINUTES.replace('# 週會', '# 週會（修訂）').replace('先找兩位 😀', '先找三位 😀')
        anchors = [r.get('insertText', {}).get('location', {}).get('index') or
                   r.get('deleteContentRange', {}).get('range', {}).get('startIndex') for r in self.plan(MINUTES, new).requests
                   if 'insertText' in r or 'deleteContentRange' in r]
        self.assertEqual(anchors, sorted(anchors, reverse=True))

    def test_a_colleagues_newer_text_is_not_overwritten(self):
        remote = MINUTES.replace('活動預算確定為 10 萬元。', '活動預算確定為 12 萬元（Amy 更正）。')
        mine = MINUTES.replace('活動預算確定為 10 萬元。', '活動預算確定為 15 萬元。') \
                      .replace('KOL 合作先找兩位試行。', 'KOL 合作先找三位試行。')
        plan = self.plan(MINUTES, mine, doc_md=remote)
        self.assertEqual(plan.conflicts, ['活動預算確定為 10 萬元。'])
        texts = [ds.norm(t) for _, t in plan.expected]
        self.assertIn('活動預算確定為 12 萬元（Amy 更正）。', texts)
        self.assertIn('KOL 合作先找三位試行。', texts)

    def test_a_cell_a_colleague_filled_first_is_kept(self):
        remote = MINUTES.replace('| 1 | 社群活動執行 | [__] |', '| 1 | 社群活動執行 | Amy |')
        mine = MINUTES.replace('| 1 | 社群活動執行 | [__] |', '| 1 | 社群活動執行 | Ken |')
        plan = self.plan(MINUTES, mine, doc_md=remote)
        self.assertEqual(plan.conflicts, ['[__]'])
        self.assertEqual(plan.requests, [])

    def test_a_new_table_row_needs_a_full_upload(self):
        new = MINUTES.rstrip('\n') + '\n| 3 | 新事項 | Amy | 下週 |\n'
        with self.assertRaises(ds.Structural):
            self.plan(MINUTES, new)


class Pull(unittest.TestCase):
    def test_colleague_edits_come_into_the_markdown(self):
        remote = MINUTES.replace('主持人：[__]', '主持人：王小明') \
                        .replace('| 1 | 社群活動執行 | [__] |', '| 1 | 社群活動執行 | Amy |') \
                        .replace('- 主要投放在 Threads 與 Instagram。\n', '- 主要投放在 Threads 與 Instagram。\n- 人選由 Ken 提供。\n')
        merged, changes = ds.merge_remote(MINUTES, fake_doc(remote))
        self.assertEqual(plains(merged), plains(remote))
        self.assertIn('**12%**', merged)                      # untouched paragraphs keep their own Markdown
        found = {(c.kind, c.before, c.after) for c in changes}
        self.assertIn(('edit', '[__]', '王小明'), found)
        self.assertIn(('add', '', '人選由 Ken 提供。'), found)
        again, more = ds.merge_remote(merged, fake_doc(remote))
        self.assertEqual((again, more), (merged, []))

    def test_changed_words_widen_to_whole_numbers_and_words(self):
        self.assertEqual(ds.changed_words('預算 10 萬元', '預算 12 萬元'), ('10', '12'))
        self.assertEqual(ds.changed_words('Threads 與 Instagram', 'Threads 與 IG'), ('Instagram', 'IG'))


class Learning(unittest.TestCase):
    def setUp(self):
        import minutes_app
        self.app = minutes_app

    def test_what_is_kept_and_what_is_not(self):
        c = self.app.classify
        heard = '主要投放在 Fresh 跟 Instagram'
        self.assertEqual(c('Fresh', 'Threads', '', heard), 'term')            # a misheard word from the transcript
        self.assertEqual(c('10', '12', '', heard), 'once')                     # a number is a fact of this meeting
        self.assertEqual(c('', '終點', '', heard), 'once')                     # adding words
        self.assertEqual(c('[__]', 'Amy', '', heard), 'once')                  # filling a blank
        self.assertEqual(c('會中說明：', '', '會中說明：a 會中說明：b', heard), 'pref')   # a phrase the minutes repeat
        self.assertEqual(c('產品端討論', '', '產品端討論', heard), 'once')    # a one-off deletion
        self.assertEqual(c('有所提升', '變多', '', heard), 'style')            # Claude's wording, rewritten

    def test_word_guesses_are_read_from_plain_check_items(self):
        m = self.app.GUESS.search('「Fresh」推測是 Threads')
        self.assertEqual((m.group(1), m.group(2).strip()), ('Fresh', 'Threads'))
        self.assertIsNone(self.app.GUESS.search('逐字稿未標講者'))

    def test_preview_shows_raw_html_as_text_and_drops_internet_pictures(self):
        html = self.app.preview('# 標題\n\n<script>alert(1)</script> ![x](https://example.com/a.png) [__]\n', [], [])
        self.assertNotIn('<script>', html)
        self.assertNotIn('example.com', html)
        self.assertIn('<span class="blank">[__]</span>', html)

    def test_marks_and_comment_anchors_nest(self):
        md = '- 活動預算確定為 12 萬元。\n'
        html = self.app.preview(md, [{'after': '12', 'block': 0, 'who': 'Amy'}], [{'n': 1, 'quote': '12 萬元'}])
        self.assertIn('<span class="anchor" data-c="1"><span class="edited"', html)
        self.assertIn('data-ui="1"', html)


def read_back(md: str) -> str:
    return minutes_html.back(minutes_app.preview(md, [], []))


class RoundTrip(unittest.TestCase):
    CASES = [MINUTES, EXAMPLE, '- point one.\n\n- point two.\n\n- point three.\n', '> a quote\n\nafter\n',
             'text\n\n---\n\nmore\n', '2026\\. plan and \\*not italic\\*\n', '正文第一行\n接著第二行\n',
             '![chart](data:image/png;base64,iVBORw0KGgo=)\n\ncaption\n', '請**「行銷部」**提供資料。\n',
             '見 [報告](https://example.com/2026/q4)，數字照 `report_v2` 的。\n']

    def test_saving_without_typing_changes_nothing(self):
        for md in self.CASES:
            back = read_back(md)
            new, skipped = ds.carry(md, back, back)
            self.assertEqual((new, skipped), (md, []), md[:30])
            self.assertEqual(ds.plan_push(fake_doc(md), md, new).requests, [], md[:30])

    def test_one_edit_in_a_loose_list_touches_that_item_only(self):
        md = '- point one.\n\n- point two.\n\n- point three.\n'
        back = read_back(md)
        new, skipped = ds.carry(md, back, back.replace('point two.', 'point 2.'))
        self.assertEqual(new, md.replace('point two.', 'point 2.'))
        self.assertEqual(skipped, [])

    def test_a_quote_stays_a_quote_when_edited(self):
        md = '> a quote\n\nafter\n'
        back = read_back(md)
        new, _ = ds.carry(md, back, back.replace('a quote', 'the quote'))
        self.assertEqual(new, '> the quote\n\nafter\n')

    def test_lines_of_one_chinese_paragraph_join_without_a_space(self):
        _, blocks = ds.parse('正文第一行\n接著第二行\n')
        self.assertEqual(blocks[0].plain, '正文第一行接著第二行')


def with_chip(md: str, words: str, name: str) -> dict:
    """fake_doc(md), with `words` in it replaced by a person chip showing `name` (one index in the Doc)."""
    doc = fake_doc(md)
    shift = 0
    for el in doc['body']['content']:
        el['startIndex'] -= shift
        el['endIndex'] -= shift
        par = el.get('paragraph')
        if not par:
            continue
        new_elements = []
        for e in par['elements']:
            e['startIndex'] -= shift
            e['endIndex'] -= shift
            text = e['textRun']['content']
            at = text.find(words) if not shift else -1
            if at < 0:
                new_elements.append(e)
                continue
            head, tail = text[:at], text[at + len(words):]
            s0 = e['startIndex']
            if head:
                new_elements.append({'startIndex': s0, 'endIndex': s0 + ds.u16(head), 'textRun': {'content': head, 'textStyle': {}}})
            chip_at = s0 + ds.u16(head)
            new_elements.append({'startIndex': chip_at, 'endIndex': chip_at + 1,
                                 'person': {'personProperties': {'name': name, 'email': 'x@example.com'}}})
            new_elements.append({'startIndex': chip_at + 1, 'endIndex': chip_at + 1 + ds.u16(tail),
                                 'textRun': {'content': tail, 'textStyle': {}}})
            shift = ds.u16(words) - 1
            el['endIndex'] -= shift
        par['elements'] = new_elements
    return doc


class Chips(unittest.TestCase):
    def test_a_chip_reads_as_its_name_and_survives_an_edit_beside_it(self):
        remote = MINUTES.replace('主持人：[__]', '主持人：Amy 本週確認')
        doc = with_chip(remote, 'Amy', 'Amy')
        merged, _ = ds.merge_remote(MINUTES, doc)
        self.assertIn('主持人：Amy 本週確認', merged)
        plan = ds.plan_push(doc, merged, merged.replace('本週確認', '下週確認'))
        deletes = [r['deleteContentRange']['range'] for r in plan.requests if 'deleteContentRange' in r]
        chip = next(u for u in ds.units(doc) if u.text.startswith('主持人'))
        chip_index = chip.pos[chip.text.index('Amy')]
        self.assertTrue(deletes and all(not (d['startIndex'] <= chip_index < d['endIndex']) for d in deletes))

    def test_an_edit_that_would_cut_a_chip_is_a_conflict(self):
        remote = MINUTES.replace('主持人：[__]', '主持人：Amy 本週確認')
        doc = with_chip(remote, 'Amy', 'Amy')
        merged, _ = ds.merge_remote(MINUTES, doc)
        plan = ds.plan_push(doc, merged, merged.replace('Amy 本週', 'Ken 本週'))
        self.assertEqual(plan.requests, [])
        self.assertEqual(len(plan.conflicts), 1)


class Flows(unittest.TestCase):
    """minutes_app's save / undo paths with Google replaced by stand-ins."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='job-'))
        self.job_dir = self.root / '20261014-103000'
        self.job_dir.mkdir()
        self.md_path = self.root / 'minutes.md'
        self.md_path.write_text(MINUTES, encoding='utf-8')
        (self.job_dir / 'job.json').write_text(json.dumps({'started': '2026-10-14T10:30:00+08:00'}))
        (self.job_dir / 'status.json').write_text(json.dumps({'step': 'done', 'at': '2026-10-14T11:00:00+08:00'}))
        (self.job_dir / 'result.json').write_text(json.dumps({
            'status': 'ok', 'title': '週會', 'minutes_md': str(self.md_path),
            'doc_url': 'https://docs.google.com/document/d/' + 'D' * 30 + '/edit'}))
        for name in ('同步基準.md', '學習基準.md'):
            (self.job_dir / name).write_text(MINUTES, encoding='utf-8')
        self.saved = {name: getattr(ds, name) for name in ('push', 'get_doc', 'revisions_since', 'comments',
                                                            'batch_update', 'authorize', 'modified_time',
                                                            'paint_blanks', 'get_doc_inline')}
        self.saved_out = minutes_app.out
        ds.paint_blanks = lambda *a: ''                  # the blanks' red has its own tests (Blanks)
        ds.revisions_since = lambda *a: [{'lastModifyingUser': {'displayName': 'Amy'}, 'modifiedTime': LISTED}]
        ds.modified_time = lambda *a: CHANGED
        ds.comments = lambda *a: []
        ds.authorize = lambda: None
        ds.AUTH['Authorization'] = 'Bearer test'
        self.outs = []
        minutes_app.out = self.outs.append

    def tearDown(self):
        for name, fn in self.saved.items():
            setattr(ds, name, fn)
        minutes_app.out = self.saved_out
        ds.AUTH.clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def job(self):
        return minutes_app.Job(self.job_dir)

    def test_offline_edits_stay_here_and_go_out_on_the_next_sync(self):
        def offline(*a):
            raise SystemExit('OFFLINE: no network')
        ds.push = offline
        job = self.job()
        mine = MINUTES.replace('主持人：[__]', '主持人：王小明')
        result = minutes_app.push_edit(job, mine)
        self.assertEqual(result['held'], minutes_app.OFFLINE_SAVED)
        self.assertEqual(self.md_path.read_text(encoding='utf-8'), mine)       # nothing typed is lost
        self.assertEqual(job.synced_md, MINUTES)
        sent = []

        def online(doc_id, base, new):
            sent.append((base, new))
            return ds.Plan([{'x': 1}], [], []), fake_doc(new), True
        ds.push = online
        minutes_app.sync_up(self.job())
        self.assertEqual(sent, [(MINUTES, mine)])
        self.assertEqual(self.job().synced_md, mine)

    def test_a_colleagues_edit_during_a_save_is_logged_as_theirs_and_never_learned(self):
        mine = MINUTES.replace('Threads 與 Instagram', 'Threads 與 IG')
        theirs = mine.replace('活動預算確定為 10 萬元。', '活動預算確定為 12 萬元。')
        ds.push = lambda doc_id, base, new: (ds.Plan([{'x': 1}], [], []), fake_doc(theirs), True)
        job = self.job()
        result = minutes_app.push_edit(job, mine)
        self.assertTrue(result['reload'])
        self.assertEqual(self.md_path.read_text(encoding='utf-8'), theirs)
        log = (self.job_dir / '操作紀錄.jsonl').read_text(encoding='utf-8')
        self.assertIn('"who": "Amy"', log)
        self.assertIn('12', log)
        learned = minutes_app.cmd_learn(self.job())
        texts = ' '.join(item['text'] for item in learned)
        self.assertIn('IG', texts)
        self.assertNotIn('12', texts)

    def test_saving_the_preview_as_opened_sends_nothing(self):
        loose = '# 週會\n\n- point one.\n\n- point two.\n\n> a quote\n\n---\n\n2026\\. plan\n'
        self.md_path.write_text(loose, encoding='utf-8')
        (self.job_dir / '同步基準.md').write_text(loose, encoding='utf-8')
        sent = []
        ds.push = lambda doc_id, base, new: sent.append(new) or (ds.Plan([], [], []), fake_doc(new), True)
        page = self.root / 'page.html'
        page.write_text(minutes_app.preview(loose, [], []), encoding='utf-8')
        minutes_app.out = lambda data: None
        minutes_app.cmd_save(self.job(), page)
        self.assertEqual(sent, [])
        self.assertEqual(self.md_path.read_text(encoding='utf-8'), loose)

    def test_undo_takes_back_only_what_claude_changed(self):
        claude = MINUTES.replace('主要投放在 Threads 與 Instagram。', '主要投放在社群平台。') \
                        .replace('KOL 合作先找兩位試行。', 'KOL 合作先找兩位網紅試行。')
        later = claude.replace('KOL 合作先找兩位網紅試行。', 'KOL 合作先找三位網紅試行（Amy 改）。')
        self.md_path.write_text(later, encoding='utf-8')
        (self.job_dir / '同步基準.md').write_text(later, encoding='utf-8')
        (self.job_dir / '復原.md').write_text(MINUTES, encoding='utf-8')
        (self.job_dir / '復原後.md').write_text(claude, encoding='utf-8')
        ds.push = lambda doc_id, base, new: (ds.Plan([{'x': 1}], [], []), fake_doc(new), True)
        result = []
        minutes_app.out = lambda data: result.append(data)
        minutes_app.cmd_undo(self.job())
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('主要投放在 Threads 與 Instagram。', md)                 # Claude's change, undone
        self.assertIn('KOL 合作先找三位網紅試行（Amy 改）。', md)              # changed again later: kept
        self.assertEqual(result[0]['kept'], ['KOL 合作先找兩位網紅試行。'])         # named as Claude wrote it


class Back(unittest.TestCase):
    def test_comment_numbers_do_not_end_up_in_the_minutes(self):
        import minutes_html
        md = minutes_html.back('<ul><li>預算 <span class="anchor" data-c="1">12 萬元</span>'
                               '<sup class="cnum" data-ui="1" contenteditable="false">1</sup>。</li></ul>')
        self.assertEqual(md.strip(), '- 預算 12 萬元。')


class Google:
    """A Doc held as Markdown: get_doc shows it, push plans against it and applies the plan when nothing conflicts."""

    def __init__(self, md: str):
        self.md, self.sent = md, []

    def doc(self) -> dict:
        return fake_doc(self.md)

    def push(self, doc_id, base, new):
        doc = self.doc()
        plan = ds.plan_push(doc, base, new)              # raises Structural just as the real push does
        self.sent.append(plan.requests)
        if plan.requests:
            self.md = ds.carry(self.md, base, new)[0]
        return plan, self.doc(), True


class Sync(Flows):
    """The ways a save could undo a colleague's work, and what happens instead."""

    def setUp(self):
        super().setUp()
        self.google = Google(MINUTES)
        ds.push = self.google.push
        ds.get_doc = lambda doc_id: self.google.doc()
        ds.batch_update = lambda *a: self.fail('nothing should go to Google directly')

    def page(self, md: str, *edits) -> Path:
        html_text = minutes_app.preview(md, [], [])
        for old, new in edits:
            html_text = html_text.replace(old, new, 1)
        path = self.root / f'page{len(self.outs)}.html'
        path.write_text(html_text, encoding='utf-8')
        return path

    def test_typing_on_while_a_save_brings_in_a_colleague_edit_keeps_it(self):
        shown = minutes_app.shown_token(self.job(), MINUTES)
        self.google.md = MINUTES.replace('10 萬元。\n- 主要', '12 萬元。\n- 主要')        # Amy, in the Doc
        mine = ('Threads 與 Instagram', 'Threads 與 IG')
        minutes_app.cmd_save(self.job(), self.page(MINUTES, mine), shown)
        self.assertIn('活動預算確定為 12 萬元', self.md_path.read_text(encoding='utf-8'))
        # the page kept the old text because the user kept typing; the next save must not type 10 back
        more = ('兩位試行', '三位試行')
        minutes_app.cmd_save(self.job(), self.page(MINUTES, mine, more), self.outs[-1]['typed'])
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('活動預算確定為 12 萬元', md)
        self.assertIn('三位試行', md)
        self.assertIn('活動預算確定為 12 萬元', self.google.md)
        self.assertEqual(minutes_app.cmd_learn(self.job()) and
                         [i for i in minutes_app.cmd_learn(self.job()) if '12' in i['text']], [])

    def test_typing_on_in_the_same_page_saves_each_edit_once(self):
        shown = minutes_app.shown_token(self.job(), MINUTES)
        first = ('Threads 與 Instagram', 'Threads 與 IG')
        minutes_app.cmd_save(self.job(), self.page(MINUTES, first), shown)
        self.assertNotIn('html', self.outs[-1])                          # nothing to reload: the page is right
        minutes_app.cmd_save(self.job(), self.page(MINUTES, first, ('兩位試行', '三位試行')), self.outs[-1]['typed'])
        self.assertEqual(self.outs[-1]['skipped'], [])
        self.assertEqual(self.google.md, MINUTES.replace(*first).replace('兩位試行', '三位試行'))
        self.assertEqual(len([r for r in self.google.sent if r]), 2)

    def test_a_paragraph_both_changed_keeps_the_colleagues_words_on_every_later_save(self):
        shown = minutes_app.shown_token(self.job(), MINUTES)
        self.google.md = MINUTES.replace('活動預算確定為 10 萬元。', '活動預算確定為 12 萬元。')
        mine = ('活動預算確定為 10 萬元。', '活動預算確定為 15 萬元。')
        minutes_app.cmd_save(self.job(), self.page(MINUTES, mine), shown)
        self.assertEqual(len(self.outs[-1]['conflicts']), 1)
        minutes_app.cmd_save(self.job(), self.page(MINUTES, mine, ('兩位試行', '三位試行')), self.outs[-1]['typed'])
        self.assertIn('活動預算確定為 12 萬元。', self.google.md)
        self.assertNotIn('15 萬元', self.google.md)
        self.assertIn('三位試行', self.google.md)
        self.assertIn('12 萬元', self.outs[-1]['html'])                  # the page is put right once typing stops

    def test_a_cell_a_colleague_changed_is_not_typed_over_either(self):
        shown = minutes_app.shown_token(self.job(), MINUTES)
        self.google.md = MINUTES.replace('| Ken | 先找兩位', '| Amy | 先找兩位')
        minutes_app.cmd_save(self.job(), self.page(MINUTES, ('Threads 與 Instagram', 'Threads 與 IG')), shown)
        minutes_app.cmd_save(self.job(), self.page(MINUTES, ('Threads 與 Instagram', 'Threads 與 IG'),
                                                   ('>Ken<', '>Bob<')), self.outs[-1]['typed'])
        self.assertIn('| Amy | 先找兩位', self.google.md)
        self.assertNotIn('Bob', self.google.md)

    def test_a_moved_minutes_file_never_empties_the_doc(self):
        self.md_path.unlink()
        minutes_app.cmd_open(self.job())
        self.assertEqual(self.google.sent, [])
        self.assertTrue(self.outs[-1]['readonly'])
        self.assertIn('minutes.md', self.outs[-1]['warning'])
        with self.assertRaises(SystemExit):
            minutes_app.Job(self.job_dir).write_md('x')

    def test_a_colleague_adding_a_table_row_does_not_lock_the_meeting(self):
        self.google.md = MINUTES.rstrip('\n') + '\n| 3 | 新事項 | Amy | 下週 |\n'
        minutes_app.cmd_save(self.job(), self.page(MINUTES, ('Threads 與 Instagram', 'Threads 與 IG')),
                             minutes_app.shown_token(self.job(), MINUTES))
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('新事項', md)
        self.assertIn('Threads 與 IG', md)
        self.assertIn('Threads 與 IG', self.google.md)                  # and it reached the Doc
        self.assertEqual(self.outs[-1]['held'], '')
        self.assertEqual(self.job().synced_md, md)

    def test_removing_a_table_row_in_the_preview_is_refused_without_losing_anything(self):
        before = self.md_path.read_text(encoding='utf-8')
        page = self.page(MINUTES)
        html_text = page.read_text(encoding='utf-8')
        start = html_text.index('<tr>', html_text.index('KOL 試行合作') - 200)
        page.write_text(html_text[:start] + html_text[html_text.index('</tr>', start) + 5:], encoding='utf-8')
        minutes_app.cmd_save(self.job(), page, minutes_app.shown_token(self.job(), MINUTES))
        self.assertEqual(self.outs[-1]['warning'], minutes_app.TABLE_SHAPE)
        self.assertTrue(self.outs[-1]['unsaved'])
        self.assertEqual(self.md_path.read_text(encoding='utf-8'), before)
        self.assertEqual(self.google.sent, [])

    def test_a_claude_table_rewrite_that_cannot_go_up_whole_is_dropped_cleanly(self):
        claude = MINUTES.replace('1. 預算 10 萬元。\n2. KOL 合作先找兩位試行。\n',
                                 '| 項目 | 內容 |\n|---|---|\n| 預算 | 10 萬元 |\n')
        ds.comments = lambda *a: [{'id': 'c1', 'resolved': False}]
        self.assertEqual(minutes_app.whole_upload_blocked(self.job()), minutes_app.ai_words(minutes_app.AI_TABLES_COMMENTS))
        (self.job_dir / '復原.md').write_text(MINUTES, encoding='utf-8')
        (self.job_dir / '復原後.md').write_text(claude, encoding='utf-8')
        result = minutes_app.push_edit(self.job(), claude, who='Claude')   # a comment came in after the check
        self.assertTrue(result['dropped'])
        self.assertEqual(self.md_path.read_text(encoding='utf-8'), MINUTES)
        self.assertFalse((self.job_dir / '復原.md').exists())

    def test_a_conflict_is_never_learned_as_the_users_wording(self):
        self.google.md = MINUTES.replace('增加 **12%**', '明顯成長 **12%**')
        shown = minutes_app.shown_token(self.job(), MINUTES)
        minutes_app.cmd_save(self.job(), self.page(MINUTES, ('增加 <strong>12%', '變多 <strong>12%')), shown)
        learned = ' '.join(i['text'] for i in minutes_app.cmd_learn(self.job()))
        self.assertNotIn('明顯成長', learned)
        self.assertNotIn('變多', learned)

    def test_a_colleague_typing_right_after_a_push_is_logged_and_not_learned(self):
        mine = MINUTES.replace('KOL 合作先找兩位試行。', 'KOL 合作先找三位試行。')
        theirs = mine.replace('主要投放在 Threads 與 Instagram。', '集中投放在短影音平台。')
        ds.push = lambda doc_id, base, new: (ds.plan_push(fake_doc(base), base, new), fake_doc(theirs), False)
        result = minutes_app.push_edit(self.job(), mine)
        self.assertTrue(result['marks'])
        self.assertIn('Amy', (self.job_dir / '操作紀錄.jsonl').read_text(encoding='utf-8'))
        learned = ' '.join(i['text'] for i in minutes_app.cmd_learn(self.job()))
        self.assertIn('三', learned)
        self.assertNotIn('短影音', learned)

    def test_claude_shortening_a_paragraph_the_user_just_fixed_learns_only_the_fix(self):
        md0 = MINUTES.replace('主要投放在 Threads 與 Instagram。', '主要投放在 Fresh 與 Instagram 平台。')
        for f in (self.md_path, self.job_dir / '同步基準.md', self.job_dir / '學習基準.md'):
            f.write_text(md0, encoding='utf-8')
        self.google.md = md0
        user = md0.replace('Fresh', 'Threads')
        minutes_app.push_edit(self.job(), user)
        first = minutes_app.cmd_learn(self.job())                       # what ai_edit runs before Claude starts
        claude = user.replace('主要投放在 Threads 與 Instagram 平台。', '集中投放 Threads、Instagram。')
        minutes_app.relearn(self.job(), user, claude)
        minutes_app.push_edit(self.job(), claude, who='Claude')
        later = minutes_app.cmd_learn(self.job())
        self.assertIn('Threads', ' '.join(i['text'] for i in first))
        self.assertEqual(later, [])

    def test_offline_edits_that_meet_a_colleagues_edit_are_reported_on_open(self):
        mine = MINUTES.replace('活動預算確定為 10 萬元。', '活動預算確定為 15 萬元。')
        self.md_path.write_text(mine, encoding='utf-8')                  # typed while offline
        self.google.md = MINUTES.replace('活動預算確定為 10 萬元。', '活動預算確定為 12 萬元。')
        minutes_app.cmd_open(self.job())
        self.assertIn(minutes_app.OFFLINE_CONFLICT, self.outs[-1]['warning'])
        self.assertIn('12 萬元', self.md_path.read_text(encoding='utf-8'))

    def test_a_cell_filled_here_never_lands_in_another_row_after_a_colleague_removes_one(self):
        local = MINUTES.replace('| 社群活動執行 | [__] |', '| 社群活動執行 | Bob |')
        self.md_path.write_text(local, encoding='utf-8')                 # filled here, not sent yet
        self.google.md = MINUTES.replace('| 1 | 社群活動執行 | [__] | 時程 [__] |\n', '')   # Amy removed that row
        result = minutes_app.sync_up(self.job())
        self.assertNotIn('Bob', self.google.md)
        self.assertNotIn('Bob', self.md_path.read_text(encoding='utf-8'))
        self.assertIn('Bob', result['skipped'])

    def test_typing_on_after_a_colleague_adds_a_row_never_fills_the_wrong_row(self):
        shown = minutes_app.shown_token(self.job(), MINUTES)
        self.google.md = MINUTES.replace('|---|---|---|---|\n', '|---|---|---|---|\n| 0 | 預算確認 | [__] | [__] |\n')
        first = ('Threads 與 Instagram', 'Threads 與 IG')
        minutes_app.cmd_save(self.job(), self.page(MINUTES, first), shown)
        self.assertIn('預算確認', self.md_path.read_text(encoding='utf-8'))
        fill = ('<td><span class="blank">[__]</span></td>', '<td>Bob</td>')
        minutes_app.cmd_save(self.job(), self.page(MINUTES, first, fill), self.outs[-1]['typed'])
        self.assertNotIn('Bob', self.google.md)
        self.assertIn('Bob', self.outs[-1]['skipped'])
        self.assertIn('預算確認', self.outs[-1]['html'])                  # the page gets the new row

    def test_google_troubles_are_named(self):
        self.assertEqual(minutes_app.trouble('GOOGLE LOGIN EXPIRED (400 invalid_grant)'), minutes_app.LOGIN_SAVED)
        self.assertEqual(minutes_app.trouble('HTTP 403 from Google: x', saving=False), minutes_app.NO_RIGHT_OPEN)
        self.assertEqual(minutes_app.trouble('HTTP 404 from Google: x'), minutes_app.GONE_SAVED)
        self.assertEqual(minutes_app.trouble('OFFLINE: Google did not answer'), minutes_app.OFFLINE_SAVED)
        self.assertEqual(minutes_app.trouble('HTTP 400 from Google: Invalid requests'), minutes_app.REJECTED_SAVED)


class SentForReal(unittest.TestCase):
    """Plans applied to a stand-in Doc read exactly like the new Markdown."""

    EDITS = [('主持人：[__]', '主持人：王小明'), ('- 主要投放在 Threads 與 Instagram。\n', ''),
             ('1. 預算 10 萬元。', '1. 預算 12 萬元。\n2. 新增一項。'), ('| 時程 [__] |', '| 10/20 前 |'),
             ('流量增加 **12%**', '流量增加 **15%**'), ('### （一）社群活動', '### （一）社群與廣告活動'),
             ('先找兩位 😀', '先找三位 😀')]

    def test_every_edit_alone_and_all_together(self):
        for edits in [[e] for e in self.EDITS] + [self.EDITS]:
            new = MINUTES
            for old, rep in edits:
                new = new.replace(old, rep, 1)
            plan = ds.plan_push(fake_doc(MINUTES), MINUTES, new)
            self.assertEqual(plan.conflicts, [], edits)
            self.assertEqual(docsim.after_push(fake_doc(MINUTES), plan), docsim.want(new), edits)

    def test_a_footnote_in_a_paragraph_does_not_block_editing_it(self):
        doc = fake_doc(MINUTES)
        for el in doc['body']['content']:
            par = el.get('paragraph')
            if par and '流量' in ''.join(e['textRun']['content'] for e in par['elements']):
                at = next(e for e in par['elements'] if e['textRun']['content'] == '12%')['endIndex']
                for e in par['elements']:
                    if e['startIndex'] >= at:
                        e['startIndex'] += 1
                        e['endIndex'] += 1
                k = next(i for i, e in enumerate(par['elements']) if e['startIndex'] > at)
                par['elements'].insert(k, {'startIndex': at, 'endIndex': at + 1, 'footnoteReference': {}})
                el['endIndex'] += 1
                for later in doc['body']['content']:
                    if later is not el and later['startIndex'] >= at:
                        shift(later, 1)
                break
        merged, changes = ds.merge_remote(MINUTES, doc)
        self.assertEqual((merged, changes), (MINUTES, []))
        new = MINUTES.replace('主要來自三篇文章', '主要來自四篇文章')
        plan = ds.plan_push(doc, MINUTES, new)
        self.assertEqual(plan.conflicts, [])
        self.assertEqual(docsim.after_push(doc, plan), docsim.want(new))
        new = MINUTES.replace('**12%**，主要', '**一成**，主要')               # the words before the mark
        plan = ds.plan_push(doc, MINUTES, new)
        self.assertEqual(plan.conflicts, [])
        self.assertEqual(docsim.after_push(doc, plan), docsim.want(new))
        plan = ds.plan_push(doc, MINUTES, MINUTES.replace('**12%**，主要', '一成主要'))
        self.assertEqual(len(plan.conflicts), 1)                         # across the mark: it would delete it

    def test_removing_the_paragraph_right_before_a_table(self):
        new = MINUTES.replace('## 四、行動方案\n\n', '')
        plan = ds.plan_push(fake_doc(MINUTES), MINUTES, new)
        self.assertEqual(docsim.after_push(fake_doc(MINUTES), plan), docsim.want(new))

    def test_a_paragraph_with_a_picture_can_still_be_edited(self):
        md = '# 標題\n\n![圖](data:image/png;base64,iVBORw0KGgo=)圖一：流量\n\n結尾\n'
        doc = fake_doc(md)
        par = next(el for el in doc['body']['content'] if 'paragraph' in el
                   and '圖一' in el['paragraph']['elements'][0]['textRun']['content'])
        at = par['startIndex']
        for el in doc['body']['content']:
            if el['startIndex'] >= at:
                shift(el, 1)
        par['startIndex'] = at
        par['paragraph']['elements'].insert(0, {'startIndex': at, 'endIndex': at + 1, 'inlineObjectElement': {}})
        self.assertEqual(ds.merge_remote(md, doc), (md, []))
        new = md.replace('流量', '流量走勢')
        plan = ds.plan_push(doc, md, new)
        self.assertEqual(plan.conflicts, [])
        self.assertEqual(docsim.after_push(doc, plan), docsim.want(new))

    def test_a_push_whose_answer_was_lost_is_not_sent_twice(self):
        local = MINUTES.replace('- 主要投放在 Threads 與 Instagram。', '- 主要投放在 Threads 與 Instagram。\n- 新增一條。')
        saved = ds.get_doc, ds.batch_update
        try:
            ds.get_doc = lambda doc_id: fake_doc(local)                 # the first try got there
            ds.batch_update = lambda *a: self.fail('sent twice')
            plan, _, as_planned = ds.push('D', MINUTES, local)
            self.assertEqual((plan.requests, as_planned), ([], True))
        finally:
            ds.get_doc, ds.batch_update = saved


def shift(el: dict, n: int):
    el['startIndex'] += n
    el['endIndex'] += n
    for e in el.get('paragraph', {}).get('elements', []):
        e['startIndex'] += n
        e['endIndex'] += n
    for row in el.get('table', {}).get('tableRows', []):
        for cell in row['tableCells']:
            for p in cell['content']:
                shift(p, n)


class Preview(unittest.TestCase):
    def test_what_the_user_types_stays_text(self):
        md = minutes_html.back('<p>a*b*c and `x` and file_name [__]</p>')
        self.assertEqual(ds.plain(md.strip()), 'a*b*c and `x` and file_name [__]')

    def test_small_headings_and_code_survive(self):
        md = minutes_html.back('<h5>小標</h5><p>用 <code>git pull</code> 更新</p>')
        self.assertEqual(md, '##### 小標\n\n用 `git pull` 更新\n')

    def test_a_mark_never_lands_inside_a_link_address(self):
        lines = ['見 [報告](https://example.com/2026/q4) 的 2026 數字']
        minutes_app.wrap_in_lines(lines, 0, 0, '2026', '[', ']')
        self.assertEqual(lines, ['見 [報告](https://example.com/2026/q4) 的 [2026] 數字'])

    def test_bold_reads_the_way_the_preview_and_the_doc_show_it(self):
        self.assertEqual(ds.plain('請**「行銷部」**提供'), '請**「行銷部」**提供')     # CommonMark: literal here
        self.assertEqual(ds.spans('增加 **12%**，主要')[1], [(3, 6, True, None)])

    def test_characters_typed_in_the_doc_read_back_the_same(self):
        doc = fake_doc(MINUTES)
        typed = {'主要來自三篇文章。': '主要來自 *三* 篇 **文章**。', '結尾。': '1. 不是清單'}
        for el in doc['body']['content']:            # a colleague typed these as plain text in the Doc
            for e in el.get('paragraph', {}).get('elements', []):
                for old, new in typed.items():
                    if old in e['textRun']['content']:
                        e['textRun']['content'] = e['textRun']['content'].replace(old, new)
        merged, changes = ds.merge_remote(MINUTES, doc)
        self.assertEqual(len(changes), 1)
        self.assertIn('會中說明：上個月網站流量增加 12%，主要來自 *三* 篇 **文章**。', plains(merged))
        self.assertEqual(ds.merge_remote(merged, doc), (merged, []))     # no phantom edit on the next open
        line = ds.escape_lead(ds.escape_md('1. 不是清單'))
        self.assertEqual([(b.kind, b.plain) for b in ds.parse(line)[1]], [('p', '1. 不是清單')])

    def test_a_mark_never_lands_on_a_list_number(self):
        lines = ['1. 預算 1 萬元。']
        minutes_app.wrap_in_lines(lines, 0, 0, '1', '[', ']')
        self.assertEqual(lines, ['1. 預算 [1] 萬元。'])


class DocInWindow(Flows):
    """The window shows the Google Doc itself; refresh brings what was typed there into the minutes."""

    def setUp(self):
        super().setUp()
        self.google = Google(MINUTES)
        ds.push = self.google.push
        ds.get_doc = lambda doc_id: self.google.doc()
        ds.batch_update = lambda *a: self.fail('nothing should go to Google directly')
        (self.job_dir / '同步.json').write_text(json.dumps({'revision': 'r0'}), encoding='utf-8')

    def typed_by(self, who: dict, old: str, new: str, listed: str = LISTED):
        ds.revisions_since = lambda *a: [{'lastModifyingUser': who, 'modifiedTime': listed}]
        self.google.md = self.google.md.replace(old, new)
        minutes_app.cmd_refresh(self.job())
        return self.outs[-1]

    def test_what_the_user_types_in_the_doc_is_learned(self):
        r = self.typed_by({'me': True, 'displayName': 'Vin'}, 'Threads 與 Instagram', 'Threads 與 IG')
        self.assertIn('IG', ' '.join(item['text'] for item in r['learned']))
        self.assertIn('Threads 與 IG', self.md_path.read_text(encoding='utf-8'))
        self.assertIn('在 Google 文件', (self.job_dir / '操作紀錄.jsonl').read_text(encoding='utf-8'))
        self.assertEqual(self.google.sent, [])                       # nothing went back up

    def test_what_a_colleague_types_in_the_doc_is_logged_and_never_learned(self):
        r = self.typed_by({'displayName': 'Amy', 'emailAddress': 'amy@example.com'}, 'Threads 與 Instagram', 'Threads 與 IG')
        self.assertEqual(r['learned'], [])
        self.assertIn('Threads 與 IG', self.md_path.read_text(encoding='utf-8'))
        self.assertIn('"who": "Amy"', (self.job_dir / '操作紀錄.jsonl').read_text(encoding='utf-8'))

    def test_a_blank_filled_in_the_doc_leaves_the_side_panel(self):
        result = json.loads((self.job_dir / 'result.json').read_text(encoding='utf-8'))
        result['todo'] = [{'label': '主持人', 'line': '主持人：'}, {'label': '負責', 'line': '社群活動執行'}]
        (self.job_dir / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        self.assertEqual([t['label'] for t in minutes_app.todo_items(self.job(), MINUTES)], ['主持人', '負責'])
        r = self.typed_by({'me': True}, '主持人：[__]', '主持人：王小明')
        self.assertEqual([t['label'] for t in r['todo']], ['負責'])

    def test_an_edit_drive_has_not_listed_yet_waits_for_the_next_refresh(self):
        r = self.typed_by({'me': True}, 'Threads 與 Instagram', 'Threads 與 IG', listed='2026-10-15T01:40:00.000Z')
        self.assertEqual(r['learned'], [])
        self.assertNotIn('IG', self.md_path.read_text(encoding='utf-8'))      # not taken in under nobody's name
        self.assertFalse((self.job_dir / '操作紀錄.jsonl').is_file())
        state = json.loads((self.job_dir / '同步.json').read_text(encoding='utf-8'))
        state['waiting_since'] = '2026-10-15T09:00:00+08:00'                  # two minutes and more ago
        (self.job_dir / '同步.json').write_text(json.dumps(state), encoding='utf-8')
        minutes_app.cmd_refresh(self.job())
        self.assertIn('Threads 與 IG', self.md_path.read_text(encoding='utf-8'))

    def test_an_item_is_located_by_how_far_down_the_doc_it_is(self):
        doc = fake_doc(MINUTES)
        ds.get_doc = lambda doc_id: doc
        minutes_app.cmd_locate(self.job(), '社群活動執行')
        at = self.outs[-1]['at']
        self.assertTrue(0.7 < at < 1, at)                                      # the table at the end of the minutes
        minutes_app.cmd_locate(self.job(), '主持人')
        self.assertLess(self.outs[-1]['at'], 0.3)
        minutes_app.cmd_locate(self.job(), '不在文件裡的字')
        self.assertEqual(self.outs[-1], {'at': None})

    def test_each_item_knows_the_words_to_look_for_in_the_doc(self):
        plains = [b.plain for b in ds.parse(MINUTES)[1]]
        self.assertEqual(minutes_app.find_words(plains, '社群活動執行', '負責'), '社群活動執行')
        self.assertEqual(minutes_app.find_words(plains, '', '講者 B 推測是 Ken'), 'Ken')
        self.assertEqual(minutes_app.find_words(plains, 'Threads', '「Fresh」推測是 Threads'), 'Threads')
        self.assertEqual(minutes_app.find_words(plains, '', '完全無關'), '')

    def test_a_refresh_never_waits_for_a_claude_rewrite(self):
        held = minutes_app.try_turn(self.job())
        self.assertIsNotNone(held)
        argv, sys.argv = sys.argv, ['minutes_app.py', 'refresh', str(self.job_dir)]
        try:
            minutes_app.main()
        finally:
            sys.argv = argv
            held.close()
            minutes_app.TURN.clear()
        self.assertEqual(self.outs[-1], {'busy': True})



class TimeZone(unittest.TestCase):
    """The calendar is read and invitations are made in the Mac's own time zone, not Taiwan's."""

    def setUp(self):
        import time
        self.saved = os.environ.get('TZ')
        os.environ['TZ'] = 'America/New_York'
        time.tzset()

    def tearDown(self):
        import time
        if self.saved is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = self.saved
        time.tzset()

    def test_a_day_in_new_york_is_asked_for_in_new_york_time_summer_and_winter(self):
        import workspace
        from datetime import date
        self.assertEqual(workspace.zone_name(), 'America/New_York')
        self.assertIn('timeMin=2026-07-01T00%3A00%3A00-04%3A00', workspace.day_query(date(2026, 7, 1)))
        self.assertIn('timeMin=2026-12-01T00%3A00%3A00-05%3A00', workspace.day_query(date(2026, 12, 1)))


if __name__ == '__main__':
    unittest.main()


RED = {'foregroundColor': {'color': {'rgbColor': dict(ds.BLANK_INK)}},
       'backgroundColor': {'color': {'rgbColor': dict(ds.BLANK_GROUND)}}}


def painted(doc: dict, words: str, style: dict) -> dict:
    """The Doc with the first run holding `words` split so that those words carry `style`."""
    def walk(content):
        for el in content:
            par = el.get('paragraph')
            for i, e in enumerate((par or {}).get('elements', [])):
                text = e.get('textRun', {}).get('content', '')
                k = text.find(words)
                if k < 0:
                    continue
                a, b = e['startIndex'] + ds.u16(text[:k]), e['startIndex'] + ds.u16(text[:k + len(words)])
                base = e['textRun'].get('textStyle', {})
                parts = [(text[:k], e['startIndex'], a, base), (words, a, b, {**base, **style}),
                         (text[k + len(words):], b, e['endIndex'], base)]
                par['elements'][i:i + 1] = [{'startIndex': s, 'endIndex': t, 'textRun': {'content': c, 'textStyle': st}}
                                            for c, s, t, st in parts if c]
                return True
            for row in el.get('table', {}).get('tableRows', []):
                for cell in row['tableCells']:
                    if walk(cell['content']):
                        return True
        return False
    assert walk(doc['body']['content']), words
    return doc


def paint_all(doc: dict) -> dict:
    """The Doc with every [__] carrying the blank's look, as paint_blanks leaves it."""
    def walk(content):
        for el in content:
            par = el.get('paragraph')
            if par:
                out = []
                for e in par['elements']:
                    text, at = e['textRun']['content'], e['startIndex']
                    for piece in re.split(r'(\[__\])', text):
                        if piece:
                            st = {**e['textRun'].get('textStyle', {}), **(RED if piece == '[__]' else {})}
                            out.append({'startIndex': at, 'endIndex': at + ds.u16(piece),
                                        'textRun': {'content': piece, 'textStyle': st}})
                            at += ds.u16(piece)
                par['elements'] = out
            for row in el.get('table', {}).get('tableRows', []):
                for cell in row['tableCells']:
                    walk(cell['content'])
    walk(doc['body']['content'])
    return doc


def at_of(doc: dict, words: str) -> int:
    """The Doc index where `words` first starts."""
    for u in ds.units(doc):
        k = u.text.find(words)
        if k >= 0:
            return u.pos[k]
    raise AssertionError(words)


class Blanks(Flows):
    """Every [__] in the Doc is red on pale red; words typed into one go back to plain text."""

    def setUp(self):
        super().setUp()
        self.doc = fake_doc(MINUTES)
        ds.get_doc = ds.get_doc_inline = lambda doc_id: self.doc
        self.sent = []

    def paint(self, doc_id, requests, revision):
        self.sent.append((requests, revision))
        return {'writeControl': {'requiredRevisionId': 'r2'}}

    def test_every_blank_is_painted_and_nothing_else(self):
        reqs = ds.blank_requests(self.doc)
        spans = sorted((r['updateTextStyle']['range']['startIndex'], r['updateTextStyle']['range']['endIndex'])
                       for r in reqs)
        starts = []
        for u in ds.units(self.doc):
            k = u.text.find('[__]')
            while k >= 0:
                starts.append(u.pos[k])
                k = u.text.find('[__]', k + 4)
        self.assertEqual(len(starts), 3)                       # 主持人, and two in the table
        self.assertEqual(spans, [(a, a + 4) for a in sorted(starts)])
        self.assertTrue(all(r['updateTextStyle']['textStyle'] == RED for r in reqs))

    def test_a_painted_doc_needs_nothing(self):
        self.assertEqual(ds.blank_requests(paint_all(fake_doc(MINUTES))), [])
        self.assertEqual(ds.blank_requests(fake_doc(MINUTES.replace('[__]', 'XXXX'))), [])

    def test_words_typed_into_a_blank_go_back_to_plain_text(self):
        doc = painted(fake_doc(MINUTES.replace('主持人：[__]', '主持人：王小明')), '王小明', RED)
        reqs = ds.blank_requests(doc)
        plain = [r for r in reqs if r['updateTextStyle']['textStyle'] == {}]
        a = at_of(doc, '王小明')
        self.assertEqual([(r['updateTextStyle']['range']['startIndex'], r['updateTextStyle']['range']['endIndex'])
                          for r in plain], [(a, a + 3)])
        self.assertEqual(plain[0]['updateTextStyle']['fields'], 'foregroundColor,backgroundColor')

    def test_text_inserted_next_to_a_blank_does_not_copy_its_red(self):
        self.assertNotIn('foregroundColor', ds.look_of({**RED, 'fontSize': {'magnitude': 11}}))
        self.assertIn('fontSize', ds.look_of({**RED, 'fontSize': {'magnitude': 11}}))
        ink = {'foregroundColor': {'color': {'rgbColor': {'red': 0.1, 'green': 0.2, 'blue': 0.3}}}}
        self.assertEqual(ds.look_of(ink), ink)

    def test_opening_a_meeting_paints_its_blanks_on_the_doc_it_just_synced(self):
        (self.job_dir / '同步.json').write_text(json.dumps({'revision': 'r1'}), encoding='utf-8')
        ds.paint_blanks = self.saved['paint_blanks']
        ds.batch_update = self.paint
        minutes_app.cmd_open(self.job())
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][1], 'r1')                # refused by Google if someone typed meanwhile
        state = json.loads((self.job_dir / '同步.json').read_text(encoding='utf-8'))
        self.assertEqual(state['revision'], 'r2')              # the next refresh does not take it for an edit
        self.assertIn('own_until', state)                      # nor Drive's listing of it for the user's edit

    def test_nothing_is_painted_while_a_colleagues_suggestion_is_pending(self):
        (self.job_dir / '同步.json').write_text(json.dumps({'revision': 'r1'}), encoding='utf-8')
        ds.paint_blanks = self.saved['paint_blanks']
        ds.batch_update = self.paint
        suggested = json.loads(json.dumps(self.doc))
        suggested['body']['content'][2]['paragraph']['elements'][0]['textRun']['suggestedInsertionIds'] = ['s1']
        ds.get_doc_inline = lambda doc_id: suggested
        minutes_app.cmd_open(self.job())
        self.assertEqual(self.sent, [])

    def test_the_apps_own_change_is_never_put_down_to_anyone(self):
        job = self.job()
        job.state['own_until'] = '2026-10-15T09:43:14+08:00'
        revs = [{'lastModifyingUser': {'me': True}, 'modifiedTime': '2026-10-15T01:43:09.375Z'},     # the paint
                {'lastModifyingUser': {'displayName': 'Amy'}, 'modifiedTime': '2026-10-15T01:44:00.000Z'}]
        self.assertEqual(minutes_app.authors_since(job, revs=revs), ['Amy'])
        revs.append({'lastModifyingUser': {'me': True}, 'modifiedTime': '2026-10-15T01:45:00.000Z'})  # typed later
        self.assertEqual(minutes_app.authors_since(job, revs=revs), ['Amy', '你'])

    def test_text_typed_next_to_a_blank_loses_its_pale_red_ground_too(self):
        reqs = ds.style_requests(5, '王小明', [], False, {**RED, 'fontSize': {'magnitude': 11}})
        fields = reqs[0]['updateTextStyle']['fields'].split(',')
        self.assertIn('backgroundColor', fields)
        self.assertNotIn('backgroundColor', reqs[0]['updateTextStyle']['textStyle'])

    def test_nothing_is_painted_while_a_colleagues_edit_waits_for_drive(self):
        (self.job_dir / '同步.json').write_text(json.dumps({'revision': 'r0'}), encoding='utf-8')
        ds.paint_blanks = self.saved['paint_blanks']
        ds.batch_update = self.paint
        ds.revisions_since = lambda *a: [{'lastModifyingUser': {'displayName': 'Amy'}, 'modifiedTime': '2026-10-15T01:40:00.000Z'}]
        self.doc = fake_doc(MINUTES.replace('Threads 與 Instagram', 'Threads 與 IG'))
        minutes_app.cmd_refresh(self.job())
        self.assertEqual(self.sent, [])

    def test_a_colleague_typing_at_that_moment_leaves_the_blanks_for_the_next_refresh(self):
        (self.job_dir / '同步.json').write_text(json.dumps({'revision': 'r1'}), encoding='utf-8')
        ds.paint_blanks = self.saved['paint_blanks']

        def refused(*a):
            raise SystemExit('HTTP 400 from Google: The required revision ID does not match')
        ds.batch_update = refused
        minutes_app.cmd_refresh(self.job())
        self.assertEqual(self.outs[-1]['warning'], '')
        state = json.loads((self.job_dir / '同步.json').read_text(encoding='utf-8'))
        self.assertEqual(state['revision'], 'r1')


def png(path: Path, w: int = 8, h: int = 6) -> Path:
    """A real, tiny PNG (sips reads its size)."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\x00' + b'\x80\x80\x80' * w for _ in range(h))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    return path


class AttachmentsSection(unittest.TestCase):
    """「參考附件」 is in every set of minutes, 無 when nothing was attached (Vin 2026-10-20); the first attachment
    takes the place of 無, and old minutes that still say 補充資訊 keep working. It is the seventh section since
    待確認事項 went into 行動方案 (Vin 2026-10-28); minutes written before then keep it as the eighth."""

    def test_the_section_is_named_and_the_first_attachment_replaces_none(self):
        import attachments
        self.assertEqual(attachments.SECTION, '## 七、參考附件')
        self.assertEqual(attachments.SECTIONS['en'], '## 7. Attachments')
        md = MINUTES + '\n## 八、參考附件\n\n無\n'
        out = attachments.add_lines(md, ['- Amy 的報表：[a.xlsx](https://drive.google.com/file/d/1/view)'])
        self.assertTrue(out.endswith('## 八、參考附件\n\n- Amy 的報表：[a.xlsx](https://drive.google.com/file/d/1/view)\n'))
        self.assertNotIn('\n無\n', out)
        out = attachments.add_lines(MINUTES + '\n## 8. Attachments\n\nNone\n', ['- [a.pdf](https://x/a)'])
        self.assertTrue(out.endswith('## 8. Attachments\n\n- [a.pdf](https://x/a)\n'))
        self.assertEqual(attachments.listed(md), [])                     # 無 is not an attachment
        # 無 beside a link stays; a 無 in another section is not the attachments' 無
        kept = attachments.add_lines(MINUTES + '\n## 八、參考附件\n\n無\n- [b.pdf](https://x/b)\n', ['- [a.pdf](https://x/a)'])
        self.assertIn('無\n- [b.pdf](https://x/b)\n- [a.pdf](https://x/a)\n', kept)
        other = MINUTES.replace('## 二、討論摘要\n\n', '## 二、討論摘要\n\n無\n\n') + '\n## 八、參考附件\n\n無\n\n## 九、備註\n\n備註一\n'
        out = attachments.add_lines(other, ['- [a.pdf](https://x/a)'])
        self.assertIn('## 二、討論摘要\n\n無\n\n', out)
        self.assertIn('## 八、參考附件\n\n- [a.pdf](https://x/a)\n\n## 九、備註\n', out)

    def test_minutes_without_the_section_get_it_and_old_minutes_keep_their_heading(self):
        import attachments
        out = attachments.add_lines(MINUTES, ['- [a.pdf](https://x/a)'])
        self.assertTrue(out.endswith('## 七、參考附件\n\n- [a.pdf](https://x/a)\n'))
        seven = MINUTES + '\n## 七、參考附件\n\n無\n'                  # the layout since v0.4.24
        out = attachments.add_lines(seven, ['- [a.pdf](https://x/a)'])
        self.assertTrue(out.endswith('## 七、參考附件\n\n- [a.pdf](https://x/a)\n'))
        self.assertEqual(attachments.listed(out)[0]['name'], 'a.pdf')
        eight = MINUTES + '\n## 七、其他建議\n\n建議下週再談。\n'           # written before it, without the section
        out = attachments.add_lines(eight, ['- [a.pdf](https://x/a)'])
        self.assertTrue(out.endswith('## 七、其他建議\n\n建議下週再談。\n\n## 八、參考附件\n\n- [a.pdf](https://x/a)\n'))
        self.assertEqual(attachments.listed(eight + '\n## 八、參考附件\n\n- [b.pdf](https://x/b)\n')[0]['name'], 'b.pdf')
        self.assertEqual(attachments.listed(eight + '- [c.pdf](https://x/c)\n'), [])   # 其他建議 is not the attachments
        lower = attachments.add_lines('## 1. Meeting Details\n\n## 7. other suggestions\n\nLater.\n', ['- [a.pdf](https://x/a)'])
        self.assertTrue(lower.endswith('## 8. Attachments\n\n- [a.pdf](https://x/a)\n'))
        out = attachments.add_lines('## 1. Meeting Details\n\n- Date: Oct 14\n\n## 7. Other Suggestions\n\nLater.\n',
                                    ['- [a.pdf](https://x/a)'])
        self.assertTrue(out.endswith('## 8. Attachments\n\n- [a.pdf](https://x/a)\n'))
        old = MINUTES + '\n## 八、補充資訊\n\n- [b.pdf](https://x/b)\n'
        out = attachments.add_lines(old, ['- [a.pdf](https://x/a)'])
        self.assertTrue(out.endswith('## 八、補充資訊\n\n- [b.pdf](https://x/b)\n- [a.pdf](https://x/a)\n'))
        self.assertEqual(out.count('## 八、'), 1)


class Attach(Flows):
    """Files, links and pictures from the box under the Doc become lines of 「八、參考附件」."""

    def setUp(self):
        super().setUp()
        import attachments
        self.at = attachments
        self.saved_at = {n: getattr(attachments, n) for n in ('folder_for', 'upload', 'show_picture', 'call',
                                                                'close_link')}
        self.google = Google(MINUTES)
        ds.push = self.google.push
        ds.get_doc = ds.get_doc_inline = lambda doc_id: self.google.doc()
        (self.job_dir / '同步.json').write_text(json.dumps({'revision': 'r1'}), encoding='utf-8')
        self.uploaded, self.shown = [], []
        attachments.folder_for = lambda state, doc_id, lang="zh-TW": state.setdefault('attach_folder', 'F')
        attachments.upload = lambda path, folder, name, mime='': (
            self.uploaded.append((name, folder, mime))
            or {'id': f'id{len(self.uploaded)}', 'link': f'https://drive.google.com/file/d/id{len(self.uploaded)}/view'})
        attachments.show_picture = lambda doc_id, doc, fid, width: self.shown.append(fid) or {'revision': 'r9'}
        self.files = self.root / 'picked'
        self.files.mkdir()
        (self.files / '9月流量報表.xlsx').write_bytes(b'xlsx')
        png(self.files / '主視覺.png')

    def tearDown(self):
        for n, fn in self.saved_at.items():
            setattr(self.at, n, fn)
        super().tearDown()

    def attach(self, note, *items):
        minutes_app.cmd_attach(self.job(), note, json.dumps(list(items)))
        return self.outs[-1]

    def state(self) -> dict:
        return json.loads((self.job_dir / '同步.json').read_text(encoding='utf-8'))

    def test_a_file_a_picture_and_a_link_become_lines_of_the_attachments(self):
        sidecar = self.root / 'minutes.md.gdoc.json'
        sidecar.write_text(json.dumps({'id': 'D' * 30, 'mails': []}), encoding='utf-8')
        r = self.attach('Amy 提供的資料', {'kind': 'file', 'path': str(self.files / '9月流量報表.xlsx')},
                        {'kind': 'image', 'path': str(self.files / '主視覺.png')},
                        {'kind': 'link', 'url': 'https://example.com/post'})
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('## 七、參考附件', md)
        self.assertIn('- Amy 提供的資料：[9月流量報表.xlsx](https://drive.google.com/file/d/id1/view)', md)
        self.assertIn('- Amy 提供的資料：[https://example.com/post](https://example.com/post)', md)
        self.assertIn('![主視覺.png](minutes_附件/主視覺.png)', md)            # the Word file has the picture too
        self.assertTrue((self.root / 'minutes_附件' / '主視覺.png').is_file())
        self.assertEqual(self.uploaded, [('9月流量報表.xlsx', 'F', 'application/vnd.openxmlformats-officedocument'
                                                                  '.spreadsheetml.sheet'), ('主視覺.png', 'F', 'image/png')])
        self.assertIn('[9月流量報表.xlsx](https://drive.google.com/file/d/id1/view)', self.google.md)
        self.assertEqual(self.shown, ['id2'])
        self.assertEqual((self.state()['revision'], self.state()['attach_folder'], self.state()['pictures']),
                         ('r9', 'F', []))
        self.assertIn('own_until', self.state())                          # the picture is not a colleague's edit
        self.assertIn('9月流量報表.xlsx', r['reply'])
        self.assertEqual(r['warning'], '')
        self.assertIn('參考附件', (self.job_dir / '操作紀錄.jsonl').read_text(encoding='utf-8'))
        record = json.loads(sidecar.read_text(encoding='utf-8'))      # the files the mail opens to its recipients
        self.assertEqual((record['attach_files'], record['mails']), (['id1', 'id2'], []))

    def test_without_a_sentence_the_line_is_the_name_and_later_lines_follow_the_earlier_ones(self):
        self.attach('', {'kind': 'file', 'path': str(self.files / '9月流量報表.xlsx')})
        self.attach('# Ken 會後補充', {'kind': 'link', 'url': 'https://example.com/a'})
        md = self.md_path.read_text(encoding='utf-8')
        tail = md.split('## 七、參考附件', 1)[1].strip().splitlines()
        self.assertEqual(tail, ['- [9月流量報表.xlsx](https://drive.google.com/file/d/id1/view)',
                                '- \\# Ken 會後補充：[https://example.com/a](https://example.com/a)'])
        self.assertEqual(md.count('## 七、參考附件'), 1)

    def test_each_item_is_led_by_its_own_note_and_the_row_above_the_minutes_lists_them(self):
        r = self.attach('', {'kind': 'file', 'path': str(self.files / '9月流量報表.xlsx'), 'note': ' Pitt 要的\n各通路業績 '},
                        {'kind': 'link', 'url': 'https://example.com/post', 'note': ''})
        tail = self.md_path.read_text(encoding='utf-8').split('## 七、參考附件', 1)[1].strip().splitlines()
        self.assertEqual(tail, ['- Pitt 要的 各通路業績：[9月流量報表.xlsx](https://drive.google.com/file/d/id1/view)',
                                '- [https://example.com/post](https://example.com/post)'])
        self.assertEqual(r['attachments'], [
            {'name': '9月流量報表.xlsx', 'link': 'https://drive.google.com/file/d/id1/view', 'note': 'Pitt 要的 各通路業績',
             'kind': 'file'},
            {'name': 'https://example.com/post', 'link': 'https://example.com/post', 'note': '', 'kind': 'link'}])

    def test_the_list_reads_lines_typed_in_the_doc_and_stops_at_the_next_section(self):
        md = (MINUTES + '\n## 八、參考附件\n\n- Ken 的簡報：[a\\]b.pdf](https://drive.google.com/file/d/X/view)\n'
              '- 沒有連結的一行\n![主視覺.png](m_附件/主視覺.png)\n- [主視覺.png](https://drive.google.com/file/d/Y/view)\n'
              '\n## 九、其他\n\n- [不算](https://example.com)\n')
        self.assertEqual([(a['name'], a['note'], a['kind']) for a in self.at.listed(md)],
                         [('a]b.pdf', 'Ken 的簡報', 'file'), ('主視覺.png', '', 'image')])
        self.assertEqual(self.at.listed(MINUTES), [])


    def test_lines_go_into_an_existing_section_eight_before_whatever_follows_it(self):
        md = MINUTES.replace('## 四、行動方案', '## 八、參考附件\n\n- 舊的一行\n\n## 四、行動方案')
        out = self.at.add_lines(md, ['- 新的一行'])
        self.assertIn('- 舊的一行\n- 新的一行\n\n## 四、行動方案', out)
        self.assertEqual(self.at.lines_for([{'kind': 'file', 'name': 'a]b.pdf', 'link': 'https://x/(1)'}], ''),
                         ['- [a\\]b.pdf](https://x/%281%29)'])

    def test_a_colleague_changing_the_end_of_the_minutes_first_does_not_lose_the_new_lines(self):
        self.google.md = MINUTES.replace('| Ken | 先找兩位 😀 |', '| Amy | 先找兩位 😀 |')    # typed in the Doc
        r = self.attach('', {'kind': 'file', 'path': str(self.files / '9月流量報表.xlsx')})
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('[9月流量報表.xlsx]', md)
        self.assertIn('| Amy | 先找兩位', md)
        self.assertIn('[9月流量報表.xlsx]', self.google.md)
        self.assertNotIn('刪掉一段', (self.job_dir / '操作紀錄.jsonl').read_text(encoding='utf-8'))
        self.assertIn('參考附件', r['reply'])

    def test_lines_a_colleague_crowds_out_are_reported_not_announced(self):
        def push(doc_id, base, new):                       # the Doc refuses the new lines: both neighbours changed
            plan = ds.Plan([], [ds.plain(line) for line in new.splitlines() if 'xlsx' in line], [])
            return plan, self.google.doc(), True
        ds.push = push
        trashed = []
        self.at.call = lambda url, body=None, method=None, **k: trashed.append((url, body, method)) or {}
        r = self.attach('', {'kind': 'file', 'path': str(self.files / '9月流量報表.xlsx')})
        self.assertEqual((r['warning'], r['reply']), (self.at.CROWDED, ''))
        self.assertEqual(trashed, [(ds.DRIVE + 'id1?fields=id', {'trashed': True}, 'PATCH')])   # no second copy later
        log = (self.job_dir / '操作紀錄.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('加了', log)

    def test_new_lines_at_the_end_still_go_in_when_a_colleague_changed_the_last_paragraph(self):
        base = MINUTES + '\n## 七、其他建議\n\n建議下次再談。\n'
        doc = fake_doc(base.replace('建議下次再談。', '建議下週再談。'))       # the colleague's edit, not synced yet
        new = base + '\n## 八、參考附件\n\n- [a.pdf](https://x/a)\n'
        plan = ds.plan_push(doc, base, new)
        self.assertEqual(plan.conflicts, [])
        after = docsim.after_push(doc, plan)
        self.assertEqual(after[-3:], [('p', '建議下週再談。'), ('h2', '八、參考附件'), ('li', 'a.pdf')])

    def test_a_picture_waits_while_the_doc_has_moved_on_and_goes_in_with_the_next_refresh(self):
        doc = self.google.doc()
        ds.get_doc_inline = lambda doc_id: {**doc, 'revisionId': 'r-colleague'}    # someone typed meanwhile
        self.attach('', {'kind': 'image', 'path': str(self.files / '主視覺.png')})
        self.assertEqual((self.shown, [p['id'] for p in self.state()['pictures']]), ([], ['id1']))
        ds.get_doc_inline = lambda doc_id: self.google.doc()
        minutes_app.cmd_refresh(self.job())
        self.assertEqual((self.shown, self.state()['pictures']), (['id1'], []))

    def test_each_picture_goes_in_only_on_the_revision_the_one_before_it_left(self):
        png(self.files / '第二張.png')
        self.attach('', {'kind': 'image', 'path': str(self.files / '主視覺.png')},
                    {'kind': 'image', 'path': str(self.files / '第二張.png')})
        # the Doc read after the first picture is not the revision that picture made: the second one waits
        self.assertEqual((self.shown, [p['id'] for p in self.state()['pictures']]), (['id1'], ['id2']))

    def test_a_picture_the_account_cannot_share_by_link_stays_a_link(self):
        self.at.show_picture = lambda *a: {'why': 'shared'}
        r = self.attach('', {'kind': 'image', 'path': str(self.files / '主視覺.png')})
        self.assertEqual(r['warning'], self.at.NO_PUBLIC)
        self.assertEqual(self.state()['pictures'], [])
        self.assertIn('[主視覺.png](https://drive.google.com/file/d/id1/view)', self.md_path.read_text(encoding='utf-8'))

    def test_a_link_left_open_is_closed_on_the_next_sync(self):
        self.at.show_picture = lambda *a: {'revision': 'r9', 'open': {'file': 'id1', 'perm': 'anyoneWithLink'}}
        closed = []
        self.at.close_link = lambda f, p: closed.append(f) or len(closed) > 1
        self.attach('', {'kind': 'image', 'path': str(self.files / '主視覺.png')})
        self.assertEqual(self.state()['open_links'], [{'file': 'id1', 'perm': 'anyoneWithLink'}])
        (self.job_dir / '同步.json').write_text(json.dumps({**self.state(), 'revision': 'r1'}), encoding='utf-8')
        minutes_app.cmd_refresh(self.job())                          # Google still does not answer the first time
        self.assertEqual((closed, len(self.state()['open_links'])), (['id1'], 1))
        minutes_app.cmd_refresh(self.job())
        self.assertEqual((closed, self.state()['open_links']), (['id1', 'id1'], []))

    def test_nothing_changes_when_drive_cannot_be_reached(self):
        def offline(*a, **k):
            raise SystemExit('OFFLINE: Google did not answer')
        self.at.upload = offline
        with self.assertRaises(SystemExit) as caught:
            self.attach('', {'kind': 'file', 'path': str(self.files / '9月流量報表.xlsx')})
        self.assertEqual(str(caught.exception), self.at.OFFLINE)
        self.assertEqual(self.md_path.read_text(encoding='utf-8'), MINUTES)

    def test_a_file_that_is_not_a_picture_stops_everything_before_any_upload(self):
        (self.files / 'notes.svg').write_text('<svg/>')
        with self.assertRaises(SystemExit) as caught:
            self.attach('', {'kind': 'file', 'path': str(self.files / '9月流量報表.xlsx')},
                        {'kind': 'image', 'path': str(self.files / 'notes.svg')})
        self.assertIn('notes.svg', str(caught.exception))
        self.assertEqual(self.uploaded, [])

    def test_what_the_window_sends_is_checked(self):
        for raw, words in (('[]', self.at.NO_ITEMS), ('[{"kind": "file", "path": "/nope/a.pdf"}]', 'a.pdf'),
                           ('[{"kind": "link", "url": "javascript:alert(1)"}]', 'http')):
            with self.assertRaises(SystemExit) as caught:
                self.at.items_from(raw)
            self.assertIn(words, str(caught.exception))

    def test_the_picture_goes_into_a_paragraph_of_its_own_under_its_line_and_the_link_closes_again(self):
        self.at.show_picture = self.saved_at['show_picture']
        md = self.at.add_lines(MINUTES, ['- Amy：[同名.png](https://drive.google.com/file/d/AAA/view)',
                                         '- Ken：[同名.png](https://drive.google.com/file/d/BBB/view)'])
        doc = fake_doc(md)
        calls, sent = [], []
        self.at.call = lambda url, body=None, method=None, **k: calls.append((url, method)) or {'id': 'anyoneWithLink'}
        ds.batch_update = lambda doc_id, reqs, rev: sent.append((reqs, rev)) or {'writeControl': {'requiredRevisionId': 'r5'}}
        self.assertEqual(self.at.show_picture('D', doc, 'AAA', 300), {'revision': 'r5'})
        line = next(el for el in doc['body']['content']             # the line that links to it, not the same name
                    if 'Amy：' in ''.join(e['textRun']['content'] for e in el.get('paragraph', {}).get('elements', [])))
        reqs = sent[0][0]
        self.assertEqual(reqs[0]['insertText'], {'location': {'index': line['endIndex'] - 1}, 'text': '\n'})
        self.assertEqual(reqs[1]['deleteParagraphBullets']['range']['startIndex'], line['endIndex'])
        self.assertEqual(reqs[3]['insertInlineImage']['location']['index'], line['endIndex'])
        self.assertEqual(sent[0][1], 'r1')                                  # refused if someone typed meanwhile
        self.assertEqual(calls[-1], (ds.DRIVE + 'AAA/permissions/anyoneWithLink', 'DELETE'))

        def refused(*a):
            raise SystemExit('HTTP 400 from Google: revision')
        ds.batch_update = refused
        calls.clear()
        self.assertEqual(self.at.show_picture('D', doc, 'AAA', 300), {'why': 'refused'})
        self.assertEqual(calls[-1][1], 'DELETE')                           # closed again even then
        self.assertEqual(self.at.show_picture('D', doc, 'ZZZ', 300), {'why': 'line'})

    def test_a_line_added_after_a_picture_goes_under_the_picture_not_between_it_and_its_line(self):
        line_a = '- A：[p.png](https://drive.google.com/file/d/P1/view)'
        doc = fake_doc(MINUTES + f'\n## 八、參考附件\n\n{line_a}\n\nＰ\n')
        pic = next(el for el in doc['body']['content']           # the picture itself, as Google Docs has it
                   if el.get('paragraph', {}).get('elements', [{}])[0].get('textRun', {}).get('content') == 'Ｐ')
        first = pic['paragraph']['elements'][0]
        pic['paragraph']['elements'][0] = {'startIndex': first['startIndex'], 'endIndex': first['endIndex'],
                                           'inlineObjectElement': {'inlineObjectId': 'kix.1', 'textStyle': {}}}
        base = self.at.add_lines(MINUTES, [line_a, '![p.png](m_附件/p.png)'])
        new = self.at.add_lines(base, ['- B：[q.pdf](https://x/q)'])
        plan = ds.plan_push(doc, base, new)
        self.assertEqual(plan.conflicts, [])
        self.assertEqual(plan.requests[0]['insertText']['location']['index'], pic['endIndex'] - 1)

    def test_a_line_added_after_a_picture_reaches_the_doc_and_the_picture_stays_in_the_minutes(self):
        self.attach('A', {'kind': 'image', 'path': str(self.files / '主視覺.png')})
        self.attach('B', {'kind': 'file', 'path': str(self.files / '9月流量報表.xlsx')})
        self.assertEqual(self.outs[-1]['conflicts'], [])
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('![主視覺.png](minutes_附件/主視覺.png)\n\n- B：', md)
        self.assertIn('B：[9月流量報表.xlsx]', self.google.md)
        self.assertEqual(ds.merge_remote(md, fake_doc(self.google.md))[1], [])   # nobody 'removed' the picture


class AiChoice(unittest.TestCase):
    """Claude Code, Codex or Antigravity write the minutes, each able to touch only the folder it is given."""

    def setUp(self):
        import ai_runner
        self.ai = ai_runner
        self.home = Path(os.environ['MINUTES_HOME'])
        self.home.mkdir(parents=True, exist_ok=True)
        self.settings = self.home / 'settings.json'
        self.before = self.settings.read_text(encoding='utf-8') if self.settings.exists() else None
        self.folder = Path(tempfile.mkdtemp(prefix='ai-'))

    def tearDown(self):
        if self.before is None:
            self.settings.unlink(missing_ok=True)
        else:
            self.settings.write_text(self.before, encoding='utf-8')
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_the_choice_is_kept_in_settings_and_claude_is_the_default(self):
        self.settings.unlink(missing_ok=True)
        self.assertEqual((self.ai.chosen(), self.ai.name()), ('claude', 'Claude'))
        self.ai.choose('codex')
        self.assertEqual((self.ai.chosen(), self.ai.name()), ('codex', 'Codex'))
        self.assertEqual(json.loads(self.settings.read_text(encoding='utf-8'))['ai'], 'codex')
        with self.assertRaises(SystemExit):
            self.ai.choose('gpt')

    def test_each_ai_gets_its_own_way_of_staying_in_the_folder(self):
        claude, _ = self.ai.command('claude', '/x/claude', 'P', self.folder, write=True)
        self.assertEqual(claude[:3], ['/x/claude', '-p', 'P'])
        self.assertIn('--restricted', claude)
        self.assertEqual(claude[claude.index('--tools') + 1], 'Read,Glob,Grep,Write,Edit')
        edit, _ = self.ai.command('claude', '/x/claude', 'P', self.folder, write=False)
        self.assertEqual(edit[edit.index('--tools') + 1], 'Read,Write,Edit')
        codex, _ = self.ai.command('codex', '/x/codex', 'P', self.folder, write=True)
        self.assertEqual(codex[codex.index('--sandbox') + 1], 'workspace-write')
        self.assertEqual(codex[codex.index('-C') + 1], str(self.folder))
        agy, profile = self.ai.command('antigravity', '/x/agy', 'P', self.folder, write=True)
        try:
            self.assertEqual(agy[:3], ['/usr/bin/sandbox-exec', '-f', str(profile)])
            self.assertEqual(agy[3:6], ['/x/agy', '-p', 'P'])
            rules = profile.read_text()
            self.assertIn('(deny file-write*)', rules)
            self.assertIn('(deny process-exec)', rules)
            self.assertIn(str(self.folder.resolve()), rules)
        finally:
            profile.unlink()

    @unittest.skipUnless(Path('/usr/bin/sandbox-exec').exists(), 'macOS only')
    def test_inside_the_sandbox_only_the_folder_can_be_written_and_nothing_else_started(self):
        outside = Path(tempfile.mkdtemp(prefix='outside-'))                  # the temp area of every program too
        profile = self.folder.parent / (self.folder.name + '.sb')
        profile.write_text(self.ai.sandbox_profile(self.folder, '/bin/zsh'))   # /bin/sh would start bash
        try:
            run = lambda script: subprocess.run(['/usr/bin/sandbox-exec', '-f', str(profile), '/bin/zsh', '-c', script],  # noqa: E731
                                                capture_output=True, text=True, timeout=30)
            run(f'echo ok > "{self.folder}/in.txt"; echo no > "{outside}/out.txt"; /bin/ls / > "{self.folder}/ls.txt"')
            self.assertEqual((self.folder / 'in.txt').read_text().strip(), 'ok')
            self.assertFalse((outside / 'out.txt').exists())
            self.assertEqual((self.folder / 'ls.txt').read_text(), '')         # ls could not start
            home_file = Path.home() / '.zshrc'
            if home_file.exists():
                run(f'print -r -- "$(<{home_file})" > "{self.folder}/home.txt"')    # zsh reads it itself, no cat
                self.assertEqual((self.folder / 'home.txt').read_text().strip(), '')   # the user's own files stay unread
        finally:
            profile.unlink(missing_ok=True)
            shutil.rmtree(outside, ignore_errors=True)

    def test_an_ai_that_is_not_installed_says_where_to_set_it_up(self):
        saved = self.ai.find
        self.ai.find = lambda key=None: None
        try:
            with self.assertRaises(SystemExit) as caught:
                self.ai.run('P', self.folder, write=False, timeout=5, env={}, key='antigravity')
            self.assertIn('環境設定自檢', str(caught.exception))
        finally:
            self.ai.find = saved

    def test_minutes_that_carry_a_sign_in_are_not_kept(self):
        self.assertTrue(self.ai.leaks('主持人：王小明', '{"refresh_token": "1//0abcdefghijklmnop"}'))
        self.assertTrue(self.ai.leaks('GOCSPX-abcdefgh123'))
        self.assertTrue(self.ai.leaks('-----BEGIN RSA ' + 'PRIVATE KEY-----'))   # split so secret scanners skip it
        self.assertTrue(self.ai.leaks('ya29.a0AfB_byC1234567890abcdefghij'))
        # a technical meeting may name them without carrying one
        self.assertFalse(self.ai.leaks('預算 10 萬元，client 下週回覆', '討論 refresh_token 過期與 client_secret 輪替'))
        self.assertTrue(self.ai.new_leaks('舊紀錄 GOCSPX-abcdefgh123', '舊紀錄 GOCSPX-abcdefgh123 新的 GOCSPX-zzzzzzzz999'))
        self.assertFalse(self.ai.new_leaks('舊紀錄 GOCSPX-abcdefgh123', '改過的舊紀錄 GOCSPX-abcdefgh123'))

    def test_without_a_choice_the_installed_ai_writes_the_minutes(self):
        self.settings.unlink(missing_ok=True)
        saved = self.ai.find
        self.ai.find = lambda key=None: '/x/agy' if key == 'antigravity' else None
        try:
            self.assertEqual(self.ai.chosen(), 'antigravity')
        finally:
            self.ai.find = saved

    def test_the_menu_by_the_prompt_box_shows_the_ai_in_use_and_greys_out_the_missing_ones(self):
        saved = self.ai.find
        self.ai.find = lambda key=None: {'claude': '/x/claude', 'codex': '/x/codex'}.get(key or self.ai.chosen())
        try:
            self.ai.choose('codex')
            self.assertEqual(minutes_app.ai_choice(),
                             {'ai': 'codex', 'ai_name': 'Codex', 'ai_installed': ['claude', 'codex']})
            self.ai.choose('claude')
            self.assertEqual(minutes_app.ai_choice()['ai_name'], 'Claude')
        finally:
            self.ai.find = saved

    def test_the_menu_greys_out_an_ai_that_is_not_installed_or_not_signed_in(self):
        saved_find, saved_signed = self.ai.find, self.ai.signed_in
        self.ai.find = lambda key=None: None if key == 'antigravity' else f'/x/{key}'
        self.ai.signed_in = lambda key, exe: {'claude': True, 'codex': False}[key]
        try:
            self.assertEqual(self.ai.states(), {'claude': 'done', 'codex': 'login', 'antigravity': 'install'})
            self.ai.signed_in = lambda key, exe: None                      # it did not answer within 30 seconds
            self.assertEqual(self.ai.states()['claude'], 'unknown')
        finally:
            self.ai.find, self.ai.signed_in = saved_find, saved_signed

    def test_known_failures_name_the_chosen_ai(self):
        import auto_minutes
        self.ai.choose('codex')
        self.assertIn('Codex 還沒登入', auto_minutes.friendly('Error: not logged in', 'x'))
        self.assertIn('更新 Codex', auto_minutes.friendly("The 'gpt-5.5' model is not supported when using Codex "
                                                          'with a ChatGPT account.', 'x'))


class SetupCheck(unittest.TestCase):
    """環境設定自檢: each item says whether it is done, and what its button does."""

    def setUp(self):
        import google_setup
        import setup_check
        self.gs, self.sc = google_setup, setup_check
        self.home = Path(tempfile.mkdtemp(prefix='setup-'))
        self.saved = {n: getattr(google_setup, n) for n in ('CONFIG', 'CLIENT', 'TOKEN', 'SETTINGS')}
        self.saved_sc = {n: getattr(setup_check, n) for n in ('VOICE', 'RUNNING', 'FAILED')}
        google_setup.CONFIG, google_setup.CLIENT = self.home, self.home / 'oauth-client.json'
        google_setup.TOKEN, google_setup.SETTINGS = self.home / 'google-token.json', self.home / 'settings.json'
        setup_check.VOICE, setup_check.RUNNING = self.home / 'models' / 'campplus.onnx', self.home / 'setup-running.json'
        setup_check.FAILED = self.home / 'setup-failed.json'
        os.environ['HF_HUB_CACHE'] = str(self.home / 'hf')

    def tearDown(self):
        for n, v in self.saved.items():
            setattr(self.gs, n, v)
        for n, v in self.saved_sc.items():
            setattr(self.sc, n, v)
        os.environ.pop('HF_HUB_CACHE', None)
        shutil.rmtree(self.home, ignore_errors=True)

    def test_a_new_computer_has_everything_to_do_and_google_waits_for_its_key(self):
        st = self.sc.status(True)
        self.assertEqual((st['speech']['state'], st['voice']['state'], st['client']['state']), ('todo', 'todo', 'todo'))
        self.assertEqual({st[k]['state'] for k in ('login', 'docs', 'gmail', 'calendar')}, {'locked'})

    def test_downloaded_models_count_as_done(self):
        snap = self.sc.hub() / 'snapshots' / 'abc'
        snap.mkdir(parents=True)
        (snap / 'weights.safetensors').write_bytes(b'w')
        self.sc.VOICE.parent.mkdir(parents=True)
        self.sc.VOICE.write_bytes(b'0' * 2_000_000)
        st = self.sc.status(True)
        self.assertEqual((st['speech']['state'], st['voice']['state']), ('done', 'done'))

    def test_a_download_in_progress_shows_how_far_it_got(self):
        self.sc.VOICE.parent.mkdir(parents=True)
        self.sc.VOICE.with_suffix('.onnx.part').write_bytes(b'0' * (self.sc.VOICE_BYTES // 2))
        job = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', 'setup_check.py'])
        try:
            self.sc.RUNNING.write_text(json.dumps({'voice': job.pid}))          # a download that is running
            self.assertEqual(self.sc.voice(), {'state': 'loading', 'pct': 50})
            self.sc.RUNNING.write_text(json.dumps({'voice': os.getpid()}))      # a number another program has now
            self.assertEqual(self.sc.voice()['state'], 'todo')
        finally:
            job.kill()
        self.sc.FAILED.write_text(json.dumps({'voice': 'URLError: timed out'}))
        self.assertEqual(self.sc.voice(), {'state': 'todo', 'failed': True})

    def test_only_a_desktop_app_client_is_taken(self):
        f = self.home / 'client_secret_x.json'
        f.write_text(json.dumps({'web': {'client_id': 'a', 'client_secret': 'b'}}))
        with self.assertRaises(SystemExit) as caught:
            self.sc.take_client(f)
        self.assertIn('電腦版應用程式', str(caught.exception))
        f.write_text('not json')
        with self.assertRaises(SystemExit):
            self.sc.take_client(f)
        f.write_text(json.dumps({'installed': {'client_id': 'a', 'client_secret': 'b', 'project_id': 'p1',
                                               'token_uri': 'https://oauth2.googleapis.com/token'}}))
        self.sc.take_client(f)
        self.assertEqual(oct(self.gs.CLIENT.stat().st_mode & 0o777), '0o600')
        st = self.sc.status(True)
        self.assertEqual((st['client']['state'], st['login']['state'], st['project']), ('done', 'todo', 'p1'))

    def test_an_api_turned_off_in_the_cloud_project_gets_its_own_page_to_turn_it_on(self):
        self.sc.take_client(self._client())
        self.gs.TOKEN.write_text(json.dumps({'refresh_token': 'r', 'email': 'someone@example.com'}))
        saved = (self.gs.access_token, self.sc.probe)
        self.gs.access_token = lambda: 'T'
        self.sc.probe = lambda token, api: 'off' if api == 'gmail.googleapis.com' else 'ok'
        try:
            st = self.sc.status(False)
        finally:
            self.gs.access_token, self.sc.probe = saved
        self.assertEqual(st['login'], {'state': 'done', 'email': 'someone@example.com'})
        self.assertEqual((st['docs']['state'], st['calendar']['state']), ('done', 'done'))
        self.assertEqual(st['gmail'], {'state': 'off', 'url': 'https://console.cloud.google.com/apis/library/'
                                                              'gmail.googleapis.com?project=p1'})

    def _client(self) -> Path:
        f = self.home / 'c.json'
        f.write_text(json.dumps({'installed': {'client_id': 'a', 'client_secret': 'b', 'project_id': 'p1',
                                               'token_uri': 'https://oauth2.googleapis.com/token'}}))
        return f


class AiSetup(unittest.TestCase):
    """Item 5 of the checklist, step by step: pick the AI, Vinutes installs it, the user signs in, one short answer
    shows the account can write the minutes (the prototype Vin approved on 2026-10-19)."""

    def setUp(self):
        import ai_runner
        import google_setup
        import setup_check
        self.ai, self.gs, self.sc = ai_runner, google_setup, setup_check
        self.home = Path(tempfile.mkdtemp(prefix='aisetup-'))
        self.saved_gs = {n: getattr(google_setup, n) for n in ('CONFIG',)}
        self.saved_sc = {n: getattr(setup_check, n) for n in ('RUNNING', 'FAILED', 'TESTED', 'LOGIN_DONE')}
        self.saved_ai = {n: getattr(ai_runner, n) for n in ('find', 'account', 'download', 'run')}
        self.settings = google_setup.SETTINGS                   # the AI chosen is kept there (MINUTES_HOME)
        self.before = self.settings.read_text(encoding='utf-8') if self.settings.exists() else None
        google_setup.CONFIG = self.home
        setup_check.RUNNING, setup_check.FAILED = self.home / 'setup-running.json', self.home / 'setup-failed.json'
        setup_check.TESTED = self.home / 'setup-ai.json'
        setup_check.LOGIN_DONE = self.home / 'setup-ai-login-done'
        ai_runner.choose('claude')

    def tearDown(self):
        for n, v in self.saved_gs.items():
            setattr(self.gs, n, v)
        for n, v in self.saved_sc.items():
            setattr(self.sc, n, v)
        for n, v in self.saved_ai.items():
            setattr(self.ai, n, v)
        if self.before is None:
            self.settings.unlink(missing_ok=True)
        else:
            self.settings.write_text(self.before, encoding='utf-8')
        shutil.rmtree(self.home, ignore_errors=True)

    def test_each_ai_is_installed_from_its_makers_own_script_without_questions(self):
        self.assertEqual(self.ai.installer('claude')[:2], ('https://claude.ai/install.sh', 'bash'))
        url, shell, extra = self.ai.installer('codex')
        self.assertEqual((url, shell), ('https://chatgpt.com/codex/install.sh', 'sh'))
        self.assertEqual(extra, {'CODEX_NON_INTERACTIVE': '1'})        # it would otherwise ask to start Codex
        self.assertEqual(self.ai.installer('antigravity')[:2], ('https://antigravity.google/cli/install.sh', 'bash'))

    def _script(self, body: str):
        self.ai.download = lambda url, dest: Path(dest).write_text('#!/bin/sh\n' + body + '\n')

    def test_an_install_runs_the_downloaded_script_and_ends_with_the_command_found(self):
        marker = self.home / 'ran'
        self._script(f'echo done > "{marker}"')
        self.ai.find = lambda key=None: '/x/claude' if marker.exists() else None
        self.assertEqual(self.ai.install('claude'), '/x/claude')
        self.assertTrue(marker.exists())

    def test_an_install_that_fails_or_leaves_no_command_says_so(self):
        self._script('exit 3')
        self.ai.find = lambda key=None: None
        with self.assertRaises(SystemExit):
            self.ai.install('claude')
        self._script('exit 0')
        with self.assertRaises(SystemExit):
            self.ai.install('claude')

    def test_the_checklist_asks_about_the_sign_in_also_when_the_app_starts(self):
        self.ai.find = lambda key=None: '/x/claude' if (key or 'claude') == 'claude' else None
        self.ai.account = lambda key, exe: (False, '')
        self.assertEqual(self.sc.status(True)['ai']['state'], 'login')     # was 'done' as soon as it was installed
        self.ai.account = lambda key, exe: (True, 'someone@example.com')
        ai = self.sc.status(True)['ai']
        self.assertEqual((ai['state'], ai['email'], ai['installed']), ('done', 'someone@example.com', ['claude']))

    def test_an_install_in_progress_or_failed_shows_on_step_two_of_that_ai_only(self):
        self.ai.find = lambda key=None: None
        self.assertEqual(self.sc.ai(True)['state'], 'install')
        job = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', 'setup_check.py'])
        try:
            self.sc.RUNNING.write_text(json.dumps({'ai-claude': job.pid}))
            self.assertEqual(self.sc.ai(True)['state'], 'installing')
            self.assertEqual(self.sc.main_progress()['ai'], {'state': 'installing'})
            self.ai.choose('codex')                                   # Claude is still installing, not Codex
            self.assertEqual(self.sc.ai(True)['state'], 'install')
            self.assertEqual(self.sc.main_progress()['ai'], {'state': 'ended'})
        finally:
            job.kill()
            job.wait()
        self.sc.RUNNING.write_text('{}')
        self.sc.FAILED.write_text(json.dumps({'ai-claude': 'exit 3'}))
        self.assertNotIn('failed', {k for k, v in self.sc.ai(True).items() if v})   # Codex was never tried
        self.ai.choose('claude')
        self.assertEqual(self.sc.ai(True), {**self.sc.ai(True), 'state': 'install', 'failed': True})

    def test_the_short_answer_tells_a_working_account_from_a_used_up_or_signed_out_one(self):
        self.assertEqual(self.sc.test_result(0, 'OK'), 'done')
        self.assertEqual(self.sc.test_result(1, "You've hit your usage limit · resets 3pm"), 'quota')
        self.assertEqual(self.sc.test_result(1, 'Error: not logged in. Please run /login'), 'login')
        self.assertEqual(self.sc.test_result(1, 'Your subscription does not include Claude Code'), 'plan')
        self.assertEqual(self.sc.test_result(1, 'something else went wrong'), 'error')
        self.assertEqual(self.sc.test_result(0, ''), 'error')                  # it said nothing back
        self.assertEqual(self.sc.test_result(0, 'OK\nwarning: rate limit headers missing'), 'done')   # it answered

    def test_a_passed_test_is_kept_for_that_ai_only(self):
        self.ai.find = lambda key=None: f'/x/{key or "claude"}'
        self.ai.account = lambda key, exe: (True, '')
        self.ai.run = lambda prompt, folder, **kw: subprocess.CompletedProcess([], 0, 'OK', '')
        self.assertEqual(self.sc.ai_test(), {'test': 'done', 'ai': 'claude'})
        self.assertTrue(self.sc.ai(True)['tested'])
        self.ai.choose('codex')
        self.assertFalse(self.sc.ai(True)['tested'])
        self.ai.run = lambda prompt, folder, **kw: subprocess.CompletedProcess([], 1, '', 'usage limit reached')
        self.assertEqual(self.sc.ai_test()['test'], 'quota')
        self.assertFalse(self.sc.ai(True)['tested'])

    def test_an_account_whose_plan_cannot_write_keeps_item_five_open(self):
        self.ai.find = lambda key=None: '/x/claude'
        self.ai.account = lambda key, exe: (True, 'free@example.com')
        self.ai.run = lambda prompt, folder, **kw: subprocess.CompletedProcess(
            [], 1, '', 'Your subscription does not include Claude Code')
        self.assertEqual(self.sc.ai_test()['test'], 'plan')
        self.assertEqual(self.sc.ai(True)['state'], 'plan')          # not ✓ just because it is signed in
        self.ai.account = lambda key, exe: (True, 'paid@example.com')
        self.assertEqual(self.sc.ai(True)['state'], 'done')          # another account: it is asked again
        self.ai.run = lambda prompt, folder, **kw: subprocess.CompletedProcess([], 0, 'OK', '')
        self.ai.account = lambda key, exe: (True, 'free@example.com')
        self.assertEqual(self.sc.ai_test()['test'], 'done')          # the same account after an upgrade
        self.assertEqual(self.sc.ai(True)['state'], 'done')

    def test_an_ai_that_was_signed_in_before_says_its_sign_in_ran_out(self):
        self.ai.find = lambda key=None: '/x/claude'
        self.ai.account = lambda key, exe: (False, '')
        self.assertFalse(self.sc.ai(True)['was_signed'])              # a first sign-in: the steps
        self.ai.account = lambda key, exe: (True, 'someone@example.com')
        self.sc.ai(True)
        self.ai.account = lambda key, exe: (False, '')
        ai = self.sc.ai(True)
        self.assertEqual((ai['state'], ai['was_signed']), ('login', True))   # 登入失效, 重新登入

    def test_the_sign_in_window_leaves_a_mark_when_it_ends(self):
        self.ai.find = lambda key=None: '/x/claude'
        self.ai.account = lambda key, exe: (True, '')
        self.assertEqual(self.sc.ai(True)['login_at'], 0)
        self.sc.LOGIN_DONE.write_text('')
        self.assertGreater(self.sc.ai(True)['login_at'], 1_700_000_000_000)    # milliseconds, like Date.now()


class ListCorner(Flows):
    """The list's two buttons per meeting and the version in its corner."""

    def test_the_list_says_which_meetings_have_a_recording_and_a_transcript(self):
        row = minutes_app.summary(self.job())
        self.assertEqual((row['has_audio'], row['has_transcript']), (False, False))
        (self.job_dir / '錄音.m4a').write_bytes(b'0')
        (self.job_dir / '逐字稿.txt').write_text('[00:01] 大家好', encoding='utf-8')
        row = minutes_app.summary(self.job())
        self.assertEqual((row['has_audio'], row['has_transcript']), (True, True))

    def test_version_update_shows_only_for_a_newer_one_and_github_is_asked_once_an_hour(self):
        import check_update
        saved = check_update.fetch
        asked = []
        check_update.fetch = lambda name: asked.append(name) or 'version: "1.2.0"\n'
        minutes_app.APP_UPDATE.unlink(missing_ok=True)
        try:
            minutes_app.cmd_version('1.1.9')
            minutes_app.cmd_version('1.2.0')
            minutes_app.cmd_version('1.10.0')
        finally:
            check_update.fetch = saved
            minutes_app.APP_UPDATE.unlink(missing_ok=True)
        self.assertEqual([o['update'] for o in self.outs], [True, False, False])   # 1.10 is newer than 1.2
        self.assertEqual(self.outs[0]['newest'], '1.2.0')
        self.assertEqual(len(asked), 1)

    def test_a_version_released_the_same_day_is_seen_within_the_hour(self):
        # Vin 2026-10-19: three versions went out in one evening and the corner still showed none (asked once a day)
        import check_update
        saved = check_update.fetch
        check_update.fetch = lambda name: 'version: "1.3.0"\n'
        def looked_up(ago):
            minutes_app.APP_UPDATE.write_text(json.dumps({'checked_at': datetime.now().timestamp() - ago,
                                                          'newest': '1.2.0'}), encoding='utf-8')
            minutes_app.cmd_version('1.2.0')
            return self.outs[-1]['newest']
        try:
            # the window asks every 3600 seconds and the last look-up was stamped after its download: just under an
            # hour ago still counts as an hour
            self.assertEqual(looked_up(3590), '1.3.0')
            self.assertEqual(looked_up(30 * 60), '1.2.0')              # half an hour ago: GitHub is not asked again
        finally:
            check_update.fetch = saved
            minutes_app.APP_UPDATE.unlink(missing_ok=True)

    def test_offline_the_corner_shows_the_version_without_the_button(self):
        import check_update
        saved = check_update.fetch

        def offline(name):
            raise OSError('no network')
        check_update.fetch = offline
        minutes_app.APP_UPDATE.unlink(missing_ok=True)
        try:
            minutes_app.cmd_version('1.0.0')
        finally:
            check_update.fetch = saved
        self.assertEqual(self.outs[-1], {'version': '1.0.0', 'newest': '', 'update': False})


class ArchiveDelete(Flows):
    """封存 hides a meeting from the list and brings it back; 刪除 sends its Doc and Drive folder to Google's trash
    and names the files beside the minutes for the app to move to the Mac's Trash."""

    def setUp(self):
        super().setUp()
        self.saved_call = ds.call
        self.calls = []
        ds.call = lambda url, body=None, method=None: self.calls.append((url, body, method)) or {}

    def tearDown(self):
        ds.call = self.saved_call
        super().tearDown()

    def test_an_archived_meeting_is_marked_in_the_list_until_it_is_unarchived(self):
        self.assertFalse(minutes_app.summary(self.job())['archived'])
        minutes_app.cmd_archive(self.job(), True)
        self.assertTrue(minutes_app.summary(self.job())['archived'])
        minutes_app.cmd_archive(self.job(), False)
        self.assertFalse(minutes_app.summary(self.job())['archived'])

    def test_delete_trashes_the_doc_and_its_drive_folder_and_names_the_files_beside_the_minutes(self):
        job = self.job()
        job.state['attach_folder'] = 'F' * 20
        job.save_state()
        beside = [self.root / 'minutes.md.gdoc.json', self.root / 'minutes_逐字稿.txt',
                  self.root / 'minutes_沒存回的修改.md']
        for path in beside:
            path.write_text('x', encoding='utf-8')
        (self.root / 'minutes_附件').mkdir()                 # picture copies for the Word file
        (self.root / 'other.md').write_text('another meeting', encoding='utf-8')
        minutes_app.cmd_delete(self.job())
        trashed = [(url.split('?')[0], body, method) for url, body, method in self.calls]
        self.assertEqual(trashed, [(ds.DRIVE + 'F' * 20, {'trashed': True}, 'PATCH'),     # the Doc goes last
                                   (ds.DRIVE + 'D' * 30, {'trashed': True}, 'PATCH')])
        self.assertEqual(sorted(self.outs[-1]['trash']),
                         sorted(str(p) for p in [self.md_path, *beside, self.root / 'minutes_附件']))
        self.assertTrue(self.md_path.exists())           # the app moves them to the Trash, not this script

    def test_a_drive_folder_shared_by_a_series_stays_and_only_this_meetings_uploads_go(self):
        job = self.job()
        job.state.update(attach_folder='F' * 20, pictures=[{'id': 'P' * 20, 'name': 'a.png', 'width': 100}])
        job.save_state()
        (self.root / 'minutes.md.gdoc.json').write_text(json.dumps({'attach_files': ['A' * 20, 'P' * 20]}))
        other_dir = self.root / '20261007-103000'
        other_dir.mkdir()
        (other_dir / 'job.json').write_text('{}')
        (other_dir / '同步.json').write_text(json.dumps({'attach_folder': 'F' * 20}))
        saved = minutes_app.all_jobs
        minutes_app.all_jobs = lambda: [self.job(), minutes_app.Job(other_dir)]
        try:
            minutes_app.cmd_delete(self.job())
        finally:
            minutes_app.all_jobs = saved
        trashed = [url.split('?')[0].removeprefix(ds.DRIVE) for url, body, method in self.calls]
        self.assertEqual(trashed, ['A' * 20, 'P' * 20, 'D' * 30])

    def test_the_transcript_copy_is_found_beside_minutes_named_as_the_app_names_them(self):
        md = self.root / '20261014_1030_週會_會議紀錄.md'
        self.md_path.rename(md)
        result = json.loads((self.job_dir / 'result.json').read_text())
        result['minutes_md'] = str(md)
        (self.job_dir / 'result.json').write_text(json.dumps(result))
        (self.root / '20261014_1030_週會_逐字稿.txt').write_text('x', encoding='utf-8')
        (self.root / '20261014_1030_週會_會議紀錄_附件').mkdir()
        (self.root / '20261021_1030_週會_逐字稿.txt').write_text('next week', encoding='utf-8')
        minutes_app.cmd_delete(self.job())
        self.assertEqual(sorted(Path(p).name for p in self.outs[-1]['trash']),
                         ['20261014_1030_週會_會議紀錄.md', '20261014_1030_週會_會議紀錄_附件', '20261014_1030_週會_逐字稿.txt'])

    def test_a_meeting_still_being_written_up_is_not_archived(self):
        (self.job_dir / 'status.json').write_text(json.dumps({'step': 'transcribing'}))
        with self.assertRaises(SystemExit):
            minutes_app.cmd_archive(self.job(), True)
        self.assertFalse(self.job().archived)

    def test_previous_and_next_skip_archived_meetings(self):
        def meeting(stamp, archived=False):
            folder = self.root / stamp
            folder.mkdir()
            (folder / 'job.json').write_text(json.dumps({'started': f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T10:30:00+08:00'}))
            (folder / 'status.json').write_text(json.dumps({'step': 'done'}))
            (folder / 'result.json').write_text(json.dumps({'title': '週會', 'minutes_md': str(self.md_path)}))
            if archived:
                (folder / '封存.json').write_text('{}')
            return minutes_app.Job(folder)
        newer, older = meeting('20261021-103000', archived=True), meeting('20261007-103000')
        saved = minutes_app.all_jobs
        minutes_app.all_jobs = lambda: [newer, self.job(), older]
        try:
            around = minutes_app.neighbours(self.job())
        finally:
            minutes_app.all_jobs = saved
        self.assertEqual((around['prev'], around['next']), ('20261007-103000', ''))

    def test_a_doc_already_gone_from_drive_does_not_stop_the_delete(self):
        def gone(url, body=None, method=None):
            raise SystemExit('HTTP 404 from Google: File not found')
        ds.call = gone
        minutes_app.cmd_delete(self.job())
        self.assertIn(str(self.md_path), self.outs[-1]['trash'])

    def test_offline_nothing_is_deleted_and_the_window_says_so(self):
        def offline(url, body=None, method=None):
            raise SystemExit('OFFLINE: Google did not answer')
        ds.call = offline
        with self.assertRaises(SystemExit) as stop:
            minutes_app.cmd_delete(self.job())
        self.assertEqual(str(stop.exception), '沒有連上 Google，這場會議沒有刪除，請再試一次。')
        self.assertEqual(self.outs, [])

    def test_a_meeting_without_a_doc_asks_nothing_of_google(self):
        result = json.loads((self.job_dir / 'result.json').read_text())
        del result['doc_url']
        (self.job_dir / 'result.json').write_text(json.dumps(result))
        minutes_app.cmd_delete(self.job())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.outs[-1]['trash'], [str(self.md_path)])

    def test_a_meeting_still_being_written_up_is_not_deleted(self):
        (self.job_dir / 'status.json').write_text(json.dumps({'step': 'writing'}))
        with self.assertRaises(SystemExit):
            minutes_app.cmd_delete(self.job())
        self.assertEqual(self.calls, [])


class Voices(unittest.TestCase):
    """Who said each line: grouping alike voices, knowing named people, and naming a voice."""

    def setUp(self):
        import numpy as np
        import speakers
        self.np, self.sp = np, speakers
        rng = np.random.default_rng(7)
        # voices about as alike as three colleagues on one laptop microphone (cosine about 0.45 between people)
        common = self.unit(rng.normal(size=192))
        self.people = {n: self.unit(common + 1.1 * self.unit(rng.normal(size=192))) for n in ('vin', 'amy', 'ken')}
        # a meeting: vin talks most, amy some, ken a little; each line a noisy print of its speaker's voice
        self.who = ['vin'] * 30 + ['amy'] * 12 + ['ken'] * 6
        rng.shuffle(self.who)
        self.V = np.array([self.unit(self.people[w] + rng.normal(size=192) * 0.05) for w in self.who], dtype=np.float32)
        self.ok = np.ones(len(self.who), dtype=bool)
        self.spans = [(i * 6.0, i * 6.0 + 5.0) for i in range(len(self.who))]
        shutil.rmtree(speakers.VOICES, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(self.sp.VOICES, ignore_errors=True)

    def unit(self, v):
        return v / self.np.linalg.norm(v)

    def groups_by_person(self, result):
        by = {}
        for w, g in zip(self.who, result['lines']):
            by.setdefault(w, set()).add(g)
        return by

    def test_alike_voices_become_one_speaker_each_without_a_head_count(self):
        result = self.sp.label(self.V, self.ok, self.spans, {})
        by = self.groups_by_person(result)
        self.assertEqual(by, {'vin': {'A'}, 'amy': {'B'}, 'ken': {'C'}})       # letters follow how long each talked
        self.assertEqual([g['name'] for g in result['groups'].values()], ['', '', ''])

    def test_a_named_voice_is_known_at_the_next_meeting(self):
        np = self.np
        self.sp.remember('Amy', np.array([self.unit(self.people['amy'] + 0.3 * self.people['vin'])]), ['old:1'])
        result = self.sp.label(self.V, self.ok, self.spans, self.sp.library())
        named = {g: info['name'] for g, info in result['groups'].items()}
        amy = self.groups_by_person(result)['amy']
        self.assertEqual({named[g] for g in amy}, {'Amy'})
        self.assertEqual(sorted(n for n in named.values() if n), ['Amy'])     # the others stay 講者 X

    def test_a_named_persons_second_voice_joins_them(self):
        """Vin 2026-10-21: a two-person meeting listed seven speakers. 采瑤's short lines missed her kept prints and
        were grouped on their own as 講者 C (0.11 from her voice), so the minutes listed a third person."""
        np, rng = self.np, self.np.random.default_rng(3)
        away = self.unit(rng.normal(size=192))
        self.sp.remember('Amy', np.array([self.unit(self.people['amy'] + 1.0 * away)]), ['old:1'])   # last month's mic
        # amy's lines again, heard from the other side: too far from the kept print to be matched line by line,
        # alike enough to be grouped, and together 30 seconds, so they used to become a speaker of their own
        again = [self.unit(self.people['amy'] - 0.6 * away + 0.2 * self.unit(rng.normal(size=192))) for _ in range(6)]
        V = np.concatenate([self.V, np.array(again, dtype=np.float32)])
        ok = np.ones(len(V), dtype=bool)
        spans = self.spans + [(300 + i * 6.0, 305 + i * 6.0) for i in range(6)]
        result = self.sp.label(V, ok, spans, self.sp.library())
        amy = {result['lines'][i] for i, w in enumerate(self.who) if w == 'amy'}
        self.assertEqual(len(amy), 1)
        self.assertEqual({result['lines'][i] for i in range(len(self.who), len(V))}, amy)   # the same voice, not 講者 C
        self.assertEqual(result['groups'][amy.pop()]['name'], 'Amy')
        self.assertEqual(len(result['groups']), 3)

    def test_short_acknowledgements_do_not_make_a_speaker(self):
        """嗯, 對, 好: prints of lines under three seconds are noise. Fifteen of them, alike and 24 seconds
        together, used to be 講者 D; now they go to the nearest voice."""
        np, rng = self.np, self.np.random.default_rng(5)
        noise = self.unit(rng.normal(size=192))
        short = [self.unit(noise + 0.3 * self.unit(rng.normal(size=192))) for _ in range(15)]
        V = np.concatenate([self.V, np.array(short, dtype=np.float32)])
        ok = np.ones(len(V), dtype=bool)
        spans = self.spans + [(300 + i * 2.0, 301.6 + i * 2.0) for i in range(15)]
        result = self.sp.label(V, ok, spans, {})
        self.assertEqual(len(result['groups']), 3)
        self.assertEqual(self.groups_by_person(result), {'vin': {'A'}, 'amy': {'B'}, 'ken': {'C'}})

    def test_a_person_heard_only_in_short_lines_is_not_there(self):
        """A kept voice matched by three two-second lines (Ally, at the meeting of 2026-10-21, 7 seconds) is a
        mishearing, not a person at the meeting: those lines go to the nearest voice."""
        np, rng = self.np, self.np.random.default_rng(9)
        ally = self.unit(rng.normal(size=192))
        self.sp.remember('Ally', np.array([ally]), ['old:1'])
        brief = [self.unit(ally + 0.1 * self.unit(rng.normal(size=192))) for _ in range(3)]
        V = np.concatenate([self.V, np.array(brief, dtype=np.float32)])
        ok = np.ones(len(V), dtype=bool)
        spans = self.spans + [(300 + i * 3.0, 302 + i * 3.0) for i in range(3)]
        result = self.sp.label(V, ok, spans, self.sp.library())
        self.assertNotIn('Ally', [g['name'] for g in result['groups'].values()])
        self.assertEqual(len(result['groups']), 3)

    def test_a_known_person_who_speaks_in_short_sentences_is_still_there(self):
        """Review of v0.4.19: Amy, known, says fifteen things of 2.9 seconds each. Those are not noise; she is
        at the meeting and named, not folded into vin."""
        np, rng = self.np, self.np.random.default_rng(11)
        self.sp.remember('Amy', np.array([self.people['amy']]), ['old:1'])
        who = ['vin'] * 20 + ['amy'] * 15
        V = np.array([self.unit(self.people[w] + rng.normal(size=192) * 0.05) for w in who], dtype=np.float32)
        ok = np.ones(len(V), dtype=bool)
        spans = [(i * 6.0, i * 6.0 + (5.0 if w == 'vin' else 2.9)) for i, w in enumerate(who)]
        result = self.sp.label(V, ok, spans, self.sp.library())
        amy = {result['lines'][i] for i, w in enumerate(who) if w == 'amy'}
        self.assertEqual(len(amy), 1)
        self.assertEqual(result['groups'][amy.pop()]['name'], 'Amy')
        self.assertEqual(len(result['groups']), 2)

    def test_a_recording_of_short_sentences_only_still_has_a_speaker(self):
        """Forty lines of 2.5 seconds, one person, nobody known: 講者 A, not an empty result."""
        np, rng = self.np, self.np.random.default_rng(13)
        V = np.array([self.unit(self.people['vin'] + rng.normal(size=192) * 0.05) for _ in range(40)], dtype=np.float32)
        ok = np.ones(40, dtype=bool)
        spans = [(i * 3.0, i * 3.0 + 2.5) for i in range(40)]
        result = self.sp.label(V, ok, spans, {})
        self.assertEqual(list(result['groups']), ['A'])
        self.assertEqual(set(result['lines']), {'A'})

    def test_naming_a_voice_and_moving_one_line(self):
        job = Path(tempfile.mkdtemp(prefix='voices-'))
        lines = '\n'.join(f'[00:{i:02d}] 第 {i} 句' for i in range(len(self.who)))
        (job / '逐字稿.txt').write_text(lines + '\n', encoding='utf-8')
        (job / '逐字稿.json').write_text(json.dumps({'lines': self.spans}), encoding='utf-8')
        self.np.savez(job / '聲紋.npz', V=self.V, ok=self.ok)
        result = self.sp.label(self.V, self.ok, self.spans, {})
        (job / '講者.json').write_text(json.dumps(result), encoding='utf-8')
        try:
            self.sp.set_name(job, 'B', 'Amy')
            first_amy = self.who.index('amy')
            self.assertEqual(self.sp.name_of(self.sp.load(job), first_amy), 'Amy')
            kept = len(self.sp.library()['Amy'])
            self.assertEqual(kept, 12)
            self.sp.set_name(job, 'B', 'Amy')                                  # naming again does not pile up
            self.assertEqual(len(self.sp.library()['Amy']), 12)
            self.sp.set_name(job, 'C', 'Ken', line=first_amy)                 # one line was really someone else
            data = self.sp.load(job)
            self.assertEqual(self.sp.name_of(data, first_amy), 'Ken')
            self.assertEqual(len(self.sp.library()['Amy']), 11)               # and Amy no longer keeps that line
            text = self.sp.labelled_transcript(job).splitlines()
            self.assertEqual(text[first_amy], f'[00:{first_amy:02d}] Ken：第 {first_amy} 句')
        finally:
            shutil.rmtree(job, ignore_errors=True)

    def test_without_line_times_each_line_ends_where_the_next_starts(self):
        job = Path(tempfile.mkdtemp(prefix='voices-'))
        try:
            (job / '逐字稿.txt').write_text('[00:00] 開始\n[00:07] 第二句\n[1:00:02] 最後\n', encoding='utf-8')
            self.assertEqual(self.sp.lines_of(job), [(0, 7), (7, 3602), (3602, 3607)])
        finally:
            shutil.rmtree(job, ignore_errors=True)


class MailTurn(unittest.TestCase):
    """寄出 and the attachment previews take turns; only a mail really going out turns the next one away."""

    def setUp(self):
        import auto_minutes
        self.am = auto_minutes
        self.job = Path(tempfile.mkdtemp(prefix='mail-'))

    def tearDown(self):
        shutil.rmtree(self.job, ignore_errors=True)

    def hold(self, what):
        import fcntl
        lock = open(self.job / '.sending', 'a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (self.job / '.sending.who').write_text(what, encoding='utf-8')
        return lock

    def test_a_second_preview_waits_for_the_first_instead_of_saying_the_mail_is_going_out(self):
        import threading
        first = self.hold('preview')                     # the Word file is still being made
        threading.Timer(0.8, first.close).start()
        lock = self.am.mail_turn(self.job, 'preview')    # the user clicked PDF meanwhile
        self.assertEqual((self.job / '.sending.who').read_text(encoding='utf-8'), 'preview')
        lock.close()

    def test_send_waits_for_an_attachment_still_being_made(self):
        import threading
        first = self.hold('preview')
        threading.Timer(0.8, first.close).start()
        lock = self.am.mail_turn(self.job, 'send')
        self.assertEqual((self.job / '.sending.who').read_text(encoding='utf-8'), 'send')
        lock.close()

    def test_while_the_mail_goes_out_another_step_is_told_so(self):
        first = self.hold('send')
        try:
            with self.assertRaises(SystemExit) as stop:
                self.am.mail_turn(self.job, 'preview')
            self.assertIn('正在寄出', str(stop.exception))
        finally:
            first.close()


class FinishedMail(unittest.TestCase):
    """The mail goes out when the minutes are done: it never asks the recipients to fill the blanks."""

    def test_the_fill_the_blanks_paragraph_is_dropped(self):
        body = ('各位好，\n\n今天官網改版雙周會的會議紀錄整理好了：\nhttps://docs.google.com/document/d/X/edit\n\n'
                '紀錄裡標 [__] 的地方（與會人員）麻煩直接在文件上補，改完跟我說一聲即可。\n\nVin')
        self.assertEqual(minutes_app.finished_body(body),
                         '各位好，\n\n今天官網改版雙周會的會議紀錄整理好了：\nhttps://docs.google.com/document/d/X/edit\n\nVin')

    def test_a_body_without_blanks_stays_as_it_is(self):
        body = '各位好，\n\n紀錄整理好了。\n\nVin'
        self.assertEqual(minutes_app.finished_body(body), body)


class Languages(unittest.TestCase):
    """Vinutes speaks English or Traditional Chinese (i18n.py, strings.py); the minutes follow the meeting."""

    def setUp(self):
        os.environ['VINUTES_LANG'] = 'en'

    def tearDown(self):
        os.environ['VINUTES_LANG'] = 'zh-TW'

    def test_both_tables_have_the_same_keys_and_blanks(self):
        import string
        import strings
        self.assertEqual(set(strings.EN), set(strings.ZH))
        blanks = lambda text: {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}   # noqa: E731
        for key in strings.EN:
            self.assertEqual(blanks(strings.EN[key]), blanks(strings.ZH[key]), key)

    def test_dates_lengths_and_formats_in_english(self):
        when = datetime(2025, 10, 15, 14, 52)
        self.assertEqual(minutes_app.day_words(when), 'Wed, Oct 15, 2025')
        this_year = datetime(minutes_app.now().year, 3, 2)
        day = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[this_year.weekday()]
        self.assertEqual(minutes_app.day_words(this_year), f'{day}, Mar 2')
        self.assertEqual(minutes_app.short_time('2026-10-15T14:52:00+08:00')[:6], 'Oct 15')
        self.assertEqual(minutes_app.length_words(70), '1 h 10 min')
        self.assertEqual(minutes_app.length_words(120), '2 h')
        self.assertEqual(minutes_app.length_words(0), '1 min')
        self.assertEqual(minutes_app.format_words('word'), 'Word file')
        self.assertEqual(minutes_app.format_words('pdf'), 'PDF file')
        self.assertEqual(minutes_app.format_words(None), 'Google Docs link')

    def test_the_same_words_stay_chinese_in_chinese(self):
        os.environ['VINUTES_LANG'] = 'zh-TW'
        self.assertEqual(minutes_app.day_words(datetime(2025, 10, 15)), '2025/10/15（三）')
        self.assertEqual(minutes_app.length_words(70), '1 小時 10 分鐘')
        self.assertEqual(minutes_app.format_words(None), 'Google 文件連結')

    def test_a_message_the_window_shows_is_in_english(self):
        with self.assertRaises(SystemExit) as stop:
            minutes_app.Job(Path(HOME) / 'no-such-recording')
        self.assertEqual(str(stop.exception), "Can't find this recording.")

    def test_an_unnamed_voice_is_speaker_a(self):
        job_dir = Path(tempfile.mkdtemp(prefix='voices-'))
        try:
            (job_dir / 'job.json').write_text('{}')
            (job_dir / '講者.json').write_text(json.dumps({
                'groups': {'A': {'name': '', 'seconds': 120, 'sample': [1, 4]},
                           'B': {'name': 'Amy', 'seconds': 60, 'sample': [9, 12]}},
                'lines': ['A', 'B'], 'fixed': {}}), encoding='utf-8')
            job = minutes_app.Job(job_dir)
            self.assertEqual([v['label'] for v in minutes_app.voices_view(job)], ['Speaker A', 'Amy'])
            os.environ['VINUTES_LANG'] = 'zh-TW'
            self.assertEqual([v['label'] for v in minutes_app.voices_view(job)], ['講者 A', 'Amy'])
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    def test_minutes_follow_the_meeting_and_other_languages_the_app(self):
        import i18n
        self.assertEqual(i18n.norm('zh_Hant_TW'), 'zh-TW')
        self.assertEqual(i18n.norm('en-US'), 'en')
        self.assertEqual(i18n.norm('ja'), '')
        self.assertEqual(i18n.minutes_lang('zh'), 'zh-TW')
        self.assertEqual(i18n.minutes_lang('yue'), 'zh-TW')
        self.assertEqual(i18n.minutes_lang('en'), 'en')
        self.assertEqual(i18n.minutes_lang('ja'), 'en')
        os.environ['VINUTES_LANG'] = 'zh-TW'
        self.assertEqual(i18n.minutes_lang('ja'), 'zh-TW')
        self.assertEqual(i18n.minutes_lang('en'), 'en')

    def test_english_minutes_get_the_attachments_section(self):
        import attachments as at
        md = '# Weekly\n\n## 1. Basic Information\n\n- Date: Oct 14\n\n## 2. Discussion Summary\n\nBudget set.\n'
        lines = at.lines_for([{'kind': 'link', 'name': 'Slides', 'link': 'https://example.com/slides'}],
                             'Deck from Amy', 'en')
        self.assertEqual(lines, ['- Deck from Amy: [Slides](https://example.com/slides)'])
        out = at.add_lines(md, lines)
        self.assertIn('## 7. Attachments\n\n- Deck from Amy: [Slides](https://example.com/slides)', out)
        self.assertNotIn('參考附件', out)
        self.assertIn('：[Slides]', at.lines_for([{'kind': 'link', 'name': 'Slides', 'link': 'https://e.com'}],
                                                'Amy 的簡報', 'zh-TW')[0])


class ProjectTags(Flows):
    """The list groups meetings by project (Claude names it, the user can change it) and tags (Claude suggests some,
    only the ones the user adds stay); what the user changes is kept in 分類.json, never in result.json."""

    def setUp(self):
        super().setUp()
        self.others = []
        self.saved_all = minutes_app.all_jobs
        minutes_app.all_jobs = lambda: [self.job(), *[minutes_app.Job(d) for d in self.others]]

    def tearDown(self):
        minutes_app.all_jobs = self.saved_all
        super().tearDown()

    def result(self, **more):
        result = json.loads((self.job_dir / 'result.json').read_text())
        result.update(more)
        (self.job_dir / 'result.json').write_text(json.dumps(result))

    def meeting(self, stamp, project, archived=False):
        folder = self.root / stamp
        folder.mkdir()
        (folder / 'job.json').write_text(json.dumps({'started': f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T10:30:00+08:00'}))
        (folder / 'status.json').write_text(json.dumps({'step': 'done'}))
        (folder / 'result.json').write_text(json.dumps({'title': '週會', 'project': project,
                                                        'minutes_md': str(self.md_path)}))
        if archived:
            (folder / '封存.json').write_text('{}')
        self.others.append(folder)
        return folder

    def test_the_project_claude_named_shows_until_the_user_moves_the_meeting(self):
        self.result(project='新品上市')
        self.assertEqual(minutes_app.summary(self.job())['project'], '新品上市')
        before = (self.job_dir / 'result.json').read_text()
        minutes_app.cmd_move(self.job(), '  悠遊卡 ')
        self.assertEqual(minutes_app.summary(self.job())['project'], '悠遊卡')
        self.assertEqual((self.job_dir / 'result.json').read_text(), before)    # the mail step may be rewriting it
        minutes_app.cmd_move(self.job(), '')
        self.assertEqual(minutes_app.summary(self.job())['project'], '')       # 未分類

    def test_a_project_name_is_one_line_of_at_most_30_characters(self):
        minutes_app.cmd_move(self.job(), '台北\n捷運   合作' + '案' * 40)
        name = minutes_app.summary(self.job())['project']
        self.assertTrue(name.startswith('台北 捷運 合作'))
        self.assertEqual(len(name), 30)

    def test_renaming_a_project_renames_it_on_every_meeting_archived_ones_too(self):
        self.result(project='新品上市')
        self.meeting('20261007-103000', '新品上市', archived=True)
        self.meeting('20261008-103000', '悠遊卡')
        minutes_app.cmd_rename_project('新品上市', '新品上市一期')
        projects = {j.id: minutes_app.summary(j)['project'] for j in minutes_app.all_jobs()}
        self.assertEqual(projects, {'20261014-103000': '新品上市一期', '20261007-103000': '新品上市一期',
                                    '20261008-103000': '悠遊卡'})
        self.assertEqual(self.outs[-1], {'project': '新品上市一期', 'count': 2})

    def test_renaming_to_a_name_already_in_use_puts_the_two_projects_together(self):
        self.result(project='新品上市專案')
        self.meeting('20261008-103000', '新品上市')
        minutes_app.cmd_rename_project('新品上市專案', '新品上市')
        self.assertEqual({minutes_app.summary(j)['project'] for j in minutes_app.all_jobs()}, {'新品上市'})

    def test_a_project_is_not_renamed_to_nothing(self):
        self.result(project='新品上市')
        with self.assertRaises(SystemExit):
            minutes_app.cmd_rename_project('新品上市', '   ')
        with self.assertRaises(SystemExit):
            minutes_app.cmd_rename_project('', '悠遊卡')               # 未分類 is not a project
        self.assertEqual(minutes_app.summary(self.job())['project'], '新品上市')

    def test_previous_and_next_follow_the_project_the_user_set(self):
        self.result(project='官網改版')
        older = self.meeting('20261007-103000', '新品上市')
        self.assertEqual(minutes_app.neighbours(self.job())['prev'], '')
        minutes_app.cmd_move(self.job(), '新品上市')
        self.assertEqual(minutes_app.neighbours(self.job())['prev'], older.name)

    def test_tags_are_trimmed_one_each_and_at_most_eight(self):
        minutes_app.cmd_tags(self.job(), json.dumps([' 對外 ', '對外', '', '月會', 'x' * 40, *map(str, range(10))]))
        tags = minutes_app.summary(self.job())['tags']
        self.assertEqual(tags[:3], ['對外', '月會', 'x' * 20])
        self.assertEqual(len(tags), 8)
        self.assertEqual(self.outs[-1]['tags'], tags)

    def test_claude_s_suggestions_show_until_added_and_one_removed_later_does_not_come_back(self):
        self.result(tag_suggestions=['對外', '月會'])
        self.assertEqual(minutes_app.summary(self.job())['suggested'], ['對外', '月會'])
        minutes_app.cmd_tags(self.job(), json.dumps(['對外']))
        self.assertEqual(minutes_app.summary(self.job())['suggested'], ['月會'])
        minutes_app.cmd_tags(self.job(), json.dumps([]))
        self.assertEqual(minutes_app.summary(self.job())['suggested'], ['月會'])

    def test_suggestions_are_gone_once_the_minutes_are_sent(self):
        self.result(tag_suggestions=['對外'], sent_at='2026-10-14T12:00:00')
        self.assertEqual(minutes_app.summary(self.job())['suggested'], [])

    def test_bad_tags_change_nothing(self):
        minutes_app.cmd_tags(self.job(), json.dumps(['對外']))
        with self.assertRaises(SystemExit):
            minutes_app.cmd_tags(self.job(), '{"not": "a list"}')
        self.assertEqual(minutes_app.summary(self.job())['tags'], ['對外'])

    def test_claude_s_next_minutes_see_the_names_the_user_chose(self):
        import auto_minutes
        self.result(project='新品上市專案')
        minutes_app.cmd_move(self.job(), '新品上市')
        minutes_app.cmd_tags(self.job(), json.dumps(['對外']))
        self.assertEqual(auto_minutes.sorted_as(self.job_dir, json.loads((self.job_dir / 'result.json').read_text())),
                         ('新品上市', ['對外']))

    def test_claude_s_result_keeps_up_to_three_short_tag_suggestions(self):
        import auto_minutes
        work = self.root / 'work'
        work.mkdir()
        (work / auto_minutes.DRAFT).write_text(MINUTES, encoding='utf-8')
        (work / 'result.json').write_text(json.dumps({'status': 'ok', 'title': '週會', 'project': '新品上市',
                                                      'tags': ['對外', ' 月會 ', '對外', 'y' * 30, '內部']}))
        saved = auto_minutes.minutes_path
        auto_minutes.minutes_path = lambda folder, meta, title, lang: self.md_path
        try:
            result = auto_minutes.check_result(work, {}, self.root)
        finally:
            auto_minutes.minutes_path = saved
        self.assertEqual(result['tag_suggestions'], ['對外', '月會', 'y' * 20])


class LearnPeople(unittest.TestCase):
    """What 人員 changes in the minutes (a voice named, a person added or taken off) is the app's own edit, not the
    user's wording: learning from the user's edits must not turn it into a rule (Vin 2026-10-20, issue 27)."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='learn-'))
        self.job_dir = self.root / '20261020-150000'
        self.job_dir.mkdir()
        self.md_path = self.root / 'minutes.md'
        for path in (self.md_path, self.job_dir / '同步基準.md', self.job_dir / '學習基準.md'):
            path.write_text(MINUTES, encoding='utf-8')
        (self.job_dir / 'job.json').write_text(json.dumps({'started': '2026-10-20T15:00:00+08:00'}))
        (self.job_dir / 'status.json').write_text(json.dumps({'step': 'done'}))
        (self.job_dir / 'result.json').write_text(json.dumps({'status': 'ok', 'title': '週會', 'minutes_md': str(self.md_path)}))
        self.saved_out, self.outs = minutes_app.out, []
        minutes_app.out = self.outs.append
        self.notes = minutes_app.CONFIG / 'notes.md'
        self.notes.unlink(missing_ok=True)

    def tearDown(self):
        minutes_app.out = self.saved_out
        self.notes.unlink(missing_ok=True)
        shutil.rmtree(self.root, ignore_errors=True)

    def job(self):
        return minutes_app.Job(self.job_dir)

    def test_adding_and_removing_people_teaches_nothing(self):
        minutes_app.cmd_people(self.job(), 'add', 'Adam')
        self.assertIn('與會人員：Amy、Ken、Adam', self.md_path.read_text(encoding='utf-8'))
        self.assertEqual(minutes_app.cmd_learn(self.job(), quiet=True, log=False), [])
        self.assertFalse(self.notes.is_file() and 'Adam' in self.notes.read_text(encoding='utf-8'))
        minutes_app.cmd_people(self.job(), 'remove', 'Ken')
        self.assertEqual(minutes_app.cmd_learn(self.job(), quiet=True, log=False), [])
        # the user's own edit right after is still learned
        md = self.md_path.read_text(encoding='utf-8').replace('活動預算確定為 10 萬元', '活動預算確定為十萬元')
        self.md_path.write_text(md, encoding='utf-8')
        learned = minutes_app.cmd_learn(self.job(), quiet=True, log=False)
        self.assertEqual(len(learned), 1)
        self.assertNotIn('Adam', json.dumps(learned, ensure_ascii=False))


class Departments(unittest.TestCase):
    """The people a room booking's note names start the meeting's people, and the department it names remembers
    the people the user confirmed, so the next meeting of that department starts with them
    (prototypes/department-people.html, Vin 2026-10-20)."""

    NOTE = {'title': '(ITRI-427會議室)數據課週會', 'series': '數據課週會', 'recurring': '', 'start': '2026-10-20T15:00:00+08:00',
            'guests': [], 'host': '高聖哲(Vin)', 'departments': ['數據經濟發展課'], 'participants': ['高聖哲(Vin)']}
    EMPTY = {'host': '', 'departments': [], 'roster': [], 'roster_from': '', 'learned': False}

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='dept-'))
        self.saved_out, self.saved_sender = minutes_app.out, minutes_app.sender_name
        self.outs = []
        minutes_app.out = self.outs.append
        minutes_app.sender_name = lambda: '高聖哲 Vin'            # the note's own spelling is kept, not this one
        for f in (minutes_app.DEPARTMENTS, minutes_app.PROJECT_PEOPLE):
            f.unlink(missing_ok=True)

    def tearDown(self):
        minutes_app.out, minutes_app.sender_name = self.saved_out, self.saved_sender
        minutes_app.DEPARTMENTS.unlink(missing_ok=True)
        shutil.rmtree(self.root, ignore_errors=True)

    def job(self, name, calendar, md=MINUTES):
        d = self.root / name
        d.mkdir()
        (d / 'minutes.md').write_text(md, encoding='utf-8')
        (d / 'job.json').write_text(json.dumps({'started': f'2026-{name[4:6]}-{name[6:8]}T15:00:00+08:00'}))
        (d / 'status.json').write_text(json.dumps({'step': 'done'}))
        (d / 'result.json').write_text(json.dumps({'status': 'ok', 'title': '數據課週會', 'minutes_md': str(d / 'minutes.md')}))
        (d / '行事曆.json').write_text(json.dumps(calendar, ensure_ascii=False), encoding='utf-8')
        return minutes_app.Job(d)

    def test_the_notes_host_and_participants_start_the_meetings_people(self):
        job = self.job('20261020-150000', {**self.NOTE, 'participants': ['高聖哲(Vin)', '許恩碩(Eric)']})
        self.assertEqual(minutes_app.invited(job), ['高聖哲(Vin)', '許恩碩(Eric)'])     # as the note spells them
        self.assertEqual(minutes_app.meeting_people(job), ['高聖哲(Vin)', '許恩碩(Eric)', 'Amy', 'Ken'])
        self.assertEqual(minutes_app.calendar_payload(job),
                         {**self.EMPTY, 'host': '高聖哲(Vin)', 'departments': ['數據經濟發展課']})

    def test_adding_a_person_remembers_the_department_but_the_ais_attendee_line_does_not(self):
        job = self.job('20261020-150000', self.NOTE)          # the minutes' 與會人員 line says Amy、Ken: not confirmed
        minutes_app.cmd_people(job, 'add', 'Adam')
        people, where = minutes_app.roster(['數據經濟發展課'])
        self.assertEqual(people, ['高聖哲(Vin)', 'Adam'])
        self.assertEqual(where, '2026-10-20 數據課週會')
        self.assertEqual(self.outs[-1]['calendar'],
                         {'host': '高聖哲(Vin)', 'departments': ['數據經濟發展課'], 'roster': people,
                          'roster_from': '2026-10-20 數據課週會', 'learned': True})

    def test_in_the_meeting_that_taught_the_roster_the_user_can_still_correct_it(self):
        job = self.job('20261020-150000', self.NOTE)
        minutes_app.cmd_people(job, 'add', 'Adan')                              # a typo
        minutes_app.cmd_people(job, 'remove', 'Adan')
        minutes_app.cmd_people(job, 'add', 'Adam')
        self.assertEqual(minutes_app.roster(['數據經濟發展課'])[0], ['高聖哲(Vin)', 'Adam'])
        later = self.job('20261027-150000', {**self.NOTE, 'start': '2026-10-27T15:00:00+08:00'},
                         md=MINUTES.replace('Amy、Ken', '[__]'))
        minutes_app.cmd_people(later, 'remove', 'Adam')                        # absent one week: the roster keeps him
        self.assertEqual(minutes_app.roster(['數據經濟發展課'])[0], ['高聖哲(Vin)', 'Adam'])
        minutes_app.cmd_people(later, 'add', '許恩碩(Eric)')                    # a later meeting adds, never takes off
        self.assertEqual(minutes_app.roster(['數據經濟發展課']), (['高聖哲(Vin)', 'Adam', '許恩碩(Eric)'], '2026-10-20 數據課週會'))
        minutes_app.cmd_people(later, 'remove', '許恩碩(Eric)')                 # and still cannot take off, even its own addition
        self.assertEqual(minutes_app.roster(['數據經濟發展課'])[0], ['高聖哲(Vin)', 'Adam', '許恩碩(Eric)'])

    def test_the_next_meeting_of_the_department_starts_with_the_roster(self):
        first = self.job('20261020-150000', self.NOTE)
        minutes_app.cmd_people(first, 'add', 'Adam')
        later = self.job('20261027-150000', {**self.NOTE, 'start': '2026-10-27T15:00:00+08:00'},
                         md=MINUTES.replace('Amy、Ken', '[__]'))
        self.assertEqual(minutes_app.meeting_people(later), ['高聖哲(Vin)', 'Adam'])
        self.assertEqual(minutes_app.calendar_payload(later),
                         {'host': '高聖哲(Vin)', 'departments': ['數據經濟發展課'], 'roster': ['高聖哲(Vin)', 'Adam'],
                          'roster_from': '2026-10-20 數據課週會', 'learned': False})
        # a participant the note names who is not in the roster is added, and nobody twice
        third = self.job('20261103-150000', {**self.NOTE, 'participants': ['高聖哲(Vin)', 'Adam', '許恩碩(Eric)']},
                         md=MINUTES.replace('Amy、Ken', '[__]'))
        self.assertEqual(minutes_app.meeting_people(third), ['高聖哲(Vin)', 'Adam', '許恩碩(Eric)'])
        # a meeting before the one that taught the roster does not get it
        earlier = self.job('20261013-150000', {**self.NOTE, 'start': '2026-10-13T15:00:00+08:00'},
                           md=MINUTES.replace('Amy、Ken', '[__]'))
        self.assertEqual(minutes_app.meeting_people(earlier), ['高聖哲(Vin)'])
        self.assertEqual(minutes_app.calendar_payload(earlier), {**self.EMPTY, 'host': '高聖哲(Vin)', 'departments': ['數據經濟發展課']})

    def test_a_description_the_ai_wrote_beside_a_name_is_not_part_of_the_name(self):
        line = '- 與會人員：Vin、Adam（負責 AI SEO，逐字稿標記為講者 B）、Eric、陳怡君（Jessie）、王小明 (Ming)\n'
        self.assertEqual(minutes_app.attendees(line), ['Vin', 'Adam', 'Eric', '陳怡君（Jessie）', '王小明 (Ming)'])
        self.assertEqual(minutes_app.attendees('- Attendees: Amy Chen (Marketing lead, Speaker C), Ken Lee\n'), ['Amy Chen', 'Ken Lee'])

    def test_a_meeting_without_a_department_writes_no_roster(self):
        job = self.job('20261020-150000', {**self.NOTE, 'departments': []})
        minutes_app.cmd_people(job, 'add', 'Adam')
        self.assertFalse(minutes_app.DEPARTMENTS.exists())
        self.assertEqual(self.outs[-1]['calendar'], {**self.EMPTY, 'host': '高聖哲(Vin)'})
        self.assertEqual(minutes_app.calendar_payload(self.job('20261021-150000', {})), self.EMPTY)
        self.assertEqual(minutes_app.roster(['數據經濟發展課']), ([], ''))


class Contacts(unittest.TestCase):
    """contacts.py: the addresses Vinutes knows (directory, calendar invitees, people mailed before), a name to an
    address, and the people offered while typing a recipient (prototypes/mail-recipients.html, Vin 2026-10-20)."""

    def setUp(self):
        import contacts
        self.c = contacts
        contacts.CONTACTS.unlink(missing_ok=True)
        contacts.learn('erichsu@example.com', '許恩碩 Eric', 'directory')
        contacts.learn('adam.wang@example.com', '王建安 Adam', 'directory')
        contacts.learn('phoebe@example.com', '林佩蓉 Phoebe', 'directory')
        contacts.learn('chen@partner.example.com', '陳小姐', 'mail')

    def tearDown(self):
        self.c.CONTACTS.unlink(missing_ok=True)

    def test_a_name_finds_its_address_whichever_part_of_the_name_is_used(self):
        self.assertEqual(self.c.address_of('Eric'), 'erichsu@example.com')
        self.assertEqual(self.c.address_of('許恩碩'), 'erichsu@example.com')
        self.assertEqual(self.c.address_of('許恩碩(Eric)'), 'erichsu@example.com')
        self.assertEqual(self.c.address_of('adam'), 'adam.wang@example.com')
        self.assertEqual(self.c.address_of('Ken'), '')                        # nobody of that name
        self.assertEqual(self.c.address_of('林'), '')                          # one character matches too many
        self.assertEqual(self.c.address_of('Amy（悠遊卡）'), '')               # an explanation beside a name is not an alias
        self.c.learn('amy@example.com', 'Amy Chen', 'directory')
        self.assertEqual(self.c.address_of('Amy（悠遊卡）'), '')               # still not the company's Amy
        self.assertEqual(self.c.address_of('Amy Chen'), 'amy@example.com')
        self.assertEqual(self.c.address_of('Amy'), 'amy@example.com')
        self.assertEqual(self.c.address_of('陳小姐（台灣 PASS）'), '')
        self.c.learn('eric.lee@example.com', 'Eric Lee', 'calendar')
        self.assertEqual(self.c.address_of('Eric'), '')                        # two Erics: the user picks

    def test_typing_offers_people_by_name_or_address_and_not_those_already_added(self):
        self.assertEqual([p['mail'] for p in self.c.suggest('ph')], ['phoebe@example.com'])
        self.assertEqual([p['mail'] for p in self.c.suggest('許')], ['erichsu@example.com'])
        self.assertEqual([p['mail'] for p in self.c.suggest('example.com', exclude=['phoebe@example.com'])],
                         ['adam.wang@example.com', 'chen@partner.example.com', 'erichsu@example.com'])
        self.assertEqual(self.c.suggest('陳')[0], {'name': '陳小姐', 'mail': 'chen@partner.example.com', 'src': 'mail'})
        self.assertEqual(self.c.suggest(''), [])

    def test_learning_again_keeps_the_directorys_name_and_a_mail_remembers_new_people(self):
        self.c.learn('erichsu@example.com', 'Eric Hsu the Great', 'calendar')     # longer, but the directory's name wins
        self.assertEqual(self.c.suggest('eric')[0]['name'], '許恩碩 Eric')
        self.assertEqual(self.c.suggest('eric')[0]['src'], 'directory')
        self.c.learn('new@example.com', '', 'mail')                            # an address without a name
        self.assertEqual(self.c.suggest('new')[0]['name'], 'new@example.com')
        self.c.learn_many([('guest@partner.example.com', '王小姐', 'mail'), ('bad address', 'x', 'mail')])
        self.assertIn({'name': '王小姐', 'mail': 'guest@partner.example.com', 'src': 'mail'}, self.c.suggest('王'))
        self.assertEqual(self.c.suggest('e')[0]['mail'], 'erichsu@example.com')   # a name part starting with it comes first


MINUTES_WITH_PURPOSE = MINUTES.replace('## 二、討論摘要', '## 二、會議目的\n\n確認 10 月社群活動的預算與 KOL 名單，作為下週對外報價的依據。\n\n## 三、討論摘要')


class MailDefaults(Flows):
    """What the mail sheet opens with: the meeting's people as recipients with their addresses, who has none, and
    a body with the meeting's purpose and highlights (prototypes/mail-recipients.html, Vin 2026-10-20)."""

    def setUp(self):
        super().setUp()
        import contacts
        self.c = contacts
        contacts.CONTACTS.unlink(missing_ok=True)
        self.saved_refresh = contacts.refresh_directory
        contacts.refresh_directory = lambda: None
        contacts.learn('ken@example.com', '李國豪 Ken', 'directory')
        (self.job_dir / '行事曆.json').write_text(json.dumps({
            'title': '週會', 'guests': [{'name': 'Amy Chen', 'email': 'amy@example.com', 'self': False},
                                      {'name': '', 'email': 'vincent@example.com', 'self': True}],
            'host': '', 'departments': [], 'participants': []}, ensure_ascii=False), encoding='utf-8')
        (self.job_dir / '信件內文.txt').write_text('Hi，\n\n週會的會議紀錄整理好了：\n{文件網址}\n\n內容有需要調整的地方再跟我說。\n\nVin\n', encoding='utf-8')
        self.saved_owner, self.saved_sender = minutes_app.owner, minutes_app.sender_name
        minutes_app.owner = lambda: 'vincent@example.com'
        minutes_app.sender_name = lambda: '高聖哲 Vin'
        result = json.loads((self.job_dir / 'result.json').read_text(encoding='utf-8'))
        result['mail'] = {'to': [], 'subject': '週會會議紀錄'}
        (self.job_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')

    def tearDown(self):
        self.c.refresh_directory = self.saved_refresh
        self.c.CONTACTS.unlink(missing_ok=True)
        minutes_app.owner, minutes_app.sender_name = self.saved_owner, self.saved_sender
        super().tearDown()

    def test_the_meetings_people_are_the_recipients_and_the_calendar_teaches_addresses(self):
        self.md_path.write_text(MINUTES_WITH_PURPOSE.replace('Amy、Ken', 'Vin、Amy、Ken'), encoding='utf-8')
        self.c.learn('vincent@example.com', 'Vincent Kao', 'directory')       # the directory's name for the user
        mail = minutes_app.mail_defaults(self.job())
        # the invitation's Amy Chen and the minutes' Amy are one address: one chip; the user, Vin in the minutes and
        # 高聖哲 Vin on the invitation, is one too, whatever the directory calls them
        self.assertEqual(mail['people'], [{'name': 'Amy Chen', 'mail': 'amy@example.com'}, {'name': '高聖哲 Vin', 'mail': 'vincent@example.com'},
                                          {'name': 'Ken', 'mail': 'ken@example.com'}])
        self.assertEqual(mail['missing'], [])
        self.assertEqual(mail['to'], ['amy@example.com', 'vincent@example.com', 'ken@example.com'])
        self.assertEqual(self.c.address_of('Amy Chen'), 'amy@example.com')     # learned from the invitation

    def test_a_person_without_an_address_or_with_two_is_listed_as_missing(self):
        self.c.learn('eric.lee@example.com', 'Eric Lee', 'directory')
        self.c.learn('erichsu@example.com', '許恩碩 Eric', 'directory')
        self.md_path.write_text(MINUTES.replace('Amy、Ken', 'Amy、Ken、陳小姐、Eric'), encoding='utf-8')
        mail = minutes_app.mail_defaults(self.job())
        self.assertEqual([p['name'] for p in mail['people']], ['Amy Chen', '高聖哲 Vin', 'Ken', '陳小姐', 'Eric'])
        self.assertEqual(mail['people'][3], {'name': '陳小姐', 'mail': ''})
        self.assertEqual(mail['missing'], ['陳小姐', 'Eric'])                 # two Erics: the user picks one
        self.assertNotIn('', mail['to'])

    def test_the_body_gets_the_purpose_and_the_highlights_after_the_link(self):
        self.md_path.write_text(MINUTES_WITH_PURPOSE, encoding='utf-8')
        body = minutes_app.mail_defaults(self.job())['body']
        self.assertNotIn('Ken', body.split('重點：')[1])                     # who does what stays in the minutes
        self.assertIn('{文件網址}\n\n會議目的：確認 10 月社群活動的預算與 KOL 名單，作為下週對外報價的依據。\n\n重點：\n'
                      '1. 預算 10 萬元。\n2. KOL 合作先找兩位試行。\n3. KOL 試行合作\n\n內容有需要調整的地方再跟我說。', body)   # the row whose owner is still [__] stays in the Doc
        again = minutes_app.with_summary(body, MINUTES_WITH_PURPOSE, 'zh-TW')
        self.assertEqual(again, body)                                          # not twice
        self.assertEqual(minutes_app.with_summary('Hi\n\n{文件網址}\n\nVin', '# x\n\n## 一、會議基本資訊\n\n- 主持人：Vin\n', 'zh-TW'),
                         'Hi\n\n{文件網址}\n\nVin')                               # nothing to take: unchanged

    def test_english_minutes_get_purpose_and_highlights(self):
        md = ('# Weekly\n\n## 1. Meeting Details\n\n- Host: Vin\n\n## 2. Purpose\n\nSettle the October budget.\n\n'
              '## 4. Agreements\n\n- Budget is 100k.\n  - detail that stays in the Doc\n- Two KOLs first.\n- Venue [__] to confirm.\n\n'
              '## 6. Action Items\n\n'
              '| No. | Action | Owner | Notes |\n|---|---|---|---|\n| 1 | Book the venue | Amy | by Friday |\n| 2 | 確認合約付款事項 | Ken | |\n')
        out = minutes_app.with_summary('Hi,\n\nThe minutes:\n{doc_url}\n\nVin', md, 'en')
        self.assertIn('{doc_url}\n\nPurpose: Settle the October budget.\n\nHighlights:\n1. Budget is 100k.\n2. Two KOLs first.\n'
                      '3. Book the venue\n4. 確認合約付款事項\n\nVin', out)      # the header row is not an item, nor a sub-point or a blank
        long = '## 二、會議目的\n\n' + '這是一句很長的話，' * 12 + '最後一句。\n'
        got = minutes_app.with_summary('Hi\n\n{文件網址}\n\nVin', long, 'zh-TW')
        self.assertLessEqual(len(got.split('會議目的：')[1].split('\n')[0]), 160)
        self.assertTrue(got.split('會議目的：')[1].split('\n')[0].endswith(('，', '。', '…')))
        self.assertEqual(minutes_app.with_summary('Hi\n\n會議目的: x\n\n{文件網址}', long, 'zh-TW'), 'Hi\n\n會議目的: x\n\n{文件網址}')

    AI_BODY = ('Hi，\n\n週會的會議紀錄整理好了：\n{文件網址}\n\n會議目的：AI 寫的目的。\n\n重點：\n- 預算 10 萬元（Nina）\n\n'
               '內容有需要調整的地方再跟我說。\n\nVin\n')

    def test_the_mail_ends_with_the_vinutes_that_sent_it_once(self):
        version = (minutes_app.ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        body = minutes_app.mail_defaults(self.job())['body']
        self.assertTrue(body.endswith(f'\n\nVin\n\nSent by Vinutes v{version}'))
        self.assertEqual(minutes_app.with_signature(body), body)

    def test_untouched_minutes_keep_the_summary_the_ai_wrote_with_them(self):
        self.md_path.write_text(MINUTES_WITH_PURPOSE, encoding='utf-8')
        (self.job_dir / minutes_app.scores.ORIGINAL).write_text(MINUTES_WITH_PURPOSE, encoding='utf-8')
        (self.job_dir / '信件內文.txt').write_text(self.AI_BODY, encoding='utf-8')
        mail = minutes_app.mail_defaults(self.job())
        self.assertTrue(mail['summary_fresh'])
        self.assertIn('會議目的：AI 寫的目的。\n\n重點：\n- 預算 10 萬元（Nina）', mail['body'])

    def test_edited_minutes_drop_the_ais_summary_and_take_the_minutes_until_the_ai_rewrites_it(self):
        (self.job_dir / minutes_app.scores.ORIGINAL).write_text(MINUTES_WITH_PURPOSE, encoding='utf-8')
        edited = MINUTES_WITH_PURPOSE.replace('預算 10 萬元', '預算 12 萬元')
        self.md_path.write_text(edited, encoding='utf-8')
        (self.job_dir / '信件內文.txt').write_text(self.AI_BODY, encoding='utf-8')
        mail = minutes_app.mail_defaults(self.job())
        self.assertFalse(mail['summary_fresh'])                                # the window asks for the AI's rewrite
        self.assertNotIn('Nina', mail['body'])
        self.assertNotIn('AI 寫的目的', mail['body'])
        self.assertIn('重點：\n1. 預算 12 萬元。', mail['body'])                   # meanwhile: the minutes' own lines
        asked = []
        saved = minutes_app.ai_summary
        minutes_app.ai_summary = lambda job, md: asked.append(md) or '會議目的：新的目的。\n\n重點：\n- 預算 12 萬元，下週定案'
        try:
            minutes_app.cmd_mail_summary(self.job())
            got = self.outs[-1]
            self.assertTrue(got['summary_fresh'])
            self.assertIn('{文件網址}\n\n會議目的：新的目的。\n\n重點：\n- 預算 12 萬元，下週定案\n\n內容有需要調整的地方再跟我說。', got['body'])
            self.assertEqual(got['body'].count('Sent by Vinutes'), 1)
            minutes_app.cmd_mail_summary(self.job())                             # the same minutes: kept, not asked again
            self.assertEqual(len(asked), 1)
            self.assertEqual(self.outs[-1]['body'], got['body'])
            self.md_path.write_text(edited.replace('12 萬', '15 萬'), encoding='utf-8')
            self.assertFalse(minutes_app.mail_defaults(self.job())['summary_fresh'])   # changed again: asked again
            minutes_app.ai_summary = lambda job, md: ''                          # the AI gave nothing
            minutes_app.cmd_mail_summary(self.job())
            self.assertFalse(self.outs[-1]['summary_fresh'])
            self.assertIn('1. 預算 15 萬元。', self.outs[-1]['body'])
        finally:
            minutes_app.ai_summary = saved

    def test_the_text_the_mail_sheet_wrote_is_kept_as_it_is(self):
        """A preview (Word, PDF) or a send that failed writes the sheet's text to 信件內文.txt: what the user typed
        there stays, even when the minutes changed since."""
        (self.job_dir / minutes_app.scores.ORIGINAL).write_text(MINUTES_WITH_PURPOSE, encoding='utf-8')
        self.md_path.write_text(MINUTES_WITH_PURPOSE.replace('預算 10 萬元', '預算 12 萬元'), encoding='utf-8')
        mine = 'Hi，\n\n詳細如附件。\n\n會議目的：我改過的目的。\n\n重點：\n1. 我手改的重點\n\nVin\n\nSent by Vinutes v0.4.22'
        (self.job_dir / '信件內文.txt').write_text(mine, encoding='utf-8')
        (self.job_dir / minutes_app.SHEET_TEXT).touch()
        self.assertEqual(minutes_app.mail_body(self.job()), (mine, True))

    def test_a_preview_of_the_text_as_given_does_not_keep_old_highlights(self):
        """Word picked once to see the file, nothing typed: after the minutes change, the mail follows them again,
        and the highlights go before the sign-off, not after it."""
        (self.job_dir / minutes_app.scores.ORIGINAL).write_text(MINUTES_WITH_PURPOSE, encoding='utf-8')
        self.md_path.write_text(MINUTES_WITH_PURPOSE, encoding='utf-8')
        (self.job_dir / '信件內文.txt').write_text(self.AI_BODY, encoding='utf-8')
        given = minutes_app.mail_body(self.job())[0]
        word = given.replace('週會的會議紀錄整理好了：\n{文件網址}', '週會的會議紀錄整理好了，詳細如附件。')
        (self.job_dir / '信件內文.txt').write_text(word, encoding='utf-8')                # what the preview wrote
        (self.job_dir / minutes_app.SHEET_TEXT).touch()
        self.assertEqual(minutes_app.mail_body(self.job()), (word, True))                  # nothing changed since
        self.md_path.write_text(MINUTES_WITH_PURPOSE.replace('預算 10 萬元', '預算 12 萬元'), encoding='utf-8')
        body, fresh = minutes_app.mail_body(self.job())
        self.assertFalse(fresh)
        self.assertNotIn('AI 寫的目的', body)
        self.assertTrue(body.endswith('重點：\n1. 預算 12 萬元。\n2. KOL 合作先找兩位試行。\n3. KOL 試行合作\n\n'
                                      'Vin\n\nSent by Vinutes v' + (minutes_app.ROOT / 'VERSION').read_text().strip()), body)

    def test_a_list_left_under_its_own_heading_goes_with_it(self):
        self.assertEqual(minutes_app.without_summary('Hi\n\n{文件網址}\n\n重點：\n\n- a\n- b\n\n會議目的：x\n\nVin'),
                         'Hi\n\n{文件網址}\n\nVin')

    def test_only_two_paragraphs_with_a_highlight_are_taken_from_the_ai(self):
        self.assertEqual(minutes_app.summary_of('會議目的：a\n\n重點：\n- b\n- c\n\n以上兩段可直接放進信裡，需要調整再告訴我。', 'zh-TW'),
                         '會議目的：a\n\n重點：\n- b\n- c')                     # what the AI says after them is not mailed
        self.assertEqual(minutes_app.summary_of('**會議目的**：a\n\n**重點**：\n\n1. b', 'zh-TW'), '會議目的：a\n\n重點：\n\n1. b')
        self.assertEqual(minutes_app.summary_of('會議目的：a\n\n重點：\n以下為重點：\n- b', 'zh-TW'), '')   # not a list right under it
        self.assertEqual(minutes_app.summary_of('好的，以下是：\n\n```\n會議目的：談預算。\n\n重點：\n- 預算 10 萬元（Amy）\n```\n', 'zh-TW'),
                         '會議目的：談預算。\n\n重點：\n- 預算 10 萬元（Amy）')
        self.assertEqual(minutes_app.summary_of('Purpose: budget.\n\nHighlights:\n1. Budget 100k (Amy)', 'en'),
                         'Purpose: budget.\n\nHighlights:\n1. Budget 100k (Amy)')
        self.assertEqual(minutes_app.summary_of('會議目的：談預算。', 'zh-TW'), '')              # no highlights
        self.assertEqual(minutes_app.summary_of('會議目的：談預算。\n\n重點：\n- 場地 [__]', 'zh-TW'), '')
        self.assertEqual(minutes_app.summary_of('', 'zh-TW'), '')


class CalendarPick(unittest.TestCase):
    """workspace.pick_meeting: which calendar event a recording was. Only events on the user's own calendar that
    they have not declined count as theirs; the company calendar's rooms are only offered as maybes."""

    def ev(self, title, start, end, primary=True, me='accepted', uid=None):
        day = '2026-10-07'
        event = {'summary': title, 'iCalUID': uid or title, 'start': {'dateTime': f'{day}T{start}:00+08:00'},
                 'end': {'dateTime': f'{day}T{end}:00+08:00'}, 'organizer': {'self': True}}
        if me:
            event['attendees'] = [{'email': 'vincent@example.com', 'self': True, 'responseStatus': me},
                                  {'email': 'amy@example.com', 'responseStatus': 'accepted'}]
        return {'ev': event, 'primary': primary, 'cal': 'vincent@example.com' if primary else '範例公司'}

    def pick(self, found, start='15:31', end='16:15', me=()):
        import workspace
        day = '2026-10-07'
        return workspace.pick_meeting(found, datetime.fromisoformat(f'{day}T{start}:00+08:00'),
                                      datetime.fromisoformat(f'{day}T{end}:00+08:00'), me=list(me))

    # an ERP room booking: nobody invited, the people written in the event's note instead
    NOTE = ('開始時間: 2026-10-07 15:00\n結束時間: 2026-10-07 16:00\n主持人: 高聖哲(Vin)\n參與部門: 數據經濟發展課\n'
            '會議連結: https://erp.example.com/meetingRoom/1\n參與人員: 高聖哲(Vin)')

    def booking(self, note, title='(ITRI-427會議室)數據課週會'):
        f = self.ev(title, '15:00', '16:00', primary=False, me=None)
        f['ev']['description'] = note
        return f

    def test_the_note_of_a_booking_is_read_whichever_wording_it_uses(self):
        import workspace
        self.assertEqual(workspace.describe({'description': self.NOTE}),
                         {'host': '高聖哲(Vin)', 'departments': ['數據經濟發展課'], 'participants': ['高聖哲(Vin)']})
        self.assertEqual(workspace.describe({'description': 'Host: Amy Chen\nDepartments: Data, Marketing\nAttendees: Amy Chen; Ken Lee'}),
                         {'host': 'Amy Chen', 'departments': ['Data', 'Marketing'], 'participants': ['Amy Chen', 'Ken Lee']})
        self.assertEqual(workspace.describe({'description': '與會人員：王小明、Amy\n主席：王小明\n與會部門：行銷部／數據部'}),
                         {'host': '王小明', 'departments': ['行銷部', '數據部'], 'participants': ['王小明', 'Amy']})
        empty = {'host': '', 'departments': [], 'participants': []}
        self.assertEqual(workspace.describe({'description': '參與人員:\n主持人：\n參與部門:  '}), empty)
        self.assertEqual(workspace.describe({}), empty)
        # a meeting link, an address, HTML list items: never a department or a person
        self.assertEqual(workspace.describe({'description': 'Teams: https://teams.microsoft.com/l/meetup-join/abc\n'
                                                            'Attendees: amy@example.com; Ken Lee\n參與部門: 數據課'}),
                         {'host': '', 'departments': ['數據課'], 'participants': ['Ken Lee']})
        self.assertEqual(workspace.describe({'description': '<ul><li>主持人: Amy</li><li>參與部門: 行銷部</li></ul>'}),
                         {'host': 'Amy', 'departments': ['行銷部'], 'participants': []})

    def test_the_users_name_is_matched_by_its_parts_not_inside_another_name(self):
        import workspace
        me = workspace.me_tokens('高聖哲 Vin')
        self.assertEqual(me, ['高聖哲', 'Vin'])
        self.assertTrue(workspace.names_me('高聖哲(Vin)', me))
        self.assertTrue(workspace.names_me('vin kao', me))
        self.assertFalse(workspace.names_me('Kevin Wu', me))
        self.assertFalse(workspace.names_me('', me))
        self.assertEqual(workspace.me_tokens('Vincent Kao'), ['Vincent', 'Kao'])
        self.assertEqual(workspace.me_tokens(''), [])

    def test_a_booking_whose_note_names_the_user_is_the_meeting(self):
        got = self.pick([self.booking(self.NOTE), self.booking('主持人: 王小明\n參與人員: 王小明、Amy', title='(會議室D)ISMS 專案會議')],
                        me=['高聖哲', 'Vin'])
        self.assertEqual(got['match']['ev']['summary'], '(ITRI-427會議室)數據課週會')
        self.assertEqual([o['ev']['summary'] for o in got['others']], ['(會議室D)ISMS 專案會議'])

    def test_a_booking_whose_note_names_only_others_stays_a_maybe(self):
        got = self.pick([self.booking('主持人: 王小明\n參與部門: 數據經濟發展課\n參與人員: 王小明、Amy')], me=['高聖哲', 'Vin'])
        self.assertIsNone(got['match'])
        self.assertEqual(len(got['others']), 1)
        got = self.pick([self.booking('主持人:\n參與人員:')], me=['高聖哲', 'Vin'])     # labels with nothing after them
        self.assertIsNone(got['match'])

    def test_the_note_lines_are_shown_for_the_agent(self):
        import io
        import contextlib
        import workspace
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            workspace.show(self.booking(self.NOTE)['ev'], '範例公司')
        lines = out.getvalue().splitlines()
        self.assertIn('   主持人: 高聖哲(Vin)', lines)
        self.assertIn('   參與部門: 數據經濟發展課', lines)
        self.assertIn('   參與人員: 高聖哲(Vin)', lines)
        self.assertIn('   連結: https://erp.example.com/meetingRoom/1', lines)

    def test_a_room_booking_the_user_is_not_on_is_never_the_meeting(self):
        got = self.pick([self.ev('(會議室A)FunTOUR月會', '15:30', '17:00', primary=False, me=None),
                         self.ev('(會議室B)好好玩網站討論', '14:00', '15:00')])
        self.assertIsNone(got['match'])
        self.assertEqual([o['ev']['summary'] for o in got['others']], ['(會議室A)FunTOUR月會'])

    def test_the_users_own_meeting_that_overlaps_most_wins(self):
        got = self.pick([self.ev('短會', '15:00', '15:40'), self.ev('新品上市討論', '15:30', '16:30'),
                         self.ev('(會議室A)FunTOUR月會', '15:30', '17:00', primary=False, me=None)])
        self.assertEqual(got['match']['ev']['summary'], '新品上市討論')

    def test_a_declined_meeting_does_not_count(self):
        got = self.pick([self.ev('新品上市討論', '15:30', '16:30', me='declined')])
        self.assertIsNone(got['match'])

    def test_the_same_event_on_two_calendars_counts_once_as_the_users(self):
        got = self.pick([self.ev('(會議室B)新品上市討論', '15:30', '16:30', primary=False, me=None, uid='x1'),
                         self.ev('(會議室B)新品上市討論', '15:30', '16:30', me='needsAction', uid='x1')])
        self.assertEqual(got['match']['ev']['summary'], '(會議室B)新品上市討論')
        self.assertEqual(got['others'], [])

    def test_a_meeting_that_ended_before_the_recording_is_listed_as_earlier_not_picked(self):
        got = self.pick([self.ev('(會議室B)好好玩網站討論', '14:00', '15:00')])
        self.assertIsNone(got['match'])
        self.assertEqual([e['ev']['summary'] for e in got['earlier']], ['(會議室B)好好玩網站討論'])

    def test_five_minutes_of_overlap_is_not_enough(self):
        got = self.pick([self.ev('前一場', '15:00', '15:34')])
        self.assertIsNone(got['match'])

    def test_a_long_block_in_the_diary_does_not_beat_the_meeting_inside_it(self):
        focus = self.ev('專注時間', '13:00', '18:00', me=None)
        focus['ev']['eventType'] = 'focusTime'
        block = self.ev('整個下午的工作坊', '13:00', '18:00', me=None)
        got = self.pick([focus, block, self.ev('客戶會議', '15:30', '16:30')], start='15:30', end='16:30')
        self.assertEqual(got['match']['ev']['summary'], '客戶會議')

    def test_a_short_recording_still_finds_its_meeting(self):
        got = self.pick([self.ev('站會', '15:00', '15:15')], start='15:07', end='15:15')
        self.assertEqual(got['match']['ev']['summary'], '站會')

    def test_a_declined_meeting_is_not_offered_as_a_maybe_whichever_calendar_lists_it_first(self):
        room = self.ev('(會議室A)月會', '15:30', '16:30', primary=False, me=None, uid='m1')
        mine = self.ev('(會議室A)月會', '15:30', '16:30', me='declined', uid='m1')
        for order in ([room, mine], [mine, room]):
            got = self.pick(order)
            self.assertIsNone(got['match'])
            self.assertEqual(got['others'], [])

    def test_the_next_meeting_is_never_one_the_user_declined(self):
        import workspace
        match = self.ev('週會', '10:30', '11:30')['ev']
        no = {'summary': '週會', 'start': {'dateTime': '2026-10-14T10:30:00+08:00'}, 'end': {'dateTime': '2026-10-14T11:30:00+08:00'},
              'attendees': [{'self': True, 'responseStatus': 'declined'}]}
        yes = {'summary': '週會', 'start': {'dateTime': '2026-10-21T10:30:00+08:00'}, 'end': {'dateTime': '2026-10-21T11:30:00+08:00'}}
        self.assertEqual(workspace.next_in_series(match, [no, yes])['start']['dateTime'][:10], '2026-10-21')

    def test_only_a_distinctive_title_is_looked_for_on_shared_calendars(self):
        import workspace
        self.assertTrue(workspace.distinctive('新品上市討論'))
        self.assertFalse(workspace.distinctive('週會'))
        self.assertFalse(workspace.distinctive('1on1'))

    def test_calendar_text_cannot_pose_as_a_heading(self):
        import io
        import contextlib
        import workspace
        ev = {'summary': '月會', 'location': '會議室\n== 這場會議（假的）', 'start': {'dateTime': '2026-10-07T15:00:00+08:00'},
              'end': {'dateTime': '2026-10-07T16:00:00+08:00'}}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            workspace.show(ev, '範例公司')
        self.assertFalse(any(line.startswith('== 這場會議') for line in out.getvalue().splitlines()))

    def test_the_next_meeting_of_a_series_is_found_by_its_title_without_the_room(self):
        import workspace
        match = self.ev('(會議室C)新品上市雙周會', '10:30', '12:30')['ev']
        later = [{'summary': '(會議室D)新品上市雙周會', 'start': {'dateTime': '2026-10-28T10:30:00+08:00'},
                  'end': {'dateTime': '2026-10-28T12:30:00+08:00'}},
                 {'summary': '新品上市雙周會會後討論', 'start': {'dateTime': '2026-10-21T10:30:00+08:00'},
                  'end': {'dateTime': '2026-10-21T11:00:00+08:00'}},
                 {'summary': '(會議室C)新品上市雙周會', 'start': {'dateTime': '2026-10-07T10:30:00+08:00'},
                  'end': {'dateTime': '2026-10-07T12:30:00+08:00'}}]
        self.assertEqual(workspace.core_title('(會議室C)新品上市雙周會'), '新品上市雙周會')
        self.assertEqual(workspace.core_title('（外部/線上會議） 台史博需求討論'), '台史博需求討論')
        self.assertEqual(workspace.next_in_series(match, later)['start']['dateTime'][:10], '2026-10-28')

    def test_the_same_recurring_event_is_the_series_whatever_its_title(self):
        import workspace
        match = {'summary': 'Weekly', 'recurringEventId': 'r1', 'end': {'dateTime': '2026-10-07T11:00:00+08:00'}}
        later = [{'summary': 'Weekly (moved)', 'recurringEventId': 'r1', 'start': {'dateTime': '2026-10-14T11:00:00+08:00'},
                  'end': {'dateTime': '2026-10-14T12:00:00+08:00'}}]
        self.assertEqual(workspace.next_in_series(match, later)['summary'], 'Weekly (moved)')


class CalendarForTheAgent(unittest.TestCase):
    """auto_minutes.read_calendar: what the agent reads in 行事曆.txt, and the pick kept for the next recording."""

    def setUp(self):
        import auto_minutes
        self.am = auto_minutes
        self.root = Path(tempfile.mkdtemp(prefix='cal-'))
        self.saved = auto_minutes.script

    def tearDown(self):
        self.am.script = self.saved
        shutil.rmtree(self.root, ignore_errors=True)

    def answer(self, out, code=0):
        self.am.script = lambda *a, **k: subprocess.CompletedProcess(a, code, out, 'HTTP 401' if code else '')

    def test_the_pick_is_kept_and_earlier_meetings_of_the_series_are_listed(self):
        old = self.root / '20261001-103000'
        old.mkdir()
        (old / 'result.json').write_text(json.dumps({'status': 'ok', 'title': '新品上市雙周會', 'project': '新品上市'}))
        (old / '行事曆.json').write_text(json.dumps({'series': '新品上市雙周會'}))
        (old / '分類.json').write_text(json.dumps({'project': '新品上市一期'}, ensure_ascii=False))
        job = self.root / '20261014-103500'
        job.mkdir()
        self.answer('== 這場會議（…）\n== 10:30–12:30 (會議室C)新品上市雙周會  [範例公司]\n'
                    'MATCH {"title": "(會議室C)新品上市雙周會", "series": "新品上市雙周會", "recurring": "", "start": ""}\n')
        text = self.am.read_calendar(job, {'started': '2026-10-14T10:35:00+08:00', 'ended': '2026-10-14T12:20:00+08:00'})
        self.assertNotIn('MATCH', text)
        self.assertIn('2026-10-01 新品上市雙周會　專案：新品上市一期', text)    # the project the user chose
        self.assertEqual(json.loads((job / '行事曆.json').read_text())['series'], '新品上市雙周會')

    def test_a_recording_written_up_again_does_not_learn_from_later_meetings(self):
        later = self.root / '20261021-103000'
        later.mkdir()
        (later / 'result.json').write_text(json.dumps({'status': 'ok', 'title': '週會', 'project': '別的專案'}, ensure_ascii=False))
        (later / '行事曆.json').write_text(json.dumps({'series': '週會'}, ensure_ascii=False))
        job = self.root / '20261014-103500'
        job.mkdir()
        self.answer('== 這場會議\nMATCH {"title": "週會", "series": "週會", "recurring": "", "start": ""}\n')
        self.assertNotIn('別的專案', self.am.read_calendar(job, {'started': '2026-10-14T10:35:00+08:00'}))

    def test_a_recurring_event_is_matched_by_its_series_not_by_a_common_title(self):
        other = self.root / '20261007-103000'
        other.mkdir()
        (other / 'result.json').write_text(json.dumps({'status': 'ok', 'title': '週會', 'project': 'A 專案'}, ensure_ascii=False))
        (other / '行事曆.json').write_text(json.dumps({'series': '週會', 'recurring': 'rA'}))
        job = self.root / '20261014-103500'
        job.mkdir()
        self.answer('== 這場會議\nMATCH {"title": "週會", "series": "週會", "recurring": "rB", "start": ""}\n')
        self.assertNotIn('A 專案', self.am.read_calendar(job, {'started': '2026-10-14T10:35:00+08:00'}))

    def test_no_match_leaves_nothing_to_follow(self):
        job = self.root / '20261007-153111'
        job.mkdir()
        self.answer('== 這場會議：行事曆上沒有…\nMATCH {"title": "", "series": "", "recurring": "", "start": ""}\n')
        text = self.am.read_calendar(job, {'started': '2026-10-07T15:31:11+08:00', 'ended': ''})
        self.assertNotIn('同一系列之前', text)
        self.assertEqual(json.loads((job / '行事曆.json').read_text())['series'], '')

    def test_a_calendar_that_cannot_be_read_says_so(self):
        job = self.root / '20261007-153111'
        job.mkdir()
        self.answer('', code=1)
        self.assertTrue(self.am.read_calendar(job, {'started': '2026-10-07T15:31:11+08:00'}).startswith('（讀不到行事曆'))

    def test_the_roster_of_the_department_the_note_names_is_handed_to_the_agent(self):
        minutes_app.DEPARTMENTS.write_text(json.dumps({'數據經濟發展課': {'people': ['高聖哲(Vin)', 'Adam', 'Eric'],
                                                                     'from': '2026-10-13 數據課週會'}}, ensure_ascii=False))
        try:
            job = self.root / '20261020-150051'
            job.mkdir()
            self.answer('== 這場會議\nMATCH {"title": "(ITRI-427會議室)數據課週會", "series": "數據課週會", "recurring": "", "start": "",'
                        ' "host": "高聖哲(Vin)", "departments": ["數據經濟發展課"], "participants": ["高聖哲(Vin)"]}\n')
            text = self.am.read_calendar(job, {'started': '2026-10-20T15:00:51+08:00'})
            self.assertIn('== 參與部門之前確認過的名單', text)
            self.assertIn('數據經濟發展課：高聖哲(Vin)、Adam、Eric', text)
            self.assertIn('2026-10-13 數據課週會', text)
            self.assertEqual(json.loads((job / '行事曆.json').read_text())['departments'], ['數據經濟發展課'])
            other = self.root / '20261021-150051'
            other.mkdir()
            self.answer('== 這場會議\nMATCH {"title": "週會", "series": "週會", "recurring": "", "start": "", "departments": ["行銷部"]}\n')
            self.assertNotIn('參與部門之前確認過的名單', self.am.read_calendar(other, {'started': '2026-10-21T15:00:51+08:00'}))
        finally:
            minutes_app.DEPARTMENTS.unlink(missing_ok=True)


class ScriptLog(unittest.TestCase):
    """vlog: every script run is two lines in scripts.log, never the user's words, and the file stays bounded."""

    def setUp(self):
        import vlog
        self.vlog = vlog
        self.dir = Path(tempfile.mkdtemp(prefix='logs-'))
        os.environ['VINUTES_LOG_DIR'] = str(self.dir)
        self.argv = sys.argv
        sys.argv = ['/x/minutes_app.py', 'ask', '/r/recordings/20261017-153005', 'make Alex Wang the chair']

    def tearDown(self):
        sys.argv = self.argv
        os.environ['VINUTES_LOG_DIR'] = os.path.join(HOME, 'logs')
        shutil.rmtree(self.dir, ignore_errors=True)

    def text(self):
        return (self.dir / 'scripts.log').read_text(encoding='utf-8')

    def test_a_run_logs_its_command_and_meeting_but_not_what_the_user_typed(self):
        self.vlog.run(lambda: None)
        self.assertIn('minutes_app[', self.text())
        self.assertIn('start ask 20261017-153005', self.text())
        self.assertIn('end ok', self.text())
        self.assertNotIn('Alex Wang', self.text())

    def test_a_failure_logs_its_message_and_a_crash_its_traceback(self):
        with self.assertRaises(SystemExit):
            self.vlog.run(lambda: sys.exit('Google did not answer. Please try again.'))
        self.assertIn('end failed', self.text())
        self.assertIn('Google did not answer', self.text())

        def boom():
            raise ValueError('bad page')
        with self.assertRaises(ValueError):
            self.vlog.run(boom)
        self.assertIn('end crashed', self.text())
        self.assertIn('ValueError: bad page', self.text())

    def test_an_address_in_a_message_never_reaches_the_log(self):
        with self.assertRaises(SystemExit):
            self.vlog.run(lambda: sys.exit('STOP: give plain addresses only: Alex <alex.wang@example.com>'))
        self.assertNotIn('alex.wang@example.com', self.text())
        self.assertIn('<address>', self.text())

    def test_an_empty_message_does_not_break_the_script(self):
        with self.assertRaises(SystemExit) as stop:           # the script's own exit, not an IndexError from the log
            self.vlog.run(lambda: sys.exit(''))
        self.assertEqual(stop.exception.code, '')
        self.assertIn('end failed', self.text())

    def test_what_the_window_asks_every_few_seconds_is_logged_only_when_it_fails(self):
        sys.argv = ['/x/minutes_app.py', 'refresh', '/r/recordings/20261017-153005']
        self.vlog.run(lambda: None)
        self.assertFalse((self.dir / 'scripts.log').exists())
        with self.assertRaises(SystemExit):
            self.vlog.run(lambda: sys.exit('Google did not answer.'))
        self.assertIn('end failed', self.text())
        self.assertIn('refresh 20261017-153005', self.text())

    def test_the_log_turns_over_past_its_limit_and_keeps_one_older_file(self):
        saved = self.vlog.LIMIT
        self.vlog.LIMIT = 200
        try:
            for i in range(40):
                self.vlog.log(f'line {i}')
        finally:
            self.vlog.LIMIT = saved
        files = sorted(p.name for p in self.dir.iterdir())
        self.assertEqual(files, ['scripts.log', 'scripts.log.1'])
        self.assertLess((self.dir / 'scripts.log').stat().st_size, 400)
        self.assertIn('line 39', self.text())


class MeetingLanguage(unittest.TestCase):
    """transcribe.detect: which language the meeting was held in, by majority of three stretches."""

    def detect(self, *heard):
        import transcribe
        said = iter(heard)
        fake = lambda audio, **kw: {'text': 'words', 'language': next(said)}   # noqa: E731
        return transcribe.detect(range(10 * 60 * 16000), fake)

    def test_the_majority_wins(self):
        self.assertEqual(self.detect('en', 'zh', 'en'), 'en')

    def test_a_tie_goes_to_the_earliest(self):
        self.assertEqual(self.detect('zh', 'ja', 'ko'), 'zh')

    def test_cantonese_counts_as_chinese(self):
        self.assertEqual(self.detect('yue', 'en', 'zh'), 'zh')


class UsageLimit(unittest.TestCase):
    """An AI that has used up its limit says when it is back, in the app's language (auto_minutes.limit_until)."""
    NOW = datetime(2026, 10, 17, 22, 46)

    def tearDown(self):
        os.environ['VINUTES_LANG'] = 'zh-TW'

    def until(self, text, lang='zh-TW'):
        import auto_minutes
        os.environ['VINUTES_LANG'] = lang
        return auto_minutes.limit_until(text, self.NOW)

    def test_claude_weekly_limit_is_tomorrow_noon(self):
        self.assertEqual(self.until("You've hit your weekly limit · resets 12pm (Asia/Taipei)"), '明天中午 12 點')
        self.assertEqual(self.until("You've hit your weekly limit · resets 12pm (Asia/Taipei)", 'en'), 'tomorrow at 12 pm')

    def test_a_later_hour_today_and_minutes(self):
        self.assertEqual(self.until("You've hit your limit · resets 11:30pm"), '今天晚上 11 點 30 分')

    def test_a_date_and_the_small_hours(self):
        self.assertEqual(self.until("You've hit your weekly limit · resets Oct 20, 9am"), '10/20 上午 9 點')
        self.assertEqual(self.until("You've hit your usage limit · resets 3am"), '明天凌晨 3 點')

    def test_other_wordings(self):
        self.assertEqual(self.until('5-hour limit reached ∙ resets 2am'), '明天凌晨 2 點')
        self.assertEqual(self.until('Your limit will reset at 5pm'), '明天下午 5 點')
        self.assertEqual(self.until("You've hit your weekly limit · resets Feb 29, 9am"), '')   # 2026 has no Feb 29

    def test_no_time_no_words(self):
        self.assertEqual(self.until('Claude AI usage limit reached'), '')
        self.assertEqual(self.until('something else went wrong'), '')

    def test_the_message_the_user_sees(self):
        import auto_minutes
        os.environ['VINUTES_LANG'] = 'zh-TW'
        said = auto_minutes.friendly("You've hit your weekly limit · resets 12pm (Asia/Taipei)", 'DEFAULT')
        self.assertIn('才會恢復，可以先換用其他 AI', said)
        self.assertNotEqual(auto_minutes.friendly('Claude AI usage limit reached', 'DEFAULT'), 'DEFAULT')


class People(unittest.TestCase):
    """人員: a guess about who a voice is goes with that voice; the names on the 與會人員 line are listed."""

    def test_a_guess_about_a_voice_keeps_the_voice_the_name_and_the_role(self):
        g = minutes_app.SPEAKER_GUESS.match('講者 B 負責文章，可能是 Nina')
        self.assertEqual((g.group(1), g.group(2).strip(' ，,、:：'), g.group(3)), ('B', '負責文章', 'Nina'))
        self.assertEqual(minutes_app.SPEAKER_GUESS.match('講者 A 推測是 Vin').group(3), 'Vin')
        self.assertEqual(minutes_app.SPEAKER_GUESS.match('Speaker C is probably Ming.').group(3), 'Ming')

    def test_no_single_name_no_person(self):
        for text in ('講者 B 與講者 C 可能是同一人', '講者 B 可能是 Nina 或 Mia', '講者 A 可能是主持人'):
            g = minutes_app.SPEAKER_GUESS.match(text)
            self.assertTrue(g is None or minutes_app.NOT_A_NAME.search(g.group(3)), text)
        self.assertIsNone(minutes_app.SPEAKER_GUESS.match('Speakers A and B are probably Ming'))

    def test_a_guess_about_a_word_is_no_person(self):
        self.assertIsNone(minutes_app.SPEAKER_GUESS.match('「HOWAN PASS」推測是台灣 PASS'))
        self.assertIsNone(minutes_app.SPEAKER_GUESS.match('第四項產品聽不出（方圖）'))

    def test_the_attendees_line_without_blanks(self):
        self.assertEqual(minutes_app.attendees('* 主持人：Vin\n* 與會人員：Vin、Mia、雅婷\n'), ['Vin', 'Mia', '雅婷'])
        self.assertEqual(minutes_app.attendees('* 與會人員：Vin、[請補姓名]'), ['Vin'])
        self.assertEqual(minutes_app.attendees('* Attendees: Jessie Chen, Ming Wang'), ['Jessie Chen', 'Ming Wang'])
        self.assertEqual(minutes_app.attendees('沒有這一行'), [])


class MeetingPeople(unittest.TestCase):
    """人員: a meeting's list starts from the invitation and the minutes; adding, naming a voice and taking someone off
    go into the minutes' 與會人員 line. Adding and naming also put the person in the project's list (its brief);
    taking someone off a meeting leaves the brief alone (Vin 2026-10-17, 10-19)."""

    job = Flows.job

    def setUp(self):
        Flows.setUp(self)
        (self.job_dir / '逐字稿.txt').write_text('', encoding='utf-8')
        self.md_path.write_text(MINUTES.replace('會中說明：', '講者 B 說明：'), encoding='utf-8')
        for name in ('同步基準.md', '學習基準.md'):
            (self.job_dir / name).write_text(self.md_path.read_text(encoding='utf-8'), encoding='utf-8')
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['project'] = '週會專案'
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        (self.job_dir / '行事曆.json').write_text(json.dumps({'guests': [
            {'name': '', 'email': 'leo@example.com', 'self': False},
            {'name': 'Amy', 'email': 'amy@example.com', 'self': False}]}))
        (self.job_dir / '講者.json').write_text(json.dumps({'groups': {
            'A': {'name': '', 'seconds': 300, 'sample': [1, 5]}, 'B': {'name': '', 'seconds': 200, 'sample': [9, 12]}},
            'lines': [], 'fixed': {}}, ensure_ascii=False))
        minutes_app.PROJECT_PEOPLE.unlink(missing_ok=True)
        ds.push = lambda doc_id, base, new: (ds.Plan([{'x': 1}], [], []), fake_doc(new), True)

    def tearDown(self):
        minutes_app.PROJECT_PEOPLE.unlink(missing_ok=True)
        Flows.tearDown(self)

    def test_the_list_starts_from_the_invitation_and_the_minutes(self):
        minutes_app.save_project_people('週會專案', ['Lily', 'amy'])
        self.assertEqual(minutes_app.meeting_people(self.job()), ['Leo', 'Amy', 'Ken'])   # 以當場會議邀請的人為主

    def test_with_no_invitation_the_minutes_say_who_was_there_not_the_project_list(self):
        (self.job_dir / '行事曆.json').write_text('{}')
        minutes_app.save_project_people('週會專案', ['Lily', 'amy'])
        self.assertEqual(minutes_app.meeting_people(self.job()), ['Amy', 'Ken'])   # Lily is the project's, not here

    def test_group_addresses_are_no_people(self):
        (self.job_dir / '行事曆.json').write_text(json.dumps({'guests': [{'email': 'rd-team@example.com'},
                                                                          {'email': 'room3@example.com'}]}))
        self.assertEqual(minutes_app.invited(self.job()), [])

    def test_the_attendees_line_stays_on_its_line(self):
        job = self.job()
        self.assertEqual(minutes_app.with_people(job, '* 與會人員：\n* 會議資料：[x](u)\n', ['Amy']),
                         '* 與會人員：Amy\n* 會議資料：[x](u)\n')
        self.assertEqual(minutes_app.with_people(job, '* **與會人員：** Vin\n', ['Vin', 'Amy']), '* **與會人員：** Vin、Amy\n')
        self.assertEqual(minutes_app.with_people(job, '**與會人員：Vin**\n', ['Vin', 'Amy']), '**與會人員：Vin、Amy**\n')
        self.assertEqual(minutes_app.with_people(job, '與會人員：Vin。\n', ['Vin', 'Amy']), '與會人員：Vin、Amy。\n')
        self.assertTrue(minutes_app.same_name('陳怡君（Jessie）', 'jessie'))

    def test_a_name_with_a_nickname_inside_the_nickname_is_the_same_person(self):
        # the company's calendar writes 高聖哲(Vin(Vincent)); the voice Vinutes knows is Vin (2026-10-21)
        self.assertTrue(minutes_app.same_name('高聖哲(Vin(Vincent))', 'Vin'))
        self.assertTrue(minutes_app.same_name('高聖哲(Vin(Vincent))', 'Vincent'))
        self.assertTrue(minutes_app.same_name('高聖哲(Vin(Vincent))', '高聖哲'))
        self.assertFalse(minutes_app.same_name('高聖哲(Vin(Vincent))', 'Vinnie'))

    def test_the_same_person_written_twice_on_the_list_is_listed_once(self):
        job = self.job()
        minutes_app.save_meeting_people(job, ['高聖哲(Vin(Vincent))', 'Amy', 'Vin'])
        self.assertEqual(minutes_app.meeting_people(job), ['高聖哲(Vin(Vincent))', 'Amy'])
        minutes_app.save_meeting_people(job, ['Vin', 'Amy', '高聖哲(Vin(Vincent))'])   # the fuller spelling stays
        self.assertEqual(minutes_app.meeting_people(job), ['高聖哲(Vin(Vincent))', 'Amy'])

    def test_naming_a_voice_by_a_nickname_of_an_invitee_does_not_list_the_invitee_as_silent(self):
        # the meeting of 2026-10-21: the calendar note said 高聖哲(Vin(Vincent)), the voice was named Vin
        (self.job_dir / '行事曆.json').write_text(json.dumps({'guests': [
            {'name': '高聖哲(Vin(Vincent))', 'email': 'vin@example.com', 'self': False},
            {'name': 'Amy', 'email': 'amy@example.com', 'self': False}]}, ensure_ascii=False))
        minutes_app.cmd_speaker(self.job(), 'B', 'Vin')
        self.assertEqual(minutes_app.meeting_people(self.job()), ['高聖哲(Vin(Vincent))', 'Amy', 'Ken'])
        self.assertEqual(minutes_app.silent_people(self.job()), ['Amy', 'Ken'])
        minutes_app.cmd_speaker(self.job(), 'B', '高聖哲')      # the same person by another of the spellings
        self.assertEqual(minutes_app.meeting_people(self.job()), ['高聖哲(Vin(Vincent))', 'Amy', 'Ken'])
        self.assertIn('與會人員：高聖哲(Vin(Vincent))、Amy、Ken', self.md_path.read_text(encoding='utf-8'))
        minutes_app.cmd_speaker(self.job(), 'B', 'Mia')          # someone else: the first name goes
        self.assertEqual(minutes_app.meeting_people(self.job()), ['Amy', 'Ken', 'Mia'])

    def test_renaming_a_named_voice_swaps_the_name_in_the_minutes(self):
        minutes_app.cmd_speaker(self.job(), 'B', 'Mia')
        minutes_app.cmd_speaker(self.job(), 'B', 'Nina')
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('Nina 說明：', md)
        self.assertIn('與會人員：Leo、Amy、Ken、Nina', md)

    def test_adding_someone_writes_the_attendees_line_and_the_project_list(self):
        minutes_app.cmd_people(self.job(), 'add', 'Sammi')
        self.assertIn('與會人員：Leo、Amy、Ken、Sammi', self.md_path.read_text(encoding='utf-8'))
        self.assertEqual(minutes_app.project_people('週會專案'), ['Sammi'])

    def test_naming_a_voice_replaces_its_letter_and_joins_the_list(self):
        minutes_app.cmd_speaker(self.job(), 'B', 'Mia')
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('Mia 說明：', md)
        self.assertNotIn('講者 B', md)
        self.assertIn('與會人員：Leo、Amy、Ken、Mia', md)
        self.assertEqual(minutes_app.project_people('週會專案'), ['Mia'])

    def test_taking_someone_off_a_meeting_frees_their_voice_and_keeps_them_in_the_brief(self):
        minutes_app.cmd_speaker(self.job(), 'B', 'Mia')
        minutes_app.cmd_people(self.job(), 'remove', 'mia')
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('與會人員：Leo、Amy、Ken\n', md)
        self.assertEqual(minutes_app.project_people('週會專案'), ['Mia'])   # she wasn't at this one; still the project's
        self.assertEqual([v['name'] for v in minutes_app.voices_view(self.job())], ['', ''])
        self.assertNotIn('Mia', minutes_app.meeting_people(self.job()))   # she doesn't come back by herself
        self.assertEqual(minutes_app.speakers_shown(self.job())['B'], '')

    def test_someone_who_spoke_is_not_listed_as_silent_under_another_spelling(self):
        minutes_app.save_meeting_people(self.job(), ['Jessie', 'Amy'])
        minutes_app.cmd_speaker(self.job(), 'B', '陳怡君（Jessie）')
        self.assertEqual(minutes_app.silent_people(self.job()), ['Amy'])

    def test_a_renamed_project_keeps_its_people(self):
        minutes_app.save_project_people('週會專案', ['Amy'])
        minutes_app.save_project_people('新名字', ['Ken'])
        minutes_app.cmd_rename_project('週會專案', '新名字')
        self.assertEqual(minutes_app.project_people('新名字'), ['Ken', 'Amy'])
        self.assertEqual(minutes_app.project_people('週會專案'), [])


class SpeakerPick(unittest.TestCase):
    """人員: each voice's menu starts on the AI's guess, which the minutes already use; picking someone else swaps
    the name in the minutes, remembers the voice, and settles the guess (Vin 2026-10-17)."""
    job = Flows.job

    def setUp(self):
        MeetingPeople.setUp(self)
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['check'] = [{'text': '講者 B 負責文章，可能是 Nina'}, {'text': '「HOWAN PASS」推測是台灣 PASS'}]
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))

    def tearDown(self):
        MeetingPeople.tearDown(self)

    def test_the_guess_goes_into_the_minutes_after_the_write_up(self):
        import speakers
        md = speakers.guesses_into(self.job_dir, self.md_path.read_text(encoding='utf-8'), self.job().result['check'])
        self.assertIn('Nina 說明：', md)
        self.assertEqual(minutes_app.speakers_shown(self.job()), {'A': '', 'B': 'Nina'})
        self.assertEqual([v['name'] for v in minutes_app.voices_view(self.job())], ['', ''])   # not remembered

    def test_picking_someone_else_swaps_the_name_and_settles_the_guess(self):
        import speakers
        self.md_path.write_text(speakers.guesses_into(self.job_dir, self.md_path.read_text(encoding='utf-8'),
                                                      self.job().result['check']), encoding='utf-8')
        minutes_app.cmd_speaker(self.job(), 'B', 'Mia')
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('Mia 說明：', md)
        self.assertNotIn('Nina', md)
        self.assertEqual(minutes_app.speakers_shown(self.job())['B'], 'Mia')
        self.assertEqual([c['label'] for c in minutes_app.check_items(self.job())], ['「HOWAN PASS」推測是台灣 PASS'])

    def written(self):
        import speakers
        self.md_path.write_text(speakers.guesses_into(self.job_dir, self.md_path.read_text(encoding='utf-8'),
                                                      self.job().result['check']), encoding='utf-8')

    def test_only_the_voices_own_places_change(self):
        md = self.md_path.read_text(encoding='utf-8').replace('講者 B 說明：', '講者 B 說明：報價由 Nina 負責。')
        self.md_path.write_text(md, encoding='utf-8')
        self.written()
        self.assertIn('Nina 說明：報價由 Nina 負責。', self.md_path.read_text(encoding='utf-8'))
        minutes_app.cmd_speaker(self.job(), 'B', 'Mia')
        self.assertIn('Mia 說明：報價由 Nina 負責。', self.md_path.read_text(encoding='utf-8'))
        minutes_app.cmd_speaker(self.job(), 'B', 'Lily')        # and again, from the name given last
        minutes_app.cmd_speaker(self.job(), 'B', 'Mia')
        self.assertIn('Mia 說明：報價由 Nina 負責。', self.md_path.read_text(encoding='utf-8'))

    def test_two_voices_guessed_as_the_same_person_keep_their_letters(self):
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['check'] = [{'text': '講者 A 主持，可能是 Nina'}, {'text': '講者 B 負責文章，可能是 Nina'}]
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        self.written()
        self.assertIn('講者 B 說明：', self.md_path.read_text(encoding='utf-8'))

    def test_a_name_inside_a_longer_name_stays(self):
        import speakers
        md = speakers.name_voice(self.job_dir, '陳怡君說明。怡君補充。', 'B', '怡君', 'Amy', ['陳怡君'])
        self.assertEqual(md, '陳怡君說明。Amy補充。')
        self.assertEqual(speakers.name_voice(self.job_dir, 'Vincent 與 Vin', 'C', 'Vin', 'Ken'), 'Vincent 與 Ken')

    def test_the_mail_names_the_voice_too(self):
        (self.job_dir / '信件內文.txt').write_text('講者 B 會再寄報價。', encoding='utf-8')
        minutes_app.cmd_speaker(self.job(), 'B', 'Mia')
        self.assertEqual((self.job_dir / '信件內文.txt').read_text(encoding='utf-8'), 'Mia 會再寄報價。')


class McpServer(unittest.TestCase):
    """Claude Code reads and changes meetings through mcp_server.py (issue #4): every meeting from any folder,
    archived ones only by name; writing goes through minutes_app's own commands and is logged as Claude Code."""

    job = Flows.job

    def setUp(self):
        Flows.setUp(self)
        import mcp_server
        self.mcp = mcp_server
        self.saved_recordings = minutes_app.RECORDINGS
        minutes_app.RECORDINGS = self.root
        r = json.loads((self.job_dir / 'result.json').read_text())
        r.pop('doc_url')                              # no Google here: the change stays in the file
        r['project'] = '週會專案'
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        (self.job_dir / '逐字稿.txt').write_text('[00:05] 報價下週由 Ken 寄出\n[01:10] 好\n', encoding='utf-8')

    def tearDown(self):
        minutes_app.RECORDINGS = self.saved_recordings
        Flows.tearDown(self)

    def ask(self, tool, **args):
        reply = self.mcp.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                 'params': {'name': tool, 'arguments': args}})['result']
        text = reply['content'][0]['text']
        return (text, True) if reply.get('isError') else (json.loads(text), False)

    def test_the_tools_and_which_ones_write(self):
        tools = self.mcp.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})['result']['tools']
        writes = {t['name'] for t in tools if not t['annotations']['readOnlyHint']}
        self.assertEqual(writes, {'name_speaker', 'add_note', 'replace_text', 'set_tags', 'set_project'})
        self.assertFalse([t['name'] for t in tools if re.search(r'delete|send|mail', t['name'])])
        init = self.mcp.handle({'jsonrpc': '2.0', 'id': 0, 'method': 'initialize',
                                'params': {'protocolVersion': '2025-06-18'}})['result']
        self.assertEqual(init['protocolVersion'], '2025-06-18')
        self.assertIsNone(self.mcp.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}))

    def test_search_finds_the_minutes_and_what_was_said(self):
        found, err = self.ask('search_meetings', query='預算 10')
        self.assertFalse(err)
        self.assertEqual(found['meetings'][0]['meeting'], '20261014-103000')
        self.assertTrue(all('預算' in m['text'] for m in found['meetings'][0]['matches']))
        said, _ = self.ask('search_meetings', query='報價 Ken')
        self.assertEqual(said['meetings'][0]['matches'][0], {'source': 'transcript', 'at': '00:05',
                                                              'text': '報價下週由 Ken 寄出'})
        none, _ = self.ask('search_meetings', query='預算', project='別的專案')
        self.assertEqual(none['meetings'], [])

    def test_an_archived_meeting_only_when_asked_for(self):
        (self.job_dir / '封存.json').write_text('{}')
        self.assertEqual(self.ask('list_meetings')[0]['meetings'], [])
        self.assertEqual(len(self.ask('list_meetings', include_archived=True)[0]['meetings']), 1)
        self.assertIn('預算 10 萬元', self.ask('get_minutes', meeting='20261014-103000')[0]['minutes'])

    def test_a_meeting_that_does_not_exist(self):
        said, err = self.ask('get_minutes', meeting='../../etc')
        self.assertTrue(err)
        self.assertIn('list_meetings', said)

    def test_replacing_words_changes_the_minutes_once_and_logs_claude_code(self):
        done, err = self.ask('replace_text', meeting='20261014-103000', old='預算確定為 10 萬元', new='預算確定為 12 萬元')
        self.assertFalse(err, done)
        self.assertIn('預算確定為 12 萬元', self.md_path.read_text(encoding='utf-8'))
        self.assertEqual(self.job().log_entries()[0]['who'], 'Claude Code')
        again, err = self.ask('replace_text', meeting='20261014-103000', old='預算確定為 10 萬元', new='x')
        self.assertTrue(err)
        self.assertIn('紀錄裡沒有這段文字', again)
        many, err = self.ask('replace_text', meeting='20261014-103000', old='Ken', new='Kenny')
        self.assertTrue(err)
        self.assertIn('出現 2 次', many)

    def test_a_note_goes_into_the_attachments(self):
        done, err = self.ask('add_note', meeting='20261014-103000', text='報價確定為每人 1,200 元。')
        self.assertFalse(err, done)
        md = self.md_path.read_text(encoding='utf-8')
        self.assertRegex(md, r'## 七、參考附件\n\n- 報價確定為每人 1,200 元。\n$')

    def test_minutes_already_mailed_say_so(self):
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['sent_at'] = '2026-10-14T12:00:00+08:00'
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        done, _ = self.ask('add_note', meeting='20261014-103000', text='補一句。')
        self.assertTrue(done['sent'])
        self.assertTrue(any('without a new mail' in n for n in done['notes']))

    def test_nothing_changes_while_the_minutes_are_being_written(self):
        (self.job_dir / 'status.json').write_text(json.dumps({'step': 'transcribe'}))
        said, err = self.ask('set_tags', meeting='20261014-103000', tags=['報價'])
        self.assertTrue(err)
        self.assertIn('written up', said)
        self.assertEqual(minutes_app.tags_of(self.job()), [])

    def test_tags_and_project(self):
        self.ask('set_tags', meeting='20261014-103000', tags=['報價', '報價', 'KOL'])
        self.assertEqual(minutes_app.tags_of(self.job()), ['報價', 'KOL'])
        self.assertEqual(self.ask('set_project', meeting='20261014-103000', project='新專案')[0]['project'], '新專案')

    def test_name_speaker_names_the_voice(self):
        (self.job_dir / '講者.json').write_text(json.dumps({'groups': {
            'A': {'name': '', 'seconds': 300, 'sample': [1, 5]}, 'B': {'name': '', 'seconds': 200, 'sample': [9, 12]}},
            'lines': ['A', 'B'], 'fixed': {}}, ensure_ascii=False))
        done, err = self.ask('name_speaker', meeting='20261014-103000', speaker='講者 B', name='Mia')
        self.assertFalse(err, done)
        self.assertEqual(self.ask('get_transcript', meeting='20261014-103000')[0]['lines'][1], '[01:10] Mia：好')
        nobody, err = self.ask('name_speaker', meeting='20261014-103000', speaker='C', name='Ken')
        self.assertTrue(err)

    def test_a_meeting_busy_with_something_else_answers_at_once(self):
        import fcntl
        import time
        with open(self.job_dir / '.app.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            began = time.time()
            said, err = self.ask('add_note', meeting='20261014-103000', text='補一句。')
        self.assertTrue(err)
        self.assertIn('別的動作', said)
        self.assertLess(time.time() - began, 10)

    def test_the_server_only_writes_json_and_survives_a_bad_message(self):
        lines = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
                 {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': ['x']},
                 {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'nope'}},
                 {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'}]
        done = subprocess.run([sys.executable, str(Path(minutes_app.__file__).with_name('mcp_server.py'))],
                              input='\n'.join(json.dumps(m) for m in lines) + '\nnot json\n', capture_output=True,
                              text=True, timeout=60, env={**os.environ, 'MINUTES_HOME': HOME})
        replies = [json.loads(line) for line in done.stdout.splitlines()]
        self.assertEqual([r.get('id') for r in replies], [1, 2, 3, 4, None])
        self.assertEqual(replies[2]['error']['code'], -32602)
        self.assertEqual(replies[4]['error']['code'], -32700)
        self.assertIn('tools', replies[3]['result'])


class AgentEdit(Flows):
    """An agent's change through minutes_app (note, replace) goes to the Google Doc too, and what the user typed
    before it is still logged as the user's."""

    def test_the_doc_gets_the_change_and_each_one_is_logged_by_who_made_it(self):
        sent = []
        ds.push = lambda doc_id, base, new: (sent.append(new), (ds.Plan([{'x': 1}], [], []), fake_doc(new), True))[1]
        saved_connect = minutes_app.connect
        minutes_app.connect = lambda: 'OFFLINE'      # nothing to pull: the push is what is checked
        self.md_path.write_text(MINUTES.replace('主要來自三篇文章', '主要來自四篇文章'), encoding='utf-8')
        os.environ['VINUTES_ACTOR'] = 'Claude Code'
        try:
            minutes_app.cmd_replace(self.job(), '預算確定為 10 萬元', '預算確定為 12 萬元')
        finally:
            os.environ.pop('VINUTES_ACTOR', None)
            minutes_app.connect = saved_connect
        self.assertIn('預算確定為 12 萬元', sent[-1])
        who = {e['text']: e['who'] for e in self.job().log_entries()}
        self.assertEqual(who[next(t for t in who if '12 萬元' in t)], 'Claude Code')
        self.assertNotEqual(who[next(t for t in who if '四' in t)], 'Claude Code')     # the user's own typing

    def test_a_replacement_over_two_lines_is_refused(self):
        with self.assertRaises(SystemExit) as stop:
            minutes_app.cmd_replace(self.job(), '預算確定為 10 萬元', '預算\n## 新章節')
        self.assertIn('不能有換行', str(stop.exception.code))


class ConnectAgents(unittest.TestCase):
    """install.sh connects Vinutes to the AI tools that keep their servers in a JSON file without touching the rest."""

    def setUp(self):
        import connect_agents
        self.ca = connect_agents
        self.root = Path(tempfile.mkdtemp(prefix='agents-'))
        self.file = self.root / 'mcp.json'

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_added_once_and_the_other_servers_kept(self):
        self.file.write_text(json.dumps({'mcpServers': {'ownmind': {'command': 'node'}}, 'theme': 'dark'}))
        self.assertIn('connected', self.ca.json_tool('Cursor', self.root, self.file, False))
        self.assertEqual(self.ca.json_tool('Cursor', self.root, self.file, False), 'Cursor: already connected')
        data = json.loads(self.file.read_text())
        self.assertEqual(data['theme'], 'dark')
        self.assertEqual(set(data['mcpServers']), {'ownmind', 'vinutes'})
        self.assertTrue(data['mcpServers']['vinutes']['args'][0].endswith('mcp_server.py'))
        self.ca.json_tool('Cursor', self.root, self.file, True)
        self.assertEqual(set(json.loads(self.file.read_text())['mcpServers']), {'ownmind'})

    def test_an_empty_file_or_none(self):
        self.file.write_text('')
        self.assertIn('connected', self.ca.json_tool('Antigravity', self.root, self.file, False))
        self.assertIn('vinutes', json.loads(self.file.read_text())['mcpServers'])

    def test_a_tool_not_installed_or_a_broken_file_is_left_alone(self):
        self.assertEqual(self.ca.json_tool('Cursor', self.root / 'none', self.root / 'none' / 'mcp.json', False),
                         'Cursor: not installed')
        self.file.write_text('{ not json')
        self.assertIn('left alone', self.ca.json_tool('Cursor', self.root, self.file, False))
        self.assertEqual(self.file.read_text(), '{ not json')

    def test_the_file_keeps_its_permissions(self):
        self.file.write_text('{}')
        os.chmod(self.file, 0o640)
        self.ca.json_tool('Cursor', self.root, self.file, False)
        self.assertEqual(os.stat(self.file).st_mode & 0o777, 0o640)


class ProjectBrief(unittest.TestCase):
    """專案背景 (Vin 2026-10-19): each project's people with what they do, its terms with the ways the transcript
    mishears them, and a few lines of background. 確認無誤 on a new name or a word, and an edit the user keeps, write
    into it; the AI that writes the next minutes reads every project's brief."""
    job = Flows.job

    def setUp(self):
        import briefs
        self.briefs = briefs
        Flows.setUp(self)
        self.result(project='官網改版')
        self.files = (minutes_app.PROJECT_PEOPLE, briefs.BRIEFS, minutes_app.CONFIG / 'glossary.md')
        for f in self.files:
            f.unlink(missing_ok=True)

    def tearDown(self):
        import project_folders
        for f in self.files:
            f.unlink(missing_ok=True)
        shutil.rmtree(project_folders.CACHE, ignore_errors=True)
        Flows.tearDown(self)

    def result(self, **changes):
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['check'] = [{'text': '新的人名：Grace', 'person': 'Grace', 'role': '說明會窗口'},
                      {'text': '「凱文」推測是 Kevin', 'heard': '凱文', 'meant': 'Kevin'}]
        r.update(changes)
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))

    def glossary(self):
        path = minutes_app.CONFIG / 'glossary.md'
        return path.read_text(encoding='utf-8') if path.is_file() else ''

    def test_the_brief_keeps_the_project_people_with_what_they_do(self):
        b = self.briefs.save('官網改版', {
            'people': [{'name': '陳怡君（Jessie）', 'role': '網站、目標頁'}, {'name': '李大華', 'role': '社群'},
                       {'name': 'jessie', 'role': '重複的人'}],
            'terms': [{'word': '#官網改版', 'meaning': '社群標籤'}, {'word': '', 'meaning': '沒有名詞的一列'}],
            'background': '第一期到 12 月底，交成效報告。'})
        self.assertEqual([(p['name'], p['role']) for p in b['people']], [('陳怡君（Jessie）', '網站、目標頁'), ('李大華', '社群')])
        self.assertEqual([(t['word'], t['meaning']) for t in b['terms']], [('#官網改版', '社群標籤')])
        self.assertEqual(b['background'], '第一期到 12 月底，交成效報告。')
        self.assertEqual(minutes_app.project_people('官網改版'), ['陳怡君（Jessie）', '李大華'])   # the 人員 tab's list

    def test_someone_taken_off_the_brief_leaves_the_project_list(self):
        self.briefs.save('官網改版', {'people': [{'name': 'Amy'}, {'name': 'Ken'}]})
        self.briefs.save('官網改版', {'people': [{'name': 'Ken'}]})
        self.assertEqual(minutes_app.project_people('官網改版'), ['Ken'])

    def test_the_people_tab_and_the_brief_show_the_same_list(self):
        minutes_app.save_project_people('官網改版', ['Amy'])
        self.assertEqual([p['name'] for p in self.briefs.load('官網改版')['people']], ['Amy'])

    def test_confirming_a_new_name_puts_the_person_in_the_brief(self):
        item = next(c for c in minutes_app.check_items(self.job()) if c.get('person'))
        self.assertEqual((item['person'], item['role']), ('Grace', '說明會窗口'))
        minutes_app.cmd_confirm(self.job(), '新的人名：Grace')
        self.assertEqual([(p['name'], p['role']) for p in self.briefs.load('官網改版')['people']],
                         [('Grace', '說明會窗口')])
        self.assertNotIn('新的人名：Grace', [c['label'] for c in minutes_app.check_items(self.job())])

    def test_a_confirmed_word_goes_into_the_project_brief(self):
        minutes_app.save_project_people('官網改版', ['Kevin'])
        minutes_app.cmd_confirm(self.job(), '「凱文」推測是 Kevin')
        self.assertEqual(self.briefs.load('官網改版')['people'][0]['heard'], ['凱文'])   # Kevin is a person: on him
        self.assertEqual(self.glossary(), '')
        learned = self.outs[-1]['learned'][0]
        self.assertEqual((learned['where'], learned['project']), ('brief', '官網改版'))

    def test_a_learned_word_moves_to_the_glossary_and_back_and_can_be_taken_back(self):
        minutes_app.cmd_confirm(self.job(), '「凱文」推測是 Kevin')
        item_id = self.outs[-1]['learned'][0]['id']
        self.assertEqual([t['word'] for t in self.briefs.load('官網改版')['terms']], ['Kevin'])   # no such person yet
        minutes_app.cmd_move_learned(self.job(), item_id, 'glossary')
        self.assertEqual(self.briefs.load('官網改版')['terms'], [])
        self.assertIn('| 凱文 | Kevin |', self.glossary())
        minutes_app.cmd_move_learned(self.job(), item_id, 'brief')
        self.assertNotIn('凱文', self.glossary())
        self.assertEqual(self.briefs.load('官網改版')['terms'][0]['heard'], ['凱文'])
        minutes_app.cmd_unlearn(self.job(), item_id, True)
        self.assertEqual(self.briefs.load('官網改版')['terms'], [])
        minutes_app.cmd_unlearn(self.job(), item_id, False)
        self.assertEqual(self.briefs.load('官網改版')['terms'][0]['heard'], ['凱文'])

    def test_a_meeting_without_a_project_learns_into_the_glossary(self):
        self.result(project='')
        minutes_app.cmd_confirm(self.job(), '「凱文」推測是 Kevin')
        self.assertIn('| 凱文 | Kevin |', self.glossary())
        self.assertNotIn('where', self.outs[-1]['learned'][0])
        self.assertNotIn('新的人名：Grace', [c['label'] for c in minutes_app.check_items(self.job())])   # nobody to add her to
        self.assertEqual(self.briefs.projects(), [])

    def test_a_renamed_project_keeps_its_brief(self):
        self.briefs.save('官網改版', {'people': [{'name': 'Amy', 'role': '網站'}], 'background': '十二月底結案。'})
        self.briefs.save('官網改版二期', {'people': [{'name': 'Ken', 'role': '社群'}], 'background': '先做目標頁。'})
        minutes_app.cmd_rename_project('官網改版', '官網改版二期')
        b = self.briefs.load('官網改版二期')
        self.assertEqual([(p['name'], p['role']) for p in b['people']], [('Ken', '社群'), ('Amy', '網站')])
        self.assertEqual(b['background'], '先做目標頁。\n十二月底結案。')
        self.assertEqual(self.briefs.load('官網改版')['people'], [])

    def test_the_ai_reads_every_brief_with_something_in_it(self):
        self.briefs.save('官網改版', {'people': [{'name': 'Kevin'}], 'terms': [{'word': '目標頁', 'meaning': '雙周會簡報'}]})
        self.briefs.add_heard('官網改版', '凱文', 'Kevin')
        self.briefs.add_heard('官網改版', 'kevan', 'Kevin')
        minutes_app.save_project_people('空專案', [])
        md = self.briefs.markdown()
        self.assertIn('## 官網改版', md)
        self.assertIn('- Kevin（逐字稿常聽成：凱文、kevan）', md)
        self.assertIn('- 目標頁：雙周會簡報', md)
        self.assertNotIn('空專案', md)
        self.assertEqual(self.briefs.markdown('空專案'), '')

    def test_the_minutes_writer_gets_the_briefs_in_its_folder(self):
        import auto_minutes
        self.briefs.save('官網改版', {'people': [{'name': 'Amy', 'role': '網站'}]})
        (self.job_dir / '逐字稿.txt').write_text('[00:01] 好，我們開始。\n', encoding='utf-8')
        work = auto_minutes.gather(self.job_dir, {}, self.root / 'minutes')
        self.assertIn('- Amy：網站', (work / '參考' / '專案背景.md').read_text(encoding='utf-8'))
        self.assertIn('專案背景.md', auto_minutes.prompt(work, {}, self.root / 'minutes'))

    def test_the_brief_keeps_the_project_folder_and_a_rename_keeps_it_too(self):
        folder = self.root / '春季活動'
        folder.mkdir()
        self.assertEqual(self.briefs.save('官網改版', {'folder': str(folder)})['folder'], str(folder.resolve()))
        self.briefs.save('官網改版', {'background': '十二月底結案。'})            # a save without the folder keeps it
        self.assertEqual(self.briefs.load('官網改版')['folder'], str(folder.resolve()))
        with self.assertRaises(SystemExit):                                    # a folder that isn't there
            self.briefs.save('官網改版', {'folder': str(self.root / '沒有這個資料夾')})
        self.assertEqual(self.briefs.load('官網改版')['folder'], str(folder.resolve()))
        minutes_app.cmd_rename_project('官網改版', '官網改版二期')
        self.assertEqual(self.briefs.folders(), {'官網改版二期': folder.resolve()})
        self.briefs.save('官網改版二期', {'folder': ''})                        # 移除資料夾
        self.assertEqual(self.briefs.folders(), {})

    def test_the_minutes_writer_gets_a_copy_of_the_project_folder(self):
        import auto_minutes
        import docx
        import project_folders
        folder = self.root / '春季活動'
        (folder / '會議紀錄').mkdir(parents=True)
        (folder / '.git').mkdir()
        (folder / '會議紀錄' / '10-14 週會.md').write_text('# 10/14 週會\n報價下週五前給。\n', encoding='utf-8')
        (folder / '.git' / 'notes.md').write_text('hidden', encoding='utf-8')
        (folder / '.DS_Store').write_bytes(b'\0')
        (folder / '場地照片.png').write_bytes(b'\x89PNG')
        word = docx.Document()
        word.add_paragraph('春遊祭提案：4 月在華山辦。')
        word.save(folder / '提案.docx')
        (folder / '~$提案.docx').write_bytes(b'lock')                         # Word's lock file
        (folder / '鎖住的.md').write_text('讀不到', encoding='utf-8')
        os.chmod(folder / '鎖住的.md', 0)                                      # unreadable: left out, nothing stops
        before = {str(p): (p.lstat().st_mtime_ns, p.read_bytes() if p.is_file() and os.access(p, os.R_OK) else b'')
                  for p in folder.rglob('*')}
        self.briefs.save('官網改版', {'folder': str(folder)})
        (self.job_dir / '逐字稿.txt').write_text('[00:01] 好，我們開始。\n', encoding='utf-8')
        work = auto_minutes.gather(self.job_dir, {}, self.root / 'minutes')
        copy = work / '參考' / '專案資料夾' / '官網改版'
        self.assertEqual(sorted(str(p.relative_to(copy)) for p in copy.rglob('*') if p.is_file()),
                         sorted(['會議紀錄/10-14 週會.md', '提案.docx.txt', '檔案清單.md']))
        self.assertIn('4 月在華山辦', (copy / '提案.docx.txt').read_text(encoding='utf-8'))
        listed = (copy / '檔案清單.md').read_text(encoding='utf-8')
        self.assertIn('會議紀錄/10-14 週會.md', listed)
        self.assertIn('提案.docx　', listed)
        self.assertIn('專案資料夾', auto_minutes.prompt(work, {}, self.root / 'minutes'))
        self.assertEqual(len(list(project_folders.CACHE.glob('*.txt'))), 1)   # the Word file became text once
        after = {str(p): (p.lstat().st_mtime_ns, p.read_bytes() if p.is_file() and os.access(p, os.R_OK) else b'')
                 for p in folder.rglob('*')}
        self.assertEqual(after, before)                                       # the folder itself is never touched
        (folder / '會議紀錄' / '10-14 週會.md').write_text('改過', encoding='utf-8')
        import references
        with mock.patch.object(references, 'read_file', side_effect=AssertionError('converted again')):
            work = auto_minutes.gather(self.job_dir, {}, self.root / 'minutes')   # the next meeting: a fresh copy
        copy = work / '參考' / '專案資料夾' / '官網改版'
        self.assertEqual((copy / '會議紀錄' / '10-14 週會.md').read_text(encoding='utf-8'), '改過')
        self.assertIn('4 月在華山辦', (copy / '提案.docx.txt').read_text(encoding='utf-8'))   # from the cache

    def test_a_project_folder_that_fails_never_stops_the_minutes(self):
        import auto_minutes
        import project_folders
        folder = self.root / '春季活動'
        folder.mkdir()
        self.briefs.save('官網改版', {'folder': str(folder)})
        (self.job_dir / '逐字稿.txt').write_text('[00:01] 好，我們開始。\n', encoding='utf-8')
        with mock.patch.object(project_folders, 'copy', side_effect=RuntimeError('boom')):
            work = auto_minutes.gather(self.job_dir, {}, self.root / 'minutes')
        self.assertTrue((work / '逐字稿.txt').is_file())
        self.assertFalse((work / '參考' / '專案資料夾').exists())
        self.assertIn('project folders not copied', (self.job_dir / 'log.txt').read_text(encoding='utf-8'))

    def test_project_names_never_leave_or_share_their_folder(self):
        import project_folders
        taken = set()
        self.assertEqual([project_folders.place(p, taken) for p in ('..', '.', 'ABC', 'abc', 'a/b')],
                         ['專案..', '專案.', 'ABC', 'abc (2)', 'a／b'])

    def test_a_project_folder_past_the_limits_keeps_its_newest_files(self):
        import project_folders
        folder = self.root / '大資料夾'
        folder.mkdir()
        for i in range(5):
            f = folder / f'{i}.txt'
            f.write_text('x' * 100, encoding='utf-8')
            os.utime(f, (1_700_000_000 + i, 1_700_000_000 + i))
        with mock.patch.object(project_folders, 'MOST_FILES', 3):
            self.assertEqual([p.name for p, _ in project_folders.files(folder)], ['4.txt', '3.txt', '2.txt'])
        with mock.patch.object(project_folders, 'MOST_BYTES', 250):
            self.assertEqual([p.name for p, _ in project_folders.files(folder)], ['4.txt', '3.txt'])

    def test_the_brief_commands_answer_and_refuse_a_broken_brief(self):
        minutes_app.cmd_save_brief('官網改版', json.dumps({'people': [{'name': 'Amy'}]}))
        self.assertEqual(self.outs[-1]['brief']['people'][0]['name'], 'Amy')
        minutes_app.cmd_brief('官網改版')
        self.assertEqual(self.outs[-1]['brief']['project'], '官網改版')
        with self.assertRaises(SystemExit):
            minutes_app.cmd_save_brief('官網改版', 'not json')
        with self.assertRaises(SystemExit):
            minutes_app.cmd_save_brief('', '{}')

    def test_saving_keeps_what_was_learned_while_the_window_was_open(self):
        self.briefs.save('官網改版', {'people': [{'name': 'Amy'}], 'terms': [{'word': 'POC', 'meaning': '試行'}]})
        shown = self.briefs.load('官網改版')                               # the window opens
        self.briefs.add_heard('官網改版', '愛咪', 'Amy')                   # the 15-second sync learns two words
        self.briefs.add_heard('官網改版', '凱文', 'Kevin')
        minutes_app.save_project_people('官網改版', ['Amy', 'Ken'])        # and someone is added in 人員
        b = self.briefs.save('官網改版', {
            'people': [{'name': 'Amy', 'role': '網站'}], 'terms': [{'word': 'POC', 'meaning': '試行'}], 'background': '',
            'seen': {'people': [p['name'] for p in shown['people']], 'terms': [x['word'] for x in shown['terms']]}})
        self.assertEqual([(p['name'], p['role'], p['heard']) for p in b['people']], [('Amy', '網站', ['愛咪']), ('Ken', '', [])])
        self.assertEqual([(x['word'], x['heard']) for x in b['terms']], [('POC', []), ('Kevin', ['凱文'])])

    def test_a_save_without_some_parts_leaves_them_as_they_are(self):
        self.briefs.save('官網改版', {'people': [{'name': 'Amy'}], 'terms': [{'word': 'POC'}], 'background': '十二月底結案。'})
        b = self.briefs.save('官網改版', {})
        self.assertEqual(([p['name'] for p in b['people']], [x['word'] for x in b['terms']], b['background']),
                         (['Amy'], ['POC'], '十二月底結案。'))

    def test_a_word_taken_back_after_a_rename_comes_off_the_new_name(self):
        minutes_app.cmd_confirm(self.job(), '「凱文」推測是 Kevin')
        item_id = self.outs[-1]['learned'][0]['id']
        minutes_app.cmd_rename_project('官網改版', '官網改版二期')
        self.result(project='官網改版二期')
        minutes_app.cmd_unlearn(self.job(), item_id, True)
        self.assertEqual(self.briefs.load('官網改版二期')['terms'], [])
        self.assertEqual(self.briefs.projects(), ['官網改版二期'])      # no empty brief under the old name
        self.assertNotIn('## 官網改版\n', self.briefs.markdown())

    def test_taking_a_word_back_leaves_a_term_the_user_made(self):
        self.briefs.save('官網改版', {'terms': [{'word': 'POC'}]})
        self.briefs.add_heard('官網改版', 'PO西', 'POC')
        self.briefs.remove_heard('官網改版', 'PO西', 'POC')
        self.assertEqual([(x['word'], x['heard']) for x in self.briefs.load('官網改版')['terms']], [('POC', [])])

    def test_a_word_two_people_share_is_nobodys(self):
        minutes_app.save_project_people('官網改版', ['王小明（PM）', '李大華（PM）'])
        self.briefs.add_heard('官網改版', 'P M', 'PM')
        b = self.briefs.load('官網改版')
        self.assertEqual([p['heard'] for p in b['people']], [[], []])
        self.assertEqual([(x['word'], x['heard']) for x in b['terms']], [('PM', ['P M'])])

    def test_only_names_the_project_does_not_have_are_asked_about(self):
        minutes_app.save_project_people('官網改版', ['Grace'])
        self.result(check=[{'text': '新的人名：Grace', 'person': 'Grace'}, {'person': 'Leo', 'role': 'KOL'},
                           {'text': '新的人名：x', 'person': ['Grace']}])
        self.assertEqual([(c['label'], c['person'], c['role']) for c in minutes_app.check_items(self.job())],
                         [('新的人名：Leo', 'Leo', 'KOL')])
        self.result(project='', check=[{'person': 'Leo'}])          # no project: nobody to add her to
        self.assertEqual(minutes_app.check_items(self.job()), [])

    def test_a_broken_brief_file_is_set_aside_not_emptied(self):
        self.briefs.BRIEFS.write_text('{"官網改版": ', encoding='utf-8')
        self.briefs.add_heard('別的專案', '凱文', 'Kevin')
        kept = list(self.briefs.BRIEFS.parent.glob('briefs.json.*.bad'))
        self.assertEqual([f.read_text(encoding='utf-8') for f in kept], ['{"官網改版": '])
        for f in kept:
            f.unlink()

    def test_four_windows_writing_at_once_lose_nothing(self):
        code = ('import sys; sys.path.insert(0, sys.argv[1]); import briefs\n'
                'for i in range(30): briefs.add_heard(sys.argv[2], f"h{i}", f"w{i}")')
        scripts = str(Path(minutes_app.__file__).parent)
        runs = [subprocess.Popen([sys.executable, '-c', code, scripts, f'P{n}'], env={**os.environ, 'MINUTES_HOME': HOME})
                for n in range(4)]
        self.assertEqual([r.wait() for r in runs], [0, 0, 0, 0])
        self.assertEqual(sorted(self.briefs.projects()), ['P0', 'P1', 'P2', 'P3'])
        self.assertEqual({len(self.briefs.load(f'P{n}')['terms']) for n in range(4)}, {30})


class EnterWithInputMethod(unittest.TestCase):
    """注音 and the other input methods: the Enter that picks a word is not a send. WebKit fires that keydown after the
    word is already in the box (isComposing false, keyCode 229), so every Enter in the window asks inputMethod(e)."""

    def handlers(self, src):
        found = []
        for m in re.finditer(r"addEventListener\('keydown'", src):
            depth = 0
            for j in range(src.index('(', m.start()), len(src)):
                depth += {'(': 1, ')': -1}.get(src[j], 0)
                if depth == 0:
                    break
            if "'Enter'" in src[m.start():j]:
                found.append(src[m.start():j])
        return found

    def test_every_enter_lets_the_input_method_have_it(self):
        src = (Path(__file__).resolve().parent.parent / 'recorder' / 'app' / 'app.js').read_text(encoding='utf-8')
        handlers = self.handlers(src)
        self.assertGreaterEqual(len(handlers), 8)
        self.assertEqual([h.split('\n')[0] for h in handlers if 'inputMethod(e)' not in h], [])
        self.assertEqual(src.count('e.isComposing'), 1)        # only inside inputMethod: no half checks again


# a 1×1 PNG: enough for a picture the AI is shown
PNG = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010806000000'
                    '1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082')


class AskTheAi(unittest.TestCase):
    """The box under the minutes (Vin 2026-10-19): a pasted picture goes to the AI with the sentence, not into the
    minutes; a 待確認 card that is wrong is put right through the AI, and one not worth handling is skipped. Neither
    teaches Vinutes the wrong word the way 確認無誤 on a wrong guess does."""
    job = Flows.job

    def setUp(self):
        import ai_runner
        import briefs
        Flows.setUp(self)
        self.ai, self.briefs = ai_runner, briefs
        self.saved_ai = {n: getattr(ai_runner, n) for n in ('find', 'run')}
        self.saved_connect, self.saved_speaker = minutes_app.connect, minutes_app.cmd_speaker
        minutes_app.connect = lambda: 'OFFLINE'      # nothing to pull: what is pushed is checked
        ds.push = lambda doc_id, base, new: (ds.Plan([{'x': 1}], [], []), fake_doc(new), True)
        ai_runner.find = lambda key=None: '/x/claude'
        self.calls, self.code, self.change = [], 0, (lambda md: md)

        def run(prompt, folder, **kw):
            self.calls.append({'prompt': prompt, 'files': sorted(p.name for p in folder.iterdir()), **kw})
            md = (folder / '紀錄.md').read_text(encoding='utf-8')
            (folder / '紀錄.md').write_text(self.change(md), encoding='utf-8')
            (folder / '說明.txt').write_text('改好了', encoding='utf-8')
            return subprocess.CompletedProcess([], self.code, '', '')
        ai_runner.run = run
        r = json.loads((self.job_dir / 'result.json').read_text())
        r.update(project='官網改版', check=[{'text': '「Fresh」推測是 Threads', 'heard': 'Fresh', 'meant': 'Threads'},
                                          '講者 C 只有附和，未列與會', '講者 B 推測是 Ken'])
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        self.files = (minutes_app.PROJECT_PEOPLE, briefs.BRIEFS, minutes_app.CONFIG / 'glossary.md')
        for f in self.files:
            f.unlink(missing_ok=True)

    def tearDown(self):
        for name, fn in self.saved_ai.items():
            setattr(self.ai, name, fn)
        minutes_app.connect, minutes_app.cmd_speaker = self.saved_connect, self.saved_speaker
        for f in self.files:
            f.unlink(missing_ok=True)
        Flows.tearDown(self)

    def labels(self):
        return [c['label'] for c in minutes_app.check_items(self.job())]

    def main(self, *args):
        argv, sys.argv = sys.argv, ['minutes_app.py', *args]
        try:
            minutes_app.main()
        finally:
            sys.argv = argv
            for lock in minutes_app.TURN:
                lock.close()
            minutes_app.TURN.clear()

    def test_a_pasted_picture_goes_to_the_ai_and_not_into_the_minutes(self):
        picture = self.root / '貼上的圖片 2026-10-19 17.04.12.png'
        picture.write_bytes(PNG)
        self.change = lambda md: md.replace('10 萬元。', '12 萬元。')
        self.main('ask', str(self.job_dir), '預算改成截圖上的數字', '--pictures', json.dumps([str(picture)]))
        call = self.calls[-1]
        self.assertIn('screenshot-1.png', call['files'])
        self.assertIn('screenshot-1.png', call['prompt'])
        self.assertIn('預算改成截圖上的數字', call['prompt'])
        self.assertEqual([p.name for p in call['pictures']], ['screenshot-1.png'])
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('活動預算確定為 12 萬元。', md)
        self.assertNotIn('貼上的圖片', md)

    def test_a_request_without_pictures_reads_as_before(self):
        self.main('ask', str(self.job_dir), '主持人是王小明')
        self.assertIn('主持人是王小明', self.calls[-1]['prompt'])
        self.assertNotIn('screenshot', self.calls[-1]['prompt'])
        self.assertEqual(self.calls[-1]['pictures'], [])

    def test_codex_is_handed_the_pictures_before_the_prompt(self):
        folder = self.root / 'work'
        folder.mkdir()
        codex, _ = self.ai.command('codex', '/x/codex', 'P', folder, write=False, pictures=[folder / 'screenshot-1.png'])
        self.assertEqual(codex[-1], 'P')
        self.assertIn(f'--image={folder / "screenshot-1.png"}', codex)
        claude, _ = self.ai.command('claude', '/x/claude', 'P', folder, write=False, pictures=[folder / 'screenshot-1.png'])
        self.assertFalse([a for a in claude if a.startswith('--image')])   # Claude opens the file itself

    def test_skipping_a_guess_takes_the_card_off_and_learns_nothing(self):
        minutes_app.cmd_skip(self.job(), '「Fresh」推測是 Threads')
        self.assertNotIn('「Fresh」推測是 Threads', self.labels())
        self.assertNotIn('「Fresh」推測是 Threads', [c['label'] for c in self.outs[-1]['check']])
        self.assertEqual(self.briefs.load('官網改版')['terms'], [])
        self.assertNotIn('Fresh', self.glossary())
        self.assertIn('略過', ' '.join(e['text'] for e in self.job().log_entries()))
        with self.assertRaises(SystemExit):
            minutes_app.cmd_skip(self.job(), '「Fresh」推測是 Threads')    # already gone

    def glossary(self):
        path = minutes_app.CONFIG / 'glossary.md'
        return path.read_text(encoding='utf-8') if path.is_file() else ''

    def test_a_wrong_guess_put_right_changes_the_minutes_and_learns_the_right_word(self):
        self.change = lambda md: md.replace('Threads 與', 'Threads App 與')
        minutes_app.cmd_correct(self.job(), '「Fresh」推測是 Threads', 'Threads App')
        prompt = self.calls[-1]['prompt']
        for word in ('Fresh', 'Threads', 'Threads App'):
            self.assertIn(word, prompt)
        self.assertIn('Threads App 與 Instagram', self.md_path.read_text(encoding='utf-8'))
        self.assertNotIn('「Fresh」推測是 Threads', self.labels())
        self.assertEqual([(x['word'], x['heard']) for x in self.briefs.load('官網改版')['terms']], [('Threads App', ['Fresh'])])
        self.assertIn('Threads App', ' '.join(e['text'] for e in self.job().log_entries()))

    def test_a_correction_the_ai_could_not_make_keeps_the_card(self):
        self.code = 1
        with self.assertRaises(SystemExit):
            minutes_app.cmd_correct(self.job(), '「Fresh」推測是 Threads', 'Threads App')
        self.assertIn('「Fresh」推測是 Threads', self.labels())
        self.assertEqual(self.briefs.load('官網改版')['terms'], [])

    def test_a_note_without_a_word_goes_to_the_ai_as_it_is(self):
        self.change = lambda md: md.replace('與會人員：Amy、Ken', '與會人員：Amy、Ken、C')
        minutes_app.cmd_correct(self.job(), '講者 C 只有附和，未列與會', 'C 是 Amy，有與會')
        prompt = self.calls[-1]['prompt']
        self.assertIn('講者 C 只有附和，未列與會', prompt)
        self.assertIn('C 是 Amy，有與會', prompt)
        self.assertNotIn('講者 C 只有附和，未列與會', self.labels())

    def test_a_correction_with_nothing_to_change_still_takes_the_card_off(self):
        # Vin 2026-10-19: he pressed 修改 and sent, the AI found the minutes already right, and the card stayed
        minutes_app.cmd_correct(self.job(), '「Fresh」推測是 Threads', 'Threads App')   # the minutes come back unchanged
        self.assertNotIn('「Fresh」推測是 Threads', self.labels())
        self.assertEqual(self.briefs.load('官網改版')['terms'], [])                     # nothing changed: nothing learned

    def test_a_sentence_typed_as_the_fix_is_not_learned_as_the_word(self):
        # 「又有好好玩」 was learned as 「這一段不是又有好好玩，是「悠遊好好玩」這個是…」 (2026-10-19)
        self.change = lambda md: md.replace('Threads 與', 'Threads App 與')
        minutes_app.cmd_correct(self.job(), '「Fresh」推測是 Threads', '這一段不是 Fresh，是「Threads App」這個網站')
        self.assertNotIn('「Fresh」推測是 Threads', self.labels())
        self.assertEqual(self.briefs.load('官網改版')['terms'], [])

    def test_a_new_name_put_right_goes_into_the_brief_with_its_role(self):
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['check'] = [{'text': '新的人名：Grace', 'person': 'Grace', 'role': '說明會窗口'}]
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        self.change = lambda md: md.replace('Amy、Ken', 'Amy、Ken、Gracie')
        minutes_app.cmd_correct(self.job(), '新的人名：Grace', 'Gracie')
        self.assertEqual([(x['name'], x['role']) for x in self.briefs.load('官網改版')['people']], [('Gracie', '說明會窗口')])
        self.assertIn('Grace', self.calls[-1]['prompt'])

    def test_requests_left_waiting_when_the_window_closes_are_done_in_order(self):
        self.change = lambda md: md.replace('10 萬元', '12 萬元', 1) if '12 萬元' not in md else md.replace('Threads 與', 'Threads App 與')
        items = [{'kind': 'ask', 'text': '預算改成 12 萬'}, {'kind': 'correct', 'item': '沒有這一項', 'text': 'x'},
                 {'kind': 'correct', 'item': '「Fresh」推測是 Threads', 'text': 'Threads App'}]
        self.main('ask_many', str(self.job_dir), json.dumps(items, ensure_ascii=False))
        self.assertEqual(len(self.calls), 2)                       # the missing item is passed over, the rest still go
        self.assertIn('預算改成 12 萬', self.calls[0]['prompt'])
        self.assertIn('Threads App', self.calls[1]['prompt'])
        md = self.md_path.read_text(encoding='utf-8')
        self.assertIn('12 萬元', md)
        self.assertIn('Threads App 與', md)
        self.assertNotIn('「Fresh」推測是 Threads', self.labels())

    def test_a_question_about_a_voice_put_right_with_a_name_names_the_voice(self):
        named = []
        minutes_app.cmd_speaker = lambda job, group, name, line='': named.append((group, name))
        (self.job_dir / '講者.json').write_text(json.dumps({'groups': {'C': {'name': '', 'seconds': 40}}, 'lines': []}))
        minutes_app.cmd_correct(self.job(), '講者 C 只有附和，未列與會', 'Amy')
        self.assertEqual(named, [('C', 'Amy')])
        self.assertEqual(self.calls, [])
        minutes_app.cmd_correct(self.job(), '講者 C 只有附和，未列與會', 'C 其實是會議室的雜音，不是人')
        self.assertEqual(len(self.calls), 1)                       # a sentence goes to the AI

    def test_only_a_name_for_a_line_asking_who_a_voice_is_names_the_voice(self):
        named = []
        minutes_app.cmd_speaker = lambda job, group, name, line='': named.append((group, name))
        (self.job_dir / '講者.json').write_text(json.dumps({'groups': {'C': {'name': '', 'seconds': 40}}, 'lines': []}))
        r = json.loads((self.job_dir / 'result.json').read_text())
        asks = ['講者 C 只有附和，未列與會', '講者 C 請補姓名', '講者 C 是誰不確定']
        r['check'] = ['講者 C 提到上線日 10/20，待確認', '講者 C 說的「SL」推測是 SEO', *asks]
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        minutes_app.cmd_correct(self.job(), '講者 C 提到上線日 10/20，待確認', '10/27')    # a date, not a name
        minutes_app.cmd_correct(self.job(), '講者 C 說的「SL」推測是 SEO', 'GEO')          # a word guess
        for label, nobody in zip(asks, ('雜音', '不是人是雜音', '同 B')):
            minutes_app.cmd_correct(self.job(), label, nobody)
        self.assertEqual(named, [])
        self.assertEqual(len(self.calls), 5)                       # each went to the AI instead

    def test_a_guess_learned_only_when_the_minutes_have_the_right_word(self):
        # a sentence with spaces passes the punctuation check; it is not what the AI wrote into the minutes
        self.change = lambda md: md.replace('Threads 與', 'Threads App 與')
        minutes_app.cmd_correct(self.job(), '「Fresh」推測是 Threads', '不是 Fresh 是 Threads App 這個')
        self.assertEqual(self.briefs.load('官網改版')['terms'], [])
        self.change = lambda md: md.replace('Threads App 與', 'Threads.com 與')
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['check'] = [{'text': '「Fresh2」推測是 Threads', 'heard': 'Fresh2', 'meant': 'Threads'}]
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        minutes_app.cmd_correct(self.job(), '「Fresh2」推測是 Threads', 'Threads.com')   # a dot is fine in a term
        self.assertEqual([(x['word'], x['heard']) for x in self.briefs.load('官網改版')['terms']], [('Threads.com', ['Fresh2'])])

    def test_a_new_name_answered_with_nothing_to_change_is_not_added_to_the_brief(self):
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['check'] = [{'text': '新的人名：Grace', 'person': 'Grace', 'role': '說明會窗口'}]
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        minutes_app.cmd_correct(self.job(), '新的人名：Grace', 'Gracie')          # the minutes come back unchanged
        self.assertEqual(self.briefs.load('官網改版')['people'], [])

    def test_an_ai_that_says_nothing_keeps_the_card(self):
        def silent(prompt, folder, **kw):
            self.calls.append({'prompt': prompt})
            return subprocess.CompletedProcess([], 0, '', '')              # no 說明.txt, 紀錄.md as it was
        self.ai.run = silent
        minutes_app.cmd_correct(self.job(), '「Fresh」推測是 Threads', 'Threads App')
        self.assertIn('「Fresh」推測是 Threads', self.labels())

    def test_a_voice_guess_put_right_names_the_voice(self):
        named = []
        minutes_app.cmd_speaker = lambda job, group, name, line='': named.append((group, name))
        minutes_app.cmd_correct(self.job(), '講者 B 推測是 Ken', 'Kenny')
        self.assertEqual(named, [('B', 'Kenny')])
        self.assertEqual(self.calls, [])

    def test_an_empty_correction_is_refused(self):
        with self.assertRaises(SystemExit):
            minutes_app.cmd_correct(self.job(), '「Fresh」推測是 Threads', '  ')
        self.assertEqual(self.calls, [])


class References(unittest.TestCase):
    """＋ beside the box under the minutes (Vin 2026-10-19): files and links handed to the AI with a sentence are read
    into its folder as 參考資料-1, -2, … and never go into the minutes."""
    job = Flows.job
    setUp, tearDown, main = AskTheAi.setUp, AskTheAi.tearDown, AskTheAi.main

    def run_ai(self, *refs, pictures=()):
        import ai_runner
        seen = {}
        run = ai_runner.run

        def reading(prompt, folder, **kw):
            seen.update({p.name: p.read_bytes() for p in folder.iterdir() if p.name.startswith('參考資料')})
            return run(prompt, folder, **kw)
        ai_runner.run = reading
        args = ['ask', str(self.job_dir), '照參考資料補上預算', '--refs', json.dumps(list(refs), ensure_ascii=False)]
        if pictures:
            args += ['--pictures', json.dumps([str(p) for p in pictures])]
        self.main(*args)
        return seen

    def office(self, name: str, parts: dict) -> Path:
        import zipfile
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as z:
            for part, xml in parts.items():
                z.writestr(part, xml)
        return path

    def test_word_excel_powerpoint_and_pdf_become_files_the_ai_reads(self):
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        xlsx = self.office('10月業績.xlsx', {
            'xl/workbook.xml': f'<workbook {ns}><sheets><sheet name="通路"/><sheet name="合計"/></sheets></workbook>',
            'xl/sharedStrings.xml': f'<sst {ns}><si><t>通路</t></si><si><t>業績</t></si><si><r><t>官</t></r><r><t>網</t></r></si></sst>',
            'xl/worksheets/sheet1.xml': f'<worksheet {ns}><sheetData><row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>'
                                        '<row><c t="s"><v>2</v></c><c><v>120000</v></c></row></sheetData></worksheet>',
            'xl/worksheets/sheet2.xml': f'<worksheet {ns}><sheetData><row><c t="inlineStr"><is><t>總計</t></is></c>'
                                        '<c><v>120000</v></c></row></sheetData></worksheet>'})
        a = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        pptx = self.office('提案.pptx', {
            'ppt/slides/slide10.xml': f'<sld {a}><a:p><a:r><a:t>第十頁</a:t></a:r></a:p></sld>',
            'ppt/slides/slide2.xml': f'<sld {a}><a:p><a:r><a:t>預算 </a:t></a:r><a:r><a:t>12 萬</a:t></a:r></a:p></sld>'})
        src = self.root / '會議前說明.txt'
        src.write_text('主持人是王小明', encoding='utf-8')
        subprocess.run(['/usr/bin/textutil', '-convert', 'docx', str(src)], check=True, capture_output=True)
        pdf = self.root / '報價.pdf'
        pdf.write_bytes(b'%PDF-1.4 x')
        seen = self.run_ai(*[{'kind': 'file', 'path': str(p)} for p in (xlsx, pptx, self.root / '會議前說明.docx', pdf)])
        self.assertEqual(sorted(seen), ['參考資料-1.txt', '參考資料-2.txt', '參考資料-3.txt', '參考資料-4.pdf'])
        self.assertEqual(seen['參考資料-1.txt'].decode().splitlines(),
                         ['## 通路', '通路\t業績', '官網\t120000', '', '## 合計', '總計\t120000'])
        self.assertEqual(seen['參考資料-2.txt'].decode().splitlines(), ['## Slide 1', '預算 12 萬', '', '## Slide 2', '第十頁'])
        self.assertIn('主持人是王小明', seen['參考資料-3.txt'].decode())
        prompt = self.calls[-1]['prompt']
        self.assertIn('參考資料-1.txt（10月業績.xlsx）', prompt)
        self.assertIn('參考資料-4.pdf（報價.pdf）', prompt)
        self.assertNotIn('參考資料', self.md_path.read_text(encoding='utf-8'))

    def test_a_picture_handed_with_the_plus_goes_with_the_screenshots(self):
        picture = self.root / '白板.png'
        picture.write_bytes(PNG)
        seen = self.run_ai({'kind': 'file', 'path': str(picture)})
        self.assertEqual(seen, {})
        self.assertEqual([p.name for p in self.calls[-1]['pictures']], ['screenshot-1.png'])
        self.assertNotIn('使用者附了參考資料', self.calls[-1]['prompt'])

    def web(self, pages: dict, drive: dict | None = None):
        """urllib answers with pages[url] = (bytes, content type, address it lands on); Drive with drive[url]."""
        import attachments
        import email.message
        import references
        asked = []

        class Resp:
            def __init__(self, url):
                self.body, ctype, self.landed = pages[url]
                self.headers = email.message.Message()
                self.headers['Content-Type'] = ctype
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def geturl(self): return self.landed
            def read(self, n=-1): return self.body
        saved = references.urllib.request.urlopen, attachments.call
        references.urllib.request.urlopen = lambda req, timeout=0: asked.append(req.full_url) or Resp(req.full_url)
        attachments.call = lambda url, want='json', **k: asked.append(url) or (drive or {})[url]
        self.addCleanup(lambda: (setattr(references.urllib.request, 'urlopen', saved[0]),
                                 setattr(attachments, 'call', saved[1])))
        return asked

    def test_a_page_is_read_as_its_text_and_a_google_file_through_the_login(self):
        page = '<html><head><title>x</title><style>p{}</style></head><body><script>var a</script>' \
               '<h1>FUNIT 9 月</h1><p>流量   12 萬</p></body></html>'
        big5 = '<html><head><meta charset="big5"></head><body><p>預算 12 萬</p></body></html>'.encode('big5')
        doc = ds.DRIVE + 'S' * 30
        self.web({'https://example.com/report': (page.encode(), 'text/html; charset=utf-8', 'https://example.com/report'),
                  'https://example.com/big5': (big5, 'text/html', 'https://example.com/big5')},
                 {doc + '?fields=name,mimeType': {'name': '預算', 'mimeType': 'application/vnd.google-apps.document'},
                  doc + '/export?mimeType=text/plain': '\ufeff預算 12 萬'.encode()})
        seen = self.run_ai({'kind': 'link', 'url': 'https://example.com/report'},
                           {'kind': 'link', 'url': 'https://docs.google.com/document/u/1/d/' + 'S' * 30 + '/edit'},
                           {'kind': 'link', 'url': 'https://example.com/big5'})
        self.assertEqual(seen['參考資料-1.txt'].decode(), 'https://example.com/report\n\nx\nFUNIT 9 月\n流量 12 萬')
        self.assertTrue(seen['參考資料-2.txt'].decode().endswith('\n\n預算 12 萬'))     # no mark before the words
        self.assertIn('預算 12 萬', seen['參考資料-3.txt'].decode())                    # the page's own encoding
        self.assertIn('參考資料-1.txt（https://example.com/report）', self.calls[-1]['prompt'])

    def test_every_tab_of_a_google_sheet_and_a_pdf_kept_in_drive_are_read(self):
        sheet, pdf = ds.DRIVE + 'T' * 30, ds.DRIVE + 'P' * 30
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        xlsx = self.office('x.xlsx', {
            'xl/workbook.xml': f'<workbook {ns}><sheets><sheet name="一月"/><sheet name="二月"/></sheets></workbook>',
            'xl/worksheets/sheet1.xml': f'<worksheet {ns}><sheetData><row><c t="inlineStr"><is><t>a</t></is></c></row></sheetData></worksheet>',
            'xl/worksheets/sheet2.xml': f'<worksheet {ns}><sheetData><row><c t="inlineStr"><is><t>預算</t></is></c></row></sheetData></worksheet>'})
        self.web({}, {sheet + '?fields=name,mimeType': {'name': '業績', 'mimeType': 'application/vnd.google-apps.spreadsheet'},
                      sheet + '/export?mimeType=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': xlsx.read_bytes(),
                      pdf + '?fields=name,mimeType': {'name': '報價.pdf', 'mimeType': 'application/pdf'},
                      pdf + '?alt=media': b'%PDF-1.4 x'})
        seen = self.run_ai({'kind': 'link', 'url': 'https://docs.google.com/spreadsheets/d/' + 'T' * 30 + '/edit#gid=2'},
                           {'kind': 'link', 'url': 'https://drive.google.com/file/d/' + 'P' * 30 + '/view?usp=sharing'})
        self.assertIn('## 二月\n預算', seen['參考資料-1.txt'].decode())
        self.assertEqual(seen['參考資料-2.pdf'], b'%PDF-1.4 x')
        self.assertEqual(sorted(p for p in self.calls[-1]['files'] if '參考' in p), ['參考資料-1.txt', '參考資料-2.pdf'])

    def test_a_page_that_sends_you_to_sign_in_stops_before_the_ai_starts(self):
        self.web({'https://intra.example.com/doc': (b'<html><body>Sign in</body></html>', 'text/html',
                                                   'https://intra.example.com/login?next=/doc')})
        with self.assertRaises(SystemExit) as stop:
            self.run_ai({'kind': 'link', 'url': 'https://intra.example.com/doc'})
        self.assertIn('要登入才能看', str(stop.exception))
        self.assertEqual(self.calls, [])

    def test_sheets_and_slides_keep_the_order_shown_and_cells_their_columns(self):
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        r = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        rels = lambda pairs: ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                              + ''.join(f'<Relationship Id="{i}" Target="{t}"/>' for i, t in pairs) + '</Relationships>')
        xlsx = self.office('排序.xlsx', {
            'xl/workbook.xml': f'<workbook {ns} {r}><sheets><sheet name="後來加的" r:id="r2"/><sheet name="原本的" r:id="r1"/></sheets></workbook>',
            'xl/_rels/workbook.xml.rels': rels([('r1', 'worksheets/sheet1.xml'), ('r2', 'worksheets/sheet2.xml')]),
            'xl/worksheets/sheet1.xml': f'<worksheet {ns}><sheetData><row><c r="A1" t="inlineStr"><is><t>a</t></is></c>'
                                        '<c r="C1"><v>3</v></c></row></sheetData></worksheet>',
            'xl/worksheets/sheet2.xml': f'<worksheet {ns}><sheetData><row><c r="B1"><v>2</v></c></row></sheetData></worksheet>'})
        a = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        pptx = self.office('排序.pptx', {
            'ppt/presentation.xml': f'<presentation {r}><sldIdLst><sldId r:id="s2"/><sldId r:id="s1"/></sldIdLst></presentation>',
            'ppt/_rels/presentation.xml.rels': rels([('s1', 'slides/slide1.xml'), ('s2', '/ppt/slides/slide2.xml')]),
            'ppt/slides/slide1.xml': f'<sld {a}><a:p><a:r><a:t>原本第一頁</a:t></a:r></a:p></sld>',
            'ppt/slides/slide2.xml': f'<sld {a}><a:p><a:r><a:t>移到最前面</a:t></a:r></a:p></sld>'})
        log = self.root / '紀錄.log'
        log.write_text('10:00 預算 12 萬', encoding='utf-8')
        seen = self.run_ai(*[{'kind': 'file', 'path': str(p)} for p in (xlsx, pptx, log)])
        self.assertEqual(seen['參考資料-1.txt'].decode().splitlines(),
                         ['## 後來加的', '\t2', '', '## 原本的', 'a\t\t3'])
        self.assertEqual(seen['參考資料-2.txt'].decode().splitlines()[:2], ['## Slide 1', '移到最前面'])
        self.assertEqual(seen['參考資料-3.txt'].decode(), '10:00 預算 12 萬')

    def test_a_link_that_needs_a_sign_in_stops_before_the_ai_starts(self):
        import references
        import urllib.error
        saved = references.urllib.request.urlopen

        def refuse(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 403, 'Forbidden', {}, None)
        references.urllib.request.urlopen = refuse
        try:
            with self.assertRaises(SystemExit) as stop:
                self.run_ai({'kind': 'link', 'url': 'https://example.com/private'})
        finally:
            references.urllib.request.urlopen = saved
        self.assertIn('要登入才能看', str(stop.exception))
        self.assertEqual(self.calls, [])

    def test_a_kind_the_ai_cannot_read_and_a_missing_file_are_refused(self):
        odd = self.root / '錄音.m4a'
        odd.write_bytes(b'\x00\x01ftypM4A')
        with self.assertRaises(SystemExit) as stop:
            self.run_ai({'kind': 'file', 'path': str(odd)})
        self.assertIn('錄音.m4a', str(stop.exception))
        with self.assertRaises(SystemExit) as stop:
            self.run_ai({'kind': 'file', 'path': str(self.root / '不見了.pdf')})
        self.assertIn('找不到「不見了.pdf」', str(stop.exception))
        self.assertEqual(self.calls, [])

    def test_requests_left_waiting_keep_their_files(self):
        src = self.root / '補充.md'
        src.write_text('預算 12 萬', encoding='utf-8')
        items = [{'kind': 'ask', 'text': '照參考資料補預算', 'refs': [{'kind': 'file', 'path': str(src)}]}]
        self.main('ask_many', str(self.job_dir), json.dumps(items, ensure_ascii=False))
        self.assertIn('參考資料-1.md', self.calls[-1]['files'])


class VoiceOff(unittest.TestCase):
    """人員: a voice that is nobody (the recording split one person in two, or a noise) can be taken off and put back
    (Vin 2026-10-19: 講者 C 是語音誤判，要有地方移除). Its lines keep their words without a speaker, nothing about it is
    remembered, and the 待確認 items about it go with it."""
    job = Flows.job

    def setUp(self):
        MeetingPeople.setUp(self)
        (self.job_dir / '逐字稿.txt').write_text('[00:01] 大家好\n[00:05] 對\n[00:09] 我們開始\n', encoding='utf-8')
        (self.job_dir / '講者.json').write_text(json.dumps({'groups': {
            'A': {'name': '', 'seconds': 300, 'sample': [1, 5]}, 'B': {'name': '', 'seconds': 200, 'sample': [9, 12]},
            'C': {'name': '', 'seconds': 40, 'sample': [5, 7]}}, 'lines': ['A', 'C', 'B'], 'fixed': {}}, ensure_ascii=False))
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['check'] = ['講者 C 只有附和，未列與會', {'text': '「HOWAN PASS」推測是台灣 PASS'}]
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))

    def tearDown(self):
        MeetingPeople.tearDown(self)

    def test_a_voice_taken_off_leaves_the_people_tab_and_its_lines_lose_the_name(self):
        minutes_app.cmd_drop_voice(self.job(), 'C')
        self.assertEqual([v['group'] for v in minutes_app.voices_view(self.job())], ['A', 'B'])
        self.assertEqual([v['group'] for v in self.outs[-1]['voices_off']], ['C'])
        self.assertEqual([(x['text'], x['who']) for x in minutes_app.transcript(self.job())],
                         [('大家好', '講者 A'), ('對', ''), ('我們開始', '講者 B')])
        self.assertEqual([c['label'] for c in self.outs[-1]['check']], ['「HOWAN PASS」推測是台灣 PASS'])
        self.assertIn('移除講者 C', ' '.join(e['text'] for e in self.job().log_entries()))
        import speakers
        self.assertNotIn('講者 C', speakers.labelled_transcript(self.job_dir))     # the AI does not see it as a person

    def test_a_voice_taken_off_can_be_put_back(self):
        minutes_app.save_speaker(self.job(), 'C', 'Ken')                  # the name the minutes gave it
        minutes_app.cmd_drop_voice(self.job(), 'C')
        self.assertNotIn('C', minutes_app.speaker_map(self.job()))
        minutes_app.cmd_drop_voice(self.job(), 'C', back=True)
        self.assertEqual([v['group'] for v in minutes_app.voices_view(self.job())], ['A', 'B', 'C'])
        self.assertEqual(self.outs[-1]['voices_off'], [])
        self.assertEqual(minutes_app.transcript(self.job())[1]['who'], '講者 C')
        self.assertEqual(minutes_app.speaker_map(self.job())['C'], 'Ken')
        self.assertIn('講者 C 只有附和，未列與會', [c['label'] for c in minutes_app.check_items(self.job())])

    def test_a_named_voice_taken_off_is_forgotten_as_that_person(self):
        import speakers
        forgot = []
        saved = speakers.forget
        speakers.forget = lambda name, tags=(), job='': forgot.append(name)
        try:
            data = json.loads((self.job_dir / '講者.json').read_text(encoding='utf-8'))
            data['groups']['C']['name'] = 'Ken'
            (self.job_dir / '講者.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            minutes_app.cmd_drop_voice(self.job(), 'C')
        finally:
            speakers.forget = saved
        self.assertEqual(forgot, ['Ken'])
        self.assertEqual(minutes_app.transcript(self.job())[1]['who'], '')

    def test_a_question_about_a_voice_goes_once_the_voice_is_named(self):
        # 講者 B 推測是主管，請補姓名 stayed under 待處理 after 講者 B was named under 人員 (Vin 2026-10-19)
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['check'] = ['講者 B 推測是主管，請補姓名', '講者 C 只有附和，未列與會']
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        data = json.loads((self.job_dir / '講者.json').read_text(encoding='utf-8'))
        data['groups']['B']['name'] = '主管（營運處處長 Pitt）'
        (self.job_dir / '講者.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        items = minutes_app.check_items(self.job())
        self.assertEqual([(c['label'], c.get('voice')) for c in items], [('講者 C 只有附和，未列與會', 'C')])

    def test_naming_a_voice_settles_its_guess_for_good(self):
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['check'] = ['講者 B 推測是 Ken', 'speaker C is probably Leo']
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        minutes_app.cmd_speaker(self.job(), 'B', 'Ken')
        self.assertIn('講者 B 推測是 Ken', self.job().state.get('confirmed', []))   # stays settled if Ken is taken off
        minutes_app.cmd_speaker(self.job(), 'C', 'Leo')
        self.assertEqual(minutes_app.check_items(self.job()), [])

    def test_the_items_about_a_removed_voice_come_back_with_it(self):
        r = json.loads((self.job_dir / 'result.json').read_text())
        r['check'] = ['講者 C 只有附和，未列與會']
        (self.job_dir / 'result.json').write_text(json.dumps(r, ensure_ascii=False))
        minutes_app.cmd_drop_voice(self.job(), 'C')
        self.assertEqual(minutes_app.check_items(self.job()), [])
        self.assertEqual(self.job().state['voices_off']['C']['aside'], ['講者 C 只有附和，未列與會'])
        minutes_app.cmd_drop_voice(self.job(), 'C', back=True)
        self.assertEqual([c['label'] for c in minutes_app.check_items(self.job())], ['講者 C 只有附和，未列與會'])

    def test_an_unknown_voice_is_refused(self):
        with self.assertRaises(SystemExit):
            minutes_app.cmd_drop_voice(self.job(), 'Z')


WINDOW = Path(__file__).resolve().parent.parent / 'recorder' / 'app'


def js_function(src: str, start: str) -> str:
    """The text of the function in app.js that begins with `start`, up to its closing brace."""
    at = src.index(start)
    depth = 0
    for j in range(src.index('{', at), len(src)):
        depth += {'{': 1, '}': -1}.get(src[j], 0)
        if depth == 0:
            return src[at:j + 1]
    raise AssertionError(start)


class QuietList(unittest.TestCase):
    """The tags are kept but not shown, and each meeting in the list reads 好好玩 FUNIT on its colour, then 已寄出 2 人;
    no time, no round mark in front (Vin 2026-10-28, prototypes/hide-tags.html)."""
    src = (WINDOW / 'app.js').read_text(encoding='utf-8')
    strings = (WINDOW / 'strings.js').read_text(encoding='utf-8')

    def test_the_tags_are_kept_but_not_shown(self):
        self.assertIn('const SHOW_TAGS = false;', self.src)
        self.assertIn('if (!SHOW_TAGS) return [];', js_function(self.src, 'function allTags'))   # no 標籤 filter
        tags = js_function(self.src, 'function renderTags')
        self.assertLess(tags.index('if (!SHOW_TAGS)'), tags.index("t('tag')"))   # 附件 and the score only
        self.assertIn("'tags'", self.src)                  # the agent's tools and the search still have them

    def test_each_meeting_shows_its_project_on_its_colour_then_who_got_it(self):
        side = js_function(self.src, 'function renderSide')
        self.assertNotIn('projectMark(j.project)', side)
        self.assertNotIn('esc(j.time)', side)
        self.assertLess(side.index('projectTag(j.project)'), side.index('listStatus(j)'))
        self.assertEqual(self.strings.count('sent_short:'), 2)          # 已寄出 2 人 in both languages

    def test_the_project_is_a_folder_on_its_colour_and_its_name_in_grey(self):
        # prototypes/project-folder-list.html (Vin 2026-10-28): only the folder keeps the colour
        tag = self.src[self.src.index('const projectTag'):]
        tag = tag[:tag.index('\n')]
        self.assertLess(tag.index('${FOLDER}'), tag.index('esc(name)'))
        self.assertIn('·', tag)
        css = (WINDOW / 'app.css').read_text(encoding='utf-8')
        self.assertIn('.ptag.p0 svg { color: var(--p0-ink); }', css)
        self.assertNotIn('.ptag.p0 { background', css)


class NameWhileTheAiWrites(unittest.TestCase):
    """人員: a voice can be named while the AI rewrites the minutes (Vin 2026-10-28: 選人那邊卡卡的). The name shows at
    once and goes in after the rewrite, one name after another in the order they were picked."""
    src = (WINDOW / 'app.js').read_text(encoding='utf-8')

    def test_the_pick_stays_open_while_the_ai_writes(self):
        people = js_function(self.src, 'function peopleHTML')
        self.assertIn('const pickBusy = S.peopleBusy || S.busy;', people)
        self.assertIn("pickBusy ? ' disabled' : ''", people)
        self.assertIn("t('people_after_ai', aiName())", people)
        choose = self.src[self.src.index('const choose = (g, name)'):]
        self.assertIn('else if (aiBusy() || peopleQueued()) nameLater(g, name);', choose[:400])
        strings = (WINDOW / 'strings.js').read_text(encoding='utf-8')
        self.assertEqual(strings.count('people_after_ai:'), 2)

    def test_a_name_sent_during_a_rewrite_waits_for_it(self):
        import fcntl
        import threading
        import time
        folder = Path(tempfile.mkdtemp(prefix='job-'))
        (folder / 'job.json').write_text('{}')
        job = minutes_app.Job(folder)
        rewrite = open(folder / '.app.lock', 'w')
        fcntl.flock(rewrite, fcntl.LOCK_EX)              # the AI's rewrite holds the meeting
        threading.Timer(0.8, lambda: (fcntl.flock(rewrite, fcntl.LOCK_UN), rewrite.close())).start()
        began = time.time()
        turn = minutes_app.wait_for_turn(job)           # what the window's 人員 pick runs through
        self.assertGreaterEqual(time.time() - began, 0.7)
        turn.close()
        shutil.rmtree(folder)

    def run_picks(self, script: str) -> dict:
        """nameLater and sendLater from app.js with a stand-in server that answers each name after a while."""
        if not shutil.which('node'):
            self.skipTest('node is not installed')
        code = '\n'.join([
            "const S = { sel: 'm1', peopleLater: {}, peopleSending: {}, editSeq: 0 };",
            'const sent = [], done = [], alerts = []; let open = 0, most = 0;',
            'const call = (cmd, a) => { open++; most = Math.max(most, open); sent.push(`${a.group}=${a.name}`);',
            "  return new Promise((ok, no) => setTimeout(() => { open--; a.name === 'Bad' ? no(new Error('busy'))",
            '    : ok({ voices: [a.group] }); }, 30)); };',
            'const peopleDone = (r) => done.push(r.voices[0]); const renderRail = () => {};',
            'const showAlert = (m) => alerts.push(m);',
            next(line for line in self.src.splitlines() if line.startswith('const peopleQueued')),
            js_function(self.src, 'function nameLater'),
            js_function(self.src, 'async function sendLater'),
            js_function(self.src, 'function namesLeft'),
            'let snap = null;', script,
            'const end = setInterval(() => { if (!peopleQueued(\'m1\')) { clearInterval(end);',
            '  console.log(JSON.stringify({ sent, done, alerts, most, left: S.peopleLater, snap })); } }, 5);',
        ])
        return json.loads(subprocess.run(['node', '-e', code], capture_output=True, text=True, check=True, timeout=10).stdout)

    def test_the_names_go_in_one_after_another(self):
        out = self.run_picks("nameLater('B', 'Mia'); nameLater('A', 'Leo'); nameLater('C', 'Bad'); nameLater('A', 'Leo');")
        self.assertEqual(out, {'sent': ['B=Mia', 'A=Leo', 'C=Bad'], 'done': ['B', 'A'], 'alerts': ['busy'], 'most': 1,
                               'left': {}, 'snap': None})

    def test_a_voice_named_again_sends_only_its_last_name(self):
        out = self.run_picks("nameLater('A', 'Leo'); nameLater('B', 'Mia'); nameLater('B', 'Lily');")
        self.assertEqual(out['sent'], ['A=Leo', 'B=Lily'])           # Mia never went: not remembered, not listed
        out = self.run_picks("nameLater('B', 'Mia'); nameLater('B', 'Lily'); nameLater('B', 'Mia');")
        self.assertEqual(out['sent'], ['B=Mia'])                     # back to the name on its way: nothing more
        out = self.run_picks("nameLater('B', 'Mia'); setTimeout(() => nameLater('B', 'Lily'), 10);")
        self.assertEqual(out['sent'], ['B=Mia', 'B=Lily'])           # changed while Mia went: Lily follows

    def test_the_names_not_sent_go_with_the_window_closing(self):
        out = self.run_picks("nameLater('A', 'Leo'); nameLater('B', 'Mia'); nameLater('A', 'Ken'); snap = namesLeft('m1');")
        self.assertEqual(out['snap'], [{'kind': 'speaker', 'group': 'A', 'name': 'Ken'},    # Leo is on its way already
                                       {'kind': 'speaker', 'group': 'B', 'name': 'Mia'}])
        src = js_function(self.src, 'window.beforeClose = async')
        self.assertIn('namesLeft(id).concat(', src)

    def test_the_server_names_a_voice_left_by_a_closed_window(self):
        job = Flows.job
        MeetingPeople.setUp(self)
        try:
            minutes_app.cmd_ask_many(job(self), json.dumps([{'kind': 'speaker', 'group': 'B', 'name': 'Mia'},
                                                            {'kind': 'speaker', 'group': 'b', 'name': 'Zed'}]))
            self.assertIn('Mia 說明：', self.md_path.read_text(encoding='utf-8'))
            self.assertNotIn('Zed', self.md_path.read_text(encoding='utf-8'))   # not a voice letter
        finally:
            MeetingPeople.tearDown(self)
