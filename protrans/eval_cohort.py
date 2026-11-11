"""Full admitted-cohort run of the current engine + rules.json under one variant name; prints train/test for the
current scorer and for the previous one (score_v2, i.e. without the v3 beat-identity term). Usage:
python3 protrans/eval_cohort.py <variant> [rules.json]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, run_admitted_tune as T

def summary_v2(rows):
    ok = [r for r in rows if isinstance(r.get('score'), dict) and 'score_v2' in r['score']]
    m = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    return dict(train_mean=m([r['score']['score_v2'] for r in ok if r['split'] == 'train']),
                test_mean=m([r['score']['score_v2'] for r in ok if r['split'] == 'test']))

if __name__ == '__main__':
    variant = sys.argv[1]
    rules = json.load(open(sys.argv[2] if len(sys.argv) > 2 else paths.RULES))
    recs = T.load_recs()
    rows = T.run_set_checkpointed(recs, rules, variant, variant[:6])
    sm = T.summarize(rows); v2 = summary_v2(rows)
    fams = {}
    for r in rows:
        f = (r.get('pick') or {}).get('fam'); fams[f] = fams.get(f, 0) + 1
    out = dict(variant=variant, v3=dict(train=sm['train_mean'], test=sm['test_mean'], n=sm['n'], n_fail=sm['n_fail']),
               v2=dict(train=v2['train_mean'], test=v2['test_mean']), fams=fams, by_dj=sm['by_dj'])
    json.dump(out, open(os.path.join(paths.RESULTS, f'eval_{variant}.json'), 'w'), indent=2)
    print('RESULT ' + json.dumps(out), flush=True)
