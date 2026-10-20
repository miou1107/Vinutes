"""Shared bits of the bench scripts: where the repo's scripts are, how two transcripts are compared, how a
transcript is read back line by line. Every bench script writes transcripts in the app's own format, one line
per utterance, '[mm:ss] text', so they can be read back by the same code and compared character by character."""
import difflib
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts'
PY = sys.executable
LINE = re.compile(r'\[(?:(\d+):)?(\d+):(\d{2})\]\s*(.*)')
RATE = 16000


def say(line: str):
    print(f'[{time.strftime("%H:%M:%S")}] {line}', flush=True)


def stamp(seconds: float) -> str:
    s = int(seconds)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f'[{h}:{m:02d}:{s:02d}]' if h else f'[{m:02d}:{s:02d}]'


def lines(path: Path) -> list[tuple[int, str]]:
    """(start second, text) for each line of a transcript"""
    out = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        m = LINE.match(raw)
        if m:
            out.append((int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3)), m.group(4)))
    return out


def words(path: Path) -> str:
    """the transcript's text without timestamps, as one string"""
    return ''.join(t for _, t in lines(path))


def changed_pct(a: str, b: str) -> float:
    """share of a's characters that differ from b (insertions, deletions and replacements counted once each)"""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != 'equal')
    return round(100 * changed / max(1, len(a)), 2)


def compare(a: Path, b: Path) -> dict:
    ta, tb = words(a), words(b)
    la, lb = a.read_text(encoding='utf-8').splitlines(), b.read_text(encoding='utf-8').splitlines()
    return {'chars_a': len(ta), 'chars_b': len(tb), 'changed_pct': changed_pct(ta, tb), 'lines_a': len(la),
            'lines_b': len(lb), 'diff': list(difflib.unified_diff(la, lb, lineterm='', n=0, fromfile=a.name, tofile=b.name))}


def to_wav(src: Path, wav: Path):
    """16 kHz mono 16-bit WAV through macOS's afconvert (the way the app's transcriber reads audio)"""
    import subprocess
    if not wav.exists():
        subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', str(src), str(wav)], check=True)


def load_wav(wav: Path):
    import wave
    import numpy as np
    with wave.open(str(wav), 'rb') as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def save_wav(path: Path, audio):
    import wave
    import numpy as np
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes())


def whisper(audio: Path, out: Path, pieces: Path | None = None, model: str = '') -> float:
    """scripts/transcribe.py over a file, the way the app runs it; seconds taken"""
    import os
    import subprocess
    began = time.time()
    env = dict(os.environ)
    if model:
        env['MINUTES_WHISPER_MODEL'] = model
    cmd = [PY, str(SCRIPTS / 'transcribe.py'), str(audio), str(out)] + (['--pieces', str(pieces)] if pieces else [])
    done = subprocess.run(cmd, capture_output=True, text=True, env=env)
    text = (done.stdout + done.stderr).strip()
    say(text.splitlines()[-1] if text else f'exit {done.returncode}')
    if done.returncode:
        raise SystemExit(f'transcribe.py failed: {done.stderr[-500:]}')
    return time.time() - began
