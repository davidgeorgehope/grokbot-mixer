"""n1126 priority (a): detection and false-alarm rates of the OFFICIAL hard checks (hardcheck.check, pro-p95 thresholds and
FP.LOCK_MIN_MS unchanged, 11-25 beat-clash fix included) on injected faults. Same injection protocol as calib_v2.py (11-20):
clash60/clash110 = incoming deck delayed 60/110 ms over the whole crop; hole4/hole8 = both decks' lows < 150 Hz cut 50 dB for
4/8 bars in the blend middle; pump = both decks -10 dB for 1 bar in the blend middle; clean = untouched. Decks are rendered once
per meta (blend_diag.crop_decks, cached) and the injection is applied to the arrays that check() and finephase read.
Nothing is tuned here. usage: hcinject_1126.py <variant>   (reads its metas in /tmp/protrans_bench; writes nightly_1126_work/hcinject_<variant>.json)"""
import glob, json, os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.dirname(H))
import run_admitted_tune as T, hardcheck as HC, calib_v2 as CV
import paths; os.chdir(paths.SRC2); sys.path.insert(0, paths.SRC2)
import blend_diag as BD
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
    elif kind == 'pump':
        i0, i1 = int(mid * BS), int((mid + 1) * BS); A[i0:i1] *= 10 ** (-0.5); B[i0:i1] *= 10 ** (-0.5)
    return s0, A, B
BD.crop_decks = patched
KINDS = ['clean', 'clash60', 'clash110', 'hole4', 'hole8', 'pump']
v = sys.argv[1]; rows = T.load_ckpt(v); out = {}
for k, r in sorted(rows.items()):
    m = [x for x in sorted(glob.glob(os.path.splitext(r.get('ours') or 'x')[0] + '_*_meta.json')) if not x.endswith('_dry_meta.json')]
    if not m: continue
    out[k] = {}
    for kind in KINDS:
        INJ[0] = kind
        try:
            c = HC.check(m[0]); out[k][kind] = dict(clash=bool(c['beat_clash']), hole=bool(c['bass_hole']), pump=bool(c['pumping']), van=bool(c['incoming_vanish']), lag=c['residual_lag_ms'], dip=c['lows_dip_db'], pump_db=c['pump_db'])
        except Exception as ex: out[k][kind] = dict(error=f'{type(ex).__name__}: {ex}')
    CACHE.clear(); print(k, {kk: [n for n in ('clash', 'hole', 'pump') if vv.get(n)] for kk, vv in out[k].items()}, flush=True)
summ = {}
for kind in KINDS:
    R = [x[kind] for x in out.values() if 'error' not in x[kind]]
    summ[kind] = dict(n=len(R), **{f'flag_{c}': round(float(np.mean([x[c] for x in R])), 3) for c in ('clash', 'hole', 'pump')}, any_fail=round(float(np.mean([x['clash'] or x['hole'] or x['pump'] or x['van'] for x in R])), 3))
json.dump(dict(variant=v, summary=summ, rows=out, doc=__doc__), open(os.path.join(H, 'nightly_1126_work', f'hcinject_{v}.json'), 'w'), indent=1, default=str)
print('SUMMARY', json.dumps(summ))
