"""Decision distance to the pro (bars) for default vs REPLICA cohort picks, plus per-pair similarity score."""
import json, os, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H)
PRO = json.load(open(os.path.join(H, 'protrans_decisions.json')))
def load(v):
    return {r['id']: r for r in map(json.loads, open(os.path.join(P, 'results', 'score_ckpt', v + '.jsonl')))}
D, Rp = load('d1118_base'), load('rp1118_replica_v2')
rows = []
for k, p in PRO.items():
    if k not in D or k not in Rp or p.get('out_bar_at_entry') is None: continue
    def dist(r):
        w = r['pick']['win']; return abs(w[1] - w[4] - p['out_bar_at_entry']), abs(w[3] - p['in_bar_at_entry'])
    do, di = dist(D[k]); ro, ri = dist(Rp[k])
    rows.append(dict(id=k, split=D[k]['split'], def_out=do, rep_out=ro, def_in=di, rep_in=ri, def_score=D[k]['score']['score'], rep_score=Rp[k]['score']['score'], rep_fam=Rp[k]['pick']['fam']))
a = lambda k: np.array([r[k] for r in rows], float)
out = dict(n=len(rows),
  exit_within16=dict(default=round(float(np.mean(a('def_out') <= 16)), 3), replica=round(float(np.mean(a('rep_out') <= 16)), 3)),
  exit_median=dict(default=float(np.median(a('def_out'))), replica=float(np.median(a('rep_out')))),
  cue_within16=dict(default=round(float(np.mean(a('def_in') <= 16)), 3), replica=round(float(np.mean(a('rep_in') <= 16)), 3)),
  exit_closer=int(np.sum(a('rep_out') < a('def_out'))), exit_further=int(np.sum(a('rep_out') > a('def_out'))),
  score_up=int(np.sum(a('rep_score') > a('def_score'))), score_down=int(np.sum(a('rep_score') < a('def_score'))),
  rows=rows)
json.dump(out, open(os.path.join(H, 'cohort_decisions.json'), 'w'), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != 'rows'}, indent=1))
