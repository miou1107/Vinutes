"""Transcribe the meeting in pieces while it is still being recorded, so that when the recording stops only the
last few minutes are left to do.

Usage:
  live_transcribe.py <job folder>        the app starts it with the recording (MeetingRecorder.swift)

It follows the recording (錄音.caf: 16 kHz mono 16-bit PCM, written as the meeting goes) and, each time 5½ minutes
of audio past the last cut exist, cuts at the quietest half second between 4½ and 5½ minutes past that cut, so a
piece never ends in the middle of a sentence. The piece is transcribed with the same model, hint and settings as
transcribe.py gives the whole recording. The language is decided once, on the first piece, unless the setting
fixes it.

Each finished piece is <job>/分段/0001.json, 0002.json, ...:
  {"start", "end": seconds from the recording's beginning, "language", "segments": [[start, end, text], ...],
   "took": seconds, "cut": "quiet" | "end"}
While a piece is being transcribed, <job>/分段/working.json says so ({"pid", "start", "end"}). transcribe.py --pieces
reuses the pieces and waits for that one. A pause in the recording needs nothing: the file stops growing.

It ends by itself: when job.json gets its "ended" time (after the piece in hand, never starting another), when the
app that started it is gone (after the piece in hand), or when the recording file cannot be read for a minute.
With "live_transcribe": false in settings.json it does nothing at all. It runs at low priority and never writes
the recording.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import transcribe as tr  # noqa: E402
from google_setup import settings  # noqa: E402

RATE = tr.RATE
PIECE = 300.0            # seconds a piece aims for
SEARCH = 30.0            # the cut is the quietest half second within this many seconds either side of the mark
QUIET = 0.5              # seconds of quiet looked for
FRAME = 0.05             # seconds per loudness frame
POLL = 2.0               # seconds between looks at the file
PIECES = '分段'
UNREADABLE = 60.0        # seconds the file may be missing or unreadable before giving up


def caf_data_start(head: bytes) -> int | None:
    """Where the samples begin in a CAF file: after the 'data' chunk's header and its 4-byte edit count. The
    chunk's size is -1 while the file is still being written, so the size is never trusted for the data chunk."""
    if len(head) < 8 or head[:4] != b'caff':
        return None
    at = 8
    while at + 12 <= len(head):
        kind = head[at:at + 4]
        size = int.from_bytes(head[at + 4:at + 12], 'big', signed=True)
        if kind == b'data':
            return at + 12 + 4
        if size < 0:
            return None
        at += 12 + size
    return None


def quietest_cut(audio, lo: int, hi: int, rate: int = RATE, quiet: float = QUIET, frame: float = FRAME) -> int:
    """The sample in audio[lo:hi] at the middle of its quietest `quiet` seconds (loudness measured per `frame`
    seconds, root mean square). hi when the stretch is too short to search."""
    import numpy as np
    step = max(1, int(frame * rate))
    hi = min(hi, len(audio))
    n = (hi - lo) // step
    need = max(1, int(round(quiet / frame)))
    if n < need:
        return hi
    x = audio[lo:lo + n * step].reshape(n, step).astype(np.float64)
    loud = np.sqrt((x * x).mean(axis=1))
    window = np.convolve(loud, np.ones(need), mode='valid')         # the sum over `need` frames in a row
    best = int(np.argmin(window))
    return lo + (best * step) + (need * step) // 2


def write_json(path: Path, data: dict):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


class Runner:
    """One recording, followed until it ends. `transcribe` and `detect` are mlx-whisper's and transcribe.py's
    (the tests put stand-ins in); `sleep` and `parent_alive` likewise."""

    def __init__(self, job: Path, transcribe, detect=tr.detect, sleep=time.sleep, parent_alive=None, log=None,
                 piece: float = PIECE, search: float = SEARCH, poll: float = POLL, language: str = 'auto',
                 choose=None):
        self.job = job
        self.audio = job / '錄音.caf'
        self.folder = job / PIECES
        self.transcribe = transcribe
        self.detect = detect
        # which recogniser writes the pieces, decided once the language is known: tr.recogniser (Qwen3-ASR for a
        # Chinese meeting when chosen and ready, else Whisper); the tests pass a stand-in built on `transcribe`
        self.choose = choose or (lambda lang: tr.recogniser(lang, transcribe))
        self.name, self.recognise = '', None
        self.sleep = sleep
        self.parent_alive = parent_alive or (lambda: os.getppid() != 1)
        self.log = log or (lambda line: None)
        self.piece, self.search, self.poll = piece, search, poll
        self.language = language if language != 'auto' else ''
        self.data_start: int | None = None
        self.cut = 0.0                                     # seconds of the recording transcribed so far
        self.number = 0
        self.done = 0

    # --- the recording file -----------------------------------------------------------------------

    def meta(self) -> dict:
        try:
            return json.loads((self.job / 'job.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def ended(self) -> bool:
        return bool(self.meta().get('ended'))

    def available(self) -> float:
        """Seconds of audio in the file so far, or -1 when the file cannot be read yet."""
        try:
            if self.data_start is None:
                with open(self.audio, 'rb') as f:              # Core Audio puts the data chunk near 4 KB; read well past
                    self.data_start = caf_data_start(f.read(65536))
                if self.data_start is None:
                    return -1
            size = self.audio.stat().st_size
        except OSError:
            return -1
        return max(0, (size - self.data_start) // 2) / RATE

    def read(self, start: float, end: float):
        """audio[start:end] in seconds, as 16 kHz floats: exactly round((end - start) * RATE) samples when the file
        has them (271.1 * 16000 is not a whole number in floating point; truncating it loses a sample)"""
        import numpy as np
        a, b = round(start * RATE), round(end * RATE)
        with open(self.audio, 'rb') as f:
            f.seek(self.data_start + a * 2)
            blob = f.read((b - a) * 2)
        return np.frombuffer(blob[:len(blob) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768.0

    # --- pieces -----------------------------------------------------------------------------------

    def resume(self):
        """Pieces already on disk (this helper started again mid-meeting): go on after the last one."""
        if not self.folder.is_dir():
            return
        have = tr.pieces_in(self.folder, float('inf'))
        if have:
            self.cut = have[-1]['end']
            self.number = len(have)
            self.language = self.language or str(have[0].get('language') or '')
            self.log(f'going on after {self.number} pieces ({tr.stamp(self.cut)[1:-1]})')

    def do_piece(self) -> bool:
        """Transcribe the next piece. False when the recording ended meanwhile (nothing written)."""
        self.folder.mkdir(exist_ok=True)
        marker = self.folder / tr.WORKING
        hi = self.cut + self.piece + self.search
        write_json(marker, {'pid': os.getpid(), 'start': self.cut, 'end': hi})
        if self.ended():                            # Stop came first: the final run takes it from here
            marker.unlink(missing_ok=True)
            return False
        began = time.time()
        try:
            audio = self.read(self.cut, hi)
            at = quietest_cut(audio, round((self.piece - self.search) * RATE), round((self.piece + self.search) * RATE))
            piece = audio[:at]
            if not self.language:
                self.language = self.detect(piece, self.transcribe)
            if self.recognise is None:
                self.name, self.recognise = self.choose(self.language)
            segments = self.recognise(piece, self.cut)
            end = round(self.cut + at / RATE, 2)
            self.number += 1
            write_json(self.folder / f'{self.number:04d}.json',
                       {'start': round(self.cut, 2), 'end': end, 'language': self.language, 'segments': segments,
                        'recogniser': self.name, 'took': round(time.time() - began, 1), 'cut': 'quiet'})
            self.log(f'piece {self.number}: {tr.stamp(self.cut)[1:-1]}-{tr.stamp(end)[1:-1]}, {len(segments)} segments, '
                     f'{self.name}, {time.time() - began:.0f}s')
            self.cut = end
            self.done += 1
        finally:
            marker.unlink(missing_ok=True)
        return True

    def run(self) -> int:
        """Until the recording ends. The number of pieces written."""
        self.resume()
        unreadable_since = None
        while True:
            if self.ended():
                self.log('recording ended')
                break
            if not self.parent_alive():
                self.log('the app is gone')
                break
            have = self.available()
            if have < 0:
                unreadable_since = unreadable_since or time.time()
                if time.time() - unreadable_since > UNREADABLE:
                    self.log('recording file unreadable for a minute, giving up')
                    break
                self.sleep(self.poll)
                continue
            unreadable_since = None
            if have >= self.cut + self.piece + self.search:
                if not self.do_piece():
                    break
                continue
            self.sleep(self.poll)
        return self.done


def main():
    import vlog
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    job = Path(sys.argv[1]).expanduser()
    if not (job / 'job.json').exists():
        sys.exit(f'NO SUCH JOB {job}')
    if settings().get('live_transcribe', True) is False:
        vlog.log('live transcribing is off in settings.json')
        return
    try:
        import mlx_whisper
    except ImportError as err:
        sys.exit(f'NOT INSTALLED ({err.name}): run recorder/install.sh')
    try:
        os.nice(10)                                 # the meeting's call and the user's work come first
    except OSError:
        pass

    def log(line: str):
        vlog.log(f'{job.name}: {line}')
        try:
            with open(job / 'log.txt', 'a', encoding='utf-8') as f:
                f.write(f'[{time.strftime("%H:%M:%S")}] live: {line}\n')
        except OSError:
            pass

    runner = Runner(job, mlx_whisper.transcribe, log=log, language=tr.meeting_setting())
    done = runner.run()
    print(f'LIVE {job.name}: {done} pieces, up to {tr.stamp(runner.cut)[1:-1]}')


if __name__ == '__main__':
    import vlog
    vlog.run(main)
