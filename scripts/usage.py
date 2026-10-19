"""What Vinutes uses, meeting by meeting: AI runs (seconds and tokens), Google requests, emails sent, audio
transcribed. The window's 用量統計 adds disk and shows it by day and by project (minutes_app.py usage).

The record: $MINUTES_HOME/usage/<YYYY-MM>.jsonl, one JSON object per line, appended whole by each process:
  {"at", "kind", "meeting", "project", ...}
  kind ai          task (write | edit | test), ai, s (seconds), ok, limit (stopped by the AI's usage limit),
                   tokens {"in", "cached", "out"} when the AI said
  kind google      api (docs | drive | gmail | calendar | people | other), n requests, bytes uploaded; one line per
                   API per process, written when the process ends
  kind mail        to (recipients)
  kind transcribe  s, audio (seconds of recording)
  kind speakers    s
"meeting" is the recording folder's name ($VINUTES_MEETING, set by minutes_app.py and auto_minutes.py; '' for
setup); "project" is the meeting's project at that moment, kept for meetings deleted later. Only ids and numbers:
no titles, names, addresses or requests.

usage/started.json: when the record began and how long each meeting's log.txt was then. Meetings recorded before
are filled in once from their logs (fill), never counting twice what the record has.
"""
from __future__ import annotations

import atexit
import json
import os
import re
from datetime import datetime
from pathlib import Path

from google_setup import CONFIG

FOLDER = CONFIG / 'usage'
RECORDINGS = CONFIG / 'recordings'
MEETING_ID = re.compile(r'^\d{8}-\d{6}$')
COUNTS: dict[str, list[int]] = {}           # this process's Google requests: api -> [requests, bytes uploaded]


def now() -> datetime:
    return datetime.now().astimezone()


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def meeting() -> str:
    found = os.environ.get('VINUTES_MEETING', '')
    return found if MEETING_ID.match(found) else ''


def project(mid: str) -> str:
    """The meeting's project as the window shows it: the one the user set (分類.json), else the AI's."""
    if not mid:
        return ''
    d = RECORDINGS / mid
    mine = read_json(d / '分類.json')
    name = mine['project'] if isinstance(mine.get('project'), str) else read_json(d / 'result.json').get('project')
    return re.sub(r'\s+', ' ', str(name or '')).strip()[:30]


def begin() -> dict:
    """usage/started.json, written once: the moment the record began, and each meeting's log.txt length then."""
    path = FOLDER / 'started.json'
    known = read_json(path)
    if known.get('at'):
        return known
    logs = {}
    if RECORDINGS.is_dir():
        for d in RECORDINGS.iterdir():
            if MEETING_ID.match(d.name) and (d / 'log.txt').is_file():
                logs[d.name] = (d / 'log.txt').stat().st_size
    started = {'at': now().isoformat(timespec='seconds'), 'logs': logs}
    try:
        FOLDER.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f'started.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(started, ensure_ascii=False), encoding='utf-8')
        try:
            os.link(tmp, path)                       # the first process to get here wins; the others read its file
        except FileExistsError:
            pass
        finally:
            tmp.unlink(missing_ok=True)
    except OSError:
        return started
    return read_json(path) or started


def record(kind: str, **fields):
    """One line in this month's record. Never raises: counting must not stop the meeting's work."""
    try:
        begin()
        mid = meeting()
        line = {'at': now().isoformat(timespec='seconds'), 'kind': kind, 'meeting': mid, 'project': project(mid),
                **fields}
        FOLDER.mkdir(parents=True, exist_ok=True)
        fd = os.open(FOLDER / f'{line["at"][:7]}.jsonl', os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(line, ensure_ascii=False) + '\n').encode('utf-8'))   # whole lines beside others
        finally:
            os.close(fd)
    except Exception:
        pass


def events(month: str, name: str | None = None) -> list[dict]:
    """The record's lines for a month (YYYY-MM), or of usage/<name>; a broken line is skipped."""
    found = []
    try:
        text = (FOLDER / (name or f'{month}.jsonl')).read_text(encoding='utf-8')
    except OSError:
        return found
    for raw in text.splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if isinstance(line, dict) and str(line.get('at', '')).startswith(month):
            found.append(line)
    return found


def limited(text: str) -> bool:
    """The AI said its usage limit was reached, in the words auto_minutes.friendly knows."""
    import auto_minutes
    low = (text or '').lower()
    return bool(auto_minutes.limit_until(text or '')) or any(
        key.lower() in low for key, words in auto_minutes.FRIENDLY if words == 'err_rate_limit')


def ai_run(task: str, ai: str, seconds: float, code: int, tokens: dict | None, text: str = ''):
    fields = {'task': task, 'ai': ai, 's': round(seconds, 1), 'ok': code == 0,
              'limit': bool(code) and limited(text)}
    if tokens:
        fields['tokens'] = tokens
    record('ai', **fields)


def api_of(url: str) -> str:
    host = re.sub(r'^https?://', '', url).split('/')[0]
    if host == 'docs.googleapis.com':
        return 'docs'
    if host == 'gmail.googleapis.com':
        return 'gmail'
    if host == 'people.googleapis.com':
        return 'people'
    if '/drive/' in url:
        return 'drive'
    if '/calendar/' in url:
        return 'calendar'
    return 'other'


def google(url: str, sent: int = 0):
    """One request to a Google API; written with the others of this process when it ends."""
    if not COUNTS:
        atexit.register(flush)
    count = COUNTS.setdefault(api_of(url), [0, 0])
    count[0] += 1
    count[1] += sent or 0


def flush():
    for api, (n, sent) in list(COUNTS.items()):
        record('google', api=api, n=n, **({'bytes': sent} if sent else {}))
    COUNTS.clear()


def mail(recipients: int):
    record('mail', to=recipients)
