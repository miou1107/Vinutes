# Changelog

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
