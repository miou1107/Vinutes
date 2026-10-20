# Changelog

## v0.4.16 (2026-10-20)

- The transcript is mostly done when you press Stop. While a meeting is recorded, Vinutes transcribes it in pieces of about five minutes in the background, each cut at a quiet moment so no sentence is split, each told the last words of the piece before so names keep their spelling. After Stop only the last piece is transcribed, so the transcript takes about a minute instead of four or more, and the minutes arrive that much sooner. The model, the glossary hint and the language setting are the same as before; on three recorded meetings the transcript came out the same as a one-go transcript to within the run-to-run noise of the model (the figures are in issue 1). Pausing needs nothing, and pieces survive a crash or a restart. `live_transcribe: false` in settings.json turns it off.

## v0.4.15 (2026-10-20)

- Naming a voice, adding or removing a person under People no longer teaches Vinutes anything: the change it makes to the 與會人員 line is the app's own, not your wording, so no "照你的寫法" rule is written to notes.md for it. Your own edits right after are still learned.

## v0.4.14 (2026-10-20)

- 發送信件 opens with the meeting's people as the recipients, each with the address Vinutes found: the calendar invitation, the company directory (read once a day) or a mail you sent before. A person it has no address for is a dashed chip; click it and type one. Typing a name or part of an address offers people to pick (Enter or a click adds them); a full address still works as before. What Vinutes knows is in ~/.config/vin-meeting-minutes-zh/contacts.json.
- The mail says what the meeting was for and what came out of it: after the link, 會議目的 (one sentence from the minutes' section 二) and 重點 (up to five lines from the agreements in section 四 and the action items in section 六, the owner after each). The AI writes them for new minutes; for minutes already written, Vinutes fills them in from the minutes when the mail opens. Edit them before sending as before.

## v0.4.13 (2026-10-20)

- Section 8 of the minutes is now 參考附件 (Attachments in English minutes) and every set of minutes has it: the AI writes 無 (None) when nothing was attached, and the first attachment you add takes the place of that line. Minutes written before this version keep their 補充資訊 heading, and attachments still go there.

## v0.4.12 (2026-10-20)

- A room booking made in a company system (an ERP) that invites nobody on Google, but writes the host and the participants into the calendar event's note, now counts as your meeting when the note names you. The note's host and participants start the meeting's people, spelled as the note spells them, and the minutes AI reads them with the calendar.
- Under People, a voice that was given the wrong name can be removed like an unnamed one (移除講者 X), and each person listed as not having spoken has ✕ to take them off this meeting. A description the AI wrote beside a name on the 與會人員 line ("Adam（負責 AI SEO，逐字稿標記為講者 B）") is no longer split into two people; the name is Adam.
- The department such a note names (參與部門) remembers the people you confirm under People at that meeting. The next meeting that names the department starts with them, under People and in the minutes the AI writes, so its voices are matched against them first. People shows what the calendar note said and which meeting the roster came from. Vinutes never takes anyone off a roster; the rosters are in ~/.config/vin-meeting-minutes-zh/departments.json.

## v0.4.11 (2026-10-19)

- Add attachments, beside Tags under the meeting's title, opens a window for the files, links and pictures that go into section 8 of the minutes, Supporting Materials. Each one has a note of its own, which leads its line ("September traffic report from Amy: report.xlsx"); one without a note shows its name only. Beside the button are the attachments section 8 already holds, and a click opens one.
- ＋ and the picture button beside the box under the minutes now hand files, links and pictures to the AI with your sentence, as a pasted screenshot already was; they no longer go into the minutes. The AI reads PDF, Word, Excel, PowerPoint and text files, and web pages; a Google Docs, Sheets or Slides link is read with your Google sign-in. A link that needs some other sign-in stops the request and says so.

## v0.4.10 (2026-10-19)

- Update in the corner of the meeting list shows within an hour of a new version, no longer the next day: GitHub is asked about the newest version once an hour instead of once a day.
- An item under To confirm that was answered elsewhere (a voice named under People) leaves the side panel even while a Fix box is open on another item.

## v0.4.9 (2026-10-19)

- Usage (用量統計), in the meeting window above the version and in the menu-bar panel between All Meetings and Settings, shows a month by day or by project: meetings and minutes of audio, AI runs (write-ups and edits) with their minutes and tokens, Google requests, emails sent, and disk. A day with a run stopped by the AI's usage limit says so. A project opens to its meetings, and a meeting opens from there.
- The disk tile shows the meetings, the speech-to-text model and Vinutes' own program apart, so it shows whether deleting old meetings frees much space.
- Each AI is asked for a short report after it runs, so its tokens can be counted. The words the window shows and the meeting's log are the same as before; when the AI reports an error, the log also keeps its report.
- Meetings recorded before this version are filled in once from their logs: AI runs and their minutes, minutes of audio and mail sent. Tokens and Google requests were not written down then; those days carry a Filled in tag.
- What is counted stays on the Mac, in ~/.config/vin-meeting-minutes-zh/usage/, as meeting ids, project names and numbers: no meeting titles, people's names or addresses.

## v0.4.8 (2026-10-19)

- An item under To confirm now goes once you have sent a Fix and the AI has answered, also when the AI finds the minutes already right. Before, the item came back.
- A To confirm line about one voice (Speaker B …, Speaker C …) goes once that voice is named or removed under People, and Fix with a name on it names the voice.
- A sentence typed into the Fix box goes to the AI but is no longer learned as the word: only a name or a term is learned.

## v0.4.7 (2026-10-19)

- Typing Chinese with Zhuyin or another input method, the Enter that picks a word no longer sends what is in the box under the minutes. A second Enter while the first sentence is on its way doesn't send it twice either.
- While the AI is changing the minutes, the box stays open. What you send meanwhile waits under To change and goes to the AI one after another, each answer showing as it comes in; ✕ takes a waiting one off. Opening another meeting or closing the window doesn't stop them. Before, the box was greyed out until the AI was done.
- A screenshot pasted into the box (⌘V) shows small above it and goes to the AI with your sentence, so it can see what you mean. It no longer becomes an attachment in section 8 of the minutes; the picture button beside the box still adds pictures there.
- Each item under To confirm has Fix and Skip beside Looks right. Fix opens a box that starts from the guess: what you type goes to the AI, the minutes change to it, and the right word is learned. Skip takes the item off and learns nothing. Before, a wrong guess could only be confirmed, which taught Vinutes the wrong word.
- Under People, a voice's menu ends with Remove Speaker C (or whichever letter), for a voice that is no one: the recording split one person in two, or picked up a noise. Its lines in the transcript keep their words without a speaker, the To confirm items about it go too, and Undo brings it back.

## v0.4.6 (2026-10-19)

- The minutes put the slides shown in a meeting in Meeting Details, right under the attendees, as Slides: [deck title](link), so readers find them first. When the AI can't find the link it writes Slides: [__], which shows under To fill in until someone pastes the link. Other files stay on their own Materials line.

## v0.4.5 (2026-10-19)

- Each project has a brief. The gear by the project's name opens Project settings on its first page, Brief: the project's people with what each one does, its terms with what they mean, and a few lines of background. The people are the same list as the People tab; the project's name and moving a meeting are on the second page.
- The AI that writes the minutes reads every project's brief, decides which project the meeting is, and writes names, who does what and terms as that brief has them, putting right the spellings the transcript keeps getting wrong. Before, it knew only the people on the calendar invitation.
- A name in the minutes that the project's brief doesn't have waits under To confirm as New name; Looks right adds the person, with what they do, to the brief.
- The People tab of a meeting with no calendar invitation starts from the attendees the minutes name and the voices you named, no longer from the whole project list. Taking someone off a meeting only says they weren't there; they stay in the project's brief, and the Brief page is where someone leaves the project.
- Looks right on a misheard word, and an edit Vinutes learns, now go into the project's brief; under the AI's note about your edits each word can go to the project brief or to the glossary instead. A meeting without a project still adds words to the glossary.

## v0.4.4 (2026-10-19)

- Item 5 of the setup checklist (the AI that writes the minutes) walks through four steps: pick Claude Code, Codex or Antigravity (each card names the account it needs), Vinutes installs it with its maker's own script, you sign in, and the AI answers one short test. Before, the checklist only opened each AI's install page, and the install was up to you in Terminal.
- Vinutes now asks about the AI's sign-in when it starts too: an AI that is installed but signed out opens the checklist, with Sign in again on item 5. Before, that showed only after a meeting, when its minutes could not be written.
- A recording started while the AI isn't set up still records. The menu-bar panel opens once with a yellow note and Set Up; the transcript is kept, and Write up again makes the minutes once the AI is ready.
- In the AI menu by the prompt box, an AI that isn't installed or signed in opens these steps for it. Before, it was greyed out and could not be picked.
- An AI installed from the checklist is connected to your meetings right away, the way install.sh connects the AI tools already on the Mac.
- The README no longer asks you to install an AI before installing Vinutes.
- install.sh downloads one small file from the counter on GitHub after it installs or updates the app, so its download count shows roughly how many Macs use Vinutes. Nothing about the Mac or its user is sent. A file named no-count in ~/.config/vin-meeting-minutes-zh (or VINUTES_NO_COUNT=1) leaves a Mac out.

## v0.4.3 (2026-10-18)

- The README shows the menu-bar panel, the meeting window and the floating bar with live captions (English, made-up meetings; docs/screenshots/demo_home.py makes those meetings again for new pictures).
- While recording, the meeting being recorded no longer shows up among the panel's recent meetings, and Pause has no blue ring around it when the panel opens.
- The times in the panel's recent meetings line up, whatever symbol each meeting has.

## v0.4.2 (2026-10-18)

- The menu-bar icon opens a panel instead of a menu. In the middle is a big round button: red with a white dot to start recording, white with a red ring and a red square to stop it (⌃⌥R still does both). While recording, the panel shows how long it has run with the level bars, and Pause.
- Under it are the last three meetings, then All Meetings (opens the meeting list), Settings and Quit in three equal buttons. Settings has the setup checklist, open at login, the two languages and the recordings folder.
- The bottom line shows the version. When GitHub has a newer one, Update to … sits beside it (not while recording).
- The Vinutes line at the top of the old menu, which did nothing when clicked, is gone, and so are More… and Discard this recording; a wrong recording is deleted from the meeting list.

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
