"""Turn a meeting recording into a transcript the rest of the skill can read.

Usage:
  transcribe.py <audio file> [out.txt]      writes <audio>.txt next to the recording unless out.txt is given

Runs on the Mac itself; the recording never leaves the computer. For now only Macs with Apple silicon:
it uses mlx-whisper with the whisper-large-v3-turbo model (about 1.6 GB, downloaded once into
~/.cache/huggingface). An hour of audio takes about 7 minutes on an M1 Pro.

Audio is decoded with macOS's own afconvert, so m4a, mp3, wav, aac and caf work without ffmpeg.
The words in the correct-name column of references/glossary.md and $MINUTES_HOME/glossary.md are given
to the model as a hint, so product and system names come out right more often.
The meeting's language comes from "meeting_language" in settings.json: "zh" or "en", or "auto" (the default),
where three 30-second stretches (start, middle, end) are each given to the model to name the language and the
most common answer wins. A Chinese meeting is converted to Traditional Chinese with Taiwan wording (OpenCC
s2twp); any other language keeps the model's own text. Each line starts with [mm:ss] (or [h:mm:ss]), counted
from the start of the recording. The language is kept in <out>.json as "language" (Whisper's code: zh, en, ja...).

Install the two packages with recorder/install.sh, or: pip install mlx-whisper opencc-python-reimplemented
Environment: MINUTES_WHISPER_MODEL picks another model; MINUTES_MEETING_LANG (zh, en, auto) overrides the setting.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_setup import CONFIG, settings  # noqa: E402  (standard library only)

MODEL = os.environ.get('MINUTES_WHISPER_MODEL') or 'mlx-community/whisper-large-v3-turbo'
SKILL_DIR = Path(__file__).resolve().parent.parent
HINT_HEAD = '以下是台灣公司的會議錄音，用繁體中文記錄。'
HINT_MAX = 180          # characters; whisper only reads the last ~224 tokens of a prompt
# Lines whisper invents on silence or music; dropped when a whole segment is one of these.
HALLUCINATIONS = ('請不吝點贊', '訂閱 轉發', '明鏡與點點', '字幕由', '字幕組', '感謝觀看', '謝謝觀看', '請訂閱')


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
    window = 30 * 16000
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


def tidy(text: str, convert) -> str:
    text = convert(text.strip())
    cjk = '[一-鿿]'
    text = re.sub(rf'(?<={cjk}),\s*|,\s*(?={cjk})', '，', text)
    text = re.sub(rf'(?<={cjk})\?', '？', text)
    text = re.sub(rf'(?<={cjk})!', '！', text)
    return text


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1]).expanduser()
    out = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else src.with_suffix('.txt')
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
    audio = load_audio(src)
    setting = meeting_setting()
    lang = detect(audio, mlx_whisper.transcribe) if setting == 'auto' else setting
    extra = {'initial_prompt': hint()} if lang == 'zh' else {}
    result = mlx_whisper.transcribe(audio, path_or_hf_repo=MODEL, language=lang, condition_on_previous_text=False,
                                    verbose=None, **extra)
    convert = OpenCC('s2twp').convert
    lines, spans, last = [], [], ''
    for seg in result.get('segments', []):
        text = tidy(seg.get('text', ''), convert) if lang == 'zh' else seg.get('text', '').strip()
        if not text or text == last or any(h in text for h in HALLUCINATIONS):
            continue
        lines.append(f'{stamp(seg.get("start", 0))} {text}')
        spans.append([round(float(seg.get('start', 0)), 2), round(float(seg.get('end', 0)), 2)])
        last = text
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    # each line's start and end in seconds, for telling the voices apart (speakers.py)
    out.with_suffix('.json').write_text(json.dumps({'lines': spans, 'language': lang}), encoding='utf-8')
    print(f'TRANSCRIPT {out} ({len(lines)} lines, language {lang}, audio {stamp(len(audio) / 16000)[1:-1]}, '
          f'took {time.time() - began:.0f}s)')


if __name__ == '__main__':
    main()
