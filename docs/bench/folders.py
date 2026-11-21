"""Do project folders make the minutes better? (issue #2)

Writes a past meeting's minutes again, several times with and several times without the project folders, and
scores every run against the minutes as they were sent, the way the window's score is made (scores.py edits).

Nothing of the user's is changed, and the AI never sees the minutes it is scored against. Each run works on
copies in a bench folder of its own:
- the settings folder ($MINUTES_HOME) is copied without recordings, models and the venv, and the copy is what
  the run reads, so briefs.json can be changed there; the Google sign-in files in the copies are removed at the end;
- of the meeting only what the writer reads at first is copied: job.json, the transcript and the speakers. The
  sent minutes, the mail, the AI's first draft and the score stay where they are;
- project folders are copied with the files the app would read (project_folders.KINDS and its limit on one
  file), and only those that existed before the meeting started (created and last changed before it); the
  earlier minutes the same way, and the list of recent meetings holds only earlier ones, with the user's own
  project for each.

What the bench cannot take back: the speakers' names and the project briefs, glossary and rules are as they are
today, so they may hold what was learned from this very meeting. Both conditions get the same, so the
difference between them is still the folders'; both scores come out a little higher than at the time.

  folders.py <bench folder> <meeting folder>... [--runs 3]

prints and writes <bench folder>/scores.json: for each meeting, the scores of the runs without and with folders.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from common import PY, SCRIPTS, say

sys.path.insert(0, str(SCRIPTS))
import project_folders  # noqa: E402  (the app's own rules for which files of a folder are read)

LIVE = Path(os.environ.get('MINUTES_HOME') or '~/.config/vin-meeting-minutes-zh').expanduser()
LEAVE = {'recordings', 'models', 'venv', 'folder-text', 'usage', 'voices'}
JOB_FILES = ('job.json', '逐字稿.txt', '逐字稿.json', '講者.json')
CHOSEN = '分類.json'                 # the project the user picked for a meeting
SIGN_IN = ('google-token.json', 'google-access.json', 'oauth-client.json')
MINUTES_DIR = '~/會議紀錄'    # the app's default folder of minutes
SENT = '定稿.md'                      # the minutes as sent, as scores.py names them for the AI


def existed(st: os.stat_result, cutoff: float) -> bool:
    """Created and last changed before cutoff: a file copied or synced in later often keeps an older change time."""
    return max(st.st_mtime, getattr(st, 'st_birthtime', 0)) < cutoff


def before(src: Path, dest: Path, cutoff: float):
    """The files of src the app would read and that existed before cutoff, into dest with the same subfolders."""
    library = Path.home() / 'Library'
    for root, dirs, names in os.walk(src):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in project_folders.SKIP
                   and Path(root) / d != library]
        for name in names:
            f = Path(root) / name
            if name.startswith(('.', '~$')) or f.suffix.lower() not in project_folders.KINDS:
                continue
            try:
                st = f.lstat()
                if f.is_symlink() or not 0 < st.st_size <= project_folders.MOST_FILE or not existed(st, cutoff):
                    continue
                target = dest / f.relative_to(src)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
            except OSError:
                continue


def home(bench: Path, job: Path, cutoff: float, with_folders: bool) -> Path:
    """A settings folder for one condition of one meeting."""
    h = bench / job.name / ('folders' if with_folders else 'none') / 'home'
    shutil.rmtree(h.parent, ignore_errors=True)
    h.mkdir(parents=True)
    for item in LIVE.iterdir():
        if item.name in LEAVE or item.name.endswith('.bak'):
            continue
        (shutil.copytree if item.is_dir() else shutil.copy2)(item, h / item.name)
    briefs = json.loads((h / 'briefs.json').read_text(encoding='utf-8'))
    for i, brief in enumerate(briefs.values()):
        if not isinstance(brief, dict):
            continue
        folder = brief.get('folder') or ''
        snap = ''
        if with_folders and folder and Path(folder).is_dir():
            snap = h.parent / 'snapshots' / f'p{i}'
            before(Path(folder), snap, cutoff)
        brief['folder'] = str(snap)
    (h / 'briefs.json').write_text(json.dumps(briefs, ensure_ascii=False, indent=1), encoding='utf-8')
    settings = json.loads((h / 'settings.json').read_text(encoding='utf-8')) if (h / 'settings.json').is_file() else {}
    earlier = Path(settings.get('auto_folder') or MINUTES_DIR).expanduser()
    old = h.parent / 'earlier-minutes'
    old.mkdir()
    for f in earlier.glob('*.md') if earlier.is_dir() else []:
        if existed(f.stat(), cutoff):
            shutil.copy2(f, old / f.name)
    settings['auto_folder'] = str(old)
    (h / 'settings.json').write_text(json.dumps(settings, ensure_ascii=False, indent=1), encoding='utf-8')
    return h


def copy_job(h: Path, job: Path, n: int) -> Path:
    """The meeting for run n, in a recordings folder of its own beside the earlier meetings' results only, so
    another run's copy of the same meeting never shows up in the list of recent meetings."""
    rec = h.parent / f'run{n}'
    shutil.rmtree(rec, ignore_errors=True)
    rec.mkdir()
    for other in (LIVE / 'recordings').iterdir():
        if other.name < job.name and (other / 'result.json').is_file():
            (rec / other.name).mkdir()
            for name in ('result.json', CHOSEN):
                if (other / name).is_file():
                    shutil.copy2(other / name, rec / other.name / name)
    dest = rec / job.name
    dest.mkdir()
    for name in JOB_FILES:
        if (job / name).is_file():
            shutil.copy2(job / name, dest / name)
    return dest


RUN = r'''
import json, sys
from pathlib import Path
import auto_minutes as am, scores
job, key, out, sent = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
meta = am.read_json(job / 'job.json')
folder = Path(am.setting('auto_folder', 'MINUTES_AUTO_FOLDER')).expanduser()
spoken = meta.get('language') or am.spoken_language(job)
lang = am.minutes_lang(spoken)
work = am.gather(job, meta, folder, lang)
am.write_minutes(job, work, meta, folder, lang, spoken)
wrote = (work / am.DRAFT).read_text(encoding='utf-8')
answer, ai = scores.ask(job, 'edits', {scores.ORIGINAL: wrote, sent: key.read_text(encoding='utf-8')})
entry = scores.entry('edits', answer, ai)
entry['copied'] = [l for l in (job / 'log.txt').read_text(encoding='utf-8').splitlines() if 'project folders' in l]
out.write_text(json.dumps(entry, ensure_ascii=False, indent=1), encoding='utf-8')
'''


def one(h: Path, job: Path, key: Path, n: int) -> dict:
    try:
        copy = copy_job(h, job, n)
        out = copy.parent / 'score.json'
        env = {**os.environ, 'MINUTES_HOME': str(h), 'MINUTES_NO_SEND': '1', 'PYTHONPATH': str(SCRIPTS)}
        env.pop('MINUTES_AUTO_FOLDER', None)          # it would point the run at the live minutes folder
        done = subprocess.run([PY, '-c', RUN, str(copy), str(key), str(out), SENT], cwd=SCRIPTS, env=env,
                              capture_output=True, text=True, timeout=60 * 60)
        if done.returncode or not out.is_file():
            say(f'{job.name} {h.parent.name} run {n} failed: {(done.stderr or done.stdout)[-400:]}')
            return {}
        entry = json.loads(out.read_text(encoding='utf-8'))
    except Exception as err:                          # one run's trouble never costs the others
        say(f'{job.name} {h.parent.name} run {n} failed: {err!r}')
        return {}
    say(f'{job.name} {h.parent.name} run {n}: {entry["score"]} {entry["categories"]} {entry.get("copied")}')
    return entry


def main():
    args = sys.argv[1:]
    runs = int(args[args.index('--runs') + 1]) if '--runs' in args else 3
    rest = [a for i, a in enumerate(args) if not a.startswith('--') and not (i and args[i - 1] == '--runs')]
    bench, jobs = Path(rest[0]).expanduser().resolve(), [Path(a).expanduser() for a in rest[1:]]
    if bench == LIVE.resolve() or LIVE.resolve() in bench.parents:
        sys.exit('the bench folder must be outside the settings folder')
    bench.mkdir(parents=True, exist_ok=True)
    tasks, entries = [], []
    for job in jobs:                                  # one meeting at a time: a later meeting's copies hold the
        meta = json.loads((job / 'job.json').read_text(encoding='utf-8'))      # earlier one's sent minutes, so
        cutoff = datetime.fromisoformat(meta['started']).timestamp()          # they are gone before it runs
        key = Path(json.loads((job / 'result.json').read_text(encoding='utf-8'))['minutes_md'])
        homes = [home(bench, job, cutoff, with_folders) for with_folders in (False, True)]
        mine = [(h, job, key, n) for h in homes for n in range(1, runs + 1)]
        try:
            with ThreadPoolExecutor(3) as pool:
                entries += list(pool.map(lambda t: one(*t), mine))
        finally:
            for h in homes:
                shutil.rmtree(h.parent / 'snapshots', ignore_errors=True)
                shutil.rmtree(h.parent / 'earlier-minutes', ignore_errors=True)
                for name in SIGN_IN:
                    (h / name).unlink(missing_ok=True)
        tasks += mine
    result = {}
    for (h, job, _, _), e in zip(tasks, entries):
        result.setdefault(job.name, {}).setdefault(h.parent.name, []).append(e.get('score'))
    (bench / 'scores.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
    for name, by in result.items():
        say(f'{name}: ' + ', '.join(f'{k} {v}' for k, v in by.items()))


if __name__ == '__main__':
    main()
