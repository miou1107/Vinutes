"""A made-up Vinutes home for the README screenshots: four example meetings in English, nobody real in them.

  python3 docs/screenshots/demo_home.py /tmp/vinutes-demo

Then start a second copy of the app on it (the real one keeps running; nothing of yours is read or changed):

  MINUTES_HOME=/tmp/vinutes-demo ~/Applications/Vinutes.app/Contents/MacOS/MeetingRecorder &

The app language is English, there is no Google sign-in (the meeting window shows the minutes themselves), and the
Python and the Vinutes folder are the ones install.sh wrote for the real app.
"""
import json
import shutil
import sys
from pathlib import Path

REAL = Path('~/.config/vin-meeting-minutes-zh').expanduser()
PEOPLE = ['Amy Chen', 'David Lee', 'Priya Patel', 'Tom Baker']

MINUTES = {
    'kickoff': """# Spring Campaign Kickoff

# Meeting Minutes

## 1. Meeting Details

- Subject: Spring Campaign Kickoff
- Date: Friday, October 16, 2026, 14:00–14:45
- Location: Meeting Room 3
- Chair: Amy Chen
- Attendees: Amy Chen, David Lee, Priya Patel, Tom Baker

## 2. Purpose

The team agreed on the spring campaign's three channels, the budget split and who owns each piece, so that the
first drafts can be reviewed at the next meeting.

## 3. Discussion Summary

### (a) Channels

- Amy Chen proposed three channels: the newsletter, short videos and the partner stores.
- David Lee noted that last spring's short videos brought the most new sign-ups.
- Priya Patel asked to keep the partner stores to the ten largest, so the displays arrive on time.

### (b) Budget

- Tom Baker explained the budget: 60% short videos, 25% newsletter, 15% store displays.
- The team kept 10% of the video budget back until the first two videos are out.

## 4. Agreements

1. The campaign runs from March 2 to April 30.
2. Short videos get 60% of the budget; 10% of it waits for the first results.
3. The partner stores are the ten largest only.

## 5. Open Questions

| Item | Details | Confirm with |
|---|---|---|
| Store displays | Whether the printer can deliver by February 20 | Priya Patel |
| Video length | 15 or 30 seconds for the first two | David Lee |

## 6. Action Items

| No. | Action | Owner | Details and next steps |
|---|---|---|---|
| 1 | Draft the newsletter | Amy Chen | First draft by October 23 |
| 2 | Script the first two videos | David Lee | Scripts by October 27 |
| 3 | Ask the printer for a delivery date | Priya Patel | Answer by [__] |

## 7. Other Suggestions

The next meeting should review the newsletter draft and the video scripts; the store displays can wait until the
printer answers.
""",
    'weekly': """# Website Redesign Weekly

# Meeting Minutes

## 1. Meeting Details

- Subject: Website Redesign Weekly
- Date: Thursday, October 15, 2026, 10:30–11:00
- Location: Online
- Chair: David Lee
- Attendees: David Lee, Amy Chen, Tom Baker

## 2. Purpose

The weekly check on the new website: what changed since last week and what is needed before the test launch.

## 3. Discussion Summary

### (a) Progress

- David Lee showed the new home page and the product pages.
- Tom Baker noted that the search page is still slow on phones.

## 4. Agreements

1. The test launch stays on November 2.

## 6. Action Items

| No. | Action | Owner | Details and next steps |
|---|---|---|---|
| 1 | Make the search page faster on phones | Tom Baker | By October 22 |
""",
}

MEETINGS = [
    # folder, minutes key, title, project, tags, when, place, sent
    ('20261016-140000', 'kickoff', 'Spring Campaign Kickoff', 'Spring Campaign', ['planning', 'budget'],
     'Fri, Oct 16, 14:00–14:45', 'Meeting Room 3', False),
    ('20261015-103000', 'weekly', 'Website Redesign Weekly', 'Website Redesign', ['weekly'],
     'Thu, Oct 15, 10:30–11:00', 'Online', True),
    ('20261014-160000', 'weekly', 'Supplier Call: Packaging', 'Spring Campaign', ['suppliers'],
     'Wed, Oct 14, 16:00–16:30', 'Online', True),
    ('20261013-093000', 'weekly', 'Hiring Sync', 'Team', [],
     'Tue, Oct 13, 09:30–10:00', 'Meeting Room 1', True),
]


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(text, encoding='utf-8')


def main(home: Path):
    if home.exists() and (home / 'recordings').exists() and not (home / '.vinutes-demo').exists():
        sys.exit(f'{home} is not a demo home made by this script; pick another folder')
    shutil.rmtree(home, ignore_errors=True)
    home.mkdir(parents=True)
    write(home / '.vinutes-demo', 'made by docs/screenshots/demo_home.py\n')
    shutil.copy(REAL / 'recorder.json', home / 'recorder.json')        # the real Python and Vinutes folder
    if (REAL / 'models').exists():
        (home / 'models').symlink_to(REAL / 'models')                  # the speech model, read only
    write(home / 'settings.json', {'language': 'en', 'meeting_language': 'en', 'ai': 'claude',
                                   'sender_name': 'Amy Chen', 'our_company': 'Northwind'})
    write(home / 'setup-seen', '')
    for folder, key, title, project, tags, when, place, sent in MEETINGS:
        job = home / 'recordings' / folder
        y, m, d, hh, mm = folder[:4], folder[4:6], folder[6:8], folder[9:11], folder[11:13]
        start = f'{y}-{m}-{d}T{hh}:{mm}:00+08:00'
        write(job / 'job.json', {'audio': '錄音.m4a', 'started': start, 'ended': start, 'paused_seconds': 0,
                                 'language': 'en'})
        write(job / 'status.json', {'step': 'done', 'message': title, 'at': start})
        md = job / '整理' / '紀錄.md'
        write(md, MINUTES[key].replace(MINUTES[key].splitlines()[0], f'# {title}', 1))
        result = {'status': 'ok', 'title': title, 'minutes_md': str(md), 'when': when, 'place': place,
                  'project': project, 'minutes_lang': 'en', 'spoken': 'en', 'tags': tags,
                  'mail': {'to': ['amy@example.com', 'david@example.com'], 'subject': f'[Minutes] {title}'}}
        if sent:
            result['sent_at'] = start
        write(job / 'result.json', result)
        write(job / '分類.json', {'project': project, 'tags': tags})
        write(job / '人員.json', {'people': PEOPLE})
        write(job / '逐字稿.txt', '[00:00] Amy Chen: Let\'s start with the channels.\n')
        log = [{'at': start, 'who': 'Amy Chen', 'text': 'Started recording', 'kind': ''},
               {'at': start, 'who': 'Assistant', 'text': 'Wrote the minutes', 'kind': ''}]
        write(job / '操作紀錄.jsonl', ''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in log))
    print(f'demo home ready: {home}')


if __name__ == '__main__':
    main(Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/vinutes-demo').expanduser())
