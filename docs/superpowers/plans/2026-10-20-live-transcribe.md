# Transcribe while the meeting is still being recorded — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When the user presses Stop, most of the meeting is already text. Vinutes transcribes the recording in
pieces of about five minutes while it is being recorded, so the transcript is ready about a minute after the
meeting ends instead of four to seven minutes later (an hour takes about 260 s on the author's Mac today).

**Spec:** issue #1 (Vin 2026-10-20: 「1 go」).

**Architecture:**

- `scripts/live_transcribe.py <job folder>` is a helper the app starts when a recording begins (like the caption
  helper, but Python). At low priority it follows `錄音.caf` as it grows (16 kHz mono 16-bit PCM; the samples
  after the CAF data chunk's header). Every time 5½ minutes of audio past the last cut exist, it finds the quietest
  half second between 4½ and 5½ minutes past the last cut, cuts there, and transcribes that piece with Whisper. Each
  finished piece is `分段/0001.json`, `0002.json`, … (`start`, `end` in seconds from the recording's beginning,
  `language`, `segments` as [start, end, text] in recording time). The language is detected once, on the first
  piece, unless the setting fixes it. Each piece gets exactly the prompt a whole recording gets (the glossary hint
  for Chinese, nothing for English). The last words of the piece before were tried as an extra prompt and dropped:
  on a real meeting the model then skipped most of the first half minute of the next piece, and with a full
  glossary the prompt overran Whisper's 223-token window. While a piece is being transcribed, `分段/working.json`
  holds the helper's pid. The helper exits when `job.json` has an `ended` time (after finishing the piece in hand, never
  starting another), when the app that started it is gone (after the piece in hand), or when the setting
  `live_transcribe` is false.
- `scripts/transcribe.py <audio> [out] [--pieces <dir>]` reuses the pieces: it waits for `working.json` (at most
  three minutes, then stops that helper, after checking the pid really is a live_transcribe.py), takes the longest
  run of pieces that starts at 0 and joins end to start, transcribes only the audio after the last piece (with the
  same hint, in the pieces' language),
  and writes `逐字稿.txt` and `逐字稿.json` exactly as before. The transcription and assembly code is shared
  between the helper and the final run.
- `auto_minutes.py` passes `--pieces <job>/分段` and removes the folder once the transcript is written. Pause and
  resume need nothing: the file simply stops growing. A crash or restart keeps the finished pieces on disk, and the
  recovered job reuses them.
- Speakers stay at the end (`speakers.py` after the transcript): the voice prints of an hour take well under a
  minute, and grouping needs the whole meeting anyway. Measured on the author's Mac during this work; noted in the
  issue if it turns out otherwise.
- The app (`MeetingRecorder.swift`): a `LiveTranscriber` that runs the helper through the same login shell and
  Python as the other scripts, started in `beginRecording`, logged when it ends; nothing on screen changes. The
  helper is not killed at Stop: it ends by itself, and the write-up waits for it.

## Tasks

1. `transcribe.py`: split into `transcribe_range(audio, lang, prompt, offset)` and `assemble(segments, lang)`; add
   `--pieces`, `pieces_in(dir, audio_seconds)`, `wait_for_helper(dir)`. Tests: class `Pieces` (contiguity, a gap,
   a piece past the end of the audio, the final run with a fake Whisper over a CAF file made with afconvert).
2. `live_transcribe.py`: `caf_data_start(head)`, `available_seconds(path)`, `quietest_cut(audio, lo, hi)`,
   `Runner` with an injectable transcriber and clock, `main`. Tests: class `Live` (the CAF header, the cut in a
   silent gap, a run over a file that grows between polls, stop after `ended`, the setting off).
3. `auto_minutes.py`: `--pieces`, remove `分段` after the transcript; log how many pieces were reused.
4. Swift: `LiveTranscriber`, started in `beginRecording`; `recorder.json` config reused; log lines.
5. Measure on a real recording (replayed as a growing file) and on a real call later; CHANGELOG v0.4.16, README
   line (EN, ZH), FILELIST, VERSION, issue #1 tasks ticked.
