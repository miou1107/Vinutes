"""Where two transcripts of the same recording differ: per five-minute stretch, the characters in each and how
much of the text changed, and the lines around each piece cut side by side. A difference that sits at the cuts
shows up against the model's own run-to-run noise (A vs A2).

  python docs/bench/breakdown.py <out folder> [first second ...]     default A B, plus A2 when it exists
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import changed_pct, lines  # noqa: E402


def bucket(ls, lo, hi) -> str:
    return ''.join(t for s, t in ls if lo <= s < hi)


def main():
    folder = Path(sys.argv[1]).expanduser()
    names = sys.argv[2:] or ['A', 'B'] + (['A2'] if (folder / 'A2.txt').exists() else [])
    first, others = names[0], names[1:]
    texts = {n: lines(folder / f'{n}.txt') for n in names}
    end = max(s for ls in texts.values() for s, _ in ls) + 1
    width = 300
    print(f'{"minutes":>10} {"chars " + first:>10}' + ''.join(f' {"chars " + n:>10} {first + "/" + n + " %":>9}' for n in others))
    for lo in range(0, end, width):
        a = bucket(texts[first], lo, lo + width)
        row = f'{lo // 60:>4}-{min(lo + width, end) // 60:<5} {len(a):>10}'
        for n in others:
            b = bucket(texts[n], lo, lo + width)
            row += f' {len(b):>10} {changed_pct(a, b):>9}'
        print(row)
    try:
        cuts = json.loads((folder / 'report.json').read_text(encoding='utf-8')).get('B_piece_ends', [])
    except (OSError, ValueError):
        cuts = []
    for cut in cuts:
        lo, hi = cut - 25, cut + 25
        print(f'\n--- cut at {int(cut) // 60}:{int(cut) % 60:02d} ---')
        for n in names:
            print(f'{n}: ' + ' / '.join(t for s, t in texts[n] if lo <= s < hi))


if __name__ == '__main__':
    main()
