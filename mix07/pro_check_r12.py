#!/usr/bin/env python3
"""Run mix QA beat-align (TOL 10 ms, corr floor 0.65) and non-phrase energy-drop
(DROP_DB 6) on the 37 admitted pro transitions. Used to decide whether those
thresholds match the pro distribution."""
from __future__ import annotations
import json, os, sys, subprocess, time
import numpy as np
import soundfile as sf
import librosa

ROOT = '/workspace/mixes'
sys.path.insert(0, f'{ROOT}/protrans')
sys.path.insert(0, f'{ROOT}/src/eval')
import version_match as VM

ADMITTED = f'{ROOT}/protrans/results/admitted.json'
LIB = f'{ROOT}/protrans/lib'
CLIPS = f'{ROOT}/protrans/clips'
CACHE = f'{ROOT}/mix07/pro_check_cache.json'
OUT = f'{ROOT}/mix07/pro_check_results.json'
BPM = 174.0
BAR = 4 * 60 / BPM  # 1.379310...
SR = 22050
HOP = 64
FR = SR / HOP
DROP_DB = 6.0
TOL_MS = 10
CORR_FLOOR = 0.65
SPAN_MS = 40

def load_audio(path, sr=SR, t0=None, dur=None):
    cmd = ['ffmpeg', '-v', 'error']
    if t0 is not None:
        cmd += ['-ss', f'{float(t0):.3f}']
    cmd += ['-i', path]
    if dur is not None:
        cmd += ['-t', f'{float(dur):.3f}']
    cmd += ['-ac', '1', '-ar', str(sr), '-f', 'f32le', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()

def onset(y):
    return librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)

def downbeat0(y, o=None):
    """Phase of a 174 BPM 4-beat grid that maximises onset energy at bar starts."""
    o = onset(y) if o is None else o
    nbf = int(round(BAR * FR))
    best = ( -1.0, 0.0 )
    # search 0..BAR in 2 ms steps
    for ms in range(0, int(BAR * 1000), 2):
        d0 = ms / 1000.0
        sc = 0.0; n = 0
        i0 = int(d0 * FR)
        while i0 + 4 < len(o):
            sc += float(o[i0]); n += 1
            i0 += nbf
        if n:
            v = sc / n
            if v > best[0]:
                best = (v, d0)
    return best[1]

def bar_rms(y, sr, n=None):
    bs = BAR * sr
    n = n or int(len(y) / bs)
    out = np.full(n, -120.0)
    for i in range(n):
        seg = y[int(i * bs):int((i + 1) * bs)]
        if len(seg) < bs * 0.5:
            continue
        out[i] = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9)
    return out

def src_bar_of(loc, d0, mix_bar):
    """Source bar index playing at mix bar start, or None."""
    if not loc or loc.get('mix_t') is None or loc.get('track_t') is None:
        return None
    mix_t = mix_bar * BAR
    src_t = loc['track_t'] + (mix_t - loc['mix_t'])
    k = (src_t - d0) / BAR
    if k < -0.5:
        return None
    return int(round(k))

def energy_events(mix_rms, src_rms, src_map):
    """Same rule as checks.energy_events: drop vs prior-8 median, phrase if a mapped
    source's own bar is within 4 dB of that drop relative to its neighbours."""
    ev = []
    R = mix_rms
    for i in range(8, len(R) - 1):
        if not np.isfinite(R[i]) or R[i] < -80:
            continue
        base = np.median(R[i - 8:i])
        dlt = base - R[i]
        if dlt < DROP_DB or R[i - 1] < base - DROP_DB:
            continue
        phr = False
        for sid, rms in src_rms.items():
            k = src_map[sid][i] if i < len(src_map[sid]) else None
            if k is None or k < 0 or k >= len(rms):
                continue
            ctx = np.concatenate([rms[max(0, k - 8):k], rms[k + 1:k + 9]]) if k < 8 else rms[k - 8:k]
            if len(ctx) and np.median(ctx) - rms[k] >= dlt - 4:
                phr = True
        ev.append(dict(bar=i, t=round(i * BAR, 2), drop_db=round(float(dlt), 2), phrase=bool(phr)))
    return ev

def presence(mix, src, loc, d0, n_bars):
    """Per-bar Pearson corr of 1-bar waveforms (presence proxy for the 6 dB skip)."""
    out = np.zeros(n_bars)
    if not loc or loc.get('mix_t') is None:
        return out
    bs = int(BAR * SR)
    for i in range(n_bars):
        k = src_bar_of(loc, d0, i)
        if k is None or k < 0:
            continue
        a = mix[int(i * bs):int((i + 1) * bs)]
        b = src[int((d0 + k * BAR) * SR):int((d0 + (k + 1) * BAR) * SR)]
        n = min(len(a), len(b))
        if n < bs * 0.5:
            continue
        a, b = a[:n], b[:n]
        if a.std() < 1e-6 or b.std() < 1e-6:
            continue
        out[i] = float(np.corrcoef(a, b)[0, 1])
    return out

def deck_align(mix_o, src_o, d0, loc, mix_bar, nb=2, span_ms=SPAN_MS):
    k0 = src_bar_of(loc, d0, mix_bar)
    if k0 is None:
        return None
    m = mix_o[int(mix_bar * BAR * FR):int((mix_bar + nb) * BAR * FR)]
    nbf = int(round(BAR * FR))
    best = (-1e9, 0)
    for lag_ms in range(-span_ms, span_ms + 1):
        parts = []
        ok = True
        for j in range(nb):
            kj = k0 + j
            i0 = int((d0 + kj * BAR + lag_ms / 1000.0) * FR)
            if i0 < 0 or i0 + nbf > len(src_o):
                ok = False
                break
            parts.append(src_o[i0:i0 + nbf])
        if not ok:
            continue
        s = np.concatenate(parts)[:len(m)]
        if len(s) < len(m) or s.std() == 0 or m.std() == 0:
            continue
        c = float(np.corrcoef(m, s)[0, 1])
        if c > best[0]:
            best = (c, lag_ms)
    if best[0] < -1:
        return None
    return dict(lag=int(best[1]), corr=round(float(best[0]), 3), src_bar=int(k0))

def align_report(mix_o, sources, n_bars):
    """sources: {id: {o, d0, loc, pres}} — same skip + corr floor as checks.bar_alignment_report."""
    rows, bad = [], []
    ids = list(sources)
    if len(ids) < 2:
        return rows, bad
    A, B = ids
    for i in range(0, n_bars - 1):
        for D, O in ((A, B), (B, A)):
            pD, pO = sources[D]['pres'][i], sources[O]['pres'][i]
            # skip if this deck is clearly under the other (~6 dB / 0.5 linear gain)
            if pD < 0.5 * max(pO, 1e-6) or pD < 0.12:
                continue
            # only count overlap-ish bars (other deck also somewhat present) — the mix test
            # iterates overlap of planned decks; here presence stands in
            if pO < 0.08:
                continue
            a = deck_align(mix_o, sources[D]['o'], sources[D]['d0'], sources[D]['loc'], i)
            if not a:
                continue
            row = dict(bar=i, deck=D, lag=a['lag'], corr=a['corr'], src_bar=a['src_bar'], pres=round(float(pD), 3))
            rows.append(row)
            if a['corr'] >= CORR_FLOOR and abs(a['lag']) > TOL_MS:
                bad.append(row)
    return rows, bad

def src_path(yt):
    p = os.path.join(LIB, f'{yt}.m4a')
    if os.path.exists(p):
        return p
    for e in ('.wav', '.mp3', '.webm'):
        q = os.path.join(LIB, f'{yt}{e}')
        if os.path.exists(q):
            return q
    raise FileNotFoundError(yt)

def main():
    rows = json.load(open(ADMITTED))
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    results = []
    t0 = time.time()
    for n, rec in enumerate(rows, 1):
        rid = rec['id']
        clip = os.path.join(CLIPS, rec['split'], rid, 'pro.wav')
        print(f'\n[{n}/{len(rows)}] {rid} {rec["dj"]} {rec["pair"]}', flush=True)
        mix = load_audio(clip)
        n_bars = int(len(mix) / (BAR * SR))
        mix_o = onset(mix)
        mix_rms = bar_rms(mix, SR, n_bars)
        srcs = {}
        src_rms = {}
        src_map = {}
        for side, info in (('a', rec['a']), ('b', rec['b'])):
            yt = info['yt']
            y = load_audio(src_path(yt))
            ck = cache.get(rid, {}).get(side)
            if ck and ck.get('track_t') is not None:
                loc = ck
            else:
                loc = VM.locate_in(mix, y)
                cache.setdefault(rid, {})[side] = loc
                json.dump(cache, open(CACHE, 'w'), indent=1)
            print(f'  {side} locate z={loc.get("z")} cc={loc.get("cc")} mix_t={loc.get("mix_t")} track_t={loc.get("track_t")}', flush=True)
            o = onset(y)
            d0 = downbeat0(y, o)
            pres = presence(mix, y, loc, d0, n_bars)
            srcs[side] = dict(o=o, d0=d0, loc=loc, pres=pres, yt=yt)
            src_rms[side] = bar_rms(y, SR)
            src_map[side] = [src_bar_of(loc, d0, i) for i in range(n_bars)]
        ev = energy_events(mix_rms, src_rms, src_map)
        bad_e = [e for e in ev if not e['phrase']]
        aligns, bad_a = align_report(mix_o, srcs, n_bars)
        # per-transition summaries
        lags = [abs(r['lag']) for r in aligns if r['corr'] >= CORR_FLOOR]
        r = dict(
            id=rid, dj=rec['dj'], split=rec['split'], pair=rec['pair'],
            n_bars=n_bars,
            energy_events=ev, energy_fail=bad_e,
            energy_pass=not bad_e,
            max_nonphrase_db=max([e['drop_db'] for e in bad_e], default=0.0),
            max_any_drop_db=max([e['drop_db'] for e in ev], default=0.0),
            n_align=len(aligns), n_align_hi=len(lags),
            align_fail=bad_a, align_pass=not bad_a,
            max_abs_lag_hi=max(lags, default=None),
            p95_abs_lag_hi=round(float(np.percentile(lags, 95)), 1) if lags else None,
            median_abs_lag_hi=round(float(np.median(lags)), 1) if lags else None,
            locate={s: {k: srcs[s]['loc'].get(k) for k in ('z', 'cc', 'mix_t', 'track_t')} for s in srcs},
            d0={s: round(srcs[s]['d0'], 4) for s in srcs},
        )
        print(f'  energy fail={len(bad_e)} max_np={r["max_nonphrase_db"]}  align fail={len(bad_a)}/{len(lags)} max|lag|={r["max_abs_lag_hi"]}', flush=True)
        results.append(r)
        json.dump(dict(n=len(results), rows=results), open(OUT, 'w'), indent=1)

    def pct_pass(key):
        return round(100 * sum(1 for r in results if r[key]) / len(results), 1)

    # distributions for calibration
    max_np = sorted(r['max_nonphrase_db'] for r in results)
    max_lag = sorted(r['max_abs_lag_hi'] for r in results if r['max_abs_lag_hi'] is not None)

    def q(xs, p):
        return None if not xs else round(float(np.percentile(xs, p)), 2)

    # What DROP_DB / TOL would make 95% of transitions pass?
    drop95 = q(max_np, 95)
    lag95 = q(max_lag, 95)
    # corr-floor sweep: fraction of transitions that fail align at each floor, still TOL=10
    floors = [0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
    floor_stats = []
    for fl in floors:
        n_fail = 0
        n_hi = 0
        worst = []
        for r in results:
            bad = [a for a in r['align_fail'] if a['corr'] >= fl] if fl == CORR_FLOOR else None
        # recompute from stored rows: we only stored fails at 0.65+. For higher floors, filter those.
        # For floors > 0.65, fails are subset of align_fail. For measuring pass rate we also need
        # max|lag| among rows with corr>=fl — we didn't store all align rows (too big).
        # Recompute pass from align_fail only: a trans fails at floor fl iff some align_fail has corr>=fl
        # That's correct because align_fail is |lag|>10 and corr>=0.65; higher floor just drops some fails.
        # It does NOT introduce new fails.
        nf = sum(1 for r in results if any(a['corr'] >= fl for a in r['align_fail']))
        floor_stats.append(dict(corr_floor=fl, n_fail=nf, n_pass=len(results)-nf,
                                pct_pass=round(100*(len(results)-nf)/len(results), 1)))

    summary = dict(
        n=len(results),
        elapsed_s=round(time.time() - t0, 1),
        thresholds=dict(DROP_DB=DROP_DB, TOL_MS=TOL_MS, CORR_FLOOR=CORR_FLOOR),
        energy=dict(
            n_pass=sum(1 for r in results if r['energy_pass']),
            pct_pass=pct_pass('energy_pass'),
            max_nonphrase_db=dict(p50=q(max_np, 50), p90=q(max_np, 90), p95=q(max_np, 95),
                                  p100=q(max_np, 100), values=max_np),
            drop_db_for_95pct_pass=drop95,
        ),
        align=dict(
            n_pass=sum(1 for r in results if r['align_pass']),
            pct_pass=pct_pass('align_pass'),
            max_abs_lag_hi=dict(p50=q(max_lag, 50), p90=q(max_lag, 90), p95=q(max_lag, 95),
                                p100=q(max_lag, 100), values=max_lag),
            tol_for_95pct_pass=lag95,
            corr_floor_sweep=floor_stats,
        ),
        fails_energy=[dict(id=r['id'], dj=r['dj'], max_db=r['max_nonphrase_db'], ev=r['energy_fail'][:4])
                      for r in results if not r['energy_pass']],
        fails_align=[dict(id=r['id'], dj=r['dj'], max_lag=r['max_abs_lag_hi'], n_bad=len(r['align_fail']),
                          sample=r['align_fail'][:4])
                     for r in results if not r['align_pass']],
    )
    json.dump(dict(summary=summary, rows=[{k: v for k, v in r.items() if k not in ('align_fail',) or True}
                                          for r in results]), open(OUT, 'w'), indent=1)
    print('\n==== SUMMARY ====', json.dumps(summary, indent=2, default=float))

if __name__ == '__main__':
    main()
