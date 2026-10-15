"""Share the minutes Doc with attendees and let Google email them the link with the user's message.

Usage: notify.py <minutes.md|doc-id> <message.txt> <email>[,<email>...] [--role writer|commenter|reader]

The message file is the exact text the user approved (the subject line is set by Google).
Default role: writer for colleagues on the user's company domain (so they can fill in the [__] blanks),
commenter for anyone outside the company, because editors can read the version history.
"""
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from md_to_gdoc import AUTH, access_token, call, company_domain, sidecar_for  # noqa: E402
from google_setup import same_company  # noqa: E402


def doc_id_of(arg: str) -> str:
    path = Path(arg)
    if path.suffix in ('.md', '.docx'):
        sidecar = sidecar_for(path)
        if not sidecar.exists():
            sys.exit(f'no {sidecar.name}; publish the minutes first')
        return json.loads(sidecar.read_text())['id']
    match = re.search(r'[-A-Za-z0-9_]{25,}', arg)
    if not match:
        sys.exit('pass a minutes .md or a Google Doc id/url')
    return match.group(0)


def main():
    if 'MINUTES_NO_SEND' in os.environ:
        sys.exit('STOP: automatic run (MINUTES_NO_SEND); sharing mails go out only after the user approves')
    doc = doc_id_of(sys.argv[1])
    message = Path(sys.argv[2]).read_text(encoding='utf-8').strip()
    emails = [e.strip() for e in sys.argv[3].split(',') if e.strip()]
    forced = sys.argv[sys.argv.index('--role') + 1] if '--role' in sys.argv else None
    AUTH['Authorization'] = 'Bearer ' + access_token()
    me = call('https://www.googleapis.com/drive/v3/about?fields=user(emailAddress)')['user']['emailAddress']
    company = company_domain(me)
    already = {p.get('emailAddress', '').lower() for p in call(
        f'https://www.googleapis.com/drive/v3/files/{doc}/permissions?fields=permissions(emailAddress)')['permissions']}
    query = urllib.parse.urlencode({'sendNotificationEmail': 'true', 'emailMessage': message,
                                    'fields': 'id,role,emailAddress'})
    for email in emails:
        if email.lower() in already:
            print('skip, already shared:', email)      # a rerun after a partial failure must not email twice
            continue
        role = forced or ('writer' if same_company(email, company) else 'commenter')
        body = json.dumps({'type': 'user', 'role': role, 'emailAddress': email}).encode()
        print(call(f'https://www.googleapis.com/drive/v3/files/{doc}/permissions?{query}', body, 'POST',
                   {'Content-Type': 'application/json'}))


if __name__ == '__main__':
    main()
