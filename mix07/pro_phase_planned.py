#!/usr/bin/env python3
"""Run the current checks.alignment_failures detector on the 37 admitted pro
transitions using planned-deck maps (locate mix_t/track_t → source bar per mix
bar) and the real library source files. No presence-proxy overlap skip."""
from __future__ import annotations
import json, os, sys, time
import numpy as np
import librosa

sys.path.insert(0, '/workspace/mixes/mix07')
sys.path.insert(0, '/workspace/mixes/src/tests')
import pro_check_r12 as P
import checks as C

OUT = '/workspace/mixes/mix07/pro_phase_planned.json'
LOG = '/workspace/mixes/mix07/pro_phase_planned.log'
FR = 22050 / 64

def deck_from_locate(yt, loc, d0, n_bars, n_src_bars):
    """Build a mix_simple-like deck: full_map[i] is the source bar planned at mix bar start+i."""
    pairs = []
    for i in range(n_bars):
        k = P.src_bar_of(loc, d0, i)
        if k is None or k < 0 or k >= n_src_bars:
            continue
        pairs.append((i, int(k)))
    if not pairs:
        return None
    a0, a1 = pairs[0][0], pairs[-1][0] + 1
    full = []
    for i in range(a0, a1):
        k = P.src_bar_of(loc, d0, i)
        if k is None:
            # linear plan from locate even if slightly out of range; skip later via src window
            mix_t = i * P.BAR
            src_t = loc['track_t'] + (mix_t - loc['mix_t'])
            k = int(round((src_t - d0) / P.BAR))
        full.append([int(k), 'mix'])
    return dict(id=yt, start_bar=a0, end_bar=a1, full_map=full,
                auto={'gain': [[float(a0), 1.0], [float(a1), 1.0]]}, acap=False)

def process(rec, cache):
    rid = rec['id']
    clip = os.path.join(P.CLIPS, rec['split'], rid, 'pro.wav')
    mix = P.load_audio(clip)  # 22050
    n_bars = int(len(mix) / (P.BAR * P.SR))
    mix_o = P.onset(mix)
    srcs = {}
    decks = []
    for side, info in (('a', rec['a']), ('b', rec['b'])):
        yt = info['yt']
        y = P.load_audio(P.src_path(yt))  # 22050
        ck = cache.get(rid, {}).get(side)
        loc = ck if ck and ck.get('track_t') is not None else P.VM.locate_in(mix, y)
        cache.setdefault(rid, {})[side] = loc
        o = P.onset(y)
        d0 = P.downbeat0(y, o)
        n_src = max(1, int(len(y) / (P.BAR * P.SR)))
        d = deck_from_locate(yt, loc, d0, n_bars, n_src)
        srcs[side] = dict(o=o, d0=d0, loc=loc, yt=yt, n_src=n_src)
        decks.append(d)
    if any(d is None for d in decks):
        return dict(id=rid, dj=rec['dj'], split=rec['split'], pair=rec['pair'],
                    n_bars=n_bars, n_align=0, n_fail=0, align_pass=False,
                    error='no_valid_planned_bars',
                    locate={s: {k: srcs[s]['loc'].get(k) for k in ('z', 'cc', 'mix_t', 'track_t')} for s in srcs})

    # Point checks.py at this clip + these sources (same search/fail rules as Mix 07).
    C.onset = lambda: (mix_o, FR)
    store = {srcs['a']['yt']: (srcs['a']['o'], srcs['a']['d0']),
             srcs['b']['yt']: (srcs['b']['o'], srcs['b']['d0'])}
    C.src_onset = lambda b, _s=store: _s[b]
    C.nudge_ms = lambda b, k: 0
    rows = C.bar_alignment_report(deck_pair=(decks[0], decks[1]))
    bad = C.alignment_failures(rows)
    return dict(
        id=rid, dj=rec['dj'], split=rec['split'], pair=rec['pair'], n_bars=n_bars,
        deck_span=[(d['start_bar'], d['end_bar']) for d in decks],
        overlap=[max(decks[0]['start_bar'], decks[1]['start_bar']),
                 min(decks[0]['end_bar'], decks[1]['end_bar'])],
        n_align=len(rows), n_fail=len(bad), align_pass=not bad,
        n_mix=sum(1 for r in rows if r.get('kind')=='mix'),
        n_mix_fail=sum(1 for r in bad if r.get('kind')=='mix'),
        align_fail=bad[:12],
        locate={s: {k: srcs[s]['loc'].get(k) for k in ('z', 'cc', 'mix_t', 'track_t')} for s in srcs},
        d0={s: round(float(srcs[s]['d0']), 4) for s in srcs},
    )

def main():
    rows = json.load(open(P.ADMITTED))
    cache = json.load(open(P.CACHE)) if os.path.exists(P.CACHE) else {}
    results = []
    t0 = time.time()
    for n, rec in enumerate(rows, 1):
        print(f'\n[{n}/{len(rows)}] {rec["id"]} {rec["dj"]} {rec["pair"]}', flush=True)
        try:
            r = process(rec, cache)
        except Exception as e:
            r = dict(id=rec['id'], dj=rec['dj'], pair=rec['pair'], align_pass=False,
                     error=repr(e), n_align=0, n_fail=-1)
            print('  ERR', e, flush=True)
        json.dump(cache, open(P.CACHE, 'w'), indent=1)
        print(f'  align_pass={r.get("align_pass")} n_fail={r.get("n_fail")}/{r.get("n_align")} '
              f'overlap={r.get("overlap")} err={r.get("error")}', flush=True)
        if r.get('align_fail'):
            print('   e.g.', r['align_fail'][0], flush=True)
        results.append(r)
        json.dump(dict(n=len(results), rows=results), open(OUT, 'w'), indent=1)
    n = len(results)
    ok = [r for r in results if r.get('align_pass')]
    summary = dict(
        n=n, elapsed_s=round(time.time() - t0, 1),
        DROP_DB=C.DROP_DB, TOL_DRIFT_MS=C.TOL_DRIFT_MS, CORR_MIN=C.CORR_MIN,
        method='planned_decks_real_sources',
        align_pass=len(ok),
        align_pct=round(100 * len(ok) / n, 1) if n else 0,
        align_fails=[r['id'] for r in results if not r.get('align_pass')],
        n_empty=[r['id'] for r in results if r.get('n_align') == 0],
    )
    json.dump(dict(summary=summary, rows=results), open(OUT, 'w'), indent=1)
    print('\nSUMMARY', json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
