# Changelog

## Unreleased

Each meeting shows which project it belongs to, and can carry tags.

- In the list, a meeting's icon is the first character of its project on a colour of its own, the same colour every time. A meeting without a project shows an empty dashed circle. Meetings still being written up and ones that failed keep their own icons, and "Not finished" is in red.
- Tags sit under the path at the top of a meeting: remove one with its ×, or type a new one with Add tag. Claude suggests a few when it writes the minutes, shown dashed; a suggestion is on the meeting only once you add it, and suggestions go away when the minutes are sent.
- The list shows each meeting's tags. Pick one in the new Tags menu, or click a tag on a meeting, to see only the meetings with it. Search finds tags too.
- The gear beside the project name opens Project settings: rename the project (every meeting of it gets the new name; a name another project already uses puts the two together), or move this meeting to another project or a new one.
- Claude's next minutes see the project names and tags you chose, so a series keeps them.
- The box of what Claude learned from your edits is three lines high and scrolls; Expand shows six.

The minutes are filed under the right meeting.

- Only a calendar event you are invited to (and haven't declined) counts as the meeting you recorded, and the one that overlaps the recording most wins. Room bookings on a shared company calendar that you are not on are only offered to the AI as maybes, to use when the transcript is plainly about them.
- The next meeting of the same series is looked up in the next four weeks, so the minutes give its real date instead of one heard in the transcript.
- A later recording of the same series is given the name and project used before.

## v0.3.0 (2026-10-16)

Meetings can be archived and deleted from the list.

- Select, beside the list's title, puts a checkbox on each meeting; Select all checks every meeting the list shows. Archive and Delete at the bottom act on the checked ones. Right-clicking a meeting offers the same two for that meeting, or for all the checked ones when it is one of them.
- An archived meeting leaves the list and the menu bar's recent meetings, and is shown under Archived in the project picker, where Unarchive brings it back.
- Delete asks first, listing the meetings. The recording, transcript and minutes (with their picture copies) go to the Mac's Trash, and the Google Doc and the files the meeting attached to Google Drive's trash, whether or not the minutes were sent. Meetings of one series share a Drive folder for attachments; it stays as long as another meeting uses it. A meeting that was sent to others is marked in the dialog, with a warning that they can no longer read the Doc.
- Offline, nothing is deleted and the dialog says so; with several meetings picked, the first failure stops the rest. A meeting still being written up can't be archived or deleted.

## v0.2.0 (2026-10-16)

Vinutes speaks English, with Traditional Chinese as the second language.

- The menu bar, the meeting window, notifications and messages follow the Mac's language. Change it under Settings > App Language in the menu bar (Same as Mac, English or 繁體中文), or with English／中文 at the top of the setup checklist.
- People who used Vinutes before this version stay in Chinese, even on an English Mac.
- Each recording's language is detected from its start, middle and end. Settings > Meeting Language can fix it to English or Chinese instead.
- English meetings get English minutes, with the same eight sections as Chinese ones; Chinese meetings get Chinese minutes as before. A meeting in another language gets minutes in the app's language, and its transcript keeps the original words.
- The email to attendees is in the minutes' language. Unnamed voices are "Speaker A" in English and 「講者 A」 in Chinese.
- The README lists how well each language is recognised; a Chinese README is added.
- Earlier meetings are not rewritten: switching the language changes the app's words only.

## v0.1.0 (2026-10-15)

First release as its own repository. Until now the app lived inside the vin-meeting-minutes-zh skill under the name 「Vin 會議記錄助手」.

- The app is now called Vinutes. Installing it removes the old app; macOS asks for the microphone again, and "open at login" has to be turned on again from the menu.
- Version numbers and the update button follow this repository.
- Settings, Google sign-in and recordings stay where they were, so nothing has to be set up again.
