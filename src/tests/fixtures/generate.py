"""Deterministic, copyright-free audio. Writes only into a caller-owned temp directory.

Run: python generate.py /tmp/mixer-fixtures
FLAC containers retain .wav names because the engine uses that path contract;
soundfile decodes by header. No source downloads, demucs, or archival renders.
"""
from pathlib import Path
import json
import numpy as np
import soundfile as sf
SR = 44100
BAR = 240 / 174

def pulse(bpm=174, seconds=12, seed=7):
    rng = np.random.default_rng(seed)
    y = np.zeros(int(SR * seconds), np.float32)
    n = int(.045 * SR)
    t = np.arange(n) / SR
    hit = (.4 * np.sin(2*np.pi*70*t) + .08*rng.standard_normal(n)) * np.exp(-t*100)
    for sec in np.arange(.1, seconds-.05, 60/bpm):
        k = round(sec*SR)
        y[k:k+n] += hit[:len(y[k:k+n])]
    return y

def build(root):
    root = Path(root); (root / 'st').mkdir(parents=True, exist_ok=True)
    nb = 32; n = round(nb*BAR*SR)
    t = np.arange(n) / SR
    beat = .12*np.sin(2*np.pi*60*t) + pulse(seconds=n/SR)*.7
    melody = .025*np.sin(2*np.pi*440*t)
    for name, intro in [('fixture_out', 0), ('fixture_in', 12)]:
        drums = beat.copy(); drums[:round(intro*BAR*SR)] = 0
        full = np.column_stack([drums+melody, drums+melody]).astype(np.float32)
        stem = np.column_stack([drums, drums]).astype(np.float32)
        for suffix, audio in [('', full), ('.dnb', stem)]:
            sf.write(root/'st'/f'{name}{suffix}.wav', audio, SR, format='FLAC', subtype='PCM_16')
        grid = dict(downs=[i*BAR for i in range(nb)], bar=dict(
            all=[-16.]*nb, drums=[-80.]*intro+[-18.]*(nb-intro), low=[-22.]*nb, voc=[-80.]*nb))
        (root/'st'/f'{name}.json').write_text(json.dumps(grid))
    return root

if __name__ == '__main__':
    import sys
    build(sys.argv[1])
