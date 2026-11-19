#!/usr/bin/env python3
"""Decision-level eval vs pros (primary signal) with grouped CV, bootstrap CIs and hard checks.
usage: analyze.py [--final] variant [variant ...]   (first variant = reference, normally 'default')
Dev = protrans 33 + corpus_v2 minus the final-holdout DJs in holdout.json; --final reports ONLY the holdout."""
import json, os, sys, numpy as np, collections
H = os.path.dirname(os.path.abspath(__file__)); CK = os.path.join(H, 'gate_ckpt')
HOLD = json.load(open(os.path.join(H, 'holdout.json')))['final_holdout_djs']

def load(v):
    rows = {}
    p = os.path.join(CK, v + '.jsonl')
    for l in open(p):
        r = json.loads(l); rows[r['id']] = r  # last row wins
    return rows

def subset(rows, final):
    return {k: r for k, r in rows.items() if (r['src'] == 'corpus_v2' and r['dj'] in HOLD) == final}

def metric(r, k):
    if r.get('error'): return None
    if k == 'exit_cue': return (r['err']['exit'] + r['err']['cue']) / 2
    if k == 'fade': return r.get('fade_err')
    return r['err'].get(k)

def boot_delta(ids, A, B, k, groups, n=4000, seed=20261118):
    """grouped (by mix) bootstrap of mean(B - A) over pairs where both have the metric"""
    d = collections.defaultdict(list)
    for i in ids:
        a, b = metric(A[i], k), metric(B[i], k)
        if a is not None and b is not None: d[groups[i]].append(b - a)
    G = list(d); rng = np.random.default_rng(seed)
    if not G: return None
    allv = [x for g in G for x in d[g]]; est = float(np.mean(allv)); bs = []
    for _ in range(n):
        s = rng.choice(len(G), len(G)); v = [x for j in s for x in d[G[j]]]; bs.append(np.mean(v))
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(n=len(allv), groups=len(G), delta=round(est, 2), ci=[round(float(lo), 2), round(float(hi), 2)],
                verdict='better' if hi < 0 else ('worse' if lo > 0 else 'no clear difference'))

def summarize(V, final=False, keys=('exit', 'cue', 'exit_cue', 'overlap', 'swap', 'fade')):
    R = {v: subset(load(v), final) for v in V}
    ids = sorted(set.intersection(*[set(r) for r in R.values()]))
    groups = {i: R[V[0]][i]['mix'] for i in ids}
    out = dict(n_pairs=len(ids), n_mixes=len(set(groups.values())), variants={})
    for v in V:
        rr = [R[v][i] for i in ids]; ok = [r for r in rr if not r.get('error')]
        hf = [r for r in ok if r['hard']['hard_fail']]
        s = dict(errors=len(rr) - len(ok), hard_fail=len(hf), hard_fail_ids=[(r['id'], [c for c in ('beat_clash', 'bass_hole', 'pumping') if r['hard'][c]]) for r in hf],
                 paths=dict(collections.Counter((r.get('fam') or 'ERR') for r in rr)))
        for k in keys:
            m = [metric(r, k) for r in ok]; m = [x for x in m if x is not None]
            s[k + '_median'] = round(float(np.median(m)), 1) if m else None; s[k + '_mean'] = round(float(np.mean(m)), 1) if m else None
            s[k + '_n'] = len(m)
        s['exit_within16'] = round(float(np.mean([r['err']['exit'] <= 16 for r in ok])), 3) if ok else None
        s['cue_within16'] = round(float(np.mean([r['err']['cue'] <= 16 for r in ok])), 3) if ok else None
        if v != V[0]:
            s['vs_' + V[0]] = {k: boot_delta(ids, R[V[0]], R[v], k, groups) for k in keys}
            sw = [(i, metric(R[v][i], 'exit_cue') - metric(R[V[0]][i], 'exit_cue')) for i in ids if metric(R[v][i], 'exit_cue') is not None and metric(R[V[0]][i], 'exit_cue') is not None]
            sw.sort(key=lambda x: -x[1]); s['worst_pairs'] = [(i, round(d, 1)) for i, d in sw[:5]]
        out['variants'][v] = s
    return out

if __name__ == '__main__':
    a = sys.argv[1:]; final = '--final' in a; V = [x for x in a if not x.startswith('--')]
    print(json.dumps(summarize(V, final), indent=1))
