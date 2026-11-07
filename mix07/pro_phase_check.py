#!/usr/bin/env python3
"""Re-run the calibrated energy gate (DROP_DB=12.2) and the new bar/downbeat
phase detector on the 37 admitted pro transitions. Pros should pass the phase
check; energy already calibrated so ~95% pass."""
from __future__ import annotations
import json, os, sys, time
import numpy as np
sys.path.insert(0, '/workspace/mixes/mix07')
import pro_check_r12 as P
sys.path.insert(0, '/workspace/mixes/src/tests')
import checks as C

P.DROP_DB = C.DROP_DB  # 12.2
OUT = '/workspace/mixes/mix07/pro_phase_results.json'
BEAT_MS = C.BEAT * 1000
PHASE_BEATS = C.PHASE_BEATS
CORR_MIN = C.CORR_MIN
INTERDECK_CORR = C.INTERDECK_CORR
TOL = C.TOL_DRIFT_MS

def xcorr_src(so, d0, k0, nb, lag_ms, fr=P.FR):
    nbf = int(round(P.BAR * fr))
    parts = []
    for j in range(nb):
        i0 = int((d0 + (k0 + j) * P.BAR + lag_ms / 1000.0) * fr)
        if i0 < 0 or i0 + nbf > len(so):
            return None
        parts.append(so[i0:i0 + nbf])
    return np.concatenate(parts)

def search_phase(get_pair):
    """get_pair(lag_ms) -> (a,b) arrays or None. Returns best + 0-lag."""
    fine = (-1e9, 0)
    for lag in range(-40, 41):
        pair = get_pair(lag)
        if pair is None:
            continue
        a, b = pair
        n = min(len(a), len(b))
        if n < 50:
            continue
        a, b = a[:n], b[:n]
        if a.std() == 0 or b.std() == 0:
            continue
        c = float(np.corrcoef(a, b)[0, 1])
        if c > fine[0]:
            fine = (c, lag)
    best = fine
    for bt in PHASE_BEATS:
        c0 = int(round(bt * BEAT_MS))
        for lag in range(c0 - 20, c0 + 21, 2):
            pair = get_pair(lag)
            if pair is None:
                continue
            a, b = pair
            n = min(len(a), len(b))
            if n < 50:
                continue
            a, b = a[:n], b[:n]
            if a.std() == 0 or b.std() == 0:
                continue
            c = float(np.corrcoef(a, b)[0, 1])
            if c > best[0]:
                best = (c, lag)
    return dict(lag=int(best[1]), corr=round(float(best[0]), 2) if best[0] > -1 else -1.0,
                lag_0=int(fine[1]), corr_0=round(float(fine[0]), 2) if fine[0] > -1 else -1.0,
                beat_off=round(best[1] / BEAT_MS, 2))

def fails_row(r):
    return r in C.alignment_failures([r])

def process(rec, cache):
    rid = rec['id']
    clip = os.path.join(P.CLIPS, rec['split'], rid, 'pro.wav')
    mix = P.load_audio(clip)
    n_bars = int(len(mix) / (P.BAR * P.SR))
    mix_o = P.onset(mix)
    mix_rms = P.bar_rms(mix, P.SR, n_bars)
    srcs, src_rms, src_map = {}, {}, {}
    for side, info in (('a', rec['a']), ('b', rec['b'])):
        yt = info['yt']
        y = P.load_audio(P.src_path(yt))
        ck = cache.get(rid, {}).get(side)
        loc = ck if ck and ck.get('track_t') is not None else P.VM.locate_in(mix, y)
        cache.setdefault(rid, {})[side] = loc
        o = P.onset(y)
        d0 = P.downbeat0(y, o)
        pres = P.presence(mix, y, loc, d0, n_bars)
        srcs[side] = dict(o=o, d0=d0, loc=loc, pres=pres, yt=yt, y=y)
        src_rms[side] = P.bar_rms(y, P.SR)
        src_map[side] = [P.src_bar_of(loc, d0, i) for i in range(n_bars)]
    ev = P.energy_events(mix_rms, src_rms, src_map)
    bad_e = [e for e in ev if not e['phrase']]
    rows = []
    for i in range(0, n_bars - 1):
        pA, pB = srcs['a']['pres'][i], srcs['b']['pres'][i]
        for D, O in (('a', 'b'), ('b', 'a')):
            pD, pO = srcs[D]['pres'][i], srcs[O]['pres'][i]
            if pD < 0.5 * max(pO, 1e-6) or pD < 0.12 or pO < 0.08:
                continue
            k0 = P.src_bar_of(srcs[D]['loc'], srcs[D]['d0'], i)
            if k0 is None:
                continue
            mo = mix_o[int(i * P.BAR * P.FR):int((i + 2) * P.BAR * P.FR)]
            def pair_mix(lag, _k0=k0, _D=D, _mo=mo):
                s = xcorr_src(srcs[_D]['o'], srcs[_D]['d0'], _k0, 2, lag)
                if s is None:
                    return None
                return _mo, s
            a = search_phase(pair_mix)
            row = dict(bar=i, deck=D, lag=a['lag'], corr=a['corr'], beat_off=a['beat_off'],
                       lag_0=a['lag_0'], corr_0=a['corr_0'], kind='mix')
            rows.append(row)
        if pA >= 0.15 and pB >= 0.15:
            kA = P.src_bar_of(srcs['a']['loc'], srcs['a']['d0'], i)
            kB = P.src_bar_of(srcs['b']['loc'], srcs['b']['d0'], i)
            if kA is not None and kB is not None:
                def pair_id(lag, _kA=kA, _kB=kB):
                    a = xcorr_src(srcs['a']['o'], srcs['a']['d0'], _kA, 2, 0)
                    b = xcorr_src(srcs['b']['o'], srcs['b']['d0'], _kB, 2, lag)
                    if a is None or b is None:
                        return None
                    return a, b
                p = search_phase(pair_id)
                rows.append(dict(bar=i, deck='a>b', lag=p['lag'], corr=p['corr'],
                                 beat_off=p['beat_off'], lag_0=p['lag_0'], corr_0=p['corr_0'],
                                 kind='interdeck'))
    bad = C.alignment_failures(rows)
    return dict(
        id=rid, dj=rec['dj'], split=rec['split'], pair=rec['pair'], n_bars=n_bars,
        energy_fail=bad_e, energy_pass=not bad_e,
        max_nonphrase_db=max([e['drop_db'] for e in bad_e], default=0.0),
        n_align=len(rows), n_fail=len(bad), align_pass=not bad,
        align_fail=bad[:12],
        locate={s: {k: srcs[s]['loc'].get(k) for k in ('z', 'cc', 'mix_t', 'track_t')} for s in srcs},
    )

def main():
    rows = json.load(open(P.ADMITTED))
    cache = json.load(open(P.CACHE)) if os.path.exists(P.CACHE) else {}
    results = []
    t0 = time.time()
    for n, rec in enumerate(rows, 1):
        print(f'\n[{n}/{len(rows)}] {rec["id"]} {rec["dj"]} {rec["pair"]}', flush=True)
        r = process(rec, cache)
        json.dump(cache, open(P.CACHE, 'w'), indent=1)
        print(f'  energy_pass={r["energy_pass"]} max_np={r["max_nonphrase_db"]}  '
              f'align_pass={r["align_pass"]} n_fail={r["n_fail"]}/{r["n_align"]}', flush=True)
        if r['align_fail']:
            print('   e.g.', r['align_fail'][0], flush=True)
        results.append(r)
        json.dump(dict(n=len(results), rows=results), open(OUT, 'w'), indent=1)
    n = len(results)
    summary = dict(
        n=n, elapsed_s=round(time.time() - t0, 1),
        DROP_DB=C.DROP_DB, TOL_DRIFT_MS=C.TOL_DRIFT_MS,
        CORR_MIN=C.CORR_MIN, INTERDECK_CORR=C.INTERDECK_CORR,
        energy_pass=sum(1 for r in results if r['energy_pass']),
        align_pass=sum(1 for r in results if r['align_pass']),
        energy_fails=[r['id'] for r in results if not r['energy_pass']],
        align_fails=[r['id'] for r in results if not r['align_pass']],
    )
    summary['energy_pct'] = round(100 * summary['energy_pass'] / n, 1)
    summary['align_pct'] = round(100 * summary['align_pass'] / n, 1)
    json.dump(dict(summary=summary, rows=results), open(OUT, 'w'), indent=1)
    print('\nSUMMARY', json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
