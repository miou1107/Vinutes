# File list

| File | What it is |
|---|---|
| `README.md` | What Vinutes is, which languages it handles, how to install and update it |
| `README.zh-TW.md` | The same in Traditional Chinese |
| `CHANGELOG.md` | What changed in each version |
| `FILELIST.md` | This list |
| `VERSION` | The version number; the update button compares it with GitHub |
| `SKILL.md` | How Chinese minutes are written (Traditional Chinese, Taiwan usage); the AI reads it for every Chinese meeting |
| `references/minutes-guide-en.md` | How English minutes are written, with the same eight sections; the AI reads it for every English meeting |
| `references/example-minutes-en.md` | A made-up, complete set of English minutes the AI uses as a model |
| `references/example-minutes.md` | A made-up, complete set of minutes the AI uses as a model |
| `references/glossary.md` | Common speech-recognition mistakes and their correct spelling |
| `recorder/Capture.swift` | What a recording hears: the microphone and the sound the Mac plays (an online meeting's other side), mixed into 錄音.caf |
| `recorder/MeetingRecorder.swift` | The menu-bar app: recording, pause and shortcuts, the floating bar with its level bars and live captions, notifications, the meeting window |
| `recorder/Captions.swift` | The live-caption helper (built as Contents/MacOS/VinutesCaptions): reads the recording as it grows and runs Apple's on-device transcriber; logs to ~/Library/Logs/Vinutes/captions.log |
| `recorder/app/` | The meeting window's page (`index.html`, `app.css`, `app.js`, `docblink.js`, `docfind.js`), copied into the app when it is built |
| `recorder/app/strings.js` | Every word the meeting window shows, in English and Traditional Chinese |
| `recorder/Info.plist` | The app's name, version and microphone permission text |
| `recorder/l10n/` | The microphone permission text in English and Chinese (`en.lproj`, `zh-Hant.lproj`) |
| `recorder/make_icon.swift` | Draws the app icon at install time |
| `recorder/install.sh` | Installs or updates Vinutes: Python packages, speech and voice models, builds and opens the app |
| `scripts/auto_minutes.py` | After a recording: transcript, calendar match, minutes by the chosen AI, Google Doc, draft email; also sends the email when the user presses Send |
| `scripts/minutes_app.py` | Everything the meeting window asks for: the list, syncing the Doc, saving edits, AI rewrites, comments, history, learning from the user's edits, archiving and deleting meetings, projects and tags |
| `scripts/ai_runner.py` | Runs Claude Code, Codex or Antigravity, each sandboxed to one meeting's folder |
| `scripts/transcribe.py` | Turns a recording into a transcript on the Mac (Whisper); audio is not uploaded |
| `scripts/connect_agents.py` | Adds Vinutes' MCP server to the AI tools installed on the Mac (Claude Code, Codex, Gemini CLI, Claude's app, Antigravity, Cursor); install.sh runs it |
| `scripts/mcp_server.py` | Vinutes as an MCP server: Claude Code searches and reads past meetings, and names speakers, adds notes, changes words, tags and projects when asked |
| `scripts/speakers.py` | Tells speakers apart by voice and remembers the names the user gives them |
| `scripts/doc_sync.py` | Keeps the Markdown minutes and the Google Doc in step, paragraph by paragraph, so comments stay put |
| `scripts/minutes_html.py` | Turns what was edited in the window's preview back into Markdown |
| `scripts/attachments.py` | Files, links and pictures added under the Doc: uploads them to Google Drive and lists them in the minutes' last section |
| `scripts/setup_check.py` | The setup checklist: models, AI sign-in, Google connection |
| `scripts/i18n.py` | Which language the app speaks (the user's pick, else the Mac's) and which language the minutes are written in |
| `scripts/strings.py` | Every message the Python scripts show, in English and Traditional Chinese |
| `scripts/google_setup.py` | Google sign-in and the user's `settings.json` |
| `scripts/md_to_docx.py` | Lays the minutes out as a Word file |
| `scripts/md_to_gdoc.py` | Publishes the minutes as a Google Doc, updating the same Doc each time |
| `scripts/gdoc_to_md.py` | Pulls a Google Doc back as Markdown |
| `scripts/workspace.py` | Gmail, Calendar and the company directory: reading, sending, invitations, and which calendar event a recording was |
| `scripts/vlog.py` | The scripts' log: one start and one end line per run in ~/Library/Logs/Vinutes/scripts.log, under 5 MB plus one older file |
| `scripts/notify.py` | Sends the Doc link through Google Docs sharing when Gmail is not available |
| `scripts/check_update.py` | Looks up the newest version on GitHub |
| `tests/` | `python3 -m unittest discover -s tests` |
| `.github/workflows/ci.yml` | The check GitHub runs on a clean Mac for every push and pull request: the Python tests, the meeting window's scripts, the installer, the plists and both Swift builds. main only takes changes that pass it |
| `prototypes/` | Design prototypes approved before building a screen |

The user's own files are not here. They live in `~/.config/vin-meeting-minutes-zh/` (settings, Google sign-in, glossary, voices, recordings), shared with the vin-meeting-minutes-zh skill.
