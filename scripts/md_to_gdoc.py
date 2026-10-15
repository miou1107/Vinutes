"""Publish meeting minutes as a Google Doc owned by the user's Google account (google_setup.py), shared to their company.

Usage:
  md_to_gdoc.py <minutes.md|minutes.docx> <drive-folder-name-or-id>   create a new Doc
        [--create-folder]                                             make the folder in My Drive if there is none
  md_to_gdoc.py <minutes.md|minutes.docx> --update                      overwrite the Doc recorded for this minutes
  md_to_gdoc.py <minutes.md> --accept-current                           after merging a pulled copy, take the Doc's
                                                                        current state as the new baseline

The record lives next to the Markdown file as <name>.md.gdoc.json, also when the input is <name>.docx,
so the same Doc is updated whichever file is uploaded.

.md is rendered with md_to_docx.py (the standard layout) and the .docx is uploaded and converted, so the
Google Doc looks exactly like the Word file. A new Doc gets general access "<company domain>, anyone with
the link can comment" (google_setup.company_domain; none for a personal Gmail account); updates never
touch sharing.

--update refuses when the Doc changed since the last upload (modifiedTime or plain text differs) or has
unresolved comments. Merge flow: gdoc_to_md.py <doc> <name>.remote.md (records when it pulled), merge the
edits into <name>.md, --accept-current (refuses if the Doc changed again after the pull), then --update.
"""
import hashlib
import json
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DOC_MIME = 'application/vnd.google-apps.document'
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
AUTH = {}

sys.path.insert(0, str(Path(__file__).parent))
from google_setup import access_token, company_domain, owner  # noqa: E402  (re-exported for notify.py)

OWNER = owner()                 # optional: warn when the Doc is owned by someone else


def call(url, body=None, method=None, headers=None, raw=False):
    req = urllib.request.Request(url, data=body, method=method, headers={**AUTH, **(headers or {})})
    resp = urllib.request.urlopen(req, timeout=120).read()
    return resp if raw else json.loads(resp)


def export_text(doc_id: str) -> str:
    url = f'https://www.googleapis.com/drive/v3/files/{doc_id}/export?mimeType=text/plain'
    return call(url, raw=True).decode('utf-8').lstrip('﻿')


def modified_time(doc_id: str) -> str:
    return call(f'https://www.googleapis.com/drive/v3/files/{doc_id}?fields=modifiedTime')['modifiedTime']


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sidecar_for(path: Path) -> Path:
    """One record per minutes, keyed by the Markdown name even when a .docx is uploaded."""
    return path.with_suffix('.md').with_name(path.with_suffix('.md').name + '.gdoc.json')


def open_comments(doc_id: str) -> int:
    count, token = 0, ''
    while True:
        page = call(f'https://www.googleapis.com/drive/v3/files/{doc_id}/comments'
                    f'?fields=nextPageToken,comments(resolved)&pageSize=100'
                    + (f'&pageToken={urllib.parse.quote(token)}' if token else ''))
        count += sum(1 for c in page.get('comments', []) if not c.get('resolved'))
        token = page.get('nextPageToken')
        if not token:
            return count


def find_folder(name_or_id: str) -> str:
    if name_or_id == 'root' or re.fullmatch(r'[A-Za-z0-9_-]{25,}', name_or_id):
        return name_or_id
    safe = name_or_id.replace("'", "\\'")
    q = urllib.parse.quote(f"name = '{safe}' and mimeType = 'application/vnd.google-apps.folder' "
                           f"and trashed = false and 'me' in owners")
    files = call(f'https://www.googleapis.com/drive/v3/files?q={q}&fields=files(id,name)').get('files', [])
    if not files and '--create-folder' in sys.argv:
        made = call('https://www.googleapis.com/drive/v3/files?fields=id',
                    json.dumps({'name': name_or_id, 'mimeType': 'application/vnd.google-apps.folder'}).encode(),
                    'POST', {'Content-Type': 'application/json'})
        print(f'created folder "{name_or_id}" in My Drive')
        return made['id']
    if not files:
        sys.exit(f'folder not found: {name_or_id} (add --create-folder to make it in My Drive)')
    if len(files) > 1:
        sys.exit(f'more than one folder named {name_or_id}; pass the folder id instead')
    return files[0]['id']


def share_with_company(doc_id: str, domain: str) -> str:
    perms = call(f'https://www.googleapis.com/drive/v3/files/{doc_id}/permissions'
                 f'?fields=permissions(type,domain,role)')['permissions']
    for p in perms:
        if p['type'] == 'domain' and p.get('domain') == domain:
            return p['role']
    share = {'type': 'domain', 'domain': domain, 'role': 'commenter', 'allowFileDiscovery': False}
    call(f'https://www.googleapis.com/drive/v3/files/{doc_id}/permissions?sendNotificationEmail=false',
         json.dumps(share).encode(), 'POST', {'Content-Type': 'application/json'})
    return share['role']


def title_of(src: Path) -> str:
    if src.suffix == '.docx':
        return src.stem
    heads = []
    for line in src.read_text(encoding='utf-8').splitlines():
        if line.startswith('# '):
            heads.append(line[2:].strip())
        elif line.strip():
            break
    return ''.join(heads) or src.stem       # two title lines: topic + the words for "minutes"


def write_record(sidecar: Path, rec: dict):
    sidecar.write_text(json.dumps(rec, indent=2, ensure_ascii=False))


def main():
    src = Path(sys.argv[1])
    sidecar = sidecar_for(src)
    AUTH['Authorization'] = 'Bearer ' + access_token()

    if '--accept-current' in sys.argv:
        rec = json.loads(sidecar.read_text())
        now = modified_time(rec['id'])
        text_now = sha(export_text(rec['id']))
        if rec.get('pulled_modifiedTime') != now or rec.get('pulled_sha256') != text_now:
            sys.exit('STOP: the Doc changed after the last pull (or was never pulled). '
                     'Pull it again with gdoc_to_md.py and merge before accepting.')
        rec.update(sha256=text_now, modifiedTime=now)
        write_record(sidecar, rec)
        print('baseline updated to the pulled version')
        return

    if src.suffix == '.docx':
        docx_path = src
    else:
        sys.path.insert(0, str(Path(__file__).parent))
        from md_to_docx import build
        docx_path = build(src, Path(tempfile.mkdtemp()) / (src.stem + '.docx'))
    content = docx_path.read_bytes()

    fields = 'id,name,webViewLink,owners(emailAddress),parents'
    if '--update' in sys.argv:
        if not sidecar.exists():
            sys.exit(f'no {sidecar.name}; create the Doc first')
        rec = json.loads(sidecar.read_text())
        doc_id = rec['id']
        if modified_time(doc_id) != rec.get('modifiedTime') or sha(export_text(doc_id)) != rec['sha256']:
            sys.exit('STOP: the Doc changed since the last upload (someone edited it). Pull it with '
                     'gdoc_to_md.py into a separate file, merge, run --accept-current, then --update.')
        if open_comments(doc_id):
            sys.exit('STOP: the Doc has open comments; overwriting would detach them. Ask the user how to handle them.')
        meta = {}
        url = f'https://www.googleapis.com/upload/drive/v3/files/{doc_id}?uploadType=multipart&fields={fields}'
        method = 'PATCH'
    else:
        if sidecar.exists():
            sys.exit(f'STOP: {sidecar.name} already exists; this minutes already has a Doc. Use --update.')
        if len(sys.argv) < 3 or sys.argv[2].startswith('--'):
            sys.exit('create mode needs a Drive folder name or id')
        meta = {'name': title_of(src), 'mimeType': DOC_MIME, 'parents': [find_folder(sys.argv[2])]}
        url = f'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields={fields}'
        method = 'POST'

    boundary = uuid.uuid4().hex
    payload = (f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n'
               f'--{boundary}\r\nContent-Type: {DOCX_MIME}\r\n\r\n').encode() + content + f'\r\n--{boundary}--'.encode()
    doc = call(url, payload, method, {'Content-Type': f'multipart/related; boundary={boundary}'})
    # keep what the record already holds (mail log, pull marks) and only refresh the upload fields
    rec = {**(json.loads(sidecar.read_text()) if sidecar.exists() else {}),
           'id': doc['id'], 'url': doc['webViewLink'], 'sha256': '', 'modifiedTime': ''}
    write_record(sidecar, rec)                      # written at once so a failed step below cannot cause a duplicate

    if method == 'POST':
        domain = company_domain((doc.get('owners') or [{}])[0].get('emailAddress', ''))
        if not domain:
            print('NOT SHARED: no company domain (personal Google account, or share_domain set to none); the user shares the Doc by hand')
        else:
            try:
                print(f'SHARED {domain} as {share_with_company(doc["id"], domain)}')
            except urllib.error.HTTPError as err:
                print(f'NOT SHARED with {domain} (HTTP {err.code}); the Doc is created, the user shares it by hand')
    readback = export_text(doc['id'])
    rec.update(sha256=sha(readback), modifiedTime=modified_time(doc['id']))
    write_record(sidecar, rec)

    owners = [o['emailAddress'] for o in doc.get('owners', [])]
    if OWNER and OWNER not in owners:
        print(f'WARNING: owner is {owners}, expected {OWNER}')
    print(json.dumps(doc, ensure_ascii=False))
    print(f'READBACK {len(readback)} chars')
    print(readback[:300])


if __name__ == '__main__':
    main()
