"""Let every AI tool on this Mac look things up in the meetings, and change them when asked: adds Vinutes' MCP server
(mcp_server.py) to each one that is installed. install.sh runs it; running it again changes nothing.

  connect_agents.py [--remove]

Claude Code, Codex and Gemini CLI are told with their own `mcp add` command, at user level so every folder sees it.
Claude's desktop app, Antigravity and Cursor keep their servers in a JSON file: Vinutes' entry is added or brought
up to date, everything else in the file stays as it is, and the file is written in one step. A tool that is not
installed is left alone. What happened is printed one line per tool, and logged (scripts.log).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = 'vinutes'
HOME = Path.home()
JSON_TOOLS = [   # (name, the folder that shows the tool is installed, its settings file)
    ('Claude desktop app', HOME / 'Library/Application Support/Claude',
     HOME / 'Library/Application Support/Claude/claude_desktop_config.json'),
    ('Antigravity', HOME / '.gemini/antigravity', HOME / '.gemini/antigravity/mcp_config.json'),
    ('Cursor', HOME / '.cursor', HOME / '.cursor/mcp.json'),
]


def server() -> list[str]:
    """How a tool starts the server: Vinutes' own Python and this folder's mcp_server.py."""
    return [sys.executable, str(HERE / 'mcp_server.py')]


def run(*cmd: str) -> subprocess.CompletedProcess:
    """A tool's command; one that hangs or asks something counts as failed, after 60 s at most."""
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    except (subprocess.TimeoutExpired, OSError) as err:
        return subprocess.CompletedProcess(list(cmd), 124, '', f'{err.__class__.__name__}')


def cli(tool: str, label: str, remove: bool) -> str:
    exe = shutil.which(tool)
    if not exe:
        return f'{label}: not installed'
    cmd = server()
    if tool == 'claude':
        got = run(exe, 'mcp', 'get', NAME)
        have, same = got.returncode == 0, all(part in got.stdout for part in cmd)
        drop = [exe, 'mcp', 'remove', '--scope', 'user', NAME]
        add = [exe, 'mcp', 'add', '--scope', 'user', NAME, '--', *cmd]
    elif tool == 'codex':
        got = run(exe, 'mcp', 'get', NAME)
        have, same = got.returncode == 0, all(part in got.stdout for part in cmd)
        drop = [exe, 'mcp', 'remove', NAME]
        add = [exe, 'mcp', 'add', NAME, '--', *cmd]
    else:                                            # gemini
        listed = run(exe, 'mcp', 'list')
        mine = [line for line in (listed.stdout + listed.stderr).splitlines()
                if re.match(rf'^\W*{NAME}:', line.strip())]
        have, same = bool(mine), bool(mine) and all(part in mine[0] for part in cmd)
        drop = [exe, 'mcp', 'remove', '-s', 'user', NAME]
        add = [exe, 'mcp', 'add', '-s', 'user', NAME, *cmd]
    if remove:
        return f'{label}: removed' if have and run(*drop).returncode == 0 else f'{label}: nothing to remove'
    if have and same:
        return f'{label}: already connected'
    if have:                                         # an older entry points at another Python or folder: replace it
        run(*drop)
    done = run(*add)
    if done.returncode == 0:
        return f'{label}: connected'
    said = (done.stderr or done.stdout).strip().splitlines()
    return f'{label}: could not connect ({said[-1] if said else f"exit {done.returncode}"})'


def json_tool(label: str, folder: Path, file: Path, remove: bool) -> str:
    if not folder.is_dir():
        return f'{label}: not installed'
    try:
        text = file.read_text(encoding='utf-8') if file.is_file() else ''
        data = json.loads(text) if text.strip() else {}
    except (OSError, ValueError) as err:
        return f'{label}: left alone, its settings file could not be read ({err.__class__.__name__})'
    if not isinstance(data, dict) or not isinstance(data.get('mcpServers', {}), dict):
        return f'{label}: left alone, its settings file is not what Vinutes expects'
    servers = data.get('mcpServers', {})
    cmd = server()
    entry = {'command': cmd[0], 'args': cmd[1:]}
    if remove:
        if NAME not in servers:
            return f'{label}: nothing to remove'
        servers.pop(NAME)
    elif servers.get(NAME) == entry:
        return f'{label}: already connected'
    else:
        servers[NAME] = entry
    data['mcpServers'] = servers
    target = file.resolve()                          # a linked settings file stays linked: write where it points
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600   # keys inside stay private
    fd, tmp = tempfile.mkstemp(prefix='.vinutes-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except OSError as err:
        Path(tmp).unlink(missing_ok=True)
        return f'{label}: could not write its settings file ({err.__class__.__name__})'
    return f'{label}: {"removed" if remove else "connected"}' + (' (restart it to see the meetings)' if not remove else '')


def main():
    remove = '--remove' in sys.argv[1:]
    steps = [lambda t=t, l=l: cli(t, l, remove) for t, l in (('claude', 'Claude Code'), ('codex', 'Codex'),
                                                               ('gemini', 'Gemini CLI'))]
    steps += [lambda a=a, b=b, c=c: json_tool(a, b, c, remove) for a, b, c in JSON_TOOLS]
    lines = []
    for step in steps:                               # one tool's trouble never stops the others
        try:
            line = step()
        except Exception as err:
            line = f'tool skipped: {err.__class__.__name__}: {err}'
        print(line, flush=True)
        lines.append(line)
    try:
        import vlog
        vlog.log('agents: ' + '; '.join(lines))
    except Exception:
        pass


if __name__ == '__main__':
    main()
