"""Whether the voice prints made during a recording (speakers.piece_prints, v0.4.20) are the prints made after
Stop, and how much time they take off after Stop, on a meeting already recorded on this Mac.

The meeting's audio is decoded once (its CAF file if it is still there, else its AAC copy, so the samples of both
paths are the same decoded ones); each piece is cut where the recording's pieces were cut (the times in its log.txt)
and printed as live_transcribe.py prints it, with its threads; then speakers.prints runs over the whole recording
with those prints and without them, and the two results are compared line by line, grouped with the user's kept
voices. That the helper's raw CAF samples are the ones afconvert gives after Stop is tested in tests/test_live.py.

Usage:
  ~/.config/vin-meeting-minutes-zh/venv/bin/python docs/bench/live_voices.py <job folder> <out folder> <cuts>
  cuts: the pieces' starts and the last one's end in seconds, e.g. 0,320,646
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import speakers  # noqa: E402
from live_transcribe import VOICE_THREADS  # noqa: E402


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    job, out = Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser()
    cuts = [float(c) for c in sys.argv[3].split(',')]
    out.mkdir(parents=True, exist_ok=True)
    wav = out / 'a.wav'
    audio = next(job.glob('*.caf'), None) or next(job.glob('*.m4a'))
    subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', str(audio), str(wav)], check=True)
    pcm, rate = sf.read(str(wav), dtype='int16')
    spans = speakers.lines_of(job)
    model, live = speakers.extractor(), speakers.extractor(threads=VOICE_THREADS)

    known, took = {}, []
    for a, b in zip(cuts, cuts[1:]):                 # each piece as live_transcribe.py reads it from the CAF file
        samples = pcm[round(a * rate):round(b * rate)].astype(np.float32) / 32768.0
        began = time.time()
        S, V, ok = speakers.piece_prints(samples, a, [s for s in spans if a <= s[0] < b], live)
        took.append(time.time() - began)
        known.update({speakers.key(x, y): (v, bool(g)) for (x, y), v, g in zip(S, V, ok)})

    began = time.time()
    V1, ok1 = speakers.prints(wav, spans, known, model)
    after = time.time() - began
    began = time.time()
    V0, ok0 = speakers.prints(wav, spans, None, model)
    whole = time.time() - began
    people = speakers.library()
    with_live, without = speakers.label(V1, ok1, spans, people), speakers.label(V0, ok0, spans, people)

    print(f'{len(spans)} lines, {sum(1 for s in spans if speakers.key(*s) in known)} printed during the recording')
    print('seconds per piece:', ', '.join(f'{s:.1f}' for s in took))
    print(f'after Stop: {after:.1f} s, against {whole:.1f} s for every line')
    print(f'largest difference between the prints: {float(np.abs(V1 - V0).max())}, '
          f'same lines printable: {bool((ok1 == ok0).all())}')
    print('same speaker on every line:', with_live['lines'] == without['lines'])


if __name__ == '__main__':
    main()
