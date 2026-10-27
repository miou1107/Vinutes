"""Each project's folder (專案設定 › 專案資料夾, Vin 2026-10-28), copied for the AI that writes the minutes.

The AI reads only its own folder, so it never sees the project's files themselves and can't change them. Before it
starts, every project's folder is copied into 參考/專案資料夾/<project>/ with the same subfolders: PDF and text files
as they are, Word, Excel and PowerPoint as text (references.read_file), with 檔案清單.md listing what is there,
newest first. The AI decides which project the meeting is and reads what it needs from that project's copy; the copy
is removed once the minutes are written (auto_minutes.run), so a meeting doesn't keep it.

Hidden files and folders, ~/Library, pictures, videos, web pages and anything else that isn't text are left out, and
so is what goes past the limits below (the oldest first). A folder too big to look through (more than MOST_SEEN
entries, e.g. the home folder) gives the newest of what was seen. A file that can't be read is left out; nothing
here stops the minutes. A Word, Excel or PowerPoint file made into text is kept in $MINUTES_HOME/folder-text/ by its
path, size and time, so the next meeting doesn't convert it again.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import references
from google_setup import CONFIG

DIR = '專案資料夾'
LIST = '檔案清單.md'
CACHE = CONFIG / 'folder-text'
OFFICE = {'.doc', '.docx', '.rtf', '.odt', '.xlsx', '.pptx'}      # made into text
KINDS = references.AS_IS | OFFICE
SKIP = {'node_modules', '__pycache__'}
MOST_FILES = 200                 # files from one project's folder
MOST_BYTES = 60_000_000          # of them, as the files on disk
MOST_FILE = 20_000_000           # one file
MOST_SEEN = 20_000               # entries looked at in one folder


def files(folder: Path) -> list[tuple[Path, os.stat_result]]:
    """The folder's files the AI can read with what stat said of them, newest first, within the limits."""
    found, seen = [], 0
    library = Path.home() / 'Library'
    for top, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in SKIP and Path(top) / d != library)
        seen += len(dirs) + len(names)
        for name in names:
            path = Path(top) / name
            if name.startswith(('.', '~$')) or path.suffix.lower() not in KINDS:
                continue
            try:
                st = path.lstat()
            except OSError:
                continue
            if path.is_symlink() or not 0 < st.st_size <= MOST_FILE:
                continue
            found.append((path, st))
        if seen > MOST_SEEN:
            break
    found.sort(key=lambda f: f[1].st_mtime, reverse=True)
    kept, total = [], 0
    for path, st in found:
        if len(kept) >= MOST_FILES or total + st.st_size > MOST_BYTES:
            continue
        kept.append((path, st))
        total += st.st_size
    return kept


def as_text(src: Path, st: os.stat_result, target: Path) -> bool:
    """A Word, Excel or PowerPoint file as text at `target`, from the cache when the file hasn't changed."""
    key = hashlib.sha256(f'{src}\0{st.st_size}\0{st.st_mtime_ns}'.encode()).hexdigest()[:32]
    kept = CACHE / f'{key}.txt'
    if not kept.is_file():
        with tempfile.TemporaryDirectory(prefix='vinutes-folder-') as tmp:
            try:
                name = references.read_file(src, Path(tmp), 'text')
            except (SystemExit, Exception):
                return False
            CACHE.mkdir(parents=True, exist_ok=True)
            fd, part = tempfile.mkstemp(dir=CACHE, suffix='.part')    # another meeting may read it meanwhile
            os.close(fd)
            shutil.copy(Path(tmp) / name, part)
            os.replace(part, kept)
    shutil.copy(kept, target)
    return True


def copy(folder: Path, dest: Path) -> int:
    """One project's folder into `dest` (made only when a file comes); how many files the AI got."""
    rows = []
    for src, st in files(folder):
        try:
            rel = src.relative_to(folder)
            kind = src.suffix.lower()
            target = dest / rel if kind in references.AS_IS else dest / rel.parent / f'{rel.name}.txt'
            if target.exists() or target == dest / LIST:     # foo.docx beside a foo.docx.txt: the newer one
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if kind in references.AS_IS:
                shutil.copy(src, target)
            elif not as_text(src, st, target):
                continue
        except Exception:                            # gone meanwhile, unreadable, a path too long: left out
            continue
        when = datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d')
        shown = '' if target.name == rel.name else f'（文字版：{target.relative_to(dest)}）'
        rows.append(f'- {rel}　{when}　{max(1, st.st_size // 1024)} KB{shown}')
    if rows:
        (dest / LIST).write_text(f'# {folder.name}\n\n使用者的專案資料夾裡 AI 讀得到的檔案，新的在前面。\n\n'
                                 + '\n'.join(rows) + '\n', encoding='utf-8')
    return len(rows)


def place(project: str, taken: set[str]) -> str:
    """The project's folder name under 專案資料夾/: never . or .., and not one another project has (APFS ignores case)."""
    name = project.replace('/', '／').replace(':', '：').strip() or '專案'
    if name in ('.', '..'):
        name = f'專案{name}'
    base, n = name, 2
    while name.casefold() in taken:
        name, n = f'{base} ({n})', n + 1
    taken.add(name.casefold())
    return name


def copy_all(projects: dict[str, Path], ref: Path) -> dict[str, int]:
    """Every project's folder under ref/專案資料夾/; how many files each one got (0 when none could be read)."""
    copied, taken = {}, set()
    for project, folder in projects.items():
        copied[project] = copy(folder, ref / DIR / place(project, taken))
    return copied
