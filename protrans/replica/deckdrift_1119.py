#!/usr/bin/env python3
"""2026-11-19 day: are the 'clean' renders clean? For the renders with the largest clean self-referenced drift (deckclash2),
per bar and per deck: xcorr of that bar's kick-band onset envelope against the deck's own solo-bar template (+-120 ms), on the master
bar grid. A grid/tempo error shows as a TREND (offset grows across bars, high R^2); measurement noise shows as random jumps.
Also: the same per-bar offset for each deck's solo bars (where nothing else plays) gives the noise floor. -> deckdrift_1119.json + PNGs"""
import json, os, sys, pickle, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import deckclash_1119 as D1, deckclash2_1119 as D2
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
FPB = D2.FPB; N = int(round(FPB)); OUTD = os.path.join(H, 'deckdrift_png'); os.makedirs(OUTD, exist_ok=True)
def bar_prof(e, k):
    idx = (k * FPB + np.arange(N)).astype(int) - D1.NFFT // (2 * D1.HOP)
    return e[idx] if idx.min() >= 0 and idx.max() < len(e) else None
def per_bar(e, bars, tmpl):
    out = []
    for k in bars:
        p = bar_prof(e, k)
        if p is None or p.std() == 0: out.append((k, np.nan, 0.)); continue
        l, r = D1.xlag(tmpl, p, 120.0); out.append((k, l, r))
    return out
def regions(c):
    n = min(len(c['aA']), len(c['aB'])); s, e = max(0, c['s']), min(n, c['e']); aA, aB = c['aA'][:n], c['aB'][:n]
    lA, lB = np.percentile(aA, 90) - 15, np.percentile(aB, 90) - 15
    ov = [k for k in range(s, e) if aA[k] > lA and aB[k] > lB] or list(range(s, e))
    soA = [k for k in range(0, s) if aA[k] > lA and aB[k] < lB] or [k for k in range(0, s) if aA[k] > lA]
    soB = [k for k in range(e, n) if aB[k] > lB and aA[k] < lA] or [k for k in range(e, n) if aB[k] > lB]
    return n, ov, soA, soB, aA, aB, lA, lB
def trend(pts, rmin=0.2):
    x = np.array([k for k, l, r in pts if np.isfinite(l) and r >= rmin], float); y = np.array([l for k, l, r in pts if np.isfinite(l) and r >= rmin], float)
    if len(x) < 4: return dict(n=len(x))
    b, a = np.polyfit(x, y, 1); res = y - (a + b * x); r2 = 1 - res.var() / y.var() if y.var() > 0 else 0
    return dict(n=len(x), slope_ms_per_bar=round(float(b), 2), span_ms=round(float(b * (x.max() - x.min())), 1), r2=round(float(r2), 2), resid_sd=round(float(res.std()), 1),
                jump_sd=round(float(np.std(np.diff(y))), 1), mean=round(float(y.mean()), 1))
if __name__ == '__main__':
    E = pickle.load(open(D2.CP, 'rb')); rows = []
    for k, c in E.items():
        m = D2.measure(c)
        if np.isfinite(m['drift']): rows.append((abs(m['drift']), k, m))
    rows.sort(reverse=True); top = [x for x in rows if x[2]['r'] >= 0.2][:10]; rnd = rows[len(rows) // 2: len(rows) // 2 + 10]
    res = dict(n=len(rows), drift_abs_hist={b: int(np.sum([(lo <= x[0] < hi) for x in rows])) for b, lo, hi in (('<20', 0, 20), ('20-40', 20, 40), ('40-80', 40, 80), ('80-140', 80, 140), ('>=140', 140, 1e9))},
               near_half_beat=int(np.sum([abs(x[0] - 172.4) < 25 for x in rows])), near_quarter_beat=int(np.sum([abs(x[0] - 86.2) < 15 for x in rows])), cases=[])
    for grp, L in (('top', top), ('median', rnd)):
        for dabs, k, m in L:
            c = E[k]; n, ov, soA, soB, aA, aB, lA, lB = regions(c); eA, eB = c['eA'].astype(float), c['eB'].astype(float)
            tA, tB = D1.fold_profile(eA, soA), D1.fold_profile(eB, soB)
            pA = per_bar(eA, sorted(set(soA) | set(ov)), tA); pB = per_bar(eB, sorted(set(ov) | set(soB)), tB)
            ovs = set(ov)
            rec = dict(key=k, group=grp, drift=round(m['drift'], 1), dA=round(m['dA'], 1), dB=round(m['dB'], 1), r=round(m['r'], 2), n_ov=len(ov),
                       A_solo=trend([p for p in pA if p[0] not in ovs]), A_ov=trend([p for p in pA if p[0] in ovs]),
                       B_ov=trend([p for p in pB if p[0] in ovs]), B_solo=trend([p for p in pB if p[0] not in ovs]),
                       A_bars=[(int(a), None if not np.isfinite(b) else round(b, 1), round(r, 2)) for a, b, r in pA], B_bars=[(int(a), None if not np.isfinite(b) else round(b, 1), round(r, 2)) for a, b, r in pB])
            res['cases'].append(rec)
            fig, ax = plt.subplots(3, 1, figsize=(11, 8.5))
            for P_, col, lab in ((pA, 'tab:blue', 'deck A (outgoing)'), (pB, 'tab:orange', 'deck B (incoming)')):
                x = [p[0] for p in P_]; y = [p[1] if p[2] >= 0.2 else np.nan for p in P_]; ax[0].plot(x, y, 'o-', color=col, label=lab, ms=3)
            ax[0].axvspan(min(ov), max(ov) + 1, color='grey', alpha=0.15, label='overlap'); ax[0].axhline(0, color='k', lw=0.5)
            ax[0].set_ylabel('kick offset vs own solo template (ms)'); ax[0].set_title(f'{k}  drift {m["drift"]:.0f} ms'); ax[0].legend(fontsize=7)
            for j, (e_, so, lab) in enumerate(((eA, soA, 'A'), (eB, soB, 'B'))):
                bars = sorted(set(so) | set(ov)); img = np.array([bar_prof(e_, b) if bar_prof(e_, b) is not None else np.zeros(N) for b in bars])
                img = img / (img.max(1, keepdims=True) + 1e-9)
                ax[1 + j].imshow(img.T, aspect='auto', origin='lower', extent=[bars[0], bars[-1] + 1, 0, D1.BAR * 1000], cmap='magma')
                for q in range(1, 4): ax[1 + j].axhline(q * D1.BEAT * 1000, color='w', lw=0.4, ls=':')
                ax[1 + j].axvspan(min(ov), max(ov) + 1, ymin=0, ymax=0.03, color='cyan'); ax[1 + j].set_ylabel(f'deck {lab}: ms in bar')
            ax[2].set_xlabel('bar (crop)'); fig.tight_layout(); fig.savefig(os.path.join(OUTD, k.replace(':', '__') + '.png'), dpi=90); plt.close(fig)
            print(grp, k, rec['drift'], 'A_ov', rec['A_ov'], 'B_ov', rec['B_ov'], 'A_solo', rec['A_solo'].get('resid_sd'), 'B_solo', rec['B_solo'].get('resid_sd'), flush=True)
    json.dump(res, open(os.path.join(H, 'deckdrift_1119.json'), 'w'), indent=1, default=float); print({k: res[k] for k in ('n', 'drift_abs_hist', 'near_half_beat', 'near_quarter_beat')})
