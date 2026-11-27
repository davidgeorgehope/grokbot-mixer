"""Calibrate BASS_WAIT_DB = pro p95 of (incoming drop-body minus incoming lows at the pro's bass-swap bar).

Uses the 33 official pro transitions (protrans_decisions in_bar_at_swap + incoming source).
Band: <90 Hz, same as the lows_hole sensor. Writes nightly_1128_work/bass_wait_calib.json
and patches src2/bass_wait.py BASS_WAIT_DB. Does not write rules.json.
"""
from __future__ import annotations
import json, os, sys, numpy as np
from pathlib import Path

H = os.path.dirname(os.path.abspath(__file__))
P = os.path.dirname(H)
sys.path.insert(0, P)
sys.path.insert(0, H)
import st_pin
os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
import paths, run_admitted_tune as T, score
os.chdir(paths.SRC2)
if paths.SRC2 not in sys.path:
    sys.path.insert(0, paths.SRC2)
import blend_diag as BD
from engine import BS

DEC = json.load(open(os.path.join(H, 'protrans_decisions.json')))
OUT = os.path.join(H, 'nightly_1128_work', 'bass_wait_calib.json')
FC = 90.0


def drop_bars(sec):
    bars = []
    for a, b in (sec or {}).get('drops') or []:
        bars.extend(range(int(a), int(b)))
    return bars


def main():
    recs = T.load_recs()
    rows = []
    for rec in recs:
        d = DEC.get(rec['id']) or {}
        ib = d.get('in_bar_at_swap')
        if ib is None:
            continue
        sb = rec.get('sb') or os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        y = score._load(sb)
        y2 = np.stack([y, y], 1) if y.ndim == 1 else y
        n = int(len(y2) // BS)
        lo = BD.band_bar_db(y2, n, BS, 'low', FC)
        body_bars = drop_bars(d.get('sec_b'))
        from bass_wait import drop_body
        body = drop_body(lo, body_bars)
        if body is None:
            continue
        k = int(round(float(ib)))
        if not (0 <= k < len(lo)) or not np.isfinite(lo[k]):
            continue
        deficit = float(body) - float(lo[k])
        rows.append(dict(id=rec['id'], in_bar_at_swap=round(float(ib), 2), body=round(float(body), 2),
                         incoming=round(float(lo[k]), 2), deficit=round(deficit, 2)))
    defs = [r['deficit'] for r in rows]
    p95 = float(np.percentile(defs, 95)) if defs else None
    # Never wait for a tighter margin than the pro p95 (would be stricter than the pros).
    # Floor at 0 (incoming already at body).
    p95 = max(0.0, round(p95, 2)) if p95 is not None else None
    out = dict(n=len(rows), p95=p95, median=round(float(np.median(defs)), 2) if defs else None,
               mean=round(float(np.mean(defs)), 2) if defs else None,
               min=round(min(defs), 2) if defs else None, max=round(max(defs), 2) if defs else None,
               fc_hz=FC, rows=rows,
               note='BASS_WAIT_DB is this p95: incoming is "present" once it is within p95 dB of its drop body, the margin pros themselves use at the bass swap.')
    json.dump(out, open(OUT, 'w'), indent=2)
    print('CALIB', json.dumps({k: out[k] for k in out if k != 'rows'}), flush=True)
    if p95 is not None:
        bp = Path(os.path.join(paths.SRC2 if 'src2_pin' not in paths.SRC2 else '/workspace/mixes/src2', 'bass_wait.py'))
        # always patch live src2 (shadow is a symlink)
        bp = Path('/workspace/mixes/src2/bass_wait.py')
        txt = bp.read_text()
        # replace the assignment line
        import re
        txt2, n = re.subn(r'^BASS_WAIT_DB = .*$', f'BASS_WAIT_DB = {p95}  # pro p95, official 33, 90 Hz, {len(rows)} pairs', txt, count=1, flags=re.M)
        assert n == 1, 'could not patch BASS_WAIT_DB'
        bp.write_text(txt2)
        print('patched live bass_wait.BASS_WAIT_DB =', p95, flush=True)
    return out

if __name__ == '__main__':
    main()
