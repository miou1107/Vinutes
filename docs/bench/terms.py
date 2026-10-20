"""How often each glossary term, and each name or term from the project briefs, appears in each transcript of a
meeting. The recogniser that writes the company's names the way the glossary spells them is the one the minutes
want; this is the measure a Whisper judge cannot give.

  python docs/bench/terms.py <out folder> [names...]     default A C qwen sense
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import SCRIPTS, words  # noqa: E402

sys.path.insert(0, str(SCRIPTS))
import transcribe as tr  # noqa: E402
from google_setup import CONFIG  # noqa: E402

TAI_OLD, TAI_NEW = chr(0x81FA), chr(0x53F0)          # the two spellings of the first character of Taiwan


def norm(text: str) -> str:
    return text.replace(TAI_OLD, TAI_NEW).replace(' ', '').lower()


def brief_words() -> list[str]:
    out = []
    try:
        data = json.loads((CONFIG / 'briefs.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return out
    projects = data.get('projects') if isinstance(data.get('projects'), dict) else data
    for project in projects.values():
        if not isinstance(project, dict):
            continue
        for person in project.get('people') or []:
            name = person.get('name') if isinstance(person, dict) else person
            if name:
                out.append(str(name))
        for term in project.get('terms') or []:
            word = (term.get('term') or term.get('name')) if isinstance(term, dict) else term
            if word:
                out.append(str(word))
    return out


def main():
    folder = Path(sys.argv[1]).expanduser()
    names = [n for n in (sys.argv[2:] or ['A', 'C', 'qwen', 'sense']) if (folder / f'{n}.txt').exists()]
    texts = {n: norm(words(folder / f'{n}.txt')) for n in names}
    terms = []
    for term in tr.glossary_terms() + brief_words():
        if len(term) >= 2 and term not in terms:
            terms.append(term)
    totals = {n: 0 for n in names}
    print(f'{"term":<16}' + ''.join(f'{n:>8}' for n in names))
    for term in terms:
        counts = {n: texts[n].count(norm(term)) for n in names}
        if any(counts.values()):
            print(f'{term:<16}' + ''.join(f'{counts[n]:>8}' for n in names))
            for n in names:
                totals[n] += counts[n]
    print(f'{"total":<16}' + ''.join(f'{totals[n]:>8}' for n in names))


if __name__ == '__main__':
    main()
