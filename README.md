# Vinutes

Vinutes records your meetings on a Mac and turns them into formal, well-structured minutes. The minutes are published as a Google Doc your colleagues can edit and comment on, and the follow-up email goes out only when you press Send.

> **Status: early.** Vinutes runs on Macs with Apple silicon. The app and the minutes are in Traditional Chinese today. English is being added next and will become the default language, followed by Chinese.

## What it does

- **Records from the menu bar.** Start with one click or ⌃⌥R, pause and resume while the meeting goes on.
- **Transcribes on your Mac.** Audio is turned into text locally with Whisper and is not uploaded.
- **Tells speakers apart** by their voices, and remembers the names you give them.
- **Writes the minutes with the AI you already use:** Claude Code, Codex or Antigravity. Each one runs in a sandbox that can only read and write that meeting's folder.
- **Matches the recording to your Google Calendar** to fill in the title, time, place and attendees.
- **Publishes a Google Doc** and keeps it in sync: your colleagues' edits and comments show up in the app, and when you edit in the app only the paragraphs you changed are updated, so their comments stay where they were.
- **Learns from your corrections.** A misheard name you fix once goes into your glossary, and the next meeting gets it right.
- **Prepares the email** to the attendees. Nothing is sent until you press Send.

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
| `SKILL.md`, `references/` | How the minutes are written (Traditional Chinese, Taiwan usage); the AI reads these for every meeting |
| `tests/` | `python3 -m unittest discover -s tests` |

## Only have a transcript?

If you just want an AI to turn a transcript into minutes, without recording, use the [vin-meeting-minutes-zh](https://github.com/miou1107/vin-meeting-minutes-zh) skill instead.
