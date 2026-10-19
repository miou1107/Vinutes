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
from datetime import datetime, timedelta
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
            if MEETING_ID.match(d.name) and (d / 'job.json').is_file():
                logs[d.name] = (d / 'log.txt').stat().st_size if (d / 'log.txt').is_file() else 0
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


# --- meetings recorded before the record began -----------------------------------------------------------------
# Their log.txt (read only up to its length when the record began) has the transcript's length and time, the write-up's
# start and end, and one line per AI edit; scripts.log has each edit's seconds and date; result.json the mail sent.
# Tokens and Google requests were never written down, so they stay unknown.

STAMP = re.compile(r'^\[(\d\d):(\d\d):(\d\d)\] (.*)$')
TRANSCRIPT = re.compile(r'^TRANSCRIPT .*\baudio (\d+(?::\d\d){1,2}), took (\d+)s\)')
SPEAKERS = re.compile(r'^SPEAKERS .*\((\d+)s\)$')
WRITE_START = re.compile(r'^(claude|codex|antigravity) in /')
WRITE_END = re.compile(r'^(claude|codex|antigravity) exited (-?\d+)$')
ASK = re.compile(r'^ask .*: exit (-?\d+)$')
RUN_START = re.compile(r'^\[([^\]]+)\] minutes_app\[(\d+)\] start (?:ask|quick) (\d{8}-\d{6})')
RUN_END = re.compile(r'^\[([^\]]+)\] minutes_app\[(\d+)\] end \w+, ([\d.]+) s')


def seconds_of(clock: str) -> int:
    return sum(int(n) * 60 ** i for i, n in enumerate(reversed(clock.split(':'))))


def edit_runs(before: str) -> dict[str, list[tuple[datetime, float]]]:
    """scripts.log (and the older .1): each AI edit of a meeting, when it ended and how long it took."""
    import vlog
    runs: dict[str, list[tuple[datetime, float]]] = {}
    started: dict[str, str] = {}
    for name in ('scripts.log.1', 'scripts.log'):
        try:
            text = (vlog.folder() / name).read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        for line in text.splitlines():
            found = RUN_START.match(line)
            if found:
                started[found[2]] = found[3]
                continue
            found = RUN_END.match(line)
            if found and found[2] in started and found[1] < before:
                try:
                    runs.setdefault(started.pop(found[2]), []).append((datetime.fromisoformat(found[1]), float(found[3])))
                except ValueError:
                    pass
    return runs


def from_log(mid: str, text: str, runs: list[tuple[datetime, float]]) -> list[dict]:
    """One old meeting's log.txt as records. Its lines carry only the time of day: the day is the meeting's, and
    moves on when the clock goes back by more than an hour."""
    when = datetime.strptime(mid, '%Y%m%d-%H%M%S').astimezone()
    found, write_began, last = [], None, when
    for line in text.splitlines():
        stamp = STAMP.match(line)
        if not stamp:
            continue
        at = last.replace(hour=int(stamp[1]), minute=int(stamp[2]), second=int(stamp[3]))
        if at < last - timedelta(hours=1):
            at += timedelta(days=1)
        last, said = at, stamp[4]
        if TRANSCRIPT.match(said):
            hit = TRANSCRIPT.match(said)
            found.append({'at': at, 'kind': 'transcribe', 's': int(hit[2]), 'audio': seconds_of(hit[1])})
        elif SPEAKERS.match(said):
            found.append({'at': at, 'kind': 'speakers', 's': int(SPEAKERS.match(said)[1])})
        elif WRITE_START.match(said):
            write_began = at
        elif WRITE_END.match(said):
            hit = WRITE_END.match(said)
            found.append({'at': at, 'kind': 'ai', 'task': 'write', 'ai': hit[1], 'ok': hit[2] == '0', 'limit': False,
                          's': round((at - write_began).total_seconds(), 1) if write_began else 0})
            write_began = None
        elif ASK.match(said):
            # its seconds and exact day from scripts.log: the run that ended within half a minute of this line
            match = next((r for r in runs if abs((r[0] - at).total_seconds()) % 86400 < 30
                          or abs((r[0] - at).total_seconds()) % 86400 > 86370), None)
            if match:                                 # the day is scripts.log's; the time stays this line's
                runs.remove(match)
                day = match[0].astimezone(at.tzinfo)
                at = at.replace(year=day.year, month=day.month, day=day.day)
            found.append({'at': at, 'kind': 'ai', 'task': 'edit', 'ai': 'claude', 'ok': ASK.match(said)[1] == '0',
                          'limit': False, 's': match[1] if match else 0})
    return found


def fill() -> list[dict]:
    """The meetings that existed when the record began, from their logs; worked out once and kept in
    usage/filled.jsonl, so a log rotated or a meeting deleted later changes nothing."""
    path = FOLDER / 'filled.jsonl'
    if path.is_file():
        return [e for e in events('', 'filled.jsonl')]
    started = begin()
    runs = edit_runs(started['at'])
    found = []
    for mid in sorted(started.get('logs', {})):
        d = RECORDINGS / mid
        if not MEETING_ID.match(mid) or not d.is_dir():
            continue
        try:
            with (d / 'log.txt').open('rb') as f:
                text = f.read(started['logs'][mid]).decode('utf-8', 'replace')
        except OSError:
            text = ''
        mine = from_log(mid, text, runs.get(mid, []))
        meta = read_json(d / 'job.json')
        if not any(e['kind'] == 'transcribe' for e in mine) and meta.get('started') and meta.get('ended'):
            try:
                length = (datetime.fromisoformat(meta['ended']) - datetime.fromisoformat(meta['started'])).total_seconds()
                mine.append({'at': datetime.fromisoformat(meta['started']), 'kind': 'transcribe',
                             'audio': max(0, round(length - float(meta.get('paused_seconds') or 0)))})
            except ValueError:
                pass
        result = read_json(d / 'result.json')
        if result.get('sent_at') and isinstance(result.get('mail'), dict):
            try:
                at = datetime.fromisoformat(result['sent_at'])
                if at.tzinfo is None:
                    at = at.astimezone()
                mine.append({'at': at, 'kind': 'mail', 'to': len(result['mail'].get('to') or [])})
            except ValueError:
                pass
        name = project(mid)
        for e in sorted(mine, key=lambda e: e['at']):
            found.append({**e, 'at': e['at'].isoformat(timespec='seconds'), 'meeting': mid, 'project': name,
                          'filled': True})
    try:
        FOLDER.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f'filled.{os.getpid()}.tmp')
        tmp.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in found), encoding='utf-8')
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass
        finally:
            tmp.unlink(missing_ok=True)
    except OSError:
        pass
    return found


# --- one month, by day and by project -----------------------------------------------------------------------------

def blank() -> dict:
    return {'meetings': 0, 'audio': 0, 'write': {'n': 0, 's': 0}, 'edit': {'n': 0, 's': 0}, 'test': {'n': 0, 's': 0},
            'tokens': 0, 'google': 0, 'mails': 0, 'disk': 0, 'limit': 0, 'failed': 0, 'filled': False}


def add(row: dict, e: dict):
    """One record into a row of the table."""
    row['filled'] = row['filled'] or bool(e.get('filled'))
    kind = e.get('kind')
    if kind == 'ai':
        run = row.get(e.get('task'), row['edit'])
        run['n'] += 1
        run['s'] = round(run['s'] + float(e.get('s') or 0), 1)
        tokens = e.get('tokens') if isinstance(e.get('tokens'), dict) else {}
        row['tokens'] += sum(int(tokens.get(k) or 0) for k in ('in', 'cached', 'out'))
        row['limit'] += 1 if e.get('limit') else 0
        row['failed'] += 0 if e.get('ok', True) else 1
    elif kind == 'google':
        row['google'] += int(e.get('n') or 0)
    elif kind == 'mail':
        row['mails'] += int(e.get('to') or 0)


def summary(month: str, meetings: list[dict]) -> dict:
    """The month (YYYY-MM): its total, one row per day, one per project with its meetings, and the months there
    are. `meetings`: what minutes_app knows of each meeting that still exists: id, date, title, project, disk
    (bytes), audio (seconds, from its start and end). A meeting counts on the day it was recorded, with its disk;
    everything else on the day it happened. Its project is the one it has now; a deleted meeting's is the one it had."""
    found = [e for e in events(month) + [e for e in fill() if str(e.get('at', '')).startswith(month)]
             if isinstance(e, dict)]
    facts = {m['id']: m for m in meetings}
    audio, last_project = {}, {}
    for e in found:
        mid = e.get('meeting') or ''
        if e.get('kind') == 'transcribe' and mid and e.get('audio') is not None:
            audio[mid] = int(e['audio'])
        if mid and mid not in facts:
            last_project[mid] = e.get('project') or ''
    recorded = {mid: f'{mid[:4]}-{mid[4:6]}-{mid[6:8]}' for mid in set(facts) | set(audio) | set(last_project)
                if MEETING_ID.match(mid)}
    recorded = {mid: day for mid, day in recorded.items() if day.startswith(month)}
    filled_meetings = {e.get('meeting') for e in found if e.get('filled')}

    def project_of(mid: str):
        if not mid:
            return None                                  # 其他: setup, nothing tied to a meeting
        return facts[mid]['project'] if mid in facts else last_project.get(mid, '')

    days: dict[str, dict] = {}
    projects: dict = {}
    items: dict[str, dict] = {}

    def item(mid: str) -> dict:
        if mid not in items:
            fact = facts.get(mid, {})
            items[mid] = {**blank(), 'id': mid, 'date': fact.get('date') or recorded.get(mid) or
                          f'{mid[:4]}-{mid[4:6]}-{mid[6:8]}', 'title': fact.get('title') or '', 'exists': mid in facts}
            projects.setdefault(project_of(mid), {**blank(), 'name': project_of(mid), 'items': []})['items'].append(items[mid])
        return items[mid]

    for mid, day in recorded.items():
        length = audio.get(mid, (facts.get(mid) or {}).get('audio') or 0)
        size = (facts.get(mid) or {}).get('disk') or 0
        for row in (days.setdefault(day, {**blank(), 'date': day}), item(mid)):
            row['meetings'] += 1
            row['audio'] += length
            row['disk'] += size
            row['filled'] = row['filled'] or mid in filled_meetings
        group = projects[project_of(mid)]
        group['meetings'] += 1
        group['audio'] += length
        group['disk'] += size
        group['filled'] = group['filled'] or mid in filled_meetings
    for e in found:
        if e.get('kind') in ('transcribe', 'speakers'):
            continue                                     # counted with the meeting above
        day = str(e.get('at', ''))[:10]
        add(days.setdefault(day, {**blank(), 'date': day}), e)
        mid = e.get('meeting') or ''
        if mid:
            add(item(mid), e)
        add(projects.setdefault(project_of(mid), {**blank(), 'name': project_of(mid), 'items': []}), e)

    total = blank()
    for row in days.values():
        for key in ('meetings', 'audio', 'tokens', 'google', 'mails', 'disk', 'limit', 'failed'):
            total[key] += row[key]
        for key in ('write', 'edit', 'test'):
            total[key] = {'n': total[key]['n'] + row[key]['n'], 's': round(total[key]['s'] + row[key]['s'], 1)}
        total['filled'] = total['filled'] or row['filled']
    for group in projects.values():
        group['items'].sort(key=lambda r: r['id'], reverse=True)
    named = sorted((p for p in projects.values() if p['name']), key=lambda p: p['name'])
    rest = [projects[k] for k in ('', None) if k in projects]
    months = {month, now().strftime('%Y-%m')} | {m['date'][:7] for m in meetings if m.get('date')}
    if FOLDER.is_dir():
        months |= {p.stem for p in FOLDER.glob('*.jsonl') if re.match(r'^\d{4}-\d\d$', p.stem)}
    months |= {str(e.get('at', ''))[:7] for e in fill() if e.get('at')}
    return {'month': month, 'months': sorted(months), 'total': total,
            'days': sorted(days.values(), key=lambda d: d['date'], reverse=True),
            'projects': named + rest}
