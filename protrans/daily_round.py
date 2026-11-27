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
        pv = d.get('provsours') or {}  # 2026-11-19: pro pick vs ours table + PNG (goes in the daily note)
        print('PROVSOURS', pv.get('md'), pv.get('png'), pv.get('error') or '', flush=True)
        if pv.get('md'): print(open(pv['md']).read(), flush=True)
    except Exception as e:
        print('DIAG skipped:', type(e).__name__, str(e)[-200:], flush=True)

if __name__ == '__main__':
    # 2026-11-27 list (base lcb_1127: current ridegate+LOCK+PUMP default, 34.17/33.91, 33 admitted, 0 fails).
    # Pick joe_syntax_hospital__00 (Fred V & Grafix - Find My Way -> Nu:Tone - The Feeling ft. Ben Westbeech): next unused
    # TRAIN in load_recs order. Ours (default) ridegate_live exit A 96-112 (end of A's only drop) / cue B 32 / 16 bars,
    # score 40.96. Pro: B in at its bar 44.6 (end of B drop 1) over A's last ~7 bars (A 105.1), bass swap 1 bar later,
    # A gone at 113.1 (A's end): 8-bar blend. Same exit end as ours; pro blend is half as long and cues B ~12.6 bars later.
    # r1: shorter blend / faster bass swap / linger guards (the listener 11-26 fault: old drums lingering) + placement families.
    # r1 result: every knob above left the pick at 40.96 (ridegate_live keeps its own window and ignores family knobs)
    # except tail_exit_4 (38.28). r2: render-shape knobs that do reach the ridegate window, and ridegate-off families.
    CANDS = [
        ('tail_exit_8', {'TAIL_EXIT': 8}),
        ('tail_exit_5', {'TAIL_EXIT': 5}),
        ('high_ofs_4', {'HIGH_OFS': 4}),
        ('swap_pos_04', {'SWAP_POS': 0.4}),
        ('rg_off', {'RIDEGATE': 0}),
        ('rg_off_lp8', {'RIDEGATE': 0, 'length_pref': 8}),
        ('rg_off_replica8', {'RIDEGATE': 0, 'REPLICA': 1, 'REPLICA_X': 8}),
        ('rg_off_dropcand', {'RIDEGATE': 0, 'DROPCAND': 'exit'}),
    ]
    main(sys.argv[1], sys.argv[2], CANDS)
