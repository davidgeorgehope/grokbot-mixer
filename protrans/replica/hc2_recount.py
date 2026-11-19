#!/usr/bin/env python3
"""Re-count hard fails with hardcheck v2 (thresholds from hardcheck_v2_calib.json, pro p95 only) on rendered variants.
CHOSEN (23:20): hard_fail = v2b bass hole (area, T0 30 dB, thr = pro p95) OR v1 beat clash OR engine half-beat fail OR v1
pumping. The v2b xcorr clash detector is counted for information only: held-out detection 6.7% at 110 ms (not adopted). Per-row flags cached in replica/hc2_cache/rows_<variant>.json. Then counts per variant on the 103 frozen ids,
the 91 DEV pairs, and the online-style policies (online_style.py protocol) with v1 vs v2 counts and the pairs that newly fail.
usage: hc2_recount.py default on gated [dropx dropc ...]"""
import json, os, sys, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P), 'src2')
for p in (P, SRC2, H):
    if p not in sys.path: sys.path.insert(0, p)
import hardcheck_v2 as V
CAL = json.load(open(os.path.join(H, 'hardcheck_v2_calib.json'))); TH = CAL['thresholds']; CH = CAL['chosen']

def flags_for(variant):
    cp = os.path.join(H, 'hc2_cache', f'rows2_{variant}.json'); out = json.load(open(cp)) if os.path.exists(cp) else {}
    os.chdir(SRC2); import blend_diag as BD
    from engine import BS, BAR
    for l in open(os.path.join(H, 'gate_ckpt', variant + '.jsonl')):
        r = json.loads(l)
        if r.get('error') or r['id'] in out: continue
        M = json.load(open(r['meta'])); t = M['trans'][0]; s0, A, B = BD.crop_decks(M, 0)
        s, e = int(float(t['start_bar']) - s0), int(float(t['end_bar']) - s0)
        f = V.deck_feats_b(A, B, BS, BAR/4); aud = V.audible_mask(f['allA'], f['allB'])
        h = V.hole_score(f['lows'], s, e, CH['T0']); c = V.clash_score_b(f['lag'], f['xr'], aud, CH['D'], CH['cmin'])
        hd = r['hard']; v2 = dict(hole_score=round(h, 1), clash_run=c, bass_hole=h > TH['hole'], clash_v2b=c > TH['clash'], beat_clash=bool(hd.get('beat_clash')),
                                  halfbeat_fail=bool(hd.get('halfbeat_fail')), pumping=bool(hd.get('pumping')))
        v2['hard_fail'] = bool(v2['bass_hole'] or v2['beat_clash'] or v2['halfbeat_fail'] or v2['pumping']); v2['v1_hard_fail'] = bool(hd['hard_fail']); v2['dj'] = r['dj']
        out[r['id']] = v2; json.dump(out, open(cp, 'w'))
    return out

def summ(F, ids):
    ids = [i for i in ids if i in F]
    return dict(n=len(ids), v2_fail=sum(F[i]['hard_fail'] for i in ids), v1_fail=sum(F[i]['v1_hard_fail'] for i in ids),
                v2_hole=sum(F[i]['bass_hole'] for i in ids), v1_clash=sum(F[i]['beat_clash'] for i in ids), v2b_clash_info_only=sum(F[i]['clash_v2b'] for i in ids), v1_hole=None,
                halfbeat=sum(F[i]['halfbeat_fail'] for i in ids), pump=sum(F[i]['pumping'] for i in ids))

if __name__ == '__main__':
    vs = sys.argv[1:] or ['default', 'on', 'gated']; F = {v: flags_for(v) for v in vs}
    fz = json.load(open(os.path.join(H, 'frozen_ids.json')))['ids']; hold = set(json.load(open(os.path.join(H, 'holdout.json')))['final_holdout_djs'])
    res = dict(thresholds=TH, chosen=CH, variants={})
    for v in vs:
        d = F[v]; dev = [i for i in fz if i in d and d[i]['dj'] not in hold]
        res['variants'][v] = dict(frozen103=summ(d, fz), dev=summ(d, dev))
        if v != 'default' and 'default' in F:
            res['variants'][v]['new_vs_default_103'] = sorted(i for i in fz if i in d and i in F['default'] and d[i]['hard_fail'] and not F['default'][i]['hard_fail'])
            res['variants'][v]['fixed_vs_default_103'] = sorted(i for i in fz if i in d and i in F['default'] and not d[i]['hard_fail'] and F['default'][i]['hard_fail'])
    json.dump(res, open(os.path.join(H, 'hc2_recount_' + '_'.join(vs) + '.json'), 'w'), indent=1, default=bool)
    print(json.dumps(res, indent=1, default=bool))
