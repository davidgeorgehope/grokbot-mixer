#!/usr/bin/env python3
"""2026-11-19 day: per-bar beat re-sync PROTOTYPE (research; engine code and rules.json untouched; uses the engine's existing
per-source-bar NUDGE hook in memory only). Two passes on one render plan:
  1) render each deck raw (gains/EQ off, timing identical), measure each bar's kick offset vs the deck's own solo template (+-120 ms),
  2) smooth (5-bar running median over bars with r >= 0.2, held across gaps), apply nudge = -offset where |offset| >= 8 ms (cap 60),
     re-render the real blend (gains/EQ on).
Writes before/after mp3 clips (local + Drive, not git) and PNGs, and before/after per-bar offsets. usage: barsync_demo_1119.py VARIANT:ID"""
import json, os, sys, copy, numpy as np, subprocess
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import deckclash_1119 as D1, deckclash2_1119 as D2, deckdrift_1119 as DD
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
OUT = os.path.join(H, 'deckdrift_clips'); os.makedirs(OUT, exist_ok=True)
def strip(M):
    M2 = copy.deepcopy(M)
    for d in M2['decks'][:2]: d['auto'] = dict(gain=[[-1e6, 1.0], [1e6, 1.0]]); d.pop('dswap', None); d.pop('graphcut', None)
    return M2
def measure(BD, M, s, e):
    s0, A, B = BD.crop_decks(strip(M), 0); n = int(min(len(A), len(B)) // D1.BS); eA, eB = D1.kick_env(A), D1.kick_env(B)
    soA, ov, soB = list(range(0, s)), list(range(s, min(n, e))), list(range(min(n, e), n))
    pA = DD.per_bar(eA, list(range(0, min(n, e))), D1.fold_profile(eA, soA)); pB = DD.per_bar(eB, list(range(s, n)), D1.fold_profile(eB, soB))
    return s0, n, ov, pA, pB
def smooth(P):
    ks = [k for k, l, r in P]; v = np.array([l if (np.isfinite(l) and r >= 0.2) else np.nan for k, l, r in P]); out = {}
    for i, k in enumerate(ks):
        w = v[max(0, i - 2):i + 3]; w = w[np.isfinite(w)]
        if len(w): out[k] = float(np.median(w))
    last = 0.0
    for k in ks:
        last = out.get(k, last); out[k] = last
    return out
def ov_stats(P, ov):
    v = [l for k, l, r in P if k in set(ov) and np.isfinite(l) and r >= 0.2]; return dict(n=len(v), med=round(float(np.median(v)), 1) if v else None, spread=round(float(np.ptp(v)), 1) if v else None, trend=DD.trend([p for p in P if p[0] in set(ov)]))
if __name__ == '__main__':
    v, pid = sys.argv[1].split(':', 1); row = next(json.loads(l) for l in open(os.path.join(H, 'gate_ckpt', v + '.jsonl')) if json.loads(l)['id'] == pid)
    os.chdir(D2.SRC2); import blend_diag as BD, engine
    M = json.load(open(row['meta'])); t = M['trans'][0]; s0 = int(t['start_bar']) - BD.PRE; s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0)
    _, n, ov, pA0, pB0 = measure(BD, M, s, e)
    _, A0, B0 = BD.crop_decks(M, 0); mix0 = A0 + B0
    nud = {}
    for P_, d in ((pA0, M['decks'][0]), (pB0, M['decks'][1])):
        sm = smooth(P_); fm = d['full_map']
        for c, off in sm.items():
            j = s0 + c - d['start_bar']
            if 0 <= j < len(fm) and abs(off) >= 8: nud.setdefault(d['id'], {})[str(fm[j][0])] = round(float(-np.clip(off, -60, 60)), 1)
    saved = copy.deepcopy(engine.NUDGE)
    for tid, mp in nud.items():
        base = engine.NUDGE.setdefault(tid, {})
        for sb, ms in mp.items(): base[sb] = float(base.get(sb, 0)) + ms
    _, n1, ov1, pA1, pB1 = measure(BD, M, s, e); _, A1, B1 = BD.crop_decks(M, 0); mix1 = A1 + B1
    engine.NUDGE.clear(); engine.NUDGE.update(saved)
    tag = sys.argv[1].replace(':', '__'); import soundfile as sf
    for nm, y in (('before', mix0), ('after', mix1)):
        pk = np.max(np.abs(y)) + 1e-9; w = os.path.join(OUT, f'{tag}_{nm}.wav'); sf.write(w, (y / pk * 0.89).astype(np.float32), D1.SR)
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', w, '-b:a', '192k', w[:-4] + '.mp3'], check=True); os.remove(w)
    res = dict(key=sys.argv[1], overlap_bars=[s, e], nudged_bars={k: len(v) for k, v in nud.items()}, nudges=nud,
               before=dict(A=ov_stats(pA0, ov), B=ov_stats(pB0, ov)), after=dict(A=ov_stats(pA1, ov), B=ov_stats(pB1, ov)))
    fig, ax = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for j, (pa, pb, nm) in enumerate(((pA0, pB0, 'before (engine as is)'), (pA1, pB1, 'after per-bar re-sync'))):
        for P_, col, lab in ((pa, 'tab:blue', 'deck A (outgoing)'), (pb, 'tab:orange', 'deck B (incoming)')):
            ax[j].plot([p[0] for p in P_], [p[1] if p[2] >= 0.2 else np.nan for p in P_], 'o-', color=col, label=lab, ms=3)
        ax[j].axvspan(s, e, color='grey', alpha=0.15, label='overlap'); ax[j].axhline(0, color='k', lw=0.5); ax[j].axhspan(-20, 20, color='green', alpha=0.06)
        ax[j].set_ylabel('kick offset vs own template (ms)'); ax[j].set_title(f'{sys.argv[1]}: {nm}'); ax[j].legend(fontsize=7)
    ax[1].set_xlabel('bar (crop; green band = +-20 ms)'); fig.tight_layout(); fig.savefig(os.path.join(OUT, f'{tag}_offsets.png'), dpi=90); plt.close(fig)
    json.dump(res, open(os.path.join(OUT, f'{tag}.json'), 'w'), indent=1, default=float); print(json.dumps({k: v for k, v in res.items() if k != 'nudges'}, default=float))
