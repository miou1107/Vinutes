# Transcription bench

How Vinutes measures a change to the way a recording becomes a transcript, and what has been measured so far.
Everything here runs on a Mac with the app's own Python (`~/.config/vin-meeting-minutes-zh/venv/bin/python`,
which has mlx-whisper, sherpa-onnx and OpenCC) against real recordings; nothing leaves the Mac. The
measurements below were taken on 2026-10-20 on an Apple-silicon Mac with three real meetings (40, 58 and 44
minutes, Chinese, recorded with the Mac's microphone in a meeting room).

## The method

There is no hand-made transcript of a whole meeting, so a change is judged three ways, and a conclusion needs
all three to agree:

1. **Against a bigger model.** `judge.py` transcribes the recording with whisper-large-v3 (not turbo, about twice
   as slow) and reports, for every transcript in the folder, the share of the judge's characters that differ.
   The judge is a Whisper too, so this is fair between two Whisper runs and only indicative for another recogniser.
2. **Against the model's own noise.** The same recording transcribed twice the same way (`pieces.py --twice`)
   already differs: by 12% of its characters on the 40-minute meeting, and by 1.9 points in its distance to the
   judge. A change smaller than that is not a change. `breakdown.py` shows where two transcripts differ, per
   five-minute stretch: the noisy stretches (questions from the floor, far from the microphone) move by 36 to 44%
   between two runs, the clear ones by 0 to 5%.
3. **Names and terms.** `terms.py` counts how often each word of the glossary and of the project briefs appears in
   each transcript. The minutes care about the company's names more than about any other character, and a Whisper
   judge cannot score another model on them.

A folder per recording holds the job (`job/錄音.caf`), the transcripts (`A.txt` whole file, `A2.txt` whole file
again, `B.txt` pieces, `C.txt` judge, `agc.txt`, `denoise.txt`, `qwen.txt`, `sense.txt`) and the JSON reports.

```bash
PY=~/.config/vin-meeting-minutes-zh/venv/bin/python
$PY docs/bench/pieces.py ~/.config/vin-meeting-minutes-zh/recordings/20261019-105319/錄音.m4a /tmp/bench/m1 --twice
$PY docs/bench/judge.py /tmp/bench/m1
$PY docs/bench/breakdown.py /tmp/bench/m1
$PY docs/bench/clean.py /tmp/bench/m1               # pip install noisereduce first
$PY docs/bench/models.py sense /tmp/bench/m1        # the SenseVoice model folder and silero_vad.onnx under docs/bench/models/
$PY docs/bench/models.py qwen /tmp/bench/m1         # pip install mlx-qwen3-asr opencc-python-reimplemented in a venv of its own
$PY docs/bench/terms.py /tmp/bench/m1 A B C qwen sense
```

## Transcribing in pieces during the recording (v0.4.16, issue #1)

Share of the judge's characters that differ:

| Meeting | Whole file (A) | Whole file again (A2) | Pieces (B) |
|---|---|---|---|
| 10/19, 40 min, 7 pieces | 25.3% | 23.4% | 25.1% |
| 10/20, 58 min, 11 pieces | 20.7% | | 21.9% |
| 10/20, 44 min, 8 pieces | 28.0% | | 27.7% |

The pieces' transcript is as far from the judge as the one-go transcript, within the model's own 1.9-point noise.
The character count per five-minute stretch matches to within 1 to 2% everywhere, so nothing is lost at a cut.

Glossary terms found, whole file against pieces: 64 against 81 on the 10/19 meeting (KOL 6 against 11, 台灣 PASS
6 against 12), 2 against 2 on the 58-minute meeting (a data meeting with few glossary words), 13 against 22 on the
44-minute meeting (台灣 PASS 2 against 11). The glossary hint reaches the model once per piece instead of once per
meeting, so the pieces spell the company's names right more often.

Time on this Mac: a five-minute piece takes 11 to 16 s in the background; after Stop the rest took 19, 21 and
14 s, against 148, 152 and 132 s for the whole file at once.

Two things learned on the way, both kept out of the shipped code:

- **A prompt made of the previous piece's last words hurts.** Giving each piece the last 80 characters of the
  piece before (as the issue first asked) made the model skip most of the next piece's first half minute on a real
  meeting (4:38 to 5:01 came back empty), and with a full company glossary the prompt overran Whisper's 223-token
  window, pushing the glossary out. Pieces get exactly the prompt a whole recording gets.
- **The model sometimes gets stuck** repeating one character for a whole segment (seen once in three meetings,
  inside a piece). `transcribe.py` drops such a segment in every transcript since v0.4.16.

## Cleaning the audio before Whisper (not shipped)

| Meeting | Raw | Gain levelling (agc) | Levelling + noise reduction |
|---|---|---|---|
| 10/19, 40 min | 25.3% | 23.7% | 28.2% |
| 10/20, 58 min | 20.7% | 20.6% | 21.5% |
| 10/20, 44 min | 28.0% | 28.5% | 29.5% |

Levelling the quiet speakers up to the loud ones changes nothing across the three meetings (one point either way,
inside the noise). Spectral-gating noise reduction (the `noisereduce` package, light setting) makes every meeting
worse: it takes part of the far voices with the noise. This matches the published results: enhancement in front
of Whisper gains a point at best and often loses ([EUSIPCO 2024](https://arxiv.org/pdf/2406.12699),
["When De-noising Hurts", Dec 2025](https://arxiv.org/pdf/2512.17562)); Whisper's training data is noisy enough.
Neither is in the app.

## Other recognisers (measured 2026-10-20; Qwen3-ASR shipped as a choice in v0.4.17)

For Chinese meetings Whisper is the weak link, not the audio: on the WenetSpeech meeting subset the published
character error rates are 18.9% for whisper-large-v3, 6.7% for SenseVoice-L, 7.0% for Paraformer-large and
lower still for Qwen3-ASR and FireRedASR (all reported by the model makers,
[FireRedASR's table](https://github.com/FireRedTeam/FireRedASR), [Qwen3-ASR report](https://arxiv.org/pdf/2601.21337)).
Two of them run on a Mac and were tried on the same three meetings: Qwen3-ASR 1.7B through MLX
(`mlx-qwen3-asr`, the 8-bit build, 2.2 GB plus a 1.8 GB aligner for timestamps, Apache-2.0) and SenseVoice through sherpa-onnx on the CPU
(FunASR model licence). FireRedASR's best model is an 8B LLM and too heavy for a laptop. A Whisper judge cannot
rank them, so they are compared on what they write.

Glossary terms found (the names the minutes need):

| Meeting | Whisper whole | Whisper pieces | SenseVoice | Qwen3-ASR |
|---|---|---|---|---|
| 10/19, 40 min | 64 | 81 | 45 | 88 |
| 10/20, 58 min | 2 | 2 | 4 | 3 |
| 10/20, 44 min | 13 | 22 | 11 | 26 |

Characters transcribed in the whole meeting (more is better here: the far voices either come out or they don't):

| Meeting | Whisper whole | Whisper pieces | SenseVoice | Qwen3-ASR |
|---|---|---|---|---|
| 10/19, 40 min | 9,448 | 9,770 | 7,820 | 9,956 |
| 10/20, 58 min | 10,362 | 10,516 | 11,222 | 11,385 |
| 10/20, 44 min | 7,742 | 8,082 | 8,190 | 8,508 |

Qwen3-ASR hears the most and names the most. In the 10/19 meeting's questions from the floor (minute 30),
Whisper wrote 教育國立人 / 賺款 / 票數 where Qwen3-ASR wrote 高鐵國旅 / 轉換 / 跳出去 / 加入購物車, which is what was
said; in the 58-minute meeting Whisper's 把理科帶進來臺灣玩 is Qwen3-ASR's 把旅客帶進來臺灣玩. SenseVoice reads
the clear stretches well but its voice detector drops the far voices (the 10/19 meeting's last 15 minutes came
out at a third to a half of Whisper's length), and it found the fewest names. Qwen3-ASR's weak spots: no
punctuation, long run-on lines (the minutes AI copes), a name it has never seen comes out by sound (臺灣巴斯 for
Taiwan PASS) because the glossary hint was not given to it, and it is slow: 559, 490 and 330 s for the three
meetings on this Mac (while SenseVoice ran beside it) against 148, 152 and 132 s for Whisper turbo. In pieces
during the recording that is about a minute per five-minute piece, which the background still absorbs.

### Qwen3-ASR with the glossary as its context (the shipped path, measured 2026-10-21)

v0.4.17 gives Qwen3-ASR the glossary hint as its `context`, the way Whisper gets it as a prompt, and writes one
line per sentence with the aligner's times. The three meetings again through `scripts/transcribe.py` with
`MINUTES_SPEECH_MODEL=qwen3-asr`, glossary terms found:

| Meeting | Whisper whole | Whisper pieces | Qwen3-ASR, no context | Qwen3-ASR, glossary context |
|---|---|---|---|---|
| 10/19, 40 min | 64 | 81 | 88 | 97 |
| 10/20, 58 min | 2 | 2 | 3 | 8 |
| 10/20, 44 min | 13 | 22 | 26 | 35 |

With the context Taiwan PASS comes out as the glossary spells it, and the lines are punctuated. One thing to
know before trusting a count like this: over a quiet stretch Qwen3-ASR sometimes writes its context down as a
sentence, the whole term list joined by 、 as if someone had read it out (four times in the 44-minute meeting,
once in the 58-minute one). Counted naively those two meetings read 131 and 32. `transcribe.echoes()` drops a
sentence that runs through four or more of the context's terms in the context's own order; the table above is
after that filter, and a sentence that names three people in passing is kept. Any jump in a term count should
be checked that way first: open the transcript and look at the lines the extra hits are on.

Timing alone on this Mac: 572 s for the 40-minute meeting and 295 s for the 44-minute one; the 58-minute meeting
took 1214 s but a browser and a Swift build ran beside it. A clean five-minute piece is about 50 s with Qwen3-ASR
against 40 s with Whisper turbo, so the pieces during a recording keep pace.

Conclusion: the next quality step for Chinese meetings is Qwen3-ASR as the transcriber (with the glossary given
to it as context, and Whisper kept for other languages or as a fallback), not audio cleaning. Not built yet; it
needs the model in install.sh (2.5 GB), the pieces path in live_transcribe.py, and the same bench run again.
