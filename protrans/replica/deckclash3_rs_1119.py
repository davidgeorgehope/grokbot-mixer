#!/usr/bin/env python3
"""2026-11-19 day: deckclash3 on per-bar RE-SYNCED renders (prototype re-sync of barsync_demo_1119, applied in the envelope domain to the
FP0 raw-deck envelopes: each bar segment shifted by -smoothed offset where |offset| >= 8 ms, cap 60; equivalent to the NUDGE re-render up to
seam smoothing, checked on the demo case). Then the same planted overlap-only B shifts (applied AFTER re-sync) and the same dev/held-out
threshold choice. Caveat: re-sync and detector share the per-bar measurement, so on re-synced renders the check mainly verifies that the
re-sync worked; it cannot see what the per-bar measurement cannot see (bars with no clear kick). -> deckclash3_rs_1119.json"""
import json, os, sys, pickle, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import deckclash_1119 as D1, deckclash2_1119 as D2, deckclash3_1119 as D3, deckdrift_1119 as DD, barsync_demo_1119 as BS_
FPB = D2.FPB; MINB = int(os.environ.get('MINB', 3)); SUF = os.environ.get('SUF', '')
def resync_env(e, P):
    sm = BS_.smooth(P); out = e.astype(float).copy(); ar = np.arange(len(e))
    for k, off in sm.items():
        if abs(off) < 8: continue
        f0, f1 = int(k * FPB), min(len(e), int((k + 1) * FPB)); idx = np.arange(f0, f1) - D1.NFFT // (2 * D1.HOP); idx = idx[(idx >= 0) & (idx < len(e))]
        out[idx] = np.interp(idx + np.clip(off, -60, 60) / 1000 * D1.SR / D1.HOP, ar, e)
    return out
if __name__ == '__main__':
    E = pickle.load(open(D3.CP, 'rb')); C = {}; RM = (0.1, 0.2, 0.3)
    for k, c in E.items():
        n, s, e = c['n'], max(0, c['s']), min(c['n'], c['e']); soA, soB = list(range(0, s)), list(range(e, n))
        if len(soA) < 3 or len(soB) < 3 or e - s < 4: continue
        eA, eB = c['eA0'].astype(float), c['eB0'].astype(float)
        pA = DD.per_bar(eA, list(range(0, e)), D1.fold_profile(eA, soA)); pB = DD.per_bar(eB, list(range(s, n)), D1.fold_profile(eB, soB))
        c2 = dict(c, eA0=resync_env(eA, pA), eB0=resync_env(eB, pB))
        b = {kd: D3.deck_bars(c2, '0', pl) for kd, pl in D3.KINDS.items()}
        C[k] = dict(split=D1.split_of(k.split(':', 1)[1]), **{f'{kd}|{rm}': (lambda m: (m[0], m[1], (min(abs(m[0]), abs(m[1])) if np.isfinite(m[0]) and np.isfinite(m[1]) else np.nan)))(D3.stat(b[kd], rm, MINB)) for kd in D3.KINDS for rm in RM})
    grid = []
    for si, sname in ((0, 'med'), (1, 'half'), (2, 'both')):
        for rm in RM:
            for Dm in range(10, 61, 2):
                def rate(sp, kd): v = [bool(np.isfinite(c[f'{kd}|{rm}'][si]) and abs(c[f'{kd}|{rm}'][si]) > Dm) for c in C.values() if c['split'] == sp]; return round(float(np.mean(v)), 3) if v else None
                grid.append(dict(stat=sname, rmin=rm, D=Dm, judged=round(float(np.mean([np.isfinite(c[f'clean|{rm}'][si]) for c in C.values()])), 3), **{f'{sp}_{kd}': rate(sp, kd) for sp in ('dev', 'heldout') for kd in D3.KINDS}))
    ok = [g for g in grid if g['dev_clean'] <= 0.05]; best = max(ok, key=lambda g: (min(g['dev_clash60'], g['dev_clash110'], g['dev_clashm60']), -g['D'])) if ok else None
    cm = np.array([c['clean|0.2'][0] for c in C.values() if np.isfinite(c['clean|0.2'][0])])
    out = dict(n=len(C), n_dev=sum(c['split'] == 'dev' for c in C.values()), n_heldout=sum(c['split'] == 'heldout' for c in C.values()),
               clean_abs_p50=round(float(np.median(np.abs(cm))), 1), clean_abs_p90=round(float(np.percentile(np.abs(cm), 90)), 1), clean_abs_p95=round(float(np.percentile(np.abs(cm), 95)), 1),
               clean_over20=round(float(np.mean(np.abs(cm) > 20)), 3), chosen_on_dev=best,
               meets=bool(best and min(best['heldout_clash60'], best['heldout_clash110'], best['heldout_clashm60']) >= 0.8 and best['heldout_clean'] <= 0.05), grid=grid)
    json.dump(out, open(os.path.join(H, f'deckclash3_rs_1119{SUF}.json'), 'w'), indent=1, default=float); print({k: v for k, v in out.items() if k != 'grid'})
