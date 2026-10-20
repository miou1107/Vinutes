"""The whole recording at once (A) against pieces as during a recording plus the rest after Stop (B), both with
the app's own Whisper. With --twice, A is run a second time (A2) to see how much the model moves on its own.

  python docs/bench/pieces.py <recording.m4a|caf> <out folder> [--twice]

Writes A.txt, B.txt (A2.txt), the pieces, A_vs_B.diff and report.json with the timings. Run it with the app's
Python (~/.config/vin-meeting-minutes-zh/venv/bin/python), which has mlx-whisper.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import SCRIPTS, compare, say, whisper  # noqa: E402

sys.path.insert(0, str(SCRIPTS))


def main():
    src, out = Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser()
    twice = '--twice' in sys.argv
    out.mkdir(parents=True, exist_ok=True)
    job = out / 'job'
    shutil.rmtree(job, ignore_errors=True)
    job.mkdir()
    import mlx_whisper
    import live_transcribe as live
    runner = live.Runner(job, mlx_whisper.transcribe, log=say)
    caf = runner.audio                                  # the recording's name inside a job, as the app writes it
    pieces_dir = job / live.PIECES
    import subprocess
    say(f'converting {src.name} to CAF')
    subprocess.run(['afconvert', '-f', 'caff', '-d', 'LEI16@16000', '-c', '1', str(src), str(caf)], check=True)
    (job / 'job.json').write_text(json.dumps({'audio': caf.name, 'started': '2026-01-01T10:00:00+08:00', 'ended': None}))
    report = {'source': str(src)}

    say('A: the whole file at once')
    report['A_seconds'] = whisper(caf, out / 'A.txt')
    if twice:
        say('A2: the whole file again')
        report['A2_seconds'] = whisper(caf, out / 'A2.txt')

    say('B: pieces as during the recording')

    def sleep(_):                                       # the file is complete: the first wait is the end of the meeting
        meta = json.loads((job / 'job.json').read_text())
        meta['ended'] = '2026-01-01T11:00:00+08:00'
        (job / 'job.json').write_text(json.dumps(meta))
    runner.sleep = sleep
    n = runner.run()
    pieces = [json.loads(p.read_text()) for p in sorted(pieces_dir.glob('[0-9]*.json'))]
    report['B_pieces'] = n
    report['B_piece_took'] = [p['took'] for p in pieces]
    report['B_piece_ends'] = [p['end'] for p in pieces]
    say(f'B: {n} pieces, up to {runner.cut:.0f}s; now the rest')
    report['B_rest_seconds'] = whisper(caf, out / 'B.txt', pieces_dir)
    shutil.copytree(pieces_dir, out / 'pieces', dirs_exist_ok=True)

    report['A_vs_B'] = {k: v for k, v in compare(out / 'A.txt', out / 'B.txt').items() if k != 'diff'}
    (out / 'A_vs_B.diff').write_text('\n'.join(compare(out / 'A.txt', out / 'B.txt')['diff']), encoding='utf-8')
    if twice:
        report['A_vs_A2'] = {k: v for k, v in compare(out / 'A.txt', out / 'A2.txt').items() if k != 'diff'}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    say(f"done: A {report['A_seconds']:.0f}s, B rest {report['B_rest_seconds']:.0f}s, "
        f"A/B {report['A_vs_B']['changed_pct']}%" + (f", A/A2 {report['A_vs_A2']['changed_pct']}%" if twice else ''))


if __name__ == '__main__':
    main()
