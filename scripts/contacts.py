"""The addresses Vinutes knows, for the mail sheet's recipients (prototypes/mail-recipients.html, Vin 2026-10-20):
the company directory (read at most once a day), the people a calendar invitation listed, and the people the user
mailed before. Kept in $MINUTES_HOME/contacts.json as {"synced": when, "people": {address: {name, src}}}.

A name from the meeting's 人員 list becomes an address (address_of) when exactly one contact has that name, or a
part of it (Evan, 許志明, 許志明(Evan) all find 許志明 Evan); typing in the sheet offers people by any part of the
name or the address (suggest). Nothing here sends anything.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from briefs import name_keys  # noqa: E402
from google_setup import CONFIG  # noqa: E402

CONTACTS = CONFIG / 'contacts.json'
ADDRESS = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
SOURCES = ('directory', 'calendar', 'mail', 'self')      # which source's name wins when two know the address
REFRESH_EVERY = timedelta(days=1)
PEOPLE_API = 'https://people.googleapis.com/v1/people:listDirectoryPeople'
MOST = 8


def _read() -> dict:
    try:
        data = json.loads(CONTACTS.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict):
    CONTACTS.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONTACTS.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.replace(CONTACTS)


def people() -> dict[str, dict]:
    found = _read().get('people')
    return {a: p for a, p in found.items() if isinstance(p, dict)} if isinstance(found, dict) else {}


def learn(address: str, name: str, src: str):
    """Keep this address under this name. A fuller name replaces a shorter one; a directory name is never replaced
    by what a calendar or a mail called the person."""
    address = (address or '').strip().lower()
    if not ADDRESS.match(address):
        return
    name = ' '.join((name or '').split())[:60]
    data = _read()
    folks = data.setdefault('people', {})
    had = folks.get(address) if isinstance(folks.get(address), dict) else {}
    rank = SOURCES.index if src in SOURCES else (lambda s: len(SOURCES))

    def order(s):
        return SOURCES.index(s) if s in SOURCES else len(SOURCES)
    old_src, old_name = had.get('src', ''), had.get('name', '')
    if old_name and (order(old_src) < order(src) or len(old_name) >= len(name)):
        name = old_name
    folks[address] = {'name': name, 'src': old_src if old_name and order(old_src) <= order(src) else src}
    _write(data)


def tokens(name: str) -> set[str]:
    """The parts of a name a person may be called by: 許志明 Evan -> 許志明, evan; one character is not a name."""
    parts = re.split(r'[\s()（）,，、/／]+', (name or '').casefold())
    return {p for p in parts if len(p) >= 2}


def address_of(name: str) -> str:
    """The one address whose contact is called this, else '' (nobody, or more than one)."""
    keys = {k for k in name_keys(name or '') if len(k) >= 2} | tokens(name)
    if not keys:
        return ''
    hits = []
    for address, p in people().items():
        called = tokens(p.get('name', '')) | {(p.get('name') or '').casefold()}
        if keys & called:
            hits.append(address)
    return hits[0] if len(hits) == 1 else ''


def suggest(query: str, exclude=()) -> list[dict]:
    """The people whose name or address contains what was typed, for the sheet's menu: {name, mail, src}."""
    q = ' '.join((query or '').split()).casefold()
    if not q:
        return []
    out = []
    skip = {a.lower() for a in exclude}
    for address, p in sorted(people().items()):
        name = p.get('name') or ''
        if address in skip or not (q in name.casefold() or q in address):
            continue
        out.append({'name': name or address, 'mail': address, 'src': p.get('src', '')})
        if len(out) >= MOST:
            break
    return out


def refresh_directory():
    """The company directory into the contacts, at most once a day; quietly nothing when offline or when the
    account has no directory (a personal Gmail)."""
    data = _read()
    synced = data.get('synced')
    try:
        if synced and datetime.now(timezone.utc) - datetime.fromisoformat(synced) < REFRESH_EVERY:
            return
    except (TypeError, ValueError):
        pass
    import urllib.parse
    import doc_sync
    found, token = [], None
    try:
        while True:
            query = urllib.parse.urlencode({'readMask': 'names,emailAddresses', 'sources': 'DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE',
                                            'pageSize': 200, **({'pageToken': token} if token else {})})
            page = doc_sync.call(f'{PEOPLE_API}?{query}')
            found += page.get('people', [])
            token = page.get('nextPageToken')
            if not token:
                break
    except SystemExit:
        return
    for person in found:
        names = [n.get('displayName') for n in person.get('names', []) if n.get('displayName')]
        mails = [e.get('value') for e in person.get('emailAddresses', []) if e.get('value')]
        if mails:
            learn(mails[0], names[0] if names else '', 'directory')
    data = _read()
    data['synced'] = datetime.now(timezone.utc).isoformat()
    _write(data)
