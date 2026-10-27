"""A project's brief (專案背景, Vin 2026-10-17, 10-19 and 10-28): the people and what each of them does, the project's
own terms with the ways the transcript mishears them, a few lines of background the user writes, and the folder on
this Mac where the project's files are (project_folders.py copies it for the AI). The AI that writes the minutes reads
every project's brief, decides which project the meeting is, and writes names and terms its way.

Where it lives, on this Mac only (one brief per person, never shared):
  $MINUTES_HOME/people.json   {project: [name, ...]}: the project's people, the same list the 人員 tab keeps
  $MINUTES_HOME/briefs.json   {project: {"people": {name: {"role", "heard", "added"}},
                                         "terms": [{"word", "meaning", "heard", "added", "learned"}], "background",
                                         "folder": "/Users/…/the project's folder"}}

Only what the user confirmed goes in: a name or a word Claude guessed waits under 待確認 until the user presses
確認無誤 or keeps an edit. The background is the user's own text; nothing here writes it but 儲存 in 專案設定.
The AI reads every project's brief, so internal-only notes (price floors, opinions about vendors) don't belong in it.

The window, the 15-second sync and an agent may all write these files at once: every change reads, changes and writes
under one lock, and a file that can't be read is set aside as *.bad instead of being taken for an empty one.
"""
import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from google_setup import CONFIG
from i18n import t as tr                          # t is a term in the loops below

PEOPLE = CONFIG / 'people.json'
BRIEFS = CONFIG / 'briefs.json'
FILE_NAME = '專案背景.md'                       # what the AI reads, in the folder it works in
LIMITS = {'name': 30, 'role': 20, 'word': 30, 'meaning': 30, 'heard': 30, 'background': 600}
_held = 0                                        # how deep this process is inside _locked()


def one_line(text, limit: int) -> str:
    return re.sub(r'\s+', ' ', str(text or '')).strip()[:limit]


def name_keys(name: str) -> set[str]:
    """陳怡君（Jessie） -> {陳怡君（jessie）, 陳怡君, jessie}: the ways the same person is written in minutes.
    A company calendar writes 黃建國(Vin(Vinston)): every part of a bracket inside a bracket counts too, so the
    voice Vinutes knows as Vin is this person (2026-10-21)."""
    whole = name.strip().casefold()
    keys = {whole}
    found = re.match(r'^(.*?)\s*[（(]\s*(.*?)\s*[）)]\s*$', whole)
    if found:
        for part in found.groups():
            if part:
                keys |= name_keys(part)
    return keys


def same_name(a: str, b: str) -> bool:
    return bool(name_keys(a) & name_keys(b))


def add_name(names: list[str], name: str) -> list[str]:
    name = one_line(name, LIMITS['name'])
    return names if not name or any(same_name(n, name) for n in names) else names + [name]


@contextmanager
def _locked():
    """One reader-changer-writer at a time across processes; a function inside another one doesn't lock twice."""
    global _held
    if _held:
        _held += 1
        try:
            yield
        finally:
            _held -= 1
        return
    CONFIG.mkdir(parents=True, exist_ok=True)
    with open(CONFIG / '.briefs.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _held = 1
        try:
            yield
        finally:
            _held = 0


def _read(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    try:                                         # kept for the user to look at, never written over as if empty
        path.replace(path.with_name(path.name + f'.{datetime.now():%Y%m%d-%H%M%S}.bad'))
    except OSError:
        pass
    return {}


def _write(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def _today() -> str:
    return f'{datetime.now():%Y-%m-%d}'


def _heard(value) -> list[str]:
    words = []
    for w in value if isinstance(value, list) else []:
        w = one_line(w, LIMITS['heard'])
        if w and w.casefold() not in (x.casefold() for x in words):
            words.append(w)
    return words[:10]


def _key(word) -> str:
    return one_line(word, 99).casefold()


def people_of(project: str) -> list[str]:
    names = _read(PEOPLE).get(project) if project else None
    return [n for n in names if isinstance(n, str)] if isinstance(names, list) else []


def save_people(project: str, names: list[str]):
    if not project:
        return
    with _locked():
        data = _read(PEOPLE)
        data[project] = names
        _write(PEOPLE, data)


# A room booking made in a company system names a department instead of inviting people. Who that department's
# people are is learned from the meetings the user confirmed (minutes_app.remember_roster): every name under 人員
# in a meeting whose calendar note names the department, kept as {department: {'people': [...], 'from':
# '2026-10-20 數據課週會'}}. The next meeting that names the department starts with them, and the minutes AI reads
# them (prototypes/department-people.html, Vin 2026-10-20). Nothing is ever taken off a roster by the app.
DEPARTMENTS = CONFIG / 'departments.json'


def roster(departments: list[str], before: str = '') -> tuple[list[str], str]:
    """The people these departments' earlier meetings confirmed, and the meeting the first of them was learned at.
    `before` (a date, 2026-10-20): only a roster learned at a meeting up to that day, so an older meeting opened
    later does not get people it never had."""
    data = _read(DEPARTMENTS)
    names, where = [], ''
    for dept in departments:
        entry = data.get(dept) if isinstance(data.get(dept), dict) else {}
        learned = entry.get('from') if isinstance(entry.get('from'), str) else ''
        if before and learned[:10] > before:
            continue
        for n in entry.get('people') or []:
            if isinstance(n, str):
                names = add_name(names, n)
        where = where or learned
    return names, where


def save_roster(department: str, names: list[str], where: str, replace: bool = False):
    """These names join the department's roster. `where` is the meeting doing this; a roster keeps the meeting
    that first taught it as its `from`. `replace`: that first meeting is correcting it, so the roster becomes
    exactly these names (the only way a name leaves)."""
    with _locked():
        data = _read(DEPARTMENTS)
        entry = data.get(department) if isinstance(data.get(department), dict) else {}
        merged = [] if replace else [n for n in (entry.get('people') or []) if isinstance(n, str)]
        for n in names:
            merged = add_name(merged, n)
        taught = entry.get('from') if isinstance(entry.get('from'), str) and entry.get('from') else where
        data[department] = {'people': merged, 'from': taught}
        _write(DEPARTMENTS, data)


def _entry(project: str) -> dict:
    found = _read(BRIEFS).get(project)
    found = found if isinstance(found, dict) else {}
    people = found.get('people') if isinstance(found.get('people'), dict) else {}
    terms = [t for t in found.get('terms') or [] if isinstance(t, dict) and t.get('word')]
    folder = found.get('folder') if isinstance(found.get('folder'), str) else ''
    return {'people': people, 'terms': terms, 'background': str(found.get('background') or ''), 'folder': folder}


def _save_entry(project: str, entry: dict):
    data = _read(BRIEFS)
    data[project] = entry
    _write(BRIEFS, data)


def _kept_as(people: dict, name: str) -> str | None:
    """The spelling the brief keeps a person under."""
    return next((k for k, v in people.items() if isinstance(v, dict) and same_name(k, name)), None)


def load(project: str) -> dict:
    """The brief as the window shows it: the project's people in the 人員 order, each with what they do."""
    entry = _entry(project)
    people = []
    for name in people_of(project):
        info = entry['people'].get(_kept_as(entry['people'], name) or '', {})
        people.append({'name': name, 'role': one_line(info.get('role'), LIMITS['role']),
                       'heard': _heard(info.get('heard')), 'added': info.get('added') or ''})
    terms = [{'word': one_line(t['word'], LIMITS['word']), 'meaning': one_line(t.get('meaning'), LIMITS['meaning']),
              'heard': _heard(t.get('heard')), 'added': t.get('added') or ''} for t in entry['terms']]
    return {'project': project, 'people': people, 'terms': terms,
            'background': entry['background'][:LIMITS['background']], 'folder': entry['folder']}


def save(project: str, brief: dict) -> dict:
    """The window's 儲存: the people (in its order), the terms and the background as the user left them.
    What the window doesn't send stays as it is; what changed on disk while the window was open stays too: a person
    or term the window never showed (brief['seen'] lists what it showed) is kept, and the transcript's spellings
    (heard) always come from disk, since the window can't edit them."""
    if not project or not isinstance(brief, dict):
        return load(project)
    with _locked():
        entry = _entry(project)
        seen = brief.get('seen') if isinstance(brief.get('seen'), dict) else {}
        if isinstance(brief.get('people'), list):
            shown = [n for n in seen.get('people') or [] if isinstance(n, str)]
            names, people = [], {}
            for p in brief['people']:
                name = one_line(p.get('name'), LIMITS['name']) if isinstance(p, dict) else ''
                if not name or any(same_name(n, name) for n in names):
                    continue
                names.append(name)
                before = entry['people'].get(_kept_as(entry['people'], name) or '', {})
                people[name] = {'role': one_line(p.get('role'), LIMITS['role']), 'heard': _heard(before.get('heard')),
                                'added': before.get('added') or _today()}
            if 'seen' in brief:                      # added elsewhere since the window opened: still the project's
                for name in people_of(project):
                    if not any(same_name(name, s) for s in shown) and not any(same_name(name, n) for n in names):
                        names.append(name)
                        kept = _kept_as(entry['people'], name)
                        if kept:
                            people[name] = entry['people'][kept]
            save_people(project, names)
            entry['people'] = people
        if isinstance(brief.get('terms'), list):
            shown = {_key(w) for w in seen.get('terms') or []}
            terms = []
            for t in brief['terms']:
                word = one_line(t.get('word'), LIMITS['word']) if isinstance(t, dict) else ''
                if not word or _key(word) in {_key(x['word']) for x in terms}:
                    continue
                before = next((x for x in entry['terms'] if _key(x.get('word')) == _key(word)), {})
                terms.append({'word': word, 'meaning': one_line(t.get('meaning'), LIMITS['meaning']),
                              'heard': _heard(before.get('heard')), 'added': before.get('added') or _today()})
            if 'seen' in brief:
                taken = {_key(x['word']) for x in terms}
                terms += [x for x in entry['terms'] if _key(x.get('word')) not in shown | taken]
            entry['terms'] = terms
        if isinstance(brief.get('background'), str):
            entry['background'] = brief['background'].strip()[:LIMITS['background']]
        if isinstance(brief.get('folder'), str):     # '' takes the folder off; anything else must be a folder here
            folder = brief['folder'].strip()
            if folder and not Path(folder).expanduser().is_dir():
                raise SystemExit(tr('bad_folder'))
            entry['folder'] = str(Path(folder).expanduser().resolve()) if folder else ''
        _save_entry(project, entry)
        return load(project)


def add_person(project: str, name: str, role: str = ''):
    """A name the user confirmed: on the project's list, and what they do if the brief has nothing yet."""
    name = one_line(name, LIMITS['name'])
    if not project or not name:
        return
    with _locked():
        save_people(project, add_name(people_of(project), name))
        entry = _entry(project)
        kept = _kept_as(entry['people'], name) or name
        info = dict(entry['people'].get(kept) or {})
        if role and not info.get('role'):
            info['role'] = one_line(role, LIMITS['role'])
        info.setdefault('added', _today())
        entry['people'][kept] = info
        _save_entry(project, entry)


def _person_for(project: str, meant: str) -> str | None:
    """The one person on the project's list `meant` is; a word two people share (a role like PM) is nobody's."""
    found = [n for n in people_of(project) if same_name(n, meant)]
    return found[0] if len(found) == 1 else None


def add_heard(project: str, heard: str, meant: str):
    """The transcript wrote `meant` as `heard`: kept on the person or the term it is, else a new term."""
    heard, meant = one_line(heard, LIMITS['heard']), one_line(meant, LIMITS['word'])
    if not project or not heard or not meant:
        return
    with _locked():
        entry = _entry(project)
        person = _person_for(project, meant)
        if person:
            kept = _kept_as(entry['people'], person) or person
            info = dict(entry['people'].get(kept) or {})
            info['heard'] = _heard((info.get('heard') or []) + [heard])
            info.setdefault('added', _today())
            entry['people'][kept] = info
        else:
            term = next((t for t in entry['terms'] if _key(t.get('word')) == _key(meant)), None)
            if term is None:
                term = {'word': meant, 'meaning': '', 'heard': [], 'added': _today(), 'learned': True}
                entry['terms'].append(term)
            term['heard'] = _heard((term.get('heard') or []) + [heard])
        _save_entry(project, entry)


def remove_heard(project: str, heard: str, meant: str):
    """Takes back add_heard: the spelling comes off the person or term it went on; a term that only that learning
    made, and that has nothing else on it now, goes too. A project with no brief is left alone."""
    with _locked():
        if not project or project not in _read(BRIEFS):
            return
        entry = _entry(project)
        drop = lambda words: [w for w in words or [] if w.casefold() != heard.casefold()]   # noqa: E731
        person = _person_for(project, meant)
        kept = _kept_as(entry['people'], person) if person else None
        if kept:
            entry['people'][kept]['heard'] = drop(entry['people'][kept].get('heard'))
        for term in entry['terms']:
            if _key(term.get('word')) == _key(meant):
                term['heard'] = drop(term.get('heard'))
        entry['terms'] = [t for t in entry['terms'] if not (t.get('learned') and _key(t.get('word')) == _key(meant)
                                                            and not t.get('heard') and not t.get('meaning'))]
        _save_entry(project, entry)


def rename(old: str, new: str) -> list[str]:
    """A renamed project keeps its people and brief; two projects put together keep both, the new name's first.
    Answers the project's people after."""
    with _locked():
        names = people_of(new)
        for n in people_of(old):
            names = add_name(names, n)
        data = _read(PEOPLE)
        if old in data:
            data.pop(old)
            data[new] = names
            _write(PEOPLE, data)
        briefs = _read(BRIEFS)
        if old in briefs:
            gone, into = _entry(old), _entry(new)
            for name, info in gone['people'].items():
                kept = _kept_as(into['people'], name)
                if kept is None:
                    into['people'][name] = info
                elif isinstance(info, dict):
                    mine = into['people'][kept]
                    mine['heard'] = _heard((mine.get('heard') or []) + (info.get('heard') or []))
                    mine['role'] = mine.get('role') or info.get('role') or ''
            for term in gone['terms']:
                same = next((t for t in into['terms'] if _key(t.get('word')) == _key(term.get('word'))), None)
                if same is None:
                    into['terms'].append(term)
                else:
                    same['heard'] = _heard((same.get('heard') or []) + (term.get('heard') or []))
                    same['meaning'] = same.get('meaning') or term.get('meaning') or ''
            into['background'] = '\n'.join(b for b in (into['background'], gone['background']) if b)
            into['folder'] = into['folder'] or gone['folder']
            briefs.pop(old)
            briefs[new] = into
            _write(BRIEFS, briefs)
        return names


def folders() -> dict[str, Path]:
    """Each project's folder that is still there, by project."""
    found = {}
    for project, entry in _read(BRIEFS).items():
        folder = entry.get('folder') if isinstance(entry, dict) else None
        if isinstance(project, str) and project and isinstance(folder, str) and folder and Path(folder).is_dir():
            found[project] = Path(folder)
    return found


def projects() -> list[str]:
    """Every project with a brief or a people list."""
    people, briefs = _read(PEOPLE), _read(BRIEFS)
    return [p for p in list(people) + [p for p in briefs if p not in people] if isinstance(p, str) and p]


def markdown(only: str | None = None, lang: str = 'zh-TW') -> str:
    """The briefs as the AI reads them; empty when there is nothing to tell."""
    zh = lang != 'en'
    sep, colon = ('、', '：') if zh else (', ', ': ')
    heard_as = (lambda w: f"（逐字稿常聽成：{sep.join(w)}）") if zh else (lambda w: f" (the transcript often has: {sep.join(w)})")
    parts = []
    for project in [only] if only else projects():
        b = load(project)
        if not (b['people'] or b['terms'] or b['background']):
            continue
        lines = [f'## {project}', '']
        for title, rows, first, second in (('人員：' if zh else 'People:', b['people'], 'name', 'role'),
                                           ('名詞：' if zh else 'Terms:', b['terms'], 'word', 'meaning')):
            if rows:
                lines.append(title)
                lines += [f"- {r[first]}" + (f"{colon}{r[second]}" if r[second] else '') + (heard_as(r['heard']) if r['heard'] else '')
                          for r in rows]
                lines.append('')
        if b['background']:
            lines += ['背景：' if zh else 'Background:', b['background'], '']
        parts.append('\n'.join(lines).rstrip())
    if not parts:
        return ''
    head = ('# 專案背景\n\n使用者確認過的每個專案的人員、名詞與背景。先判斷這場會議屬於哪一個專案，'
            '人名、誰負責什麼、名詞的寫法照那個專案的專案背景；別的專案的人和事不要寫進這場紀錄。'
            '專案背景上的人是專案成員，不是這場會議的與會者。\n'
            if zh else
            '# Project briefs\n\nWhat the user confirmed about each project: its people, terms and background. Decide which '
            'project this meeting belongs to and write names, who does what and terms as its brief has them; nothing '
            "from another project's brief goes into these minutes. The people in a brief belong to the project; they "
            "are not this meeting's attendees.\n")
    return head + '\n' + '\n\n'.join(parts) + '\n'
