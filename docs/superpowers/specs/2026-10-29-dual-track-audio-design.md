# Dual-track recording (mic / system audio) — design

2026-10-29. Branch `worktree-vin+dual-track-audio`.

## Why

A recording mixes the microphone (your voice) and the Mac's sound (the other
side of an online meeting) into one 16 kHz mono `錄音.caf`. When the two are
mixed we cannot tell, after the fact, whether the other side was captured at
all — the mix always has the microphone in it, so it is never silent even when
the system-audio tap delivered nothing.

Two real situations make this matter:

- **Bluetooth headset meetings.** When a Bluetooth headset is both the mic and
  the output, macOS puts it into the phone-grade (HFP) narrowband mode. The
  other side comes through that narrow, unstable path, and its quality drops.
- **macOS 26 process-tap bug.** `AudioHardwareCreateProcessTap` can deliver
  all-zero buffers for stretches of minutes while the IO callback keeps firing
  normally (Apple forum thread 825780, unresolved). All-zero is
  indistinguishable from genuine silence, so it is easy to miss.

Investigation on 2026-10-29 (a 43-minute live recording) found the audio was in
fact fine — the spectrogram showed clear speech in the voice band — so this is a
*safety net*, not a fix for a live failure.

## Goal (this change, phase 1)

Record the microphone and the system audio as their own tracks **alongside** the
existing mixed track, so that:

- it is visible whether the other side was captured (is `other.caf` silent?),
- the two speakers can be separated later (your voice vs. the other side),
- diagnosing a quiet-other-side report no longer needs a live reproduction.

## Non-goals (explicitly out of phase 1)

- **Auto-rebuild on all-zero.** Detecting the all-zero state and tearing down +
  recreating the tap and aggregate device. It needs a controlled Bluetooth
  reproduction to confirm when it triggers, and it carries a brief-dropout
  tradeoff on every rebuild that is the user's decision. Deferred to phase 2.
- **Recovering Bluetooth narrowband quality.** That is a hardware limit of the
  HFP path; software cannot restore frequencies the headset never sent.
- **Changing transcription or captions.** They keep reading `錄音.caf`.

## Design decisions (made here, open to review)

1. **Keep `錄音.caf` (the mix) exactly as it is.** Captions (`VinutesCaptions`)
   and the transcriber both read it; nothing about their path changes.
2. **Add two sibling files in the same job folder:** `me.caf` (microphone only)
   and `other.caf` (system audio only), 16 kHz mono 16-bit, written as the audio
   comes in, on the same writer queue as the mix.
3. **`other.caf` carries exactly the samples the tap delivered** — no mic, no
   mixing — so its size and level answer "did the other side come in?" directly.
4. **Record them in `job.json`** (`me`, `other` keys) so later tooling can find
   them; absence of the keys means an older recording with the mix only.
5. **Three tracks coexist.** Write volume roughly triples (16 kHz mono 16-bit is
   ~32 KB/s per track, ~115 MB/hour for three). Acceptable; the mix cannot be
   dropped because captions/transcription depend on it.

## Left to the builder

- Phase 2 (auto-rebuild) only. Phase 1 above is fully specified.

## Verification

- Baseline build of the recorder is clean (`swiftc -Onone`, 2026-10-29).
- Phase 1 done means: a recording produces `錄音.caf`, `me.caf`, `other.caf`;
  with system audio playing and the mic quiet, `other.caf` is non-silent; with
  the mic muted and system quiet, `me.caf` reflects it. Confirmed by a small
  harness that drives `MeetingCapture` with synthetic buffers, then by a real
  Bluetooth meeting afterward.
