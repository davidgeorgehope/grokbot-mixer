"""Grid-free truth from the pro: fit each deck's STRETCHED audio (src2/st/<id>.wav, the audio our grid lives on) into the pro clip
(score._deck_line: band-power chunk line + onset fine shift), then read both decks' position on OUR beat grids at the middle of the
span where both are located. A pro DJ beatmatches by ear, so the decks' grid phases should agree (diff ~0 ms) if our grids are right.
diff = (A grid beat frac - B grid beat frac) in ms (+ = A's grid is late vs B's relative to the music the pro lined up).
Run on our own clip as a control (should read our engine's lock: 0 or the BLEND_LOCK value)."""
import json, os, sys
import numpy as np
sys.path.insert(0, '/workspace/mixes/protrans'); sys.path.insert(0, '/workspace/mixes/src/eval')
import score as S, paths
import run_admitted_tune as T
import control_curves as CC
ST = '/workspace/mixes/src2/st'
def grid_phase(y, ida, idb):
    Fm, em = CC.bandpow(y), S._fine_env(y); out = {}
    for nm, yid in (('a', ida), ('b', idb)):
        ln = S._deck_line(y, Fm, em, f'{ST}/{yid}.wav'); g = json.load(open(f'{ST}/{yid}.json'))
        if not ln: return dict(error=f'deck {nm} not located')
        out[nm] = dict(ln, d0=g['downs'][0], per=g['per'], beats=g['beats'])
    m0 = max(out['a']['span'][0], out['b']['span'][0]); m1 = min(out['a']['span'][1], out['b']['span'][1])
    tc = (m0 + m1) / 2 if m1 > m0 else len(y) / S.SR / 2
    def frac(o):
        st_t = (tc - o['a']) / o['s']; b = np.array(o['beats']); k = np.searchsorted(b, st_t) - 1
        k = int(np.clip(k, 0, len(b) - 2)); return (st_t - b[k]) / (b[k + 1] - b[k])
    d = float((frac(out['a']) - frac(out['b']) + 0.5) % 1.0 - 0.5)
    return dict(diff_ms=round(d * 60 / 174 * 1000, 1), r_a=out['a']['r'], r_b=out['b']['r'], rate=round(1 / out['a']['s'], 4), tc=round(tc, 1), both_span=[round(m0, 1), round(m1, 1)])
def run(pid, ours=None):
    rec = {r['id']: r for r in T.load_recs()}[pid]; ida, idb = rec['a']['yt'], rec['b']['yt']
    res = dict(pick=pid, a=ida, b=idb, pair=rec['pair'], pro=grid_phase(S._load(rec['pro_clip']), ida, idb))
    if ours: res['ours'] = grid_phase(S._load(ours), ida, idb)
    return res
if __name__ == '__main__':
    for pid in sys.argv[1:]:
        ours = None
        if '=' in pid: pid, ours = pid.split('=', 1)
        try: print(json.dumps(run(pid, ours)), flush=True)
        except Exception as e: print(pid, 'ERR', type(e).__name__, str(e)[-200:], flush=True)
