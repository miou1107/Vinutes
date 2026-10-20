"""A transcript by a bigger Whisper (large-v3, not turbo) as the judge, and how far every other transcript in the
folder is from it. The judge is a Whisper too, so it is fair between two Whisper runs and only indicative for
another recogniser.

  python docs/bench/judge.py <out folder> [names...]      needs job/*.caf from pieces.py; writes C.txt, judge.json
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import compare, say, whisper  # noqa: E402

JUDGE = 'mlx-community/whisper-large-v3-mlx'


def main():
    out = Path(sys.argv[1]).expanduser()
    names = sys.argv[2:] or ['A', 'A2', 'B', 'agc', 'denoise', 'qwen', 'sense']
    caf = next((out / 'job').glob('*.caf'))
    if not (out / 'C.txt').exists():
        say(f'C: {out.name} with {JUDGE}')
        began = time.time()
        whisper(caf, out / 'C.txt', model=JUDGE)
        say(f'judge took {time.time() - began:.0f}s')
    result = {}
    for name in names:
        if (out / f'{name}.txt').exists():
            result[name] = compare(out / 'C.txt', out / f'{name}.txt')['changed_pct']
            say(f'judge vs {name}: {result[name]}% of the judge\'s characters differ')
    (out / 'judge.json').write_text(json.dumps(result, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
