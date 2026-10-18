"""Vinutes as an MCP server: Claude Code (or another agent) looks things up in past meetings, and changes them when
the user asks, the same changes the meeting window makes (issue #4, 2026-10-18).

  claude mcp add --scope user vinutes -- <Vinutes' python> <this folder>/mcp_server.py

It speaks MCP over stdin/stdout (JSON-RPC, one message per line) and needs nothing beyond Vinutes' own Python.
Every meeting can be read, from any folder (Vin 2026-10-18); archived ones only when named. Writing goes through
minutes_app.py's own commands, so the Google Doc follows and the meeting's 操作紀錄 names "Claude Code". No tool
deletes a meeting or sends mail. The log (scripts.log) says which tool ran and how many meetings it returned,
never the words searched for or any text of a meeting.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import minutes_app as app  # noqa: E402
import vlog  # noqa: E402

PROTOCOLS = ('2025-06-18', '2025-03-26', '2024-11-05')
ACTOR = 'Claude Code'
MOST_MEETINGS = 20
MOST_HITS = 6
MOST_LINES = 600


class Refused(Exception):
    """A tool call that can't be done; the agent is told why."""


# --- reading -------------------------------------------------------------------------------------

def jobs(include_archived=False) -> list:
    return [j for j in app.all_jobs() if include_archived or not j.archived]


def job_of(meeting: str):
    name = Path(str(meeting or '')).name
    if not re.fullmatch(r'\d{8}-\d{6}', name) or not (app.RECORDINGS / name / 'job.json').is_file():
        raise Refused(f'No meeting {meeting!r}. Meeting ids look like 20261016-153005; list_meetings gives them.')
    return app.Job(app.RECORDINGS / name)


def ready(job) -> bool:
    return job.status_word() in ('ready', 'sent')


def people_of(job) -> list[str]:
    try:
        return app.meeting_people(job)
    except Exception:
        return []


def card(job) -> dict:
    s = app.summary(job)
    return {'meeting': job.id, 'date': s['date'], 'time': s['time'] + (f"–{s['ended_time']}" if s['ended_time'] else ''),
            'title': s['title'], 'project': s['project'], 'tags': s['tags'], 'status': s['status'],
            'people': people_of(job), 'sent': bool(s['sent_at']), 'archived': s['archived'],
            'doc_url': job.result.get('doc_url') or '', 'when': job.result.get('when') or '',
            'place': job.result.get('place') or ''}


def keys(text: str) -> str:
    return (text or '').casefold()


def picked(args: dict) -> list:
    """The meetings the filters leave, newest first."""
    project, tag = keys(args.get('project')), keys(args.get('tag'))
    person = (args.get('person') or '').strip()
    since, until = (args.get('since') or '')[:10], (args.get('until') or '')[:10]
    found = []
    for job in jobs(bool(args.get('include_archived'))):
        s = app.summary(job)
        if project and project not in keys(s['project']):
            continue
        if tag and not any(tag == keys(t) for t in s['tags']):
            continue
        if since and s['date'] < since or until and s['date'] > until:
            continue
        if person and not any(app.same_name(person, n) or keys(person) in keys(n) for n in people_of(job)):
            continue
        found.append(job)
    return found


def lines_of(job) -> list[tuple[str, str, str]]:
    """(source, where, text) for every line of the minutes and the transcript."""
    rows = [('minutes', '', line) for line in job.md.splitlines() if line.strip()] if ready(job) and job.md_path else []
    for item in app.transcript(job):
        rows.append(('transcript', item['at'], f"{item.get('who') or ''}：{item['text']}" if item.get('who') else item['text']))
    return rows


def search_meetings(args: dict) -> dict:
    words = [keys(w) for w in str(args.get('query') or '').split() if w.strip()]
    if not words:
        raise Refused('query is empty.')
    most = max(1, min(int(args.get('limit') or 10), MOST_MEETINGS))
    hits = []
    for job in picked(args):
        head = keys(' '.join([job.result.get('title') or '', app.project_of(job), *app.tags_of(job)]))
        found = []
        for source, at, text in lines_of(job):
            low = keys(text)
            if all(w in low or w in head for w in words) and any(w in low for w in words):
                found.append({'source': source, **({'at': at} if at else {}), 'text': text.strip()[:300]})
        if found or all(w in head for w in words):
            hits.append({**card(job), 'matches': found[:MOST_HITS], 'more_matches': max(0, len(found) - MOST_HITS)})
        if len(hits) >= most:
            break
    return {'meetings': hits, 'note': 'Read a whole meeting with get_minutes, or what was said with get_transcript.'}


def list_meetings(args: dict) -> dict:
    most = max(1, min(int(args.get('limit') or MOST_MEETINGS), 100))
    found = picked(args)
    return {'meetings': [card(j) for j in found[:most]], 'total': len(found)}


def get_minutes(args: dict) -> dict:
    job = job_of(args.get('meeting'))
    if not ready(job):
        raise Refused(f'Meeting {job.id} is not written up yet ({job.status_word()}).')
    if not job.md_path:
        raise Refused(f'The minutes file of meeting {job.id} was moved or renamed outside Vinutes.')
    return {**card(job), 'minutes': job.md, 'to_fill': [i['label'] for i in app.todo_items(job, job.md)],
            'next_meeting': job.result.get('next_meeting') or ''}


def seconds(value) -> int | None:
    if value in (None, ''):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    parts = [int(p) for p in re.findall(r'\d+', str(value))]
    total = 0
    for p in parts:
        total = total * 60 + p
    return total if parts else None


def get_transcript(args: dict) -> dict:
    job = job_of(args.get('meeting'))
    start, end = seconds(args.get('start')), seconds(args.get('end'))
    lines = [i for i in app.transcript(job) if (start is None or i['sec'] >= start) and (end is None or i['sec'] <= end)]
    shown = [f"[{i['at']}] {i['who']}：{i['text']}" if i.get('who') else f"[{i['at']}] {i['text']}" for i in lines]
    return {'meeting': job.id, 'title': job.result.get('title') or '', 'lines': shown[:MOST_LINES],
            'more_lines': max(0, len(shown) - MOST_LINES),
            'speakers': {k: v for k, v in app.speakers_shown(job).items()} if lines else {}}


def list_projects(args: dict) -> dict:
    projects: dict[str, dict] = {}
    for job in jobs(bool(args.get('include_archived'))):
        s = app.summary(job)
        name = s['project'] or ''
        p = projects.setdefault(name, {'project': name or '(none)', 'meetings': 0, 'last': '', 'recent': []})
        p['meetings'] += 1
        if s['date'] > p['last']:
            p['last'] = s['date']
        if len(p['recent']) < 3:
            p['recent'].append({'meeting': job.id, 'date': s['date'], 'title': s['title']})
    for p in projects.values():
        p['people'] = app.project_people(p['project']) if p['project'] != '(none)' else []
    return {'projects': sorted(projects.values(), key=lambda p: p['last'], reverse=True)}


ACTIONS = re.compile(r'^##\s.*(?:行動方案|Action).*$', re.M | re.I)
OPEN = re.compile(r'^##\s.*(?:待確認|To Be Confirmed|Open Questions).*$', re.M | re.I)


def section(md: str, heading: re.Pattern) -> str:
    head = heading.search(md)
    if not head:
        return ''
    rest = md[head.end():]
    stop = re.search(r'^##\s', rest, re.M)
    return rest[:stop.start() if stop else len(rest)].strip()


def open_items(args: dict) -> dict:
    """Per meeting: the action items, the questions left open, the blanks still to fill, the next meeting."""
    most = max(1, min(int(args.get('limit') or 5), MOST_MEETINGS))
    out = []
    for job in picked(args):
        if not ready(job) or not job.md_path:
            continue
        md = job.md
        out.append({'meeting': job.id, 'date': app.summary(job)['date'], 'title': job.result.get('title') or '',
                    'project': app.project_of(job), 'actions': section(md, ACTIONS),
                    'to_confirm': section(md, OPEN),
                    'to_fill': [i['label'] for i in app.todo_items(job, md)],
                    'next_meeting': job.result.get('next_meeting') or ''})
        if len(out) >= most:
            break
    return {'meetings': out}


# --- writing: minutes_app.py's own commands, logged as Claude Code ---------------------------------

def run_app(job, *argv) -> dict:
    if not ready(job):
        raise Refused(f'Meeting {job.id} is being written up or failed ({job.status_word()}); it can be changed '
                      'once its minutes are ready.')
    done = subprocess.run([sys.executable, str(HERE / 'minutes_app.py'), argv[0], str(job.dir), *argv[1:]],
                          capture_output=True, text=True, timeout=5 * 60,
                          env={**os.environ, 'VINUTES_ACTOR': ACTOR, 'VINUTES_NO_WAIT': '1'})
    if done.returncode:
        said = (done.stderr.strip() or done.stdout.strip()).splitlines()
        raise Refused(said[-1] if said else f'Vinutes could not make the change (exit {done.returncode}).')
    last = next((line for line in reversed(done.stdout.splitlines()) if line.startswith('JSON ')), '')
    return json.loads(last[5:]) if last else {}


def changed(job, answer: dict) -> dict:
    job = app.Job(job.dir)                           # read again: the command changed it
    sent = bool(job.result.get('sent_at'))
    note = []
    if answer.get('held'):
        note.append('The change is saved on this Mac; the Google Doc gets it when Vinutes is back online or the '
                    'Doc is free again.')
    if answer.get('warning'):
        note.append(str(answer['warning']))
    if sent:
        note.append('These minutes were already mailed: the people who got them see the new text in the Google Doc, '
                    'without a new mail.')
    return {'ok': True, 'meeting': job.id, 'title': job.result.get('title') or '', 'sent': sent,
            'doc_url': job.result.get('doc_url') or '', 'notes': note}


def name_speaker(args: dict) -> dict:
    job = job_of(args.get('meeting'))
    group = str(args.get('speaker') or '').strip().upper().removeprefix('講者').removeprefix('SPEAKER').strip()
    name = app.one_line(args.get('name'), 30)
    voices = {v['group'] for v in app.voices_view(job)}
    if group not in voices:
        raise Refused(f'Meeting {job.id} has no speaker {group or "?"}; its speakers are {", ".join(sorted(voices)) or "none"}.')
    if not name:
        raise Refused('name is empty.')
    return changed(job, run_app(job, 'speaker', group, name))


def add_note(args: dict) -> dict:
    job = job_of(args.get('meeting'))
    return changed(job, run_app(job, 'note', str(args.get('text') or '')))


def replace_text(args: dict) -> dict:
    job = job_of(args.get('meeting'))
    old, new = str(args.get('old') or ''), str(args.get('new') or '')
    if not old:
        raise Refused('old is empty.')
    return changed(job, run_app(job, 'replace', old, new))


def set_tags(args: dict) -> dict:
    job = job_of(args.get('meeting'))
    tags = args.get('tags')
    if not isinstance(tags, list):
        raise Refused('tags must be a list of words.')
    if not ready(job):
        raise Refused(f'Meeting {job.id} is not written up yet ({job.status_word()}).')
    run_app(job, 'tags', json.dumps(tags, ensure_ascii=False))
    return {**changed(job, {}), 'tags': app.tags_of(app.Job(job.dir))}


def set_project(args: dict) -> dict:
    job = job_of(args.get('meeting'))
    run_app(job, 'move', app.one_line(args.get('project'), 30))
    return {**changed(job, {}), 'project': app.project_of(app.Job(job.dir))}


def text(desc: str) -> dict:
    return {'type': 'string', 'description': desc}


MEETING = text('The meeting id, e.g. 20261016-153005 (from list_meetings or search_meetings).')
FILTERS = {'project': text('Only meetings of this project (part of the name is enough).'),
           'tag': text('Only meetings with this tag.'),
           'person': text('Only meetings this person was at (invited, on the attendees line, or a named voice).'),
           'since': text('Only meetings on or after this date, YYYY-MM-DD.'),
           'until': text('Only meetings on or before this date, YYYY-MM-DD.'),
           'include_archived': {'type': 'boolean', 'description': 'Also archived meetings (default false).'}}

TOOLS = [
    ('search_meetings', search_meetings, False,
     'Search past meetings recorded with Vinutes: their minutes and what was said (the transcript). Every word of the '
     'query must appear in a line (or in the title, project or tags). Returns each meeting with its matching lines. '
     'Minutes are mostly in Traditional Chinese; search with the words people would have used.',
     {'query': text('Words to find, separated by spaces.'), **FILTERS,
      'limit': {'type': 'integer', 'description': 'At most this many meetings (default 10).'}}, ['query']),
    ('list_meetings', list_meetings, False,
     'List past meetings, newest first: date, time, title, project, tags, people, whether the minutes were mailed, '
     'and the Google Doc link.',
     {**FILTERS, 'limit': {'type': 'integer', 'description': 'At most this many (default 20).'}}, []),
    ('get_minutes', get_minutes, False,
     "One meeting's minutes in full (Markdown), with the blanks still to fill and the next meeting.",
     {'meeting': MEETING}, ['meeting']),
    ('get_transcript', get_transcript, False,
     'What was said in one meeting, line by line with the time and the speaker; optionally only from start to end '
     '(mm:ss or seconds).',
     {'meeting': MEETING, 'start': text('From this time, mm:ss.'), 'end': text('Up to this time, mm:ss.')}, ['meeting']),
    ('list_projects', list_projects, False,
     'The projects meetings belong to, with how many meetings, the latest date, the people and the recent meetings.',
     {'include_archived': FILTERS['include_archived']}, []),
    ('open_items', open_items, False,
     "Action items (each meeting's action section), blanks still to fill and next meetings, newest meetings first.",
     {**FILTERS, 'limit': {'type': 'integer', 'description': 'At most this many meetings (default 5).'}}, []),
    ('name_speaker', name_speaker, True,
     'Say who a voice in a meeting is (講者 B is Mia). The minutes and the Google Doc use the name where that voice '
     'is meant, and Vinutes recognises the voice in later meetings. Only when the user asked.',
     {'meeting': MEETING, 'speaker': text('The voice letter, e.g. B.'), 'name': text("The person's name.")},
     ['meeting', 'speaker', 'name']),
    ('add_note', add_note, True,
     'Add a paragraph at the end of section 八、補充資訊 (8. Supporting Materials) of a meeting\'s minutes, and to its '
     'Google Doc. Only when the user asked; write it in the minutes\' language.',
     {'meeting': MEETING, 'text': text('The paragraph to add.')}, ['meeting', 'text']),
    ('replace_text', replace_text, True,
     "Change words in a meeting's minutes and its Google Doc: `old` must appear exactly once (read get_minutes first "
     'and copy it exactly, with enough words around it), one line at a time; an empty `new` deletes the words. '
     'Only when the user asked.',
     {'meeting': MEETING, 'old': text('The exact text now in the minutes.'), 'new': text('What it becomes.')},
     ['meeting', 'old', 'new']),
    ('set_tags', set_tags, True,
     "Set a meeting's tags (the whole list; at most 8). Only when the user asked.",
     {'meeting': MEETING, 'tags': {'type': 'array', 'items': {'type': 'string'}, 'description': 'The tags.'}},
     ['meeting', 'tags']),
    ('set_project', set_project, True,
     'Put a meeting under a project (an existing name, or a new one). Only when the user asked.',
     {'meeting': MEETING, 'project': text('The project name.')}, ['meeting', 'project']),
]
BY_NAME = {t[0]: t for t in TOOLS}


def tool_list() -> list[dict]:
    return [{'name': name, 'description': desc,
             'inputSchema': {'type': 'object', 'properties': props, 'required': req},
             'annotations': {'readOnlyHint': not writes, 'destructiveHint': name == 'replace_text',
                             'openWorldHint': False}}
            for name, _, writes, desc, props, req in TOOLS]


def call(name: str, args: dict) -> dict:
    try:
        result = BY_NAME[name][1](args or {})
    except Refused as why:
        vlog.log(f'{name}: refused')
        return {'content': [{'type': 'text', 'text': str(why)}], 'isError': True}
    except SystemExit as stop:                        # minutes_app's own messages
        vlog.log(f'{name}: refused')
        return {'content': [{'type': 'text', 'text': str(stop.code or 'Vinutes could not do that.')}], 'isError': True}
    except Exception as err:
        vlog.log(f'{name}: crashed {err.__class__.__name__}')
        return {'content': [{'type': 'text', 'text': f'Vinutes failed: {err.__class__.__name__}: {err}'}], 'isError': True}
    count = len(result.get('meetings', [])) if 'meetings' in result else len(result.get('projects', [])) or 1
    vlog.log(f'{name}: ok, {count}')
    return {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False, indent=1)}]}


def handle(msg: dict) -> dict | None:
    method, mid = msg.get('method'), msg.get('id')
    if mid is None:                                   # a notification: nothing to answer
        return None
    if method == 'initialize':
        asked = (msg.get('params') or {}).get('protocolVersion')
        result = {'protocolVersion': asked if asked in PROTOCOLS else PROTOCOLS[0],
                  'capabilities': {'tools': {'listChanged': False}},
                  'serverInfo': {'name': 'vinutes', 'version': (HERE.parent / 'VERSION').read_text().strip()
                                 if (HERE.parent / 'VERSION').is_file() else '0'},
                  'instructions': 'Past meetings recorded with Vinutes on this Mac. Search or list them, read the '
                                  'minutes and the transcript, and answer with the meeting date and title. Change a '
                                  'meeting only when the user asks.'}
    elif method == 'tools/list':
        result = {'tools': tool_list()}
    elif method == 'tools/call':
        params = msg.get('params') if isinstance(msg.get('params'), dict) else {}
        args = params.get('arguments') if isinstance(params.get('arguments'), dict) else {}
        if params.get('name') not in BY_NAME:
            return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32602, 'message': f"Unknown tool {params.get('name')}"}}
        result = call(params['name'], args)
    elif method == 'ping':
        result = {}
    else:
        return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': f'Unknown method {method}'}}
    return {'jsonrpc': '2.0', 'id': mid, 'result': result}


def main():
    vlog.log('start')
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        else:
            try:
                reply = handle(msg) if isinstance(msg, dict) else None
            except Exception as err:                  # one bad message never stops the server
                vlog.log(f'bad message: {err.__class__.__name__}')
                reply = {'jsonrpc': '2.0', 'id': msg.get('id') if isinstance(msg, dict) else None,
                         'error': {'code': -32603, 'message': 'Internal error'}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + '\n')
            sys.stdout.flush()
    vlog.log('end')


if __name__ == '__main__':
    main()
