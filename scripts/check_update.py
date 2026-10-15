"""Check GitHub for a newer version of Vinutes, at most once a day and once per new version.

Usage:
  check_update.py            prints one line: UP TO DATE / UPDATE / ALREADY ASKED / SKIPPED / COULD NOT CHECK
  check_update.py --force    check now and report even a version the user was already asked about

UPDATE is followed by the newest section of the remote CHANGELOG.md, so the AI can tell the user in one or two
sentences what the new version adds before asking whether to update. Only a version number and the public
CHANGELOG are fetched from GitHub; nothing about the user is sent. The last check is remembered in
$MINUTES_HOME/update-check.json, so a declined version is not asked about again.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_setup import CONFIG  # noqa: E402  (standard library only)

RAW = 'https://raw.githubusercontent.com/miou1107/Vinutes/main/'
ROOT = Path(__file__).resolve().parent.parent
STATE = CONFIG / 'vinutes-update-check.json'   # the skill keeps its own update-check.json
DAY = 24 * 3600


def version_of(text: str) -> tuple[int, ...] | None:
    """The version in a VERSION file (`0.1.0`) or a `version: "0.1.0"` line."""
    match = re.search(r'^\s*(?:version:\s*)?"?(\d+(?:\.\d+)*)"?\s*$', text, re.M)
    return tuple(int(n) for n in match.group(1).split('.')) if match else None


def shown(version: tuple[int, ...] | None) -> str:
    return 'v' + '.'.join(map(str, version)) if version else 'unknown'


def fetch(name: str) -> str:
    with urllib.request.urlopen(RAW + name, timeout=5) as resp:
        return resp.read().decode('utf-8')


def newest_section(changelog: str) -> str:
    parts = re.split(r'^## ', changelog, flags=re.M)
    return ('## ' + parts[1]).strip() if len(parts) > 1 else ''


def load_state() -> dict:
    try:
        data = json.loads(STATE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict):
    try:
        CONFIG.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2), encoding='utf-8')
    except OSError:
        pass                                    # remembering is a nicety; never fail the user's work over it


def main():
    force = '--force' in sys.argv
    state = load_state()
    if not force and time.time() - state.get('checked_at', 0) < DAY:
        print('SKIPPED (checked within the last day)')
        return
    local = version_of((ROOT / 'VERSION').read_text(encoding='utf-8'))
    try:
        remote = version_of(fetch('VERSION'))
    except Exception as err:                    # offline, GitHub down, proxy: say so and move on
        print(f'COULD NOT CHECK ({err.__class__.__name__})')
        return
    state['checked_at'] = time.time()
    if not (local and remote) or remote <= local:
        save_state(state)
        print(f'UP TO DATE {shown(local)}')
        return
    if not force and state.get('asked_version') == shown(remote):
        save_state(state)
        print(f'ALREADY ASKED {shown(remote)} (installed {shown(local)})')
        return
    state['asked_version'] = shown(remote)
    save_state(state)
    git = 'git' if (ROOT / '.git').exists() else 'no git'
    print(f'UPDATE {shown(local)} -> {shown(remote)} (folder: {ROOT}, {git})')
    try:
        print(newest_section(fetch('CHANGELOG.md')))
    except Exception:
        pass


if __name__ == '__main__':
    main()
