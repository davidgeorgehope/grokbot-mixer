#!/usr/bin/env python3
"""Print EXITPOS_GATE decisions for the 33 admitted-cohort pairs, using the same planner path as eval_cohort
(apply_rules from a rules copy + blend_bench.cands_for / families). Does not write rules.json."""
import os, sys, json, copy
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(H))
import paths, recreate, run_admitted_tune as T
LOG = '/tmp/epg_decisions_1119.jsonl'
if os.path.exists(LOG): os.remove(LOG)
os.makedirs('/tmp/protrans_bench', exist_ok=True)
os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'
os.environ['PREF_W'] = '0'
os.environ['EPG_LOG_FILE'] = LOG
sys.path.insert(0, paths.SRC2)
import blend_bench as BB

base = json.load(open(paths.RULES))
assert not base.get('EXITPOS') and not base.get('EXITPOS_GATE')
rules = copy.deepcopy(base); rules['EXITPOS'] = 1; rules['EXITPOS_GATE'] = 1
recs = T.load_recs()
floor = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(paths.RESULTS, 'score_ckpt', 'cb1119_base.jsonl'))}
rows = []
env = recreate.apply_rules(rules)
old = {k: os.environ.get(k) for k in env}
os.environ.update(env)
print(f"{'id':40} {'split':5} take  reason          default            alt                nat_short          vs_floor")
try:
    os.chdir(paths.SRC2)
    for rec in recs:
        i = rec['id']
        ya, yb = rec['a']['yt'], rec['b']['yt']
        n0 = sum(1 for _ in open(LOG)) if os.path.exists(LOG) else 0
        cs = BB.cands_for(ya, yb, 'epgdec_' + i.replace('/', '_')[-20:])
        fams = {c['fam']: c['win'] for c in BB.families(cs, None)}
        ns, nl = fams.get('nat_short'), fams.get('nat_long')
        # last gate line(s) for this pair
        decs = [json.loads(l) for l in open(LOG)][n0:]
        d = decs[-1] if decs else {}
        fw = (floor.get(i) or {}).get('pick', {}).get('win')
        take = d.get('take')
        sh, lg = d.get('short') or {}, d.get('long') or {}
        print(f"{i:40} {rec['split']:5} take={take!s:5} {str(d.get('reason','NO_LOG')):16} "
              f"short {sh.get('default')} -> {sh.get('alt')} {sh.get('take')} {sh.get('reason')}  "
              f"long {lg.get('default')} -> {lg.get('alt')} {lg.get('take')} {lg.get('reason')}  "
              f"ns={ns} floor={fw}")
        rows.append(dict(id=i, split=rec['split'], dj=rec['dj'], take=take, reason=d.get('reason'),
                         default=d.get('default'), alt=d.get('alt'), info=d,
                         short=sh, long=lg,
                         nat_short=ns, nat_long=nl, floor_fam=(floor.get(i) or {}).get('pick', {}).get('fam'),
                         floor_win=fw, blocked=(take is False), allowed=bool(take)))
finally:
    for k, v in old.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v
out = os.path.join(H, 'epg_decisions_1119.json')
json.dump(dict(n=len(rows), n_take=sum(bool(r['take']) for r in rows), n_block=sum(r['take'] is False for r in rows),
               n_no_log=sum(r['take'] is None for r in rows), rows=rows), open(out, 'w'), indent=1)
print('wrote', out)
print('take', sum(bool(r['take']) for r in rows), 'block', sum(r['take'] is False for r in rows), 'no_log', sum(r['take'] is None for r in rows))
# family vs default
from collections import Counter
print('floor fams', Counter(r['floor_fam'] for r in rows))
print('EPG nat_short==floor', sum(r['nat_short']==r['floor_win'] for r in rows if r['floor_fam']=='nat_short'),
      'of', sum(r['floor_fam']=='nat_short' for r in rows))
print('floor nat_long', [r['id'] for r in rows if r['floor_fam']=='nat_long'])
