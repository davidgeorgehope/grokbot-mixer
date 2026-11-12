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

MAX_CANDS = 6

def candidates():
    # priority: phase-aware picking, EQ swap >=2 bars, outgoing shape, length, then phase extras
    # n1110 list, re-tested on the STRUCT=1 + 2-bar-swap base (n1109 kept bass_swap_2bar,
    # phase_pref 0.4/0.8 rejected; d1109 kept STRUCT=1)
    return [
        # n1112 list on the new FADE=long + LONG_SOLO 16/exit + BASS_SWAP 3 + HIGH_OFS 8 base.
        # Untested so far: breakdown/linger phase weights, swap position, long-solo length, length_pref 24/16.
        ('break_03', {'breakdown_pen_w': 0.3}),
        ('linger_015', {'linger_pen_w': 0.15}),
        ('swap_pos_035', {'SWAP_POS': 0.35}),
        ('long_solo_12', {'LONG_SOLO': 12}),
        ('length_pref_24', {'length_pref': 24}),
        ('length_pref_16', {'length_pref': 16}),
][:MAX_CANDS]

def main():
    tag = time.strftime('n%m%d')
    recs = T.load_recs()
    base_rules = json.load(open(paths.RULES))
    print(f'nightly {tag}: {len(recs)} admitted; rules={base_rules}', flush=True)
    rows = T.run_set_checkpointed(recs, base_rules, f'{tag}_base', f'{tag}b')
    base = T.summarize(rows)
    print(f'BASELINE train={base["train_mean"]} test={base["test_mean"]} n_fail={base["n_fail"]}', flush=True)
    tried = []; kept = None
    for name, delta in candidates():
        trial = copy.deepcopy(base_rules); trial.update(delta)
        r = T.run_set_checkpointed(recs, trial, f'{tag}_{name}', f'{tag}{name[:6]}')
        sm = T.summarize(r)
        ok = (sm['test_mean'] is not None and base['test_mean'] is not None
              and sm['test_mean'] > base['test_mean'] + 1e-9 and sm['n_fail'] <= base['n_fail'])
        why = (f'held-out improved {base["test_mean"]} -> {sm["test_mean"]}' if ok
               else f'held-out did not improve ({base["test_mean"]} -> {sm["test_mean"]})')
        print(f'  {name} {delta}: train={sm["train_mean"]} test={sm["test_mean"]} fails={sm["n_fail"]} -> {"KEEP?" if ok else "reject"}', flush=True)
        row = dict(name=f'{tag}_{name}', delta=delta, train_mean=sm['train_mean'], test_mean=sm['test_mean'],
                   by_dj=sm['by_dj'], kept=ok, floor_test=base['test_mean'], why=why,
                   scorer_version=score.SCORER_VERSION, nightly=tag)
        tune.log_row(row); tried.append(row)
        if ok:
            kept = dict(name=name, delta=delta, rules=trial, summary=sm); break
    out = dict(tag=tag, baseline=base, base_rules=base_rules, tried=tried, kept=kept,
               ts=time.strftime('%Y-%m-%d %H:%M %Z'))
    json.dump(out, open(os.path.join(paths.RESULTS, f'hill_climb_{tag}.json'), 'w'), indent=2, default=str)
    with open(os.path.join(paths.RESULTS, 'hill_climb_nights.jsonl'), 'a') as f:
        f.write(json.dumps(dict(tag=tag, kept=bool(kept), base_test=base['test_mean'],
                                new_test=kept['summary']['test_mean'] if kept else None,
                                kept_name=kept['name'] if kept else None, n_tried=len(tried))) + '\n')
    print('RESULT ' + json.dumps(dict(kept=kept and kept['name'], base=base['test_mean'],
                                      new=kept and kept['summary']['test_mean'])), flush=True)
    try: cleanup.drop_stems()
    except Exception as e: print('cleanup warn', e)

if __name__ == '__main__':
    main()
