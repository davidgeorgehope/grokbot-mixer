#!/usr/bin/env python3
"""2026-11-19 day: DECK clash (flag HC_DECKCLASH=1, research). On our own renders the two decks exist separately before summing.
Per deck, fold its kick-band onset envelope (30-150 Hz spectral flux) at the BAR period over the overlap bars where that deck is
audible, and take the downbeat-kick offset = argmax of the folded profile within +-170 ms of the master bar grid (sub-frame
refined). Deck-to-deck lag = offB - offA. Unlike per-bar cross-correlation, folding at the bar period cannot alias to the
16th-note period (86 ms at 174 BPM), and needs no pro calibration (pros are summed, so this is defined on our renders only).
Validation: planted +60 / +110 ms (and -60) shifts of deck B on dev renders vs the same render clean; threshold chosen on the
md5%3 'dev' split (clean flag rate <= 5%), reported on the 'heldout' split. usage: deckclash_1119.py"""
import json, os, sys, pickle, hashlib, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P0 = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P0), 'src2')
for p in (P0, SRC2, H):
    if p not in sys.path: sys.path.insert(0, p)
SR = 44100; T = 174.0; BEAT = 60 / T; BAR = 4 * BEAT; BS = BAR * SR; HOP = 128; NFFT = 2048
def kick_env(y):
    m = y.mean(1) if y.ndim == 2 else y
    fr = np.lib.stride_tricks.sliding_window_view(m, NFFT)[::HOP] * np.hanning(NFFT)
    S = np.abs(np.fft.rfft(fr, axis=1)); f = np.fft.rfftfreq(NFFT, 1 / SR); L = np.log1p(100 * S[:, (f >= 30) & (f < 150)])
    d = np.maximum(0, np.diff(L, axis=0)).sum(1); e = np.concatenate([[0], d]); return e
def fold_profile(e, bars):
    fpb = BS / HOP; n = int(round(fpb)); prof = np.zeros(n); cnt = 0
    for k in bars:
        idx = (k * fpb + np.arange(n)).astype(int) - NFFT // (2 * HOP)
        if idx.min() < 0 or idx.max() >= len(e): continue
        prof += e[idx]; cnt += 1
    return prof if cnt else None
def xlag(pa, pb, lim_ms=170.0):
    """circular cross-correlation of the two decks' bar-folded kick profiles, lag of B vs A within +-lim (parabolic refine), and its r"""
    if pa is None or pb is None or pa.std() == 0 or pb.std() == 0: return np.nan, 0.0
    a = (pa - pa.mean()) / pa.std(); b = (pb - pb.mean()) / pb.std(); n = len(a); lm = int(lim_ms / 1000 * SR / HOP)
    L = np.arange(-lm, lm + 1); r = np.array([np.mean(a * np.roll(b, -l)) for l in L]); j = int(np.argmax(r))
    dj = 0.0
    if 0 < j < len(r) - 1:
        den = r[j - 1] - 2 * r[j] + r[j + 1]; dj = 0.5 * (r[j - 1] - r[j + 1]) / den if den != 0 else 0.0
    return float((L[j] + dj) * HOP / SR * 1000), float(r[j])
def fold_offset(e, bars, lim_ms=170.0):
    """bar-folded kick profile over the given bar indices -> (offset ms of the downbeat kick, peak clarity)"""
    fpb = BS / HOP; n = int(round(fpb)); prof = np.zeros(n); cnt = 0
    for k in bars:
        i0 = k * fpb; idx = (i0 + np.arange(n)).astype(int) - NFFT // (2 * HOP)  # frame k*fpb is centred NFFT/2 later
        if idx.min() < 0 or idx.max() >= len(e): continue
        prof += e[idx]; cnt += 1
    if not cnt or prof.sum() <= 0: return np.nan, 0.0
    prof = np.roll(prof, n // 2); c = n // 2; lm = int(lim_ms / 1000 * SR / HOP)
    w = prof[c - lm:c + lm + 1]; j = int(np.argmax(w))
    if 0 < j < len(w) - 1:
        a, b, cc = w[j - 1], w[j], w[j + 1]; den = a - 2 * b + cc; dj = 0.5 * (a - cc) / den if den != 0 else 0.0
    else: dj = 0.0
    off = (j + dj - lm) * HOP / SR * 1000; clar = float(w[j] / (np.median(prof) + 1e-9)); return float(off), clar
def bar_db(y, n):
    m = y.mean(1) if y.ndim == 2 else y; return np.array([10 * np.log10(np.mean(m[int(k * BS):int((k + 1) * BS)] ** 2) + 1e-12) for k in range(n)])
def deck_lag(A, Bd, s, e):
    n = int(len(A) // BS); aA, aB = bar_db(A, n), bar_db(Bd, n)
    ov = [k for k in range(max(0, s), min(n, e)) if aA[k] > np.percentile(aA, 90) - 15 and aB[k] > np.percentile(aB, 90) - 15]
    if len(ov) < 4: ov = list(range(max(0, s), min(n, e)))
    eA, eB = kick_env(A), kick_env(Bd); oA, cA = fold_offset(eA, ov); oB, cB = fold_offset(eB, ov); xl, xr = xlag(fold_profile(eA, ov), fold_profile(eB, ov))
    return dict(lag=float(oB - oA) if np.isfinite(oA) and np.isfinite(oB) else np.nan, offA=oA, offB=oB, clarA=cA, clarB=cB, nov=len(ov), xlag=xl, xr=xr)
def split_of(pid): return 'heldout' if int(hashlib.md5(pid.encode()).hexdigest(), 16) % 3 == 0 else 'dev'
VARS = [v for v in ('default', 'ndef1119', 'pick1119', 'et1119c', 'et1119k', 'sp1119a1', 'sp1119a2', 'sp1119b1', 'sp1119b2') if os.path.exists(os.path.join(H, 'gate_ckpt', v + '.jsonl'))]
if __name__ == '__main__':
    import picker_1119 as P
    HOLD = set(P.HOLD); cp = os.path.join(H, 'hc2_cache', 'deckclash_cases2.pkl'); C = pickle.load(open(cp, 'rb')) if os.path.exists(cp) else {}
    os.chdir(SRC2); import blend_diag as BD
    for v in VARS:
        for l in open(os.path.join(H, 'gate_ckpt', v + '.jsonl')):
            r = json.loads(l); pid = r['id']; key = f'{v}:{pid}'
            if r.get('error') or r.get('dj') in HOLD or r.get('src') == 'protrans' or key in C: continue
            try:
                M = json.load(open(r['meta'])); t = M['trans'][0]; s0, A, B = BD.crop_decks(M, 0)
            except Exception as ex: print('skip', key, ex); continue
            s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0); rec = dict(split=split_of(pid), hard_v1=r.get('hard'), v=v)
            for kind, ms in (('clean', 0), ('clash60', 60), ('clash110', 110), ('clashm60', -60)):
                k = int(abs(ms) / 1000 * SR)
                Bd = B if not k else (np.concatenate([np.zeros((k, 2), np.float32), B[:-k]]) if ms > 0 else np.concatenate([B[k:], np.zeros((k, 2), np.float32)]))
                rec[kind] = deck_lag(A, Bd, s, e)
            C[key] = rec; pickle.dump(C, open(cp, 'wb')); print(key, {k: (round(rec[k]['lag'], 1), round(rec[k]['xlag'], 1)) for k in ('clean', 'clash60', 'clash110', 'clashm60')}, flush=True)
    # threshold on |lag| chosen on dev split: smallest D with clean flag <= 5%; then report
    def flag(x, D, cmin, st): return bool(np.isfinite(x[st]) and (min(x['clarA'], x['clarB']) if st == 'lag' else x['xr']) >= cmin and abs(x[st]) > D)  # low clarity -> abstain
    grid = []
    for st, cms in (('lag', (0, 2, 3, 4)), ('xlag', (0, 0.2, 0.3, 0.4, 0.5))):
      for cmin in cms:
        def rate(sp, kind, D, cmin, st=st): v = [flag(c[kind], D, cmin, st) for c in C.values() if c['split'] == sp]; return round(float(np.mean(v)), 3) if v else None
        for D in range(10, 61, 2):
            g = dict(stat=st, D=D, cmin=cmin, judged_dev=round(float(np.mean([(min(c['clean']['clarA'], c['clean']['clarB']) if st == 'lag' else c['clean']['xr']) >= cmin for c in C.values() if c['split'] == 'dev'])), 3),
                     **{f'{sp}_{k}': rate(sp, k, D, cmin) for sp in ('dev', 'heldout') for k in ('clean', 'clash60', 'clash110', 'clashm60')}); grid.append(g)
    ok = [g for g in grid if (g['dev_clean'] if g['dev_clean'] is not None else 1) <= 0.05]
    best = max(ok, key=lambda g: (min(g['dev_clash60'], g['dev_clash110'], g['dev_clashm60']), -g['D'])) if ok else None
    cl = np.array([c['clean']['xlag'] for c in C.values() if np.isfinite(c['clean']['xlag'])])
    out = dict(n_renders=len(C), variants=VARS, clean_lag_abs_p50=round(float(np.median(np.abs(cl))), 1), clean_lag_abs_p95=round(float(np.percentile(np.abs(cl), 95)), 1),
               grid=grid, chosen_on_dev=best, meets=bool(best and min(best['heldout_clash60'], best['heldout_clash110'], best['heldout_clashm60']) >= 0.8 and best['heldout_clean'] <= 0.05))
    json.dump(out, open(os.path.join(H, 'deckclash_1119.json'), 'w'), indent=1); print('CHOSEN', best, 'meets', out['meets'], 'clean |lag| p50/p95', out['clean_lag_abs_p50'], out['clean_lag_abs_p95'])
