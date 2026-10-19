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


CLAUDE_SAID = ('{"type":"result","subtype":"success","is_error":false,"result":"OK","total_cost_usd":0.031352,'
               '"usage":{"input_tokens":2,"cache_creation_input_tokens":3908,"cache_read_input_tokens":120,'
               '"output_tokens":4}}\n')
CODEX_SAID = '\n'.join(json.dumps(x) for x in [
    {'type': 'thread.started', 'thread_id': 't'},
    {'type': 'turn.started'},
    {'type': 'item.completed', 'item': {'id': 'item_1', 'type': 'agent_message', 'text': 'Changed the chair.'}},
    {'type': 'turn.completed', 'usage': {'input_tokens': 100, 'cached_input_tokens': 40, 'output_tokens': 7}}]) + '\n'
CODEX_FAILED = '\n'.join(json.dumps(x) for x in [
    {'type': 'turn.started'},
    {'type': 'error', 'message': "The 'gpt-5.5' model is not supported when using Codex with a ChatGPT account."},
    {'type': 'turn.failed', 'error': {'message': 'stream error'}}]) + '\n'
AGY_SAID = ('{"conversation_id":"c","status":"SUCCESS","response":"OK\\n","duration_seconds":5.3,"num_turns":1,'
            '"usage":{"input_tokens":20239,"output_tokens":25,"thinking_tokens":20,"cache_read_tokens":0,'
            '"total_tokens":20264}}\n')


class AiReport(unittest.TestCase):
    """What each AI prints when asked for a report (the shapes seen 2026-10-19): the answer and the tokens."""

    def test_claude_gives_its_answer_and_tokens(self):
        import ai_runner
        self.assertEqual(ai_runner.read_report('claude', CLAUDE_SAID), ('OK', {'in': 3910, 'cached': 120, 'out': 4}))

    def test_codex_gives_its_messages_and_tokens(self):
        import ai_runner
        self.assertEqual(ai_runner.read_report('codex', CODEX_SAID),
                         ('Changed the chair.', {'in': 60, 'cached': 40, 'out': 7}))

    def test_a_codex_error_keeps_the_words_the_user_is_told_about(self):
        import ai_runner
        text, tokens = ai_runner.read_report('codex', CODEX_FAILED)
        self.assertIn('not supported when using Codex with a ChatGPT account', text)
        self.assertIsNone(tokens)

    def test_antigravity_gives_its_answer_and_tokens(self):
        import ai_runner
        self.assertEqual(ai_runner.read_report('antigravity', AGY_SAID), ('OK\n', {'in': 20239, 'cached': 0, 'out': 25}))

    def test_output_that_is_not_a_report_passes_through(self):
        import ai_runner
        for key in ('claude', 'codex', 'antigravity'):
            self.assertEqual(ai_runner.read_report(key, 'Claude AI usage limit reached|1760000000\n'),
                             ('Claude AI usage limit reached|1760000000\n', None))

    def test_a_line_printed_before_the_report_is_kept(self):
        import ai_runner
        self.assertEqual(ai_runner.read_report('claude', 'Warning: slow disk\n' + CLAUDE_SAID),
                         ('Warning: slow disk\nOK', {'in': 3910, 'cached': 120, 'out': 4}))

    def test_each_ai_is_asked_for_its_report(self):
        import ai_runner
        claude = ai_runner.report_flags('claude', ['claude', '-p', 'do it', '--tools', 'Read'])
        self.assertEqual(claude[-2:], ['--output-format', 'json'])
        codex = ai_runner.report_flags('codex', ['codex', 'exec', '-C', '/f', 'do it'])
        self.assertEqual(codex[-2:], ['--json', 'do it'])                # the prompt stays last
        agy = ai_runner.report_flags('antigravity', ['/usr/bin/sandbox-exec', '-f', 'p', 'agy', '-p', 'do it'])
        self.assertEqual(agy[-2:], ['--output-format', 'json'])


class AiRunCounted(Ledger):
    """ai_runner.run with a stand-in for the AI's command: the run is counted, the caller reads plain text."""

    def fake(self, prints: str, code: int = 0) -> str:
        exe = self.root / 'claude'
        exe.write_text(f'#!/bin/sh\ncat <<\'EOF\'\n{prints}EOF\nexit {code}\n')
        exe.chmod(0o755)
        return str(exe)

    def test_a_run_is_counted_and_the_caller_gets_the_answer(self):
        import ai_runner
        saved = ai_runner.find
        ai_runner.find = lambda key=None: self.fake(CLAUDE_SAID)
        try:
            folder = self.root / 'work'
            folder.mkdir()
            done = ai_runner.run('Reply OK', folder, write=False, timeout=30, env=dict(os.environ), key='claude',
                                 task='edit')
        finally:
            ai_runner.find = saved
        self.assertEqual(done.stdout, 'OK')
        [line] = usage.events(usage.now().strftime('%Y-%m'))
        self.assertEqual((line['kind'], line['task'], line['ai'], line['ok']), ('ai', 'edit', 'claude', True))
        self.assertEqual(line['tokens'], {'in': 3910, 'cached': 120, 'out': 4})

    def test_a_run_without_a_task_is_not_counted(self):
        import ai_runner
        saved = ai_runner.find
        ai_runner.find = lambda key=None: self.fake(CLAUDE_SAID)
        try:
            folder = self.root / 'work'
            folder.mkdir()
            ai_runner.run('Reply OK', folder, write=False, timeout=30, env=dict(os.environ), key='claude')
        finally:
            ai_runner.find = saved
        self.assertEqual(usage.events(usage.now().strftime('%Y-%m')), [])


class WriteUpLog(unittest.TestCase):
    """auto_minutes.write_minutes: log.txt gets the AI's words as plain text, and a limit becomes the message the
    user acts on, as before the AI was asked for a report."""

    def test_the_ai_words_go_to_the_log_and_a_limit_is_told_in_plain_words(self):
        import subprocess
        import ai_runner
        import auto_minutes
        root = Path(tempfile.mkdtemp(prefix='write-'))
        job, work, folder = root / 'job', root / 'work', root / 'minutes'
        for d in (job, work, folder):
            d.mkdir()
        saved = ai_runner.run, auto_minutes.prompt
        ai_runner.run = lambda *a, **kw: subprocess.CompletedProcess([], 1, "You've hit your usage limit · resets 3pm", '')
        auto_minutes.prompt = lambda *a: 'write the minutes'
        try:
            with self.assertRaises(auto_minutes.Failed) as said:
                auto_minutes.write_minutes(job, work, {}, folder)
        finally:
            ai_runner.run, auto_minutes.prompt = saved
            log = (job / 'log.txt').read_text(encoding='utf-8')
            shutil.rmtree(root, ignore_errors=True)
        self.assertIn("You've hit your usage limit · resets 3pm\n", log)
        self.assertIn('點', str(said.exception))                 # 「…才會恢復」 with the hour, in the app's words


if __name__ == '__main__':
    unittest.main()
