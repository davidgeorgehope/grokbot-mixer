"""Evaluate principled HALFBEAT_LOCK=1 (off-by-default) on pinned 33 (v1 + v2 + hardcheck).
Evaluates:
  - hbl1125_base : rules.json + HARD_FALLBACK=0 + HALFBEAT_LOCK=1
  - hbl1125_thin : rules.json + HARD_FALLBACK=0 + THIN_DROPCUE=1 + HALFBEAT_LOCK=1
Compares against n1125 baseline and thin_dropcue (both with fixed hardcheck logic).
"""
import copy, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
PROTRANS = os.path.dirname(HERE)
sys.path.insert(0, PROTRANS)
sys.path.insert(0, HERE)
import st_pin
os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
os.environ['HARD_FALLBACK'] = '0'

import paths, tune, recreate, score_v2 as S2
import run_admitted_tune as T
import n1125_run as N25

base_rules = recreate.load_rules()
base_rules['HARD_FALLBACK'] = 0
recs = T.load_recs()

runs = [
    ('hbl1125_base', {**base_rules, 'HALFBEAT_LOCK': 1}, 'hb25b'),
    ('hbl1125_thin', {**base_rules, 'THIN_DROPCUE': 1, 'HALFBEAT_LOCK': 1}, 'hb25t'),
]

out = {'ts': time.strftime('%F %T %Z'), 'src2': os.environ['PROTRANS_SRC2'], 'arms': {}}
for vname, rules, stag in runs:
    print(f'=== {vname} ===', flush=True)
    v1_rows = T.run_set_checkpointed(recs, rules, vname, stag, workers=2)
    res = T.summarize(v1_rows)
    v2_rows = N25.score_v2_and_hc(recs, v1_rows, vname, workers=2)
    v2_sum, hc_sum = N25.summarize_v2(v2_rows)
    out['arms'][vname] = dict(v1=res, v2=v2_sum, hardcheck=hc_sum)
    N25.clean_tag_files(stag)
    print(f'DONE {vname}: v1 train={res["train_mean"]} test={res["test_mean"]} | v2 train={v2_sum["train_mean"]} test={v2_sum["test_mean"]} | hc={hc_sum["hard_fail"]} clash={hc_sum["beat_clash"]} hole={hc_sum["bass_hole"]} pump={hc_sum["pumping"]}', flush=True)

dest = os.path.join(PROTRANS, 'results', 'halfbeat_lock_1125.json')
json.dump(out, open(dest, 'w'), indent=1, default=str)
print('WROTE', dest, flush=True)
