#!/usr/bin/env python3
"""2026-11-19: slowdown profiles (slowdown.py) for every track in the dev pairs and the protrans cohort. Tracks whose stretched grid wav was
cleaned up are re-prepped exactly as recreate does, profiled, then the files this created are removed again."""
import os, sys, json
from multiprocessing import Pool
H = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(H); P = os.path.dirname(R)
sys.path.insert(0, H); sys.path.insert(0, R); sys.path.insert(0, P)
SRC2 = '/workspace/mixes/src2'
def job(a):
    yt, src = a; created = []
    import slowdown as SD, recreate
    try:
        if not os.path.exists(os.path.join(SRC2, 'st', yt + '.wav')) or not os.path.exists(os.path.join(SRC2, 'st', yt + '.json')):
            if not (src and os.path.exists(src)): return yt, 'no audio'
            recreate._prep_track(yt, src, created)
        if not os.path.exists(os.path.join(SRC2, 'st', yt + '.sections.json')):
            os.chdir(SRC2); sys.path.insert(0, SRC2); import sections; sections.get(yt)  # 2026-11-19 fix: src2 on sys.path
        p = SD.profile(yt); return yt, (p or {}).get('sections', 'fail')
    except Exception as ex: return yt, f'err {type(ex).__name__}: {ex}'[:200]
    finally:
        for f in created:
            if f.endswith('.slowdown.json') or f.endswith('.sections.json'): continue
            try: os.remove(f)
            except OSError: pass
if __name__ == '__main__':
    import eval_gate as EG
    T = {}
    for p in EG.pairs(): T.setdefault(p['a'], p.get('sa')); T.setdefault(p['b'], p.get('sb'))
    todo = [(y, s) for y, s in T.items() if not os.path.exists(os.path.join(SRC2, 'st', y + '.slowdown.json'))]
    print('tracks', len(T), 'todo', len(todo), flush=True)
    with Pool(5) as pool:
        for i, (y, r) in enumerate(pool.imap_unordered(job, todo)): print(i, y, r, flush=True)
