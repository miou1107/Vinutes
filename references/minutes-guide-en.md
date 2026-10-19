audience: agent

# Writing meeting minutes in English

This guide is for the AI that writes the minutes after a Vinutes recording, when the minutes are in English: the
meeting was held in English, or in a language other than Chinese and English while the user's Vinutes is set to
English. It mirrors the Chinese guide (SKILL.md) section by section, so English and Chinese minutes have the same
eight sections and the app can read both. A filled-in example is `example-minutes-en.md` (fictional).

## Automatic mode

Vinutes, the menu-bar recorder, starts this job after the user stops a recording. It has already turned the
recording into a transcript and read that day's calendar. You run in a restricted mode that can only read and write
files: no commands, no web, no MCP servers, none of the user's own settings. The program publishes the Google Doc,
shows the mail preview and sends the mail after you finish; nothing is sent until the user presses Send in the app.
The prompt gives you the job folder (written `job` below), the recording's start and end, and where the files go.

1. Ask no questions. First read what exists in `job/參考/`: this guide, `使用者規則.md` (the user's own rules; they
   win over this guide, except that mails are never sent without the user and external minutes never keep internal
   discussion), `公司詞彙表.md` and `glossary.md` (known mis-hearings and correct names), `example-minutes-en.md`,
   `使用者設定.json` (`owner` is the user's own address, `our_company` is the user's company name), and
   `專案小抄.md` (each project's people, terms and background, as the user confirmed them).
2. Find the meeting: the program has already picked it in `job/行事曆.txt` (its headings are in Chinese).
   - 「這場會議」: the event the user is invited to that overlaps the recording most. Take its name, place, attendees
     and attachment names.
   - 「同一系列的下一次會議」: the next meeting of the same series; fill `next_meeting` from its date and time, unless
     the meeting clearly moved it (e.g. "next time on Nov 4"), then from the transcript.
   - 「同一時段公司行事曆上的其他會議」: events the user is not invited to that only overlap in time (mostly rooms
     booked by others). Use one only if the transcript is plainly about its subject; overlapping time is not enough.
   - 「今天稍早你參加過的會議」: for a discussion that ran on after a meeting, its attendees can be reused.
   - 「同一系列之前整理過的會議」: copy the meeting name and project from it.
   With `專案小抄.md`, decide first which project the meeting is: 「同一系列之前整理過的會議」 is surest, then
   `最近的會議.json` and what the transcript is about. Write names, who does what and terms as that project's brief
   has them, and turn its "the transcript often has" spellings back into the right ones. People in a brief belong to
   the project; they are not this meeting's attendees: take attendees from the calendar, and without a list there
   leave them as `[__]` as below, never filled from the brief. Nothing from another project's brief goes into these
   minutes.
   When the calendar has no such meeting, name it from the transcript, leave the attendees as `[__]`, and fill
   `next_meeting` only from what the transcript says clearly.
   Then read `job/參考/最近的會議.json` (earlier meetings' names and projects): the same meeting (e.g. a fortnightly
   review) keeps exactly the same name and project; the app finds "previous meeting" and "next meeting" by them.
3. Write the minutes from `job/逐字稿.txt` following the sections below and save them as `job/紀錄.md`. For background
   use only `job/參考/舊紀錄/` (earlier minutes), the calendar and the project's brief.
4. Prepare the mail: recipients are the attendees in the 「這場會議」 section on the user's own company domain, plus
   the user; when no meeting matched or it lists nobody, only the user. People in the other sections are not
   recipients. Write the text in the tone of a short note to colleagues, with the line
   `The minutes are ready:` and on the next line, alone, `{doc_url}`; the program puts the Doc's address there, and
   when the user sends a Word or PDF file instead it turns those two lines into "The minutes are ready; please see
   the attached file." Save it as `job/信件內文.txt`. Do not sign it unless `使用者設定.json` has a `sender_name`.
5. If the minutes name a next meeting, do not create an invitation; put it in `check`.
6. Last, write `job/result.json` (UTF-8):

   ```json
   {"status": "ok", "title": "Website redesign kickoff", "when": "Wed, Oct 15, 14:00–15:00",
    "place": "Room 3A, or [__] if unknown", "project": "Website", "tags": ["External"], "next_meeting": "Wed, Oct 29, 14:00",
    "mail": {"to": ["a@example.com", "the user's own address"], "subject": "Minutes: Website redesign kickoff (Oct 15)"},
    "todo": [{"label": "Chair", "line": "Chair:"}, {"label": "Budget", "line": "Campaign rollout"}],
    "check": [{"text": "Speaker B is probably Amy Chen", "heard": "", "meant": ""},
              {"text": "\"Fresh\" is probably Threads", "heard": "Fresh", "meant": "Threads"}],
    "notes": []}
   ```

   - `project`: which project the meeting belongs to; the app's Project menu groups meetings by it. Copy a project
     name already in `最近的會議.json`; otherwise make one of 1–4 words from the meeting name, the calendar title or
     the case name that keeps coming up, without words like "weekly", "sync", "meeting", "review"
     (e.g. "Website redesign weekly" → "Website redesign"). Write "" only when no project can be told.
   - `tags`: up to 3 tags to suggest for this meeting, 1–2 words each, or `[]`. Good ones are the kind of meeting
     (External, Internal, Monthly) and other projects the meeting also covered besides its main one. Reuse tags
     already in `最近的會議.json` rather than a new word for the same thing, and do not repeat `project`. They are
     only suggestions: a tag is on the meeting once the user adds it in the window.
   - `next_meeting`: the next meeting's time if the minutes give one, else "".
   - `todo`: one item per `[__]` in the minutes. `label` is a field name of 1–3 words; `line` is a short piece of the
     original text on the same line (or table row) as that `[__]`, apart from the `[__]` itself; the app uses it to
     see when the user has filled the blank.
   - `check`: the guesses from "Uncertain information" below (who a speaker is, unsure words) plus the next meeting,
     each `text` under 12 words. For a mis-heard word also fill `heard` (as the transcript has it) and `meant` (what
     you wrote instead); when the user clicks "Looks right" in the app, the pair goes into the project's brief (or the
     glossary when the meeting has no project). Each person the minutes name who is not in the project's brief (an
     attendee, or someone given a task) gets one item:
     `{"text": "New name: Grace", "person": "Grace", "role": "briefing contact"}`; `role` is what they do in
     this meeting, a few words, or "". When the user clicks "Looks right", the person joins the project's brief.
   - `notes`: anything else the user should know, else [].
   - Without a mail, write `"mail": null`. If you cannot finish, write
     `{"status": "error", "error": "One sentence: which step failed and what the user should do"}`.

## Before you start: internal or external

Decide first; everything below follows from it. If every calendar attendee is a colleague, it is internal. Test:
will these minutes leave the company? If yes, write them as external.

| | Internal (colleagues only) | External (clients, agencies, vendors) |
|---|---|---|
| People | Real names | Organisations only: "<Client> explained", "<Our company> noted" |
| Reviews of performance (missed targets, hours, cases) | Keep | Remove |
| Internal talk after the client left, budget limits, pricing strategy, opinions of the client | Rewrite as neutral fact | Remove entirely |
| Attendance field | Attendees: names, comma-separated | Organisations and representatives, one organisation per line |
| Owner column in tables | Owner (a person) | Owner (an organisation) |

Our company is always `our_company` from `使用者設定.json`; if it is missing, write "our company".

## Reading the transcript

- **Fix mis-heard words**: first with the two glossaries, then from context and the project's background. Keep the
  original when unsure and list it. System names, organisation names and abbreviations are mis-heard most often.
- **Speakers**: when a line has a speaker after the time (`[20:08] Amy Chen:` or `[20:08] Speaker B:`), the recorder
  told the voices apart. Use names as given; Speaker A, B are voices without a name yet: guess who they are from the
  content (who reports on their own work, who asks and decides, who refers to their own task) and put each guess in
  `check` ("Speaker B is probably Amy Chen"). One- or two-word replies (yes, right, OK) are the most often mislabelled;
  when they do not fit the context, trust the context. Two people merged into one voice: split them by content.
  When you cannot tell who it is, write the role or organisation; when not even that, write "It was raised that…".
  Never invent a name.
- **The end of the meeting**: in external minutes, drop everything said after the client left or said goodbye.
- **Group by topic, not by time**: points about one topic scattered through the meeting go into one subsection.
- **Leave out** small talk, jokes, connection trouble, repeated confirmations and back-and-forth that led nowhere.
- **Never present a guess as fact**: when a unit is unclear ("8,000" yen or orders?), keep the original and mark it.
  A sentence you cannot make sense of stays out of the minutes and goes into `notes`.
- **Numbers and dates**: a mis-heard number or date becomes a wrong decision in the minutes, and readers of a
  translated meeting are the least able to notice. When a figure or date is said differently in two places, or
  does not fit the rest (a launch "after the sale" set before the sale ends), keep the transcript's value, mark it
  `[__]` and add a `check` item.
- **Meetings in another language**: when the transcript is not in English, write the minutes in English, keep
  people's names as the transcript writes them, keep amounts in their own currency (e.g. "¥150,000"), and keep a
  short original term in parentheses when the English is a guess.

## Layout: seven sections, plus an eighth when there is supporting material

Two title lines, centred: the meeting's subject, then "Meeting Minutes". In Markdown, two `#` headings.

1. **## 1. Meeting Details** (bullets): Subject; Date as "Wednesday, October 15, 2026, 13:30–15:00"; Location (room
   or online platform, never meeting links, dial-in numbers or PINs); Chair; Attendees or organisations (see the
   table above); Materials: slides, schedules, sheets used in the meeting, as clickable links
   (`[Project schedule](address)`), from the invitation's attachments or files named in the meeting; leave the line
   out when there are none.
2. **## 2. Purpose**: one paragraph: what it follows up from the last meeting, what this one had to settle, and
   what the result is the basis for.
3. **## 3. Discussion Summary**: subsections by topic, `### (a) …`, `### (b) …`, 3–8 bullets each. Each bullet one
   fact or conclusion, saying whose position it is ("Amy Chen explained", "David Lee proposed"; external:
   "<Client> explained", "<Our company> noted", "Initial direction:"). Link pages and posts that are already live.
4. **## 4. Agreements**: a numbered list of what was agreed, nothing else.
5. **## 5. Open Questions**: a table `Item | Details | Confirm with`.
6. **## 6. Action Items**: a table `No. | Action | Owner | Details and next steps`; put dates in the details,
   `[__]` when none was given.
7. **## 7. Other Suggestions**: one paragraph: what the next meeting should focus on, what can wait.
8. **## 8. Supporting Materials** (only when there is something; otherwise leave the section out, never write
   "None"): material mentioned that belongs nowhere above, e.g. figures a colleague sent after the meeting,
   reference sites, screenshots. One line each: who provided what, then the link; pictures as `![caption](file or address)`.
   The app adds files and links the user attaches later to the end of this section.

Keep these heading texts exactly ("## 1. Meeting Details" … "## 8. Supporting Materials"): the app finds sections
by them.

## Tone and wording

- Formal, plain business English: complete sentences, past tense for what was said ("explained", "proposed",
  "agreed"), no slang, no filler, no judgement of people.
- Government and public bodies: a more formal register ("The Department confirmed…", "to be discussed separately").
- One fact per sentence; split sentences over 30 words.
- Use the same name for the same thing throughout: full name first, a short form after; glossary spellings win.
- Dates as "October 15, 2026"; times as 14:00; numbers with thousands separators.
- No dashes as punctuation; no phrases like "in today's fast-paced world", "it is worth noting that", "leverage",
  "synergy".

## Uncertain information

- Fields the transcript does not give stay `[__]`; do not guess.
- Every guess goes into `result.json`: blanks in `todo`; speaker guesses, unsure words and unsure figures in
  `check`.
