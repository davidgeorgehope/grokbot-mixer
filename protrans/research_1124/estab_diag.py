"""Do pros pick windows with a smaller predicted energy dip than our default outro-over-intro window? corpus_v2 pairs, read-only."""
import json, glob, os, sys, numpy as np
sys.path.insert(0, '/workspace/mixes/src2'); import energy_stab as E
ST = '/workspace/mixes/src2/st'; R = []
for fp in sorted(glob.glob('/workspace/mixes/protrans/corpus_v2/features/*.json')):
    f = json.load(open(fp)); c = f.get('cue') or {}; ta = (f.get('track_a') or {}).get('yt'); tb = (f.get('track_b') or {}).get('yt')
    ib, ob, ov = c.get('incoming_bar'), c.get('outgoing_bar'), f.get('overlap_bars')
    if None in (ib, ob, ov) or not ta or not tb: continue
    if not all(os.path.exists(f'{ST}/{y}.json') and os.path.exists(f'{ST}/{y}.sections.json') for y in (ta, tb)): continue
    ga = json.load(open(f'{ST}/{ta}.json'))['bar']; gb = json.load(open(f'{ST}/{tb}.json'))['bar']
    sa = json.load(open(f'{ST}/{ta}.sections.json')); sb = json.load(open(f'{ST}/{tb}.sections.json'))
    ov = int(min(max(round(ov), 8), 48)); ib = int(round(ib)); ob = int(round(ob))
    if ob + ov > len(ga['all']) or ib + ov > len(gb['all']): continue
    pro = E.predicted_dip(ga, gb, range(ob, ob + ov), range(ib, ib + ov))
    es = min(len(ga['all']), (sa['music_end'] // 8) * 8); q = sb['drop1'] - 16
    if q < 0 or es - 16 < 0: continue
    dflt = E.predicted_dip(ga, gb, range(es - 16, es), range(q, q + 16))
    # chance: same-length windows, outgoing exit anywhere in its second half on the 16 grid, incoming cue 0..80 on the 16 grid
    ch = []
    for e in range(len(ga['all']) // 2, len(ga['all']) - 1, 16):
        for qq in range(0, min(81, len(gb['all']) - ov), 16):
            if e - ov >= 0: ch.append(max(E.predicted_dip(ga, gb, range(e - ov, e), range(qq, qq + ov))))
    pct = float(np.mean(np.array(ch) < max(pro))) if ch else None
    R.append(dict(id=f['id'], pro=max(pro), dflt=max(dflt), pro_all=pro[0], dflt_all=dflt[0], pct=pct))
P = np.array([r['pro'] for r in R]); D = np.array([r['dflt'] for r in R]); pc = np.array([r['pct'] for r in R if r['pct'] is not None])
from scipy.stats import wilcoxon
out = dict(n=len(R), pro_med=round(float(np.median(P)), 2), dflt_med=round(float(np.median(D)), 2),
           pro_all_med=round(float(np.median([r['pro_all'] for r in R])), 2), dflt_all_med=round(float(np.median([r['dflt_all'] for r in R])), 2),
           pro_gt6=round(float((P > 6).mean()), 3), dflt_gt6=round(float((D > 6).mean()), 3),
           pro_pct_med=round(float(np.median(pc)), 3), wilcoxon_pro_vs_dflt_p=float(wilcoxon(P, D).pvalue))
json.dump(dict(summary=out, rows=R), open('/workspace/mixes/protrans/research_1124/estab_diag.json', 'w'), indent=1); print(json.dumps(out, indent=1))
