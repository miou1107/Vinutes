"""Turn a finished recording into minutes with nobody watching, then do what the recorder app asks.

Usage:
  auto_minutes.py <job folder>                         the whole job (the app starts it when a recording stops)
  auto_minutes.py --send <job folder> --to <a,b> --subject <s> --format gdoc|word|pdf --dry
                                                       make the attachment and print the mail as one line
                                                       MAIL {"from", "to", "subject", "body", "attachment", "code"}
  auto_minutes.py --send <job folder> --to <a,b> --subject <s> --format gdoc|word|pdf --confirm <code>
                                                       send exactly that mail (the user said yes to the preview)

A job folder is $MINUTES_HOME/recordings/<YYYYMMDD-HHMMSS>/ with the recording and job.json
({"audio": ..., "started": <ISO>, "ended": <ISO or null>}). Progress goes to status.json
({"step": "transcribing|writing|done|failed", "message", "pid"}), the outcome to result.json.

Who does what, so that nothing goes out without the user:
  - this script transcribes (transcribe.py), finds the meeting on the calendar (workspace.py meeting) for 行事曆.txt and
    copies the transcript, the calendar, SKILL.md, the glossaries, notes.md, the user's settings and copies of
    earlier minutes into the job's 整理/ folder;
  - the Claude Code CLI then runs restricted (claude -p --restricted --strict-mcp-config) in 整理/: no shell, no
    web, no MCP servers, no user settings or hooks, file tools only in that folder. It writes 整理/紀錄.md,
    整理/信件內文.txt and 整理/result.json (SKILL.md section 0.5), which this script checks and copies out to the
    minutes folder; earlier minutes and the job's own files (job.json, the calendar, the log) stay out of its reach;
  - this script publishes the Google Doc (md_to_gdoc.py --create-folder) and notes the Doc's revision, so the
    window (minutes_app.py) can tell later what colleagues changed in it.
The job runs with MINUTES_NO_SEND set, under which workspace.py and notify.py refuse to send. Only --send with
the confirm code of a preview the user approved sends; every format first gives the recipients comment access
to the Google Doc.

Settings (settings.json): auto_folder, where automatic minutes are written (the first run names it ~/會議紀錄 or ~/Meeting Minutes and keeps it);
drive_folder, the Drive folder for their Docs (the first publish names it 會議紀錄 or Meeting Minutes and keeps it); claude_path, if claude is not on the PATH.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_setup import CONFIG, owner, sender_name, setting  # noqa: E402
from i18n import minutes_lang, save, t, ui_lang  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS.parent
CLAUDE_TIMEOUT = 45 * 60
from ai_runner import EXTRA_PATH  # noqa: E402  (where claude, codex and agy are installed)
BODY = '信件內文.txt'
WORK = '整理'                   # the agent's folder inside the job
DRAFT = '紀錄.md'               # the minutes as the agent writes them there; the program copies them out
LINKS = ('{文件網址}', '{doc_url}')    # where the Doc's address goes in the mail (Chinese / English guide)
# the guide the agent writes from, by the minutes' language: (guide, example) in the Vinutes folder
GUIDES = {'zh-TW': ('SKILL.md', 'references/example-minutes.md'),
          'en': ('references/minutes-guide-en.md', 'references/example-minutes-en.md')}
SUFFIX = {'zh-TW': ('_會議紀錄', '_逐字稿'), 'en': ('_Minutes', '_Transcript')}   # minutes and transcript file names
# languages a meeting may be held in besides Chinese and English, for telling the agent: Whisper's code -> names
SPOKEN = {'ja': ('日文', 'Japanese'), 'ko': ('韓文', 'Korean'), 'es': ('西班牙文', 'Spanish'), 'fr': ('法文', 'French'),
          'de': ('德文', 'German'), 'it': ('義大利文', 'Italian'), 'pt': ('葡萄牙文', 'Portuguese'),
          'ru': ('俄文', 'Russian'), 'vi': ('越南文', 'Vietnamese'), 'id': ('印尼文', 'Indonesian'),
          'ms': ('馬來文', 'Malay'), 'tl': ('菲律賓文', 'Filipino'), 'th': ('泰文', 'Thai')}
ATTACH = {'word': 'docx', 'pdf': 'pdf'}

# known failures, in words the user can act on
FRIENDLY = [
    ('GOOGLE LOGIN EXPIRED', 'err_login_expired'),
    ('NO GOOGLE LOGIN', 'err_no_google'),
    ('already mailed these minutes', 'err_already_mailed'),
    ('give plain addresses only', 'err_plain_addresses'),
    ('NOT INSTALLED', 'err_not_installed'),
    ('CANNOT READ AUDIO', 'err_cannot_read_audio'),
    ('changed since the last upload', 'err_doc_changed'),
    ('open comments', 'err_open_comments'),
    ('GOOGLE DOCS API DISABLED', 'err_docs_api'),
    ('rate limit', 'err_rate_limit'),
    ('not supported when using Codex with a ChatGPT account', 'err_codex_old'),
    ('not logged in', 'err_not_logged_in'),
]


def friendly(text: str, default: str) -> str:
    import ai_runner
    for key, words in FRIENDLY:
        if key.lower() in text.lower():
            return t(words, ai=ai_runner.name())
    return default


def write_json(path: Path, data: dict):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def status(job: Path, step: str, message: str = ''):
    write_json(job / 'status.json', {'step': step, 'message': message, 'at': datetime.now().isoformat(),
                                     'pid': os.getpid()})


def log(job: Path, text: str):
    with (job / 'log.txt').open('a', encoding='utf-8') as f:
        f.write(f'[{datetime.now():%H:%M:%S}] {text}\n')


class Failed(Exception):
    pass


def activity(job: Path, who: str | None, text: str, kind: str = '', at: str | None = None):
    """One line in the job's 操作紀錄.jsonl, the log the window shows. who=None means the user."""
    import minutes_app
    entry = minutes_app.Job(job)
    entry.log(who or minutes_app.me(), text, kind, datetime.fromisoformat(at) if at else None)


def env(no_send: bool = True) -> dict:
    out = dict(os.environ)
    # python3 inside any command should be this interpreter, which has every package installed
    out['PATH'] = os.pathsep.join([str(Path(sys.executable).parent), out.get('PATH', ''), *EXTRA_PATH])
    if no_send:
        out['MINUTES_NO_SEND'] = '1'
    else:
        out.pop('MINUTES_NO_SEND', None)
    return out


def script(name: str, *args, no_send: bool = True, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)], capture_output=True, text=True,
                          env=env(no_send), timeout=timeout)


def doc_id(result: dict) -> str:
    found = re.search(r'/document/d/([A-Za-z0-9_-]+)', result.get('doc_url') or '')
    return found.group(1) if found else ''


def drive():
    import md_to_gdoc
    md_to_gdoc.AUTH['Authorization'] = 'Bearer ' + md_to_gdoc.access_token()
    return md_to_gdoc


# --- the whole job ---------------------------------------------------------------------------

def transcribe(job: Path, meta: dict):
    audio = job / (meta.get('audio') or '錄音.caf')
    if not audio.exists():
        raise Failed(t('no_audio'))
    if not (job / '操作紀錄.jsonl').exists() and meta.get('started'):
        activity(job, None, t('log_started'), at=meta['started'])
        if meta.get('ended'):
            import minutes_app
            minutes = round((datetime.fromisoformat(meta['ended']) - datetime.fromisoformat(meta['started'])).total_seconds() / 60)
            activity(job, None, t('log_ended', length=minutes_app.length_words(minutes)), at=meta['ended'])
    status(job, 'transcribing', t('status_transcribing'))
    began = time.time()
    try:
        done = script('transcribe.py', audio, job / '逐字稿.txt', timeout=4 * 3600)
    except subprocess.TimeoutExpired:
        raise Failed(t('transcribe_timeout'))
    log(job, (done.stdout + done.stderr).strip()[-1000:])
    if done.returncode or not (job / '逐字稿.txt').exists():
        raise Failed(friendly(done.stdout + done.stderr, t('transcribe_failed')))
    if not (job / '逐字稿.txt').read_text(encoding='utf-8').strip():
        raise Failed(t('no_speech'))
    log(job, f'transcribed in {time.time() - began:.0f}s')
    meta['language'] = spoken_language(job)
    write_json(job / 'job.json', meta)
    activity(job, t('assistant'), t('log_transcribed'))
    tell_voices(job)
    if audio.suffix == '.caf':                       # the transcript is safe, keep a small copy of the audio
        small = audio.with_suffix('.m4a')
        conv = subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', '48000', str(audio), str(small)],
                              capture_output=True, text=True)
        if conv.returncode == 0 and small.exists() and small.stat().st_size > 0:
            audio.unlink()
            meta['audio'] = small.name
            write_json(job / 'job.json', meta)


def spoken_language(job: Path) -> str:
    """The language the meeting was held in, as transcribe.py decided it (Whisper's code); Chinese before it did."""
    return str(read_json(job / '逐字稿.json').get('language') or 'zh')


def tell_voices(job: Path):
    """Each transcript line's speaker by voice (speakers.py). Minutes are still written without it, so a
    missing package or model only costs the names."""
    import speakers
    if not speakers.available():
        log(job, 'speakers: not installed')
        return
    status(job, 'transcribing', t('status_speakers'))
    began = time.time()
    try:
        done = script('speakers.py', job, timeout=1800)
    except subprocess.TimeoutExpired:
        log(job, 'speakers: timed out')
        return
    log(job, (done.stdout + done.stderr).strip()[-500:] + f' ({time.time() - began:.0f}s)')


def gather(job: Path, meta: dict, folder: Path, lang: str = 'zh-TW') -> Path:
    """Everything the restricted agent may read, copied into its own folder, so it never needs a shell or a token
    and cannot change the job's files or any earlier minutes."""
    work = job / WORK
    shutil.rmtree(work, ignore_errors=True)
    ref = work / '參考'
    ref.mkdir(parents=True)
    old = ref / '舊紀錄'                               # earlier minutes, for background: copies, so they stay as they are
    old.mkdir()
    earlier = [f for f in folder.glob('*.md') if f.is_file() and f.stat().st_size < 500_000]
    for f in sorted(earlier, key=lambda f: f.stat().st_mtime, reverse=True)[:30]:
        shutil.copy(f, old / f.name)
    import speakers                                  # the transcript with who said each line, when the voices are known
    (work / '逐字稿.txt').write_text(speakers.labelled_transcript(job, unnamed(lang)), encoding='utf-8')
    guide, example = GUIDES[lang]
    for src in (SKILL_DIR / guide, SKILL_DIR / 'references' / 'glossary.md', SKILL_DIR / example):
        if src.exists():
            shutil.copy(src, ref / src.name)
    for name, target in (('notes.md', '使用者規則.md'), ('glossary.md', '公司詞彙表.md')):
        if (CONFIG / name).exists():
            shutil.copy(CONFIG / name, ref / target)
    mine = {'owner': owner(), 'sender_name': sender_name(), 'our_company': setting('our_company', 'MINUTES_OUR_COMPANY'),
            'style': setting('style', 'MINUTES_STYLE')}
    write_json(ref / '使用者設定.json', {k: v for k, v in mine.items() if v})
    recent = []
    for other in sorted(job.parent.iterdir(), reverse=True):
        r = read_json(other / 'result.json')
        if other != job and r.get('status') == 'ok' and r.get('title'):
            project, tags = sorted_as(other, r)
            recent.append({'date': other.name[:8], 'title': r['title'], 'project': project, 'tags': tags})
        if len(recent) >= 40:
            break
    (ref / '最近的會議.json').write_text(json.dumps(recent, ensure_ascii=False, indent=1), encoding='utf-8')
    if meta.get('started'):
        (job / '行事曆.txt').write_text(read_calendar(job, meta), encoding='utf-8')
        shutil.copy(job / '行事曆.txt', work / '行事曆.txt')
    return work


def read_calendar(job: Path, meta: dict) -> str:
    """行事曆.txt for the agent: the meeting the recording was, as workspace.py meeting picked it (only one the
    user is on), the next one of its series, and how earlier meetings of the series were named and filed.
    The pick is kept in 行事曆.json, so a later recording of the same series finds this one."""
    started = meta.get('started') or ''
    try:
        done = script('workspace.py', 'meeting', started, meta.get('ended') or started, timeout=120)
    except subprocess.TimeoutExpired:
        return '（讀不到行事曆：連線逾時）\n'
    if done.returncode:
        return '（讀不到行事曆：' + friendly(done.stderr, '原因不明') + '）\n'
    lines, match = [], {}
    for text in done.stdout.splitlines():
        if text.startswith('MATCH '):
            try:
                match = json.loads(text[6:])
            except ValueError:
                match = {}
        else:
            lines.append(text)
    write_json(job / '行事曆.json', match if isinstance(match, dict) else {})
    found = '\n'.join(lines).strip() + '\n'
    match = match if isinstance(match, dict) else {}
    key = ('recurring', match['recurring']) if match.get('recurring') else ('series', match.get('series'))
    before = []
    # only meetings recorded before this one, newest first: a recording written up again doesn't learn from later ones
    for other in sorted((p for p in job.parent.iterdir() if p.name < job.name), reverse=True) if key[1] else []:
        r = read_json(other / 'result.json')
        if r.get('status') == 'ok' and read_json(other / '行事曆.json').get(key[0]) == key[1]:
            project, _ = sorted_as(other, r)
            before.append(f'   {other.name[:4]}-{other.name[4:6]}-{other.name[6:8]} {r.get("title", "")}　專案：{project or "（沒有）"}')
        if len(before) >= 3:
            break
    if before:
        found += '\n== 同一系列之前整理過的會議（會議名稱與專案照抄）\n' + '\n'.join(before) + '\n'
    return found


def unnamed(lang: str) -> str:
    """A voice without a name in the transcript the agent reads: 講者 A, or Speaker A for English minutes."""
    return t('speaker', lang)


def stamp(meta: dict) -> str:
    """2026-10-14T14:05:00+08:00 -> 20261014_1405, the start of every file name this recording writes."""
    return (meta.get('started') or '')[:16].replace('-', '').replace('T', '_').replace(':', '')


def prompt(job: Path, meta: dict, folder: Path, lang: str = 'zh-TW', spoken: str = 'zh') -> str:
    if lang == 'en':
        return prompt_en(job, meta, spoken)
    started, ended = meta.get('started') or '', meta.get('ended') or ''
    try:
        minutes = round((datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds() / 60)
        length = f'，長度約 {minutes} 分鐘'
    except (TypeError, ValueError):
        length = ''
    return (
        '自動整理模式：這是錄音程式「Vinutes」在使用者結束錄音後自動啟動的工作，沒有人會回答問題。\n'
        f'先讀 {job}/參考/SKILL.md，照第 0.5 節「錄音程式自動整理」做，其他規則照 SKILL.md 與 參考/使用者規則.md。\n'
        + (f'這場會議講的是{SPOKEN.get(spoken, (spoken, spoken))[0]}，逐字稿保留原文；會議紀錄、信件內文、result.json 裡的文字'
           '一律用繁體中文（台灣用語）寫，人名照逐字稿的寫法，金額保留原本的幣別。\n' if spoken not in ('zh', 'yue') else '') +
        f'- 逐字稿：{job}/逐字稿.txt（每行開頭是從錄音開始算的時間，有講者的話接著是講者，見 SKILL.md 第 2 節「辨識講者」）\n'
        f'- 錄音時間：{started} 到 {ended}{length}\n'
        f'- 行事曆（程式已經挑好這場會議）：{job}/行事曆.txt\n'
        f'- 詞彙表與使用者設定：{job}/參考/\n'
        f'- 之前的會議名稱、專案與標籤：{job}/參考/最近的會議.json（同一個會議沿用一樣的名稱與專案）\n'
        f'- 之前的會議紀錄（補背景用）：{job}/參考/舊紀錄/\n'
        f'- 紀錄寫成 {job}/{DRAFT}，程式會照 result.json 的 title 存進紀錄資料夾。\n'
        f'- 信件內文寫成 {job}/{BODY}，最後寫 {job}/result.json。\n'
        '這個模式不能執行指令也不能連網；發 Google 文件、預覽和寄信都由程式在你結束之後處理。'
    )


def prompt_en(job: Path, meta: dict, spoken: str) -> str:
    """The same job for English minutes, from the English guide (references/minutes-guide-en.md)."""
    started, ended = meta.get('started') or '', meta.get('ended') or ''
    try:
        minutes = round((datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds() / 60)
        length = f', about {minutes} minutes long'
    except (TypeError, ValueError):
        length = ''
    held = '' if spoken == 'en' else (
        f'The meeting was held in {SPOKEN.get(spoken, (spoken, spoken))[1]}; the transcript stays in that language. Write the '
        'minutes, the mail and the text in result.json in English; keep names as the transcript spells them and '
        'amounts in their own currency.\n')
    return (
        'Automatic mode: the recording app Vinutes started this job after the user stopped a recording; nobody will '
        'answer questions.\n'
        f'First read {job}/參考/minutes-guide-en.md and follow its section "Automatic mode"; for everything else follow '
        f'that guide and 參考/使用者規則.md (the user\'s own rules, if present).\n' + held +
        f'- Transcript: {job}/逐字稿.txt (each line starts with the time from the start of the recording, then the '
        'speaker when known; see the guide\'s section "Reading the transcript")\n'
        f'- Recording: {started} to {ended}{length}\n'
        f'- The calendar (the program has picked the meeting): {job}/行事曆.txt\n'
        f'- Glossaries and the user\'s settings: {job}/參考/\n'
        f'- Earlier meeting names, projects and tags: {job}/參考/最近的會議.json (the same meeting keeps the same name and project)\n'
        f'- Earlier minutes, for background: {job}/參考/舊紀錄/\n'
        f'- Write the minutes to {job}/{DRAFT}; the program files them under the title in result.json.\n'
        f'- Write the mail text to {job}/{BODY}, and last {job}/result.json.\n'
        'In this mode you cannot run commands or use the web; the Google Doc, the preview and the mail are done by '
        'the program after you finish.'
    )


def write_minutes(job: Path, work: Path, meta: dict, folder: Path, lang: str = 'zh-TW', spoken: str = 'zh'):
    import ai_runner
    ai = ai_runner.chosen()
    # the agent works in its own folder and can write nothing else; the program copies the minutes out
    log(job, f'{ai} in {work}')
    with (job / 'log.txt').open('a', encoding='utf-8') as out:
        try:
            done = ai_runner.run(prompt(work, meta, folder, lang, spoken), work, write=True, timeout=CLAUDE_TIMEOUT, env=env(),
                                 stdout=out, stderr=subprocess.STDOUT)
        except subprocess.TimeoutExpired:
            raise Failed(t('write_timeout', n=CLAUDE_TIMEOUT // 60))
        except SystemExit as err:
            raise Failed(str(err))
    log(job, f'{ai} exited {done.returncode}')
    if done.returncode:
        raise Failed(friendly((job / 'log.txt').read_text(encoding='utf-8')[-3000:],
                              t('write_error', ai=ai_runner.name(ai))))


def strings(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def line(value, limit: int) -> str:
    """One line of plain text, at most `limit` characters: what a field Claude wrote may become."""
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def minutes_path(folder: Path, meta: dict, title: str, lang: str = 'zh-TW') -> Path:
    """Where the minutes go. An earlier, unfinished run of this recording keeps its file, and with it its Doc."""
    earlier = sorted(f for end, _ in SUFFIX.values() for f in folder.glob(f'{stamp(meta)}_*{end}.md'))
    if earlier:
        return earlier[0]
    topic = re.sub(r'[\\/:*?"<>|\s]+', '', title)[:40] or ('Meeting' if lang == 'en' else '會議')
    return folder / f'{stamp(meta)}_{topic}{SUFFIX[lang][0]}.md'


def check_result(work: Path, meta: dict, folder: Path, lang: str = 'zh-TW') -> dict:
    """The agent's result.json, trusted only as far as it can be checked."""
    result = read_json(work / 'result.json')
    if not result:
        raise Failed(t('not_finished_retry'))
    if result.get('status') != 'ok':
        raise Failed(str(result.get('error') or t('not_finished')))
    draft = work / DRAFT
    if not draft.is_file() or not re.search(r'(?m)^#{1,3} ', draft.read_text(encoding='utf-8')):
        raise Failed(t('no_minutes_file'))
    import ai_runner
    if ai_runner.leaks(draft.read_text(encoding='utf-8'), (work / BODY).read_text(encoding='utf-8')
                       if (work / BODY).is_file() else '', json.dumps(result, ensure_ascii=False)):
        raise Failed(t('leaks', ai=ai_runner.name()))
    title = line(result.get('title'), 80) or t('untitled_minutes', lang)
    md = minutes_path(folder, meta, title, lang)
    mail = result.get('mail') if isinstance(result.get('mail'), dict) else None
    if mail:
        mail = {'to': [t.lower() for t in strings(mail.get('to'))], 'subject': str(mail.get('subject') or '').strip()}
        mail = {'to': [t for t in mail['to'] if re.fullmatch(r'[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+', t)],
                'subject': line(mail['subject'], 120)}
        if not mail['to'] or not mail['subject'] or not (work / BODY).is_file():
            mail = None
    return {'status': 'ok', 'title': title, 'minutes_md': str(md),
            'when': line(result.get('when'), 40), 'place': line(result.get('place'), 40), 'mail': mail,
            'project': line(result.get('project'), 30),
            'tag_suggestions': tag_list(result.get('tags'))[:3],
            'next_meeting': line(result.get('next_meeting'), 40),
            'todo': items(result.get('todo'), ('label', 'line'))[:10],
            'check': items(result.get('check'), ('text', 'heard', 'meant'))[:10],
            'notes': strings(result.get('notes'))[:5]}


def tag_list(value) -> list:
    """Short tags, each once (minutes_app.clean_tags keeps the user's the same way)."""
    found = []
    for v in value if isinstance(value, list) else []:
        tag = line(v, 20) if isinstance(v, str) else ''
        if tag and tag not in found:
            found.append(tag)
    return found


def sorted_as(job: Path, result: dict) -> tuple:
    """A meeting's project and tags as the window shows them: what the user set in 分類.json (minutes_app.py),
    else the project Claude named."""
    mine = read_json(job / '分類.json')
    project = mine['project'] if isinstance(mine.get('project'), str) else result.get('project')
    return line(project, 30), tag_list(mine.get('tags'))


def items(value, keys: tuple) -> list:
    """todo / check entries: plain strings, or objects with these keys (everything kept as short text)."""
    found = []
    for v in value if isinstance(value, list) else []:
        if isinstance(v, dict) and line(v.get(keys[0]), 60):
            found.append({k: line(v.get(k), 60).replace('|', '／') for k in keys})
        elif isinstance(v, str) and line(v, 60):
            found.append(line(v, 60).replace('|', '／'))
    return found


def publish(job: Path, result: dict):
    md = Path(result['minutes_md'])
    folder = setting('drive_folder', 'MINUTES_DRIVE_FOLDER')
    if not folder:
        # named in the app's language the first time, then kept, so switching languages later never splits the Docs
        folder = '會議紀錄' if ui_lang() == 'zh-TW' else 'Meeting Minutes'
        save('drive_folder', folder)
    done = script('md_to_gdoc.py', md, folder, '--create-folder', timeout=300)
    log(job, 'publish: ' + (done.stdout + done.stderr).strip()[-600:])
    url = read_json(md.with_name(md.name + '.gdoc.json')).get('url')
    if done.returncode or not url:
        raise Failed(friendly(done.stdout + done.stderr, t('publish_failed')))
    result['doc_url'] = url
    remember_revision(job, md, doc_id(result))
    body = job / BODY
    if result.get('mail'):                           # the agent cannot know the address; it leaves a placeholder
        text = body.read_text(encoding='utf-8')
        link = next((k for k in LINKS if k in text), None)
        text = text.replace(link, url) if link else text.rstrip() + f'\n\n{url}\n'
        body.write_text(text, encoding='utf-8')


def remember_revision(job: Path, md: Path, doc: str):
    """The Doc as published is the starting point for telling, later, what colleagues changed."""
    try:
        import doc_sync
        published = doc_sync.get_doc(doc)
        revision = doc_sync.paint_blanks(doc, published) or published.get('revisionId', '')   # [__] in red
    except (SystemExit, Exception) as err:          # the window then syncs without marks the first time
        log(job, f'revision not recorded: {err}')
        return
    at = datetime.now().astimezone()
    write_json(job / '同步.json', {'revision': revision, 'synced_at': at.isoformat(timespec='seconds'),
                                  'own_until': (at + timedelta(seconds=5)).isoformat(timespec='seconds')})
    shutil.copy(md, job / '學習基準.md')
    shutil.copy(md, job / '同步基準.md')


def run(job: Path):
    meta = read_json(job / 'job.json')
    subprocess.Popen(['caffeinate', '-i', '-w', str(os.getpid())])     # a closed lid still sleeps
    try:
        transcribe(job, meta)
        status(job, 'writing', t('status_writing'))
        named = setting('auto_folder', 'MINUTES_AUTO_FOLDER')
        if not named:                                # like the Drive folder: named once, in the app's language
            named = '~/會議紀錄' if ui_lang() == 'zh-TW' else '~/Meeting Minutes'
            save('auto_folder', named)
        folder = Path(named).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        spoken = meta.get('language') or spoken_language(job)
        lang = minutes_lang(spoken)
        work = gather(job, meta, folder, lang)
        (job / 'result.json').unlink(missing_ok=True)
        write_minutes(job, work, meta, folder, lang, spoken)
        result = check_result(work, meta, folder, lang)
        result.update(minutes_lang=lang, spoken=spoken)
        if result['mail']:
            shutil.copy(work / BODY, job / BODY)
        md = Path(result['minutes_md'])
        shutil.copy(work / DRAFT, md)
        import speakers
        base = next((md.stem.removesuffix(end) for end, _ in SUFFIX.values() if md.stem.endswith(end)), md.stem)
        md.with_name(base + SUFFIX[lang][1] + '.txt').write_text(speakers.labelled_transcript(job, unnamed(lang)),
                                                                 encoding='utf-8')
        publish(job, result)
        write_json(job / 'result.json', result)
        import ai_runner
        activity(job, ai_runner.name(), t('log_published'))
        status(job, 'done', result['title'])
        log(job, 'done')
    except Failed as err:
        fail(job, str(err))
    except Exception as err:                         # anything unexpected still ends as a visible failure
        log(job, f'UNEXPECTED {err.__class__.__name__}: {err}')
        fail(job, t('unexpected_run'))


def fail(job: Path, message: str):
    log(job, 'FAILED ' + message)
    write_json(job / 'result.json', {'status': 'error', 'error': message})
    status(job, 'failed', message)
    sys.exit(1)


# --- what the app asks for afterwards -------------------------------------------------------

def attachment(job: Path, result: dict, fmt: str, make: bool) -> Path | None:
    if fmt == 'gdoc':
        return None
    name = re.sub(r'[\\/:*?"<>|]+', '_', result.get('title') or t('untitled_minutes', result.get('minutes_lang')))
    path = job / '附件' / f'{name}.{ATTACH[fmt]}'
    if not make:
        if not path.is_file():
            sys.exit(t('attachment_gone'))
        return path
    path.parent.mkdir(exist_ok=True)
    if fmt == 'word':
        latest(job)
        if script('md_to_docx.py', result['minutes_md'], path).returncode:
            sys.exit(t('no_word'))
    else:
        try:
            pdf = drive().call(f'https://www.googleapis.com/drive/v3/files/{doc_id(result)}/export?mimeType=application/pdf', raw=True)
        except (Exception, SystemExit) as err:
            log(job, f'pdf export failed: {err}')
            sys.exit(friendly(str(err), t('no_pdf')))
        path.write_bytes(pdf)
    return path


def latest(job: Path):
    """A Word file is made from the local minutes: first bring in what colleagues changed in the Doc since."""
    import minutes_app
    entry = minutes_app.Job(job)
    lock = minutes_app.wait_for_turn(entry)          # not while the window is saving the same minutes
    try:
        entry = minutes_app.Job(job)
        why = minutes_app.connect()
        sent = minutes_app.sync_up(entry) if not why else None
        if why or sent['held']:
            sys.exit(t('word_offline'))
        try:
            minutes_app.pull(entry)
        except SystemExit:
            sys.exit(t('word_offline'))
        entry.save_state()
    finally:
        lock.close()


def mail_turn(job: Path, what: str):
    """One mail step at a time for a meeting. A preview (making the attachment) waits for the one before it, and
    寄出 waits for an attachment still being made; only a second 寄出 while the mail is going out is refused."""
    lock = open(job / '.sending', 'a')
    who = job / '.sending.who'
    began = time.time()
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if who.is_file() and who.read_text(encoding='utf-8').strip() == 'send':
                sys.exit(t('mail_sending'))
            if time.time() - began > 300:
                sys.exit(t('mail_attach_slow'))
            time.sleep(0.5)
    who.write_text(what, encoding='utf-8')
    return lock


def send(job: Path, to: str | None, subject: str | None, fmt: str, dry: bool, confirm: str | None):
    """--dry: the exact mail as the app will show it, with its confirm code. Otherwise send it if the code matches."""
    lock = mail_turn(job, 'preview' if dry else 'send')  # noqa: F841 (held until this process ends)
    result = read_json(job / 'result.json')
    if result.get('sent_at'):
        import minutes_app
        at = minutes_app.short_time(result['sent_at']) if ui_lang() == 'en' else result['sent_at'][:16].replace('T', ' ')
        sys.exit(t('mail_already_sent', at=at))
    if not result.get('mail') or not (job / BODY).is_file() or not doc_id(result):
        sys.exit(t('mail_none'))
    people = [t.strip().lower() for t in re.split(r'[,，、;\s]+', to or '') if t.strip()] or result['mail']['to']
    subject = (subject or '').strip() or result['mail']['subject']
    attach = attachment(job, result, fmt, make=dry)
    base = ['send', ','.join(people), subject, job / BODY, '--minutes', result['minutes_md'],
            '--share', 'comment' if fmt == 'gdoc' else 'none'] + (['--attach', attach] if attach else [])
    shown = script('workspace.py', *base)
    found = re.search(r'確認碼: (\w+)', shown.stdout)
    if shown.returncode or not found:
        log(job, 'preview: ' + (shown.stdout + shown.stderr).strip()[-600:])
        sys.exit(friendly(shown.stdout + shown.stderr, t('mail_preview_failed')))
    code = found.group(1)
    if dry:
        me = owner()
        print('MAIL ' + json.dumps({
            'from': f'{sender_name()} <{me}>' if sender_name() else me, 'to': people,
            'subject': subject, 'body': (job / BODY).read_text(encoding='utf-8').strip(),
            'attachment': attach.name if attach else '', 'attachment_kb': attach.stat().st_size // 1024 if attach else 0,
            'commenters': [p for p in people if p != me], 'code': code,
            'attachment_files': int((re.search(r'^ATTACHMENTS (\d+)', shown.stdout, re.M) or [0, 0])[1])},
            ensure_ascii=False))
        return
    if confirm != code:
        sys.exit(t('mail_changed'))
    done = script('workspace.py', *base, '--send', '--confirm', code, no_send=False)
    log(job, 'send: ' + (done.stdout + done.stderr).strip()[-1000:])
    if done.returncode:
        sys.exit(friendly(done.stdout + done.stderr, t('mail_not_sent')))
    result['mail'].update(to=people, subject=subject)
    result['sent_at'] = datetime.now().isoformat(timespec='seconds')
    gmail_id = re.search(r'^SENT (\w+)', done.stdout, re.M)
    if gmail_id:
        result['sent_id'] = gmail_id.group(1)          # the window looks for bounces in this mail's thread
    result['sent_format'] = fmt
    write_json(job / 'result.json', result)
    import minutes_app
    entry = minutes_app.Job(job)
    names = t('list_sep').join(minutes_app.name_of(entry, p) for p in people)
    entry.log(minutes_app.me(), t('log_sent', names=names, format=minutes_app.format_words(fmt)), 'sent')
    print('SENT ' + ', '.join(people))


def main():
    argv = sys.argv[1:]
    takes = ('--to', '--subject', '--format', '--confirm')

    def value(flag):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None
    rest = [a for i, a in enumerate(argv) if not a.startswith('--') and not (i and argv[i - 1] in takes)]
    if not rest:
        sys.exit(__doc__)
    job = Path(rest[0]).expanduser().resolve()
    if not (job / 'job.json').is_file():
        sys.exit(f'not a recording job folder: {job}')
    if '--send' in argv:
        fmt = value('--format') or 'gdoc'
        if fmt not in ('gdoc', 'word', 'pdf'):
            sys.exit('--format takes gdoc, word or pdf')
        if '--dry' not in argv and not value('--confirm'):
            sys.exit('--send needs --dry first, then --confirm <code> once the user said yes')
        if 'MINUTES_NO_SEND' in os.environ and '--dry' not in argv:
            sys.exit('STOP: this is an automatic run (MINUTES_NO_SEND); only the user can send from the app')
        send(job, value('--to'), value('--subject'), fmt, '--dry' in argv, value('--confirm'))
    else:
        run(job)


if __name__ == '__main__':
    try:
        main()
    except subprocess.TimeoutExpired:
        sys.exit(t('timeout'))
    except Exception as err:                         # the app shows the last line; a traceback means nothing there
        sys.exit(t('unexpected', err=f'{err.__class__.__name__}: {err}'))
