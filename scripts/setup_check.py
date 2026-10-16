"""環境設定自檢: what this computer still needs before the recorder can record, write the minutes and mail them.
The window shows ten items; the microphone and notifications come from the app itself, the rest from here.

Usage (the app runs these; each prints one last line `JSON {...}`, or exits with a message the window shows):
  setup_check.py status [--quick]           the items 3 to 10; --quick only looks at this computer (no Google, no
                                            AI sign-in check), for the app's start
  setup_check.py download speech|voice      fetch a model in the background; status tells how far it got
  setup_check.py login                      Google's consent page in the browser, in the background
  setup_check.py client <file.json>         take the OAuth client the user downloaded from Google Cloud
  setup_check.py ai claude|codex|antigravity   the AI that writes the minutes from now on
  setup_check.py ais                        whether each AI is installed and signed in, for the menu by the
                                            meeting window's prompt box
  setup_check.py fetch speech|voice         (the background download itself)
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ai_runner  # noqa: E402
import google_setup as gs  # noqa: E402
from i18n import t  # noqa: E402

SPEECH = os.environ.get('MINUTES_WHISPER_MODEL') or 'mlx-community/whisper-large-v3-turbo'
SPEECH_BYTES = 1_620_000_000
VOICE = gs.CONFIG / 'models' / 'campplus.onnx'
VOICE_URL = ('https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/'
             '3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx')
VOICE_BYTES = 28_500_000
RUNNING = gs.CONFIG / 'setup-running.json'          # {"speech"|"voice"|"login": pid} of the background jobs
FAILED = gs.CONFIG / 'setup-failed.json'            # {"speech"|"voice": why} of a download that did not finish
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
    base = os.environ.get('HF_HUB_CACHE') or os.path.join(os.environ.get('HF_HOME') or '~/.cache/huggingface', 'hub')
    return Path(base).expanduser() / ('models--' + SPEECH.replace('/', '--'))


def speech() -> dict:
    jobs = running()
    if 'speech' in jobs:
        got = sum(f.stat().st_size for f in (hub() / 'blobs').glob('*') if f.is_file()) if (hub() / 'blobs').is_dir() else 0
        return {'state': 'loading', 'pct': min(99, int(got * 100 / SPEECH_BYTES))}
    weights = [w for w in hub().glob('snapshots/*/*.safetensors') if w.exists()]
    return {'state': 'done'} if weights else {'state': 'todo', 'failed': 'speech' in failed()}


def voice() -> dict:
    if 'voice' in running():
        part = VOICE.with_suffix('.onnx.part')
        got = part.stat().st_size if part.is_file() else 0
        return {'state': 'loading', 'pct': min(99, int(got * 100 / VOICE_BYTES))}
    if VOICE.is_file() and VOICE.stat().st_size > 1_000_000:
        return {'state': 'done'}
    return {'state': 'todo', 'failed': 'voice' in failed()}


def ai(quick: bool) -> dict:
    key = ai_runner.chosen()
    exe = ai_runner.find(key)
    if not exe:
        state = 'install'
    elif quick:
        state = 'done'
    else:
        state = {True: 'done', False: 'login', None: 'unknown'}[ai_runner.signed_in(key, exe)]
    return {'state': state, 'ai': key, 'install_url': ai_runner.INSTALL[key]}


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
            snapshot_download(SPEECH)
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


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ''
    if cmd == 'status' and '--progress' in args:  # only what runs in the background, every few seconds
        jobs = running()
        return out({'speech': speech() if 'speech' in jobs else {'state': 'ended'},
                    'voice': voice() if 'voice' in jobs else {'state': 'ended'},
                    'login': {'state': 'loading' if 'login' in jobs else 'ended'}})
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
    if cmd == 'ais':
        return out({'ais': ai_runner.states()})
    if cmd == 'ai' and len(args) > 1:
        ai_runner.choose(args[1])
        return out({'ai': ai(False)})
    sys.exit(__doc__)


if __name__ == '__main__':
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    main()
