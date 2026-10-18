"""What the scripts did, for finding out later why something went wrong: ~/Library/Logs/Vinutes/scripts.log on a Mac
($MINUTES_HOME/logs/scripts.log elsewhere), beside the app's app.log and captions.log.

Each run is two lines, its start and its end: the script, its command and the meeting folder, how long it took, how
it ended, and on a crash the last lines of the traceback. Never what the user typed, the transcript, the minutes or
mail text and addresses. Steps inside a write-up stay in the meeting's own log.txt (auto_minutes.py).
The file is kept under 5 MB; past that it becomes scripts.log.1 (replacing the one before), so it never takes more
than 10 MB.

    vlog.run(main)     in a script's `if __name__ == '__main__':`, instead of main()
    vlog.log(line)     one more line
"""
from __future__ import annotations

import os
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

LIMIT = 5_000_000
NAME = 'scripts.log'
ADDRESS = re.compile(r'[\w.+-]+@[\w-]+(\.[\w-]+)+')
# asked every few seconds by the open window: logged only when they fail
QUIET = {'refresh', 'list', 'version', 'log', 'locate'}


def folder() -> Path:
    if os.environ.get('VINUTES_LOG_DIR'):                 # the tests keep their runs out of the real log
        return Path(os.environ['VINUTES_LOG_DIR'])
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Logs' / 'Vinutes'
    return Path(os.environ.get('MINUTES_HOME') or Path.home() / '.config' / 'vin-meeting-minutes-zh') / 'logs'


def log(line: str):
    try:
        where = folder()
        where.mkdir(parents=True, exist_ok=True)
        file = where / NAME
        if file.exists() and file.stat().st_size > LIMIT:
            os.replace(file, where / (NAME + '.1'))
        stamp = datetime.now().astimezone().isoformat(timespec='milliseconds')
        line = ADDRESS.sub('<address>', line)            # a message may name a recipient: never an address here
        text = f'[{stamp}] {Path(sys.argv[0]).stem}[{os.getpid()}] {line}\n'
        fd = os.open(file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)   # whole lines beside other processes
        try:
            os.write(fd, text.encode('utf-8'))
        finally:
            os.close(fd)
    except Exception:
        pass                                          # a log that can't be written must never stop the work


def what() -> str:
    """The command and the meeting folder (recordings/20261017-153005 -> 20261017-153005); other arguments are
    the user's own words (a request, a name, a subject) and stay out."""
    args = sys.argv[1:]
    parts = []
    if args:
        parts.append(Path(args[0]).name if args[0].startswith('/') else args[0][:40])
    if len(args) > 1 and args[1].startswith('/'):
        parts.append(Path(args[1]).name)
    return ' '.join(parts)


def run(main):
    began = time.time()
    quiet = bool(sys.argv[1:]) and sys.argv[1] in QUIET
    if not quiet:
        log('start ' + what())
    try:
        main()
    except SystemExit as stop:
        code = stop.code
        took = time.time() - began
        if code in (None, 0):
            if not quiet:
                log(f'end ok, {took:.1f} s')
        else:
            said = ((str(code).strip().splitlines() or [''])[-1][:300]) if not isinstance(code, int) else f'exit {code}'
            log(f'end failed, {took:.1f} s: {what()}: {said}')
        raise
    except BaseException as err:
        lines = traceback.format_exception(type(err), err, err.__traceback__)
        log(f'end crashed, {time.time() - began:.1f} s: {what()}: {err.__class__.__name__}: {str(err)[:300]}\n'
            + ''.join(lines[-6:]).rstrip())
        raise
    if not quiet:
        log(f'end ok, {time.time() - began:.1f} s')
