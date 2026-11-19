"""Score a judge run. usage: metrics.py runs/<ver>_<split>.jsonl [...]  -> prints + writes runs/<name>.metrics.json"""
import json, sys, math, collections
DEF = ['beat_clash', 'bass_hole', 'level_pump', 'bad_cue']
HKEY = dict(beat_clash='beat_clash', bass_hole='bass_hole', level_pump='pumping')

def wilson(k, n, z=1.96):
    if n == 0: return (None, None)
    p = k / n; d = 1 + z*z/n; c = p + z*z/(2*n); h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)); return (round((c-h)/d, 2), round((c+h)/d, 2))

def present(o, d):
    v = (o or {}).get(d)
    return bool(v.get('present')) if isinstance(v, dict) else bool(v)

def pr(rows, truth_fn, d):
    tp = fp = fn = tn = 0
    for r in rows:
        t, p = truth_fn(r, d), present(r['out'], d)
        if t is None: continue
        tp += t and p; fp += (not t) and p; fn += t and not p; tn += (not t) and not p
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=round(tp/(tp+fp), 2) if tp+fp else None, recall=round(tp/(tp+fn), 2) if tp+fn else None)

def score(rows):
    M = {}
    D = [r for r in rows if r['task'] == 'defect' and '_error' not in r['out']]
    if D:
        d0 = [r for r in D if r['rep'] == 0]
        M['defect_vs_truth'] = {d: pr(d0, lambda r, d: r['truth'].get(d), d) for d in DEF}
        M['defect_vs_truth_by_source'] = {s: {d: pr([r for r in d0 if r['source'] == s], lambda r, d: r['truth'].get(d), d) for d in DEF}
                                          for s in sorted({r['source'] for r in d0})}
        M['defect_vs_hardcheck'] = {d: pr(d0, lambda r, d: (r.get('hard') or {}).get(HKEY[d]), d) for d in HKEY}
        M['hardcheck_vs_truth'] = {d: dict(zip(('tp', 'fp', 'fn'), (
            sum(1 for r in d0 if r['truth'].get(d) and (r.get('hard') or {}).get(HKEY[d])),
            sum(1 for r in d0 if not r['truth'].get(d) and (r.get('hard') or {}).get(HKEY[d])),
            sum(1 for r in d0 if r['truth'].get(d) and not (r.get('hard') or {}).get(HKEY[d]))))) for d in HKEY}
        anyt = [(any(r['truth'].get(d) for d in DEF), any(present(r['out'], d) for d in DEF)) for r in d0]
        M['any_defect'] = dict(n=len(anyt), acc=round(sum(a == b for a, b in anyt)/len(anyt), 2),
                               false_alarm_on_clean=f"{sum(b and not a for a, b in anyt)}/{sum(not a for a, _ in anyt)}",
                               caught=f"{sum(a and b for a, b in anyt)}/{sum(a for a, _ in anyt)}")
        g = collections.defaultdict(list)
        for r in D: g[r['case']].append(tuple(present(r['out'], d) for d in DEF))
        multi = [v for v in g.values() if len(v) > 1]
        if multi: M['defect_rep_flip_rate'] = f"{sum(len(set(v)) > 1 for v in multi)}/{len(multi)} cases changed answer across repeats"
    for task, key in (('pair', 'winner'), ('dec', 'closer')):
        T = [r for r in rows if r['task'] == task and '_error' not in r['out']]
        if not T: continue
        first = 'A' if task == 'pair' else 'X'
        groups = collections.defaultdict(list)
        for r in T: groups[(r.get('src') or r.get('kind'))].append(r)
        for gname, G in sorted(groups.items()) + [('all', T)]:
            k = sum(r['out'].get(key) == r['truth'] for r in G); n = len(G)
            pos = sum(r['out'].get(key) == first for r in G)
            byc = collections.defaultdict(dict)
            for r in G: byc[(r['case'], r['rep'])][r['order']] = r['out'].get(key) == r['truth']
            both = [v for v in byc.values() if len(v) == 2]
            cons = sum(len(set(v.values())) == 1 for v in both)
            rr = collections.defaultdict(list)
            for r in G: rr[(r['case'], r['order'])].append(r['out'].get(key))
            mr = [v for v in rr.values() if len(v) > 1]
            M[f'{task}:{gname}'] = dict(n_calls=n, accuracy=round(k/n, 2), ci95=wilson(k, n), picks_first_slot=round(pos/n, 2),
                                         swap_consistent=f'{cons}/{len(both)}', both_orders_right=f"{sum(all(v.values()) for v in both)}/{len(both)}",
                                         rep_flips=f'{sum(len(set(v)) > 1 for v in mr)}/{len(mr)}' if mr else None)
    return M

if __name__ == '__main__':
    rows = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
    M = score(rows); print(json.dumps(M, indent=1))
    json.dump(M, open(sys.argv[1].replace('.jsonl', '.metrics.json'), 'w'), indent=1)
