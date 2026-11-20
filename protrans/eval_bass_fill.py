"""BASS_FILL (2026-11-20) like-for-like cohort: current rules.json vs rules + BASS_FILL=1, 2 workers (box is shared).
Usage: python3 protrans/eval_bass_fill.py <variant> [bassfill] [ids,comma]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, run_admitted_tune as T, eval_cohort as EC
variant = sys.argv[1]; on = len(sys.argv) > 2 and sys.argv[2] == 'bassfill'
ids = set(sys.argv[3].split(',')) if len(sys.argv) > 3 else None
rules = json.load(open(paths.RULES))
if on: rules['BASS_FILL'] = 1
recs = [r for r in T.load_recs() if not ids or r['id'] in ids]
rows = T.run_set_checkpointed(recs, rules, variant, variant[:6], workers=int(os.environ.get('BF_WORKERS', 2)))
sm = T.summarize(rows)
out = dict(variant=variant, bass_fill=on, v3=dict(train=sm['train_mean'], test=sm['test_mean'], n=sm['n'], n_fail=sm['n_fail']), by_dj=sm['by_dj'])
json.dump(out, open(os.path.join(paths.RESULTS, f'eval_{variant}.json'), 'w'), indent=2)
print('RESULT ' + json.dumps(out), flush=True)
