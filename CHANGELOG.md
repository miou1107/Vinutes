# Changelog

## v0.4.1 (2026-10-18)

- Updating Vinutes no longer asks again for the microphone and the Mac's sound. The installer now signs the app with a certificate of its own, made once in the login keychain (Vinutes Local Signing), instead of a new ad hoc signature every time. The first update with this change asks one last time. The certificate's key can't be exported, but a program running as you could use it to sign itself as Vinutes and get the same permissions; remove the certificate in Keychain Access to go back to asking after every update.
- The tabs at the top of the right column are underlined tabs: the one you are on is blue with a line under it, the others light up under the pointer, and their numbers sit in small round badges. In Chinese they read 待處理, 人員 and 紀錄 (was 操作紀錄).

## v0.4.0 (2026-10-18)

Online meetings are recorded with the other side's voices, also with headphones on (issue #3).

- A recording now has the microphone and the sound the Mac plays, mixed into the same file, so a Meet, Teams, Zoom or LINE call is in the transcript and the minutes even when you wear headphones or AirPods. Sound Vinutes itself plays (a recording in the meeting window) is left out.
- The first recording after this version asks once to let Vinutes record the Mac's sound (macOS 14.2 and later). If you don't allow it, or on an older Mac, Vinutes records the microphone only, as before.
- Other sounds the Mac plays during the meeting (music, notification sounds) are recorded too.
- Plugging in or taking off headphones, or AirPods connecting, mid-meeting: Vinutes keeps recording both, on the new microphone and output.

Claude Code can look things up in your meetings, and change them when you ask (issue #4).

- Installing or updating Vinutes connects it to the AI tools on the Mac: Claude Code, Codex, Gemini CLI, Claude's desktop app, Antigravity and Cursor (the last three after a restart). Their other settings stay as they were; a tool installed later is connected by running scripts/connect_agents.py.
- Claude Code (or any of them), opened in any folder, then searches the minutes and transcripts, reads a meeting, lists projects and open action items, and answers with the meeting's date and title. Archived meetings come up only when named.
- When you ask it to, it names a voice, adds a paragraph to 八、補充資訊, changes words in the minutes (words that appear exactly once), sets the tags or moves a meeting to a project. The Google Doc follows, and 操作紀錄 says Claude Code made the change. It can't delete a meeting or send mail.
- When the minutes were already mailed, Claude Code is told so: the people who got them see the new text in the Doc, without a new mail.

Each meeting shows which project it belongs to, and can carry tags.

- In the list, a meeting's icon is the first character of its project on a colour of its own, the same colour every time. A meeting without a project shows an empty dashed circle. Meetings still being written up and ones that failed keep their own icons, and "Not finished" is in red.
- Tags sit under the path at the top of a meeting: remove one with its ×, or type a new one with Add tag. Claude suggests a few when it writes the minutes, shown dashed; a suggestion is on the meeting only once you add it, and suggestions go away when the minutes are sent.
- The list shows each meeting's tags. Pick one in the new Tags menu, or click a tag on a meeting, to see only the meetings with it. Search finds tags too.
- The gear beside the project name opens Project settings: rename the project (every meeting of it gets the new name; a name another project already uses puts the two together), or move this meeting to another project or a new one.
- Claude's next minutes see the project names and tags you chose, so a series keeps them.
- The box of what Claude learned from your edits is two lines high and scrolls (Expand shows six), and it goes away 5 seconds after something new is learned, unless the pointer is on it; 操作紀錄 keeps every line.

The meeting window is easier to start with and has more room for the Doc.

- Before the first meeting is recorded, the window shows Record your first meeting with a Start recording button and the shortcut ⌃⌥R. The new recording shows up in the list as soon as it starts.
- Send email is at the right of the top row. Once the minutes are sent, it becomes "Sent to N people" (the time and format show when you point at it), and the bottom row is gone unless a recording is playing.
- 待補充 and 待確認 are one tab, 待處理, with one number; each card says which it is.
- The People tab shows each voice in the recording with a menu of who it is. The menu starts on the name the AI guessed, and the minutes already use it (a guess is written in when the minutes are, and the voice is not remembered from a guess); pick someone else, or type a name under 其他人⋯, and the minutes and the mail change at once where that voice is meant (講者 B, or the name it was given there), while the same name said about someone else stays; Vinutes remembers that voice for the next meeting. Two voices the AI guessed as the same person keep their letters until you pick. ▶ 聽錄音 plays that person's stretch and stops. The people invited who didn't speak are listed under it. The names offered come from the meeting's calendar invitation (an ERP room booking's invitees come through it), the project's own list from earlier meetings, and the minutes' 與會人員 line, which follows the list.
- When the AI has used up its limit, the window says when it is back (明天中午 12 點) instead of only that the change failed.
- The number of meetings shown is beside the list's title, 所有會議記錄 (2), instead of on a row of its own.
- ⌘V in the box where you ask Claude adds a picture on the clipboard (a screenshot, an image copied from a page, a picture file copied in Finder), the same as one chosen with the picture button; text still pastes as text.
- The quick buttons (精簡摘要, 完整詳盡 and the rest) are under the box where you ask Claude, and the ＋ menu opens upward like the AI menu.

The minutes are filed under the right meeting.

- Only a calendar event you are invited to (and haven't declined) counts as the meeting you recorded, and the one that overlaps the recording most wins. Room bookings on a shared company calendar that you are not on are only offered to the AI as maybes, to use when the transcript is plainly about them.
- The next meeting of the same series is looked up in the next four weeks, so the minutes give its real date instead of one heard in the transcript.
- A later recording of the same series is given the name and project used before.

The floating bar shows that the recording is running, and can show live captions.

- The red dot is now five small red bars that jump with how loud the room is, so a glance shows both that the recording runs and that the microphone hears. They lie flat and turn orange while paused.
- CC on the floating bar turns live captions on or off (macOS 26 and later); Vinutes remembers the choice. The captions are one line under the bar and follow it: purple words with a white edge and no background, shown as soon as they are heard, the newest on the right and older words fading out on the left.
- Captions come from Apple's transcriber on the Mac itself; nothing is sent anywhere, and they are not written into the transcript or the minutes. The arrow next to CC picks the language (Chinese, English, Japanese, Korean, Spanish, French); each recording starts in the meeting language from Settings. The first time a language is used, the Mac downloads it once.
- The captions run in a helper of their own that reads the recording file, so they can't stop or spoil the recording. What they did is logged to ~/Library/Logs/Vinutes/captions.log.

Vinutes keeps logs, to find out why something went wrong.

- ~/Library/Logs/Vinutes/ holds app.log (starting and quitting, recording started, paused, stopped or discarded, the shortcuts, the microphone permission, the meeting window and each thing done in it, every script run with how long it took and how it ended, every error shown), scripts.log (each run of a script, and the traceback when one crashes) and captions.log. Console.app shows them too.
- They hold what happened, never the transcript, the minutes, what you typed, mail text or addresses.
- Each log stays under 5 MB; past that it becomes an .1 file that replaces the older one, so a log never takes more than 10 MB.

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
