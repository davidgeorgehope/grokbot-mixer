"""Ground truth for 11-20 hm09 B: drums-only (HPSS percussive) of each rendered deck, every hit's time vs the mix grid,
per bar, plus drift (is B's offset constant or growing?) and B's own tempo in the overlap (autocorrelation)."""
import sys, os, json, numpy as np, librosa
sys.path.insert(0, '/workspace/mixes/src2'); os.chdir('/workspace/mixes/src2')
import blend_diag as BD, engine as E
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
SR = 22050; HOP = 64; DT = HOP / SR; BEAT = E.BEAT; BAR = 4 * BEAT; S16 = BEAT / 4
M = json.load(open('/tmp/protrans_bench/lab_hybrid_minds_ukf__09_meta.json')); s0, A, B = BD.crop_decks(M, 0); t = M['trans'][0]
print('lock', M['decks'][1].get('blend_lock_ms'), 'blend bars', t['start_bar'], t['end_bar'], 's0', s0)
def perc(y):
    y = librosa.resample(y.mean(1), orig_sr=44100, target_sr=SR); S = librosa.stft(y, n_fft=1024, hop_length=HOP)
    _, P = librosa.decompose.hpss(np.abs(S), margin=2.0); return librosa.istft(P * np.exp(1j * np.angle(S)), hop_length=HOP, length=len(y))
pa, pb = perc(A), perc(B)
ref = max(np.percentile(np.abs(pa), 99.5), np.percentile(np.abs(pb), 99.5))
def hits(p, b0, b1):
    i0, i1 = int((b0 - s0) * BAR * SR), int((b1 - s0) * BAR * SR); seg = p[i0:i1]
    env = librosa.onset.onset_strength(y=seg, sr=SR, hop_length=HOP)
    fr = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=HOP, backtrack=True)
    tt = fr * DT + (b0 - s0) * BAR; lv = []
    for x in tt:
        j = int(x * SR); lv.append(20 * np.log10(np.abs(p[j:j + int(0.03 * SR)]).max() / ref + 1e-9))
    return tt, np.array(lv)
out = {}
for nm, p in (('A', pa), ('B', pb)):
    tt, lv = hits(p, 184, 216); dev = ((tt + S16 / 2) % S16 - S16 / 2) * 1000; bar = (tt / BAR).astype(int) + s0
    out[nm] = dict(t=tt, lv=lv, dev=dev, bar=bar)
for k in range(184, 216):
    row = []
    for nm in ('A', 'B'):
        o = out[nm]; m = (o['bar'] == k) & (o['lv'] > -30)
        row.append(f"{nm}: n={m.sum():2d} med={np.median(o['dev'][m]) if m.any() else float('nan'):+6.1f} spread={np.std(o['dev'][m]) if m.sum() > 1 else float('nan'):5.1f} lvl={np.max(o['lv'][m]) if m.any() else float('nan'):6.1f}")
    print(k, ' | '.join(row))
# drift of B in the overlap (audible hits only)
o = out['B']; m = (o['bar'] >= 192) & (o['bar'] < 208) & (o['lv'] > -30)
if m.sum() > 3:
    c = np.polyfit(o['t'][m], o['dev'][m], 1); print('B overlap hits', int(m.sum()), 'dev vs time slope', round(c[0] * BAR, 2), 'ms/bar', 'median', round(float(np.median(o['dev'][m])), 1), 'IQR', np.percentile(o['dev'][m], [25, 75]).round(1))
oa = out['A']; ma = (oa['bar'] >= 192) & (oa['bar'] < 208) & (oa['lv'] > -30); print('A overlap hits', int(ma.sum()), 'median', round(float(np.median(oa['dev'][ma])), 1), 'IQR', np.percentile(oa['dev'][ma], [25, 75]).round(1))
# B's own tempo in the overlap: autocorrelation of its percussive onset envelope
i0, i1 = int((192 - s0) * BAR * SR), int((208 - s0) * BAR * SR)
for nm, p in (('A', pa), ('B', pb)):
    env = librosa.onset.onset_strength(y=p[i0:i1], sr=SR, hop_length=HOP); tg = librosa.feature.tempogram(onset_envelope=env, sr=SR, hop_length=HOP)
    bpm = librosa.tempo_frequencies(tg.shape[0], sr=SR, hop_length=HOP); g = tg.mean(1); ok = (bpm > 60) & (bpm < 200)
    top = np.argsort(g[ok])[::-1][:3]; print(nm, 'overlap tempogram peaks (BPM)', [round(float(bpm[ok][i]), 1) for i in top])
fig, ax = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
for a_, nm in zip(ax, ('A', 'B')):
    o = out[nm]; m = o['lv'] > -40
    sc = a_.scatter(o['bar'][m] + ((o['t'][m] / BAR) % 1), o['dev'][m], c=o['lv'][m], cmap='viridis', vmin=-40, vmax=0, s=14)
    a_.axhline(0, c='k', lw=.6); a_.axhspan(-25, 25, color='g', alpha=.07); a_.axvspan(192, 208, color='orange', alpha=.08)
    a_.set_ylabel(f'{nm} hit vs nearest 16th (ms)'); a_.set_ylim(-45, 45); a_.set_title(f'deck {nm} drums-only (HPSS) hits, colour = level dB')
ax[1].set_xlabel('mix bar (orange = blend 192-208)'); plt.colorbar(sc, ax=ax); plt.savefig('/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-20_hm09B_hits.png', dpi=110)
print('png written')
