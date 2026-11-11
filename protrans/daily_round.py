"""One daily pro-transition round (blind recreation of one unused TRAIN pick).

Baseline = an existing full-cohort checkpoint scored with the current rules.json.
Tries general-rule variants on the pick only; the best pick improver gets a
full-cohort run and is kept iff the held-out mean does not drop (and no new
fails). Writes results/daily_<date>.json. Clip export + log.jsonl are done
by the caller after reviewing the result.
"""
from __future__ import annotations
import copy, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, score, tune
import run_admitted_tune as T

def main(pick_id, base_variant, cands):
    tag = 'd' + time.strftime('%m%d')
    recs = T.load_recs(); by = {r['id']: r for r in recs}
    pick = by[pick_id]
    rules = json.load(open(paths.RULES))
    base_rows = T.run_set_checkpointed(recs, rules, base_variant, 'bx')
    base = T.summarize(base_rows)
    bpick = next(r for r in base_rows if r['id'] == pick_id)['score']['score']
    print(f'BASE pick={bpick} train={base["train_mean"]} test={base["test_mean"]}', flush=True)
    tried = []
    for name, delta in cands:
        trial = copy.deepcopy(rules); trial.update(delta)
        rows = T.run_set_checkpointed([pick], trial, f'{tag}p_{name}', f'{tag}{name[:6]}', workers=1)
        r = rows[0]
        s = None if r.get('error') else r['score']['score']
        print(f'  pick {name} {delta}: {s} {(r.get("pick") or {}).get("fam")}', flush=True)
        tried.append(dict(name=name, delta=delta, pick_score=s, pick_fam=(r.get('pick') or {}).get('fam'), kept=False))
    best = max((t for t in tried if t['pick_score'] is not None and t['pick_score'] > bpick + 1e-9),
               key=lambda t: t['pick_score'], default=None)
    kept = None
    for t in tried:
        if t is not best:
            t['why'] = 'pick score did not improve (no full-cohort run)' if (t['pick_score'] or 0) <= bpick else 'not the best pick improver (no full-cohort run)'
    if best:
        trial = copy.deepcopy(rules); trial.update(best['delta'])
        rows = T.run_set_checkpointed(recs, trial, f'{tag}_{best["name"]}', f'{tag}f{best["name"][:5]}')
        sm = T.summarize(rows)
        ok = (sm['test_mean'] is not None and sm['test_mean'] + 1e-9 >= base['test_mean']
              and sm['n_fail'] <= base['n_fail'])
        best.update(train_mean=sm['train_mean'], test_mean=sm['test_mean'], by_dj=sm['by_dj'], kept=ok,
                    why=(f'held-out held {base["test_mean"]} -> {sm["test_mean"]}' if ok
                         else f'overfit: held-out dropped {base["test_mean"]} -> {sm["test_mean"]}'))
        tune.log_row(dict(name=f'{tag}_{best["name"]}', delta=best['delta'], cohort_ids=sorted(by),
                          scorer_version=score.SCORER_VERSION, train_mean=sm['train_mean'], test_mean=sm['test_mean'],
                          by_dj=sm['by_dj'], kept=ok, floor_test=base['test_mean'], why=best['why'], daily=tag))
        if ok:
            json.dump(trial, open(paths.RULES, 'w'), indent=2)
            kept = dict(name=best['name'], delta=best['delta'], summary=sm,
                        pick_row=next(r for r in rows if r['id'] == pick_id))
    out = dict(tag=tag, pick_id=pick_id, base_variant=base_variant, base=base, pick_before=bpick,
               base_pick_row=next(r for r in base_rows if r['id'] == pick_id),
               tried=tried, kept=kept, rules_after=json.load(open(paths.RULES)))
    json.dump(out, open(os.path.join(paths.RESULTS, f'daily_{time.strftime("%Y-%m-%d")}.json'), 'w'), indent=2, default=str)
    print('RESULT', json.dumps(dict(before=bpick, kept=kept and kept['name'],
                                    tried=[(t['name'], t['pick_score']) for t in tried])), flush=True)
    # standard per-blend diagnostic figure for the pick under the rules now in place (generate-only, never fails the round)
    try:
        import daily_diag
        d = daily_diag.make(pick_id, f'daily_{time.strftime("%Y-%m-%d")}')
        print('DIAG', d['png'], 'half-beat', 'FAIL' if (d.get('halfbeat') or {}).get('fail') else 'ok', flush=True)
    except Exception as e:
        print('DIAG skipped:', type(e).__name__, str(e)[-200:], flush=True)

if __name__ == '__main__':
    CANDS = [
        ('swap_pos_050', {'SWAP_POS': 0.50}),
        ('swap_1bar', {'BASS_SWAP_BARS': 1}),
        ('length_pref_16', {'length_pref': 16}),
        ('hint_stronger', {'hint_weight': 0.4}),
        ('near_hint_64', {'near_hint_bars': 64}),
        ('high_swap_off', {'HIGH_SWAP': 0}),
        ('loop32_on', {'LOOP32': 1}),
    ]
    main(sys.argv[1], sys.argv[2], CANDS)
