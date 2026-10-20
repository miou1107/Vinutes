"""Does cleaning the audio before Whisper help? Two cleaned copies of the recording are transcribed the usual way:

  agc      quiet speech raised towards the loud speech (gain per 50 ms frame, smoothed over a second, never below
           one, silence left alone)
  denoise  spectral-gating noise reduction (the noisereduce package, light), then the same gain

  python docs/bench/clean.py <out folder>      needs job/*.caf and A.txt; writes agc.txt, denoise.txt, clean.json
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import RATE, compare, load_wav, save_wav, say, to_wav, whisper  # noqa: E402


def agc(audio, frame_s=0.05, smooth_s=1.0, max_gain=8.0):
    import numpy as np
    step = int(frame_s * RATE)
    n = len(audio) // step
    x = audio[:n * step].reshape(n, step)
    rms = np.sqrt((x * x).mean(axis=1)) + 1e-9
    speech = rms > np.percentile(rms, 10) * 2
    if not speech.any():
        return audio
    target = np.percentile(rms[speech], 90)
    gain = np.ones(n)
    gain[speech] = np.clip(target / rms[speech], 1.0, max_gain)
    k = max(1, int(smooth_s / frame_s))
    gain = np.convolve(gain, np.ones(k) / k, mode='same')
    out = audio.copy()
    out[:n * step] *= np.repeat(gain, step)
    peak = np.abs(out).max()
    if peak > 0.98:
        out *= 0.98 / peak
    return out.astype('float32')


def denoise(audio, prop=0.6):
    import noisereduce as nr
    return nr.reduce_noise(y=audio, sr=RATE, prop_decrease=prop, stationary=True, n_jobs=1).astype('float32')


def main():
    folder = Path(sys.argv[1]).expanduser()
    caf = next((folder / 'job').glob('*.caf'))
    wav = folder / 'job' / 'audio16k.wav'
    to_wav(caf, wav)
    audio = load_wav(wav)
    judge = folder / 'C.txt'
    result = {}
    for name, make in (('agc', lambda a: agc(a)), ('denoise', lambda a: agc(denoise(a)))):
        began = time.time()
        save_wav(folder / f'{name}.wav', make(audio))
        say(f'{name} made in {time.time() - began:.0f}s')
        result[f'{name}_seconds'] = whisper(folder / f'{name}.wav', folder / f'{name}.txt')
        if judge.exists():
            result[name] = compare(judge, folder / f'{name}.txt')['changed_pct']
            say(f'{name} vs judge {result[name]}%')
    if judge.exists() and (folder / 'A.txt').exists():
        result['raw'] = compare(judge, folder / 'A.txt')['changed_pct']
    (folder / 'clean.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
    say(f'clean done: {result}')


if __name__ == '__main__':
    main()
