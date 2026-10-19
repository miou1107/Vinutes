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


class Answer:
    """What urllib.request.urlopen hands back, for the four places that call Google."""

    def __init__(self, body: bytes = b'{}'):
        self.body = body

    def read(self, *a):
        return self.body

    def getheader(self, name, default=None):
        return default

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class GoogleCalls(Ledger):
    """Every place that calls Google counts the request, and how much it uploaded to Drive."""

    def setUp(self):
        super().setUp()
        import urllib.request
        self.urllib = urllib.request
        self.saved_open = urllib.request.urlopen
        self.sent = []

        def answer(req, *a, **kw):
            self.sent.append(req.full_url)
            return Answer()
        urllib.request.urlopen = answer

    def tearDown(self):
        self.urllib.urlopen = self.saved_open
        super().tearDown()

    def test_the_docs_and_drive_calls_are_counted(self):
        import attachments
        import doc_sync
        doc_sync.AUTH['Authorization'] = 'Bearer test'
        try:
            doc_sync.call('https://docs.googleapis.com/v1/documents/abc')
            attachments.call('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart', body=b'x' * 300,
                             ctype='multipart/related')
        finally:
            doc_sync.AUTH.clear()
        self.assertEqual(usage.COUNTS, {'docs': [1, 0], 'drive': [1, 300]})

    def test_the_publish_and_mail_calls_are_counted(self):
        import md_to_gdoc
        import workspace
        md_to_gdoc.call('https://www.googleapis.com/drive/v3/files?fields=id', body=b'{"name": "x"}', method='POST',
                        headers={'Content-Type': 'application/json'})
        workspace.call('https://gmail.googleapis.com/gmail/v1/users/me/profile')
        self.assertEqual(usage.COUNTS, {'drive': [1, 13], 'gmail': [1, 0]})


class TranscribeAndMail(Ledger):
    """auto_minutes counts the transcript (seconds and minutes of audio) and each mail sent with its recipients."""

    def setUp(self):
        super().setUp()
        import auto_minutes
        self.am = auto_minutes
        self.saved_script = auto_minutes.script

    def tearDown(self):
        self.am.script = self.saved_script
        super().tearDown()

    def test_a_transcript_is_counted_with_the_length_of_the_recording(self):
        import subprocess
        job = self.meeting('20261019-105319')
        (job / '錄音.m4a').write_bytes(b'audio')
        os.environ['VINUTES_MEETING'] = job.name

        def script(name, *args, **kw):
            if name == 'transcribe.py':
                (job / '逐字稿.txt').write_text('[00:01] 大家好\n', encoding='utf-8')
                return subprocess.CompletedProcess([], 0, f'TRANSCRIPT {job}/逐字稿.txt (878 lines, language zh, '
                                                          'audio 40:19, took 151s)\n', '')
            return subprocess.CompletedProcess([], 0, '', '')
        self.am.script = script
        self.am.transcribe(job, {'audio': '錄音.m4a', 'started': '2026-10-19T10:53:19+08:00'})
        [line] = [e for e in usage.events(usage.now().strftime('%Y-%m')) if e['kind'] == 'transcribe']
        self.assertEqual((line['meeting'], line['audio']), ('20261019-105319', 2419))
        self.assertGreaterEqual(line['s'], 0)

    def test_a_mail_sent_is_counted_with_its_recipients(self):
        import subprocess
        job = self.meeting('20261019-170440')
        minutes = self.root / '週會_會議紀錄.md'
        minutes.write_text('# 週會\n', encoding='utf-8')
        (job / 'result.json').write_text(json.dumps({
            'title': '週會', 'minutes_md': str(minutes), 'doc_url': 'https://docs.google.com/document/d/' + 'D' * 30,
            'mail': {'to': ['amy@example.com', 'ken@example.com'], 'subject': '週會紀錄'}}))
        (job / self.am.BODY).write_text('會議紀錄如連結。', encoding='utf-8')
        os.environ['VINUTES_MEETING'] = job.name
        self.am.script = lambda name, *args, **kw: subprocess.CompletedProcess(
            [], 0, '確認碼: abc123\nSENT 18f0 | From: me | To: amy\n', '')
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):         # send prints what it sent, for the app
            self.am.send(job, None, None, 'gdoc', False, 'abc123')
        [line] = [e for e in usage.events(usage.now().strftime('%Y-%m')) if e['kind'] == 'mail']
        self.assertEqual((line['meeting'], line['to']), ('20261019-170440', 2))


OLD_LOG = """[16:10:00] TRANSCRIPT /x/逐字稿.txt (500 lines, language zh, audio 38:12, took 120s)
[16:10:00] transcribed in 122s
[16:10:40] SPEAKERS A 600s, B 400s (36s)
[16:11:00] claude in /x/整理
The minutes are in 會議紀錄.md.
[16:13:18] claude exited 0
[16:20:05] ask 主持人是 Amy: exit 0
OK
[09:15:30] ask formal: exit 1
Claude AI usage limit reached|1760000000
"""
OLD_SCRIPTS_LOG = """[2026-10-16T16:19:50.000+08:00] minutes_app[111] start ask 20261016-153005
[2026-10-16T16:19:55.000+08:00] minutes_app[999] start refresh 20261016-153005
[2026-10-16T16:20:06.100+08:00] minutes_app[111] end ok, 16.1 s
[2026-10-17T09:15:00.000+08:00] minutes_app[222] start quick 20261016-153005
[2026-10-17T09:15:31.000+08:00] minutes_app[222] end failed, 31.0 s: quick 20261016-153005: Claude 用量已經用完
"""


class Fill(Ledger):
    """Meetings recorded before the record began are filled in once from their logs: counts and seconds, never
    tokens or Google requests, and nothing written after the record began."""

    def setUp(self):
        super().setUp()
        self.logs = self.root / 'logs'
        self.logs.mkdir()
        (self.logs / 'scripts.log').write_text(OLD_SCRIPTS_LOG, encoding='utf-8')
        self.saved_logs = os.environ.get('VINUTES_LOG_DIR')
        os.environ['VINUTES_LOG_DIR'] = str(self.logs)

    def tearDown(self):
        os.environ['VINUTES_LOG_DIR'] = self.saved_logs
        super().tearDown()

    def kinds(self, found):
        return [(e['kind'], e.get('task', '')) for e in found]

    def test_an_old_meeting_is_filled_in_from_its_log(self):
        self.meeting('20261016-153005', project='春季活動', log=OLD_LOG)
        usage.begin()
        found = usage.fill()
        self.assertEqual(self.kinds(found), [('transcribe', ''), ('speakers', ''), ('ai', 'write'), ('ai', 'edit'),
                                             ('ai', 'edit')])
        transcribe, speakers, write, ask, formal = found
        self.assertEqual((transcribe['audio'], transcribe['s'], transcribe['at'][:10]), (2292, 120, '2026-10-16'))
        self.assertEqual(speakers['s'], 36)
        self.assertEqual((write['ai'], write['s'], write['ok']), ('claude', 138, True))
        self.assertEqual((ask['s'], ask['ok'], ask['at'][:19]), (16.1, True, '2026-10-16T16:20:05'))
        self.assertEqual((formal['s'], formal['ok'], formal['at'][:10]), (31.0, False, '2026-10-17'))   # after midnight
        self.assertTrue(all(e['filled'] and e['meeting'] == '20261016-153005' and e['project'] == '春季活動'
                            and 'tokens' not in e for e in found))

    def test_what_the_log_got_after_the_record_began_is_not_filled_in(self):
        d = self.meeting('20261016-153005', log=OLD_LOG)
        usage.begin()
        with (d / 'log.txt').open('a', encoding='utf-8') as f:
            f.write('[10:00:00] ask 改短一點: exit 0\n')           # counted live by the new code
        self.assertEqual(len([e for e in usage.fill() if e['kind'] == 'ai']), 3)

    def test_a_mail_sent_before_is_filled_in(self):
        d = self.meeting('20261016-153005', log='')
        (d / 'result.json').write_text(json.dumps({'sent_at': '2026-10-16T17:02:11',
                                                   'mail': {'to': ['a@example.com', 'b@example.com', 'c@example.com']}}))
        usage.begin()
        [mail] = [e for e in usage.fill() if e['kind'] == 'mail']
        self.assertEqual((mail['to'], mail['at'][:16]), (3, '2026-10-16T17:02'))

    def test_a_meeting_whose_log_never_named_its_length_gets_it_from_its_times(self):
        d = self.meeting('20261014-103500', log='[10:50:00] claude in /x/整理\n[10:51:00] claude exited 0\n')
        (d / 'job.json').write_text(json.dumps({'started': '2026-10-14T10:35:00+08:00', 'ended': '2026-10-14T10:45:30+08:00',
                                                'paused_seconds': 30}))
        usage.begin()
        [transcribe] = [e for e in usage.fill() if e['kind'] == 'transcribe']
        self.assertEqual((transcribe['audio'], transcribe['at'][:16]), (600, '2026-10-14T10:35'))
        self.assertNotIn('s', transcribe)

    def test_the_fill_in_is_done_once(self):
        d = self.meeting('20261016-153005', log=OLD_LOG)
        usage.begin()
        first = usage.fill()
        (d / 'log.txt').write_text('')
        self.assertEqual(usage.fill(), first)
        self.assertEqual(usage.events('2026-10', 'filled.jsonl'), first)

    def test_a_meeting_recorded_after_the_record_began_is_not_filled_in(self):
        usage.begin()
        self.meeting('20261020-090000', log=OLD_LOG)
        self.assertEqual(usage.fill(), [])


if __name__ == '__main__':
    unittest.main()
