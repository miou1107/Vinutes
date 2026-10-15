"""Files, links and pictures added from the box under the Doc go into the minutes' last section, 「八、補充資訊」,
one line each, as SKILL.md §3 writes it: who gave it and what it is, then the link.

Files and pictures are uploaded to the user's Google Drive, into a folder of this meeting's own beside its Doc
(「<Doc name>_附件」, shared with the company the way the Doc is). A picture also shows in the Doc under its line,
and a copy is kept beside the minutes (「<minutes>_附件/」) so the Word file has it as well.

The Docs API only takes a picture from an address anyone can open. The uploaded picture is opened to anyone with its
link for the second the Doc takes to copy it, and closed again; where the Google account does not allow that, the
line keeps its link and the picture does not show in the Doc. A picture goes into the Doc only on the revision the
minutes were just synced with (minutes_app.place_pictures), so a colleague's typing is never taken for the app's;
until then it waits in the meeting's state and goes in after the next sync.
"""
from __future__ import annotations

import json
import mimetypes
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

import doc_sync

SECTION = '## 八、補充資訊'
UPLOAD = 'https://www.googleapis.com/upload/drive/v3/files'
FOLDER_MIME = 'application/vnd.google-apps.folder'
PICTURES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif'}
WIDEST_PT = 400                                  # a picture in the Doc is never wider than this (the text is ~450)
LONGEST_PX = 4000                                # the Doc refuses pictures over 25 megapixels or 50 MB
ALL_DRIVES = 'supportsAllDrives=true'            # a Doc on a shared drive keeps its folder there too

NO_ITEMS = '沒有要加進去的檔案、連結或圖片。'
NO_DOC = '這場會議還沒有 Google 文件，附件和圖片要等會議記錄發成 Google 文件之後才能加。'
OFFLINE = '沒有連上 Google，檔案和圖片沒辦法存進雲端硬碟，第八章沒有變動。連上網路之後再試一次。'
NO_PUBLIC = ('圖片沒辦法直接顯示在 Google 文件裡，因為你的 Google 帳號不允許用連結分享檔案。'
             '圖片已經存進雲端硬碟，第八章放的是圖片的連結。')
LOGIN = 'Google 登入已經失效，檔案沒有存進雲端硬碟，第八章沒有變動。請到「環境設定自檢」的第 7 項重新登入。'
NO_RIGHT = '你的 Google 帳號沒有權限把檔案存進這份文件所在的資料夾，第八章沒有變動。'
FAILED = '檔案沒辦法存進雲端硬碟，第八章沒有變動。請再試一次。'
CROWDED = '同事剛好也在修改 Google 文件，這次的檔案和連結沒有加進第八章。檔案已經存進雲端硬碟，請再加一次。'
NO_LINE = '第八章找不到「{name}」這一行，這張圖片沒有放進 Google 文件。'
NOT_PLACED = '圖片「{name}」沒辦法放進 Google 文件，第八章放的是這張圖片的連結。'


def drive_trouble(err) -> str:
    """What went wrong with Drive, in words for the window; nothing has changed in the minutes yet."""
    text = str(err)
    if text.startswith('OFFLINE'):
        return OFFLINE
    if re.search(r'GOOGLE LOGIN EXPIRED|NO GOOGLE LOGIN|HTTP 401', text):
        return LOGIN
    if 'HTTP 403' in text:
        return NO_RIGHT
    return FAILED if re.match(r'HTTP \d+', text) else text


def items_from(raw: str) -> list[dict]:
    """What the window sent: [{kind: file|image, path}] and [{kind: link, url}], checked before anything is
    uploaded, so a bad one leaves nothing half done."""
    try:
        items = json.loads(raw)
    except ValueError:
        items = None
    if not isinstance(items, list) or not items:
        raise SystemExit(NO_ITEMS)
    checked = []
    for it in items:
        kind = it.get('kind') if isinstance(it, dict) else None
        if kind in ('file', 'image'):
            path = Path(str(it.get('path', ''))).expanduser()
            if not path.is_file():
                raise SystemExit(f'找不到這個檔案：{path.name or "（沒有檔名）"}。')
            checked.append({'kind': kind, 'path': path, 'name': path.name})
        elif kind == 'link':
            url = str(it.get('url', '')).strip()
            if not re.match(r'https?://\S+$', url):
                raise SystemExit('網址要用 http:// 或 https:// 開頭。')
            checked.append({'kind': 'link', 'url': url, 'name': url})
    if not checked:
        raise SystemExit(NO_ITEMS)
    return checked


# --- Google Drive --------------------------------------------------------------------------------------------

def call(url: str, body=None, method: str | None = None, ctype: str = 'application/json', want: str = 'json'):
    """A Drive call with the app's Google login; urllib errors come back as doc_sync's SystemExit words."""
    import socket
    import urllib.error
    import urllib.request
    doc_sync.authorize()
    if url.startswith(('https://www.googleapis.com/drive/', UPLOAD)) and ALL_DRIVES not in url:
        url += ('&' if '?' in url else '?') + ALL_DRIVES
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    headers = {**doc_sync.AUTH, **({'Content-Type': ctype} if data is not None else {})}
    if hasattr(data, 'read'):
        headers['Content-Length'] = str(Path(data.name).stat().st_size)
    req = urllib.request.Request(url, data=data, method=method or ('POST' if data is not None else 'GET'),
                                 headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=600)
    except urllib.error.HTTPError as err:
        raise SystemExit(f'HTTP {err.code} from Google: {err.read().decode(errors="replace")[:300]}') from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as err:
        raise SystemExit(f'OFFLINE: Google did not answer ({err})') from None
    if want == 'location':
        return resp.headers.get('Location', '')
    raw = resp.read()
    return json.loads(raw) if raw else {}


def folder_for(state: dict, doc_id: str) -> str:
    """This meeting's folder on Drive, beside its Doc: made the first time, then remembered in `state`."""
    known = state.get('attach_folder')
    if known:
        try:
            if not call(doc_sync.DRIVE + known + '?fields=trashed').get('trashed'):
                return known
        except SystemExit as err:
            if 'HTTP 404' not in str(err):
                raise
    doc = call(doc_sync.DRIVE + doc_id + '?fields=name,parents')
    parent = (doc.get('parents') or ['root'])[0]
    name = f'{doc.get("name") or "會議紀錄"}_附件'
    q = (f"name = '{name.replace(chr(39), chr(92) + chr(39))}' and mimeType = '{FOLDER_MIME}' "
         f"and '{parent}' in parents and trashed = false")
    found = call(doc_sync.DRIVE.rstrip('/') + '?fields=files(id)&includeItemsFromAllDrives=true&q='
                 + urllib.parse.quote(q)).get('files', [])
    if found:
        folder = found[0]['id']
    else:
        folder = call(doc_sync.DRIVE.rstrip('/') + '?fields=id', {'name': name, 'mimeType': FOLDER_MIME,
                                                                 'parents': [parent]})['id']
        # whoever the Doc is shared with as a company can open what it links to
        perms = call(doc_sync.DRIVE + doc_id + '/permissions?fields=permissions(type,domain)').get('permissions', [])
        for p in perms:
            if p.get('type') == 'domain' and p.get('domain'):
                call(doc_sync.DRIVE + folder + '/permissions?sendNotificationEmail=false',
                     {'type': 'domain', 'domain': p['domain'], 'role': 'reader', 'allowFileDiscovery': False})
    state['attach_folder'] = folder
    return folder


def upload(path: Path, folder: str, name: str, mime: str = 'application/octet-stream') -> dict:
    """One file into the folder, in one piece of any size (Drive's resumable upload); {id, link}."""
    where = call(f'{UPLOAD}?uploadType=resumable&fields=id,webViewLink',
                 {'name': name, 'parents': [folder]}, 'POST', 'application/json; charset=UTF-8', want='location')
    if not where:
        raise SystemExit('HTTP 500 from Google: no upload address')
    with path.open('rb') as fh:
        done = call(where, fh, 'PUT', mime)
    return {'id': done['id'], 'link': done.get('webViewLink') or f'https://drive.google.com/file/d/{done["id"]}/view'}


def picture_size(path: Path) -> tuple[int, int]:
    done = subprocess.run(['sips', '-g', 'pixelWidth', '-g', 'pixelHeight', str(path)], capture_output=True, text=True)
    w, h = (re.search(rf'{k}:\s*(\d+)', done.stdout) for k in ('pixelWidth', 'pixelHeight'))
    return (int(w.group(1)), int(h.group(1))) if w and h else (0, 0)


def doc_ready_picture(path: Path, work: Path) -> Path:
    """A picture the Doc can show: PNG, JPEG and GIF as they are, anything else macOS can open as a JPEG, and a
    photo too big for the Doc made smaller (the copy in Drive is this one too)."""
    w, h = picture_size(path)
    if not w:
        raise SystemExit(f'「{path.name}」不是圖片，請改用「上傳檔案」加進去。')
    big = w * h > 20_000_000 or path.stat().st_size > 40_000_000
    if path.suffix.lower() in PICTURES and not big:
        return path
    out = work / (path.stem + (path.suffix.lower() if path.suffix.lower() in PICTURES else '.jpg'))
    cmd = ['sips'] + (['-Z', str(LONGEST_PX)] if big else []) + \
          ([] if path.suffix.lower() in PICTURES else ['-s', 'format', 'jpeg']) + [str(path), '--out', str(out)]
    done = subprocess.run(cmd, capture_output=True)
    if done.returncode or not out.is_file():
        raise SystemExit(f'「{path.name}」沒辦法轉成 Google 文件能顯示的圖片格式。')
    return out


def width_pt(path: Path) -> int:
    """How wide the picture shows in the Doc: its own size, at most WIDEST_PT."""
    w, _ = picture_size(path)
    return min(WIDEST_PT, max(40, int(w * 0.75))) if w else WIDEST_PT


def mime_of(path: Path) -> str:
    return PICTURES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or 'application/octet-stream'


def show_picture(doc_id: str, doc: dict, file_id: str, width: int) -> dict:
    """The uploaded picture in `doc` (read with suggestions in place, on the revision just synced), in a paragraph
    of its own right after the line that links to it. {'revision': the Doc's revision afterwards} when it went in;
    else {'why': 'line' (no line links to it), 'shared' (the account does not share by link) or 'refused'};
    'open' names a link permission that could not be closed again."""
    end = None
    for el in doc.get('body', {}).get('content', []):
        links = [e.get('textRun', {}).get('textStyle', {}).get('link', {}).get('url', '')
                 for e in el.get('paragraph', {}).get('elements', [])]
        if any(file_id in link for link in links):
            end = el['endIndex'] - 1                  # before the line's own newline
    if end is None:
        return {'why': 'line'}
    try:
        opened = call(doc_sync.DRIVE + file_id + '/permissions?fields=id', {'type': 'anyone', 'role': 'reader'})
    except SystemExit:
        return {'why': 'shared'}
    own = {'startIndex': end + 1, 'endIndex': end + 2}  # the new paragraph: not a list item, not indented
    result: dict = {}
    try:
        done = doc_sync.batch_update(doc_id, [
            {'insertText': {'location': {'index': end}, 'text': '\n'}},
            {'deleteParagraphBullets': {'range': own}},
            {'updateParagraphStyle': {'range': own, 'fields': 'indentStart,indentFirstLine', 'paragraphStyle': {
                'indentStart': {'magnitude': 0, 'unit': 'PT'}, 'indentFirstLine': {'magnitude': 0, 'unit': 'PT'}}}},
            {'insertInlineImage': {'location': {'index': end + 1},
                                   'uri': f'https://drive.google.com/uc?export=view&id={file_id}',
                                   'objectSize': {'width': {'magnitude': width, 'unit': 'PT'}}}},
        ], doc.get('revisionId'))
        result['revision'] = (done.get('writeControl') or {}).get('requiredRevisionId', '')
    except SystemExit:
        result['why'] = 'refused'
    finally:
        if not close_link(file_id, opened.get('id', 'anyoneWithLink')):
            result['open'] = {'file': file_id, 'perm': opened.get('id', 'anyoneWithLink')}
    return result


def throw_away(file_ids: list[str]):
    """Files uploaded for lines that did not get into the minutes: to Drive's trash, so adding them again does not
    leave two of each."""
    for file_id in file_ids:
        try:
            call(doc_sync.DRIVE + file_id + '?fields=id', {'trashed': True}, 'PATCH')
        except SystemExit:
            pass


def close_link(file_id: str, perm: str) -> bool:
    """The picture's 'anyone with the link' closed again; False when Google could not be told this time."""
    try:
        call(doc_sync.DRIVE + file_id + '/permissions/' + perm, None, 'DELETE')
        return True
    except SystemExit as err:
        return 'HTTP 404' in str(err)              # already gone


# --- the minutes ---------------------------------------------------------------------------------------------

def link_text(text: str) -> str:
    return doc_sync.escape_md(text).replace('[', '\\[').replace(']', '\\]')


def link_target(url: str) -> str:
    return url.replace(' ', '%20').replace('(', '%28').replace(')', '%29')


def lines_for(items: list[dict], note: str) -> list[str]:
    """One list item per file, link or picture; a picture's own paragraph follows its line."""
    lead = f'{doc_sync.escape_lead(link_text(note.strip()))}：' if note.strip() else ''
    out = []
    for it in items:
        out.append(f'- {lead}[{link_text(it["name"])}]({link_target(it["link"])})')
        if it['kind'] == 'image' and it.get('local'):
            out.append(f'![{link_text(it["name"])}]({link_target(it["local"])})')
    return out


def add_lines(md: str, lines: list[str]) -> str:
    """The lines at the end of 「八、補充資訊」, the section made at the end of the minutes when it is missing."""
    rows = md.rstrip('\n').split('\n')
    head = next((i for i, r in enumerate(rows) if re.match(r'##\s*八、', r)), None)
    block: list[str] = []
    for line in lines:                               # a picture is a paragraph of its own: blank lines around it
        if line.startswith('!['):
            block += ['', line, '']
        else:
            block.append(line)
    if head is None:
        return '\n'.join(rows + ['', SECTION, ''] + block).rstrip('\n') + '\n'
    end = next((i for i in range(head + 1, len(rows)) if re.match(r'#{1,2}\s', rows[i])), len(rows))
    while end > head + 1 and not rows[end - 1].strip():
        end -= 1
    after_picture = rows[end - 1].startswith('![')
    joined = rows[:end] + ([''] if end == head + 1 or after_picture else []) + block + rows[end:]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(joined)).rstrip('\n') + '\n'


def keep_beside(minutes: Path, picture: Path) -> str:
    """A copy of the picture beside the minutes, for the Word file; its path as the Markdown writes it."""
    folder = minutes.with_name(minutes.stem + '_附件')
    folder.mkdir(exist_ok=True)
    target, n = folder / picture.name, 2
    while target.exists() and target.read_bytes() != picture.read_bytes():
        target, n = folder / f'{picture.stem}-{n}{picture.suffix}', n + 1
    if not target.exists():
        shutil.copy2(picture, target)
    return f'{folder.name}/{target.name}'
