"""Precompute src2/consonance.py per-bar peak caches for the 33-pair protrans cohort (2026-11-19)."""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import paths, run_admitted_tune as T
sys.path.insert(0, paths.SRC2)
import consonance as C
ids = sorted({y for r in T.load_recs() for y in (r['a']['yt'], r['b']['yt'])})
for i, y in enumerate(ids):
    t = time.time(); P = C.track_peaks(y)
    print(i + 1, len(ids), y, len(P), round(time.time() - t, 1), flush=True)
