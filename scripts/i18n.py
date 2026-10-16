"""Which language Vinutes speaks, and its words in that language.

Two languages: 'en' (the default) and 'zh-TW'. The app's language is, in order:
  1. VINUTES_LANG, which the menu-bar app sets for every script it starts, so the window, the menu and the
     scripts never disagree;
  2. "language" in settings.json ("en" or "zh-TW"), which the app writes when the user picks one ("auto" = none);
  3. the Mac's own language: Chinese first in System Settings > Language & Region -> zh-TW, anything else -> en.

The meeting's language is a separate setting, "meeting_language": "auto" (the default; transcribe.py listens to
the recording and decides), "en" or "zh". Minutes follow the meeting: a Chinese meeting gets Chinese minutes, an
English meeting English ones, and a meeting in any other language gets minutes in the app's language.

Words live in strings.py, one table per language with the same keys; t('key', name=...) fills in the blanks.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from google_setup import CONFIG, settings  # noqa: E402

LANGS = ('en', 'zh-TW')
MEETING_LANGS = ('auto', 'en', 'zh')


def norm(value: str) -> str:
    """'zh', 'zh-Hant-TW', 'zh_TW' -> 'zh-TW'; 'en', 'en-US' -> 'en'; anything else -> ''."""
    v = (value or '').strip().lower().replace('_', '-')
    if v.startswith('zh'):
        return 'zh-TW'
    if v.startswith('en'):
        return 'en'
    return ''


@lru_cache(maxsize=1)
def mac_lang() -> str:
    """The first language in the Mac's list: Chinese of any kind -> zh-TW, else en."""
    try:
        out = subprocess.run(['defaults', 'read', '-g', 'AppleLanguages'], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return 'en'
    first = next((w.strip(' ",()') for w in out.split('\n') if w.strip(' ",()')), '')
    return 'zh-TW' if first.lower().startswith('zh') else 'en'


def ui_lang() -> str:
    return norm(os.environ.get('VINUTES_LANG', '')) or norm(str(settings().get('language') or '')) or mac_lang()


def meeting_setting() -> str:
    v = str(settings().get('meeting_language') or 'auto').strip().lower()
    return v if v in MEETING_LANGS else 'auto'


def minutes_lang(spoken: str) -> str:
    """The language the minutes are written in, from the language the meeting was held in (Whisper's code)."""
    spoken = (spoken or '').lower()
    if spoken in ('zh', 'yue'):
        return 'zh-TW'
    if spoken == 'en':
        return 'en'
    return ui_lang()


def save(key: str, value: str):
    """Write one key of settings.json, keeping the rest (used for "language" and "meeting_language")."""
    path = CONFIG / 'settings.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data[key] = value
    CONFIG.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def t(key: str, lang: str | None = None, **values) -> str:
    """The words for `key` in the app's language (or `lang`), with {name} blanks filled from `values`."""
    from strings import STRINGS
    table = STRINGS.get(lang or ui_lang()) or STRINGS['en']
    text = table.get(key)
    if text is None:
        text = STRINGS['en'].get(key, key)
    return text.format(**values) if values else text
