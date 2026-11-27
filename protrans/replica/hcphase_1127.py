"""n1127 priority (a): beat-clash detector candidate 'deck grid phase'. The official clash measure cross-correlates deck A against deck B
(two different tracks) bar by bar and only answers when >=3 bars agree, so it is silent on most pairs (it caught 9% / 15% of injected
60 / 110 ms deck delays on tonight's default). Candidate: measure each deck's OWN beat phase (high-band onset flux 2-10 kHz, folded on
the 174 BPM beat, circular mean) per bar where both decks are audible (> ref - 20 dB), take the per-bar A-minus-B phase difference
(wrapped to +-half a beat), median over bars. Threshold = pro p95 of the same number on the 33 pro clips, using the source tracks
placed on the pro mix (diagnose_gap.place_source + refine_lag: the pro's own beatmatch) over the pro overlap [entry, gone).
Detection = injected clash60 / clash110 on tonight's default renders (lcb_1127), false alarm = clean and hole4 / hole8. usage: hcphase_1127.py <variant>"""
import glob, json, os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.dirname(H))
import run_admitted_tune as T, calib_v2 as CV
import paths; os.chdir(paths.SRC2); sys.path.insert(0, paths.SRC2)
import blend_diag as BD, score, engine as E
from scipy.signal import butter, sosfiltfilt
SR = 44100; HOP = 64; SOS = butter(4, [2000, 10000], 'band', fs=SR, output='sos')
def bar_phase(y, bars, bs, beat_s):
    m = y.mean(1) if y.ndim == 2 else y; z = sosfiltfilt(SOS, m); n = len(z) // HOP
    env = np.sqrt((z[:n * HOP].reshape(n, HOP) ** 2).mean(1) + 1e-12); fl = np.maximum(np.diff(env, prepend=env[:1]), 0)
    P = beat_s * SR / HOP; out = {}
    for k in bars:
        i0, i1 = int(k * bs / HOP), int((k + 1) * bs / HOP)
        if i1 > len(fl) or i1 - i0 < 8: continue
        t = np.arange(i0, i1); c = np.sum(fl[i0:i1] * np.exp(-2j * np.pi * t / P))
        if abs(c) > 0: out[k] = np.angle(c)
    return out, P
def dphase_ms(A, B, bars, bs, beat_s):
    pa, P = bar_phase(A, bars, bs, beat_s); pb, _ = bar_phase(B, bars, bs, beat_s)
    d = [np.angle(np.exp(1j * (pa[k] - pb[k]))) for k in bars if k in pa and k in pb]
    if len(d) < 2: return None, len(d)
    return float(abs(np.median(d)) / (2 * np.pi) * beat_s * 1000), len(d)
# pro p95
PRO = json.load(open(os.path.join(H, 'protrans_decisions.json'))); pro = {}
import diagnose_gap as DG
for rec in T.load_recs():
    d = PRO.get(rec['id']) or {}; s, e = d.get('in_entry_clip_bar'), d.get('out_gone_clip_bar')
    if s is None or e is None or e - s < 4: continue
    try:
        y = score._load(rec['pro_clip']); y1 = y.mean(1) if y.ndim == 2 else y; bs = score.BAR_SEC * score.SR
        sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        za = DG.place_source(sa, d['loc']['a']['track_t'], d['loc']['a']['mix_t'], len(y1)); za, _ = DG.refine_lag(y1, za)
        zb = DG.place_source(sb, d['loc']['b']['track_t'], d['loc']['b']['mix_t'], len(y1)); zb, _ = DG.refine_lag(y1, zb)
        n = int(len(y1) // bs); aA = BD.band_bar_db(np.stack([za, za], 1), n, bs); aB = BD.band_bar_db(np.stack([zb, zb], 1), n, bs)
        ref = max(np.median(aA[:max(1, int(s))]), np.median(aB[min(int(e), n - 1):])) if n > e else np.median(aA[:max(1, int(s))])
        bars = [k for k in range(int(s), min(int(e), n)) if aA[k] > ref - 20 and aB[k] > ref - 20]
        v, nb = dphase_ms(za, zb, bars, bs, score.BAR_SEC / 4)
        pro[rec['id']] = None if v is None else round(v, 1)
    except Exception as ex: pro[rec['id']] = f'error {type(ex).__name__}: {ex}'
    print('pro', rec['id'], pro[rec['id']], flush=True)
pv = [x for x in pro.values() if isinstance(x, float)]; p95 = float(np.percentile(pv, 95)); print('pro dphase p95 ms', round(p95, 1), 'n', len(pv), flush=True)
ORIG = BD.crop_decks; CACHE = {}; INJ = [None]
def patched(M, i, *a, **k):
    key = (M['decks'][i]['id'], M['decks'][i + 1]['id'], M['trans'][i]['start_bar'], i)
    if key not in CACHE: CACHE[key] = ORIG(M, i, *a, **k)
    s0, A, B = CACHE[key]; kind = INJ[0]; t = M['trans'][i]
    s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0); mid = (s + e) // 2; A, B = A.copy(), B.copy()
    if kind in ('clash60', 'clash110'):
        n = int(int(kind[5:]) / 1000 * SR); B = np.concatenate([np.zeros((n, B.shape[1]), np.float32), B[:-n]])
    elif kind in ('hole4', 'hole8'):
        L = int(kind[4:]); i0, i1 = int((mid - L // 2) * E.BS), int((mid + L - L // 2) * E.BS); A[i0:i1] = CV.lows_cut(A[i0:i1]); B[i0:i1] = CV.lows_cut(B[i0:i1])
    return s0, A, B
BD.crop_decks = patched
KINDS = ['clean', 'clash60', 'clash110', 'hole4', 'hole8']; v = sys.argv[1]; rows = T.load_ckpt(v); out = {}
for k, r in sorted(rows.items()):
    m = [x for x in sorted(glob.glob(os.path.splitext(r.get('ours') or 'x')[0] + '_*_meta.json')) if not x.endswith('_dry_meta.json')]
    if not m: continue
    M = json.load(open(m[0])); t = M['trans'][0]; out[k] = {}
    for kind in KINDS:
        INJ[0] = kind; s0, A, B = BD.crop_decks(M, 0); nb = int(round(len(A) / E.BS)); s, e = float(t['start_bar']), float(t['end_bar'])
        aA, aB = BD.band_bar_db(A, nb, E.BS), BD.band_bar_db(B, nb, E.BS)
        ref = max(float(np.median(aA[:BD.PRE])), float(np.median(aB[-BD.POST:])))
        bars = [kk for kk in range(int(s - s0), int(e - s0)) if 0 <= kk < nb and aA[kk] > ref - 20 and aB[kk] > ref - 20]
        dv, nbb = dphase_ms(A, B, bars, E.BS, E.BEAT); out[k][kind] = dict(dphase=None if dv is None else round(dv, 1), n=nbb, flag=dv is not None and dv > p95)
    CACHE.clear(); print(k, {kk: vv['dphase'] for kk, vv in out[k].items()}, flush=True)
summ = {kind: dict(n=len(out), flag=round(float(np.mean([x[kind]['flag'] for x in out.values()])), 3), median_ms=round(float(np.median([x[kind]['dphase'] or 0 for x in out.values()])), 1)) for kind in KINDS}
json.dump(dict(variant=v, pro=pro, pro_p95=round(p95, 1), summary=summ, rows=out, doc=__doc__), open(os.path.join(H, 'nightly_1127_work', f'hcphase_{v}.json'), 'w'), indent=1, default=str)
print('SUMMARY', json.dumps(summ))
