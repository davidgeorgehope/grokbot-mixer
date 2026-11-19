"""One bounded nightly hill-climb round over GENERAL engine rules.

Fresh baseline on the admitted corpus, then up to 6 candidates in the
gap_diagnosis priority order. Keep the first candidate whose held-out (test DJ)
mean strictly beats the baseline; stop there. Never touches score.py weights.
Writes results/hill_climb_<date>.json and appends results/hill_climb_nights.jsonl.
"""
from __future__ import annotations
import copy, json, os, sys, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, tune, score, cleanup
import run_admitted_tune as T
import promotion_judge as PJ

MAX_CANDS = 6
CANDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'replica', 'nightly_candidates.json')

def load_candidate_spec():
    """What the nightly reads for candidates. If the file is present, it is the list;
    otherwise fall back to a generic search list. A promotion candidate is not an auto-adopt keep."""
    if os.path.exists(CANDS_FILE):
        return json.load(open(CANDS_FILE))
    return None

def candidates():
    spec = load_candidate_spec()
    if spec and spec.get('candidates'):
        return [(c['name'], c['delta']) for c in spec['candidates']][:MAX_CANDS]
    # fallback generic list (used when no nightly_candidates.json is registered)
    return [
        ('phase_pref_02', {'phase_pref_w': 0.2}),
        ('bass_swap_6bar', {'BASS_SWAP_BARS': 6}),
        ('long_xp_035', {'LONG_XP': 0.35}),
        ('length_pref_32', {'length_pref': 32}),
        ('linger_025', {'linger_pen_w': 0.25}),
        ('break_015', {'breakdown_pen_w': 0.15}),
][:MAX_CANDS]

def main():
    tag = time.strftime('n%m%d')
    recs = T.load_recs()
    base_rules = json.load(open(paths.RULES))
    print(f'nightly {tag}: {len(recs)} admitted; rules={base_rules}', flush=True)
    rows = T.run_set_checkpointed(recs, base_rules, f'{tag}_base', f'{tag}b')
    base = T.summarize(rows)
    print(f'BASELINE train={base["train_mean"]} test={base["test_mean"]} n_fail={base["n_fail"]}', flush=True)
    tried = []; kept = None; night_wins = []
    spec = load_candidate_spec() or {}
    byname = {c['name']: c for c in spec.get('candidates') or []}
    adopt = bool(spec.get('adopt_to_defaults'))
    for name, delta in candidates():
        trial = copy.deepcopy(base_rules); trial.update(delta)
        r = T.run_set_checkpointed(recs, trial, f'{tag}_{name}', f'{tag}{name[:6]}')
        sm = T.summarize(r)
        meta = byname.get(name) or {}
        if meta.get('promotion'):
            # Per-candidate judge from nightly_candidates.json / promotion_criteria_1120.json.
            # epg_drop uses the listening judge (pro-match CI may include 0). Not an auto-adopt keep.
            ok, why = PJ.promotion_night_win(meta, base, sm, base_rows=rows, arm_rows=r)
            label = 'NIGHT-WIN' if ok else 'reject'
        else:
            ok = (sm['test_mean'] is not None and base['test_mean'] is not None
                  and sm['test_mean'] > base['test_mean'] + 1e-9 and sm['n_fail'] <= base['n_fail'])
            why = (f'held-out improved {base["test_mean"]} -> {sm["test_mean"]}' if ok
                   else f'held-out did not improve ({base["test_mean"]} -> {sm["test_mean"]})')
            label = 'KEEP?' if ok else 'reject'
        print(f'  {name} {delta}: train={sm["train_mean"]} test={sm["test_mean"]} fails={sm["n_fail"]} -> {label}', flush=True)
        row = dict(name=f'{tag}_{name}', delta=delta, train_mean=sm['train_mean'], test_mean=sm['test_mean'],
                   by_dj=sm['by_dj'], kept=bool(ok and (not meta.get('promotion') or adopt)),
                   promotion=bool(meta.get('promotion')), night_win=bool(ok and meta.get('promotion')),
                   floor_test=base['test_mean'], why=why,
                   scorer_version=score.SCORER_VERSION, nightly=tag)
        tune.log_row(row); tried.append(row)
        if ok and meta.get('promotion'):
            night_wins.append(dict(name=name, delta=delta, summary=sm, why=why))
        elif ok and not meta.get('promotion') and adopt:
            kept = dict(name=name, delta=delta, rules=trial, summary=sm)
        # A nightly_candidates.json list is the night's full card: run every listed
        # arm, including shadow arms after a promotion night-win. Never write rules.json
        # from this path unless adopt_to_defaults is on (it is not for n1120).
        if not spec.get('candidates'):
            if ok and meta.get('promotion') and not adopt:
                break
            if ok and not meta.get('promotion'):
                kept = dict(name=name, delta=delta, rules=trial, summary=sm); break
    out = dict(tag=tag, baseline=base, base_rules=base_rules, tried=tried, kept=kept,
               night_wins=night_wins, promoted=False, rules_json_changed=False,
               ts=time.strftime('%Y-%m-%d %H:%M %Z'))
    json.dump(out, open(os.path.join(paths.RESULTS, f'hill_climb_{tag}.json'), 'w'), indent=2, default=str)
    nw = night_wins[0] if night_wins else None
    with open(os.path.join(paths.RESULTS, 'hill_climb_nights.jsonl'), 'a') as f:
        f.write(json.dumps(dict(tag=tag, kept=bool(kept), base_test=base['test_mean'],
                                new_test=(kept['summary']['test_mean'] if kept else (nw['summary']['test_mean'] if nw else None)),
                                kept_name=kept['name'] if kept else None,
                                night_win=bool(night_wins),
                                night_win_name=nw['name'] if nw else None,
                                night_win_names=[x['name'] for x in night_wins],
                                n_tried=len(tried))) + chr(10))
    print('RESULT ' + json.dumps(dict(kept=kept and kept['name'], night_win=nw['name'] if nw else None,
                                      base=base['test_mean'],
                                      new=(kept and kept['summary']['test_mean']) or (nw and nw['summary']['test_mean']))), flush=True)
    try: cleanup.drop_stems()
    except Exception as e: print('cleanup warn', e)

if __name__ == '__main__':
    main()
