"""Per-bar grid phase of a stretched track (st/<id>.wav vs its st/<id>.json downs).
Kick-band (<150 Hz) and snare-band (150-2k) onset strength (librosa, hop 128 @22.05k = 5.8 ms), circular mean at the beat
period inside each bar -> ms the hits sit after the grid beat. r = phase concentration (0..1)."""
import json, sys, os
import numpy as np, librosa
SRC2 = '/workspace/mixes/src2'

def onset_env(y, sr, lo, hi, hop=128):
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=hop)); f = librosa.fft_frequencies(sr=sr, n_fft=1024)
    b = np.log1p(100 * S[(f >= lo) & (f < hi)]).sum(0)
    o = np.maximum(0, np.diff(b, prepend=b[:1]))
    o = o - np.convolve(o, np.ones(64) / 64, 'same'); return np.maximum(o, 0), hop / sr

def bar_phase(o, dt, t0, per):
    """phase (ms after the grid beat) and r of onset env o (frame dt) over [t0, t0+4*per)"""
    i0, i1 = int(t0 / dt), int((t0 + 4 * per) / dt); w = o[i0:i1]
    if len(w) < 20 or w.sum() <= 0: return np.nan, 0.0
    t = (np.arange(len(w)) + i0) * dt - t0
    z = np.sum(w * np.exp(-2j * np.pi * t / per)); r = abs(z) / w.sum()
    return float(-np.angle(z) / (2 * np.pi) * per * 1000), float(r)

def track(yid, y=None, sr=22050):
    g = json.load(open(f'{SRC2}/st/{yid}.json')); per = g['per']
    if y is None: y, _ = librosa.load(f'{SRC2}/st/{yid}.wav', sr=sr)
    ok, dt = onset_env(y, sr, 20, 150); os_, _ = onset_env(y, sr, 150, 2000)
    rows = []
    for k, d in enumerate(g['downs']):
        pk, rk = bar_phase(ok, dt, d, per); ps, rs = bar_phase(os_, dt, d, per)
        rows.append(dict(bar=k, kick_ms=None if np.isnan(pk) else round(pk, 1), rk=round(rk, 2), snare_ms=None if np.isnan(ps) else round(ps, 1), rs=round(rs, 2)))
    return rows

if __name__ == '__main__':
    for yid in sys.argv[1:]:
        rows = track(yid)
        good = [r for r in rows if r['rk'] >= 0.3 and r['kick_ms'] is not None]
        print(yid, 'bars', len(rows), 'kick-confident bars', len(good), 'median kick phase', np.median([r['kick_ms'] for r in good]) if good else None)
        for r in rows: print(' ', r)
        json.dump(rows, open(f'/workspace/mixes/protrans/rca_beats/grid_{yid}.json', 'w'))
