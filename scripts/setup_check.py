"""環境設定自檢: what this computer still needs before the recorder can record, write the minutes and mail them.
The window shows ten items; the microphone and notifications come from the app itself, the rest from here.

Usage (the app runs these; each prints one last line `JSON {...}`, or exits with a message the window shows):
  setup_check.py status [--quick]           the items 3 to 10; --quick does not ask Google (for the app's start
                                            and a recording's start); the AI's sign-in is asked either way
  setup_check.py download speech|voice      fetch a model in the background; status tells how far it got
                                            (speech fetches the chosen speech model: Whisper, or Qwen3-ASR with
                                            its aligner)
  setup_check.py speech_model whisper|qwen3-asr   the speech model from now on (settings.json "speech_model");
                                            Qwen3-ASR is used for Chinese meetings once downloaded
  setup_check.py login                      Google's consent page in the browser, in the background
  setup_check.py client <file.json>         take the OAuth client the user downloaded from Google Cloud
  setup_check.py ai claude|codex|antigravity   the AI that writes the minutes from now on
  setup_check.py ais                        whether each AI is installed and signed in, for the menu by the
                                            meeting window's prompt box
  setup_check.py aiinstall claude|codex|antigravity   install that AI with its maker's script, in the background
  setup_check.py aitest                     ask the chosen AI for one short answer: is the account ready to write
  setup_check.py fetch speech|voice         (the background download itself)
  setup_check.py fetchai <ai>               (the background install itself)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ai_runner  # noqa: E402
import google_setup as gs  # noqa: E402
from i18n import t  # noqa: E402

import transcribe as tr  # noqa: E402  (the speech models: which one is chosen, where each one's files are)

SPEECH = tr.MODEL                                   # Whisper, the default; on every Mac
SPEECH_BYTES = 1_620_000_000
QWEN_BYTES = 4_000_000_000                          # Qwen3-ASR 1.7B 8-bit (2.2 GB) with its aligner model (1.8 GB)
VOICE = gs.CONFIG / 'models' / 'campplus.onnx'
VOICE_URL = ('https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/'
             '3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx')
VOICE_BYTES = 28_500_000
RUNNING = gs.CONFIG / 'setup-running.json'          # {"speech"|"voice"|"login"|"ai-<ai>": pid} of background jobs
FAILED = gs.CONFIG / 'setup-failed.json'            # {"speech"|"voice"|"ai-<ai>": why} of a job that did not finish
# per AI: {"signed": true once seen signed in, "test": the short answer's result, "email": the account it was for}
TESTED = gs.CONFIG / 'setup-ai.json'
LOGIN_DONE = gs.CONFIG / 'setup-ai-login-done'      # touched by the sign-in window when its command ends (the app)
APIS = {'docs': ['drive.googleapis.com', 'docs.googleapis.com'], 'gmail': ['gmail.googleapis.com'],
        'calendar': ['calendar-json.googleapis.com']}
PROBES = {'drive.googleapis.com': 'https://www.googleapis.com/drive/v3/about?fields=user(emailAddress)',
          'docs.googleapis.com': 'https://docs.googleapis.com/v1/documents/' + 'x' * 44,
          'gmail.googleapis.com': 'https://gmail.googleapis.com/gmail/v1/users/me/profile',
          'calendar-json.googleapis.com': 'https://www.googleapis.com/calendar/v3/users/me/calendarList?maxResults=1'}


def out(data: dict):
    print('JSON ' + json.dumps(data, ensure_ascii=False))


# --- background jobs -----------------------------------------------------------------------------------------

def running() -> dict:
    try:
        jobs = json.loads(RUNNING.read_text())
    except (OSError, ValueError):
        return {}
    alive = {}
    for what, pid in jobs.items():
        try:                                          # still this job, not another program given its number since
            seen = subprocess.run(['ps', '-p', str(int(pid)), '-o', 'command='], capture_output=True, text=True).stdout
        except ValueError:
            continue
        if 'setup_check.py' in seen or 'google_setup.py' in seen:
            alive[what] = int(pid)
    return alive


def failed() -> dict:
    try:
        return json.loads(FAILED.read_text())
    except (OSError, ValueError):
        return {}


def start(what: str, args: list[str]):
    """One background job per kind, outliving this script and the window."""
    jobs = running()
    if what in jobs:
        return
    gs.CONFIG.mkdir(parents=True, exist_ok=True)
    gone = {k: v for k, v in failed().items() if k != what}
    FAILED.write_text(json.dumps(gone))
    log = open(gs.CONFIG / 'setup.log', 'a')
    proc = subprocess.Popen([sys.executable, *args], stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                            start_new_session=True)
    jobs[what] = proc.pid
    RUNNING.write_text(json.dumps(jobs))


# --- each item -----------------------------------------------------------------------------------------------

def hub() -> Path:
    return tr.hub_dir(SPEECH)


def speech_repos(model: str) -> list[str]:
    """the model files a speech model needs: Whisper one, Qwen3-ASR its model and its aligner"""
    return [tr.QWEN, tr.QWEN_ALIGNER] if model == 'qwen3-asr' else [SPEECH]


def downloaded(repo: Path) -> int:
    """bytes of a model's files on disk so far (the blobs, whole or still being written)"""
    folder = repo / 'blobs'
    return sum(f.stat().st_size for f in folder.glob('*') if f.is_file()) if folder.is_dir() else 0


def speech() -> dict:
    """The chosen speech model (whisper or qwen3-asr) and whether its files are here: done, loading with a
    percentage while the download runs, or todo. 'have' says which of the two models is on this Mac, for the
    checklist's model page; a Mac without Qwen3-ASR's files transcribes with Whisper."""
    model = tr.speech_model()
    repos = speech_repos(model)
    total = QWEN_BYTES if model == 'qwen3-asr' else SPEECH_BYTES
    package = tr.qwen_package()                       # False on a Mac installed before the package was added
    have = {'whisper': tr.hub_has(SPEECH), 'qwen3-asr': package and tr.qwen_ready()}
    common = {'model': model, 'whisper': have['whisper'], 'have': have, 'package': package}
    if 'speech' in running():
        got = sum(downloaded(tr.hub_dir(r)) for r in repos)
        return {'state': 'loading', 'pct': min(99, int(got * 100 / total)), **common}
    ready = have[model]
    return {'state': 'done' if ready else 'todo', **common, **({} if ready else {'failed': 'speech' in failed()})}


def voice() -> dict:
    if 'voice' in running():
        part = VOICE.with_suffix('.onnx.part')
        got = part.stat().st_size if part.is_file() else 0
        return {'state': 'loading', 'pct': min(99, int(got * 100 / VOICE_BYTES))}
    if VOICE.is_file() and VOICE.stat().st_size > 1_000_000:
        return {'state': 'done'}
    return {'state': 'todo', 'failed': 'voice' in failed()}


def ai(quick: bool) -> dict:
    """Item 5 and its four steps: the AI chosen, whether it is installed (or being installed), signed in, and
    whether it gave the short answer. The sign-in is asked also at the app's start (--quick): an AI that is
    installed but signed out cannot write the minutes either, nor one whose short answer said its plan does not
    include it ('plan', for that same account)."""
    key = ai_runner.chosen()
    info = tested().get(key, {})
    out = {'ai': key, 'installed': ai_runner.installed(), 'tested': info.get('test') == 'done',
           'was_signed': bool(info.get('signed')), 'login_at': login_at()}
    exe = ai_runner.find(key)
    if exe:
        signed, email = ai_runner.account(key, exe)
        state = {True: 'done', False: 'login', None: 'unknown'}[signed]
        if signed and not info.get('signed'):
            remember(key, signed=True)
            out['was_signed'] = True
        if state == 'done' and info.get('test') == 'plan' and info.get('email', '') == email:
            state = 'plan'
        out.update(state=state, email=email)
    elif f'ai-{key}' in running():
        out['state'] = 'installing'
    else:
        out.update(state='install', failed=f'ai-{key}' in failed())
    return out


def tested() -> dict:
    """What setup-ai.json keeps for each AI (an older version kept only when its test passed)."""
    try:
        kept = json.loads(TESTED.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(kept, dict):
        return {}
    return {k: v if isinstance(v, dict) else {'test': 'done', 'signed': True} for k, v in kept.items()}


def remember(key: str, **facts):
    kept = tested()
    kept[key] = {**kept.get(key, {}), **facts}
    gs.CONFIG.mkdir(parents=True, exist_ok=True)
    tmp = TESTED.with_suffix('.tmp')
    tmp.write_text(json.dumps(kept))
    tmp.replace(TESTED)


def login_at() -> int:
    """When the sign-in window's command last ended, in milliseconds (the window compares it with its clock)."""
    try:
        return int(LOGIN_DONE.stat().st_mtime * 1000)
    except OSError:
        return 0


def test_result(code: int, text: str) -> str:
    """'done' (the AI answered), 'quota' (its usage limit), 'login' (signed out), 'plan' (the account's plan does
    not include it) or 'error'. The words are the ones the minutes' own failures are told by (auto_minutes)."""
    import auto_minutes
    low = (text or '').lower()
    if code == 0 and re.search(r'\bok\b', low):                # it answered, whatever else it printed
        return 'done'
    said = {words for key, words in auto_minutes.FRIENDLY if key.lower() in low}
    if 'err_rate_limit' in said or auto_minutes.limit_until(text or ''):
        return 'quota'
    if 'err_not_logged_in' in said or 'please run /login' in low:
        return 'login'
    if re.search(r'subscription|upgrade your plan|not (?:included|available) (?:in|on) your plan', low):
        return 'plan'
    return 'done' if code == 0 and low.strip() else 'error'


def ai_test() -> dict:
    """Step 4: the chosen AI, run the way it writes the minutes, in an empty folder, asked for one word."""
    import auto_minutes
    key = ai_runner.chosen()
    exe = ai_runner.find(key)
    email = ai_runner.account(key, exe)[1] if exe else ''
    with tempfile.TemporaryDirectory(prefix='vinutes-test-') as folder:
        try:
            done = ai_runner.run('Reply with the single word OK.', Path(folder), write=False, timeout=120,
                                 env=auto_minutes.env(), key=key, task='test')
            result = test_result(done.returncode, (done.stdout or '') + '\n' + (done.stderr or ''))
        except (subprocess.TimeoutExpired, SystemExit):
            result = 'error'
    remember(key, test=result, email=email, at=datetime.now().isoformat(timespec='seconds'))
    return {'test': result, 'ai': key}


def client() -> dict:
    info = gs.client_info()
    desktop = bool(info) and 'installed' in json.loads(gs.CLIENT.read_text())
    return {'state': 'done' if desktop else 'todo'}


def project_id() -> str:
    try:
        return (gs.client_info() or {}).get('project_id', '')
    except (OSError, ValueError):
        return ''


def probe(token: str, api: str) -> str:
    """'ok', 'off' (the API is not turned on in the Cloud project) or 'scope' (the login lacks the permission)."""
    req = urllib.request.Request(PROBES[api], headers={'Authorization': 'Bearer ' + token})
    try:
        urllib.request.urlopen(req, timeout=15)
        return 'ok'
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors='replace')
        if 'SERVICE_DISABLED' in body or 'has not been used' in body:
            return 'off'
        if 'insufficient' in body.lower() or 'SCOPE_INSUFFICIENT' in body:
            return 'scope'
        return 'ok' if api == 'docs.googleapis.com' and err.code == 404 else 'error'   # a made-up Doc: 404 when on
    except (urllib.error.URLError, OSError):
        return 'offline'


def google(quick: bool) -> dict:
    """Items 7 to 10: the login, then Drive and Docs, Gmail and Calendar."""
    items = {name: {'state': 'locked'} for name in ('login', 'docs', 'gmail', 'calendar')}
    if client()['state'] != 'done':
        return items
    if 'login' in running():
        items['login'] = {'state': 'loading'}
        return items
    if not gs.TOKEN.exists():
        items['login'] = {'state': 'todo'}
        return items
    if quick:
        items['login'] = {'state': 'done'}
        return items
    try:
        token = gs.access_token()
    except SystemExit as err:
        items['login'] = {'state': 'offline' if str(err).startswith('OFFLINE') else 'todo'}
        return items
    items['login'] = {'state': 'done', 'email': gs.saved_token().get('email', '')}
    project = project_id()
    for name, apis in APIS.items():
        found = {api: probe(token, api) for api in apis}
        off = [api for api, said in found.items() if said == 'off']
        if off:
            url = f'https://console.cloud.google.com/apis/library/{off[0]}'
            items[name] = {'state': 'off', 'url': url + (f'?project={urllib.parse.quote(project)}' if project else '')}
        elif 'scope' in found.values():
            items[name] = {'state': 'scope'}
        elif 'offline' in found.values():
            items[name] = {'state': 'offline'}
        else:
            items[name] = {'state': 'done' if all(v == 'ok' for v in found.values()) else 'error'}
    return items


def status(quick: bool) -> dict:
    return {'speech': speech(), 'voice': voice(), 'ai': ai(quick), 'client': client(), **google(quick),
            'project': project_id()}


# --- what the buttons do -------------------------------------------------------------------------------------

def fetch(what: str):
    """The background download itself (start() runs it)."""
    try:
        if what == 'speech':
            from huggingface_hub import snapshot_download
            for repo in speech_repos(tr.speech_model()):
                snapshot_download(repo)
        else:
            VOICE.parent.mkdir(parents=True, exist_ok=True)
            part = VOICE.with_suffix('.onnx.part')
            with urllib.request.urlopen(VOICE_URL, timeout=60) as src, part.open('wb') as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            part.replace(VOICE)
    except Exception as err:                          # the page says the last download did not finish
        FAILED.write_text(json.dumps({**failed(), what: f'{err.__class__.__name__}: {err}'[:300]}))
        raise
    finally:
        jobs = running()
        jobs.pop(what, None)
        RUNNING.write_text(json.dumps(jobs))


def take_client(path: Path):
    """The OAuth client JSON the user downloaded, as $MINUTES_HOME/oauth-client.json (only they can read it)."""
    try:
        blob = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        sys.exit(t('client_not_google'))
    if not isinstance(blob, dict) or 'client_secret' not in (blob.get('installed') or blob.get('web') or {}):
        sys.exit(t('client_not_google'))
    if 'installed' not in blob:
        sys.exit(t('client_web'))
    gs.CONFIG.mkdir(parents=True, exist_ok=True)
    gs.CONFIG.chmod(0o700)
    fd = os.open(gs.CLIENT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(json.dumps(blob))
    gs.CLIENT.chmod(0o600)


def install_ai(key: str):
    """The background install itself (aiinstall starts it). An AI installed here is connected to Vinutes' meetings
    the way install.sh connects the ones already on the Mac."""
    try:
        ai_runner.install(key)
    except BaseException as err:                      # step 2 says the install did not finish
        FAILED.write_text(json.dumps({**failed(), f'ai-{key}': f'{err}'[:300]}))
        raise
    finally:
        jobs = running()
        jobs.pop(f'ai-{key}', None)
        RUNNING.write_text(json.dumps(jobs))
    subprocess.run([sys.executable, str(Path(__file__).with_name('connect_agents.py'))], capture_output=True,
                   stdin=subprocess.DEVNULL, timeout=120, check=False)


def main_progress() -> dict:
    """Only what runs in the background, asked every few seconds while something does."""
    jobs = running()
    return {'speech': speech() if 'speech' in jobs else {'state': 'ended'},
            'voice': voice() if 'voice' in jobs else {'state': 'ended'},
            'login': {'state': 'loading' if 'login' in jobs else 'ended'},
            'ai': {'state': 'installing' if f'ai-{ai_runner.chosen()}' in jobs else 'ended'}}


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ''
    if cmd == 'status' and '--progress' in args:
        return out(main_progress())
    if cmd == 'status':
        return out(status('--quick' in args))
    if cmd == 'download' and len(args) > 1 and args[1] in ('speech', 'voice'):
        start(args[1], [__file__, 'fetch', args[1]])
        return out(status(True))
    if cmd == 'fetch' and len(args) > 1:
        return fetch(args[1])
    if cmd == 'login':
        start('login', [str(Path(__file__).with_name('google_setup.py')), 'login'])
        return out({'started': True})
    if cmd == 'client' and len(args) > 1:
        take_client(Path(args[1]))
        return out(status(True))
    if cmd == 'speech_model' and len(args) > 1 and args[1] in tr.SPEECH_MODELS:
        from i18n import save                       # the choice, kept in settings.json; the download is a second step
        save('speech_model', args[1])
        return out({'speech': speech()})
    if cmd == 'ais':
        return out({'ais': ai_runner.states()})
    if cmd == 'ai' and len(args) > 1:
        ai_runner.choose(args[1])
        return out({'ai': ai(False)})
    if cmd == 'aiinstall' and len(args) > 1 and args[1] in ai_runner.AIS:
        start(f'ai-{args[1]}', [__file__, 'fetchai', args[1]])
        return out({'ai': ai(False)})
    if cmd == 'fetchai' and len(args) > 1 and args[1] in ai_runner.AIS:
        return install_ai(args[1])
    if cmd == 'aitest':
        return out(ai_test())
    sys.exit(__doc__)


if __name__ == '__main__':
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    import vlog
    vlog.run(main)
