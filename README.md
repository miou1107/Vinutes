# Vinutes

Vinutes records your meetings on a Mac and turns them into formal, well-structured minutes. The minutes are published as a Google Doc your colleagues can edit and comment on, and the follow-up email goes out only when you press Send.

> **Status: early.** Vinutes runs on Macs with Apple silicon. The app speaks English and Traditional Chinese. 中文說明：[README.zh-TW.md](README.zh-TW.md)

## What it does

- **Records from the menu bar.** Start with one click or ⌃⌥R, pause and resume while the meeting goes on. In an online meeting it records the other side too, also with headphones on (macOS 14.2 and later).
- **Transcribes on your Mac.** Audio is turned into text locally with Whisper and is not uploaded.
- **Tells speakers apart** by their voices, and remembers the names you give them.
- **Writes the minutes with the AI you already use:** Claude Code, Codex or Antigravity. Each one runs in a sandbox that can only read and write that meeting's folder.
- **Matches the recording to your Google Calendar** to fill in the title, time, place and attendees.
- **Publishes a Google Doc** and keeps it in sync: your colleagues' edits and comments show up in the app, and when you edit in the app only the paragraphs you changed are updated, so their comments stay where they were.
- **Learns from your corrections.** A misheard name you fix once goes into your glossary, and the next meeting gets it right.
- **Prepares the email** to the attendees. Nothing is sent until you press Send.
- **Keeps the list tidy.** Archive the meetings you no longer need to see, or delete them: the recording, transcript and minutes go to the Trash, and the Google Doc to Google Drive's trash. Select several at once, or right-click one.

## Languages

**The app** follows your Mac's language: Traditional Chinese if Chinese comes first in System Settings > Language & Region, English otherwise. Pick English or Traditional Chinese under Settings > App Language in the menu bar, or at the top of the setup checklist; Same as Mac goes back to following the Mac.

**The meeting.** Vinutes listens to the start, middle and end of each recording and decides which language was spoken. If your meetings are always in one language, pick it under Settings > Meeting Language and Vinutes stops guessing.

**The minutes** are written in the meeting's language when it is English or Chinese. A meeting in any other language gets its minutes in the app's language, and the transcript keeps the original words.

How well each language is heard, measured on real speech (24 read sentences per language, October 2026):

| | Languages | Transcript errors per 100 words (characters for Chinese, Japanese, Korean, Thai) |
|---|---|---|
| Works well | English, Chinese, Japanese, Korean, Spanish, French, German | 3–7 |
| Usable, check the minutes more closely | Vietnamese, Indonesian, Filipino | 10–11 |
| Usable, more errors | Thai, Cantonese (treated as a Chinese meeting) | about 18 |

Names, numbers and dates are what most often come out wrong. In a meeting held in a language your team doesn't read, check them in the minutes before you send.

## Requirements

- A Mac with Apple silicon (M1 or newer)
- Xcode Command Line Tools (`xcode-select --install`) and Python 3.10 or newer
- One AI command-line tool installed and signed in: [Claude Code](https://docs.claude.com/en/docs/claude-code/setup), [Codex](https://github.com/openai/codex) or [Antigravity](https://antigravity.google/)
- For Google Docs, Gmail and Calendar: a Google account and a one-time Google Cloud setup. The app walks you through it step by step; it takes about 15 minutes.

## Install

```bash
git clone https://github.com/miou1107/Vinutes ~/Vinutes
~/Vinutes/recorder/install.sh
```

The first run downloads the speech model (about 1.6 GB), so it can take a while. When it finishes, a microphone icon appears in the menu bar. Open the meeting window and go through the setup checklist once.

## Use your meetings in Claude Code and other AI tools

Vinutes is also an MCP server. Installing or updating Vinutes connects it to the AI tools on your Mac: Claude Code, Codex, Gemini CLI, Claude's desktop app, Antigravity and Cursor (restart the last three once). To connect a tool installed later, run:

```bash
~/.config/vin-meeting-minutes-zh/venv/bin/python ~/Vinutes/scripts/connect_agents.py
```

Then, in any folder, ask Claude Code (or any of them) "what did last week's project meeting decide?" and it searches your minutes and transcripts and answers with the meeting's date and title. When you ask it to, it can also name a speaker, add a paragraph to section 8, change words in the minutes, and set tags or the project; the Google Doc follows, and the meeting's history says Claude Code made the change. Deleting a meeting and sending mail stay in Vinutes.

## Update

When a newer version is on GitHub, the meeting window shows an update button. You can also update by hand:

```bash
git -C ~/Vinutes pull && ~/Vinutes/recorder/install.sh
```

## Where your data lives

Your settings, Google sign-in, glossary and recordings are kept in `~/.config/vin-meeting-minutes-zh/`, never in this folder, so updating or reinstalling Vinutes leaves them alone. The folder is shared with the [vin-meeting-minutes-zh](https://github.com/miou1107/vin-meeting-minutes-zh) skill, so you sign in to Google only once for both.

## What is in this repository

| Path | What it is |
|---|---|
| `recorder/` | The Mac app (Swift) and the meeting window (HTML, CSS, JavaScript), plus `install.sh` |
| `scripts/` | Python: transcription, speakers, writing the minutes, Google Docs sync, Gmail and Calendar, the setup checklist |
| `SKILL.md`, `references/` | How the minutes are written: `SKILL.md` for Chinese minutes (Taiwan usage), `references/minutes-guide-en.md` for English ones; the AI reads the right one for every meeting |
| `tests/` | `python3 -m unittest discover -s tests` |

## Only have a transcript?

If you just want an AI to turn a transcript into minutes, without recording, use the [vin-meeting-minutes-zh](https://github.com/miou1107/vin-meeting-minutes-zh) skill instead.
