"""Transcribing in pieces while the meeting is recorded (live_transcribe.py) and reusing the pieces afterwards
(transcribe.py --pieces), with a stand-in for Whisper: the model is not installed on the test Mac.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import struct
import types
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# the same temporary home as the other test modules when they were imported first: modules already loaded keep
# the home they read at import, so a second one would make the two halves of a test disagree
os.environ.setdefault('VINUTES_LANG', 'zh-TW')
HOME = os.environ.setdefault('MINUTES_HOME', tempfile.mkdtemp(prefix='live-test-'))
os.environ.setdefault('VINUTES_LOG_DIR', os.path.join(HOME, 'logs'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import live_transcribe as live  # noqa: E402
import transcribe as tr  # noqa: E402

RATE = 16000


def tone(seconds: float, loud: float = 0.3):
    """`seconds` of a steady sound, as 16 kHz floats"""
    import numpy as np
    n = int(seconds * RATE)
    return np.sin(np.arange(n) * 2 * np.pi * 440 / RATE).astype(np.float32) * loud


def silence(seconds: float):
    import numpy as np
    return np.zeros(int(seconds * RATE), dtype=np.float32)


def pcm(audio) -> bytes:
    import numpy as np
    return (np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes()


def caf_header() -> bytes:
    """A CAF file's head for 16 kHz mono 16-bit little-endian PCM, with a data chunk whose size is -1 (still
    being written), as AVAudioFile leaves it while the app records."""
    head = b'caff' + struct.pack('>HH', 1, 0)
    desc = struct.pack('>dIIIIII', 16000.0, 0x6C70636D, 2, 2, 1, 1, 16)   # 'lpcm', little endian, 2 bytes a frame
    head += b'desc' + struct.pack('>q', len(desc)) + desc
    head += b'free' + struct.pack('>q', 4) + b'\0' * 4                     # a chunk to walk over
    head += b'data' + struct.pack('>q', -1) + struct.pack('>I', 0)        # the edit count, then the samples
    return head


def fake_whisper(audio, path_or_hf_repo='', language=None, initial_prompt='', **kw) -> dict:
    """One segment per second of audio, naming the second it covers; the language asked for, else Chinese."""
    seconds = len(audio) / RATE
    segs = [{'start': float(s), 'end': float(min(s + 1, seconds)), 'text': f'第{s}秒'} for s in range(int(seconds))]
    if seconds - int(seconds) >= 0.5:
        segs.append({'start': float(int(seconds)), 'end': seconds, 'text': f'第{int(seconds)}秒'})
    return {'text': ' '.join(s['text'] for s in segs), 'language': language or 'zh', 'segments': segs}


class Cut(unittest.TestCase):
    def test_the_cut_falls_in_the_quiet_gap(self):
        import numpy as np
        audio = np.concatenate([tone(6), silence(0.8), tone(3.2)])         # quiet from 6.0 to 6.8
        at = live.quietest_cut(audio, 4 * RATE, 8 * RATE) / RATE
        self.assertTrue(6.1 < at < 6.7, at)

    def test_without_a_gap_the_cut_is_still_inside_the_window(self):
        at = live.quietest_cut(tone(10), 4 * RATE, 8 * RATE) / RATE
        self.assertTrue(4 <= at <= 8, at)

    def test_a_stretch_too_short_to_search_cuts_at_its_end(self):
        self.assertEqual(live.quietest_cut(tone(1), 100, 200), 200)

    def test_a_window_past_the_end_of_the_audio_is_clamped(self):
        audio = tone(1)                                                     # 16000 samples, one short of a window
        at = live.quietest_cut(audio, 8000, 16001)
        self.assertTrue(8000 <= at <= 16000, at)


class CafHead(unittest.TestCase):
    def test_the_samples_start_after_the_data_chunk_header_and_edit_count(self):
        head = caf_header()
        self.assertEqual(live.caf_data_start(head), len(head))

    def test_not_a_caf_file(self):
        self.assertIsNone(live.caf_data_start(b'RIFF....WAVE'))
        self.assertIsNone(live.caf_data_start(b'caff\0\1\0\0desc'))        # cut off before any data chunk


class Pieces(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='pieces-'))

    def piece(self, n, start, end, text='x'):
        (self.folder / f'{n:04d}.json').write_text(json.dumps(
            {'start': start, 'end': end, 'language': 'zh', 'segments': [[start, end, text]]}), encoding='utf-8')

    def test_pieces_that_join_from_the_start_are_reused(self):
        self.piece(1, 0, 300.5)
        self.piece(2, 300.5, 601.2)
        self.piece(3, 601.2, 900)
        self.assertEqual([p['end'] for p in tr.pieces_in(self.folder, 1000)], [300.5, 601.2, 900])

    def test_a_gap_ends_the_run(self):
        self.piece(1, 0, 300)
        self.piece(2, 310, 600)                                             # 300-310 missing
        self.piece(3, 600, 900)
        self.assertEqual([p['end'] for p in tr.pieces_in(self.folder, 1000)], [300])

    def test_a_piece_past_the_end_of_the_audio_is_not_reused(self):
        self.piece(1, 0, 300)
        self.piece(2, 300, 600)
        self.assertEqual([p['end'] for p in tr.pieces_in(self.folder, 450)], [300])

    def test_a_broken_file_ends_the_run_there(self):
        self.piece(1, 0, 300)
        (self.folder / '0002.json').write_text('{not json', encoding='utf-8')
        self.piece(3, 600, 900)
        self.assertEqual([p['end'] for p in tr.pieces_in(self.folder, 1000)], [300])

    def test_no_folder_no_pieces(self):
        self.assertEqual(tr.pieces_in(self.folder / 'none', 1000), [])

    def test_waiting_ends_when_the_helper_on_a_piece_is_gone(self):
        (self.folder / tr.WORKING).write_text(json.dumps({'pid': 2 ** 22 + 7}), encoding='utf-8')   # no such process
        naps = []
        waited = tr.wait_for_helper(self.folder, limit=5, poll=0.01, sleep=naps.append)
        self.assertFalse((self.folder / tr.WORKING).exists())
        self.assertLess(waited, 2)
        self.assertEqual(naps, [])

    def test_a_pid_that_is_not_a_helper_is_neither_waited_for_nor_stopped(self):
        (self.folder / tr.WORKING).write_text(json.dumps({'pid': os.getpid()}), encoding='utf-8')   # this test runner
        naps = []
        tr.wait_for_helper(self.folder, limit=5, poll=0.01, sleep=naps.append)
        self.assertFalse((self.folder / tr.WORKING).exists())
        self.assertEqual(naps, [])                                        # still here: nothing was sent a signal

    def test_waiting_gives_up_after_the_limit_and_stops_the_helper(self):
        (self.folder / tr.WORKING).write_text(json.dumps({'pid': 4242}), encoding='utf-8')
        clock = [0.0]
        stopped = []
        tr.time.time, real = (lambda: clock[0]), tr.time.time
        tr.os.kill, kill = (lambda pid, sig: stopped.append((pid, sig))), tr.os.kill
        try:
            tr.wait_for_helper(self.folder, limit=3, poll=1, sleep=lambda s: clock.__setitem__(0, clock[0] + s),
                               running=lambda pid: pid == 4242)
        finally:
            tr.time.time, tr.os.kill = real, kill
        self.assertFalse((self.folder / tr.WORKING).exists())
        self.assertEqual(stopped, [(4242, tr.signal.SIGTERM)])

    def test_the_prompt_is_the_glossary_hint_for_chinese_and_nothing_for_english(self):
        self.assertTrue(tr.prompt_for('zh').startswith(tr.HINT_HEAD))
        self.assertEqual(tr.prompt_for('en'), '')


class Assemble(unittest.TestCase):
    def test_lines_and_spans_in_recording_time(self):
        lines, spans = tr.assemble([[0.0, 1.5, ' 第一句 '], [1.5, 3.0, '第一句'], [3.0, 4.0, ''], [305.2, 306.0, '第二段']],
                                   'zh', lambda s: s)
        self.assertEqual(lines, ['[00:00] 第一句', '[05:05] 第二段'])            # repeated and empty ones dropped
        self.assertEqual(spans, [[0.0, 1.5], [305.2, 306.0]])

    def test_a_segment_where_the_model_got_stuck_is_dropped(self):
        segs = [[0, 1, '通常自己發表請' + '教' * 60], [1, 2, '好的' * 12], [2, 3, '好 好 好'], [3, 4, '會議開始']]
        lines, _ = tr.assemble(segs, 'zh', lambda s: s)
        self.assertEqual(lines, ['[00:02] 好 好 好', '[00:03] 會議開始'])

    def test_a_piece_boundary_does_not_break_a_repeat_check(self):
        lines, _ = tr.assemble([[299.0, 300.0, '好'], [300.0, 301.0, '好']], 'zh', lambda s: s)
        self.assertEqual(len(lines), 1)


class Live(unittest.TestCase):
    """A recording that grows between looks, transcribed by a stand-in Whisper two seconds at a time."""

    def setUp(self):
        self.job = Path(tempfile.mkdtemp(prefix='job-'))
        (self.job / 'job.json').write_text(json.dumps({'audio': '錄音.caf', 'started': '2026-10-20T10:00:00+08:00',
                                                      'ended': None}), encoding='utf-8')
        self.file = self.job / '錄音.caf'
        self.file.write_bytes(caf_header())
        self.logged = []

    def grow(self, audio):
        with open(self.file, 'ab') as f:
            f.write(pcm(audio))

    def end(self):
        meta = json.loads((self.job / 'job.json').read_text(encoding='utf-8'))
        meta['ended'] = '2026-10-20T10:30:00+08:00'
        (self.job / 'job.json').write_text(json.dumps(meta), encoding='utf-8')

    def runner(self, **kw):
        return live.Runner(self.job, fake_whisper, detect=lambda audio, t: 'zh', log=self.logged.append,
                           piece=2.0, search=0.5, poll=0.0, **kw)

    def pieces(self):
        return [json.loads(p.read_text(encoding='utf-8')) for p in sorted((self.job / live.PIECES).glob('[0-9]*.json'))]

    def test_pieces_are_cut_in_the_quiet_and_the_helper_stops_at_the_end(self):
        import numpy as np
        # 1.8 s of talk, a 0.4 s gap, then on: the cut should land in the gap at about 2.0 s
        sound = np.concatenate([tone(1.8), silence(0.4), tone(1.8), silence(0.4), tone(1.8), silence(0.4), tone(1.0)])
        fed = [0]
        runner = self.runner()

        def feed(_):                                    # each look: one more second arrives; then the meeting ends
            if fed[0] < len(sound):
                self.grow(sound[fed[0]:fed[0] + RATE])
                fed[0] += RATE
            else:
                self.end()
        runner.sleep = feed
        done = runner.run()
        pieces = self.pieces()
        self.assertEqual(done, len(pieces))
        self.assertGreaterEqual(len(pieces), 2)
        self.assertEqual(pieces[0]['start'], 0)
        for a, b in zip(pieces, pieces[1:]):
            self.assertEqual(a['end'], b['start'])                   # end to start
        self.assertTrue(1.8 <= pieces[0]['end'] <= 2.2, pieces[0]['end'])      # inside the first gap
        self.assertEqual(pieces[0]['language'], 'zh')
        self.assertTrue(pieces[1]['segments'][0][0] >= pieces[1]['start'])    # recording time, not piece time
        self.assertFalse((self.job / live.PIECES / tr.WORKING).exists())
        self.assertIn('recording ended', self.logged[-1])

    def test_every_piece_gets_the_same_hint_as_a_whole_recording(self):
        prompts = []

        def whisper(audio, **kw):
            prompts.append(kw.get('initial_prompt', ''))
            return fake_whisper(audio, **kw)
        runner = live.Runner(self.job, whisper, detect=lambda a, t: 'zh', piece=2.0, search=0.5, poll=0.0)
        self.grow(tone(5.5))
        runner.sleep = lambda _: self.end()
        runner.run()
        self.assertEqual(len(prompts), 2)
        self.assertEqual(prompts, [tr.prompt_for('zh')] * 2)

    def test_reading_a_stretch_gives_exactly_its_samples_for_awkward_floats(self):
        self.grow(tone(700))
        runner = self.runner()
        runner.available()                                                  # finds where the samples start
        for start in (271.1, 123.7, 1497.7 / 5):                            # 271.1 * 16000 is not whole in floating point
            got = runner.read(start, start + 330.0)
            self.assertEqual(len(got), 330 * RATE, start)

    def test_stop_before_the_first_piece_writes_nothing(self):
        self.grow(tone(1))
        runner = self.runner()
        runner.sleep = lambda _: self.end()
        self.assertEqual(runner.run(), 0)
        self.assertFalse((self.job / live.PIECES).exists())

    def test_the_helper_goes_when_the_app_is_gone(self):
        runner = self.runner(parent_alive=lambda: False)
        self.assertEqual(runner.run(), 0)
        self.assertIn('app is gone', self.logged[-1])

    def test_a_missing_file_is_waited_for_then_given_up(self):
        self.file.unlink()
        clock = [0.0]
        runner = self.runner()
        runner.sleep = lambda s: clock.__setitem__(0, clock[0] + 30)
        live.time.time, real = (lambda: clock[0]), live.time.time
        try:
            self.assertEqual(runner.run(), 0)
        finally:
            live.time.time = real
        self.assertIn('giving up', self.logged[-1])

    def test_a_helper_started_again_goes_on_after_the_pieces_on_disk(self):
        self.grow(tone(5.5))
        first = self.runner()
        first.sleep = lambda _: self.end()
        first.run()
        before = self.pieces()
        meta = json.loads((self.job / 'job.json').read_text(encoding='utf-8'))
        meta['ended'] = None
        (self.job / 'job.json').write_text(json.dumps(meta), encoding='utf-8')
        self.grow(tone(3))
        again = self.runner()
        again.sleep = lambda _: self.end()
        again.run()
        after = self.pieces()
        self.assertEqual(after[:len(before)], before)                       # the old pieces untouched
        self.assertGreater(len(after), len(before))
        self.assertEqual(after[len(before)]['start'], before[-1]['end'])    # the new ones go on from there
        self.assertEqual(again.number, len(after))


class FinalRun(unittest.TestCase):
    """transcribe.py over a CAF file, reusing pieces: the stand-in Whisper is put in place of mlx_whisper."""

    def setUp(self):
        self.job = Path(tempfile.mkdtemp(prefix='final-'))
        self.file = self.job / '錄音.caf'
        self.file.write_bytes(caf_header() + pcm(tone(7)))
        # a proper CAF for afconvert (the data chunk size filled in), as the recorder leaves it after Stop
        wav = self.job / 'a.wav'
        subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', str(self.file), str(wav)],
                       capture_output=True)
        if not wav.exists():
            self.skipTest('afconvert is not here')

    def run_final(self, pieces=None, lang='zh'):
        import types
        fake = types.ModuleType('mlx_whisper')
        fake.transcribe = fake_whisper
        opencc = types.ModuleType('opencc')
        opencc.OpenCC = lambda name: types.SimpleNamespace(convert=lambda s: s)
        argv, mods = sys.argv, {k: sys.modules.get(k) for k in ('mlx_whisper', 'opencc')}
        sys.modules['mlx_whisper'], sys.modules['opencc'] = fake, opencc
        out = self.job / '逐字稿.txt'
        sys.argv = ['transcribe.py', str(self.file), str(out)] + (['--pieces', str(pieces)] if pieces else [])
        os.environ['MINUTES_MEETING_LANG'] = lang
        try:
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                tr.main()
        finally:
            sys.argv = argv
            for k, v in mods.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
            os.environ.pop('MINUTES_MEETING_LANG', None)
        return out.read_text(encoding='utf-8').splitlines(), json.loads(out.with_suffix('.json').read_text()), buf.getvalue()

    def test_without_pieces_the_whole_file_is_transcribed(self):
        lines, meta, said = self.run_final()
        self.assertEqual(len(lines), 7)
        self.assertEqual(lines[0], '[00:00] 第0秒')
        self.assertEqual(meta['language'], 'zh')
        self.assertNotIn('pieces reused', said)

    def test_with_pieces_only_the_rest_is_transcribed_and_the_lines_join(self):
        folder = self.job / '分段'
        folder.mkdir()
        (folder / '0001.json').write_text(json.dumps({'start': 0, 'end': 2.0, 'language': 'zh',
                                                      'segments': [[0, 1, '第一段一'], [1, 2, '第一段二']]}), encoding='utf-8')
        (folder / '0002.json').write_text(json.dumps({'start': 2.0, 'end': 4.0, 'language': 'zh',
                                                      'segments': [[2, 3, '第二段一'], [3, 4, '第二段二']]}), encoding='utf-8')
        lines, meta, said = self.run_final(pieces=folder)
        self.assertEqual(lines[:4], ['[00:00] 第一段一', '[00:01] 第一段二', '[00:02] 第二段一', '[00:03] 第二段二'])
        self.assertEqual(lines[4], '[00:04] 第0秒')                 # the rest, counted from where the pieces ended
        self.assertEqual(len(lines), 7)
        self.assertEqual(meta['lines'][4], [4.0, 5.0])
        self.assertIn('2 pieces reused', said)


class Qwen(unittest.TestCase):
    """Qwen3-ASR as the recogniser for Chinese meetings: chosen by the setting, used only when its files are here,
    its punctuated text cut into sentence lines that take the aligner's word times."""

    def setUp(self):
        self.hub = Path(tempfile.mkdtemp(prefix='hub-'))
        self.env = {k: os.environ.get(k) for k in ('HF_HUB_CACHE', 'MINUTES_SPEECH_MODEL')}
        os.environ['HF_HUB_CACHE'] = str(self.hub)
        self.fake = types.ModuleType('mlx_qwen3_asr')
        self.calls = []

        def transcribe(audio, model='', language=None, return_timestamps=False, context='', **kw):
            self.calls.append({'model': model, 'language': language, 'context': context, 'seconds': len(audio[0]) / RATE})
            return {'text': '第一句。第二句？', 'segments': [{'text': '第', 'start': 0.5, 'end': 0.6}, {'text': '一', 'start': 0.6, 'end': 0.7},
                                                      {'text': '句', 'start': 0.7, 'end': 0.9}, {'text': '第二', 'start': 1.5, 'end': 1.8},
                                                      {'text': '句', 'start': 1.8, 'end': 2.0}]}
        self.fake.transcribe = transcribe
        self.had = sys.modules.get('mlx_qwen3_asr')
        sys.modules['mlx_qwen3_asr'] = self.fake

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if self.had is None:
            sys.modules.pop('mlx_qwen3_asr', None)
        else:
            sys.modules['mlx_qwen3_asr'] = self.had

    def weights(self, *repos):
        for repo in repos:
            folder = self.hub / ('models--' + repo.replace('/', '--')) / 'snapshots' / 'abc'
            folder.mkdir(parents=True, exist_ok=True)
            (folder / 'weights.safetensors').write_bytes(b'0')

    def test_whisper_unless_the_user_chose_qwen(self):
        self.weights(tr.QWEN, tr.QWEN_ALIGNER)
        os.environ['MINUTES_SPEECH_MODEL'] = 'whisper'
        self.assertEqual(tr.recogniser('zh', fake_whisper)[0], 'whisper')
        os.environ['MINUTES_SPEECH_MODEL'] = 'qwen3-asr'
        self.assertEqual(tr.recogniser('zh', fake_whisper)[0], 'qwen3-asr')
        self.assertEqual(tr.recogniser('en', fake_whisper)[0], 'whisper')             # other languages stay with Whisper

    def test_whisper_when_qwens_files_are_not_here(self):
        os.environ['MINUTES_SPEECH_MODEL'] = 'qwen3-asr'
        self.weights(tr.QWEN)                                                        # the aligner is missing
        self.assertFalse(tr.qwen_ready())
        self.assertEqual(tr.recogniser('zh', fake_whisper)[0], 'whisper')

    def test_qwen_gets_the_glossary_as_context_and_writes_sentence_lines(self):
        self.weights(tr.QWEN, tr.QWEN_ALIGNER)
        os.environ['MINUTES_SPEECH_MODEL'] = 'qwen3-asr'
        name, run = tr.recogniser('zh')
        segs = run(tone(3), 100.0)
        self.assertEqual(name, 'qwen3-asr')
        self.assertEqual(self.calls[0]['model'], tr.QWEN)
        self.assertEqual(self.calls[0]['language'], 'Chinese')
        self.assertTrue(self.calls[0]['context'].startswith(tr.HINT_HEAD))
        self.assertEqual(segs, [[100.5, 100.9, '第一句。'], [101.5, 102.0, '第二句？']])  # recording time, with punctuation

    def test_lines_are_cut_at_sentence_ends_and_keep_pace_with_the_words(self):
        words = [{'text': c, 'start': i * 0.5, 'end': i * 0.5 + 0.4} for i, c in enumerate('今天開會明天放假')]
        segs = tr.qwen_lines('今天 開會。明天，放假', words, 0)
        self.assertEqual(segs, [[0.0, 1.9, '今天 開會。'], [2.0, 3.9, '明天，放假']])

    def test_a_piece_written_by_qwen_says_so(self):
        self.weights(tr.QWEN, tr.QWEN_ALIGNER)
        os.environ['MINUTES_SPEECH_MODEL'] = 'qwen3-asr'
        job = Path(tempfile.mkdtemp(prefix='job-'))
        (job / 'job.json').write_text(json.dumps({'audio': 'x.caf', 'started': 't', 'ended': None}), encoding='utf-8')
        file = live.Runner(job, fake_whisper).audio
        file.write_bytes(caf_header() + pcm(tone(5.5)))
        meta = json.loads((job / 'job.json').read_text())
        runner = live.Runner(job, fake_whisper, detect=lambda a, t: 'zh', piece=2.0, search=0.5, poll=0.0)
        runner.sleep = lambda _: (job / 'job.json').write_text(json.dumps({**meta, 'ended': 'now'}), encoding='utf-8')
        runner.run()
        piece = json.loads((job / live.PIECES / '0001.json').read_text(encoding='utf-8'))
        self.assertEqual(piece['recogniser'], 'qwen3-asr')
        self.assertEqual(piece['segments'][0][2], '第一句。')


if __name__ == '__main__':
    unittest.main()
