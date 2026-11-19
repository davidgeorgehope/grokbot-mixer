#!/usr/bin/env python3
"""Cache per-row v2 arrays (summed lows per bar, deck-to-deck onset lag + r per bar, audible mask, overlap bars) for rendered
variants, so any calibrated statistic can be re-counted without re-rendering. hc2_cache/arr_<variant>.pkl.
usage: hc2_arrays.py variant [variant ...]"""
import json, os, sys, pickle
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P), 'src2')
for p in (P, SRC2, H):
    if p not in sys.path: sys.path.insert(0, p)
import hardcheck_v2 as V
def arrays(variant):
    cp = os.path.join(H, 'hc2_cache', f'arr_{variant}.pkl'); out = pickle.load(open(cp, 'rb')) if os.path.exists(cp) else {}
    os.chdir(SRC2); import blend_diag as BD
    from engine import BS, BAR
    for l in open(os.path.join(H, 'gate_ckpt', variant + '.jsonl')):
        r = json.loads(l)
        if r.get('error') or r['id'] in out: continue
        M = json.load(open(r['meta'])); t = M['trans'][0]; s0, A, B = BD.crop_decks(M, 0)
        f = V.deck_feats_b(A, B, BS, BAR/4)
        out[r['id']] = dict(s=int(float(t['start_bar']) - s0), e=int(float(t['end_bar']) - s0), lows=f['lows'], lag=f['lag'], xr=f['xr'],
                            aud=V.audible_mask(f['allA'], f['allB']), hard_v1=r['hard'], dj=r['dj'], mix=r['mix'], win=r['win'])
        pickle.dump(out, open(cp, 'wb')); print(variant, r['id'], flush=True)
    return out
if __name__ == '__main__':
    for v in sys.argv[1:]: arrays(v)
