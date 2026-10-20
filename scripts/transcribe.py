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
language and with the same hint. A piece still being transcribed when the recording stopped (working.json in
the folder) is waited for, at most three minutes.

Install the two packages with recorder/install.sh, or: pip install mlx-whisper opencc-python-reimplemented
A second recogniser, Qwen3-ASR, takes Chinese meetings when "speech_model" in settings.json is "qwen3-asr" and its
model and aligner are downloaded (setup_check.py download speech); it gets the glossary as its context and writes
punctuated sentences, each line timed by the aligner's words. Whisper does everything else and is the fallback.

Environment: MINUTES_WHISPER_MODEL picks another Whisper model, MINUTES_QWEN_MODEL another Qwen build;
MINUTES_SPEECH_MODEL (whisper, qwen3-asr) and MINUTES_MEETING_LANG (zh, en, auto) override the settings.
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
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_setup import CONFIG, settings  # noqa: E402  (standard library only)

MODEL = os.environ.get('MINUTES_WHISPER_MODEL') or 'mlx-community/whisper-large-v3-turbo'
# Qwen3-ASR (Alibaba, Apache-2.0), the recogniser for Chinese meetings when "speech_model" in settings.json is
# "qwen3-asr": on the 2026-10-20 bench it heard the far voices Whisper turned into nonsense and spelled the
# glossary's names more often (docs/bench/README.md). Through the mlx-qwen3-asr package; its word times come
# from Qwen's aligner model, downloaded with it. Whisper stays for every other language and as the fallback.
QWEN = os.environ.get('MINUTES_QWEN_MODEL') or 'moona3k/mlx-qwen3-asr-1.7b-8bit'
QWEN_ALIGNER = 'Qwen/Qwen3-ForcedAligner-0.6B'
SPEECH_MODELS = ('whisper', 'qwen3-asr')
SENTENCE_END = '。！？；\n'          # where a Qwen transcript is cut into lines
SKILL_DIR = Path(__file__).resolve().parent.parent
RATE = 16000
HINT_HEAD = '以下是台灣公司的會議錄音，用繁體中文記錄。'
HINT_MAX = 180          # characters; whisper only reads the last ~224 tokens of a prompt
# Lines whisper invents on silence or music; dropped when a whole segment is one of these.
HALLUCINATIONS = ('請不吝點贊', '訂閱 轉發', '明鏡與點點', '字幕由', '字幕組', '感謝觀看', '謝謝觀看', '請訂閱')
# A segment where whisper got stuck repeating itself ("請教教教教教…", "好的好的好的…"): one character twenty times in
# a row, or a short pattern ten times. Nobody said that; the segment is dropped.
STUCK = re.compile(r'(.)\1{19,}|(.{2,6}?)\2{9,}')
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


def prompt_for(lang: str) -> str:
    """What the model is told before it listens: the glossary hint for a Chinese meeting, nothing otherwise. The
    same for the whole recording, for every piece transcribed during it and for the rest after it, so a piece
    starts the way the recording itself starts. (The words of the piece before were tried as a prompt and dropped:
    a long prompt made the model skip most of the first half minute of the next piece.)"""
    return hint() if lang == 'zh' else ''


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


def speech_model() -> str:
    """"speech_model" in settings.json (MINUTES_SPEECH_MODEL overrides): whisper unless the user chose qwen3-asr."""
    v = (os.environ.get('MINUTES_SPEECH_MODEL') or str(settings().get('speech_model') or 'whisper')).strip().lower()
    return v if v in SPEECH_MODELS else 'whisper'


def hub_dir(repo: str) -> Path:
    """Where huggingface_hub keeps a model's files on this Mac."""
    base = os.environ.get('HF_HUB_CACHE') or os.path.join(os.environ.get('HF_HOME') or '~/.cache/huggingface', 'hub')
    return Path(base).expanduser() / ('models--' + repo.replace('/', '--'))


def hub_has(repo: str) -> bool:
    """Whether a model's weights are downloaded (its snapshot links to safetensors files that exist)."""
    return any(w.exists() for w in hub_dir(repo).glob('snapshots/*/*.safetensors'))


def qwen_package() -> bool:
    """Whether the Qwen3-ASR package is installed (install.sh adds it; a Mac installed before it needs the
    installer again). Asked at every app and recording start: the package is looked up, not imported."""
    import importlib.util
    if 'mlx_qwen3_asr' in sys.modules:
        return True
    try:
        return importlib.util.find_spec('mlx_qwen3_asr') is not None
    except (ImportError, ValueError):
        return False


def qwen_ready() -> bool:
    """The Qwen3-ASR package is installed and its two models are downloaded, so it can run offline."""
    return qwen_package() and hub_has(QWEN) and hub_has(QWEN_ALIGNER)


def qwen_lines(text: str, pieces: list, offset: float) -> list[list]:
    """Qwen's transcript as sentence segments [start, end, text] in recording time. `text` is the punctuated
    transcript, `pieces` the aligner's words (dicts or objects with text, start, end, in piece time, without
    punctuation). Each sentence takes the times of the words that spell it."""
    get = lambda p, k: p.get(k) if isinstance(p, dict) else getattr(p, k, None)  # noqa: E731
    words = [(str(get(p, 'text') or '').replace(' ', ''), float(get(p, 'start') or 0), float(get(p, 'end') or 0))
             for p in pieces]
    words = [w for w in words if w[0]]
    out = []
    at = 0                                           # next word to consume
    sentence = ''
    for i, ch in enumerate(text):
        sentence += ch
        if ch in SENTENCE_END or i == len(text) - 1:
            # the aligner keeps only letters, digits and apostrophes of a word: count the sentence the same way
            body = ''.join(c for c in sentence if c == "'" or unicodedata.category(c)[0] in 'LN')
            need = len(body)
            first = at
            taken = 0
            while at < len(words) and taken < need:
                taken += sum(1 for c in words[at][0] if c == "'" or unicodedata.category(c)[0] in 'LN')
                at += 1
            if body:
                start = words[first][1] if first < len(words) else (words[-1][2] if words else 0.0)
                end = words[at - 1][2] if at > first else start
                out.append([round(start + offset, 2), round(end + offset, 2), sentence.strip()])
            sentence = ''
    return out


def echoes(text: str, context: str) -> bool:
    """Whether a sentence is the context read back: over a quiet stretch Qwen3-ASR sometimes writes its context's
    term list down as if someone had said it (four times in one recorded meeting, once in another). The sentence
    runs through four or more of the context's terms in the context's own order, one after the other, and those
    terms are at least half of the sentence; a sentence that names a few people in passing is not that."""
    split = lambda s: [p.strip() for p in re.split(r'[、，,。．.！？；!?;\s]+', s) if p.strip()]  # noqa: E731
    parts = split(text)
    if len(parts) < 4:
        return False
    order = {}
    for i, p in enumerate(split(context)):
        order.setdefault(p.lower(), i)
    where = [order.get(p.lower(), -1) for p in parts]
    hits = sum(1 for w in where if w >= 0)
    run = best = 0
    for prev, now in zip([-9] + where, where):
        run = run + 1 if now >= 0 and now == prev + 1 else (1 if now >= 0 else 0)
        best = max(best, run)
    return best >= 4 and hits * 2 >= len(parts)


def qwen_range(audio, offset: float, context: str, transcribe=None) -> list[list]:
    """Qwen3-ASR over `audio` (16 kHz floats that begin `offset` seconds into the recording), the glossary as
    its context: sentence segments in recording time, Simplified Chinese as the model writes it (assemble()
    converts). A sentence that only reads the context back is left out."""
    if transcribe is None:
        from mlx_qwen3_asr import transcribe
    result = transcribe((audio, RATE), model=QWEN, language='Chinese', return_timestamps=True, context=context,
                        forced_aligner=QWEN_ALIGNER)
    text = result.text if hasattr(result, 'text') else result.get('text', '')
    segs = result.segments if hasattr(result, 'segments') else result.get('segments', [])
    lines = qwen_lines(text or '', segs or [], offset)
    kept = [line for line in lines if not echoes(line[2], context)]
    if len(kept) < len(lines):
        import vlog
        vlog.log(f'qwen3-asr read its context back {len(lines) - len(kept)} time(s) after {stamp(offset)}; dropped')
    return kept


def recogniser(lang: str, whisper=None, want: str = ''):
    """(name, run) for a meeting in `lang`: run(audio, offset) -> segments. Qwen3-ASR for a Chinese meeting
    when the user chose it and it is ready; Whisper otherwise, prompted as before (`whisper` is mlx-whisper's
    transcribe, or a stand-in). `want` is the model the recording's earlier pieces were written with: the rest
    follows them even if the setting changed during the meeting, so one transcript comes from one model."""
    prompt = prompt_for(lang)
    chosen = want if want in SPEECH_MODELS else speech_model()

    def with_whisper(audio, offset):
        nonlocal whisper
        if whisper is None:
            import mlx_whisper
            whisper = mlx_whisper.transcribe
        return transcribe_range(audio, lang, prompt, offset, whisper)

    if lang == 'zh' and chosen == 'qwen3-asr' and qwen_ready():
        context = hint()

        def with_qwen(audio, offset):
            try:
                return qwen_range(audio, offset, context)
            except Exception as err:                    # a broken model file, a package error: this stretch by Whisper
                import vlog
                vlog.log(f'qwen3-asr failed at {stamp(offset)}, Whisper takes this stretch: {type(err).__name__}: {err}')
                return with_whisper(audio, offset)
        return 'qwen3-asr', with_qwen
    return 'whisper', with_whisper


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
    """The transcript's lines ('[mm:ss] text') and each line's [start, end]: empty, repeated, invented and
    stuck segments dropped, Chinese converted to Taiwan wording."""
    lines, spans, last = [], [], ''
    for start, end, raw in segments:
        text = tidy(raw, convert) if lang == 'zh' else (raw or '').strip()
        if not text or text == last or any(h in text for h in HALLUCINATIONS) or STUCK.search(text):
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


def is_helper(pid: int) -> bool:
    """Whether `pid` is a live_transcribe.py of this user: a pid left in working.json by a helper that died could
    since have gone to any other process, which must be neither waited for nor stopped."""
    if pid <= 0:
        return False
    try:
        done = subprocess.run(['ps', '-o', 'command=', '-p', str(pid)], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0 and 'live_transcribe.py' in done.stdout


def wait_for_helper(folder: Path, limit: float = HELPER_WAIT, poll: float = 2.0, sleep=time.sleep,
                    running=is_helper) -> float:
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
        if not running(pid):                           # the helper is gone (or never wrote a pid): nothing to wait for
            marker.unlink(missing_ok=True)
            break
        sleep(poll)
    if marker.exists():
        if running(pid):
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
    elif pieces and pieces[0].get('language'):
        lang = str(pieces[0]['language'])
    else:
        lang = detect(audio, mlx_whisper.transcribe)
    segments = [seg for piece in pieces for seg in piece['segments']]
    from_s = pieces[-1]['end'] if pieces else 0.0
    rest = audio[int(from_s * RATE):]
    name, run = recogniser(lang, mlx_whisper.transcribe, str(pieces[0].get('recogniser', '')) if pieces else '')
    if not pieces or len(rest) >= RATE // 2:              # half a second: less than that is no speech
        segments += run(rest, from_s)
    lines, spans = assemble(segments, lang, OpenCC('s2twp').convert)
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    # each line's start and end in seconds, for telling the voices apart (speakers.py); which recogniser wrote it
    out.with_suffix('.json').write_text(json.dumps({'lines': spans, 'language': lang, 'recogniser': name}),
                                        encoding='utf-8')
    reused = f', {len(pieces)} pieces reused ({stamp(from_s)[1:-1]})' if pieces else ''
    waiting = f', waited {waited:.0f}s' if waited >= 1 else ''
    print(f'TRANSCRIPT {out} ({len(lines)} lines, language {lang}, {name}, audio {stamp(total)[1:-1]}, '
          f'took {time.time() - began:.0f}s{reused}{waiting})')


if __name__ == '__main__':
    import vlog
    vlog.run(main)
