# File list

| File | What it is |
|---|---|
| `README.md` | What Vinutes is, how to install and update it |
| `CHANGELOG.md` | What changed in each version |
| `FILELIST.md` | This list |
| `VERSION` | The version number; the update button compares it with GitHub |
| `SKILL.md` | How the minutes are written (Traditional Chinese, Taiwan usage); the AI reads it for every meeting |
| `references/example-minutes.md` | A made-up, complete set of minutes the AI uses as a model |
| `references/glossary.md` | Common speech-recognition mistakes and their correct spelling |
| `recorder/MeetingRecorder.swift` | The menu-bar app: recording, pause and shortcuts, notifications, the meeting window |
| `recorder/app/` | The meeting window's page (`index.html`, `app.css`, `app.js`, `docblink.js`, `docfind.js`), copied into the app when it is built |
| `recorder/Info.plist` | The app's name, version and microphone permission text |
| `recorder/make_icon.swift` | Draws the app icon at install time |
| `recorder/install.sh` | Installs or updates Vinutes: Python packages, speech and voice models, builds and opens the app |
| `scripts/auto_minutes.py` | After a recording: transcript, calendar match, minutes by the chosen AI, Google Doc, draft email; also sends the email when the user presses Send |
| `scripts/minutes_app.py` | Everything the meeting window asks for: the list, syncing the Doc, saving edits, AI rewrites, comments, history, learning from the user's edits |
| `scripts/ai_runner.py` | Runs Claude Code, Codex or Antigravity, each sandboxed to one meeting's folder |
| `scripts/transcribe.py` | Turns a recording into a transcript on the Mac (Whisper); audio is not uploaded |
| `scripts/speakers.py` | Tells speakers apart by voice and remembers the names the user gives them |
| `scripts/doc_sync.py` | Keeps the Markdown minutes and the Google Doc in step, paragraph by paragraph, so comments stay put |
| `scripts/minutes_html.py` | Turns what was edited in the window's preview back into Markdown |
| `scripts/attachments.py` | Files, links and pictures added under the Doc: uploads them to Google Drive and lists them in the minutes' last section |
| `scripts/setup_check.py` | The setup checklist: models, AI sign-in, Google connection |
| `scripts/google_setup.py` | Google sign-in and the user's `settings.json` |
| `scripts/md_to_docx.py` | Lays the minutes out as a Word file |
| `scripts/md_to_gdoc.py` | Publishes the minutes as a Google Doc, updating the same Doc each time |
| `scripts/gdoc_to_md.py` | Pulls a Google Doc back as Markdown |
| `scripts/workspace.py` | Gmail, Calendar and the company directory: reading, sending, invitations |
| `scripts/notify.py` | Sends the Doc link through Google Docs sharing when Gmail is not available |
| `scripts/check_update.py` | Looks up the newest version on GitHub |
| `tests/` | `python3 -m unittest discover -s tests` |
| `prototypes/` | Design prototypes approved before building a screen |

The user's own files are not here. They live in `~/.config/vin-meeting-minutes-zh/` (settings, Google sign-in, glossary, voices, recordings), shared with the vin-meeting-minutes-zh skill.
