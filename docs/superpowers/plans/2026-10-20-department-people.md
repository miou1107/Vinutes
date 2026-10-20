# Department roster from the calendar — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A room booking whose calendar description names the user as host or participant is the user's meeting; the names in it start the meeting's people; the department it names remembers who the user confirmed, so the next meeting of that department starts with them.

**Architecture:** `workspace.py` parses the event description once (`describe`) and hands host / departments / participants through the `MATCH` line into `行事曆.json`. `minutes_app.py` reads them for the meeting's people and keeps a roster per department in `departments.json` next to `people.json`, written whenever the user names a voice or adds a person in a meeting that has departments. The window shows one line above the voices saying what the calendar said and where the roster came from.

**Tech Stack:** Python 3.11 (no new packages), the window's vanilla JS, unittest.

**Spec:** `prototypes/department-people.html` (approved by Vin 2026-10-20; the second name in it is Alan, not 林辰).

## Global Constraints

- Labels in the description are matched generically (Chinese and English), never only the one ERP's wording.
- Nothing is removed from a roster by the app; only the user can edit it (same rule as the project's people, Vin 2026-10-19).
- Chinese UI strings follow vin-voice.md; each new string exists in EN and ZH (`tests` compare the two tables for strings.py; strings.js is kept in step by hand).
- No new field goes into the minutes' text that the user did not see in the window.

## Review Focus

- A description with the labels but empty values (`參與人員:`) → nothing added, meeting not claimed. Test in Task 1.
- The user's own name spelled 黃建國(Vin) while settings say 黃建國 Vin → still recognised as the user. Test in Task 1.
- A department with a roster, but this meeting's description names a participant not in it → both appear, no duplicate. Test in Task 2.
- A meeting whose description names a department the user has never confirmed → calendar line shows, no roster line, nothing written. Test in Task 2.
- Naming a voice in a meeting without departments must not create a `departments.json` entry. Test in Task 2.

---

### Task 1: workspace.py reads the description

**Files:** Modify `scripts/workspace.py` (`pick_meeting`, `show`, `meeting`); Test `tests/test_app.py` class `CalendarPick`.

**Produces:**
- `describe(ev: dict) -> dict` → `{'host': str, 'departments': list[str], 'participants': list[str]}` from `ev['description']`; labels (case-insensitive, after optional spaces, `:` or `：`): host `主持人|主席|召集人|host|organizer|chair`; departments `參與部門|與會部門|部門|departments?|teams?`; participants `參與人員|與會人員|出席人員|參加人員|attendees|participants`. Values split on `、,，;；/` and newlines, trimmed, empty dropped.
- `names_me(text: str, me: list[str]) -> bool` → any token of `me` (≥ 2 chars, case-insensitive) occurs in `text`.
- `pick_meeting(found, start, end, me: list[str] = ())`: an event is the user's when on the primary calendar and not declined, **or** when `names_me` on its host or participants. `meeting()` passes `me = tokens of sender_name()` (split on spaces and brackets).
- `show()` prints `   主持人:`, `   參與部門:`, `   參與人員:` lines when present.
- The `MATCH` JSON gains `host`, `departments`, `participants`.

- [ ] Write tests `test_a_room_booking_whose_note_names_the_user_as_host_is_the_meeting`, `test_the_note_is_read_with_either_wording`, `test_empty_note_values_claim_nothing`, `test_the_users_name_in_brackets_counts`.
- [ ] Run `python3 -m unittest tests.test_app.CalendarPick -v` → the new ones fail.
- [ ] Implement; run again → pass; whole suite passes.
- [ ] Commit.

### Task 2: minutes_app.py — invited names and the department roster

**Files:** Modify `scripts/minutes_app.py` (`invited`, `meeting_people`, `cmd_people`, `cmd_speaker`, `answer`, the open/refresh payloads); Test `tests/test_app.py` new class `Departments`.

**Produces:**
- `DEPARTMENTS = CONFIG / 'departments.json'` → `{dept: {'people': [...], 'from': '2026-10-20 數據課週會'}}`.
- `calendar_of(job) -> dict` → `{'host': str, 'departments': [...], 'participants': [...]}` from `行事曆.json` (missing → empty).
- `invited(job)` also yields `host` and `participants`; a name that `names_me` the user becomes `sender_name()`.
- `roster(departments: list[str]) -> tuple[list[str], str]` → the union of the departments' people (in order) and the `from` of the first department that has one.
- `remember_roster(job, names)` → for each department of the job, writes `names` (union with what it had) and `from` = this job's date and title; called at the end of `cmd_people` add and `cmd_speaker` whole-voice.
- `meeting_people(job)` first time: `invited + roster + attendees(md)`.
- payload key `calendar` on open, refresh and every people answer: `{'host', 'departments', 'roster', 'roster_from', 'learned': bool}` (`learned` true when this job is the roster's source).

- [ ] Write tests: `test_host_and_participants_in_the_note_start_the_meetings_people`, `test_naming_a_voice_remembers_the_department`, `test_the_next_meeting_of_the_department_starts_with_the_roster`, `test_no_department_no_roster_file`, `test_a_participant_not_in_the_roster_is_added_once`.
- [ ] Run → fail. Implement → pass. Commit.

### Task 3: what the AI reads

**Files:** Modify `scripts/auto_minutes.py` (`read_calendar`), `SKILL.md` §0.5 step 2, `references/minutes-guide-en.md` "Automatic mode" step 2; Test class `CalendarForTheAgent`.

- `read_calendar` appends `== 參與部門之前確認過的名單` + one line per department when a roster exists.
- Guides: 主持人、參與人員照行事曆的「主持人」「參與人員」填；「參與部門之前確認過的名單」裡的人也是與會人員（Vin 2026-10-17：以當場會議邀請的人為主）。

- [ ] Test `test_the_roster_of_the_department_is_handed_to_the_agent`. Run → fail. Implement → pass. Commit.

### Task 4: the window

**Files:** Modify `recorder/app/app.js` (`peopleHTML`, `peopleDone`, the refresh and open code paths add `calendar`), `recorder/app/strings.js` (EN + ZH).

- Above the voices: `people_calendar(host, depts)` → ZH `行事曆：主持人 ${host}，參與部門 ${depts}` (each part only when present); when `roster_from` is another meeting: `people_roster_from(depts, from)` → `行事曆：參與部門 ${depts}，名單帶自 ${from}`; when `learned`: `people_learned(dept, names)` → `已記住${dept}的名單：${names}` under the cards.
- EN: `Calendar: host ${host}, department ${depts}` / `Calendar: department ${depts}, people from ${from}` / `Remembered for ${dept}: ${names}`.

- [ ] Implement; `node --check recorder/app/app.js`; open the real window on the 10/20 meeting after re-running its calendar pick (`workspace.py meeting`) and screenshot the People tab.
- [ ] Commit.

### Task 5: docs and version

- CHANGELOG `v0.4.12`, README (EN/ZH) one line under 對照 Google 行事曆, FILELIST unchanged (no new file), VERSION 0.4.12.
- [ ] Commit; `superpowers:verification-before-completion`; `superpowers:requesting-code-review`; PR.
