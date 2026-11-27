"""n1127 priority (a): beat-clash detector check on injected faults (same injection protocol as hcinject_1126 / calib_v2: clash60/110 =
incoming deck delayed 60/110 ms over the whole crop; hole4/hole8 = both decks' lows cut 50 dB for 4/8 bars mid-blend). Compares the
OFFICIAL lag measure (finephase.measure_blend_lag: only the longest run of bars where both decks are loud and within 6 dB) with a WIDE
variant (same 1-bar offsets and the same finephase.confident_lag rule, but over every blend bar where both decks are within 20 dB of the
reference level, i.e. the official 'bl' set). No threshold is changed: LOCK_MIN_MS 15, cluster 20 ms / span 25 ms / >=3 bars / majority
all stay. Halfbeat flags are recorded separately (they come from the render, not from these arrays). usage: hcclash_1127.py <variant>"""
import glob, json, os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.dirname(H))
import run_admitted_tune as T, calib_v2 as CV
import paths; os.chdir(paths.SRC2); sys.path.insert(0, paths.SRC2)
import blend_diag as BD, finephase as FP, engine as E
from engine import BS, SR
ORIG = BD.crop_decks; CACHE = {}; INJ = [None]
def patched(M, i, *a, **k):
    key = (M['decks'][i]['id'], M['decks'][i + 1]['id'], M['trans'][i]['start_bar'], i)
    if key not in CACHE: CACHE[key] = ORIG(M, i, *a, **k)
    s0, A, B = CACHE[key]; kind = INJ[0]; t = M['trans'][i]
    s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0); mid = (s + e) // 2
    A, B = A.copy(), B.copy()
    if kind in ('clash60', 'clash110'):
        n = int(int(kind[5:]) / 1000 * SR); B = np.concatenate([np.zeros((n, B.shape[1]), np.float32), B[:-n]])
    elif kind in ('hole4', 'hole8'):
        L = int(kind[4:]); i0, i1 = int((mid - L // 2) * BS), int((mid + L - L // 2) * BS); A[i0:i1] = CV.lows_cut(A[i0:i1]); B[i0:i1] = CV.lows_cut(B[i0:i1])
    return s0, A, B
BD.crop_decks = patched
def wide_lag(M):
    s0, yA, yB = BD.crop_decks(M, 0); t = M['trans'][0]; s, e = float(t['start_bar']), float(t['end_bar']); nb = int(round(len(yA) / E.BS))
    aA, aB = BD.band_bar_db(yA, nb, E.BS), BD.band_bar_db(yB, nb, E.BS)
    ref = max(float(np.median(aA[:BD.PRE])) if len(aA) >= BD.PRE else -60.0, float(np.median(aB[-BD.POST:])) if len(aB) >= BD.POST else -60.0)
    bl = [k for k in range(int(s - s0), int(e - s0)) if 0 <= k < nb and aA[k] > ref - 20 and aB[k] > ref - 20]
    if len(bl) < 2: return None, len(bl)
    offs = BD.bar_offsets(yA, yB, bl, E.BS, E.BEAT, win_bars=1, prefer_interior=False)
    return FP.confident_lag(offs, E.BEAT * 1000), len(bl)
KINDS = ['clean', 'clash60', 'clash110', 'hole4', 'hole8']
v = sys.argv[1]; rows = T.load_ckpt(v); out = {}
for k, r in sorted(rows.items()):
    m = [x for x in sorted(glob.glob(os.path.splitext(r.get('ours') or 'x')[0] + '_*_meta.json')) if not x.endswith('_dry_meta.json')]
    if not m: continue
    M = json.load(open(m[0])); out[k] = dict(halfbeat_fail=bool((M['trans'][0].get('halfbeat') or {}).get('fail')))
    for kind in KINDS:
        INJ[0] = kind
        try:
            lo, _ = FP.measure_blend_lag(M['decks'], M['trans'], 0); lw, nbl = wide_lag(M)
            out[k][kind] = dict(off=lo, wide=lw, n_bl=nbl, off_flag=lo is not None and abs(lo) > FP.LOCK_MIN_MS, wide_flag=lw is not None and abs(lw) > FP.LOCK_MIN_MS)
        except Exception as ex: out[k][kind] = dict(error=f'{type(ex).__name__}: {ex}')
    CACHE.clear(); print(k, {kk: (vv.get('off'), vv.get('wide')) for kk, vv in out[k].items() if isinstance(vv, dict)}, flush=True)
summ = {}
for kind in KINDS:
    R = [x[kind] for x in out.values() if 'error' not in x[kind]]
    summ[kind] = dict(n=len(R), official=round(float(np.mean([x['off_flag'] for x in R])), 3), wide=round(float(np.mean([x['wide_flag'] for x in R])), 3))
json.dump(dict(variant=v, summary=summ, rows=out, doc=__doc__), open(os.path.join(H, 'nightly_1127_work', f'hcclash_{v}.json'), 'w'), indent=1, default=str)
print('SUMMARY', json.dumps(summ))
