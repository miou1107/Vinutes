"""Turn a meeting recording into a transcript the rest of the skill can read.

Usage:
  transcribe.py <audio file> [out.txt] [--pieces <folder>]
                                      writes <audio>.txt next to the recording unless out.txt is given

Runs on the Mac itself; the recording never leaves the computer. For now only Macs with Apple silicon:
it uses mlx-whisper with the whisper-large-v3-turbo model (about 1.6 GB, downloaded once into
~/.cache/huggingface). An hour of audio takes about 4 to 7 minutes, depending on the Mac.

Audio is decoded with macOS's own afconvert, so m4a, mp3, wav, aac and caf work without ffmpeg.
The words in the correct-name column of references/glossary.md and $MINUTES_HOME/glossary.md are given
to the model as a hint, so product and system names come out right more often.
The meeting's language comes from "meeting_language" in settings.json: "zh" or "en", or "auto" (the default),
where three 30-second stretches (start, middle, end) are each given to the model to name the language and the
most common answer wins. A Chinese meeting is converted to Traditional Chinese with Taiwan wording (OpenCC
s2twp); any other language keeps the model's own text. Each line starts with [mm:ss] (or [h:mm:ss]), counted
from the start of the recording. The language is kept in <out>.json as "language" (Whisper's code: zh, en, ja...).

--pieces <folder>: pieces of the same recording already transcribed while it was being recorded
(live_transcribe.py writes them there as 0001.json, 0002.json, ...). The pieces that join end to start from the
beginning of the recording are reused and only the audio after the last one is transcribed, in the pieces'
language and prompted with their last words. A piece still being transcribed when the recording stopped
(working.json in the folder) is waited for, at most three minutes.

Install the two packages with recorder/install.sh, or: pip install mlx-whisper opencc-python-reimplemented
Environment: MINUTES_WHISPER_MODEL picks another model; MINUTES_MEETING_LANG (zh, en, auto) overrides the setting.
"""
from __future__ import annotations

import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_setup import CONFIG, settings  # noqa: E402  (standard library only)

MODEL = os.environ.get('MINUTES_WHISPER_MODEL') or 'mlx-community/whisper-large-v3-turbo'
SKILL_DIR = Path(__file__).resolve().parent.parent
RATE = 16000
HINT_HEAD = '以下是台灣公司的會議錄音，用繁體中文記錄。'
HINT_MAX = 180          # characters; whisper only reads the last ~224 tokens of a prompt
TAIL_MAX = 80           # characters of the piece before, given with the hint so names continue the same way
# Lines whisper invents on silence or music; dropped when a whole segment is one of these.
HALLUCINATIONS = ('請不吝點贊', '訂閱 轉發', '明鏡與點點', '字幕由', '字幕組', '感謝觀看', '謝謝觀看', '請訂閱')
WORKING = 'working.json'        # in the pieces folder while live_transcribe.py is on a piece: {"pid", "start", "end"}
HELPER_WAIT = 180               # seconds the final run waits for that piece before stopping the helper


def stamp(seconds: float) -> str:
    s = int(seconds)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f'[{h}:{m:02d}:{s:02d}]' if h else f'[{m:02d}:{s:02d}]'


def glossary_terms() -> list[str]:
    """Correct names from the shared and the company glossary, in table order, without duplicates."""
    terms: list[str] = []
    for path in (SKILL_DIR / 'references' / 'glossary.md', CONFIG / 'glossary.md'):
        try:
            lines = path.read_text(encoding='utf-8-sig').splitlines()
        except OSError:
            continue
        for line in lines:
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if len(cells) < 2 or not cells[1] or set(cells[1]) <= set('-: '):
                continue
            if cells[1] in ('正確名稱', '正確寫法'):
                continue
            for term in re.split(r'[／/、,，]', cells[1]):
                term = term.strip()
                if term and term not in terms:
                    terms.append(term)
    return terms


def hint() -> str:
    text = HINT_HEAD
    for term in reversed(glossary_terms()):     # company terms come last in the file; keep them first
        if len(text) + len(term) + 1 > HINT_MAX:
            break
        text += term + '、'
    return text.rstrip('、') + '。'


def prompt_for(lang: str, tail: str = '') -> str:
    """What the model is told before it listens: the glossary hint for a Chinese meeting, and the last words of
    the piece before (live_transcribe.py), so a name keeps the spelling it got there. '' when there is nothing."""
    parts = [hint()] if lang == 'zh' else []
    if tail:
        parts.append(tail)
    return ' '.join(parts)


def tail_of(segments: list, limit: int = TAIL_MAX) -> str:
    """The last `limit` characters of what was transcribed, whole segments from the end, as the next prompt."""
    text = ''
    for _, _, raw in reversed(segments):
        piece = (raw or '').strip()
        if not piece:
            continue
        if len(text) + len(piece) + 1 > limit and text:
            break
        text = (piece + ' ' + text).strip()
    return text[-limit:] if len(text) > limit else text


def load_audio(src: Path):
    """Decode any format afconvert knows into 16 kHz mono floats, the input whisper expects."""
    import numpy as np
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / 'audio.wav'
        done = subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', str(src), str(wav)],
                              capture_output=True, text=True)
        if done.returncode or not wav.exists():
            sys.exit(f'CANNOT READ AUDIO {src}: {done.stderr.strip() or "afconvert failed"}')
        frames = pcm_frames(wav.read_bytes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def pcm_frames(blob: bytes) -> bytes:
    """The data chunk of a 16-bit WAV. afconvert writes WAVE_FORMAT_EXTENSIBLE for m4a input, which the
    wave module refuses, so walk the RIFF chunks ourselves; the samples are LEI16 either way."""
    if blob[:4] != b'RIFF' or blob[8:12] != b'WAVE':
        sys.exit('CANNOT READ AUDIO: afconvert did not produce a WAV file')
    pos = 12
    while pos + 8 <= len(blob):
        kind, size = blob[pos:pos + 4], int.from_bytes(blob[pos + 4:pos + 8], 'little')
        if kind == b'data':
            return blob[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)
    sys.exit('CANNOT READ AUDIO: no sound data in the converted file')


def meeting_setting() -> str:
    v = (os.environ.get('MINUTES_MEETING_LANG') or str(settings().get('meeting_language') or 'auto')).strip().lower()
    return v if v in ('auto', 'zh', 'en') else 'auto'


def detect(audio, transcribe) -> str:
    """The meeting's language by majority of three 30-second stretches (start, middle, end); a tie goes to the
    earliest. Cantonese counts as Chinese: its minutes are written in Chinese either way."""
    window = 30 * RATE
    if len(audio) <= window:
        starts = [0]
    else:
        last = len(audio) - window
        starts = sorted({0, last // 2, last})
    votes = []
    for s in starts:
        got = transcribe(audio[s:s + window], path_or_hf_repo=MODEL, language=None,
                         condition_on_previous_text=False, verbose=None)
        if (got.get('text') or '').strip():
            votes.append('zh' if got.get('language') == 'yue' else got.get('language') or 'zh')
    if not votes:
        return 'zh'
    return max(votes, key=lambda v: (votes.count(v), -votes.index(v)))


def transcribe_range(audio, lang: str, prompt: str, offset: float, transcribe) -> list[list]:
    """Whisper over `audio` (16 kHz floats that begin `offset` seconds into the recording): segments as
    [start, end, text] in recording time, the text as the model gave it (assemble() tidies it)."""
    extra = {'initial_prompt': prompt} if prompt else {}
    result = transcribe(audio, path_or_hf_repo=MODEL, language=lang, condition_on_previous_text=False,
                        verbose=None, **extra)
    return [[round(float(seg.get('start', 0)) + offset, 2), round(float(seg.get('end', 0)) + offset, 2),
             seg.get('text', '') or ''] for seg in result.get('segments', [])]


def tidy(text: str, convert) -> str:
    text = convert(text.strip())
    cjk = '[一-鿿]'
    text = re.sub(rf'(?<={cjk}),\s*|,\s*(?={cjk})', '，', text)
    text = re.sub(rf'(?<={cjk})\?', '？', text)
    text = re.sub(rf'(?<={cjk})!', '！', text)
    return text


def assemble(segments: list, lang: str, convert) -> tuple[list[str], list[list]]:
    """The transcript's lines ('[mm:ss] text') and each line's [start, end]: empty, repeated and invented
    segments dropped, Chinese converted to Taiwan wording."""
    lines, spans, last = [], [], ''
    for start, end, raw in segments:
        text = tidy(raw, convert) if lang == 'zh' else (raw or '').strip()
        if not text or text == last or any(h in text for h in HALLUCINATIONS):
            continue
        lines.append(f'{stamp(start)} {text}')
        spans.append([round(float(start), 2), round(float(end), 2)])
        last = text
    return lines, spans


# --- pieces transcribed during the recording (live_transcribe.py) -----------------------------

def pieces_in(folder: Path, audio_seconds: float) -> list[dict]:
    """The finished pieces that can be reused, in order: the first starts at 0, each next one starts where the
    one before ended, and none ends after the audio. A piece that is unreadable, out of place or past the end
    ends the run; what comes after it is transcribed again."""
    found = []
    for path in sorted(folder.glob('[0-9]*.json')):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get('segments'), list):
            try:
                data['start'], data['end'] = float(data['start']), float(data['end'])
            except (KeyError, TypeError, ValueError):
                continue
            found.append(data)
    out, at = [], 0.0
    for piece in sorted(found, key=lambda p: p['start']):
        if abs(piece['start'] - at) > 0.01 or piece['end'] <= piece['start'] or piece['end'] > audio_seconds + 0.5:
            break
        out.append(piece)
        at = piece['end']
    return out


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_helper(folder: Path, limit: float = HELPER_WAIT, poll: float = 2.0, sleep=time.sleep) -> float:
    """The helper may still be on a piece when the recording stops: wait for it (the piece is worth more than
    the wait), at most `limit` seconds, then stop the helper and go on without that piece. Seconds waited."""
    marker = folder / WORKING
    began = time.time()
    pid = 0
    while marker.exists() and time.time() - began < limit:
        try:
            pid = int(json.loads(marker.read_text(encoding='utf-8')).get('pid') or 0)
        except (OSError, ValueError, AttributeError):
            pid = 0
        if pid and not alive(pid):                     # the helper died on it: nothing to wait for
            marker.unlink(missing_ok=True)
            break
        sleep(poll)
    if marker.exists():
        if pid and alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        marker.unlink(missing_ok=True)
    return time.time() - began


def parse_args(argv: list[str]) -> tuple[Path, Path, Path | None]:
    pieces = None
    plain = []
    i = 0
    while i < len(argv):
        if argv[i] == '--pieces' and i + 1 < len(argv):
            pieces = Path(argv[i + 1]).expanduser()
            i += 2
            continue
        plain.append(argv[i])
        i += 1
    if not plain:
        sys.exit(__doc__)
    src = Path(plain[0]).expanduser()
    out = Path(plain[1]).expanduser() if len(plain) > 1 else src.with_suffix('.txt')
    return src, out, pieces


def main():
    src, out, pieces_dir = parse_args(sys.argv[1:])
    if not src.exists():
        sys.exit(f'NO SUCH FILE {src}')
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        sys.exit('NOT SUPPORTED: transcribing on this computer needs a Mac with Apple silicon for now. '
                 'Use the transcript from the recording app instead.')
    try:
        import mlx_whisper
        from opencc import OpenCC
    except ImportError as err:
        sys.exit(f'NOT INSTALLED ({err.name}): run recorder/install.sh, '
                 'or pip install mlx-whisper opencc-python-reimplemented')

    began = time.time()
    pieces: list[dict] = []
    waited = 0.0
    if pieces_dir and pieces_dir.is_dir():
        waited = wait_for_helper(pieces_dir)
    audio = load_audio(src)
    total = len(audio) / RATE
    if pieces_dir and pieces_dir.is_dir():
        pieces = pieces_in(pieces_dir, total)
    setting = meeting_setting()
    if setting != 'auto':
        lang = setting
    elif pieces:
        lang = str(pieces[0].get('language') or 'zh')
    else:
        lang = detect(audio, mlx_whisper.transcribe)
    segments = [seg for piece in pieces for seg in piece['segments']]
    from_s = pieces[-1]['end'] if pieces else 0.0
    rest = audio[int(from_s * RATE):]
    if not pieces or len(rest) >= RATE // 2:              # half a second: less than that is no speech
        segments += transcribe_range(rest, lang, prompt_for(lang, tail_of(segments)), from_s, mlx_whisper.transcribe)
    lines, spans = assemble(segments, lang, OpenCC('s2twp').convert)
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    # each line's start and end in seconds, for telling the voices apart (speakers.py)
    out.with_suffix('.json').write_text(json.dumps({'lines': spans, 'language': lang}), encoding='utf-8')
    reused = f', {len(pieces)} pieces reused ({stamp(from_s)[1:-1]})' if pieces else ''
    waiting = f', waited {waited:.0f}s' if waited >= 1 else ''
    print(f'TRANSCRIPT {out} ({len(lines)} lines, language {lang}, audio {stamp(total)[1:-1]}, '
          f'took {time.time() - began:.0f}s{reused}{waiting})')


if __name__ == '__main__':
    import vlog
    vlog.run(main)
