"""33-pair cohort, DRUMCLASH=1 v3 (pulse + lattice, pro-p95 gated; pick-time mild, render veto) on top of rules.json (no rules.json write). Floor n1120_base: held-out 34.07, train 32.40, 0 fails."""
import json, os, sys, copy
sys.path.insert(0, '/workspace/mixes/protrans')
import paths, run_admitted_tune as T
recs = T.load_recs(); rules = json.load(open(paths.RULES)); trial = copy.deepcopy(rules); trial['DRUMCLASH'] = 1
base = T.summarize(T.run_set_checkpointed(recs, rules, 'n1120_base', 'bx'))
rows = T.run_set_checkpointed(recs, trial, 'dclash3_1120', 'dc3', workers=3)
sm = T.summarize(rows)
changed = []
bb = {r['id']: r for r in T.run_set_checkpointed(recs, rules, 'n1120_base', 'bx')}
for r in rows:
    b = bb.get(r['id'])
    if b and not r.get('error') and (r.get('pick') or {}).get('win') != (b.get('pick') or {}).get('win'):
        changed.append(dict(id=r['id'], split=r['split'], base=b['score']['score'], new=r['score']['score'], base_win=b['pick']['win'], new_win=r['pick']['win'], fam=r['pick'].get('fam')))
out = dict(base=base, dclash=sm, changed=changed)
json.dump(out, open('/workspace/mixes/protrans/rca_beats/cohort_dclash3.json', 'w'), indent=1, default=str)
print('RESULT', json.dumps(dict(base=(base['test_mean'], base['train_mean'], base['n_fail']), dclash=(sm['test_mean'], sm['train_mean'], sm['n_fail']), changed=changed), default=str))
gray = [r['id'] for r in rows if ((r.get('drumclash') or {}).get('gray'))]
hard = [dict(id=r['id'], hard=(r.get('drumclash') or {}).get('hard'), retries=(r.get('drumclash') or {}).get('retries')) for r in rows if ((r.get('drumclash') or {}).get('hard') or {}).get('flagged')]
out.update(gray=gray, render_clash=hard); json.dump(out, open('/workspace/mixes/protrans/rca_beats/cohort_dclash3.json', 'w'), indent=1, default=str)
print('GRAY', gray); print('RENDER_CLASH', json.dumps(hard, default=str))
