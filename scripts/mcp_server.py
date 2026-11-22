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
import briefs  # noqa: E402
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


# --- project briefs (issue #2) -------------------------------------------------------------------------------------

def get_brief(args: dict) -> dict:
    """The project's brief as Project settings shows it. `folder` finds the project whose folder this is."""
    project = app.one_line(args.get('project'), 30)
    if not project and args.get('folder'):
        project = briefs.project_for_folder(str(args['folder'])) or ''
    known = sorted(set(briefs.projects()) | {p for p in (app.summary(j)['project'] for j in jobs()) if p})
    if not project:
        return {'found': False, 'projects': known,
                'note': 'No project has this folder. Ask the user which of these projects it is.'}
    return {'found': project in known, 'brief': briefs.load(project), 'projects': known}


def add_to_brief(args: dict) -> dict:
    project = app.one_line(args.get('project'), 30)
    if not project:
        raise Refused('Name the project (get_brief lists them).')
    people, terms = args.get('people'), args.get('terms')
    background = args.get('background') if isinstance(args.get('background'), str) else None
    if not people and not terms and not (background or '').strip():
        raise Refused('Nothing to add: give people, terms or a background.')
    return {'brief': briefs.merge(project, people, terms, background),
            'notes': ['Saved in Vinutes: it shows in 專案設定 and the next minutes of this project use it.']}


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
     'Add a paragraph at the end of 參考附件 (Attachments), the last section of a meeting\'s minutes, and to its '
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
    ('get_brief', get_brief, False,
     "A project's brief (專案背景) in Vinutes: its people and what each one does, its terms, the background and "
     'its folder. Give `folder` (the folder you are working in) to find the project whose folder it is.',
     {'project': text('The project name.'), 'folder': text('A folder on this Mac, e.g. the current working folder.')},
     []),
    ('add_to_brief', add_to_brief, True,
     "Add people and terms to a project's brief, and set its background, as the user approved them. People and "
     'terms join the brief; a role or meaning given replaces the one kept; nothing is taken off. A background '
     'given replaces the current one. Only after the user saw this exact draft and said to save it.',
     {'project': text('The project name, as get_brief gives it.'),
      'people': {'type': 'array', 'description': 'People: name as the project writes it, role at most 20 '
                 'characters (what they do in this project).',
                 'items': {'type': 'object', 'properties': {'name': text('Name.'), 'role': text('Role.')},
                           'required': ['name']}},
      'terms': {'type': 'array', 'description': "The project's own words, meaning at most 30 characters.",
                'items': {'type': 'object', 'properties': {'word': text('The word.'), 'meaning': text('Meaning.')},
                          'required': ['word']}},
      'background': text('At most 600 characters: what the project is, for whom, where it stands.')},
     ['project']),
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


# --- the prompt for drafting a brief (issue #2, task 5) ----------------------------------------------------------
# Claude Code lists it as /mcp__vinutes__draft_brief. The conversations are read by Claude in the project's folder,
# never by Vinutes: only the author has them, and they hold keys and other clients' data (decided 2026-10-17).

TYPED = r"""import json, re, sys
from pathlib import Path
here = Path.cwd().resolve()
logs = Path.home() / '.claude' / 'projects' / re.sub(r'[^A-Za-z0-9]', '-', str(here))
DROP = re.compile(r'<(system-reminder|pasted_content|local-command-stdout|command-[a-z]+|task-notification)'
                  r'[^>]*>.*?</\1[^>]*>', re.S)
for f in sorted(logs.glob('*.jsonl'), key=lambda f: f.stat().st_mtime, reverse=True):
    for line in f.open(encoding='utf-8', errors='replace'):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get('type') != 'user' or d.get('isMeta') or d.get('isSidechain') or d.get('isCompactSummary'):
            continue
        cwd = Path(d.get('cwd') or '/nowhere')
        if cwd != here and here not in cwd.parents:   # another folder whose name maps to the same log folder
            continue
        content = d.get('message', {}).get('content')
        parts = [content] if isinstance(content, str) else [
            c.get('text', '') for c in content or [] if isinstance(c, dict) and c.get('type') == 'text']
        for text in parts:
            text = DROP.sub('', text).strip()
            if text and len(text) <= 2000 and not text.startswith('<'):
                print(d.get('timestamp', '')[:10], text.replace('\n', ' '))
"""

DRAFT_BRIEF = """Draft the Vinutes brief (專案背景) of the project this folder belongs to, from what I typed in past \
Claude Code conversations here. Show me the draft and save only what I approve.

1. Which project: call the Vinutes tool get_brief with folder set to the current working folder{project}. If it \
finds no project, show me the project names it returns and ask which one this is. Note what the brief already has.

2. Read what I typed, yourself; Vinutes never reads conversations. Run this with python3 from this folder: it \
prints only my own messages, newest conversation first, and leaves out your replies, tool output, command output, \
system text and anything longer than 2,000 characters (pasted text). Do not open the conversation files any other \
way: they hold keys and other clients' data.

```python
{typed}```

3. Also read the folder's own lists if there are any (人員對照.md, 用詞對照.md or files like them) and the newest \
minutes in this folder.

4. Draft, in the language this project's meetings are held in:
- people: each name spelled the way the project writes it, and a role of at most 20 characters saying what they \
do in this project (業務窗口, 視覺設計, 客戶端 PM);
- terms: the project's own words people might mishear or not know (product, place, client and system names), \
each with a meaning of at most 30 characters;
- background: at most 600 characters on what the project is, for whom, and where it stands now.
Keep only what someone writing this project's minutes needs to spell names and terms right and to know who does \
what. Minutes are mailed to clients and vendors, so leave out everything internal: prices, budgets, margins, \
price floors, opinions about people or vendors, anything I said not to share. No e-mail addresses, phone \
numbers, keys or passwords.

5. Show me the draft as three short tables (people, terms, background), next to what the brief already has: mark \
each row new or changed (old → new), and leave out what stays the same. Ask me what to change. Save nothing yet.

6. When I say to save, call add_to_brief with only the rows I approved. Leave background out unless I approved a \
new one: it replaces mine. Then tell me it is in Vinutes under 專案設定.
"""

PROMPTS = [{'name': 'draft_brief',
            'title': 'Draft a project brief from past conversations',
            'description': "Draft this folder's Vinutes project brief (people, terms, background) from what you "
                           'typed in past Claude Code conversations here, then save what you approve.',
            'arguments': [{'name': 'project', 'description': 'The Vinutes project, if you know it.',
                           'required': False}]}]


def prompt_text(args: dict) -> str:
    project = app.one_line((args or {}).get('project'), 30)
    return DRAFT_BRIEF.format(project=f' and project set to "{project}"' if project else '', typed=TYPED)


def handle(msg: dict) -> dict | None:
    method, mid = msg.get('method'), msg.get('id')
    if mid is None:                                   # a notification: nothing to answer
        return None
    if method == 'initialize':
        asked = (msg.get('params') or {}).get('protocolVersion')
        result = {'protocolVersion': asked if asked in PROTOCOLS else PROTOCOLS[0],
                  'capabilities': {'tools': {'listChanged': False}, 'prompts': {'listChanged': False}},
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
    elif method == 'prompts/list':
        result = {'prompts': PROMPTS}
    elif method == 'prompts/get':
        params = msg.get('params') if isinstance(msg.get('params'), dict) else {}
        if params.get('name') != 'draft_brief':
            return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32602, 'message': f"Unknown prompt {params.get('name')}"}}
        args = params.get('arguments') if isinstance(params.get('arguments'), dict) else {}
        vlog.log('draft_brief: prompt')
        result = {'description': PROMPTS[0]['description'],
                  'messages': [{'role': 'user', 'content': {'type': 'text', 'text': prompt_text(args)}}]}
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
