"""How the voice grouping (scripts/speakers.py) does on meetings already recorded on this Mac, against what the
user kept under People: a voice they named is that person, a voice they removed (移除講者 X) was no one, and a
voice left as 講者 X is a person they did not name.

Every recorded meeting keeps its line prints (聲紋.npz), so the grouping is run again from them, without the
prints that meeting itself taught the voice library, and each voice it makes is matched to the person who owns
most of its seconds. Compare two rule sets by editing the constants in speakers.py and running this before and
after; the reference figures are in README.md under "Fewer phantom speakers".

Usage:
  python3 docs/bench/voices.py [how many of the latest meetings, default 7]
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import speakers  # noqa: E402

RECORDINGS = speakers.CONFIG / 'recordings'


def library_without(job: str) -> dict:
    """The voice library as it would have been before this meeting taught it anything."""
    out = {}
    for name, file in speakers._index().items():
        rows, tags = speakers._rows(file)
        if rows is None:
            continue
        keep = [i for i, t in enumerate(tags) if not t.startswith(job + ':')]
        if keep:
            out[name] = rows[keep]
    return out


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    jobs = sorted(p for p in RECORDINGS.iterdir() if (p / '聲紋.npz').exists() and (p / '講者.json').exists())[-count:]
    for job in jobs:
        saved = np.load(job / '聲紋.npz')
        V, ok = saved['V'], saved['ok']
        spans = speakers.lines_of(job)
        if len(spans) != len(V):
            print(job.name, 'skipped: the transcript changed since the prints were made')
            continue
        dur = np.array([b - a for a, b in spans])
        kept = json.loads((job / '講者.json').read_text(encoding='utf-8'))
        groups = kept['groups']
        truth = [groups[k].get('name') or ('removed' if groups[k].get('off') else 'unnamed ' + k) for k in kept['lines']]
        print(f"\n{job.name}  kept by the user: " + ', '.join(
            f"{k}: {v.get('name') or ('removed' if v.get('off') else 'unnamed')} {v['seconds']}s" for k, v in groups.items()))
        result = speakers.label(V, ok, spans, library_without(job.name))
        rows = []
        for key, info in sorted(result['groups'].items(), key=lambda kv: -kv[1]['seconds']):
            mine = [i for i, w in enumerate(result['lines']) if w == key]
            by = {}
            for i in mine:
                by[truth[i]] = by.get(truth[i], 0) + dur[i]
            owner = max(by, key=by.get)
            share = by[owner] / max(info['seconds'], 1e-9)
            rows.append(f"{info['name'] or key} {info['seconds']}s = {owner}" + ('' if share > 0.8 else f' ({share:.0%})'))
        print(f"  grouped now: {len(result['groups'])} voices; " + '; '.join(rows))


if __name__ == '__main__':
    main()
