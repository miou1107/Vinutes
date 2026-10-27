"""Checks for the score of a meeting's minutes (scores.py, issue #17) that need no AI: how the AI's marks become
points, what is kept of its answer, the two kinds side by side in 評分.json, minutes sent as written, and what the
window gets.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault('VINUTES_LANG', 'zh-TW')
HOME = os.environ.setdefault('MINUTES_HOME', tempfile.mkdtemp(prefix='scores-test-'))
os.environ.setdefault('VINUTES_LOG_DIR', os.path.join(HOME, 'logs'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import minutes_app  # noqa: E402
import scores  # noqa: E402

MINUTES = """# 週會

## 一、會議基本資訊

- 主持人：[__]
- 與會人員：Amy、講者 B

## 二、行動方案

| 編號 | 追蹤事項 | 負責 | 說明 |
|---|---|---|---|
| 1 | 報價單 | Ken | 時程 [__] |
"""


def marks(**counts) -> list[dict]:
    """facts=marks(basics=['supported', 'blank']) style input for tally."""
    return [{'category': c, 'status': s} for c, statuses in counts.items() for s in statuses]


class Tally(unittest.TestCase):
    def test_each_category_counts_by_its_weight(self):
        score, cats = scores.tally('check', marks(basics=['supported', 'blank'], actions=['partial', 'supported'],
                                                  people=['unsupported']))
        self.assertEqual(cats['basics'], [12, 25])           # 25 * 1/2, rounded
        self.assertEqual(cats['actions'], [15, 20])          # 20 * 1.5/2
        self.assertEqual(cats['people'], [0, 20])
        self.assertEqual(cats['numbers'], [20, 20])          # no fact of it: nothing lost
        self.assertEqual(score, sum(p for p, _ in cats.values()))
        self.assertEqual(score, 12 + 15 + 0 + 20 + 15)

    def test_edits_marks_are_their_own_words(self):
        _, cats = scores.tally('edits', marks(basics=['same', 'added', 'changed', 'partial']))
        self.assertEqual(cats['basics'], [9, 25])            # 25 * 1.5/4
        self.assertEqual(scores.tally('edits', marks(basics=['supported']))[1]['basics'], [0, 25])

    def test_marks_in_other_case_still_count(self):
        self.assertEqual(scores.tally('check', marks(basics=[' Supported ']))[1]['basics'], [25, 25])
        self.assertEqual(scores.tally('check', [{'category': 'People', 'status': 'blank'}])[1]['people'], [0, 20])

    def test_what_the_user_deleted_costs_points(self):
        _, cats = scores.tally('edits', marks(decisions=['same', 'removed']))
        self.assertEqual(cats['decisions'], [8, 15])
        self.assertIn('"removed"', scores.prompt('edits', 'zh-TW'))

    def test_nothing_marked_is_100(self):
        self.assertEqual(scores.tally('edits', [])[0], 100)

    def test_odd_answers_lose_nothing_extra(self):
        score, _ = scores.tally('check', [None, 'x', {'category': 'nope', 'status': 'blank'}])
        self.assertEqual(score, 100)


class Answer(unittest.TestCase):
    def test_json_in_the_middle_of_text(self):
        got = scores.answer_of('好的，結果如下：\n{"facts": [{"category": "basics", "status": "blank"}], "lost": []}\n完成')
        self.assertEqual(got['facts'][0]['status'], 'blank')

    def test_no_facts_is_no_answer(self):
        for text in ('沒有結果', '{"lost": []}', '[1, 2]', '{"facts": []}',
                     '{"facts": [{"category": "其他", "status": "blank"}]}'):
            with self.assertRaises(ValueError):
                scores.answer_of(text)

    def test_braces_before_the_answer(self):
        text = '我讀了 {紀錄.md} 和 {逐字稿.txt}。\n{"facts": [{"category": "actions", "status": "blank"}], "lost": []}'
        self.assertEqual(scores.answer_of(text)['facts'][0]['category'], 'actions')

    def test_lost_items_are_cut_and_capped(self):
        lost = scores.lost_items([{'category': 'people', 'what': '講者 B\n沒有名字', 'fix': 'x' * 200, 'quote': '講者 B'},
                                  {'category': 'bad', 'what': '待辦沒寫期限'}, {'what': ''}, 'text', None]
                                 + [{'what': f'第 {i} 項'} for i in range(10)])
        self.assertEqual(lost[0], {'category': 'people', 'what': '講者 B 沒有名字', 'fix': 'x' * 60, 'quote': '講者 B'})
        self.assertEqual(lost[1]['category'], '')
        self.assertEqual(len(lost), scores.MOST_LOST)

    def test_prompts_are_whole(self):
        for kind in ('check', 'edits'):
            for lang in ('zh-TW', 'en'):
                text = scores.prompt(kind, lang)
                self.assertNotIn('{language}', text)
                self.assertNotIn('{{', text)
                self.assertIn('{"facts": [{"category": "basics"', text)
        self.assertIn('到人員分頁替講者取名', scores.prompt('check', 'zh-TW'))
        self.assertIn('Name the voice in the People tab', scores.prompt('edits', 'en'))


class Job(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='job-', dir=HOME))
        (self.dir / 'job.json').write_text('{}', encoding='utf-8')
        self.md = self.dir / '週會_會議紀錄.md'
        self.md.write_text(MINUTES, encoding='utf-8')
        (self.dir / 'result.json').write_text(json.dumps({'minutes_md': str(self.md), 'title': '週會'}),
                                              encoding='utf-8')
        (self.dir / 'status.json').write_text('{"step": "done"}', encoding='utf-8')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def saved(self) -> dict:
        return json.loads((self.dir / scores.FILE).read_text(encoding='utf-8'))


class Saving(Job):
    def test_both_kinds_are_kept_whichever_finishes_last(self):
        scores.save(self.dir, 'edits', scores.entry('edits', {}, ''))
        scores.save(self.dir, 'check', scores.entry('check', {'facts': marks(basics=['blank'])}, 'Claude'))
        data = self.saved()
        self.assertEqual(data['edits']['score'], 100)
        self.assertEqual(data['check']['score'], 75)
        self.assertEqual(data['check']['ai'], 'Claude')


class Edits(Job):
    def test_sent_as_written_is_100_without_the_ai(self):
        (self.dir / scores.ORIGINAL).write_text(MINUTES + '\n\n', encoding='utf-8')
        with mock.patch('auto_minutes.latest'), mock.patch.object(scores, 'ask') as ask:
            scores.edits(self.dir)
        ask.assert_not_called()
        self.assertEqual(self.saved()['edits'], {**self.saved()['edits'], 'score': 100, 'lost': []})

    def test_edited_minutes_are_compared_by_the_ai(self):
        (self.dir / scores.ORIGINAL).write_text(MINUTES.replace('Ken', 'Kenny'), encoding='utf-8')
        answer = {'facts': marks(people=['partial', 'same']),
                  'lost': [{'category': 'people', 'what': '講者 C 寫成 Kenny，你改成 Ken', 'fix': '下次會照你改的寫', 'quote': 'Ken'}]}
        with mock.patch('auto_minutes.latest'), mock.patch.object(scores, 'ask', return_value=(answer, 'Claude')) as ask:
            scores.edits(self.dir)
        files = ask.call_args.args[2]
        self.assertIn('Kenny', files['原稿.md'])
        self.assertNotIn('Kenny', files['定稿.md'])
        self.assertEqual(self.saved()['edits']['score'], 100 - 5)

    def test_no_ai_copy_no_score(self):
        with mock.patch('auto_minutes.latest'), mock.patch.object(scores, 'ask') as ask:
            scores.edits(self.dir)
        ask.assert_not_called()
        self.assertFalse((self.dir / scores.FILE).exists())

    def test_doc_not_reachable_still_scores(self):
        (self.dir / scores.ORIGINAL).write_text(MINUTES, encoding='utf-8')
        with mock.patch('auto_minutes.latest', side_effect=SystemExit('offline')):
            scores.edits(self.dir)
        self.assertEqual(self.saved()['edits']['score'], 100)


class Failing(Job):
    def test_an_ai_failure_leaves_no_score_and_says_why(self):
        (self.dir / scores.ORIGINAL).write_text(MINUTES.replace('Ken', 'Kenny'), encoding='utf-8')
        with mock.patch.object(sys, 'argv', ['scores.py', 'edits', str(self.dir)]), \
                mock.patch('auto_minutes.latest'), mock.patch.object(scores, 'ask', side_effect=ValueError('no JSON')):
            scores.main()
        self.assertFalse((self.dir / scores.FILE).exists())
        self.assertIn('edits failed: ValueError: no JSON', (self.dir / 'log.txt').read_text(encoding='utf-8'))

    def test_the_ai_folder_is_gone_after_asking(self):
        done = subprocess.CompletedProcess([], 0, stdout='{"facts": [{"category": "basics", "status": "blank"}]}', stderr='')
        with mock.patch('ai_runner.run', return_value=done) as run, mock.patch('ai_runner.name', return_value='Claude'):
            answer, ai = scores.ask(self.dir, 'check', {'紀錄.md': MINUTES})
        self.assertEqual((len(answer['facts']), ai), (1, 'Claude'))
        self.assertTrue(run.call_args.kwargs['read_only'])
        self.assertEqual(run.call_args.args[1].name, '評分-check')
        self.assertFalse(any(self.dir.glob(scores.WORK + '*')))

    def test_check_and_edits_ask_in_folders_of_their_own(self):
        seen = {}

        def answer(prompt, work, **kw):
            seen[work.name] = sorted(f.name for f in work.iterdir())
            other = work.with_name('評分-edits' if work.name == '評分-check' else '評分-check')
            if other.name not in seen:                 # the other kind starts while this one is still asking
                scores.ask(self.dir, 'edits' if work.name == '評分-check' else 'check', {'x.md': 'x'})
            self.assertTrue(work.is_dir())             # ... and has not wiped this one's files
            return subprocess.CompletedProcess([], 0, stdout='{"facts": [{"category": "basics", "status": "same"}]}', stderr='')
        with mock.patch('ai_runner.run', side_effect=answer), mock.patch('ai_runner.name', return_value='Claude'):
            scores.ask(self.dir, 'check', {'紀錄.md': MINUTES})
        self.assertEqual(seen['評分-check'], ['紀錄.md'])
        self.assertEqual(seen['評分-edits'], ['x.md'])

    def test_claude_gets_read_alone_and_codex_a_read_only_sandbox(self):
        import ai_runner
        cmd, _ = ai_runner.command('claude', 'claude', 'p', self.dir, False, read_only=True)
        self.assertEqual(cmd[cmd.index('--tools') + 1], 'Read')
        cmd, _ = ai_runner.command('codex', 'codex', 'p', self.dir, False, read_only=True)
        self.assertEqual(cmd[cmd.index('--sandbox') + 1], 'read-only')
        cmd, _ = ai_runner.command('claude', 'claude', 'p', self.dir, False)
        self.assertEqual(cmd[cmd.index('--tools') + 1], 'Read,Write,Edit')     # the other runs as before


class Starting(Job):
    def test_a_start_that_fails_stops_nothing(self):
        with mock.patch('subprocess.Popen', side_effect=OSError('no more processes')):
            scores.start(self.dir, 'check')            # returns: the minutes are published, the mail was sent

    def test_a_new_write_up_drops_the_old_score(self):
        scores.save(self.dir, 'check', scores.entry('check', {'facts': marks(basics=['blank'])}, 'Claude'))
        scores.keep_original(self.dir, self.md)
        self.assertFalse((self.dir / scores.FILE).exists())
        self.assertEqual((self.dir / scores.ORIGINAL).read_text(encoding='utf-8'), MINUTES)

    def test_a_copy_that_fails_stops_nothing(self):
        scores.keep_original(self.dir, self.dir / 'gone.md')
        self.assertFalse((self.dir / scores.ORIGINAL).exists())


class Window(Job):
    def test_no_score_yet(self):
        self.assertIsNone(minutes_app.score_view(minutes_app.Job(self.dir), MINUTES))

    def test_edits_win_over_check_once_there(self):
        scores.save(self.dir, 'check', scores.entry('check', {'facts': marks(basics=['blank']), 'lost': [
            {'category': 'people', 'what': '講者 B 沒有名字', 'fix': '到人員分頁替講者取名', 'quote': '講者 B'}]}, 'Claude'))
        view = minutes_app.score_view(minutes_app.Job(self.dir), MINUTES)
        self.assertEqual(view['kind'], 'check')
        self.assertEqual(view['score'], 75)
        self.assertEqual(view['categories'][0], ['basics', 0, 25])
        self.assertEqual([c[0] for c in view['categories']], list(scores.CATEGORIES))
        self.assertEqual(view['lost'], [{'what': '講者 B 沒有名字', 'fix': '到人員分頁替講者取名', 'find': '講者 B'}])
        scores.save(self.dir, 'edits', scores.entry('edits', {}, ''))
        view = minutes_app.score_view(minutes_app.Job(self.dir), MINUTES)
        self.assertEqual((view['kind'], view['score'], view['lost']), ('edits', 100, []))

    def test_a_quote_the_minutes_lack_finds_nothing(self):
        scores.save(self.dir, 'check', scores.entry('check', {'facts': [], 'lost': [
            {'what': '下次會議沒寫日期', 'quote': '下次會議：11/03'}]}, 'Claude'))
        self.assertEqual(minutes_app.score_view(minutes_app.Job(self.dir), MINUTES)['lost'][0]['find'], '')

    def test_part_of_a_quote_finds_nothing(self):
        scores.save(self.dir, 'check', scores.entry('check', {'facts': [], 'lost': [
            {'what': '講者 C 沒有名字', 'quote': '講者 C'}]}, 'Claude'))
        self.assertEqual(minutes_app.score_view(minutes_app.Job(self.dir), MINUTES)['lost'][0]['find'], '')

    def test_a_damaged_file_shows_no_score(self):
        for text in ('{"check": [', '{"check": {"score": "x"}}', '{"check": {"score": 1, "categories": {"basics": ["<b>", 25]}}}'):
            (self.dir / scores.FILE).write_text(text, encoding='utf-8')
            self.assertIsNone(minutes_app.score_view(minutes_app.Job(self.dir), MINUTES))

    def test_a_quote_copied_with_markdown_still_finds(self):
        scores.save(self.dir, 'check', scores.entry('check', {'facts': [], 'lost': [
            {'what': '負責人', 'quote': '| 報價單 |'}, {'what': '講者', 'quote': '**講者 B**'}]}, 'Claude'))
        lost = minutes_app.score_view(minutes_app.Job(self.dir), MINUTES)['lost']
        self.assertEqual([x['find'] for x in lost], ['報價單', '講者 B'])


if __name__ == '__main__':
    unittest.main()
