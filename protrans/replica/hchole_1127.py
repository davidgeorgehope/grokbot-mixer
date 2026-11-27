"""n1127 priority (a): bass-hole detector recalibration candidate, from pro p95 and injected faults only (no hand thresholds).
Official measure lows_dip = (max summed lows in the 2 bars before the blend) - (min summed lows anywhere in the blend). It also counts any
planned lows drop in the blend (breakdowns), so its pro p95 is 45.34 dB and it catches almost no injected 4/8-bar holes.
Candidate 'lows_hole': width-aware V-dip of the summed lows inside the blend: for w in 1..8 bars, min(max of the 2 bars before, max of the
2 bars after) - max over the w bars; take the largest. A hole that comes back is scored; a lows drop that never returns is not.
Threshold = pro p95 of the same measure on the 33 pro clips over the pro overlap [entry, gone) (same windows as calib_pro).
Detection = injected hole4 / hole8 on tonight's default renders (lcb_1127; same injection as hcinject); false alarm = clean renders.
Band: summed lows below FC Hz (env HC_HOLE_FC, default 150 = official band; 90 = below the 150 Hz injection edge, where a 4th-order
150 Hz low-pass leaks 150-300 Hz kick/bass harmonics into the official band and hides the cut).
usage: HC_HOLE_FC=<hz> hchole_1127.py <variant>"""
import glob, json, os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.dirname(H))
import run_admitted_tune as T, calib_v2 as CV, hardcheck as HC
import paths; os.chdir(paths.SRC2); sys.path.insert(0, paths.SRC2)
import blend_diag as BD, score
from engine import BS
FC = float(os.environ.get('HC_HOLE_FC', 150))
def lows_hole(lo, s, e, W=8):
    lo = np.asarray(lo, float); best = 0.0
    for w in range(1, W + 1):
        for k in range(max(2, s), min(e, len(lo) - 2) - w + 1):
            if k + w + 2 > len(lo): break
            best = max(best, min(lo[k-2:k].max(), lo[k+w:k+w+2].max()) - lo[k:k+w].max())
    return float(best)
# pro p95 (same windows as hardcheck.calib_pro)
PRO = json.load(open(os.path.join(H, 'protrans_decisions.json'))); pro = {}
for rec in T.load_recs():
    d = PRO.get(rec['id']) or {}; s, e = d.get('in_entry_clip_bar'), d.get('out_gone_clip_bar')
    if s is None or e is None or e - s < 4: continue
    y = score._load(rec['pro_clip']); y2 = np.stack([y, y], 1) if y.ndim == 1 else y; n = int(len(y2) // BS)
    lo = BD.band_bar_db(y2, n, BS, 'low', FC); pro[rec['id']] = round(lows_hole(lo, int(s), min(int(e), n)), 2)
p95 = float(np.percentile(list(pro.values()), 95)); print('pro lows_hole p95', round(p95, 2), 'n', len(pro), sorted(pro.values())[-5:], flush=True)
ORIG = BD.crop_decks; CACHE = {}; INJ = [None]
def patched(M, i, *a, **k):
    key = (M['decks'][i]['id'], M['decks'][i + 1]['id'], M['trans'][i]['start_bar'], i)
    if key not in CACHE: CACHE[key] = ORIG(M, i, *a, **k)
    s0, A, B = CACHE[key]; kind = INJ[0]; t = M['trans'][i]
    s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0); mid = (s + e) // 2; A, B = A.copy(), B.copy()
    if kind in ('hole4', 'hole8'):
        L = int(kind[4:]); i0, i1 = int((mid - L // 2) * BS), int((mid + L - L // 2) * BS); A[i0:i1] = CV.lows_cut(A[i0:i1]); B[i0:i1] = CV.lows_cut(B[i0:i1])
    return s0, A, B
BD.crop_decks = patched
cal = json.load(open(HC.CAL)); v = sys.argv[1]; rows = T.load_ckpt(v); out = {}
for k, r in sorted(rows.items()):
    m = [x for x in sorted(glob.glob(os.path.splitext(r.get('ours') or 'x')[0] + '_*_meta.json')) if not x.endswith('_dry_meta.json')]
    if not m: continue
    M = json.load(open(m[0])); t = M['trans'][0]; out[k] = {}
    for kind in ('clean', 'hole4', 'hole8'):
        INJ[0] = kind; s0, A, B = BD.crop_decks(M, 0); n = int(round(len(A) / BS)); s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0)
        loA, loB = BD.band_bar_db(A, n, BS, 'low', 150), BD.band_bar_db(B, n, BS, 'low', 150); sl150 = 10 * np.log10(10 ** (loA / 10) + 10 ** (loB / 10))
        loA, loB = BD.band_bar_db(A, n, BS, 'low', FC), BD.band_bar_db(B, n, BS, 'low', FC); sumlo = 10 * np.log10(10 ** (loA / 10) + 10 ** (loB / 10))
        od = HC.lows_dip(sl150, s, e); nh = lows_hole(sumlo, s, e)
        out[k][kind] = dict(official_dip=round(od, 1), official_flag=od > cal['lows_dip_p95'], lows_hole=round(nh, 1), new_flag=nh > p95)
    CACHE.clear(); print(k, out[k], flush=True)
summ = {kind: dict(n=len(out), official=round(float(np.mean([x[kind]['official_flag'] for x in out.values()])), 3), new=round(float(np.mean([x[kind]['new_flag'] for x in out.values()])), 3)) for kind in ('clean', 'hole4', 'hole8')}
json.dump(dict(variant=v, pro_lows_hole=pro, pro_p95=round(p95, 2), official_p95=cal['lows_dip_p95'], summary=summ, rows=out, doc=__doc__), open(os.path.join(H, 'nightly_1127_work', f'hchole_{v}_fc{int(FC)}.json'), 'w'), indent=1, default=str)
print('SUMMARY', json.dumps(summ))
