"""Everything the recorder app's window shows and changes: the meeting list, one meeting with its Google Doc,
edits, Claude rewrites, comments, the activity log, and what the AI learns from the user's own edits.

Usage (the app runs these; each prints one last line `JSON {...}`, or exits with a message the window shows):
  minutes_app.py list                              every recording, newest first
  minutes_app.py open <job>                        sync with the Google Doc, then all the window shows for it
  minutes_app.py save <job> <edited.html> [shown]  the preview as the user typed it -> Markdown -> changed paragraphs
                                                   (shown: the token of the preview the user was editing)
  minutes_app.py learn <job>                       what the user changed by hand since the last time -> glossary / notes
  minutes_app.py unlearn <job> <id> | relearn <job> <id>
  minutes_app.py ask <job> <request> [--pictures <json>] [--refs <json>]  Claude changes the minutes as asked
                                                   (restricted, file tools only), looking at the pictures pasted with
                                                   it and the files and links handed with it (references.py)
  minutes_app.py quick <job> <name>                the same with a preset request (精簡摘要, 完整詳盡, ...)
  minutes_app.py undo <job>                        back to the minutes before the last Claude change
  minutes_app.py reply <job> <comment id> <text>   answer a comment on the Google Doc
  minutes_app.py resolve <job> <comment id>        mark a comment resolved
  minutes_app.py confirm <job> <item>              the user checked one of Claude's guesses (待確認)
  minutes_app.py skip <job> <item>                 the user leaves a guess as it is: the card goes, nothing learned
  minutes_app.py drop_voice <job> <letter> [back]  移除講者 X under 人員 (a voice that is no one), or put it back
  minutes_app.py correct <job> <item> <right>      the user puts a guess right: Claude changes the minutes to it
  minutes_app.py ask_many <job> <json>             requests still waiting when the window closed, one after another
  minutes_app.py attach <job> <note> <items JSON>  files, links and pictures as lines of 「八、補充資訊」, each led by
                                                   its own note or else <note> (attachments.py)
  minutes_app.py log <job>                         the activity log, newest first
  minutes_app.py refresh <job>                     what was typed into the Google Doc the window shows -> the minutes;
                                                   learns the user's own edits; the side panel's lists again
  minutes_app.py locate <job> <words>              how far down the Doc those words are ({"at": 0.0–1.0})
  minutes_app.py note <job> <text>                 a paragraph at the end of 「八、補充資訊」, written by someone else
                                                   than the user (an agent through mcp_server.py)
  minutes_app.py replace <job> <old> <new>         the words `old`, which the minutes have exactly once, become `new`
  minutes_app.py speaker <job> <group> <name> [line]  the user named a voice (講者 A -> Alex), or one line's
  minutes_app.py archive <job> | unarchive <job>   封存: the list hides the meeting (shown under 已封存) or shows it again
  minutes_app.py move <job> <project>             the meeting belongs to this project ('' = 未分類)
  minutes_app.py tags <job> <tags JSON>            the meeting's tags, as the user left them
  minutes_app.py rename_project <old> <new>        every meeting of a project, archived ones too, gets the new name;
                                                   a name already in use puts the two projects together
  minutes_app.py brief <project>                   the project's brief (專案小抄, briefs.py): people, terms, background
  minutes_app.py save_brief <project> <brief JSON> the brief as the user left it in 專案設定
  minutes_app.py move_learned <job> <id> <brief|glossary>  a learned word goes to the project's brief or the glossary
  minutes_app.py delete <job>                      刪除: the Doc and the meeting's Drive folder (only its own files
                                                   when another meeting shares the folder) go to Google's trash;
                                                   answers {"trash": [...]}, the files beside the minutes, which the
                                                   app moves to the Mac's Trash after the job folder
  minutes_app.py version <installed>               the app's version and the newest on GitHub (looked up once an hour)
  minutes_app.py update                            git pull this folder, then recorder/install.sh in the background,
                                                   which quits the app, builds the new one and opens it
  minutes_app.py usage [YYYY-MM]                   用量統計: what the month's meetings used, by day and by project
                                                   (usage.py), with each meeting's disk and the setup's
Commands that change a job wait for each other (a lock file per job), so a save never overlaps a rewrite;
refresh, asked every few seconds, answers {"busy": true} instead of waiting.

Files in the job folder, next to what auto_minutes.py writes:
  同步.json         the Doc revision last synced, comments already seen, confirmed guesses, learned items
  同步基準.md       the minutes as the Doc last had them; edits made while offline are sent from here on
  學習基準.md       the minutes after the last change that was not the user's own (pull, Claude, undo);
                    `learn` compares it with the minutes to see what the user typed
  復原.md           the minutes before the last Claude change, for undo (復原後.md: Claude's version)
  預覽基準/         what the window's editor held, read back to Markdown, by token: each preview it was sent and
                    each page it saved; a save is compared with that, not with what the minutes became meanwhile
  操作紀錄.jsonl    the activity log, one JSON object per line: {"at", "who", "text", "kind"}
  封存.json         there when the meeting is archived: {"at"}
  分類.json         the project and tags as the user set them: {"project", "tags", "dropped"}; without "project"
                    the one Claude named in result.json counts. Never in result.json: the mail step rewrites that.
What is learned goes to the project's brief (words, when the meeting has a project; briefs.py), else
$MINUTES_HOME/glossary.md, and to notes.md (wording); the next minutes read all three.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import briefs  # noqa: E402
import doc_sync  # noqa: E402
import speakers  # noqa: E402
from briefs import add_name, same_name  # noqa: E402
from google_setup import CONFIG, owner, sender_name  # noqa: E402
from i18n import t  # noqa: E402
from strings import EN, ZH  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
RECORDINGS = CONFIG / 'recordings'
BLANK = '[__]'
AI_TIMEOUT = 10 * 60
# the preset requests under the box: what the AI is told, in the minutes' language (the window shows the names)
QUICK = {
    'zh-TW': {
        'short': '把整份紀錄改得精簡：每一節只留結論、決定和數字，刪掉重複的說明。七節的標題和表格的欄位不變。',
        'detail': '照 逐字稿.txt 把討論摘要寫完整：補回討論過程、每個人的說法和理由。其他節不變。',
        'formal': '把用語改成正式的書面語氣，口語說法全部換掉。內容和格式不變。',
        'visual': '能做成表格的內容改成表格，例如決議、負責人與時程；時程照時間先後排。',
        'external': '改成可以給公司外部的人看的版本：刪掉只適合內部看的討論，人名改成單位名稱。',
    },
    'en': {
        'short': 'Make the whole record concise: keep only conclusions, decisions and figures in each section and remove '
                 'repeated explanation. Keep the section headings and the table columns as they are.',
        'detail': 'Complete the discussion summary from 逐字稿.txt: add back how the discussion went and what each '
                  'person said and why. Leave the other sections as they are.',
        'formal': 'Rewrite the wording in a formal written register and replace every casual expression. Keep the '
                  'content and the layout.',
        'visual': 'Turn whatever can be a table into a table, for example decisions, owners and dates; put dates in '
                  'time order.',
        'external': 'Make a version people outside the company can read: remove discussion meant only for insiders '
                    'and replace people\'s names with their organisations.',
    },
}
QUICK_NAMES = {ZH[f'quick_{k}']: k for k in QUICK['en']}     # the names the window used to send (精簡摘要, ...)
CHINESE_NUMBER = re.compile(r'[\d一二三四五六七八九十百千萬兩]')
NO_FILE = t('no_file')


def out(data: dict):
    print('JSON ' + json.dumps(data, ensure_ascii=False))


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path: Path, data: dict):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def now() -> datetime:
    return datetime.now().astimezone()


def user_name() -> str:
    """How the log names the user: the sender name from settings.json, else the part of the address before @."""
    return sender_name() or (owner() or t('you')).split('@')[0]


def me() -> str:
    """Who is making this change: the user, or an agent working through the MCP server (mcp_server.py), which
    sets VINUTES_ACTOR=Claude Code."""
    return one_line(os.environ.get('VINUTES_ACTOR'), 30) or user_name()


# --- one job ---------------------------------------------------------------------------------

class Job:
    def __init__(self, path: Path):
        self.dir = path.expanduser().resolve()
        if not (self.dir / 'job.json').is_file():
            sys.exit(t('job_missing'))
        self.meta = read_json(self.dir / 'job.json')
        self.status = read_json(self.dir / 'status.json')
        self.result = read_json(self.dir / 'result.json')
        self.state_file = self.dir / '同步.json'
        self.state = read_json(self.state_file)

    @property
    def id(self) -> str:
        return self.dir.name

    @property
    def md_path(self) -> Path | None:
        md = self.result.get('minutes_md')
        return Path(md) if md and Path(md).is_file() else None

    @property
    def lang(self) -> str:
        """The minutes' language: what auto_minutes.py wrote them in; older minutes are Chinese, unless their
        headings say otherwise (minutes made in English by hand)."""
        known = self.result.get('minutes_lang')
        if known in ('en', 'zh-TW'):
            return known
        md = self.md
        return 'en' if re.search(r'(?m)^##\s*1\.\s', md) and not re.search(r'(?m)^##\s*一、', md) else 'zh-TW'

    @property
    def missing(self) -> bool:
        """The minutes file was moved or renamed outside the app: nothing is synced from or to it."""
        return bool(self.result.get('minutes_md')) and self.md_path is None

    @property
    def md(self) -> str:
        return self.md_path.read_text(encoding='utf-8') if self.md_path else ''

    def write_md(self, text: str):
        if not self.md_path:
            sys.exit(NO_FILE)
        tmp = self.md_path.with_suffix('.tmp')
        tmp.write_text(text, encoding='utf-8')
        tmp.replace(self.md_path)

    @property
    def synced_md(self) -> str:
        """The minutes as the Google Doc last had them; the local file differs only by edits not sent yet."""
        path = self.dir / '同步基準.md'
        return path.read_text(encoding='utf-8') if path.is_file() else self.md

    def write_synced(self, text: str):
        (self.dir / '同步基準.md').write_text(text, encoding='utf-8')

    @property
    def doc_id(self) -> str:
        found = re.search(r'/document/d/([A-Za-z0-9_-]+)', self.result.get('doc_url') or '')
        return found.group(1) if found else ''

    def save_state(self):
        write_json(self.state_file, self.state)

    def started(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.meta.get('started') or '')
        except ValueError:
            return None

    def status_word(self) -> str:
        step = self.status.get('step', '')
        if step == 'failed':
            return 'failed'
        if step != 'done':
            return 'working'
        return 'sent' if self.result.get('sent_at') else 'ready'

    @property
    def archived(self) -> bool:
        return (self.dir / '封存.json').is_file()

    def log(self, who: str, text: str, kind: str = '', at: datetime | None = None):
        line = {'at': (at or now()).isoformat(timespec='seconds'), 'who': who, 'text': text, 'kind': kind}
        with (self.dir / '操作紀錄.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(line, ensure_ascii=False) + '\n')

    def log_entries(self) -> list[dict]:
        entries = []
        path = self.dir / '操作紀錄.jsonl'
        if path.is_file():
            for line in path.read_text(encoding='utf-8').splitlines():
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    pass
        if not any(e.get('text') in (EN['log_started'], ZH['log_started']) for e in entries):
            entries += derived_log(self)
        entries.sort(key=lambda e: e.get('at', ''), reverse=True)
        return entries


def derived_log(job: Job) -> list[dict]:
    """The log of a recording made before the app kept one, rebuilt from its files."""
    found, who = [], me()
    started, ended = job.meta.get('started'), job.meta.get('ended')
    if started:
        found.append({'at': started, 'who': who, 'text': t('log_started'), 'kind': ''})
    if ended and started:
        try:
            minutes = round((datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds() / 60)
            found.append({'at': ended, 'who': who, 'text': t('log_ended', length=length_words(minutes)), 'kind': ''})
        except ValueError:
            pass
    if job.status.get('step') == 'done' and job.status.get('at'):
        found.append({'at': job.status['at'], 'who': ai_name(), 'text': t('log_published'), 'kind': ''})
    sent = job.result.get('sent_at')
    if sent:
        people = t('list_sep').join(name_of(job, a) for a in (job.result.get('mail') or {}).get('to', []))
        found.append({'at': sent, 'who': who, 'text': t('log_sent', names=people,
                                                        format=format_words(job.result.get('sent_format'))),
                      'kind': 'sent'})
    return found


def length_words(minutes: int) -> str:
    if minutes < 60:
        return t('len_min', m=max(minutes, 1))
    h, m = divmod(minutes, 60)
    return t('len_hour', h=h) + (' ' + t('len_min', m=m) if m else '')


def format_words(fmt: str | None) -> str:
    return t({'word': 'fmt_word', 'pdf': 'fmt_pdf'}.get(fmt or '', 'fmt_gdoc'))


def calendar_people(job: Job) -> dict[str, str]:
    """Address -> name of the people on that day's calendar, from the 行事曆.txt the job wrote."""
    people = {}
    path = job.dir / '行事曆.txt'
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            m = re.match(r'\s*與會:\s*(.*?)\s+(\S+@\S+)', line)
            if m:
                people[m.group(2).lower()] = m.group(1).strip()
    return people


def name_of(job: Job, address: str) -> str:
    address = address.lower()
    if address == (owner() or '').lower():
        return me()
    known = {**calendar_people(job), **job.state.get('names', {})}
    return known.get(address) or address


def day_words(when: datetime) -> str:
    """10/15（三）, or 2025/10/15（三） from another year; Wed, Oct 15 (Wed, Oct 15, 2025) in English."""
    key = 'day_label' if when.year == now().year else 'day_label_year'
    return t(key, weekday=t('weekdays').split(',')[when.weekday()], month=t('months').split(',')[when.month - 1],
             day=when.day, year=when.year)


def short_time(iso: str) -> str:
    try:
        when = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone()
    except ValueError:
        return iso[:16]
    return t('short_time', month=t('months').split(',')[when.month - 1], day=when.day, time=f'{when:%H:%M}')


# --- the list --------------------------------------------------------------------------------

def all_jobs() -> list[Job]:
    names = sorted((p.name for p in RECORDINGS.iterdir() if (p / 'job.json').is_file()), reverse=True) \
        if RECORDINGS.is_dir() else []
    return [Job(RECORDINGS / n) for n in names]


def summary(job: Job) -> dict:
    started = job.started() or datetime.fromtimestamp((job.dir / 'job.json').stat().st_mtime).astimezone()
    try:
        ended = f"{datetime.fromisoformat(job.meta.get('ended') or ''):%H:%M}"
    except ValueError:
        ended = ''
    return {'id': job.id, 'day': day_words(started), 'date': f'{started:%Y-%m-%d}', 'time': f'{started:%H:%M}',
            'started': started.isoformat(),
            'ended_time': ended,
            'title': job.result.get('title') or '', 'project': project_of(job),
            'tags': tags_of(job), 'suggested': suggested_tags(job),
            'status': job.status_word(), 'step': job.status.get('step', ''), 'message': job.status.get('message', ''),
            'sent_at': job.result.get('sent_at') or '', 'sent_count': len((job.result.get('mail') or {}).get('to', [])),
            'sent_format': job.result.get('sent_format') or '',
            'has_audio': (job.dir / (job.meta.get('audio') or '錄音.m4a')).is_file(),
            'has_transcript': (job.dir / '逐字稿.txt').is_file(),
            'archived': job.archived}


def cmd_list():
    out({'jobs': [summary(j) for j in all_jobs()]})


# --- project and tags --------------------------------------------------------------------------
# Claude names the project when it writes the minutes and suggests a few tags (result.json); what the user sets in
# the window goes to 分類.json, which only these commands write.

SORTING = '分類.json'
MAX_TAGS = 8


def one_line(text, most: int) -> str:
    return ' '.join(str(text or '').split())[:most].strip()


def clean_tags(value) -> list[str]:
    found = []
    for item in value if isinstance(value, list) else []:
        tag = one_line(item, 20) if isinstance(item, str) else ''
        if tag and tag not in found:
            found.append(tag)
    return found


def sorting(job: Job) -> dict:
    return read_json(job.dir / SORTING)


def project_of(job: Job) -> str:
    mine = sorting(job)
    return one_line(mine['project'] if isinstance(mine.get('project'), str) else job.result.get('project'), 30)


def tags_of(job: Job) -> list[str]:
    return clean_tags(sorting(job).get('tags'))[:MAX_TAGS]


def suggested_tags(job: Job) -> list[str]:
    """Claude's suggestions the user has not added or taken off again; none once the minutes went out."""
    if job.result.get('sent_at'):
        return []
    mine = sorting(job)
    skip = set(clean_tags(mine.get('tags'))) | set(clean_tags(mine.get('dropped')))
    return [tag for tag in clean_tags(job.result.get('tag_suggestions')) if tag not in skip]


def save_sorting(job: Job, **change):
    """Read, change and write 分類.json as one step: the window and an agent (mcp_server.py) may both set it."""
    import fcntl
    with open(job.dir / '.sorting.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        write_json(job.dir / SORTING, {**sorting(job), **change})


def cmd_move(job: Job, project: str):
    save_sorting(job, project=one_line(project, 30))
    out({'project': project_of(job)})


def cmd_tags(job: Job, raw: str):
    try:
        value = json.loads(raw)
    except ValueError:
        value = None
    if not isinstance(value, list):
        sys.exit(t('bad_tags'))
    tags = clean_tags(value)[:MAX_TAGS]
    offered = set(clean_tags(job.result.get('tag_suggestions')))
    taken_off = [tag for tag in tags_of(job) if tag in offered and tag not in tags]
    dropped = [tag for tag in clean_tags(sorting(job).get('dropped')) + taken_off if tag not in tags]
    save_sorting(job, tags=tags, dropped=list(dict.fromkeys(dropped)))
    out({'tags': tags_of(job), 'suggested': suggested_tags(job)})


def cmd_rename_project(old: str, new: str):
    old, new = one_line(old, 30), one_line(new, 30)
    if not old or not new:
        sys.exit(t('bad_project'))
    moved = [job for job in all_jobs() if project_of(job) == old]
    for job in moved:
        save_sorting(job, project=new)
    briefs.rename(old, new)                          # the people and the brief go with the name; two become one
    out({'project': new, 'count': len(moved)})


def cmd_brief(project: str):
    out({'brief': briefs.load(one_line(project, 30))})


def cmd_save_brief(project: str, raw: str):
    project = one_line(project, 30)
    try:
        brief = json.loads(raw)
    except ValueError:
        brief = None
    if not project or not isinstance(brief, dict):
        sys.exit(t('bad_brief'))
    out({'brief': briefs.save(project, brief)})


# --- archive and delete ------------------------------------------------------------------------

def cmd_archive(job: Job, on: bool):
    if on and job.status_word() == 'working':
        sys.exit(t('not_ready'))
    marker = job.dir / '封存.json'
    if on:
        write_json(marker, {'at': now().isoformat(timespec='seconds')})
    else:
        marker.unlink(missing_ok=True)
    out({'archived': on})


MINUTES_ENDS = ('_會議紀錄', '_Minutes')            # auto_minutes.SUFFIX: what the minutes' file name ends with
TRANSCRIPT_ENDS = ('_逐字稿', '_Transcript')        # and the transcript copy beside it


def beside_minutes(job: Job) -> list[Path]:
    """The minutes file and what the app keeps next to it: the Doc's record, the transcript copy, the version
    kept aside after an offline conflict, the folder of picture copies. Other files there belong to other
    meetings."""
    md = job.md_path
    if not md:
        return []
    base = next((md.stem.removesuffix(end) for end in MINUTES_ENDS if md.stem.endswith(end)), md.stem)
    names = [md, md.with_name(md.name + '.gdoc.json'), md.with_name(md.stem + '_沒存回的修改.md'),
             *(md.with_name(base + end + '.txt') for end in TRANSCRIPT_ENDS)]
    pictures = md.with_name(md.stem + '_附件')                     # attachments.keep_beside: copies for Word
    return [p for p in names if p.is_file()] + ([pictures] if pictures.is_dir() else [])


def own_uploads(job: Job) -> list[str]:
    """The Drive files this meeting uploaded for section 8: the files kept in the Doc's record and the pictures."""
    record = read_json(job.md_path.with_name(job.md_path.name + '.gdoc.json')) if job.md_path else {}
    ids = record.get('attach_files', []) + [pic.get('id') for pic in job.state.get('pictures') or []]
    return list(dict.fromkeys(i for i in ids if i))


def cmd_delete(job: Job):
    """Google first: offline, nothing is deleted and the meeting stays as it is. A file already gone is fine.
    The Drive folder for attachments is found by the Doc's title, so meetings of one series share it: then only
    this meeting's own uploads go and the folder stays for the others. The Doc goes last, so a failure on the
    way leaves it where it was."""
    if job.status_word() == 'working':
        sys.exit(t('not_ready'))
    folder = job.state.get('attach_folder') or ''
    shared = bool(folder) and any(other.id != job.id and other.state.get('attach_folder') == folder
                                  for other in all_jobs())
    for file_id in [*(own_uploads(job) if shared else [folder]), job.doc_id]:
        if not file_id:
            continue
        try:
            doc_sync.call(doc_sync.DRIVE + file_id + '?fields=id&supportsAllDrives=true', {'trashed': True}, 'PATCH')
        except SystemExit as err:
            if 'HTTP 404' not in str(err):
                sys.exit(google_says(err, t('delete_not_done')))
    out({'trash': [str(p) for p in beside_minutes(job)]})


# --- 用量統計 ----------------------------------------------------------------------------------------------

def size_of(path: Path) -> int:
    """Bytes on disk of a file, or of everything in a folder (links not followed)."""
    try:
        if path.is_symlink() or path.is_file():
            return path.lstat().st_size
        return sum(f.lstat().st_size for f in path.rglob('*') if not f.is_dir() or f.is_symlink())
    except OSError:
        return 0


def model_size(model: Path) -> int:
    """The speech model's bytes: each file its snapshots name, wherever the link leads, counted once."""
    real = set()
    for f in model.glob('snapshots/*/**/*'):
        try:
            if f.is_file():
                real.add(os.path.realpath(f))
        except OSError:
            pass
    return sum(os.path.getsize(p) for p in real if os.path.isfile(p))


def setup_disk() -> dict:
    """The speech model and Vinutes' own Python environment and voice model; measured at most once an hour, since
    the environment is thousands of files."""
    import usage
    path = usage.FOLDER / 'disk.json'
    known = read_json(path)
    try:
        fresh_enough = now() - datetime.fromisoformat(known.get('at', '')) < timedelta(hours=1)
    except ValueError:
        fresh_enough = False
    if fresh_enough and isinstance(known.get('speech'), int) and isinstance(known.get('program'), int):
        return {'speech': known['speech'], 'program': known['program']}
    import setup_check
    found = {'speech': model_size(setup_check.hub()), 'program': size_of(CONFIG / 'venv') + size_of(CONFIG / 'models')}
    try:
        usage.FOLDER.mkdir(parents=True, exist_ok=True)
        write_json(path, {'at': now().isoformat(timespec='seconds'), **found})
    except OSError:
        pass
    return found


def meeting_facts(job: Job) -> dict:
    """What usage.summary needs of a meeting that still exists."""
    started = job.started() or datetime.fromtimestamp((job.dir / 'job.json').stat().st_mtime).astimezone()
    try:
        length = (datetime.fromisoformat(job.meta.get('ended') or '') - started).total_seconds()
        length = max(0, round(length - float(job.meta.get('paused_seconds') or 0)))
    except (ValueError, TypeError):
        length = 0
    return {'id': job.id, 'date': f'{started:%Y-%m-%d}', 'title': job.result.get('title') or '',
            'project': project_of(job), 'audio': length,
            'disk': size_of(job.dir) + sum(size_of(p) for p in beside_minutes(job))}


def cmd_usage(month: str):
    import usage
    if not re.match(r'^\d{4}-(0[1-9]|1[0-2])$', month or ''):
        month = f'{now():%Y-%m}'
    facts = [meeting_facts(j) for j in all_jobs()]
    found = usage.summary(month, facts)
    found['disk'] = {'meetings': sum(f['disk'] for f in facts), **setup_disk()}
    out(found)


# --- the app's version -------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
APP_UPDATE = CONFIG / 'vinutes-update.json'   # the newest version on GitHub and when it was looked up


def cmd_version(installed: str):
    """The list's corner: the version this app was built from, and whether GitHub has a newer one. GitHub is asked
    at most once an hour, so a version released today shows today (Vin 2026-10-19); offline, the last answer stands.
    Only the public VERSION file is fetched."""
    import check_update
    try:
        state = json.loads(APP_UPDATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    # the window asks every hour and the time is stamped after the download: a little under an hour counts too
    if datetime.now().timestamp() - float(state.get('checked_at') or 0) > 3600 - 300:
        try:
            newest = check_update.version_of(check_update.fetch('VERSION'))
            state = {'checked_at': datetime.now().timestamp(), 'newest': '.'.join(map(str, newest)) if newest else ''}
            APP_UPDATE.write_text(json.dumps(state), encoding='utf-8')
        except Exception:                         # offline, GitHub down: no button today, try again later
            pass
    have = check_update.version_of(f'version: "{installed}"') if installed else \
        check_update.version_of((ROOT / 'VERSION').read_text(encoding='utf-8'))
    newest = check_update.version_of(f'version: "{state.get("newest") or ""}"')
    out({'version': '.'.join(map(str, have)) if have else installed, 'newest': state.get('newest') or '',
         'update': bool(have and newest and newest > have)})


def cmd_update():
    """版本更新: the Vinutes folder takes the new version from GitHub, then install.sh runs on its own (it quits this
    app, which ends this script's parent) and opens the new app."""
    if not (ROOT / '.git').exists():
        sys.exit(t('update_not_git'))
    try:
        pull = subprocess.run(['git', '-C', str(ROOT), 'pull', '--ff-only'], capture_output=True, text=True,
                              timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        sys.exit(t('update_no_network'))
    if pull.returncode != 0:
        sys.exit(t('update_failed'))
    (CONFIG / 'open-window-after-update').touch()   # the new app opens the meeting window again
    log = (CONFIG / 'update.log').open('w', encoding='utf-8')
    subprocess.Popen(['/bin/bash', str(ROOT / 'recorder' / 'install.sh')], stdin=subprocess.DEVNULL,
                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    out({'started': True})


# --- what is still open: 待補充 and 待確認 ----------------------------------------------------

def find_words(plains: list[str], *candidates: str) -> str:
    """What to type into the Google Doc's find box to land on an item: the first candidate one paragraph or cell
    of the minutes holds, else the longest stretch of a candidate (3 characters or more) one of them holds."""
    for c in candidates:
        c = (c or '').strip()
        if c and any(c in p for p in plains):
            return c
    best = ''
    for c in candidates:
        c = (c or '').strip()
        for i in range(len(c)):
            for j in range(len(c), i + max(len(best), 2), -1):
                piece = c[i:j].strip()
                if len(piece) > len(best) and any(piece in p for p in plains):
                    best = piece
                    break
    return best


def todo_items(job: Job, md: str) -> list[dict]:
    """A 待補充 item stays until the blank it points at is filled."""
    _, blocks = doc_sync.parse(md)
    plains = [b.plain for b in blocks]
    rows: dict[tuple, str] = {}
    for b in blocks:
        if b.kind == 'cell':
            rows[(b.table, b.row)] = rows.get((b.table, b.row), '') + ' | ' + b.plain
    units = [rows[(b.table, b.row)] if b.kind == 'cell' else b.plain for b in blocks]
    units = list(dict.fromkeys(units))
    any_blank = any(BLANK in u for u in units)
    items = []
    for raw in job.result.get('todo') or []:
        label, anchor = (raw.get('label', ''), raw.get('line', '')) if isinstance(raw, dict) else (str(raw), '')
        label = label.strip()
        if not label:
            continue
        hits = [u for u in units if anchor and anchor in u] or [u for u in units if label in u]
        still = any(BLANK in u for u in hits) if hits else any_blank
        if still:
            items.append({'label': label, 'anchor': anchor or label, 'find': find_words(plains, anchor, label)})
    return items


GUESS = re.compile(r'「(.+?)」\s*(?:推測是|推測為|應該是|可能是|改為|改成|暫寫成|寫成)\s*「?([^「」，。,]+?)」?\s*$')
GUESS_EN = re.compile(r'[“"](.+?)[”"]\s*(?:is probably|probably means|is likely|likely means|may be|changed to|written as)'
                      r'\s*[“"]?([^“”",.]+?)[”"]?\.?\s*$', re.I)


# 「講者 B 負責文章，可能是 Nina」: a guess about who a voice is, shown with that voice under 人員
SPEAKER_GUESS, NOT_A_NAME, NOT_A_ROLE = speakers.SPEAKER_GUESS, speakers.NOT_A_NAME, speakers.NOT_A_ROLE
ATTENDEES = re.compile(r'^[ \t]*(?:[*+-][ \t]+)?(?:\*\*)?(?:與會人員|出席人員|Attendees)[ \t]*(?:\*\*)?[ \t]*[：:]'
                       r'[ \t]*(?:\*\*)?[ \t]*(?P<names>[^\n]*)$', re.M | re.I)   # one line, and **與會人員：** kept


def attendees(md: str) -> list[str]:
    """The names on the minutes' 與會人員 line, blanks left out."""
    found = ATTENDEES.search(md or '')
    if not found:
        return []
    names = [n.strip(' *') for n in re.split(r'[、，,；;]', found.group('names'))]
    return [n for n in names if n and not n.startswith('[') and len(n) <= 30][:30]


# --- 人員: who was at a meeting --------------------------------------------------------------------
# A meeting's list starts from the people invited to it (the calendar, where ERP room bookings put their invitees)
# and the names on the minutes' 與會人員 line; voices that were given a name join it. What the user adds, confirms or
# takes off is kept in the meeting's 人員.json. Someone added or named also joins the project's list (people.json,
# the people of its brief); taking someone off a meeting only says they weren't there, and they stay in the brief
# (Vin 2026-10-19: the brief lists the project's people, not each meeting's, so it starts no meeting's list either).
PROJECT_PEOPLE = briefs.PEOPLE                    # the project's people are also its brief's (專案小抄)
MEETING_PEOPLE = '人員.json'
# A room booking's note may name a department instead of inviting people; the department's roster (briefs.py)
# is learned from the meetings the user confirmed and starts the next meeting that names it.
DEPARTMENTS, roster = briefs.DEPARTMENTS, briefs.roster


def calendar_of(job: Job) -> dict:
    """What the picked calendar event's note said (workspace.describe), as 行事曆.json keeps it."""
    data = read_json(job.dir / '行事曆.json')
    return {'host': data.get('host') if isinstance(data.get('host'), str) else '',
            'departments': [d for d in (data.get('departments') or []) if isinstance(d, str) and d],
            'participants': [p for p in (data.get('participants') or []) if isinstance(p, str) and p]}


def job_label(job: Job) -> str:
    """2026-10-20 數據課週會: how a roster says where it was learned."""
    started = job.meta.get('started') or ''
    day = started[:10] if re.match(r'\d{4}-\d{2}-\d{2}', started) else f'{job.id[:4]}-{job.id[4:6]}-{job.id[6:8]}'
    return f'{day} {job.result.get("title") or ""}'.strip()


def remember_roster(job: Job, names: list[str]):
    """The meeting's people join the roster of each department its calendar note names."""
    for dept in calendar_of(job)['departments']:
        briefs.save_roster(dept, names, job_label(job))


def calendar_payload(job: Job) -> dict:
    """For the window's 人員: what the calendar note said, the roster it brings in, and whether this meeting taught it."""
    cal = calendar_of(job)
    people, where = roster(cal['departments'])
    return {'host': cal['host'], 'departments': cal['departments'], 'roster': people, 'roster_from': where,
            'learned': bool(where) and where == job_label(job)}


def project_people(project: str) -> list[str]:
    return briefs.people_of(project)


def save_project_people(project: str, names: list[str]):
    briefs.save_people(project, names)


def invited(job: Job) -> list[str]:
    """The people the meeting's calendar event invited (not the ones who said no): the name, else the address's
    first part (leo@… -> Leo); this Mac's own account by the user's name."""
    names = []
    for g in read_json(job.dir / '行事曆.json').get('guests') or []:
        if not isinstance(g, dict):
            continue
        name = (sender_name() or '') if g.get('self') else ''
        name = name or g.get('name') or ''
        local = (g.get('email') or '').split('@')[0]
        if not name and local and not re.search(r'[\d_-]|team|group|room|info|service|admin|noreply|calendar', local, re.I):
            name = ' '.join(w[:1].upper() + w[1:] for w in local.split('.') if w)
        names = add_name(names, name)
    cal = calendar_of(job)                            # a room booking's note: the host and participants, as it spells them
    for n in [cal['host'], *cal['participants']]:
        names = add_name(names, n)
    return names


def meeting_people(job: Job) -> list[str]:
    data = read_json(job.dir / MEETING_PEOPLE)
    if isinstance(data.get('people'), list):
        names = [n for n in data['people'] if isinstance(n, str)]
    else:                                             # first time: from the invitation and the minutes
        names = []
        roster_names, _ = roster(calendar_of(job)['departments'])   # the department's people, confirmed earlier
        for n in invited(job) + roster_names + attendees(job.md if not job.missing else ''):   # 以當場會議邀請的人為主
            names = add_name(names, n)
    for n in speakers_shown(job).values():          # a voice with a name was there
        if n:
            names = add_name(names, n)
    return names


def save_meeting_people(job: Job, names: list[str]):
    data = read_json(job.dir / MEETING_PEOPLE)
    data['people'] = names
    write_json(job.dir / MEETING_PEOPLE, data)


def speaker_map(job: Job) -> dict:
    """{voice letter: name} the minutes already use: the AI's guess put in after the write-up, or the user's pick."""
    found = read_json(job.dir / MEETING_PEOPLE).get('speakers')
    return {g: n for g, n in found.items() if isinstance(n, str)} if isinstance(found, dict) else {}


def save_speaker(job: Job, group: str, name: str):
    data = read_json(job.dir / MEETING_PEOPLE)
    data['speakers'] = {**speaker_map(job), group: name}
    write_json(job.dir / MEETING_PEOPLE, data)


def speakers_shown(job: Job) -> dict:
    """Who each voice is, as its menu shows it: the name it was given, else the one the minutes use, else the AI's
    guess (older minutes, written before guesses went in by themselves)."""
    used, guess = speaker_map(job), speakers.guessed(job.result.get('check'))
    return {v['group']: v['name'] or used.get(v['group']) or guess.get(v['group'], '') for v in voices_view(job)}


def known_people() -> list[str]:
    """The names offered while typing under 人員: every project's list and every voice Vinutes knows."""
    names = []
    for group in read_json(PROJECT_PEOPLE).values():
        for n in group if isinstance(group, list) else []:
            names = add_name(names, n) if isinstance(n, str) else names
    for n in speakers.known_names():
        names = add_name(names, n)
    return names


def with_people(job: Job, md: str, names: list[str]) -> str:
    """The minutes with the 與會人員 line showing the meeting's list."""
    found = ATTENDEES.search(md)
    if found and names:
        sep = ', ' if job.lang == 'en' else '、'
        end = re.search(r'(?:\*\*)?[。.；;]?(?:\*\*)?\s*$', found.group('names')).group(0)   # its full stop and bold stay
        md = md[:found.start('names')] + sep.join(names) + end + md[found.end('names'):]
    return md


def silent_people(job: Job) -> list[str]:
    """The meeting's people that no voice in the recording is."""
    shown = [n for n in speakers_shown(job).values() if n]
    return [n for n in meeting_people(job) if not any(same_name(n, s) for s in shown)]


def people_change(job: Job, names: list[str], renames=()) -> dict:
    """Keep the list, then put it, and each voice's new name (group, the name it had, the new one), into the
    minutes and the Doc."""
    save_meeting_people(job, names)
    result = fresh()
    if job.md_path and not job.missing:
        new_md = with_people(job, job.md, names)
        others = names + known_people()
        for group, before, after in renames:
            new_md = speakers.name_voice(job.dir, new_md, group, before, after, others)
        if new_md != job.md:
            result = push_edit(job, new_md)
    for group, _, after in renames:                   # the mail says it the same way
        body = job.dir / '信件內文.txt'
        if body.is_file() and not job.state.get('sent'):
            text = body.read_text(encoding='utf-8')
            if (named := speakers.letter(group).sub(lambda _: after, text)) != text:
                body.write_text(named, encoding='utf-8')
    return result


def cmd_people(job: Job, action: str, name: str, group: str = ''):
    """+ 加人 (add), ✕ (remove), or a guess about a voice the recording could not tell (add with its letter)."""
    name = one_line(name, 30)
    if not name:
        sys.exit(t('people_no_name'))
    project = project_of(job)
    names = meeting_people(job)
    renames = []
    if action == 'add':
        names = add_name(names, name)
        save_project_people(project, add_name(project_people(project), name))
        remember_roster(job, names)
        job.log(me(), t('log_people_add', name=name), 'speaker')
    elif action == 'remove':
        names = [n for n in names if not same_name(n, name)]      # this meeting only: the brief keeps them
        for group, shown in speakers_shown(job).items():   # the voice with this name is a 講者 X again, in the minutes too
            if shown and same_name(shown, name):
                speakers.clear_name(job.dir, group)
                renames.append((group, shown, f"{'Speaker' if job.lang == 'en' else '講者'} {group}"))
        job.log(me(), t('log_people_remove', name=name), 'speaker')
    else:
        sys.exit(__doc__)
    if action == 'add' and group:
        renames.append((group, '', name))
    result = people_change(job, names, renames)
    answer(job, result, html=bool(result.get('reload')), people=meeting_people(job), voices=voices_view(job),
           speakers=speakers_shown(job), silent=silent_people(job),
           transcript=transcript(job), log=job.log_entries()[:200])


def check_items(job: Job) -> list[dict]:
    """Claude's guesses the user has not confirmed yet. Word guesses carry what was heard and what is meant; a
    guess about a voice carries the voice (speaker), the name and what it said the person does (role)."""
    done = {*job.state.get('confirmed', []), *job.state.get('skipped', []), *job.state.get('corrected', [])}
    plains = [] if job.missing or not job.md_path else [b.plain for b in doc_sync.parse(job.md)[1]]
    items = []
    project = project_of(job)
    listed = project_people(project)
    groups = speakers.load(job.dir).get('groups') or {}
    for raw in job.result.get('check') or []:
        person = role = ''
        if isinstance(raw, dict) and 'person' in raw:   # 新的人名: only for a meeting with a project,
            person = one_line(raw['person'], 30) if isinstance(raw['person'], str) else ''
            role = one_line(raw.get('role'), 20) if isinstance(raw.get('role'), str) else ''
            if not project or not person or any(same_name(n, person) for n in listed):   # and not someone it has
                continue
            raw = {**raw, 'text': raw.get('text') or t('new_person_label', name=person)}
        if isinstance(raw, dict):
            text, heard, meant = raw.get('text', ''), raw.get('heard', ''), raw.get('meant', '')
        else:
            text, heard, meant = str(raw), '', ''
            m = GUESS.search(text) or GUESS_EN.search(text)
            if m and len(m.group(2).strip()) <= 20:
                heard, meant = m.group(1).strip(), m.group(2).strip()
        about = re.match(ABOUT_VOICE.format('([A-Z])'), text or '')
        voice = about.group(1) if about and about.group(1) in groups else ''
        g = groups.get(voice) or {}
        if voice and (g.get('name') or g.get('off')):   # 講者 B …請補姓名 once 講者 B is named (Vin 2026-10-19)
            continue
        if text and text not in done:
            item = {'label': text, 'heard': heard, 'meant': meant, 'find': find_words(plains, meant, text)}
            if voice:
                item['voice'] = voice
            if person and not NOT_A_NAME.search(person):     # a name the project's brief does not have yet
                item.update(person=person, role=role, find=find_words(plains, person, text))
            who = SPEAKER_GUESS.match(text)
            name = who.group(3).strip() if who else ''
            if who and 0 < len(name) <= 30 and not NOT_A_NAME.search(name):
                role = re.sub(r'[（）()]', '', who.group(2)).strip(' ，,、:：')
                item.update(speaker=who.group(1), who=name, role='' if len(role) > 12 or NOT_A_ROLE.search(role) else role)
            items.append(item)
    return items


# --- preview ---------------------------------------------------------------------------------

MARK_OPEN, MARK_MID, MARK_CLOSE = '', '', ''
ANCHOR_OPEN, ANCHOR_MID, ANCHOR_CLOSE = '', '', ''


PRIVATE = re.compile('[\ue000-\ue0ff]')
LINE_MARK = re.compile(r'^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s?|\|)')   # never mark a list number or a heading's #


def wrap_in_lines(lines: list[str], first: int, last: int, words: str, opener: str, closer: str) -> bool:
    """Put markers around the first place `words` appears, reading past markers already there; a place that would
    cut across another marked stretch is skipped, so the spans always nest."""
    for i in range(first, last + 1):
        line = lines[i]
        keep = [k for k, ch in enumerate(line) if not PRIVATE.match(ch)]
        clean = ''.join(line[k] for k in keep)
        lead = LINE_MARK.match(clean)
        hidden = re.sub(r'\]\([^)]*\)|<[^>\s]+>', lambda m: '\0' * len(m.group(0)), clean)   # link addresses
        at = hidden.find(words, lead.end() if lead else 0)
        if at < 0:
            continue
        start, end = keep[at], keep[at + len(words) - 1] + 1
        inside = line[start:end]
        opens = len(re.findall('[\ue000\ue003]', inside))
        closes = len(re.findall('[\ue002\ue005]', inside))
        if opens != closes:
            continue
        lines[i] = line[:start] + opener + inside + closer + line[end:]
        return True
    return False


def preview(md: str, marks: list[dict], anchors: list[dict]) -> str:
    """The minutes as HTML for the window's editor: colleagues' changes underlined, commented words highlighted,
    blanks tinted. Raw HTML in the Markdown is shown as text, never run."""
    from markdown_it import MarkdownIt
    lines, blocks = doc_sync.parse(md)
    for a in anchors:
        quote = a['quote'].strip().split('\n')[0][:120]
        if quote:
            wrap_in_lines(lines, 0, len(lines) - 1, quote, f'{ANCHOR_OPEN}{a["n"]}{ANCHOR_MID}', ANCHOR_CLOSE)
    for n, mark in enumerate(marks):
        words = mark['after'].strip()
        if not words:
            continue
        b = blocks[mark['block']] if 0 <= mark.get('block', -1) < len(blocks) else None
        first, last = (b.first, b.last) if b else (0, len(lines) - 1)
        wrap_in_lines(lines, first, last, words, f'{MARK_OPEN}{n}{MARK_MID}', MARK_CLOSE)
    body = MarkdownIt('commonmark', {'html': False}).enable('table').render('\n'.join(lines))
    body = body.replace(BLANK, f'<span class="blank">{BLANK}</span>')

    def mark_span(m):
        mark = marks[int(m.group(1))]
        who = html.escape(mark.get('who') or '')
        return f'<span class="edited" title="{t("edited_by", who=who)}">{m.group(2)}</span>'

    body = re.sub(f'{MARK_OPEN}(\\d+){MARK_MID}(.*?){MARK_CLOSE}', mark_span, body, flags=re.S)
    body = re.sub(f'{ANCHOR_OPEN}(\\d+){ANCHOR_MID}(.*?){ANCHOR_CLOSE}',
                  lambda m: f'<span class="anchor" data-c="{m.group(1)}">{m.group(2)}</span>'
                            f'<sup class="cnum" data-ui="1" contenteditable="false">{m.group(1)}</sup>',
                  body, flags=re.S)
    for ch in (MARK_OPEN, MARK_MID, MARK_CLOSE, ANCHOR_OPEN, ANCHOR_MID, ANCHOR_CLOSE):
        body = body.replace(ch, '')
    # pictures from the internet are not loaded in the window; data: images and nothing else
    body = re.sub(r'<img [^>]*src="(?!data:)[^"]*"[^>]*>', '', body)
    return body


# --- sync with the Google Doc ----------------------------------------------------------------

OFFLINE_SAVED = t('offline_saved')
NO_DOCS_API = t('no_docs_api')
LOGIN_SAVED = t('login_saved')
NO_RIGHT_SAVED = t('no_right_saved')
GONE_SAVED = t('gone_saved')
OFFLINE_OPEN = t('offline_open')
LOGIN_OPEN = t('login_open')
NO_RIGHT_OPEN = t('no_right_open')
GONE_OPEN = t('gone_open')
OFFLINE_CONFLICT = t('offline_conflict')
TABLES_CHANGED = t('tables_changed')
TABLE_SHAPE = t('table_shape')
AI_TABLES_OFFLINE = t('ai_tables_offline')       # {ai}: ai_words fills it in
AI_TABLES_COMMENTS = t('ai_tables_comments')
AI_TABLES_COLLEAGUE = t('ai_tables_colleague')
WHOLE_COMMENTS = t('whole_comments')
WHOLE_COLLEAGUE = t('whole_colleague')
REJECTED_SAVED = t('rejected_saved')
REJECTED_OPEN = t('rejected_open')


def linked_files(job: Job, md: str) -> list[str]:
    """The Drive files 「八、補充資訊」 still links to (cmd_attach keeps their ids in the Doc's record): the mail opens
    these to its recipients (workspace.linked_files)."""
    record = read_json(job.md_path.with_name(job.md_path.name + '.gdoc.json')) if job.md_path else {}
    return [f for f in record.get('attach_files', []) if f'/file/d/{f}/' in md]


def ai_name() -> str:
    """Claude, Codex or Antigravity: the AI that writes and changes the minutes on this computer (ai_runner.py)."""
    import ai_runner
    return ai_runner.name()


def ai_choice() -> dict:
    """For the AI menu left of the prompt box: the one in use and the ones this computer has."""
    import ai_runner
    key = ai_runner.chosen()
    return {'ai': key, 'ai_name': ai_runner.name(key), 'ai_installed': ai_runner.installed()}


def ai_words(text: str) -> str:
    return text.replace('{ai}', ai_name())


def connect() -> str:
    """'' when this computer can talk to Google, else what went wrong."""
    try:
        doc_sync.authorize()
        return ''
    except SystemExit as err:
        return str(err) or 'OFFLINE'


def trouble(err, saving: bool = True) -> str:
    """What went wrong with Google, in words for the window: while saving (the edit stays here) or opening."""
    text = str(err)
    if text == doc_sync.BUSY or text in (OFFLINE_SAVED, NO_DOCS_API, LOGIN_SAVED, NO_RIGHT_SAVED, GONE_SAVED,
                                         REJECTED_SAVED):
        return text
    if 'DOCS API DISABLED' in text:
        return NO_DOCS_API
    if re.search(r'GOOGLE LOGIN EXPIRED|NO GOOGLE LOGIN|HTTP 401', text):
        return LOGIN_SAVED if saving else LOGIN_OPEN
    if 'HTTP 403' in text:
        return NO_RIGHT_SAVED if saving else NO_RIGHT_OPEN
    if 'HTTP 404' in text:
        return GONE_SAVED if saving else GONE_OPEN
    if 'HTTP 400' in text:                           # Google refused the requests themselves
        return REJECTED_SAVED if saving else REJECTED_OPEN
    return OFFLINE_SAVED if saving else OFFLINE_OPEN


def google_says(err, what: str) -> str:
    """A comment action that did not go through."""
    text = str(err)
    if re.search(r'GOOGLE LOGIN EXPIRED|NO GOOGLE LOGIN|HTTP 401', text):
        return t('gs_login', what=what)
    if text.startswith('OFFLINE'):
        return t('gs_offline', what=what)
    return t('gs_other', what=what[:1].upper() + what[1:])


def revisions(job: Job) -> list[dict]:
    """Drive's revisions of the Doc since the last sync, oldest first ([] when Drive cannot be asked)."""
    since = job.state.get('synced_at') or job.status.get('at') or ''
    try:
        return doc_sync.revisions_since(job.doc_id, to_utc(since))
    except SystemExit:
        return []


def edits_listed(job: Job, revs: list[dict]) -> bool:
    """Drive lists a revision a little after the edit itself. Until the newest one reaches the Doc's last change,
    the names it gives are not the whole story: the user's typing would be put down to nobody, or a colleague's to
    the user. True when the list has caught up, or when it has been waiting for two minutes (then the names are
    taken as they are)."""
    newest = max((r.get('modifiedTime', '') for r in revs), default='')
    try:
        last = doc_sync.modified_time(job.doc_id)
    except SystemExit:
        return True
    a, b = parse_time(newest), parse_time(last)
    if a and b and (b - a).total_seconds() <= 2:
        job.state.pop('waiting_since', None)
        return True
    started = parse_time(job.state.get('waiting_since'))
    if not started:
        job.state['waiting_since'] = now().isoformat(timespec='seconds')
        return False
    if (now() - started).total_seconds() >= 120:
        job.state.pop('waiting_since', None)
        return True
    return False


def authors_since(job: Job, before: datetime | None = None, revs: list[dict] | None = None) -> list[str]:
    """Who changed the Doc since the last sync ('你' for the user, a marker in any language), from Drive's revision
    list (or `revs`, when the caller already asked). With `before`, the user's own revisions from then on (the push
    that just ran) are left out."""
    cutoff = to_utc((before - timedelta(seconds=2)).isoformat()) if before else ''
    own = to_utc(job.state.get('own_until') or '')  # the app's own blank colours and pictures (own_write)
    found = []
    revisions = revs if revs is not None else globals()['revisions'](job)
    for r in revisions:
        user = r.get('lastModifyingUser') or {}
        if cutoff and user.get('me') and r.get('modifiedTime', '') >= cutoff:
            continue
        if own and user.get('me') and r.get('modifiedTime', '') <= own:
            continue
        name = '你' if user.get('me') else (user.get('displayName') or user.get('emailAddress') or t('someone'))
        if user.get('emailAddress') and not user.get('me'):
            job.state.setdefault('names', {})[user['emailAddress'].lower()] = name
        if name not in found:
            found.append(name)
    return found


def names(authors: list[str]) -> str:
    return t('list_sep').join(me() if a == '你' else a for a in authors) or t('someone')


def note_remote(job: Job, changes: list, authors: list[str], before: str, after: str) -> list[dict]:
    """Changes that just came in from the Doc. Colleagues' are logged under their names, kept out of what is
    learned, and returned as marks for the preview. The user's own (typed into the Doc the window shows) are logged
    the same way and stay unlearned, so the next `learn` learns them like anything typed here."""
    who = names(authors)
    for ch in changes[:5]:
        job.log(who, change_words(ch.kind, ch.before, ch.after, t('where_doc')))
    if len(changes) > 5:
        job.log(who, t('log_more_doc_edits', n=len(changes) - 5))
    if authors != ['你']:
        relearn(job, before, after)
    warn_after_send(job, who)
    return [{'after': ch.after, 'block': ch.block, 'who': who} for ch in changes if ch.kind != 'remove' and ch.after]


def relearn(job: Job, before: str, after: str):
    """The minutes went from `before` to `after` by someone other than the user (a colleague, Claude, an undo).
    What `learn` compares with becomes `after` without the user's own edits it has not learned yet, so those are
    still learned and nothing else ever is: a paragraph the change touched keeps the change."""
    path = job.dir / '學習基準.md'
    if not path.is_file():
        return
    try:
        path.write_text(doc_sync.carry(after, before, path.read_text(encoding='utf-8'))[0], encoding='utf-8')
    except doc_sync.Structural:
        path.write_text(after, encoding='utf-8')


def warn_after_send(job: Job, who: str):
    """After the minutes went out as a Word or PDF file, the first later change says the file is now old."""
    fmt, sent = job.result.get('sent_format'), job.result.get('sent_at')
    if sent and fmt in ('word', 'pdf') and job.state.get('warned_after_send') != sent:
        job.log(who, t('log_changed_after_send', format=format_words(fmt)), 'warn')
        job.state['warned_after_send'] = sent


def synced(job: Job, md: str, revision: str):
    """The Doc and the local Markdown agree from here on."""
    job.write_md(md)
    job.write_synced(md)
    job.state['revision'] = revision
    job.state['synced_at'] = now().isoformat(timespec='seconds')


OWN_GRACE = 5            # seconds after the app's own change to the Doc in which Drive may still list it


def own_write(job: Job, revision: str):
    """The app itself changed the Doc (blank colours, a picture) on top of the revision just synced: the minutes still
    match it, and Drive's listing of that change is never taken for an edit of the user's or a colleague's."""
    job.state['revision'] = revision
    job.state['synced_at'] = now().isoformat(timespec='seconds')
    job.state['own_until'] = (now() + timedelta(seconds=OWN_GRACE)).isoformat(timespec='seconds')


def after_sync(job: Job, doc: dict | None) -> list[str]:
    """Once the minutes match the Doc: links left open by a picture are closed, the Doc's [__] turn red and words
    typed into one plain again (doc_sync.blank_requests), and pictures waiting for this go in. Only on the Doc the
    minutes were just synced with, read again with colleagues' suggestions in place, so that nothing a colleague types
    is put down to the user and nothing lands on the wrong characters. What went wrong, in words for the window."""
    if not doc or not job.doc_id or doc.get('revisionId') != job.state.get('revision'):
        return []
    close_links(job)
    if not doc_sync.blank_requests(doc) and not doc_sync.title_requests(doc) and not job.state.get('pictures'):
        return []
    try:
        full = doc_sync.get_doc_inline(job.doc_id)
    except SystemExit:
        return []
    if full.get('revisionId') != job.state.get('revision') or doc_sync.has_suggestions(full):
        return []
    revision = doc_sync.paint_blanks(job.doc_id, full)
    if revision:
        own_write(job, revision)
    return place_pictures(job)


def place_pictures(job: Job) -> list[str]:
    """Pictures from 「八、補充資訊」 that are not in the Doc yet (cmd_attach): each one in a paragraph of its own under
    its line. One that fails for now waits for the next sync; after three tries its line keeps just the link."""
    import attachments
    warnings, left = [], []
    for pic in job.state.get('pictures') or []:
        try:
            doc = doc_sync.get_doc_inline(job.doc_id)
        except SystemExit:
            left.append(pic)
            continue
        if doc.get('revisionId') != job.state.get('revision') or doc_sync.has_suggestions(doc):
            left.append(pic)                          # a colleague's change comes in with the next sync first
            continue
        got = attachments.show_picture(job.doc_id, doc, pic['id'], pic.get('width') or attachments.WIDEST_PT)
        if got.get('open'):
            job.state.setdefault('open_links', []).append(got['open'])
        if got.get('revision'):
            own_write(job, got['revision'])
        elif got.get('why') == 'shared':
            warnings.append(attachments.NO_PUBLIC)
        elif got.get('why') == 'line':
            warnings.append(attachments.NO_LINE.format(name=pic['name']))
        elif pic.get('tries', 0) >= 2:
            warnings.append(attachments.NOT_PLACED.format(name=pic['name']))
        else:
            left.append({**pic, 'tries': pic.get('tries', 0) + 1})
    job.state['pictures'] = left
    return list(dict.fromkeys(warnings))


def close_links(job: Job):
    """Pictures' 'anyone with the link' that Google could not close the first time: closed now."""
    if not job.state.get('open_links'):
        return
    import attachments
    job.state['open_links'] = [x for x in job.state['open_links'] if not attachments.close_link(x['file'], x['perm'])]


def fresh() -> dict:
    """What an edit reports back: see sync_up."""
    return {'conflicts': [], 'reload': False, 'held': '', 'why': '', 'marks': [], 'warning': '', 'skipped': [],
            'dropped': False}


def held(result: dict, err, job: 'Job | None' = None) -> dict:
    result['held'], result['why'] = trouble(err), str(err)
    if job is not None:
        with (job.dir / 'log.txt').open('a', encoding='utf-8') as f:
            f.write(f'[{now():%H:%M:%S}] sync held: {str(err)[:1500]}\n')
    return result


def keep_spare(job: Job, text: str) -> Path:
    """Edits that could not go into the minutes, kept next to them so that nothing typed is lost."""
    spare = job.md_path.with_name(job.md_path.stem + '_沒存回的修改.md')
    spare.write_text(text, encoding='utf-8')
    return spare


def pull(job: Job, patient: bool = False) -> dict:
    """Bring the Doc's current paragraphs into the Markdown; report who changed what since the last sync.
    Only when everything typed here already reached the Doc (sync_up goes first). `patient` (the window's refresh,
    which comes again in a few seconds): leave the changes for later while Drive has not listed who made them."""
    info = {'marks': [], 'editors': [], 'edits': 0, 'warning': '', 'skipped': []}
    if job.missing or not job.doc_id or job.md != job.synced_md:
        return info
    doc = doc_sync.get_doc(job.doc_id)
    info['doc'] = doc
    revision = doc.get('revisionId', '')
    if revision == job.state.get('revision'):
        return info
    md = job.md
    first_sync = not job.state.get('revision')
    try:
        merged, changes = doc_sync.merge_remote(md, doc)
    except doc_sync.Structural:
        r = rebase(job, doc, fresh(), True)
        info['warning'], info['skipped'] = r['warning'], r['skipped']
        return info
    if changes and not first_sync:
        revs = revisions(job)
        if patient and not edits_listed(job, revs):
            return info
        authors = authors_since(job, revs=revs)
        info['editors'], info['edits'] = [t('you') if a == '你' else a for a in authors], len(changes)
        info['marks'] = note_remote(job, changes, authors, md, merged)
    elif merged != md:
        relearn(job, md, merged)
    synced(job, merged, revision)
    return info


def rebase(job: Job, doc: dict, result: dict, again: bool) -> dict:
    """A colleague added or removed table rows in the Doc, which paragraphs cannot follow. The Doc as it is now
    becomes the minutes, and the edits this computer has not sent yet go back on top of it, paragraph by paragraph."""
    base, local = job.synced_md, job.md
    rebuilt = doc_sync.doc_to_md(doc)
    who = names(authors_since(job))
    job.log(who, t('log_table_rows'))
    warn_after_send(job, who)
    learn_base = job.dir / '學習基準.md'
    learned_so_far = learn_base.read_text(encoding='utf-8') if learn_base.is_file() else base
    new_md, warning = rebuilt, TABLES_CHANGED
    if local != base:
        try:
            new_md, skipped = doc_sync.carry(rebuilt, base, local)
            result['skipped'] = [typed for _, typed in skipped]
        except doc_sync.Structural:
            spare = keep_spare(job, local)
            warning += t('unsaved_spare', name=spare.name)
            result['dropped'] = True
    try:
        learn_now = doc_sync.carry(rebuilt, base, learned_so_far)[0]
    except doc_sync.Structural:
        learn_now = rebuilt
    synced(job, rebuilt, doc.get('revisionId', ''))
    learn_base.write_text(learn_now, encoding='utf-8')
    if new_md != rebuilt:
        job.write_md(new_md)
    job.save_state()
    result.update(reload=True, warning=warning)
    if again and new_md != rebuilt:
        sent = sync_up(job, again=False)
        for key in ('conflicts', 'held', 'why', 'marks'):
            result[key] = sent[key]
        result['skipped'] += sent['skipped']
        result['warning'] = ' '.join(w for w in (warning, sent['warning']) if w)
    return result


def to_utc(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return ''


def change_words(kind: str, before: str, after: str, where: str) -> str:
    cut = lambda w: w if len(w) <= 24 else w[:24] + '…'   # noqa: E731
    if kind == 'add':
        return t('chg_add', where=where, text=cut(after))
    if kind == 'remove':
        return t('chg_remove', where=where, text=cut(before))
    if not before:
        return t('chg_fill', where=where, text=cut(after))
    if not after:
        return t('chg_delete', where=where, text=cut(before))
    return t('chg_change', where=where, before=cut(before), after=cut(after))


def comment_list(job: Job, md: str) -> tuple[list[dict], list[dict], int]:
    """(comments for the side column, anchors for the preview, how many are new since the last open)."""
    seen = job.state.setdefault('seen_comments', {})
    found, new = [], 0
    for c in doc_sync.comments(job.doc_id):
        if c.get('deleted'):
            continue
        author = c.get('author') or {}
        who = me() if author.get('me') else author.get('displayName') or t('someone')
        replies = [r for r in c.get('replies', []) if not r.get('deleted')]
        known = seen.get(c['id'])
        if known is None and not author.get('me'):
            new += 1
            job.log(who, t('log_comment', text=c.get('content', '')[:40]), at=parse_time(c.get('createdTime')))
        known_replies = set((known or {}).get('replies', []))
        for r in replies:
            ra = r.get('author') or {}
            if r['id'] not in known_replies and known is not None and not ra.get('me'):
                rwho = ra.get('displayName') or t('someone')
                if r.get('action') == 'resolve':
                    job.log(rwho, t('log_resolved', who=who), at=parse_time(r.get('createdTime')))
                elif r.get('content'):
                    job.log(rwho, t('log_replied', who=who, text=r['content'][:40]), at=parse_time(r.get('createdTime')))
        seen[c['id']] = {'replies': [r['id'] for r in replies]}
        if c.get('resolved'):
            continue
        found.append({'id': c['id'], 'who': who, 'at': short_time(c.get('createdTime', '')),
                      'quote': (c.get('quotedFileContent') or {}).get('value', ''), 'text': c.get('content', ''),
                      'replies': [{'who': me() if (r.get('author') or {}).get('me') else
                                   (r.get('author') or {}).get('displayName', ''), 'text': r.get('content', '')}
                                  for r in replies if r.get('content')]})
    # number them in reading order of their quoted words
    plain = doc_sync.plain(md)
    found.sort(key=lambda c: (plain.find(c['quote'].strip()) if c['quote'].strip() and
                              plain.find(c['quote'].strip()) >= 0 else 10 ** 9))
    for n, c in enumerate(found, 1):
        c['n'] = n
    anchors = [{'n': c['n'], 'quote': c['quote']} for c in found if c['quote'].strip()]
    return found, anchors, new


def parse_time(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat((iso or '').replace('Z', '+00:00')).astimezone()
    except ValueError:
        return None


def check_bounces(job: Job):
    """After a send: Gmail's bounce notices for this mail become warnings in the log, once each. Gmail files a
    bounce in the thread of the mail it bounced, so only that thread is read."""
    sent = parse_time(job.result.get('sent_at'))
    sent_id = job.result.get('sent_id') or ''
    if not sent or (now() - sent).days > 30 or not re.fullmatch(r'[0-9a-f]+', sent_id):
        return
    import workspace
    workspace.AUTH['Authorization'] = 'Bearer ' + doc_sync.AUTH['Authorization'].split(' ', 1)[1]
    seen = set(job.state.get('bounces', []))
    rcpts = [a.lower() for a in (job.result.get('mail') or {}).get('to', [])]
    thread = workspace.call(f'{workspace.GMAIL}/messages/{sent_id}?format=minimal').get('threadId', '')
    if not re.fullmatch(r'[0-9a-f]+', thread):
        return
    messages = workspace.call(f'{workspace.GMAIL}/threads/{thread}?format=metadata&metadataHeaders=From').get('messages', [])
    for m in messages:
        heads = {h['name'].lower(): h['value'] for h in m.get('payload', {}).get('headers', [])}
        if m['id'] in seen or m['id'] == sent_id or not re.search(r'mailer-daemon|postmaster', heads.get('from', ''), re.I):
            continue
        seen.add(m['id'])
        msg = workspace.call(f'{workspace.GMAIL}/messages/{m["id"]}?format=metadata'
                             '&metadataHeaders=X-Failed-Recipients&metadataHeaders=Subject')
        heads = {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}
        text = (heads.get('x-failed-recipients', '') + ' ' + msg.get('snippet', '')).lower()
        failed = [a for a in rcpts if a in text]
        if failed:
            why = t('bounce_no_address') if re.search(r'5\.1\.1|does not exist|not found|找不到', text) else ''
            job.log('Gmail', t('log_bounce', names=t('list_sep').join(name_of(job, a) for a in failed), why=why), 'warn',
                    at=parse_time(msg.get('internalDate') and datetime.fromtimestamp(
                        int(msg['internalDate']) / 1000, timezone.utc).isoformat()))
    job.state['bounces'] = sorted(seen)


# --- learning from the user's own edits --------------------------------------------------------

word_span = doc_sync.changed_words


def classify(before: str, after: str, base: str, heard: str) -> str:
    """term: a word the transcript has, written another way (a misheard name) -> glossary.
    pref: a short phrase the minutes keep repeating, deleted -> notes. style: other rewording -> notes as an example.
    once: facts of this meeting (numbers, places, filled blanks, one-off deletions) -> nothing is kept."""
    if not before or BLANK in before:
        return 'once'
    if not after:
        return 'pref' if len(before) <= 12 and (base.count(before) >= 2 or before.endswith(('：', ':'))) else 'once'
    if CHINESE_NUMBER.search(before + after) or max(len(before), len(after)) <= 1:
        return 'once'
    if len(before) <= 12 and len(after) <= 12 and before in heard:
        return 'term'
    return 'style'


def lesson_text(kind: str, before: str, after: str) -> str:
    cut = lambda w: w if len(w) <= 16 else w[:16] + '…'   # noqa: E731
    if kind == 'once' and not before:
        return t('lesson_fill', text=cut(after))
    if kind == 'once' and not after:
        return t('lesson_delete', text=cut(before))
    if kind == 'term':
        return t('lesson_term', before=before, after=after)
    if kind == 'pref':
        return t('lesson_pref', before=before)
    if kind == 'style':
        return t('lesson_style', text=cut(after))
    return t('lesson_change', before=cut(before), after=cut(after))


def glossary_line(heard: str, meant: str) -> str:
    return f'| {heard} | {meant} | {me()} {now():%Y-%m-%d} 在錄音程式確認 |'


def add_line(path: Path, line: str, section: str | None):
    """Append a line to the user's glossary table or under a section of notes.md; nothing twice."""
    text = path.read_text(encoding='utf-8') if path.is_file() else ''
    if line in text.splitlines():
        return
    if section is None:                                  # glossary.md: a table with a header
        if not text.strip():
            text = ('audience: agent\n\n# 公司自己的詞彙表\n\n跨專案都會出現的辨識錯字。\n\n'
                    '| 逐字稿可能出現 | 正確名稱 | 說明 |\n|---|---|---|\n')
        path.write_text(text.rstrip('\n') + '\n' + line + '\n', encoding='utf-8')
        return
    lines = text.split('\n') if text else ['# 補充規則', '']
    head = f'## {section}'
    if head not in lines:
        lines += ['', head, '']
    at = lines.index(head) + 1
    while at < len(lines) and not lines[at].startswith('## '):
        at += 1
    while at > 0 and not lines[at - 1].strip():
        at -= 1
    lines.insert(at, line)
    path.write_text('\n'.join(lines).rstrip('\n') + '\n', encoding='utf-8')


def remove_line(path: Path, line: str):
    if path.is_file():
        lines = path.read_text(encoding='utf-8').split('\n')
        if line in lines:
            lines.remove(line)
            path.write_text('\n'.join(lines), encoding='utf-8')


def remember(job: Job, kind: str, before: str, after: str, source: str) -> dict:
    """Write one lesson where the next minutes will read it, and keep it so the user can take it back. A word goes
    into the project's brief when the meeting has a project (Vin 2026-10-19), else into the glossary."""
    project = project_of(job) if kind == 'term' else ''
    if project:
        briefs.add_heard(project, before, after)
        learned = job.state.setdefault('learned', [])
        item = {'id': len(learned) + 1, 'kind': kind, 'text': lesson_text(kind, before, after), 'where': 'brief',
                'project': project, 'heard': before, 'meant': after, 'source': source, 'off': False}
        learned.append(item)
        job.log(ai_name(), t('log_learned_brief', text=item['text'], project=project))
        return item
    if kind == 'term':
        path, line, section = CONFIG / 'glossary.md', glossary_line(before, after), None
        if source == 'edit':
            line = line.replace('在錄音程式確認', '在錄音程式預覽改的')
    elif kind == 'pref':
        path, section = CONFIG / 'notes.md', '偏好與語氣'
        line = f'- {now():%Y-%m-%d} 在錄音程式預覽刪掉「{before}」，以後不寫。'
    else:
        path, section = CONFIG / 'notes.md', '實例'
        line = f'- {now():%Y-%m-%d} 在錄音程式預覽把「{before}」改成「{after}」。'
    add_line(path, line, section)
    learned = job.state.setdefault('learned', [])
    item = {'id': len(learned) + 1, 'kind': kind, 'text': lesson_text(kind, before, after), 'file': str(path),
            'line': line, 'section': section, 'off': False}
    if kind == 'term':
        item.update(where='glossary', heard=before, meant=after, source=source)
    learned.append(item)
    job.log(ai_name(), t('log_learned_term' if kind == 'term' else 'log_learned_pref', text=item['text']))
    return item


def public(item: dict) -> dict:
    shown = {k: item[k] for k in ('id', 'kind', 'text', 'off')}
    if item.get('project') and item.get('kind') == 'term':   # the window offers 專案小抄 or 詞彙表 for it
        shown.update(where=item.get('where', 'glossary'), project=item['project'])
    return shown


def keep_learned(job: Job, item: dict, on: bool):
    """Write a lesson where it says it goes, or take it out of there. A project renamed since: the meeting's own."""
    if item.get('where') == 'brief':
        if item['project'] not in briefs.projects() and project_of(job):
            item['project'] = project_of(job)
        (briefs.add_heard if on else briefs.remove_heard)(item['project'], item['heard'], item['meant'])
    elif on:
        add_line(Path(item['file']), item['line'], item.get('section'))
    else:
        remove_line(Path(item['file']), item['line'])


def cmd_learn(job: Job, quiet: bool = False, where: str = '', log: bool = True) -> list[dict]:
    where = where or t('where_preview')
    base_file = job.dir / '學習基準.md'
    md = job.md
    if not md:
        return []
    if not base_file.is_file():
        base_file.write_text(md, encoding='utf-8')
        return []
    base = base_file.read_text(encoding='utf-8')
    if base == md:
        return []
    _, old_blocks = doc_sync.parse(base)
    _, new_blocks = doc_sync.parse(md)
    import difflib
    pairs = []
    sm = difflib.SequenceMatcher(None, [b.key for b in old_blocks], [b.key for b in new_blocks], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            pairs += [(old_blocks[i1 + k].plain, new_blocks[j1 + k].plain) for k in range(i2 - i1)
                      if old_blocks[i1 + k].kind == 'cell' and old_blocks[i1 + k].plain != new_blocks[j1 + k].plain]
        elif tag == 'replace':
            pairs += [(old_blocks[i1 + k].plain, new_blocks[j1 + k].plain) for k in range(min(i2 - i1, j2 - j1))
                      if doc_sync.similar(old_blocks[i1 + k].plain, new_blocks[j1 + k].plain)]
    items = []
    heard = (job.dir / '逐字稿.txt').read_text(encoding='utf-8') if (job.dir / '逐字稿.txt').is_file() else ''
    for old, new in pairs:
        before, after = word_span(old, new)
        if not before and not after:
            continue
        if before.replace(BLANK, '').strip() == '' and BLANK in before:    # a blank filled in: a fact, nothing to learn
            if log:
                job.log(me(), change_words('edit', '', after, where))
            continue
        kind = classify(before, after, base, heard)
        if log:
            job.log(me(), change_words('edit', before, after, where))
        if kind == 'once':
            items.append({'id': 0, 'kind': 'once', 'text': lesson_text('once', before, after), 'off': False})
        else:
            items.append(public(remember(job, kind, before, after, 'edit')))
    base_file.write_text(md, encoding='utf-8')
    job.save_state()
    return items


def cmd_unlearn(job: Job, item_id: int, off: bool):
    for item in job.state.get('learned', []):
        if item['id'] == item_id:
            keep_learned(job, item, not off)
            job.log(me(), t('log_unlearn' if off else 'log_relearn', text=item['text']))
            item['off'] = off
            job.save_state()
            out({'learned': public(item)})
            return
    sys.exit(t('item_missing'))


def cmd_move_learned(job: Job, item_id: int, where: str):
    """A learned word goes to the project's brief or to the glossary instead (the two choices under 看過你的修改)."""
    item = next((i for i in job.state.get('learned', []) if i['id'] == item_id), None)
    if item and item.get('kind') == 'term' and not item.get('project'):   # learned before the meeting had a project
        item['project'] = project_of(job)
    if not item or item.get('kind') != 'term' or not item.get('project') or where not in ('brief', 'glossary'):
        sys.exit(t('item_missing'))
    if item.get('where', 'glossary') != where:
        if not item['off']:
            keep_learned(job, item, False)
        item['where'] = where
        if where == 'glossary':
            line = glossary_line(item['heard'], item['meant'])
            item.update(file=str(CONFIG / 'glossary.md'), section=None,
                        line=line.replace('在錄音程式確認', '在錄音程式預覽改的') if item.get('source') == 'edit' else line)
        if not item['off']:
            keep_learned(job, item, True)
        job.log(me(), t('log_learned_brief' if where == 'brief' else 'log_learned_term', text=item['text'],
                         project=item['project']))
        job.save_state()
    out({'learned': public(item)})


# --- pushing an edit -------------------------------------------------------------------------

def push_edit(job: Job, new_md: str, who: str | None = None) -> dict:
    """Keep the edit on this computer first, then send the Doc exactly the paragraphs that changed."""
    if new_md.strip() != job.md.strip():
        job.write_md(new_md)
    return sync_up(job, who)


def sync_up(job: Job, who: str | None = None, again: bool = True) -> dict:
    """Whatever the local Markdown has that the Doc has not yet: send it, then take in what colleagues changed
    meanwhile. A paragraph both sides changed keeps the colleague's words and comes back as a conflict."""
    result = fresh()
    if job.missing or not job.doc_id:
        return result
    base, local = job.synced_md, job.md
    if base == local:
        return result
    started = now()
    try:
        plan, after, as_planned = doc_sync.push(job.doc_id, base, local)
    except doc_sync.Structural:
        try:
            doc = doc_sync.get_doc(job.doc_id)
        except SystemExit as err:
            return held(result, err, job)
        if doc_sync.tables_changed(doc, base):
            return rebase(job, doc, result, again)
        return full_upload(job, base, local, result)
    except SystemExit as err:
        return held(result, err, job)
    if plan.requests:
        warn_after_send(job, who or me())
    try:
        merged, remote = doc_sync.merge_remote(local, after)
    except doc_sync.Structural:                      # a colleague changed a table while the edit went in
        synced(job, local, after.get('revisionId', ''))
        result['conflicts'] = plan.conflicts
        return rebase(job, after, result, False)
    if remote:
        result['marks'] = note_remote(job, remote, authors_since(job, before=started), local, merged)
    if not as_planned:
        result['warning'] = t('not_as_planned')
    synced(job, merged, after.get('revisionId', ''))
    job.save_state()
    result.update(conflicts=plan.conflicts, reload=bool(remote) or bool(plan.conflicts) or not as_planned)
    return result


def open_comment_count(job: Job) -> int:
    return sum(1 for c in doc_sync.comments(job.doc_id) if not c.get('resolved') and not c.get('deleted'))


def full_upload(job: Job, base: str, new_md: str, result: dict) -> dict:
    """Table rows or columns changed on this computer. Only a Claude rewrite does that (the preview refuses to), and
    ai_edit checked first that the whole Doc can be uploaded: no comment open, no colleague edit since the last
    sync. If either turned up in the seconds since, Claude's change is dropped instead of overwriting them."""
    import md_to_gdoc
    try:
        doc = doc_sync.get_doc(job.doc_id)
        blocked = WHOLE_COMMENTS if open_comment_count(job) else ''
    except SystemExit as err:
        return held(result, err)
    if not blocked:
        try:
            _, remote = doc_sync.merge_remote(base, doc)
        except doc_sync.Structural:
            remote = ['changed']
        blocked = WHOLE_COLLEAGUE if remote else ''
    if blocked:
        return drop_rewrite(job, base, doc, result, blocked)
    md_to_gdoc.AUTH['Authorization'] = doc_sync.AUTH['Authorization']
    try:
        refresh_record(job)
    except Exception as err:                         # the Drive calls md_to_gdoc makes raise urllib's own errors
        return held(result, f'OFFLINE: {err}')
    done = subprocess.run([sys.executable, str(SCRIPTS / 'md_to_gdoc.py'), str(job.md_path), '--update'],
                          capture_output=True, text=True, timeout=300, env={**os.environ, 'MINUTES_NO_SEND': '1'})
    if done.returncode:
        return held(result, done.stdout + done.stderr, job)
    try:
        doc = doc_sync.get_doc(job.doc_id)
    except SystemExit as err:
        return held(result, err)
    synced(job, new_md, doc.get('revisionId', ''))
    after_sync(job, doc)
    job.save_state()
    result.update(reload=True, whole=True)            # a Doc open in the window loads again
    return result


def drop_rewrite(job: Job, base: str, doc: dict, result: dict, why: str) -> dict:
    """A change to the tables cannot reach the Doc: the minutes go back to the Doc as it is now, and the change is
    kept in a file next to them."""
    spare = keep_spare(job, job.md)
    try:
        merged, _ = doc_sync.merge_remote(base, doc)
    except doc_sync.Structural:
        merged = doc_sync.doc_to_md(doc)
    synced(job, merged, doc.get('revisionId', ''))
    (job.dir / '學習基準.md').write_text(merged, encoding='utf-8')
    for name in ('復原.md', '復原後.md'):
        (job.dir / name).unlink(missing_ok=True)
    job.log(me(), t('log_tables_not_saved'), 'warn')
    job.save_state()
    result.update(reload=True, warning=why + t('change_spare', name=spare.name), dropped=True)
    return result


def whole_upload_blocked(job: Job) -> str:
    """Why a change to table rows or columns cannot go to the Doc right now ('' when it can)."""
    if connect() or job.md != job.synced_md:
        return ai_words(AI_TABLES_OFFLINE)
    try:
        if open_comment_count(job):
            return ai_words(AI_TABLES_COMMENTS)
        doc = doc_sync.get_doc(job.doc_id)
    except SystemExit:
        return ai_words(AI_TABLES_OFFLINE)
    try:
        _, remote = doc_sync.merge_remote(job.synced_md, doc)
    except doc_sync.Structural:
        remote = ['changed']
    return ai_words(AI_TABLES_COLLEAGUE) if remote else ''


def refresh_record(job: Job):
    """md_to_gdoc.py keeps its own idea of the Doc's last known state; bring it up to date right before a full
    upload, which the caller has just checked against the local copy."""
    import md_to_gdoc
    sidecar = md_to_gdoc.sidecar_for(job.md_path)
    if sidecar.is_file():
        rec = json.loads(sidecar.read_text())
        rec.update(sha256=md_to_gdoc.sha(md_to_gdoc.export_text(job.doc_id)), modifiedTime=md_to_gdoc.modified_time(job.doc_id))
        md_to_gdoc.write_record(sidecar, rec)


# --- the preview the window shows --------------------------------------------------------------

def remember_shown(job: Job, page_md: str) -> str:
    """What the window's editor holds (a preview it is about to get, or the page it just saved), read back to
    Markdown, kept under a token: the next save is compared with exactly that, so only what was typed since counts,
    and what the minutes became meanwhile (a colleague's words) is never typed back over."""
    token = hashlib.sha1(page_md.encode('utf-8')).hexdigest()[:16]
    folder = job.dir / '預覽基準'
    folder.mkdir(exist_ok=True)
    path = folder / f'{token}.md'
    if path.is_file():
        path.touch()
    else:
        path.write_text(page_md, encoding='utf-8')
    for old in sorted(folder.glob('*.md'), key=lambda f: f.stat().st_mtime)[:-20]:
        old.unlink(missing_ok=True)
    return token


def page_token(job: Job, html_text: str) -> str:
    """The token for a preview as it is sent to the window."""
    import minutes_html
    return remember_shown(job, minutes_html.back(html_text))


def shown_token(job: Job, md: str) -> str:
    return page_token(job, preview(md, [], []))


def shown_md(job: Job, token: str) -> str | None:
    if not re.fullmatch(r'[0-9a-f]{16}', token or ''):
        return None
    path = job.dir / '預覽基準' / f'{token}.md'
    return path.read_text(encoding='utf-8') if path.is_file() else None


def answer(job: Job, result: dict, html: bool = False, **extra):
    """What every edit returns to the window."""
    md = job.md
    skipped = list(extra.pop('skipped', [])) + list(result.get('skipped', []))
    data = {'saved_at': f'{now():%H:%M}', 'conflicts': result['conflicts'], 'held': result['held'],
            'warning': result['warning'], 'todo': todo_items(job, md), 'attendees': attendees(md), 'skipped': skipped,
            'people': meeting_people(job), 'speakers': speakers_shown(job), 'silent': silent_people(job),
            'calendar': calendar_payload(job), 'check': check_items(job), 'attachments': attachments_listed(md), **extra}
    if result['reload'] or skipped or html:
        data['html'] = preview(md, result['marks'], current_anchors(job, md))
        data['shown'] = page_token(job, data['html'])
    data['can_undo'] = (job.dir / '復原.md').is_file() and (job.dir / '復原後.md').is_file()
    data['reload_doc'] = bool(result.get('whole'))
    out(data)


def cmd_save(job: Job, edited: Path, token: str = ''):
    """What the user typed: the preview read back now, against the preview they were looking at read back the same
    way, so only paragraphs the user touched change, nothing the read-back drops is lost, and nothing a colleague
    changed meanwhile is typed back over."""
    import minutes_html
    md = job.md
    shown = shown_md(job, token)
    after = minutes_html.back(edited.read_text(encoding='utf-8'))
    before = shown if shown is not None else minutes_html.back(preview(md, [], []))
    try:
        new_md, skipped = doc_sync.carry(md, before, after)
    except doc_sync.Structural:
        result = fresh()
        result.update(reload=True, warning=TABLE_SHAPE)
        answer(job, result, unsaved=True)
        return
    typed = remember_shown(job, after)               # the page as saved: the next save starts from here
    result = push_edit(job, new_md)
    if minutes_html.back(preview(job.md, [], [])) != after:
        result['reload'] = True                       # the page shows something the minutes no longer say
    answer(job, result, skipped=[t for _, t in skipped], typed=typed)


def current_anchors(job: Job, md: str) -> list[dict]:
    try:
        return comment_list(job, md)[1]
    except SystemExit:
        return []


# --- files, links and pictures for 「八、補充資訊」 ---------------------------------------------------

def attachments_listed(md: str) -> list[dict]:
    import attachments
    return attachments.listed(md)


def cmd_attach(job: Job, note: str, raw: str):
    """What the user picked in the box under the Doc, with the sentence they wrote about it, as lines of the
    minutes' last section (attachments.py). Every item is checked first, the Doc's latest version comes in, files
    and pictures go to Drive, then the lines go into the Doc; pictures follow once the Doc is synced (after_sync)."""
    import tempfile
    import attachments
    items = attachments.items_from(raw)
    if not job.doc_id or job.missing:
        sys.exit(attachments.NO_DOC)
    if connect():
        sys.exit(attachments.OFFLINE)
    work = Path(tempfile.mkdtemp(prefix='attach-'))
    try:
        for it in items:                             # a picture the Doc cannot take stops everything before upload
            if it['kind'] == 'image':
                it['path'] = attachments.doc_ready_picture(it['path'], work)
                it['name'] = it['path'].name
                it['width'] = attachments.width_pt(it['path'])
        sent = sync_up(job)                          # the lines go after what colleagues wrote meanwhile
        if not sent['held']:
            pull(job)
        folder = None
        for it in items:
            if it['kind'] == 'link':
                it['link'] = it['url']
                continue
            folder = folder or attachments.folder_for(job.state, job.doc_id, job.lang)
            it.update(attachments.upload(it['path'], folder, it['name'], attachments.mime_of(it['path'])))
            if it['kind'] == 'image':
                it['local'] = attachments.keep_beside(job.md_path, it['path'])
    except SystemExit as err:
        job.save_state()
        sys.exit(attachments.drive_trouble(err))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    lines = attachments.lines_for(items, note, job.lang)
    result = push_edit(job, attachments.add_lines(job.md, lines, job.lang))
    if any(line not in job.md for line in lines if not line.startswith('![')):
        result['warning'] = attachments.CROWDED      # a colleague changed the end of the minutes at that moment
        attachments.throw_away([it['id'] for it in items if it.get('id')])
        for it in items:
            if it.get('local') and it['local'] not in job.md:
                (job.md_path.parent / urllib.parse.unquote(it['local'])).unlink(missing_ok=True)
        job.save_state()
        return answer(job, result, html=True, reply='', changed=False)
    files = [it['id'] for it in items if it.get('id')]
    if files:                                        # for the mail: the files whoever gets the minutes can open
        import md_to_gdoc
        sidecar = md_to_gdoc.sidecar_for(job.md_path)
        if sidecar.is_file():
            record = read_json(sidecar)
            md_to_gdoc.write_record(sidecar, {**record, 'attach_files': list(dict.fromkeys(
                record.get('attach_files', []) + files))})
    job.state['pictures'] = (job.state.get('pictures') or []) + [
        {'id': it['id'], 'name': it['name'], 'width': it['width']} for it in items if it['kind'] == 'image']
    warnings = [result['warning']] if result['warning'] else []
    if not result['held'] and job.state['pictures']:
        try:
            warnings += after_sync(job, doc_sync.get_doc(job.doc_id))
        except SystemExit:
            pass                                     # they go in with the next refresh
    result['warning'] = ' '.join(warnings)
    names = t('list_sep').join(it['name'] for it in items)
    job.log(me(), t('log_attached', names=names))
    job.save_state()
    answer(job, result, html=True, reply=t('reply_attached', names=names), changed=False)


# --- an agent changes the minutes (mcp_server.py) ------------------------------------------------
# Claude Code asked by the user: the change goes in like the window's own, Doc and all, and the log names the agent.

def agent_edit(job: Job, change) -> str:
    """The minutes after `change(md)`, from the Doc as it is now; the user's own typing is learned first and the
    agent's change is never learned as theirs."""
    actor = os.environ.pop('VINUTES_ACTOR', None)     # what the user typed is logged as theirs, not the agent's
    try:
        cmd_learn(job, quiet=True)
    finally:
        if actor is not None:
            os.environ['VINUTES_ACTOR'] = actor
    if job.doc_id and not connect():
        sync_up(job, user_name())                    # anything not sent yet is what the user typed
        try:
            pull(job)
        except SystemExit:
            pass
    md = job.md
    new = change(md)
    relearn(job, md, new)
    result = push_edit(job, new, who=me())
    job.save_state()
    out({'changed': new != md, 'held': bool(result.get('held')), 'warning': result.get('warning') or '',
         'sent': bool(job.result.get('sent_at')), 'doc_url': job.result.get('doc_url') or ''})
    return new


def cmd_note(job: Job, text: str):
    import attachments
    text = text.strip()
    if not text:
        sys.exit(t('note_empty'))
    line = '- ' + doc_sync.escape_lead(' '.join(text.split()))
    agent_edit(job, lambda md: attachments.add_lines(md, [line], job.lang))
    job.log(me(), t('log_noted', text=cut_words(text, 30)), 'note')


def cmd_replace(job: Job, old: str, new: str):
    if '\n' in new or '\n' in old:
        sys.exit(t('replace_lines'))
    def change(md: str) -> str:
        found = md.count(old) if old else 0
        if found != 1:
            sys.exit(t('replace_missing') if not found else t('replace_many', n=found))
        return md.replace(old, new)
    agent_edit(job, change)
    job.log(me(), t('log_replaced', old=cut_words(old, 20), new=cut_words(new, 20)), 'edit')


# --- Claude changes the minutes --------------------------------------------------------------

def ai_edit(job: Job, request: str, label: str, pictures: list[Path] = (), settle=None, refs: list[dict] = ()):
    """The AI changes the minutes as asked. `pictures`: what the user pasted with the sentence, and `refs` the files
    and links handed with it (references.py), for the AI to look at, never into the minutes. `settle(changed, new)`:
    a 待確認 card put right, run once the AI has answered; returns what it learned."""
    sys.path.insert(0, str(SCRIPTS))
    import ai_runner
    from auto_minutes import env
    ai = ai_name()
    if not ai_runner.find():
        sys.exit(t('ai_missing', ai=ai_runner.AIS[ai_runner.chosen()]))
    learned = cmd_learn(job)                         # the user's own typing first, so it is never mixed with Claude's
    opened = job.md
    if job.doc_id and not connect():                 # Claude starts from the Doc as it is now
        sync_up(job)
        try:
            pull(job)
        except SystemExit:
            pass
    md = job.md
    work = job.dir / '工作'
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    (work / '紀錄.md').write_text(md, encoding='utf-8')
    for src, name in ((job.dir / '逐字稿.txt', '逐字稿.txt'), (CONFIG / 'notes.md', '使用者規則.md'),
                      (CONFIG / 'glossary.md', '公司詞彙表.md')):
        if src.is_file():
            shutil.copy(src, work / name)
    brief = briefs.markdown(project_of(job), job.lang) if project_of(job) else ''
    if brief:
        (work / briefs.FILE_NAME).write_text(brief, encoding='utf-8')
    import references
    more, read = references.prepare(list(refs), work)
    shown = picture_copies(list(pictures) + more, work)
    prompt = edit_prompt(job.lang, request, [p.name for p in shown], read)
    try:
        done = ai_runner.run(prompt, work, write=False, timeout=AI_TIMEOUT, env=env(), pictures=shown, task='edit')
    except subprocess.TimeoutExpired:
        sys.exit(t('ai_timeout', ai=ai))
    return ai_edit_done(job, done, work, md, opened, label, request, learned, ai, settle)


def picture_copies(pictures: list[Path], work: Path) -> list[Path]:
    """The pasted pictures in the AI's folder as screenshot-1.png, …: a kind it can open, a size it can read."""
    import tempfile
    import attachments
    shown = []
    scratch = Path(tempfile.mkdtemp(prefix='pictures-'))
    try:
        for n, src in enumerate(pictures, 1):
            ready = attachments.doc_ready_picture(Path(src), scratch)
            shown.append(work / f'screenshot-{n}{ready.suffix.lower()}')
            shutil.copy(ready, shown[-1])
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return shown


def edit_prompt(lang: str, request: str, pictures: list[str] = (), refs: list[tuple[str, str]] = ()) -> str:
    """What the AI is told for one change. The minutes keep their language; the one line it writes back to the
    user (說明.txt) is in the app's language. `pictures`: the screenshots in the folder that came with the request;
    `refs`: the reference files there, as (name in the folder, the file's own name or the link)."""
    from i18n import ui_lang
    if lang == 'en':
        reply = ('one sentence in English, under 20 words, saying what you changed, e.g. "Filled in the chair: Amy Chen"'
                 if ui_lang() == 'en' else '一句 30 個字以內的繁體中文，說你改了什麼，例如「主持人填入 Amy Chen」')
        return (
            'You are helping the user change a set of meeting minutes: 紀錄.md in this folder.\n'
            f'The user\'s request: {request}\n'
            + (f'The user attached screenshots: {", ".join(pictures)}. Open them first: what they mark is the place '
               'to change. The screenshots themselves do not go into 紀錄.md.\n' if pictures else '')
            + (f'The user attached reference material: {", ".join(f"{n} ({what})" for n, what in refs)}. Read it '
               "first and change the minutes from what it says; don't paste it into 紀錄.md whole.\n" if refs else '')
            + 'Rules:\n'
            '- Edit 紀錄.md directly and change only what the request is about; leave every other paragraph exactly as it is.\n'
            '- Keep the layout: headings with #, ##, ###, lists with - or 1., tables with |.\n'
            '- Do not add anything the request does not say; write [__] for anything uncertain.\n'
            '- Follow 使用者規則.md (the user\'s rules), 公司詞彙表.md (the company glossary) and 專案小抄.md (the '
            'project\'s people and terms) if present; read 逐字稿.txt '
            '(the transcript) when you need what was actually said.\n'
            f'- When done, write in 說明.txt {reply}.\n'
            '- If the request cannot be done, leave 紀錄.md alone and write the reason in 說明.txt.\n'
            'In this mode you cannot run commands or use the web; you can only read and write files in this folder.')
    reply = ('一句 30 個字以內的繁體中文，說你改了什麼，例如「主持人填入王小明」' if ui_lang() == 'zh-TW' else
             'one sentence in English, under 20 words, saying what you changed, e.g. "Filled in the chair: 王小明"')
    return (
        '你在幫使用者修改一份會議紀錄，紀錄是這個資料夾裡的 紀錄.md。\n'
        f'使用者的要求：{request}\n'
        + (f'使用者附了截圖：{"、".join(pictures)}。先打開來看，截圖上標示的就是要改的地方；截圖本身不要放進 紀錄.md。\n'
           if pictures else '')
        + (f'使用者附了參考資料：{"、".join(f"{n}（{what}）" for n, what in refs)}。先讀過，照裡面的內容修改紀錄；'
           '參考資料本身不要整份貼進 紀錄.md。\n' if refs else '')
        + '規則：\n'
        '- 直接修改 紀錄.md，只改要求提到的地方，其他段落一個字都不要動。\n'
        '- 保留原本的格式：標題用 #、##、###，條列用 - 或 1.，表格用 |。\n'
        '- 要求裡沒有說的事不要自己補，不確定的資訊寫 [__]。\n'
        '- 用語照 使用者規則.md、公司詞彙表.md 與 專案小抄.md（有的話）；需要原話時看 逐字稿.txt。\n'
        f'- 改完在 說明.txt 寫{reply}。\n'
        '- 這個要求做不到時不要改 紀錄.md，在 說明.txt 寫做不到的原因。\n'
        '這個模式不能執行指令也不能連網，只能讀寫這個資料夾裡的檔案。')


def ai_edit_done(job: Job, done, work: Path, md: str, opened: str, label: str, request: str, learned: list, ai: str,
                 settle=None):
    """The AI's change, checked and saved (or why it was not)."""
    import ai_runner
    with (job.dir / 'log.txt').open('a', encoding='utf-8') as f:
        f.write(f'[{now():%H:%M:%S}] ask {label}: exit {done.returncode}\n{(done.stdout + done.stderr)[-1500:]}\n')
    if done.returncode:
        from auto_minutes import friendly
        sys.exit(friendly(done.stdout + done.stderr, t('ai_error', ai=ai)))
    new = (work / '紀錄.md').read_text(encoding='utf-8') if (work / '紀錄.md').is_file() else md
    note = (work / '說明.txt').read_text(encoding='utf-8').strip().split('\n')[0][:60] if (work / '說明.txt').is_file() else ''
    if new.strip() == md.strip():
        # nothing to change (the minutes may have it right already): a correction's card still goes, as the user
        # answered it (Vin 2026-10-19); nothing is learned. An AI that wrote no answer at all leaves it to try again.
        learned += settle(False, md) if settle and note else []
        answer(job, fresh(), html=md != opened, reply=note or t('ai_nothing'), changed=False, learned=learned)
        return
    if not re.search(r'(?m)^#{1,3} ', new) or len(new) < len(md) * 0.15:
        sys.exit(t('ai_broken', ai=ai))
    if ai_runner.new_leaks(md, new):
        sys.exit(t('ai_leaks', ai=ai))
    if job.doc_id and doc_sync.shapes(doc_sync.parse(md)[1]) != doc_sync.shapes(doc_sync.parse(new)[1]):
        why = whole_upload_blocked(job)              # checked before anything is written, so a refusal changes nothing
        if why:
            sys.exit(why)
    (job.dir / '復原.md').write_text(md, encoding='utf-8')          # before Claude
    (job.dir / '復原後.md').write_text(new, encoding='utf-8')       # Claude's version, to undo only what Claude did
    relearn(job, md, new)
    result = push_edit(job, new, who=ai)
    if result['dropped']:                            # the Doc changed shape meanwhile: Claude's change is in a side file
        for name in ('復原.md', '復原後.md'):
            (job.dir / name).unlink(missing_ok=True)
        reply, result['warning'] = result['warning'], ''
        answer(job, result, reply=reply, changed=False, learned=learned)
        return
    if settle:                                       # the user's correction: logged as theirs by settle()
        learned += settle(True, new)
    else:
        job.log(ai, t('log_quick', label=t(f'quick_{label}')) if label in QUICK['en'] else
                t('log_asked', text=cut_words(request)))
    job.save_state()
    said = (note or t('ai_done')) + (t('ai_saved_doc') if not result['held'] else '')
    answer(job, result, html=True, reply=said, changed=True, learned=learned)


def cut_words(text: str, n: int = 16) -> str:
    return text if len(text) <= n else text[:n] + '…'


def quoted(texts: list[str]) -> str:
    """「甲」、「乙」 / “A”, “B”: paragraphs named in a warning, each cut short."""
    return t('list_sep').join(t('quote', text=cut_words(c, 20)) for c in texts)


def cmd_undo(job: Job):
    """Take back what Claude changed, and only that: paragraphs someone touched after Claude stay as they are."""
    backup, claude_said = job.dir / '復原.md', job.dir / '復原後.md'
    if not backup.is_file() or not claude_said.is_file():
        sys.exit(t('undo_nothing'))
    learned = cmd_learn(job)
    before, after = claude_said.read_text(encoding='utf-8'), backup.read_text(encoding='utf-8')
    md = job.md
    try:
        new_md, kept = doc_sync.carry(md, before, after)
    except doc_sync.Structural:
        sys.exit(t('undo_tables', ai=ai_name()))
    relearn(job, md, new_md)
    result = push_edit(job, new_md)
    backup.unlink(missing_ok=True)
    claude_said.unlink(missing_ok=True)
    job.log(me(), t('log_undo', ai=ai_name()))
    job.save_state()
    answer(job, result, html=True, kept=[claude for claude, _ in kept], learned=learned)


# --- comments and guesses --------------------------------------------------------------------

def cmd_reply(job: Job, cid: str, text: str):
    text = text.strip()
    if not text:
        sys.exit(t('reply_empty'))
    try:
        r = doc_sync.reply(job.doc_id, cid, text)
    except SystemExit as err:
        sys.exit(google_says(err, t('reply_not_sent')))
    seen = job.state.setdefault('seen_comments', {}).setdefault(cid, {'replies': []})
    seen['replies'].append(r.get('id'))
    try:
        author = next((c for c in doc_sync.comments(job.doc_id) if c['id'] == cid), {}).get('author', {})
    except SystemExit:
        author = {}
    said = cut_words(text, 40)
    if author.get('me'):
        job.log(me(), t('log_replied_own', text=said))
    elif author.get('displayName'):
        job.log(me(), t('log_replied', who=author['displayName'], text=said))
    else:
        job.log(me(), t('log_replied_anon', text=said))
    job.save_state()
    out({'reply': {'who': me(), 'text': text}})


def cmd_resolve(job: Job, cid: str):
    try:
        doc_sync.resolve(job.doc_id, cid)
    except SystemExit as err:
        sys.exit(google_says(err, t('resolve_not_done')))
    try:
        comment = next((c for c in doc_sync.comments(job.doc_id) if c['id'] == cid), {})
    except SystemExit:
        comment = {}
    seen = job.state.setdefault('seen_comments', {}).setdefault(cid, {'replies': []})
    seen['replies'] = [r['id'] for r in comment.get('replies', [])]
    author = comment.get('author') or {}
    if author.get('me'):
        job.log(me(), t('log_resolved_own'))
    elif author.get('displayName'):
        job.log(me(), t('log_resolved', who=author['displayName']))
    else:
        job.log(me(), t('log_resolved_anon'))
    job.save_state()
    out({'resolved': cid})


def cmd_confirm(job: Job, label: str):
    item = next((c for c in check_items(job) if c['label'] == label), None)
    if not item:
        sys.exit(t('check_missing'))
    job.state.setdefault('confirmed', []).append(label)
    job.log(me(), t('log_confirmed', label=label))
    learned = []
    who = item.get('person') or item.get('who')
    if who and project_of(job):                       # 新的人名 or 講者 B 推測是…: the person is the project's
        briefs.add_person(project_of(job), who, item.get('role', ''))
        job.log(me(), t('log_brief_person', name=who, project=project_of(job)))
    heard, meant = item['heard'], item['meant']
    tidy = all(0 < len(w) <= 30 and not re.search(r'[|\n\r]', w) for w in (heard, meant))
    if tidy and heard != meant and heard in label and meant in label:
        learned.append(public(remember(job, 'term', heard, meant, 'confirm')))
    job.save_state()
    out({'check': check_items(job), 'learned': learned})


def cmd_skip(job: Job, label: str):
    """A guess the user does not want to handle: the card goes, the minutes stay as they are, nothing is learned."""
    if not any(c['label'] == label for c in check_items(job)):
        sys.exit(t('check_missing'))
    job.state.setdefault('skipped', []).append(label)
    job.log(me(), t('log_skipped', label=label))
    job.save_state()
    out({'check': check_items(job)})


# what the AI is told when the user puts a guess right, in the minutes' language
CORRECT = {
    'zh-TW': {'heard': '逐字稿的「{heard}」在會議記錄裡寫成「{meant}」，正確的是「{right}」。把指這個的「{meant}」都改成'
                       '「{right}」，其他地方不要動。',
              'word': '會議記錄裡的「{meant}」有誤，正確的是「{right}」。把指這個的「{meant}」都改成「{right}」，其他地方不要動。',
              'note': '這一項待確認的內容有誤：「{label}」。正確的是：{right}。照這個修改會議記錄。'},
    'en': {'heard': 'The transcript\'s “{heard}” is “{meant}” in the minutes, but it is “{right}”. Change “{meant}” to '
                    '“{right}” wherever it means this, and nothing else.',
           'word': 'The minutes have “{meant}”, which is wrong: it is “{right}”. Change “{meant}” to “{right}” wherever '
                   'it means this, and nothing else.',
           'note': 'This item to confirm is wrong: “{label}”. What is right: {right}. Change the minutes to match.'},
}


def cmd_correct(job: Job, label: str, right: str):
    """A guess the user put right (修改). A name for a line asking who a voice is names the voice, as in 人員;
    anything else goes to the AI. Once the AI has answered the card goes, also when the minutes had it right
    already; the right word is learned only when the AI wrote it into the minutes. If the AI fails, or writes
    no answer at all, the card stays."""
    right = one_line(right, 60)
    item = next((c for c in check_items(job) if c['label'] == label), None)
    if not item:
        sys.exit(t('check_missing'))
    if not right:
        sys.exit(t('correct_empty'))
    voice = item.get('speaker') or item.get('voice')
    a_name = (WORD.fullmatch(right) and re.search(r'[A-Za-z\u4e00-\u9fff]', right) and not NOT_A_NAME.search(right)
              and not NOBODY.search(right))
    asks = item.get('voice') and not item['heard'] and not item['meant'] and ASKS_WHO.search(label)
    if a_name and not item['heard'] and (item.get('speaker') or asks):   # 講者 B 推測是 Ken / 講者 B …請補姓名:
        # the voice gets the name; a word guess about what a voice said (講者 C 說的「SL」推測是 SEO) stays a word
        return cmd_speaker(job, voice, right)
    meant = item.get('person') or item['meant']
    words = CORRECT.get(job.lang, CORRECT['zh-TW'])
    kind = 'heard' if item['heard'] and meant else 'word' if meant else 'note'
    request = words[kind].format(heard=item['heard'], meant=meant, right=right, label=label)

    def settle(changed: bool, new: str) -> list:
        job.state.setdefault('corrected', []).append(label)
        written = changed and right in new                # what the AI put in, not an instruction typed
        job.log(me(), t('log_corrected', label=label, right=right))
        if item.get('person') and project_of(job) and written and WORD.fullmatch(right) and not NOT_A_NAME.search(right):
            briefs.add_person(project_of(job), right, item.get('role', ''))
            job.log(me(), t('log_brief_person', name=right, project=project_of(job)))
        heard = item['heard']
        tidy = (written and heard and heard != right and WORD.fullmatch(heard) and WORD.fullmatch(right)
                and not re.search(r'[|]', heard + right))   # a sentence typed as the fix is not a word to learn
        learned = [public(remember(job, 'term', heard, right, 'confirm'))] if tidy else []
        job.save_state()
        return learned
    ai_edit(job, request, label, settle=settle)


def cmd_ask_many(job: Job, raw: str):
    """What was still waiting under 待修改 when the window closed (each {kind: ask | quick | correct, text, item,
    pictures, refs}), done in order in this one process, which holds the meeting's turn; one that cannot be done is
    passed over and the rest still go."""
    try:
        items = [x for x in json.loads(raw) if isinstance(x, dict)]
    except ValueError:
        items = []
    for x in items:
        job = Job(job.dir)                           # each one starts from the minutes the one before left
        kind, text = x.get('kind'), str(x.get('text') or '').strip()
        try:
            if kind == 'correct':
                cmd_correct(job, str(x.get('item') or ''), text)
            elif kind == 'quick' and QUICK_NAMES.get(text, text) in QUICK['en']:
                key = QUICK_NAMES.get(text, text)
                ai_edit(job, QUICK[job.lang][key], key)
            elif kind == 'ask' and text:
                import references
                pictures = [Path(p) for p in x.get('pictures') or [] if isinstance(p, str)]
                ai_edit(job, text, text, pictures, refs=references.checked(x.get('refs') or []))
        except SystemExit as err:
            job.log(me(), str(err.code or ''))


# --- open ------------------------------------------------------------------------------------

def transcript(job: Job) -> list[dict]:
    lines = []
    path = job.dir / '逐字稿.txt'
    voices = speakers.load(job.dir)
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            m = re.match(r'\[(?:(\d+):)?(\d+):(\d{2})\]\s*(.*)', line)
            if m:
                h, mi, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
                item = {'at': line[1:line.index(']')], 'sec': h * 3600 + mi * 60 + s, 'text': m.group(4)}
                if voices:
                    n = len(lines)
                    item['group'] = voices['lines'][n] if n < len(voices['lines']) else ''
                    item['who'] = speakers.name_of(voices, n, t('speaker'))
                lines.append(item)
    return lines


def voices_view(job: Job) -> list[dict]:
    """The voices in the transcript, most talk first: who (a name or 講者 X), how long, a stretch to listen to."""
    data = speakers.load(job.dir)
    return [{'group': k, 'name': g.get('name') or '', 'label': g.get('name') or f'{t("speaker")} {k}',
             'minutes': max(1, round(g.get('seconds', 0) / 60)), 'sample': g.get('sample') or [0, 0]}
            for k, g in (data.get('groups') or {}).items() if not g.get('off')]


def voices_off(job: Job) -> list[dict]:
    """The voices the user took off, listed under 人員 with 復原."""
    groups = speakers.load(job.dir).get('groups') or {}
    return [{'group': k, 'label': f'{t("speaker")} {k}'} for k, g in groups.items() if g.get('off')]


ABOUT_VOICE = r'^\s*(?i:講者|speaker)\s*{}(?![A-Za-z])'    # a 待確認 line about one voice: 講者 C 只有附和…
WORD = re.compile(r'[^，。,;；:：!！?？「」『』"“”\n]{1,30}')        # a name or a term, not a sentence
ASKS_WHO = re.compile(r'姓名|名字|是誰|身分|身份|未列與會|請補|併入|\bname\b|\bwho\b', re.I)   # the line asks who it is
NOBODY = re.compile(r'雜音|噪音|不是人|誤判|同一|分身|不用|沒有|無此|同\s*[A-Z]\b|\bnoise\b|\bnobody\b|same as', re.I)


def cmd_drop_voice(job: Job, group: str, back: bool = False):
    """移除講者 X under 人員, or 復原 (Vin 2026-10-19). Taken off, the voice is no one: its menu and card go, the name
    the minutes gave it is no longer its, and the 待確認 items about it are put aside; the minutes stay as they are."""
    about = re.compile(ABOUT_VOICE.format(re.escape(group)))
    aside = [c['label'] for c in check_items(job) if c.get('speaker') == group or about.match(c['label'])]
    speakers.take_off(job.dir, group, not back)       # after: an off voice's items are no longer listed
    who = f'{t("speaker")} {group}'
    kept = job.state.setdefault('voices_off', {})    # what removing put aside, for 復原 to bring back
    if not back:
        kept[group] = {'aside': aside, 'name': speaker_map(job).get(group, '')}
        data = read_json(job.dir / MEETING_PEOPLE)
        data['speakers'] = {g: n for g, n in speaker_map(job).items() if g != group}
        write_json(job.dir / MEETING_PEOPLE, data)
        job.state.setdefault('skipped', []).extend(aside)
    elif group in kept:
        was = kept.pop(group)
        job.state['skipped'] = [x for x in job.state.get('skipped', []) if x not in was.get('aside', [])]
        if was.get('name'):
            save_speaker(job, group, was['name'])
    job.save_state()
    job.log(me(), t('log_voice_back' if back else 'log_voice_off', who=who), 'speaker')
    answer(job, fresh(), transcript=transcript(job), voices=voices_view(job), voices_off=voices_off(job),
           voice_names=speakers.known_names(), people=meeting_people(job), speakers=speakers_shown(job),
           silent=silent_people(job), log=job.log_entries()[:200])


def cmd_speaker(job: Job, group: str, name: str, line: str = ''):
    """The user named a voice in the transcript: every line of it, or one line."""
    before = (next((v['name'] for v in voices_view(job) if v['group'] == group), '')
              or speaker_map(job).get(group, ''))       # the name the minutes use for this voice now
    guesses = [c['label'] for c in check_items(job) if group in (c.get('speaker'), c.get('voice'))]   # before the name
    speakers.set_name(job.dir, group, name, int(line) if line.isdigit() else None)
    who = name.strip()[:30]
    lines = transcript(job)
    what = ((t('speaker_line_at', at=lines[int(line)]['at']) if int(line) < len(lines) else t('speaker_a_line'))
            if line.isdigit() else f'{t("speaker")} {group}')
    job.log(me(), t('log_speaker', what=what, who=who), 'speaker')
    extra = {'transcript': transcript(job), 'voices': voices_view(job), 'voice_names': speakers.known_names(),
             'remembered': who}
    if line.isdigit():                                # one line: only the transcript
        return out(extra)
    project = project_of(job)                        # the whole voice: the person was there, the minutes say so
    names = meeting_people(job)
    if before and not same_name(before, who):         # the voice had another name: that one goes, in the minutes too
        names = [n for n in names if not same_name(n, before)]
    names = add_name(names, who)
    save_speaker(job, group, who)
    save_project_people(project, add_name(project_people(project), who))
    remember_roster(job, names)
    settled = guesses                                # the guesses about it are answered, also if it is renamed later
    if settled:
        job.state.setdefault('confirmed', []).extend(settled)
        job.save_state()
    result = people_change(job, names, [(group, before, who)])
    answer(job, result, html=bool(result.get('reload')), people=meeting_people(job), speakers=speakers_shown(job),
           silent=silent_people(job), **extra)


def finished_body(body: str) -> str:
    """The mail goes out when the minutes are done (Vin 2026-10-15): a paragraph asking the recipients to fill the
    [__] blanks is dropped."""
    kept = [p for p in re.split(r'\n\s*\n', body) if BLANK not in p]
    return '\n\n'.join(kept).strip()


def mail_defaults(job: Job) -> dict | None:
    mail = job.result.get('mail')
    if not isinstance(mail, dict):
        return None
    mine = (owner() or '').lower()
    known = set(calendar_people(job))
    # only the user and people on that day's calendar; anything else Claude wrote is left for the user to add
    to = [a.lower() for a in mail.get('to', []) if a.lower() == mine or a.lower() in known]
    if mine and mine not in to:
        to.append(mine)
    body = (job.dir / '信件內文.txt').read_text(encoding='utf-8').strip() if (job.dir / '信件內文.txt').is_file() else ''
    body = finished_body(body)
    return {'to': to, 'subject': mail.get('subject', ''), 'body': body,
            'from': f'{sender_name()} <{owner()}>' if sender_name() else owner()}


def neighbours(job: Job) -> dict:
    """The same meeting before and after: same title in the same project."""
    title, project = job.result.get('title') or '', project_of(job)
    series = [j for j in all_jobs() if j.status_word() in ('ready', 'sent') and (j.result.get('title') or '') == title
              and project_of(j) == project and (j.archived == job.archived or j.id == job.id)]
    ids = [j.id for j in series]
    at = ids.index(job.id) if job.id in ids else -1
    prev = series[at + 1] if 0 <= at < len(series) - 1 else None
    nxt = series[at - 1] if at > 0 else None
    label = lambda j: f'{day_words(j.started())} {j.result.get("title", "")}' if j and j.started() else ''   # noqa
    return {'prev': prev.id if prev else '', 'prev_title': label(prev), 'next': nxt.id if nxt else '',
            'next_title': label(nxt), 'planned': (job.result.get('next_meeting') or '').strip()}


def page(job: Job, base: dict, md: str, html_text: str, **over) -> dict:
    """Everything the window shows for one meeting."""
    audio = job.dir / (job.meta.get('audio') or '錄音.m4a')
    data = {**base, 'when': job.result.get('when', ''), 'place': job.result.get('place', ''),
            'doc_url': job.result.get('doc_url', ''), 'account': owner() or '',      # the Doc opens as this account
            'html': html_text, 'shown': page_token(job, html_text),
            'news': {'editors': [], 'edits': 0, 'new_comments': 0}, 'warning': '', 'offline': False, 'readonly': False,
            'comments': [], 'todo': todo_items(job, md), 'check': check_items(job), 'learned': [],
            'log': job.log_entries()[:200], 'mail': mail_defaults(job),
            'sent': {'at': short_time(job.result['sent_at']), 'count': len((job.result.get('mail') or {}).get('to', [])),
                     'format': format_words(job.result.get('sent_format'))} if job.result.get('sent_at') else None,
            'transcript': transcript(job), 'voices': voices_view(job), 'voices_off': voices_off(job),
            'voice_names': speakers.known_names(), 'attendees': attendees(md), 'people': meeting_people(job), 'people_known': known_people(), 'calendar': calendar_payload(job),
            'speakers': speakers_shown(job), 'silent': silent_people(job),
            'attach_files': len(linked_files(job, md)), 'attachments': attachments_listed(md), **ai_choice(),
            'audio': str(audio) if audio.is_file() else '',
            'can_undo': (job.dir / '復原.md').is_file() and (job.dir / '復原後.md').is_file(), 'minutes_lang': job.lang,
            **neighbours(job)}
    data.update(over)
    return data


def open_missing(job: Job, base: dict):
    """The minutes file is not where the app left it: show the Doc, change nothing."""
    where = Path(job.result['minutes_md'])
    folder = str(where.parent).replace(str(Path.home()), '~', 1)
    md = ''
    if job.doc_id and not connect():
        try:
            md = doc_sync.doc_to_md(doc_sync.get_doc(job.doc_id))
        except SystemExit:
            md = ''
    warning = (t('missing_file', name=where.name) + (t('missing_showing_doc') if md else '')
               + t('missing_put_back', folder=folder))
    out(page(job, base, md, preview(md, [], []) if md else '', warning=warning, readonly=True, offline=not md,
             todo=[], can_undo=False))


def cmd_open(job: Job):
    base = summary(job)
    if job.status_word() in ('working', 'failed'):
        out({**base, 'log': job.log_entries()[:50]})
        return
    if job.missing:
        return open_missing(job, base)
    learned = cmd_learn(job, quiet=True)               # what the user typed last time, before anything is pulled
    info = {'marks': [], 'editors': [], 'edits': 0, 'warning': ''}
    comments, anchors, new = [], [], 0
    offline = False
    if job.doc_id:
        try:
            why = connect()
            if why:
                raise SystemExit(why)
            offline_md = job.md
            sent = sync_up(job)                       # edits made while offline go first
            if sent['held']:
                raise SystemExit(sent['why'] or sent['held'])
            info = pull(job)
            info['warning'] = ' '.join([w for w in (info['warning'], *after_sync(job, info.get('doc'))) if w])
            info['marks'] = sent['marks'] + info['marks']
            learned += cmd_learn(job, log=False)        # what the user typed into the Doc since (pull logged it)
            notes = []
            if sent['conflicts']:
                spare = keep_spare(job, offline_md)
                notes.append(OFFLINE_CONFLICT + quoted(sent['conflicts']) + t('offline_spare', name=spare.name))
            lost = sent['skipped'] + info.get('skipped', [])
            if lost:
                notes.append(t('not_applied') + quoted(lost))
            info['warning'] = ' '.join([w for w in (sent['warning'], info['warning']) if w] + notes)
            comments, anchors, new = comment_list(job, job.md)
            if job.result.get('sent_at'):
                try:
                    check_bounces(job)
                except (SystemExit, Exception):         # a mail check must never keep the meeting from opening
                    pass
        except SystemExit as err:
            offline = True
            info['warning'] = trouble(err, saving=False)
    job.save_state()
    md = job.md
    if not (job.dir / '學習基準.md').is_file() and md:
        (job.dir / '學習基準.md').write_text(md, encoding='utf-8')
    out(page(job, base, md, preview(md, info['marks'], anchors), learned=learned, comments=comments,
             news={'editors': info['editors'], 'edits': info['edits'], 'new_comments': new},
             warning=info['warning'], offline=offline))


def cmd_refresh(job: Job):
    """The window shows the Google Doc itself. Every little while, and before it shows another meeting, what was
    typed there comes into the minutes: the user's own edits are learned, colleagues' are logged, and the side
    panel gets its 待補充, 待確認 and 操作紀錄 again."""
    learned, warning = [], ''
    if job.doc_id and not job.missing:
        try:
            why = connect()
            if why:
                raise SystemExit(why)
            sent = sync_up(job)
            if sent['held']:
                raise SystemExit(sent['why'] or sent['held'])
            info = pull(job, patient=True)
            placed = after_sync(job, info.get('doc'))
            learned = cmd_learn(job, log=False)
            warning = ' '.join(w for w in (sent['warning'], info['warning'], *placed) if w)
        except SystemExit as err:
            warning = trouble(err, saving=False)
            if warning == OFFLINE_OPEN:              # the Doc itself shows it is offline; the next refresh catches up
                warning = ''
    job.save_state()
    md = '' if job.missing else job.md
    out({'todo': todo_items(job, md) if md else [], 'check': check_items(job), 'learned': learned,
         'attendees': attendees(md), 'people': meeting_people(job), 'speakers': speakers_shown(job), 'calendar': calendar_payload(job),
         'silent': silent_people(job),
         'log': job.log_entries()[:200], 'warning': warning,
         'can_undo': (job.dir / '復原.md').is_file() and (job.dir / '復原後.md').is_file()})


def cmd_locate(job: Job, words: str):
    """How far down the Doc the first paragraph or cell holding `words` starts, from 0 to 1: where the window
    scrolls the Doc when Google Docs' own find does not answer (Google changed its page)."""
    try:
        doc = doc_sync.get_doc(job.doc_id) if job.doc_id else {}
    except SystemExit:
        doc = {}
    content = doc.get('body', {}).get('content', [])
    total = content[-1].get('endIndex', 0) if content else 0
    for el in content:
        paragraphs = [el['paragraph']] if 'paragraph' in el else [
            c['paragraph'] for row in el.get('table', {}).get('tableRows', []) for cell in row.get('tableCells', [])
            for c in cell.get('content', []) if 'paragraph' in c]
        for par in paragraphs:
            elements = par.get('elements', [])
            text = ''.join(e.get('textRun', {}).get('content', '') for e in elements)
            if words and words in text and elements and total:
                return out({'at': round(elements[0].get('startIndex', 0) / total, 4)})
    out({'at': None})


TURN: list = []
CHANGES = {'attach', 'save', 'learn', 'unlearn', 'relearn', 'move_learned', 'ask', 'quick', 'undo', 'reply', 'resolve', 'confirm', 'refresh',
           'people', 'speaker', 'note', 'replace', 'skip', 'correct', 'drop_voice', 'ask_many'}
NEEDS_FILE = {'attach', 'save', 'learn', 'ask', 'quick', 'undo', 'note', 'replace', 'correct', 'ask_many'}


def wait_for_turn(job: Job):
    """One command per meeting at a time; a rewrite by Claude can take minutes, so wait up to 15."""
    import fcntl
    import time
    lock = open(job.dir / '.app.lock', 'w')
    deadline = time.time() + (0 if os.environ.get('VINUTES_NO_WAIT') else 15 * 60)   # an agent asks again later
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock
        except OSError:
            if time.time() > deadline:
                sys.exit(t('busy_meeting'))
            time.sleep(0.3)


def try_turn(job: Job):
    """The meeting's lock if nothing else holds it, else None."""
    import fcntl
    lock = open(job.dir / '.app.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock
    except OSError:
        lock.close()
        return None


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == 'list':
        return cmd_list()
    if cmd == 'version':
        return cmd_version(argv[1] if len(argv) > 1 else '')
    if cmd == 'update':
        return cmd_update()
    if cmd == 'usage':                                # every meeting's, not one job's
        return cmd_usage(argv[1] if len(argv) > 1 else '')
    if cmd == 'rename_project' and len(argv) == 3:  # every meeting of the project, not one job
        return cmd_rename_project(argv[1], argv[2])
    if cmd == 'brief' and len(argv) == 2:           # a project's brief: no meeting, nothing to wait for
        return cmd_brief(argv[1])
    if cmd == 'save_brief' and len(argv) == 3:
        return cmd_save_brief(argv[1], argv[2])
    if len(argv) < 2:
        sys.exit(__doc__)
    job = Job(Path(argv[1]))
    os.environ['VINUTES_MEETING'] = job.id           # what this command uses (AI, Google) is this meeting's
    rest = argv[2:]
    if cmd == 'locate':                              # only reads the Doc: no turn to wait for
        return cmd_locate(job, ' '.join(rest).strip())
    if cmd in ('archive', 'unarchive'):              # only a marker file: no turn to wait for either
        return cmd_archive(job, cmd == 'archive')
    if cmd == 'move' and len(rest) == 1:              # only 分類.json, which nothing else writes
        return cmd_move(job, rest[0])
    if cmd == 'tags' and len(rest) == 1:
        return cmd_tags(job, rest[0])
    if cmd == 'refresh':                             # asked every few seconds: never queue behind a Claude rewrite
        lock = try_turn(job)
        if not lock:
            return out({'busy': True})
        TURN.append(lock)
    else:
        TURN.append(wait_for_turn(job))              # held until the process ends
    job = Job(job.dir)                                # read again: the command before this one may have changed it
    if cmd in CHANGES and job.status_word() not in ('ready', 'sent'):
        sys.exit(t('not_ready'))
    if cmd in NEEDS_FILE and not job.md_path:
        sys.exit(NO_FILE)
    if cmd == 'log':
        return out({'log': job.log_entries()[:200]})
    if cmd == 'open':
        cmd_open(job)
    elif cmd == 'refresh':
        cmd_refresh(job)
    elif cmd == 'save' and rest:
        cmd_save(job, Path(rest[0]), rest[1] if len(rest) > 1 else '')
    elif cmd == 'learn':
        out({'learned': cmd_learn(job)})
    elif cmd in ('unlearn', 'relearn') and rest:
        cmd_unlearn(job, int(rest[0]), cmd == 'unlearn')
    elif cmd == 'move_learned' and len(rest) == 2 and rest[0].isdigit():
        cmd_move_learned(job, int(rest[0]), rest[1])
    elif cmd == 'ask' and rest:
        import references
        pictures, refs = [], []
        while len(rest) >= 3 and rest[-2] in ('--pictures', '--refs'):   # handed with the sentence (the app checks them)
            if rest[-2] == '--pictures':
                pictures = [Path(p) for p in json.loads(rest[-1]) if isinstance(p, str)]
            else:
                refs = references.checked(json.loads(rest[-1]))
            rest = rest[:-2]
        ai_edit(job, ' '.join(rest).strip(), ' '.join(rest).strip(), pictures, refs=refs)
    elif cmd == 'quick' and rest and QUICK_NAMES.get(rest[0], rest[0]) in QUICK['en']:
        key = QUICK_NAMES.get(rest[0], rest[0])
        ai_edit(job, QUICK[job.lang][key], key)
    elif cmd == 'undo':
        cmd_undo(job)
    elif cmd == 'reply' and len(rest) >= 2:
        cmd_reply(job, rest[0], ' '.join(rest[1:]))
    elif cmd == 'resolve' and rest:
        cmd_resolve(job, rest[0])
    elif cmd == 'confirm' and rest:
        cmd_confirm(job, ' '.join(rest))
    elif cmd == 'ask_many' and rest:
        cmd_ask_many(job, rest[0])
    elif cmd == 'drop_voice' and rest:
        cmd_drop_voice(job, rest[0], len(rest) > 1 and rest[1] == 'back')
    elif cmd == 'skip' and rest:
        cmd_skip(job, ' '.join(rest))
    elif cmd == 'correct' and len(rest) == 2:
        cmd_correct(job, rest[0], rest[1])
    elif cmd == 'attach' and len(rest) >= 2:
        cmd_attach(job, rest[0], rest[1])
    elif cmd == 'people' and len(rest) >= 2:
        cmd_people(job, rest[0], rest[1], rest[2] if len(rest) > 2 else '')
    elif cmd == 'note' and rest:
        cmd_note(job, ' '.join(rest))
    elif cmd == 'replace' and len(rest) == 2:
        cmd_replace(job, rest[0], rest[1])
    elif cmd == 'speaker' and len(rest) >= 2:
        cmd_speaker(job, rest[0], rest[1], rest[2] if len(rest) > 2 else '')
    elif cmd == 'delete':
        cmd_delete(job)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    import usage
    import vlog
    usage.begin()                                    # before this run writes a line the fill-in would read
    try:
        vlog.run(main)
    except subprocess.TimeoutExpired:
        sys.exit(t('timeout'))
    except Exception as err:                         # the window shows the last line; a traceback means nothing there
        sys.exit(t('unexpected', err=f'{err.__class__.__name__}: {err}'))
