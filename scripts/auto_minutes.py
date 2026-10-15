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
  - this script transcribes (transcribe.py), reads that day's calendar (workspace.py events) into 行事曆.txt and
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

Settings (settings.json): auto_folder, where automatic minutes are written (default ~/會議紀錄);
drive_folder, the Drive folder for their Docs (default 會議紀錄); claude_path, if claude is not on the PATH.
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

SCRIPTS = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS.parent
CLAUDE_TIMEOUT = 45 * 60
from ai_runner import EXTRA_PATH  # noqa: E402  (where claude, codex and agy are installed)
BODY = '信件內文.txt'
WORK = '整理'                   # the agent's folder inside the job
DRAFT = '紀錄.md'               # the minutes as the agent writes them there; the program copies them out
LINK = '{文件網址}'
ATTACH = {'word': 'docx', 'pdf': 'pdf'}

# known failures, in words the user can act on
FRIENDLY = [
    ('GOOGLE LOGIN EXPIRED', 'Google 登入已經失效，請到「環境設定自檢」的第 7 項重新登入。'),
    ('NO GOOGLE LOGIN', '這台電腦還沒有完成 Google 設定，請照「環境設定自檢」的第 6、7 項設定。'),
    ('already mailed these minutes', '這份紀錄已經寄給其中幾位收件人了。'),
    ('give plain addresses only', '收件人只能寫信箱，例如 name@example.com，不能加名字。'),
    ('NOT INSTALLED', '轉逐字稿的套件沒有裝好，請重新執行 recorder/install.sh。'),
    ('CANNOT READ AUDIO', '錄音檔讀不出來，可能是錄音過程被中斷。'),
    ('changed since the last upload', '有人已經在 Google 文件上改過，請直接到 Google 文件修改。'),
    ('open comments', 'Google 文件上有還沒處理的留言，請直接到 Google 文件修改。'),
    ('GOOGLE DOCS API DISABLED', 'Google Cloud 專案還沒開啟 Google Docs API，請到「環境設定自檢」的第 8 項按「開啟」。'),
    ('rate limit', '{ai} 的用量已經用完，等額度恢復後再按「重新整理」。'),
    ('not supported when using Codex with a ChatGPT account',
     'Codex 的版本太舊，沒辦法用 ChatGPT 帳號整理。請先更新 Codex，再按「重新整理」。'),
    ('not logged in', '{ai} 還沒登入，請到「環境設定自檢」的第 5 項登入。'),
]


def friendly(text: str, default: str) -> str:
    import ai_runner
    for key, words in FRIENDLY:
        if key.lower() in text.lower():
            return words.replace('{ai}', ai_runner.name())
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
        raise Failed('找不到錄音檔。')
    if not (job / '操作紀錄.jsonl').exists() and meta.get('started'):
        activity(job, None, '開始錄音', at=meta['started'])
        if meta.get('ended'):
            import minutes_app
            minutes = round((datetime.fromisoformat(meta['ended']) - datetime.fromisoformat(meta['started'])).total_seconds() / 60)
            activity(job, None, f'結束錄音，長度 {minutes_app.length_words(minutes)}', at=meta['ended'])
    status(job, 'transcribing', '正在把錄音轉成逐字稿')
    began = time.time()
    try:
        done = script('transcribe.py', audio, job / '逐字稿.txt', timeout=4 * 3600)
    except subprocess.TimeoutExpired:
        raise Failed('轉逐字稿超過 4 小時還沒完成，已經停止。')
    log(job, (done.stdout + done.stderr).strip()[-1000:])
    if done.returncode or not (job / '逐字稿.txt').exists():
        raise Failed(friendly(done.stdout + done.stderr, '錄音轉逐字稿失敗。'))
    if not (job / '逐字稿.txt').read_text(encoding='utf-8').strip():
        raise Failed('錄音裡沒有聽到說話的聲音。請確認錄音時麥克風有收到聲音。')
    log(job, f'transcribed in {time.time() - began:.0f}s')
    activity(job, '助手', '把錄音轉成逐字稿')
    tell_voices(job)
    if audio.suffix == '.caf':                       # the transcript is safe, keep a small copy of the audio
        small = audio.with_suffix('.m4a')
        conv = subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', '48000', str(audio), str(small)],
                              capture_output=True, text=True)
        if conv.returncode == 0 and small.exists() and small.stat().st_size > 0:
            audio.unlink()
            meta['audio'] = small.name
            write_json(job / 'job.json', meta)


def tell_voices(job: Path):
    """Each transcript line's speaker by voice (speakers.py). Minutes are still written without it, so a
    missing package or model only costs the names."""
    import speakers
    if not speakers.available():
        log(job, 'speakers: not installed')
        return
    status(job, 'transcribing', '正在分辨每一句的講者')
    began = time.time()
    try:
        done = script('speakers.py', job, timeout=1800)
    except subprocess.TimeoutExpired:
        log(job, 'speakers: timed out')
        return
    log(job, (done.stdout + done.stderr).strip()[-500:] + f' ({time.time() - began:.0f}s)')


def gather(job: Path, meta: dict, folder: Path) -> Path:
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
    (work / '逐字稿.txt').write_text(speakers.labelled_transcript(job), encoding='utf-8')
    for src in (SKILL_DIR / 'SKILL.md', SKILL_DIR / 'references' / 'glossary.md',
                SKILL_DIR / 'references' / 'example-minutes.md'):
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
            recent.append({'date': other.name[:8], 'title': r['title'], 'project': r.get('project') or ''})
        if len(recent) >= 40:
            break
    (ref / '最近的會議.json').write_text(json.dumps(recent, ensure_ascii=False, indent=1), encoding='utf-8')
    day = (meta.get('started') or '')[:10]
    if day:
        try:
            done = script('workspace.py', 'events', day, timeout=120)
            found = done.stdout if done.returncode == 0 else '（讀不到行事曆：' + friendly(done.stderr, '原因不明') + '）\n'
        except subprocess.TimeoutExpired:
            found = '（讀不到行事曆：連線逾時）\n'
        (job / '行事曆.txt').write_text(found or '（這一天沒有行程）\n', encoding='utf-8')
        shutil.copy(job / '行事曆.txt', work / '行事曆.txt')
    return work


def stamp(meta: dict) -> str:
    """2026-10-14T14:05:00+08:00 -> 20261014_1405, the start of every file name this recording writes."""
    return (meta.get('started') or '')[:16].replace('-', '').replace('T', '_').replace(':', '')


def prompt(job: Path, meta: dict, folder: Path) -> str:
    started, ended = meta.get('started') or '', meta.get('ended') or ''
    try:
        minutes = round((datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds() / 60)
        length = f'，長度約 {minutes} 分鐘'
    except (TypeError, ValueError):
        length = ''
    return (
        '自動整理模式：這是錄音程式「Vinutes」在使用者結束錄音後自動啟動的工作，沒有人會回答問題。\n'
        f'先讀 {job}/參考/SKILL.md，照第 0.5 節「錄音程式自動整理」做，其他規則照 SKILL.md 與 參考/使用者規則.md。\n'
        f'- 逐字稿：{job}/逐字稿.txt（每行開頭是從錄音開始算的時間，有講者的話接著是講者，見 SKILL.md 第 2 節「辨識講者」）\n'
        f'- 錄音時間：{started} 到 {ended}{length}\n'
        f'- 當天行事曆：{job}/行事曆.txt\n'
        f'- 詞彙表與使用者設定：{job}/參考/\n'
        f'- 之前的會議名稱與專案：{job}/參考/最近的會議.json（同一個會議沿用一樣的名稱與專案）\n'
        f'- 之前的會議紀錄（補背景用）：{job}/參考/舊紀錄/\n'
        f'- 紀錄寫成 {job}/{DRAFT}，程式會照 result.json 的 title 存進紀錄資料夾。\n'
        f'- 信件內文寫成 {job}/{BODY}，最後寫 {job}/result.json。\n'
        '這個模式不能執行指令也不能連網；發 Google 文件、預覽和寄信都由程式在你結束之後處理。'
    )


def write_minutes(job: Path, work: Path, meta: dict, folder: Path):
    import ai_runner
    ai = ai_runner.chosen()
    # the agent works in its own folder and can write nothing else; the program copies the minutes out
    log(job, f'{ai} in {work}')
    with (job / 'log.txt').open('a', encoding='utf-8') as out:
        try:
            done = ai_runner.run(prompt(work, meta, folder), work, write=True, timeout=CLAUDE_TIMEOUT, env=env(),
                                 stdout=out, stderr=subprocess.STDOUT)
        except subprocess.TimeoutExpired:
            raise Failed(f'整理超過 {CLAUDE_TIMEOUT // 60} 分鐘還沒完成，已經停止。逐字稿留在錄音資料夾裡。')
        except SystemExit as err:
            raise Failed(str(err))
    log(job, f'{ai} exited {done.returncode}')
    if done.returncode:
        raise Failed(friendly((job / 'log.txt').read_text(encoding='utf-8')[-3000:],
                              f'{ai_runner.name(ai)} 整理時出錯。'))


def strings(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []


def line(value, limit: int) -> str:
    """One line of plain text, at most `limit` characters: what a field Claude wrote may become."""
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def minutes_path(folder: Path, meta: dict, title: str) -> Path:
    """Where the minutes go. An earlier, unfinished run of this recording keeps its file, and with it its Doc."""
    earlier = sorted(folder.glob(f'{stamp(meta)}_*_會議紀錄.md'))
    if earlier:
        return earlier[0]
    topic = re.sub(r'[\\/:*?"<>|\s]+', '', title)[:40] or '會議'
    return folder / f'{stamp(meta)}_{topic}_會議紀錄.md'


def check_result(work: Path, meta: dict, folder: Path) -> dict:
    """The agent's result.json, trusted only as far as it can be checked."""
    result = read_json(work / 'result.json')
    if not result:
        raise Failed('整理沒有完成。逐字稿留在錄音資料夾裡，可以按「重新整理」再試一次。')
    if result.get('status') != 'ok':
        raise Failed(str(result.get('error') or '整理沒有完成。'))
    draft = work / DRAFT
    if not draft.is_file() or not re.search(r'(?m)^#{1,3} ', draft.read_text(encoding='utf-8')):
        raise Failed('整理完沒有找到會議紀錄檔。')
    import ai_runner
    if ai_runner.leaks(draft.read_text(encoding='utf-8'), (work / BODY).read_text(encoding='utf-8')
                       if (work / BODY).is_file() else '', json.dumps(result, ensure_ascii=False)):
        raise Failed(f'{ai_runner.name()} 寫出來的紀錄裡有看起來像登入資料的文字，為了安全，這份紀錄沒有發成 Google 文件。'
                     '逐字稿留在錄音資料夾裡，可以按「重新整理」再試一次。')
    title = line(result.get('title'), 80) or '會議紀錄'
    md = minutes_path(folder, meta, title)
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
            'next_meeting': line(result.get('next_meeting'), 40),
            'todo': items(result.get('todo'), ('label', 'line'))[:10],
            'check': items(result.get('check'), ('text', 'heard', 'meant'))[:10],
            'notes': strings(result.get('notes'))[:5]}


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
    folder = setting('drive_folder', 'MINUTES_DRIVE_FOLDER') or '會議紀錄'
    done = script('md_to_gdoc.py', md, folder, '--create-folder', timeout=300)
    log(job, 'publish: ' + (done.stdout + done.stderr).strip()[-600:])
    url = read_json(md.with_name(md.name + '.gdoc.json')).get('url')
    if done.returncode or not url:
        raise Failed(friendly(done.stdout + done.stderr, '會議紀錄寫好了，發成 Google 文件時失敗。'))
    result['doc_url'] = url
    remember_revision(job, md, doc_id(result))
    body = job / BODY
    if result.get('mail'):                           # the agent cannot know the address; it leaves a placeholder
        text = body.read_text(encoding='utf-8')
        text = text.replace(LINK, url) if LINK in text else text.rstrip() + f'\n\n{url}\n'
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
        status(job, 'writing', '正在整理成會議紀錄')
        folder = Path(setting('auto_folder', 'MINUTES_AUTO_FOLDER') or '~/會議紀錄').expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        work = gather(job, meta, folder)
        (job / 'result.json').unlink(missing_ok=True)
        write_minutes(job, work, meta, folder)
        result = check_result(work, meta, folder)
        if result['mail']:
            shutil.copy(work / BODY, job / BODY)
        md = Path(result['minutes_md'])
        shutil.copy(work / DRAFT, md)
        import speakers
        md.with_name(md.stem.removesuffix('_會議紀錄') + '_逐字稿.txt').write_text(speakers.labelled_transcript(job),
                                                                              encoding='utf-8')
        publish(job, result)
        write_json(job / 'result.json', result)
        import ai_runner
        activity(job, ai_runner.name(), '整理完會議記錄，發成 Google 文件')
        status(job, 'done', result['title'])
        log(job, 'done')
    except Failed as err:
        fail(job, str(err))
    except Exception as err:                         # anything unexpected still ends as a visible failure
        log(job, f'UNEXPECTED {err.__class__.__name__}: {err}')
        fail(job, '整理時發生沒有預期的錯誤。錄音和逐字稿都還在錄音資料夾裡。')


def fail(job: Path, message: str):
    log(job, 'FAILED ' + message)
    write_json(job / 'result.json', {'status': 'error', 'error': message})
    status(job, 'failed', message)
    sys.exit(1)


# --- what the app asks for afterwards -------------------------------------------------------

def attachment(job: Path, result: dict, fmt: str, make: bool) -> Path | None:
    if fmt == 'gdoc':
        return None
    name = re.sub(r'[\\/:*?"<>|]+', '_', result.get('title') or '會議紀錄')
    path = job / '附件' / f'{name}.{ATTACH[fmt]}'
    if not make:
        if not path.is_file():
            sys.exit('附件不見了，請重新按寄出。')
        return path
    path.parent.mkdir(exist_ok=True)
    if fmt == 'word':
        latest(job)
        if script('md_to_docx.py', result['minutes_md'], path).returncode:
            sys.exit('沒辦法產生 Word 檔。')
    else:
        try:
            pdf = drive().call(f'https://www.googleapis.com/drive/v3/files/{doc_id(result)}/export?mimeType=application/pdf', raw=True)
        except (Exception, SystemExit) as err:
            log(job, f'pdf export failed: {err}')
            sys.exit(friendly(str(err), '沒辦法產生 PDF 檔。'))
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
            sys.exit('沒有連上 Google 文件，沒辦法用最新的內容產生 Word 檔，信沒有寄出。')
        try:
            minutes_app.pull(entry)
        except SystemExit:
            sys.exit('沒有連上 Google 文件，沒辦法用最新的內容產生 Word 檔，信沒有寄出。')
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
                sys.exit('這封信正在寄出，請稍等。')
            if time.time() - began > 300:
                sys.exit('前一個附件準備超過 5 分鐘還沒好，信沒有寄出。請稍後再試一次。')
            time.sleep(0.5)
    who.write_text(what, encoding='utf-8')
    return lock


def send(job: Path, to: str | None, subject: str | None, fmt: str, dry: bool, confirm: str | None):
    """--dry: the exact mail as the app will show it, with its confirm code. Otherwise send it if the code matches."""
    lock = mail_turn(job, 'preview' if dry else 'send')  # noqa: F841 (held until this process ends)
    result = read_json(job / 'result.json')
    if result.get('sent_at'):
        sys.exit(f'這封信已經在 {result["sent_at"][:16].replace("T", " ")} 寄出了。')
    if not result.get('mail') or not (job / BODY).is_file() or not doc_id(result):
        sys.exit('這份會議紀錄沒有準備好的信件。')
    people = [t.strip().lower() for t in re.split(r'[,，、;\s]+', to or '') if t.strip()] or result['mail']['to']
    subject = (subject or '').strip() or result['mail']['subject']
    attach = attachment(job, result, fmt, make=dry)
    base = ['send', ','.join(people), subject, job / BODY, '--minutes', result['minutes_md'],
            '--share', 'comment' if fmt == 'gdoc' else 'none'] + (['--attach', attach] if attach else [])
    shown = script('workspace.py', *base)
    found = re.search(r'確認碼: (\w+)', shown.stdout)
    if shown.returncode or not found:
        log(job, 'preview: ' + (shown.stdout + shown.stderr).strip()[-600:])
        sys.exit(friendly(shown.stdout + shown.stderr, '信件預覽失敗，信沒有寄出。'))
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
        sys.exit('信件在預覽之後改過了，請重新按寄出。')
    done = script('workspace.py', *base, '--send', '--confirm', code, no_send=False)
    log(job, 'send: ' + (done.stdout + done.stderr).strip()[-1000:])
    if done.returncode:
        sys.exit(friendly(done.stdout + done.stderr, '信沒有寄出。'))
    result['mail'].update(to=people, subject=subject)
    result['sent_at'] = datetime.now().isoformat(timespec='seconds')
    gmail_id = re.search(r'^SENT (\w+)', done.stdout, re.M)
    if gmail_id:
        result['sent_id'] = gmail_id.group(1)          # the window looks for bounces in this mail's thread
    result['sent_format'] = fmt
    write_json(job / 'result.json', result)
    import minutes_app
    entry = minutes_app.Job(job)
    names = '、'.join(minutes_app.name_of(entry, p) for p in people)
    entry.log(minutes_app.me(), f'已寄給 {names}，附件是 {minutes_app.format_words(fmt)}', 'sent')
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
        sys.exit('連線逾時，請稍後再試一次。')
    except Exception as err:                         # the app shows the last line; a traceback means nothing there
        sys.exit(f'發生沒有預期的錯誤（{err.__class__.__name__}: {err}）。')
