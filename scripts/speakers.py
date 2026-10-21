"""Who said each line of a transcript, told apart by voice, on this Mac.

Usage:
  speakers.py <job folder>                         after transcribe.py: 講者.json and 聲紋.npz in the job
  speakers.py <job folder> --name <group> <name> [line]
                                                   the user named a voice (every line of the group, or one line)

Each transcript line gets a voice print (3D-Speaker CAM++, through sherpa-onnx) from the stretch of audio
transcribe.py noted for it in 逐字稿.json. Lines that sound like someone the user named before take that name;
the rest are grouped by how alike they sound into 講者 A, 講者 B, ... (no head count needed). A group that is
that person's own voice again joins them; a new voice needs 20 seconds of lines of 3 seconds or more, since the
prints of 嗯 and 對 are noise; and a known voice heard in under 20 seconds of lines is not counted as there. Naming a group
keeps a few of its prints in $MINUTES_HOME/voices/, so the next meeting knows that voice. Nothing leaves the Mac.

Files:
  <job>/講者.json   {"groups": {"A": {"name", "known", "seconds", "sample": [start, end]}},
                     "lines": ["A", "B", ...] (one per transcript line), "fixed": {"12": "Alex"}}
  <job>/聲紋.npz    the line prints (V: n x 192, ok: which lines have one)
  $MINUTES_HOME/voices/index.json + <file>.npy   the prints kept for each named person
The model (about 28 MB) is downloaded once by recorder/install.sh into $MINUTES_HOME/models/.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_setup import CONFIG  # noqa: E402
from i18n import t  # noqa: E402
from strings import EN, ZH  # noqa: E402

MODEL = CONFIG / 'models' / 'campplus.onnx'
VOICES = CONFIG / 'voices'
LINE = re.compile(r'\[(?:(\d+):)?(\d+):(\d{2})\]\s*(.*)')
GROUP_APART = 0.4          # cosine distance: two groups closer than this are one voice (tuned on a 3-person meeting)
KNOWN = 0.5                # a line this close to a named person's prints is that person
MARGIN = 0.05              # ... and clearly closer to that person than to anyone else named
MIN_GROUP = 20.0           # seconds of talk before a voice becomes 講者 X; smaller ones join the nearest voice
LONG_LINE = 3.0            # ... counted, for a new voice, from lines at least this long: the prints of 嗯 / 對 / 好 are
                           # noise, and a group made of them is no one (seven meetings of 2026-10: every such group
                           # was removed). A known voice needs MIN_GROUP of lines of 1.5 s or more (the grouping's pool)
SAME_VOICE = 0.25          # cosine distance: a group of unnamed lines this close to a named person's voice at this
                           # meeting is that person again (their short lines missed KNOWN; measured 0.01 to 0.16 on
                           # seven meetings, while two different people were never under 0.33)
SAME_MARGIN = 0.1          # ... and this much closer to them than to any other named person
KEEP = 300                 # prints kept per person, newest first


def lines_of(job: Path) -> list[tuple[float, float]]:
    """Each transcript line's (start, end) in seconds: from 逐字稿.json, or the next line's start."""
    starts = []
    for line in (job / '逐字稿.txt').read_text(encoding='utf-8').splitlines():
        m = LINE.match(line)
        if m:
            starts.append(int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3)))
    try:
        spans = json.loads((job / '逐字稿.json').read_text(encoding='utf-8'))['lines']
        if len(spans) == len(starts):
            return [(float(a), float(b)) for a, b in spans]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return [(s, starts[i + 1] if i + 1 < len(starts) else s + 5) for i, s in enumerate(starts)]


def prints(audio: Path, spans: list) -> tuple:
    import numpy as np
    import sherpa_onnx
    import soundfile as sf
    wav = Path(tempfile.mkdtemp()) / 'a.wav'
    subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', str(audio), str(wav)],
                   check=True, capture_output=True)
    x, rate = sf.read(str(wav), dtype='float32')
    wav.unlink(missing_ok=True)
    ex = sherpa_onnx.SpeakerEmbeddingExtractor(
        sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(MODEL), num_threads=8))
    V = np.zeros((len(spans), ex.dim), dtype=np.float32)
    ok = np.zeros(len(spans), dtype=bool)
    for i, (a, b) in enumerate(spans):
        if b - a < 0.6:
            continue
        if b - a > 20:                               # a long line: its middle 20 seconds are enough
            a, b = (a + b) / 2 - 10, (a + b) / 2 + 10
        s = ex.create_stream()
        s.accept_waveform(rate, x[int(a * rate):int(b * rate)])
        s.input_finished()
        v = np.array(ex.compute(s))
        n = np.linalg.norm(v)
        if n > 0:
            V[i], ok[i] = v / n, True
    return V, ok


# --- people the user named ---------------------------------------------------------------------

def _index() -> dict:
    try:
        return json.loads((VOICES / 'index.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _rows(file: str):
    """A person's kept prints and, for each, the meeting line it came from ("<job>:<line>")."""
    import numpy as np
    try:
        return np.load(VOICES / file), json.loads((VOICES / (file[:-4] + '.json')).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None, []


def remember(name: str, rows, tags: list[str], replace_job: str = ''):
    """Keep these prints for `name`, newest first. replace_job: what that meeting taught about `name` before
    is replaced by these (naming the same voice again)."""
    import numpy as np
    VOICES.mkdir(parents=True, exist_ok=True)
    index = _index()
    file = index.get(name) or hashlib.sha1(name.encode()).hexdigest()[:12] + '.npy'
    old, old_tags = _rows(file)
    if old is None:
        old, old_tags = np.zeros((0, rows.shape[1]), dtype=np.float32), []
    drop = set(tags)
    keep = [i for i, t in enumerate(old_tags)
            if t not in drop and not (replace_job and t.startswith(replace_job + ':'))]
    np.save(VOICES / file, np.concatenate([rows, old[keep]])[:KEEP].astype(np.float32))
    (VOICES / (file[:-4] + '.json')).write_text(json.dumps((list(tags) + [old_tags[i] for i in keep])[:KEEP]),
                                                 encoding='utf-8')
    index[name] = file
    (VOICES / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding='utf-8')


def forget(name: str, tags: list[str] = (), job: str = ''):
    """Take back prints of `name`: these lines ("<job>:<line>"), or everything one meeting taught."""
    import numpy as np
    file = _index().get(name)
    if not file:
        return
    rows, old_tags = _rows(file)
    if rows is None:
        return
    drop = set(tags)
    keep = [i for i, t in enumerate(old_tags) if t not in drop and not (job and t.startswith(job + ':'))]
    np.save(VOICES / file, rows[keep] if len(keep) else np.zeros((0, rows.shape[1]), dtype=np.float32))
    (VOICES / (file[:-4] + '.json')).write_text(json.dumps([old_tags[i] for i in keep]), encoding='utf-8')


def known_names() -> list[str]:
    """The people whose voices are kept, for the names the window suggests."""
    return list(_index())


def library() -> dict:
    """Every named person's kept prints."""
    out = {}
    for name, file in _index().items():
        rows, _ = _rows(file)
        if rows is not None and len(rows):
            out[name] = rows
    return out


def closeness(v, rows) -> float:
    """How much a print sounds like a person: the mean of its five best matches among their prints."""
    import numpy as np
    s = np.sort(rows @ v)[::-1]
    return float(s[:5].mean()) if len(s) else -1.0


# --- one meeting -------------------------------------------------------------------------------

def group(V, idx: list, dur) -> list[list[int]]:
    """Average-linkage grouping of the lines in idx, weighted by line length, until the closest two groups
    are GROUP_APART apart."""
    import numpy as np
    groups = [[i] for i in idx]
    sums = [V[i] * dur[i] for i in idx]
    while len(groups) > 1:
        C = np.array([s / np.linalg.norm(s) for s in sums])
        S = C @ C.T
        np.fill_diagonal(S, -9)
        a, b = np.unravel_index(int(np.argmax(S)), S.shape)
        if 1 - S[a, b] > GROUP_APART:
            break
        groups[a] += groups[b]
        sums[a] = sums[a] + sums[b]
        del groups[b], sums[b]
    return groups


def label(V, ok, spans, people: dict) -> dict:
    """Every line's voice: a named person when it clearly sounds like one, else a group of alike lines."""
    import numpy as np
    dur = np.array([b - a for a, b in spans])
    names = list(people)
    who = [''] * len(spans)
    for i in range(len(spans)):
        if not ok[i] or not names:
            continue
        scores = sorted(((closeness(V[i], people[n]), n) for n in names), reverse=True)
        if scores[0][0] >= KNOWN and (len(scores) == 1 or scores[0][0] - scores[1][0] >= MARGIN):
            who[i] = 'P:' + scores[0][1]
    def talk(idx, at_least: float) -> float:
        return sum(dur[i] for i in idx if dur[i] >= at_least)

    voices = {}                                       # key -> centroid
    for n in names:
        mine = [i for i in range(len(spans)) if who[i] == 'P:' + n]
        if not mine:
            continue
        if talk(mine, 1.5) < MIN_GROUP:               # a few short lines that sound like someone: not them, this time
            for i in mine:
                who[i] = ''
            continue
        c = sum(V[i] * dur[i] for i in mine)
        voices['P:' + n] = c / np.linalg.norm(c)
    named = list(voices)
    unknown = [i for i in range(len(spans)) if ok[i] and not who[i] and dur[i] >= 1.5]
    groups, left = group(V, unknown, dur), []
    for g in groups:
        c = sum(V[i] * dur[i] for i in g)
        c = c / np.linalg.norm(c)
        near = sorted((1 - float(voices[k] @ c), k) for k in named)
        if near and near[0][0] <= SAME_VOICE and (len(near) == 1 or near[1][0] - near[0][0] >= SAME_MARGIN):
            for i in g:                               # the named person's own voice, cut off by their short lines
                who[i] = near[0][1]
        elif talk(g, LONG_LINE) >= MIN_GROUP:
            key = f'G{len(voices)}'
            voices[key] = c
            for i in g:
                who[i] = key
        else:
            left.append((g, c))
    if not voices:                                    # nobody said three seconds in a row: the long groups still count
        for g, c in left:
            if talk(g, 0) >= MIN_GROUP:
                key = f'G{len(voices)}'
                voices[key] = c
                for i in g:
                    who[i] = key
    if not voices:
        return {'groups': {}, 'lines': [''] * len(spans), 'fixed': {}}
    keys = list(voices)
    C = np.array([voices[k] for k in keys])
    for i in range(len(spans)):                       # short lines and small groups: the nearest voice
        if not who[i] or who[i] not in voices:
            if ok[i]:
                who[i] = keys[int(np.argmax(C @ V[i]))]
    for i in range(len(spans)):                       # lines too short for a print: the line before them
        if not who[i]:
            j = next((k for k in range(i - 1, -1, -1) if who[k]), None)
            if j is None:
                j = next((k for k in range(i + 1, len(spans)) if who[k]), None)
            who[i] = who[j] if j is not None else keys[0]
    talk = {k: 0.0 for k in keys}
    for i, k in enumerate(who):
        talk[k] += dur[i]
    order = sorted(keys, key=lambda k: -talk[k])
    letter = {k: chr(ord('A') + n) for n, k in enumerate(order)}
    groups = {}
    for k in order:
        mine = [i for i in range(len(spans)) if who[i] == k]
        best = max(mine, key=lambda i: (dur[i] if dur[i] <= 20 else 0, -i))    # a clear stretch to listen to
        groups[letter[k]] = {'name': k[2:] if k.startswith('P:') else '', 'known': k.startswith('P:'),
                             'seconds': round(talk[k]), 'sample': [spans[best][0], spans[best][1]]}
    return {'groups': groups, 'lines': [letter[k] for k in who], 'fixed': {}}


def run(job: Path) -> dict:
    import numpy as np
    meta = json.loads((job / 'job.json').read_text(encoding='utf-8'))
    audio = job / (meta.get('audio') or '錄音.m4a')
    spans = lines_of(job)
    if not spans or not audio.exists():
        raise SystemExit(t('speakers_no_input'))
    V, ok = prints(audio, spans)
    np.savez(job / '聲紋.npz', V=V, ok=ok)
    result = label(V, ok, spans, library())
    (job / '講者.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    return result


def load(job: Path) -> dict:
    try:
        data = json.loads((job / '講者.json').read_text(encoding='utf-8'))
        return data if isinstance(data, dict) and data.get('groups') else {}
    except (OSError, ValueError):
        return {}


UNNAMED = (ZH['speaker'], EN['speaker'])    # a voice without a name: 講者 A in Chinese, Speaker A in English


def name_of(data: dict, i: int, word: str = ZH['speaker']) -> str:
    """The name, or 講者 X (`word` X), of transcript line i."""
    fixed = (data.get('fixed') or {}).get(str(i))
    if fixed:
        return fixed
    lines = data.get('lines') or []
    g = lines[i] if i < len(lines) else ''
    info = (data.get('groups') or {}).get(g) or {}
    if info.get('off'):                              # a voice taken off: the line has no speaker
        return ''
    return info.get('name') or (f'{word} {g}' if g else '')


def set_name(job: Path, group_key: str, name: str, line: int | None = None) -> dict:
    """The user named a voice: every line of a group, or one line. Keeps the prints for the next meeting."""
    import numpy as np
    data = load(job)
    name = name.strip()[:30]
    if not data or not name:
        raise SystemExit(t('speakers_none'))
    try:
        saved = np.load(job / '聲紋.npz')
        V, ok = saved['V'], saved['ok']
    except (OSError, ValueError, KeyError):
        V = ok = None
    spans = lines_of(job)

    def usable(i):
        return V is not None and i < len(ok) and bool(ok[i]) and spans[i][1] - spans[i][0] >= 1.5

    fixed = data.setdefault('fixed', {})
    if line is None:
        g = (data.get('groups') or {}).get(group_key)
        if g is None:
            raise SystemExit(t('speaker_missing'))
        before = g.get('name') or ''
        if before and before != name:
            forget(before, job=job.name)
        g['name'], g['known'] = name, True
        mine = [i for i, k in enumerate(data['lines']) if k == group_key and str(i) not in fixed and usable(i)][:60]
        if mine:
            remember(name, np.array([V[i] for i in mine]), [f'{job.name}:{i}' for i in mine], replace_job=job.name)
    else:
        if not 0 <= line < len(data.get('lines') or []):
            raise SystemExit(t('line_missing'))
        before = name_of(data, line)
        if before and before != name and not before.startswith(tuple(w + ' ' for w in UNNAMED)):
            forget(before, [f'{job.name}:{line}'])
        fixed[str(line)] = name
        if usable(line):
            remember(name, np.array([V[line]]), [f'{job.name}:{line}'])
    (job / '講者.json').write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    return data


# 「講者 B 負責文章，可能是 Nina」: what the minutes AI guessed about a voice (shown under 人員 in the window)
SPEAKER_GUESS = re.compile(r'^\s*(?:講者|Speaker)\s*((?-i:[A-Z]))(?![A-Za-z])\s*(.*?)\s*(?:推測是|推測為|應該是|可能是|is probably|'
                           r'is likely|probably|may be)\s*[「“"]?([^「」“”"，。,;；]+?)[」”"]?[。.]?\s*$', re.I)
NOT_A_NAME = re.compile(r'或|與|和|同一|講者|主持|與會|\b(?:and|or|same|host|speaker)\b', re.I)
NOT_A_ROLE = re.compile(r'從|根據|聽|看|依|\b(?:from|based|judging)\b', re.I)


def guessed(check) -> dict:
    """{voice letter: name} from the minutes AI's 待確認 lines; one name per voice, the first guess."""
    found = {}
    for raw in check or []:
        text = raw.get('text', '') if isinstance(raw, dict) else str(raw)
        m = SPEAKER_GUESS.match(text)
        name = m.group(3).strip() if m else ''
        if m and 0 < len(name) <= 30 and not NOT_A_NAME.search(name):
            found.setdefault(m.group(1), name)
    return found


def letter(group_key: str) -> re.Pattern:
    """講者 B / Speaker B in the minutes, not 講者 BC."""
    return re.compile(rf'(?:講者\s*{group_key}|Speaker\s+{group_key})(?![A-Za-z0-9])')


# Where each voice's name was written into the minutes, as the few characters around it (人員.json "spots"), so a
# later name for that voice changes only those places: not the same name said about someone else, not 陳怡君 when
# the voice was 怡君. Edits elsewhere in the minutes don't move them.
SPOT = 10


def _people_file(job: Path) -> dict:
    try:
        data = json.loads((job / '人員.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def _spot(md: str, at: int, size: int) -> list:
    return [md[max(0, at - SPOT):at], md[at + size:at + size + SPOT]]


def _found(md: str, name: str, spots) -> list[int]:
    """Where `name` stands at one of its spots now."""
    at = set()
    for pair in spots or []:
        if not (isinstance(pair, list) and len(pair) == 2 and name):
            continue
        whole, start = pair[0] + name + pair[1], 0
        while (i := md.find(whole, start)) >= 0:
            at.add(i + len(pair[0]))
            start = i + 1
    return sorted(at)


def _whole_name(md: str, name: str, others=()) -> list[int]:
    """Every place `name` is written as a name of its own: a Latin name as a whole word (Vin, not Vincent), a
    Chinese one not inside a longer name the meeting knows (怡君, not the one in 陳怡君)."""
    if re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", name):
        return [m.start() for m in re.finditer(rf'(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])', md)]
    longer = [o for o in others if o != name and name in o]
    at = []
    for m in re.finditer(re.escape(name), md):
        inside = any(md[m.start() - k:m.start() - k + len(o)] == o
                     for o in longer for k in range(len(o) - len(name) + 1) if o[k:k + len(name)] == name and m.start() >= k)
        if not inside:
            at.append(m.start())
    return at


def name_voice(job: Path, md: str, group_key: str, before: str, after: str, others=()) -> str:
    """The minutes with a voice called `after` where it was 講者 X or `before`; remembered in 人員.json. Only the
    voice's own places change: its letter, else the spots where its name was written. A name with no spots (older
    minutes) is changed wherever it stands as a name of its own, unless another voice goes by it too."""
    data = _people_file(job)
    names = {g: n for g, n in (data.get('speakers') or {}).items() if isinstance(n, str)}
    spots = data.get('spots') if isinstance(data.get('spots'), dict) else {}
    others_at = {g: _found(md, n, spots.get(g)) for g, n in names.items() if g != group_key}
    edits = [(m.start(), m.end()) for m in letter(group_key).finditer(md)]
    if before and before != after:
        own = _found(md, before, spots.get(group_key))
        if not own and not spots.get(group_key) and before not in [n for g, n in names.items() if g != group_key]:
            own = _whole_name(md, before, others)
        edits += [(i, i + len(before)) for i in own]
    edits = sorted(set(edits))
    kept = [e for k, e in enumerate(edits) if k == 0 or e[0] >= edits[k - 1][1]]   # no two over each other
    parts, last, mine, shift = [], 0, [], []
    for start, end in kept:
        parts += [md[last:start], after]
        mine.append(start + sum(len(after) - (e - s) for s, e in kept if e <= start))
        shift.append((end, len(after) - (end - start)))
        last = end
    new = ''.join(parts) + md[last:]
    moved = lambda i: i + sum(d for end, d in shift if end <= i)   # noqa: E731
    unnamed = bool(letter(group_key).fullmatch(after))
    spots = {g: [_spot(new, moved(i), len(names[g])) for i in at] for g, at in others_at.items() if at}
    if unnamed:                                       # back to 講者 X: nothing left to remember for this voice
        names.pop(group_key, None)
    elif after:
        names[group_key] = after
        spots[group_key] = [_spot(new, i, len(after)) for i in mine] or (data.get('spots') or {}).get(group_key) or []
    data['speakers'], data['spots'] = names, spots
    (job / '人員.json').write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    return new


def named_letters(job: Path, text: str) -> str:
    """Other text written with the minutes (the mail): 講者 X replaced by the name the minutes now use for it."""
    for g, n in (_people_file(job).get('speakers') or {}).items():
        if isinstance(n, str) and n:
            text = letter(g).sub(lambda _, n=n: n, text)
    return text


def guesses_into(job: Path, md: str, check) -> str:
    """Once the minutes are written: each voice nobody named gets the name the AI guessed (Vin 2026-10-17: the
    guess is the default; the user changes it under 人員). The voice itself is not remembered as that person, so
    a wrong guess does not label the next meeting. Two voices guessed as the same person keep their letters: one
    of the guesses is wrong, and one name for both could not be told apart later."""
    groups = load(job).get('groups') or {}
    given = {g.get('name') for g in groups.values() if g.get('name')}
    guesses = guessed(check)
    picked = {g: n for g, n in guesses.items() if g in groups and not groups[g].get('name') and not groups[g].get('off')
              and list(guesses.values()).count(n) == 1 and n not in given}
    for g, n in picked.items():
        md = name_voice(job, md, g, '', n)
    return md


def take_off(job: Path, group_key: str, off: bool = True) -> dict:
    """The user took a voice off (Vin 2026-10-19: 講者 C was the recording splitting one person in two, or a noise):
    it is no one, its lines keep their words without a speaker, and a name it had is forgotten. `off=False` puts it
    back as a 講者 X."""
    data = load(job)
    g = (data.get('groups') or {}).get(group_key)
    if not g:
        raise SystemExit(t('speaker_missing'))
    if off and g.get('name'):
        forget(g['name'], job=job.name)
        g['name'], g['known'] = '', False
    if off:
        g['off'] = True
    else:
        g.pop('off', None)
    (job / '講者.json').write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    return data


def clear_name(job: Path, group_key: str) -> dict:
    """The user took a person off the meeting: the voice they were given is a 講者 X again, and forgotten as them."""
    data = load(job)
    g = (data.get('groups') or {}).get(group_key)
    if not g:
        return data
    if g.get('name'):
        forget(g['name'], job=job.name)
    g['name'], g['known'] = '', False
    (job / '講者.json').write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    return data


def labelled_transcript(job: Path, word: str = ZH['speaker']) -> str:
    """The transcript with each line's speaker after the time: [mm:ss] Alex：..., for Claude. A voice without a
    name is `word` X (講者 A for Chinese minutes, Speaker A for English ones)."""
    data = load(job)
    out, i = [], 0
    for line in (job / '逐字稿.txt').read_text(encoding='utf-8').splitlines():
        m = LINE.match(line)
        if not m:
            continue
        who = name_of(data, i, word) if data else ''
        stamp = line[:line.index(']') + 1]
        out.append(f'{stamp} {who}：{m.group(4)}' if who else line)
        i += 1
    return '\n'.join(out) + '\n'


def available() -> bool:
    try:
        import sherpa_onnx  # noqa: F401
        import soundfile  # noqa: F401
    except ImportError:
        return False
    return MODEL.exists()


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    job = Path(sys.argv[1]).expanduser()
    if '--name' in sys.argv:
        at = sys.argv.index('--name')
        args = sys.argv[at + 1:]
        if len(args) < 2:
            sys.exit(__doc__)
        set_name(job, args[0], args[1], int(args[2]) if len(args) > 2 else None)
        print('NAMED')
        return
    if not available():
        sys.exit('NOT INSTALLED: run recorder/install.sh (sherpa-onnx and the voice model)')
    result = run(job)
    print('SPEAKERS', ', '.join(f'{k} {g["name"] or "?"} {g["seconds"]}s' for k, g in result['groups'].items()))


if __name__ == '__main__':
    import vlog
    vlog.run(main)
