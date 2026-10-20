"""Other recognisers over the same recording, written in the transcript's own format (Taiwan wording through
OpenCC) and measured against the judge and against Whisper's own transcript.

  python docs/bench/models.py qwen <out folder> [model]    Qwen3-ASR through mlx-qwen3-asr (pip install mlx-qwen3-asr);
                                                            default model moona3k/mlx-qwen3-asr-1.7b-8bit
  python docs/bench/models.py sense <out folder> [model dir] [vad.onnx]
                                                            SenseVoice through sherpa-onnx (in the app's venv), cut
                                                            into utterances by the Silero voice detector; the model
                                                            folder is sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17
                                                            from the sherpa-onnx releases, the detector silero_vad.onnx

Each writes <name>.txt and <name>.json in the folder.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import RATE, compare, load_wav, say, stamp, to_wav  # noqa: E402


def measure(folder: Path, name: str, rows, took: float, extra: dict):
    (folder / f'{name}.txt').write_text('\n'.join(f'{stamp(s)} {t}' for s, t in rows) + '\n', encoding='utf-8')
    out = {'seconds': round(took), 'lines': len(rows), **extra}
    for other in ('C', 'A'):
        if (folder / f'{other}.txt').exists():
            out[f'{other}_vs_{name}'] = compare(folder / f'{other}.txt', folder / f'{name}.txt')['changed_pct']
    (folder / f'{name}.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    say(f'{name}: {len(rows)} lines, {took:.0f}s, {out}')


def qwen(folder: Path, model: str):
    from mlx_qwen3_asr import transcribe
    from opencc import OpenCC
    convert = OpenCC('s2twp').convert
    wav = folder / 'job' / 'audio16k.wav'
    to_wav(next((folder / 'job').glob('*.caf')), wav)
    say(f'{folder.name}: Qwen3-ASR {model}')
    began = time.time()
    result = transcribe(str(wav), model=model, language='Chinese', return_timestamps=True)
    took = time.time() - began
    merged = []                                       # word-level segments joined into lines of about a sentence
    for seg in result.segments:
        text = convert((seg.text or '').strip())
        if not text:
            continue
        start, end = float(seg.start), float(seg.end)
        if merged and start - merged[-1][1] < 0.8 and len(merged[-1][2]) < 40:
            merged[-1] = (merged[-1][0], end, merged[-1][2] + text)
        else:
            merged.append((start, end, text))
    measure(folder, 'qwen', [(s, t) for s, _, t in merged], took, {'model': model})


def sense(folder: Path, model_dir: Path, vad_model: Path):
    import sherpa_onnx
    from opencc import OpenCC
    convert = OpenCC('s2twp').convert
    wav = folder / 'job' / 'audio16k.wav'
    to_wav(next((folder / 'job').glob('*.caf')), wav)
    audio = load_wav(wav)
    say(f'{folder.name}: SenseVoice through sherpa-onnx')
    began = time.time()
    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(model_dir / 'model.int8.onnx'), tokens=str(model_dir / 'tokens.txt'), num_threads=8,
        language='zh', use_itn=True)
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(vad_model)
    config.silero_vad.threshold = 0.5
    config.silero_vad.min_silence_duration = 0.4
    config.silero_vad.min_speech_duration = 0.25
    config.silero_vad.max_speech_duration = 15
    config.sample_rate = RATE
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=120)
    window = config.silero_vad.window_size
    rows = []

    def drain():
        while not vad.empty():
            seg = vad.front
            stream = recognizer.create_stream()
            stream.accept_waveform(RATE, seg.samples)
            recognizer.decode_stream(stream)
            text = convert(stream.result.text.strip())
            if text:
                rows.append((seg.start / RATE, text))
            vad.pop()
    for i in range(0, len(audio) - window + 1, window):
        vad.accept_waveform(audio[i:i + window])
        drain()
    vad.flush()
    drain()
    measure(folder, 'sense', rows, time.time() - began, {'model': model_dir.name})


def main():
    kind, folder = sys.argv[1], Path(sys.argv[2]).expanduser()
    if kind == 'qwen':
        qwen(folder, sys.argv[3] if len(sys.argv) > 3 else 'moona3k/mlx-qwen3-asr-1.7b-8bit')
    elif kind == 'sense':
        here = Path(__file__).parent / 'models'
        sense(folder, Path(sys.argv[3]) if len(sys.argv) > 3 else here / 'sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17',
              Path(sys.argv[4]) if len(sys.argv) > 4 else here / 'silero_vad.onnx')
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
