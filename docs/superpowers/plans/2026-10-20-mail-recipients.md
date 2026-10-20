# Mail window: recipients from the meeting's people, names to pick, a summary in the body — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When the user opens 發送信件, the recipients are already the meeting's people (addresses found from the calendar invite, the company directory and earlier mails), a typed name offers people to pick, and the body carries the meeting's purpose and three to five highlights taken from the minutes.

**Spec:** `prototypes/mail-recipients.html` (Vin 2026-10-20: 「OK」). Vin's words: 「發送郵件現在只能一個一個email打，我哪背得下來啊? 應該要自己輸入關鍵字就可快速選取，同時預設應該把與會人員都帶進名單中」「email的內容應該要把一些摘要放進去,例如目的和精簡的摘要」.

**Architecture:** a new `scripts/contacts.py` keeps `~/.config/vin-meeting-minutes-zh/contacts.json` (address → name, source), filled from the Google directory at most once a day, from calendar invitees and from recipients the user mailed. `mail_defaults` in `minutes_app.py` resolves each of the meeting's people to an address through it and adds the summary to the body; a new `suggest` command answers the window's typing. The window keeps recipients as {name, mail} chips. No CC.

## Tasks

1. `contacts.py`: `learn(address, name, src)`, `address_of(name)`, `suggest(query, exclude)`, `refresh_directory()` (People API listDirectoryPeople through doc_sync.call, skipped when synced within a day or offline). Tests: class `Contacts`.
2. `mail_defaults(job)` returns `people: [{name, mail}]`, `missing: [name]`, `to` as before plus the found addresses; `with_summary(body, md)` inserts 會議目的 / 重點 (Purpose / Highlights) from sections 會議目的, 初步共識, 行動方案 (Purpose, Agreements, Action Items) after the paragraph with the Doc link, unless the body already has one. Learns the calendar invitees. Tests: class `MailDefaults`.
3. `cmd_suggest(job, query)` → `{'people': [...]}`; Swift whitelist + case `suggest`; app.js chips, dashed chip for a person without an address, autocomplete from `suggest`, Enter adds; strings EN/ZH. Guides: mail body rule in SKILL.md §0.5 step 4 and §6 step 8, minutes-guide-en.
4. CHANGELOG v0.4.14, README line, VERSION.
