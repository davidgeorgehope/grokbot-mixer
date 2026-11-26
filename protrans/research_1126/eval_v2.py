"""Compute official_v2-place8c (protrans/score_v2.py) for existing cohort checkpoints without re-rendering.
Resumable jsonl per variant in protrans/research_1125/v2_<variant>.jsonl.
Usage: python3 protrans/research_1125/eval_v2.py <variant> [<variant> ...]"""
import json, os, sys, statistics
sys.path.insert(0, '/workspace/mixes/protrans')
import paths, run_admitted_tune as T, score_v2 as S2

OUT = '/workspace/mixes/protrans/research_1126'
recs = {r['id']: r for r in T.load_recs()}

for var in sys.argv[1:]:
    ck = T.load_ckpt(var)
    outp = os.path.join(OUT, f'v2_{var}.jsonl')
    have = {}
    if os.path.exists(outp):
        for l in open(outp):
            row = json.loads(l)
            have[row['id']] = row
    with open(outp, 'a') as fh:
        for rid, row in sorted(ck.items()):
            if rid in have or rid not in recs or not row.get('ours') or not os.path.exists(row['ours']):
                continue
            r = recs[rid]
            sa = os.path.join(paths.LIB, r['a']['yt'] + '.m4a')
            sb = os.path.join(paths.LIB, r['b']['yt'] + '.m4a')
            res = S2.score_v2(r['pro_clip'], row['ours'], sa, sb, v1=row.get('score'))
            item = dict(id=rid, split=r['split'], dj=r['dj'], v1=res['score'], v2=res['official_v2'],
                        parts=(res.get('placement') or {}).get('parts'))
            fh.write(json.dumps(item) + '\n'); fh.flush()
            have[rid] = item
            print(var, rid, item['split'], 'v1=', item['v1'], 'v2=', item['v2'], flush=True)
    rows = list(have.values())
    sm = {}
    for sp in ('train', 'test', 'all'):
        sub = [x for x in rows if sp == 'all' or x['split'] == sp]
        if sub:
            sm[sp] = dict(n=len(sub),
                          v1_mean=round(statistics.mean(x['v1'] for x in sub), 2),
                          v2_mean=round(statistics.mean(x['v2'] for x in sub), 2))
    print('V2_SUMMARY', var, json.dumps(sm), flush=True)
