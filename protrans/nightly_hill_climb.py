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
        # n1118 list (base: rules.json incl. TAIL_EXIT 6 + BLEND_LOCK 1, held-out ~34.07).
        # Verified against recreate.py/mix_simple.py before running:
        #  - BASS_SWAP_BARS 4 would be a no-op: under FADE=long mix_simple._ctx clamps SW<4 up to 4,
        #    so the current 3 already renders as 4. Tested 6 bars instead (same EQ-swap area).
        #  - length_pref 18 would be a no-op/repeat: windows only come in X=32 or 16, so any value
        #    other than 16/32 penalises every window equally (== length_pref 0 == n1117's
        #    length_pref_20). Tested 32 instead (prefer the long natural window).
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
