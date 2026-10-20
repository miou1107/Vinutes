"""The addresses Vinutes knows, for the mail sheet's recipients (prototypes/mail-recipients.html, Vin 2026-10-20):
the company directory (read at most once a day), the people a calendar invitation listed, and the people the user
mailed before. Kept in $MINUTES_HOME/contacts.json as {"synced": when, "people": {address: {name, src}}}, read and
written under the same lock as the projects' people (briefs.py), and readable by the user only.

A name from the meeting's 人員 list becomes an address (address_of) when exactly one contact is called that: the
name as a whole (Amy Chen), the part outside or inside a bracket (陳怡君（Jessie）), or one part of a contact's
name (Evan finds 許志明 Evan). Typing in the sheet offers people by any part of the name or the address (suggest).
Nothing here sends anything.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from briefs import _locked, _read, _write  # noqa: E402
from google_setup import CONFIG  # noqa: E402

CONTACTS = CONFIG / 'contacts.json'
ADDRESS = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
SOURCES = ('directory', 'calendar', 'mail', 'self')      # which source's name wins when two know the address
REFRESH_EVERY = timedelta(days=1)
PEOPLE_API = 'https://people.googleapis.com/v1/people:listDirectoryPeople'
MOST = 8


def _data() -> dict:
    data = _read(CONTACTS)
    return data if isinstance(data, dict) else {}


def _save(data: dict):
    _write(CONTACTS, data)
    try:
        os.chmod(CONTACTS, 0o600)                     # a whole company's names and addresses: the user's eyes only
    except OSError:
        pass


def people() -> dict[str, dict]:
    found = _data().get('people')
    return {a: p for a, p in found.items() if isinstance(p, dict)} if isinstance(found, dict) else {}


def _rank(src: str) -> int:
    return SOURCES.index(src) if src in SOURCES else len(SOURCES)


def _merge(folks: dict, address: str, name: str, src: str):
    """One contact into the table: the directory's name beats a calendar's or a mail's; at the same rank the fuller
    name stays."""
    had = folks.get(address) if isinstance(folks.get(address), dict) else {}
    old_name, old_src = had.get('name') or '', had.get('src') or ''
    if old_name and (_rank(old_src) < _rank(src) or (_rank(old_src) == _rank(src) and len(old_name) >= len(name))):
        name = old_name
    folks[address] = {'name': name, 'src': old_src if old_name and _rank(old_src) <= _rank(src) else src}


def learn(address: str, name: str, src: str):
    """Keep this address under this name (see _merge)."""
    address = (address or '').strip().lower()
    if not ADDRESS.match(address):
        return
    name = ' '.join((name or '').split())[:60]
    with _locked():
        data = _data()
        folks = data.setdefault('people', {})
        before = json.dumps(folks.get(address), sort_keys=True)
        _merge(folks, address, name, src)
        if json.dumps(folks.get(address), sort_keys=True) != before:
            _save(data)


def learn_many(entries: list[tuple[str, str, str]]):
    """Several (address, name, src) at once, one write."""
    with _locked():
        data = _data()
        folks = data.setdefault('people', {})
        before = json.dumps(folks, sort_keys=True)
        for address, name, src in entries:
            address = (address or '').strip().lower()
            if ADDRESS.match(address):
                _merge(folks, address, ' '.join((name or '').split())[:60], src)
        if json.dumps(folks, sort_keys=True) != before:
            _save(data)


def tokens(name: str) -> set[str]:
    """The parts a contact may be called by: 許志明 Evan -> 許志明, evan; one character is not a name."""
    parts = re.split(r'[\s()（）,，、/／]+', (name or '').casefold())
    return {p for p in parts if len(p) >= 2}


ALIAS = re.compile(r'^(?P<outside>.*?)\s*[（(]\s*(?P<inside>[^（）()]*?)\s*[）)]\s*$')


def address_of(name: str) -> str:
    """The one address whose contact is called this, else '' (nobody, or more than one). The name is taken whole;
    a bracket holding an English alias (陳怡君（Jessie）) also tries the two parts, a bracket holding anything else
    (Amy（悠遊卡）, 陳小姐（台灣 PASS）) is an explanation of which person, so only the whole name counts."""
    whole = ' '.join((name or '').split()).casefold()
    keys = {whole} if len(whole) >= 2 else set()
    m = ALIAS.match(whole)
    if m and re.fullmatch(r"[a-z.'-]+", m.group('inside')):
        keys |= {k for k in (m.group('outside'), m.group('inside')) if len(k) >= 2}
    if not keys:
        return ''
    hits = []
    for address, p in people().items():
        called = tokens(p.get('name', '')) | {(p.get('name') or '').casefold()}
        if keys & called:
            hits.append(address)
    return hits[0] if len(hits) == 1 else ''


def suggest(query: str, exclude=()) -> list[dict]:
    """The people whose name or address holds what was typed, for the sheet's menu: {name, mail, src}; a name or
    address that starts with it first."""
    q = ' '.join((query or '').split()).casefold()
    if not q:
        return []
    skip = {a.lower() for a in exclude}
    found = []
    for address, p in people().items():
        name = p.get('name') or ''
        low = name.casefold()
        if address in skip or not (q in low or q in address):
            continue
        starts = low.startswith(q) or address.startswith(q) or any(t.startswith(q) for t in tokens(name))
        found.append((0 if starts else 1, address, {'name': name or address, 'mail': address, 'src': p.get('src', '')}))
    return [row for _, _, row in sorted(found, key=lambda r: (r[0], r[1]))][:MOST]


def refresh_directory():
    """The company directory into the contacts, at most once a day; quietly nothing when offline. An account
    without a directory (a personal Gmail, or the People API not turned on) is remembered too, so it is not asked
    again that day."""
    data = _data()
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
            found += page.get('people', []) if isinstance(page, dict) else []
            token = page.get('nextPageToken') if isinstance(page, dict) else None
            if not token:
                break
    except SystemExit as err:
        if re.search(r'HTTP 4\d\d', str(err)):      # no directory for this account: ask again tomorrow, not now
            _stamp(no_directory=True)
        return
    except Exception:                                 # noqa: BLE001  an odd answer must not stop the meeting opening
        return
    entries = []
    for person in found:
        names = [n.get('displayName') for n in person.get('names', []) if n.get('displayName')]
        mails = [e.get('value') for e in person.get('emailAddresses', []) if e.get('value')]
        if mails:
            entries.append((mails[0], names[0] if names else '', 'directory'))
    learn_many(entries)
    _stamp()


def _stamp(no_directory: bool = False):
    with _locked():
        data = _data()
        data['synced'] = datetime.now(timezone.utc).isoformat()
        if no_directory:
            data['no_directory'] = True
        else:
            data.pop('no_directory', None)
        _save(data)
