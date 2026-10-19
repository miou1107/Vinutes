"""Checks for scripts/usage.py: what each meeting used (AI, Google, mail, audio, disk), the record of it, the
one-time fill-in from the logs of meetings recorded before the record existed, and the month the window shows.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('VINUTES_LANG', 'zh-TW')
os.environ.setdefault('MINUTES_HOME', tempfile.mkdtemp(prefix='minutes-test-'))
os.environ.setdefault('VINUTES_LOG_DIR', os.path.join(os.environ['MINUTES_HOME'], 'logs'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import usage  # noqa: E402


class Ledger(unittest.TestCase):
    """Each test gets its own usage folder and recordings, and no meeting in the environment."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='usage-'))
        self.saved = usage.FOLDER, usage.RECORDINGS, os.environ.pop('VINUTES_MEETING', None)
        usage.FOLDER = self.root / 'usage'
        usage.RECORDINGS = self.root / 'recordings'
        usage.RECORDINGS.mkdir()
        usage.COUNTS.clear()

    def tearDown(self):
        usage.FOLDER, usage.RECORDINGS, meeting = self.saved
        if meeting is not None:
            os.environ['VINUTES_MEETING'] = meeting
        else:
            os.environ.pop('VINUTES_MEETING', None)
        usage.COUNTS.clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def meeting(self, mid: str, project: str = '', mine: str | None = None, log: str = '') -> Path:
        d = usage.RECORDINGS / mid
        d.mkdir()
        (d / 'job.json').write_text(json.dumps({'started': f'{mid[:4]}-{mid[4:6]}-{mid[6:8]}T{mid[9:11]}:{mid[11:13]}:00+08:00'}))
        (d / 'result.json').write_text(json.dumps({'project': project}))
        if mine is not None:
            (d / '分類.json').write_text(json.dumps({'project': mine}))
        if log:
            (d / 'log.txt').write_text(log, encoding='utf-8')
        return d


class Record(Ledger):
    def test_a_record_comes_back_from_its_month(self):
        usage.record('mail', to=3)
        month = usage.now().strftime('%Y-%m')
        [line] = usage.events(month)
        self.assertEqual(line['kind'], 'mail')
        self.assertEqual(line['to'], 3)
        self.assertEqual(line['meeting'], '')

    def test_a_broken_line_is_skipped_and_the_rest_still_counts(self):
        usage.record('mail', to=1)
        month = usage.now().strftime('%Y-%m')
        with (usage.FOLDER / f'{month}.jsonl').open('a', encoding='utf-8') as f:
            f.write('{"kind": "mail", "to"\n')                 # a process stopped halfway through its line
        usage.record('mail', to=2)
        self.assertEqual([e['to'] for e in usage.events(month)], [1, 2])

    def test_each_record_names_the_meeting_and_the_project_it_has_now(self):
        self.meeting('20261019-105319', project='官網改版', mine='春季活動')
        os.environ['VINUTES_MEETING'] = '20261019-105319'
        usage.record('mail', to=1)
        [line] = usage.events(usage.now().strftime('%Y-%m'))
        self.assertEqual(line['meeting'], '20261019-105319')
        self.assertEqual(line['project'], '春季活動')            # what the user set wins over what the AI named

    def test_a_meeting_word_that_is_not_a_meeting_folder_is_ignored(self):
        os.environ['VINUTES_MEETING'] = '../../etc'
        usage.record('mail', to=1)
        [line] = usage.events(usage.now().strftime('%Y-%m'))
        self.assertEqual(line['meeting'], '')

    def test_nothing_is_raised_when_the_record_cannot_be_written(self):
        usage.FOLDER = self.root / 'not-a-folder'
        usage.FOLDER.write_text('a file where the folder should be')
        usage.record('mail', to=1)                               # the meeting's work goes on


class Google(Ledger):
    def test_requests_are_written_once_per_api_when_the_process_ends(self):
        for _ in range(3):
            usage.google('https://docs.googleapis.com/v1/documents/abc')
        usage.google('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart', sent=2048)
        usage.google('https://gmail.googleapis.com/gmail/v1/users/me/messages/send')
        usage.google('https://www.googleapis.com/calendar/v3/users/me/calendarList')
        usage.flush()
        usage.flush()                                            # a second flush has nothing left to write
        lines = {e['api']: e for e in usage.events(usage.now().strftime('%Y-%m'))}
        self.assertEqual(sorted(lines), ['calendar', 'docs', 'drive', 'gmail'])
        self.assertEqual(lines['docs']['n'], 3)
        self.assertEqual(lines['drive']['bytes'], 2048)
        self.assertNotIn('bytes', lines['docs'])


class AiRun(Ledger):
    def test_a_run_stopped_by_the_usage_limit_is_marked(self):
        usage.ai_run('edit', 'claude', 12.34, 1, None, "You've hit your usage limit · resets 3pm (Asia/Taipei)")
        [line] = usage.events(usage.now().strftime('%Y-%m'))
        self.assertEqual((line['task'], line['ai'], line['s'], line['ok'], line['limit']), ('edit', 'claude', 12.3, False, True))
        self.assertNotIn('tokens', line)

    def test_a_finished_run_keeps_its_tokens(self):
        usage.ai_run('write', 'claude', 137, 0, {'in': 30000, 'cached': 120000, 'out': 4000}, 'OK')
        [line] = usage.events(usage.now().strftime('%Y-%m'))
        self.assertEqual(line['tokens'], {'in': 30000, 'cached': 120000, 'out': 4000})
        self.assertFalse(line['limit'])

    def test_a_failure_that_is_not_the_limit_is_not_marked(self):
        usage.ai_run('edit', 'codex', 3, 1, None, 'not logged in')
        [line] = usage.events(usage.now().strftime('%Y-%m'))
        self.assertFalse(line['limit'])


class Begin(Ledger):
    def test_begin_keeps_how_long_each_meeting_log_was_and_never_changes_it(self):
        self.meeting('20261014-103500', log='[10:40:00] claude in x\n')
        first = usage.begin()
        self.assertEqual(first['logs'], {'20261014-103500': len('[10:40:00] claude in x\n')})
        (usage.RECORDINGS / '20261014-103500' / 'log.txt').write_text('longer now\n' * 5)
        self.assertEqual(usage.begin(), first)


if __name__ == '__main__':
    unittest.main()
