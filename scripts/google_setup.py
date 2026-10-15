"""Google sign-in for this skill: the user's own OAuth client and one token, kept outside any project folder.

Usage:
  google_setup.py check     what is set up, what is missing, and the next step to give the user
  google_setup.py login     open Google's consent page and save the token (pip3 install google-auth-oauthlib);
                            waits up to 10 minutes for the user, so run it with a long timeout

Everything that belongs to the user lives in $MINUTES_HOME, default ~/.config/vin-meeting-minutes-zh/, never in
the skill folder, so updating or sharing the skill cannot overwrite or leak it:
  settings.json       {"owner": "name@company.com", "sender_name": "...", "our_company": "...", "share_domain": "...",
                       "transcript_search": "...", "style": {...}, "auto_folder": "...", "claude_path": "...",
                       "ai": "claude|codex|antigravity"};
                      every key optional, an empty value counts as unset (auto_folder and claude_path are read by
                      auto_minutes.py, the recorder's background job; ai, the AI that writes the minutes, by ai_runner.py);
                      a non-empty MINUTES_OWNER / MINUTES_SENDER_NAME / MINUTES_SHARE_DOMAIN overrides the file
  notes.md            the user's own extra rules and real examples for the AI (SKILL.md says when to read it)
  glossary.md         the company's own misheard words, used together with references/glossary.md
  oauth-client.json   the user's own OAuth client (type: Desktop app) from their own Google Cloud project
  google-token.json   the refresh token saved by `login`, plus the account and its company domain; never printed

One token covers Google Drive and Docs (create the minutes Docs; the recorder app edits them paragraph by
paragraph and answers their comments), Gmail (read transcript mails, send the
minutes), Calendar (meeting time, room and attendees; the next meeting's invite) and the company directory
(look up a colleague's address). Turning a transcript into a Word file needs none of this.

The "company domain" is the Google Workspace domain of the signed-in account, as Google reports it at login
(personal accounts have none). A new Doc is shared with it as commenter, and colleagues on it get edit access
when the minutes are mailed. share_domain in settings.json (or $MINUTES_SHARE_DOMAIN) overrides it; "none" means
no company domain.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG = Path(os.environ.get('MINUTES_HOME') or '~/.config/vin-meeting-minutes-zh').expanduser()
CLIENT = CONFIG / 'oauth-client.json'
SETTINGS = CONFIG / 'settings.json'
TOKEN = CONFIG / 'google-token.json'
ACCESS = CONFIG / 'google-access.json'          # the current short-lived access token, shared by the scripts
SCOPES = ['openid',
          'https://www.googleapis.com/auth/userinfo.email',
          'https://www.googleapis.com/auth/drive',
          'https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/gmail.send',
          'https://www.googleapis.com/auth/calendar.readonly',
          'https://www.googleapis.com/auth/calendar.events',
          'https://www.googleapis.com/auth/directory.readonly']
# used only for a token saved without the Workspace domain: free mail providers are never a company domain
PERSONAL_DOMAINS = {'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.com.tw', 'hotmail.com', 'hotmail.com.tw',
                    'outlook.com', 'live.com', 'msn.com', 'icloud.com', 'me.com', 'mac.com', 'msa.hinet.net',
                    'hinet.net', 'pchome.com.tw', 'seed.net.tw', 'kimo.com', 'proton.me', 'protonmail.com'}


SETTING_KEYS = ('owner', 'sender_name', 'our_company', 'share_domain', 'transcript_search', 'style',
                'auto_folder', 'drive_folder', 'claude_path', 'ai')
_WARNED = []


def read_settings() -> tuple[dict, str]:
    """(settings, problem); problem is '' when the file is missing or fine."""
    if not SETTINGS.exists():
        return {}, ''
    try:
        data = json.loads(SETTINGS.read_text(encoding='utf-8-sig'))   # -sig: Notepad saves a BOM
    except (OSError, ValueError) as err:
        return {}, f'cannot read {SETTINGS} ({err})'
    if not isinstance(data, dict):
        return {}, f'{SETTINGS} must hold a JSON object {{...}}'
    return data, ''


def settings() -> dict:
    data, problem = read_settings()
    if problem and not _WARNED:                     # never crash on it, but never ignore it silently either
        _WARNED.append(problem)
        print(f'WARNING: {problem}; running without it', file=sys.stderr)
    return data


def setting(key: str, env: str) -> str:
    """A non-empty environment variable first, then settings.json; '' when neither is set."""
    value = (os.environ.get(env) or '').strip()
    if not value:
        value = str(settings().get(key) or '').strip()
    return value


def owner() -> str:
    return setting('owner', 'MINUTES_OWNER').lower()


def sender_name() -> str:
    return setting('sender_name', 'MINUTES_SENDER_NAME')


def client_info() -> dict | None:
    try:
        blob = json.loads(CLIENT.read_text())
        client = blob.get('installed') or blob.get('web')
    except (OSError, ValueError, AttributeError):
        return None
    return client if isinstance(client, dict) and 'client_secret' in client else None


def saved_token() -> dict:
    return json.loads(TOKEN.read_text())


def access_token() -> str:
    if not (TOKEN.exists() and CLIENT.exists()):
        sys.exit(f'NO GOOGLE LOGIN: {TOKEN} or {CLIENT} is missing. Hand over the Word file from md_to_docx.py, '
                 'or walk the user through the Google setup (SKILL.md section 6, step 9; start with google_setup.py check).')
    client = client_info()
    if not client:
        sys.exit(f'STOP: {CLIENT} is not an OAuth client JSON. Run google_setup.py check.')
    refresh = saved_token()['refresh_token']
    # every script is its own process; one access token (valid an hour) serves them all until it nearly runs out
    tag = hashlib.sha256(refresh.encode()).hexdigest()[:16]
    try:
        cached = json.loads(ACCESS.read_text())
        if cached.get('for') == tag and cached.get('until', 0) > time.time() + 120:
            return cached['token']
    except (OSError, ValueError):
        pass
    data = urllib.parse.urlencode({'client_id': client['client_id'], 'client_secret': client['client_secret'],
                                   'refresh_token': refresh, 'grant_type': 'refresh_token'}).encode()
    try:
        answer = json.load(urllib.request.urlopen(client['token_uri'], data, timeout=30))
    except urllib.error.HTTPError as err:
        sys.exit(f'GOOGLE LOGIN EXPIRED ({err.code} {err.read().decode(errors="replace")[:200]}). '
                 'Run google_setup.py login again.')
    except (urllib.error.URLError, OSError) as err:
        sys.exit(f'OFFLINE: Google did not answer ({err})')
    try:
        fd = os.open(ACCESS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)    # never readable by others, not even briefly
        with os.fdopen(fd, 'w') as f:
            f.write(json.dumps({'for': tag, 'token': answer['access_token'],
                                'until': time.time() + int(answer.get('expires_in', 3600))}))
        ACCESS.chmod(0o600)
    except OSError:
        pass
    return answer['access_token']


def company_domain(email: str) -> str | None:
    override = setting('share_domain', 'MINUTES_SHARE_DOMAIN').lower().lstrip('@')
    if override:                            # only an explicit "none" turns the company domain off
        return None if override == 'none' else override
    try:
        token = saved_token()
    except (OSError, ValueError):
        token = {}
    if 'hd' in token:                       # saved by login from Google's own answer; None for personal accounts
        return token['hd'] or None
    domain = email.lower().rsplit('@', 1)[-1]
    return None if domain in PERSONAL_DOMAINS else domain


def same_company(email: str, domain: str | None) -> bool:
    return bool(domain) and email.lower().endswith('@' + domain)


# ---------- check ----------

def probe(token: str, name: str, url: str):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
    try:
        return True, json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors='replace')
        if 'SERVICE_DISABLED' in body or 'has not been used' in body:
            why = f'{name} is not enabled in the Cloud project (step 2)'
        elif 'insufficient' in body.lower() or 'ACCESS_TOKEN_SCOPE_INSUFFICIENT' in body:
            why = 'the token lacks this permission; run google_setup.py login again and allow everything'
        else:
            why = f'HTTP {err.code}: {body[:160]}'
        return False, why


def check():
    print(f'settings folder: {CONFIG}')
    mine, problem = read_settings()
    if problem:
        print(f'[ ] settings.json: {problem}')
    else:
        shown = {k: mine[k] for k in SETTING_KEYS if k in mine}
        print('    settings.json: ' + (json.dumps(shown, ensure_ascii=False) if shown else 'none yet (optional)'))
    print('    notes.md: ' + ('yes' if (CONFIG / 'notes.md').exists() else 'none')
          + ' | glossary.md: ' + ('yes' if (CONFIG / 'glossary.md').exists() else 'none'))
    if not CLIENT.exists():
        print('[ ] OAuth client: missing')
        print('NEXT: SKILL.md section 6, step 9, items 1-4 (Cloud project, five APIs, consent screen, '
              f'Desktop app client), then save the downloaded JSON as {CLIENT}')
        return
    if not client_info():
        print('[ ] OAuth client: the file is not an OAuth client JSON')
        print('NEXT: download the client again (type: Desktop app) and save it over ' + str(CLIENT))
        return
    if 'installed' not in json.loads(CLIENT.read_text()):
        print('[ ] OAuth client: this is a "Web application" client; login needs a "Desktop app" one')
        print('NEXT: SKILL.md section 6, step 9, item 4: create a Desktop app client and save it over ' + str(CLIENT))
        return
    print('[x] OAuth client: Desktop app')
    try:
        import google_auth_oauthlib  # noqa: F401
        print('[x] google-auth-oauthlib installed')
    except ImportError:
        print('[ ] google-auth-oauthlib: not installed (needed only for login): pip3 install google-auth-oauthlib')
    if not TOKEN.exists():
        print('[ ] signed in: no token yet')
        print('NEXT: google_setup.py login')
        return
    token = access_token()
    ok, about = probe(token, 'Google Drive API', 'https://www.googleapis.com/drive/v3/about?fields=user(emailAddress)')
    email = about['user']['emailAddress'] if ok else ''
    print(f'[{"x" if ok else " "}] Google Drive: ' + (email if ok else about))
    checks = [('Gmail API', 'https://gmail.googleapis.com/gmail/v1/users/me/profile'),
              ('Google Calendar API', 'https://www.googleapis.com/calendar/v3/users/me/calendarList?maxResults=1'),
              ('People API', 'https://people.googleapis.com/v1/people:searchDirectoryPeople?' + urllib.parse.urlencode(
                  {'query': 'a', 'readMask': 'names', 'sources': 'DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE', 'pageSize': 1}))]
    # the recorder app changes the minutes' Doc paragraph by paragraph through the Docs API; a document that does
    # not exist answers 404 when the API is on, and SERVICE_DISABLED when it is off
    ok, why = probe(token, 'Google Docs API', 'https://docs.googleapis.com/v1/documents/' + 'x' * 44)
    docs_on = ok or 'HTTP 404' in why or 'HTTP 403' in why and 'not enabled' not in why
    print(f'[{"x" if docs_on else " "}] Google Docs API' + ('' if docs_on else f': {why}'))
    for name, url in checks:
        ok, result = probe(token, name, url)
        if ok and name == 'Gmail API':
            email = email or result['emailAddress']
        note = '' if ok else result
        if not ok and name == 'People API' and email and not company_domain(email):
            note = 'a personal Google account has no company directory; looking up addresses will not work'
        print(f'[{"x" if ok else " "}] {name}' + (f': {note}' if note else ''))
    if email:
        domain = company_domain(email)
        print(f'signed in as {email}; company domain: ' + (domain or 'none (new Docs are not shared, nobody gets '
                                                           'edit access by mail)'))


# ---------- login ----------

def id_claims(id_token: str | None) -> dict:
    """The ID token comes straight from Google's token endpoint over TLS; only its payload is read."""
    if not id_token:
        return {}
    payload = id_token.split('.')[1]
    return json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))


def login():
    if not CLIENT.exists():
        sys.exit(f'STOP: {CLIENT} is missing. Finish items 1-4 of SKILL.md section 6, step 9 first.')
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit('STOP: run pip3 install google-auth-oauthlib first')
    os.environ.setdefault('OAUTHLIB_RELAX_TOKEN_SCOPE', '1')   # an unticked permission is reported below, not a crash
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
    hint = {'login_hint': owner()} if owner() else {}
    creds = flow.run_local_server(port=0, open_browser=True, prompt='consent', timeout_seconds=600,
                                  authorization_prompt_message='Opening the consent page. If no browser opens, '
                                                               'give the user this link: {url}', **hint)
    granted = getattr(creds, 'granted_scopes', None) or creds.scopes or SCOPES
    granted = sorted(granted.split() if isinstance(granted, str) else granted)
    claims = id_claims(creds.id_token)
    CONFIG.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG, 0o700)
    fd = os.open(TOKEN, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as fh:
        fh.write(json.dumps({'refresh_token': creds.refresh_token, 'scopes': granted,
                             'email': claims.get('email'), 'hd': claims.get('hd')}))
    os.chmod(TOKEN, 0o600)                         # also when the file already existed with wider rights
    missing = [s.rsplit('/', 1)[-1] for s in SCOPES if s not in granted]
    if missing:
        print('saved, but these permissions were not ticked: ' + ', '.join(missing)
              + '. Run google_setup.py login again and tick every box.')
    else:
        print(f'saved for {claims.get("email") or "the account"}; now run google_setup.py check')


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('check', 'login'):
        sys.exit(__doc__)
    check() if sys.argv[1] == 'check' else login()
