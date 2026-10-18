"""Which AI writes and changes the minutes, and how it runs so that it can touch only the folder it is given.

  claude       Claude Code: claude -p --restricted, file tools only, no commands, no web
  codex        Codex CLI: codex exec --sandbox workspace-write; it writes only inside the folder, and its commands
               have no network
  antigravity  Antigravity CLI (agy): agy -p inside macOS's sandbox-exec. On its own, agy -p writes files anywhere
               and runs commands, whatever --mode or --sandbox say (tried 2026-10-15); the sandbox lets it read and
               write only the folder and its own settings, and start no other program

settings.json "ai" picks one (default claude); item 5 of the window's 環境設定自檢 sets it, installs it with its
maker's own script, signs it in and asks it for one short answer.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from google_setup import CONFIG, read_settings, setting
from i18n import t

AIS = {'claude': 'Claude Code', 'codex': 'Codex', 'antigravity': 'Antigravity'}
SHORT = {'claude': 'Claude', 'codex': 'Codex', 'antigravity': 'Antigravity'}
COMMAND = {'claude': 'claude', 'codex': 'codex', 'antigravity': 'agy'}
# each maker's own install script (read 2026-10-19): all three put the command in ~/.local/bin and ask nothing,
# Codex once told so; Codex's would otherwise offer to start Codex at the end
INSTALLERS = {'claude': ('https://claude.ai/install.sh', 'bash', {}),
              'codex': ('https://chatgpt.com/codex/install.sh', 'sh', {'CODEX_NON_INTERACTIVE': '1'}),
              'antigravity': ('https://antigravity.google/cli/install.sh', 'bash', {})}
LOGIN = {'claude': 'claude auth login', 'codex': 'codex login', 'antigravity': 'agy'}
EXTRA_PATH = ['/opt/homebrew/bin', '/usr/local/bin', str(Path.home() / '.local/bin'),
              str(Path.home() / '.claude/local'), str(Path.home() / '.npm-global/bin')]


# what a sign-in looks like: Google tokens and client secrets, private keys. The minutes are published and mailed
# without anyone reading them first, so text like this in what the AI wrote stops them (a transcript or a calendar
# entry could have told the AI to copy a file it can read).
SECRETS = re.compile(r'"?(?:refresh_token|client_secret|access_token)"?\s*[:=]\s*"?[\w./-]{12}|GOCSPX-[\w-]{8}'
                     r'|ya29\.[\w-]{20}|1//0[\w-]{20}|-----BEGIN [A-Z ]*PRIVATE KEY')


def leaks(*texts: str) -> bool:
    return any(SECRETS.search(t or '') for t in texts)


def new_leaks(before: str, after: str) -> bool:
    """`after` holds a sign-in that `before` did not."""
    return bool(set(SECRETS.findall(after or '')) - set(SECRETS.findall(before or '')))


def chosen() -> str:
    """settings.json "ai"; when not set, Claude Code, or the one of the three this computer has."""
    key = str(read_settings()[0].get('ai') or '').strip().lower()
    if key in AIS:
        return key
    return next((k for k in AIS if find(k)), 'claude')


def name(key: str | None = None) -> str:
    """How the window and the messages call it: Claude, Codex, Antigravity."""
    return SHORT[key or chosen()]


def choose(key: str):
    """The AI the minutes are written with from now on, kept in settings.json."""
    if key not in AIS:
        raise SystemExit(t('ai_unknown'))
    mine, problem = read_settings()
    if problem:
        raise SystemExit(t('ai_bad_settings'))
    mine['ai'] = key
    CONFIG.mkdir(parents=True, exist_ok=True)
    path = CONFIG / 'settings.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(mine, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def installed() -> list[str]:
    """The ones this computer has; the window greys out the others in the menu by the prompt box."""
    return [k for k in AIS if find(k)]


def states() -> dict:
    """Each AI: 'done' (installed and signed in), 'install', 'login', or 'unknown' (it did not say in time). The
    three are asked at once: agy takes about 3 seconds, the others under one (measured 2026-10-15)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(key: str) -> str:
        exe = find(key)
        if not exe:
            return 'install'
        return {True: 'done', False: 'login', None: 'unknown'}[signed_in(key, exe)]
    with ThreadPoolExecutor(len(AIS)) as pool:
        return dict(zip(AIS, pool.map(one, AIS)))


def find(key: str | None = None) -> str | None:
    key = key or chosen()
    if key == 'claude':
        configured = setting('claude_path', 'MINUTES_CLAUDE')
        if configured and os.access(Path(configured).expanduser(), os.X_OK):
            return str(Path(configured).expanduser())
    return shutil.which(COMMAND[key], path=os.pathsep.join([os.environ.get('PATH', ''), *EXTRA_PATH]))


def signed_in(key: str, exe: str) -> bool | None:
    """Whether the AI is signed in on this computer; None when it did not say within 30 seconds."""
    return account(key, exe)[0]


def account(key: str, exe: str) -> tuple[bool | None, str]:
    """Whether the AI is signed in (None: it did not say within 30 seconds), and with which address when it says
    (Claude Code does; the other two do not)."""
    asks = {'claude': [exe, 'auth', 'status'], 'codex': [exe, 'login', 'status'], 'antigravity': [exe, 'models']}
    try:
        done = subprocess.run(asks[key], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, ''
    except OSError:
        return False, ''
    if key == 'claude':
        try:
            said = json.loads(done.stdout)
        except ValueError:
            return False, ''
        return bool(said.get('loggedIn')), str(said.get('email') or '') if said.get('loggedIn') else ''
    if key == 'codex':
        return done.returncode == 0 and 'logged in' in (done.stdout + done.stderr).lower(), ''
    return done.returncode == 0 and bool(done.stdout.strip()), ''


def installer(key: str) -> tuple[str, str, dict]:
    """The maker's install script, the shell that runs it, and what it needs so that it asks nothing."""
    return INSTALLERS[key]


def download(url: str, dest: Path):
    """curl rather than Python's own: it uses the Mac's certificates, which some Python builds do not find."""
    subprocess.run(['/usr/bin/curl', '-fsSL', '--proto', '=https', '--proto-redir', '=https', '--max-time', '300',
                    '-o', str(dest), url], check=True,
                   capture_output=True, stdin=subprocess.DEVNULL)


def install(key: str) -> str:
    """Installs the AI with its maker's script, the way its own instructions say (the script is saved first and
    only run once it has fully arrived). Returns the command; SystemExit when it did not end up installed."""
    url, shell, extra = installer(key)
    with tempfile.TemporaryDirectory(prefix='vinutes-install-') as tmp:
        script = Path(tmp) / 'install.sh'
        try:
            download(url, script)
        except (subprocess.CalledProcessError, OSError):
            raise SystemExit(t('ai_install_failed', ai=AIS[key]))
        env = {**os.environ, **extra,
               'PATH': os.pathsep.join([os.environ.get('PATH', ''), '/usr/bin', '/bin', '/usr/sbin', '/sbin'])}
        try:
            done = subprocess.run([shell, str(script)], cwd=Path.home(), env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=15 * 60)
        except (subprocess.TimeoutExpired, OSError):
            raise SystemExit(t('ai_install_failed', ai=AIS[key]))
    exe = find(key)
    if done.returncode or not exe:
        print((done.stdout + done.stderr)[-2000:])             # for setup.log
        raise SystemExit(t('ai_install_failed', ai=AIS[key]))
    return exe


def sandbox_profile(folder: Path, exe: str) -> str:
    """sandbox-exec rules for agy: it reads the folder, its own sign-in (~/.gemini) and the system-wide preferences,
    writes only the folder (its temporary files go in there too, see run), and starts no other program. Without
    write access to ~/.gemini it keeps no history of the meeting there (tried 2026-10-15: it still answers)."""
    home = Path.home()
    quote = lambda p: '"' + str(p).replace('\\', '\\\\').replace('"', '\\"') + '"'   # noqa: E731
    real = Path(os.path.realpath(exe))
    reads = [folder.resolve(), home / '.gemini', Path(exe).parent, real.parent]
    return '\n'.join([
        '(version 1)',
        '(allow default)',
        f'(deny file-read* (subpath {quote(home)}))',
        f'(allow file-read* (literal {quote(home)}) (literal {quote(home / "Library/Preferences/.GlobalPreferences.plist")}) '
        + ' '.join(f'(subpath {quote(p)})' for p in reads) + ')',
        '(deny file-write*)',
        f'(allow file-write* (subpath {quote(folder.resolve())}) (subpath "/dev"))',
        '(deny process-exec)',
        f'(allow process-exec (literal {quote(exe)}) (literal {quote(real)}))',
    ])


def command(key: str, exe: str, prompt: str, folder: Path, write: bool) -> tuple[list[str], Path | None]:
    """The command line, and the sandbox profile file to remove afterwards (agy only). `write`: the minutes are
    written from the transcript (the agent may look around the folder); otherwise one file is changed."""
    if key == 'claude':
        tools = 'Read,Glob,Grep,Write,Edit' if write else 'Read,Write,Edit'
        return [exe, '-p', prompt, '--restricted', '--strict-mcp-config', '--tools', tools,
                '--permission-mode', 'acceptEdits', '--permission-prompts', 'none'], None
    if key == 'codex':
        return [exe, 'exec', '--sandbox', 'workspace-write', '--skip-git-repo-check', '--ephemeral',
                '-c', 'mcp_servers={}', '--color', 'never', '-C', str(folder), prompt], None   # none of the user's MCP servers
    fd, path = tempfile.mkstemp(prefix='agy-', suffix='.sb')
    with os.fdopen(fd, 'w') as f:
        f.write(sandbox_profile(folder, exe))
    return ['/usr/bin/sandbox-exec', '-f', path, exe, '-p', prompt, '--add-dir', str(folder)], Path(path)


def run(prompt: str, folder: Path, *, write: bool, timeout: int, env: dict, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, key: str | None = None) -> subprocess.CompletedProcess:
    """The chosen AI, working in `folder` only. SystemExit when it is not installed."""
    key = key or chosen()
    exe = find(key)
    if not exe:
        raise SystemExit(t('ai_missing', ai=AIS[key]))
    cmd, profile = command(key, exe, prompt, folder, write)
    scratch = folder / '.ai-tmp'
    if profile:                                       # agy's temporary files stay inside the folder it may write
        scratch.mkdir(exist_ok=True)
        env = {**env, 'TMPDIR': str(scratch) + '/'}
    try:
        return subprocess.run(cmd, cwd=folder, env=env, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                              text=True, timeout=timeout)
    finally:
        if profile:
            profile.unlink(missing_ok=True)
            shutil.rmtree(scratch, ignore_errors=True)
