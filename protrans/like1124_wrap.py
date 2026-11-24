"""Like-for-like re-score of baseline + epg_strict, epg_drop, epg_stack, thin_dropcue
with HARD_FALLBACK off. Does not write rules.json. Does not drop_stems (shared scratch).
Does not adopt. Unique checkpoints (like1124_*), not the contaminated n1124_* rows.
"""
from __future__ import annotations
import copy, json, os, sys
os.environ['HARD_FALLBACK'] = '0'
os.environ.pop('HARDCHECK_TEST_FORCE_WIN', None)
os.environ.pop('PICKER_STYLE_GATED', None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import st_pin
os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
import cleanup, paths, score
import run_admitted_tune as T
import promotion_judge as PJ
import dclash_report as DC

cleanup.drop_stems = lambda: print('drop_stems skipped (like1124 wrap; shared scratch)', flush=True)

WORKERS = 2
VARIANT_PREFIX = 'like1124'
ARMS = [
    ('epg_strict', {'EXITPOS': 1, 'EXITPOS_GATE': 1}),
    ('epg_drop', {'EXITPOS': 1, 'EXITPOS_DROP': 1}),
    ('epg_stack', {'EXITPOS': 1, 'EXITPOS_GATE': 1, 'EXITPOS_DROP': 1}),
    ('thin_dropcue', {'THIN_DROPCUE': 1}),
]
TAG = {
    'base': 'l24b',
    'epg_strict': 'l24s',
    'epg_drop': 'l24d',
    'epg_stack': 'l24k',
    'thin_dropcue': 'l24t',
}

def default_wins():
    rows = [json.loads(l) for l in open(os.path.join(os.path.dirname(__file__), 'replica', 'gate_ckpt', 'default.jsonl')) if l.strip()]
    return {r['id']: r for r in rows if r.get('split') in ('train', 'test')}

def official_hard(row):
    h = (row.get('pick') or {}).get('hard') or row.get('hard') or {}
    if not isinstance(h, dict):
        return {}
    return {k: h.get(k) for k in ('hard_fail', 'pumping', 'pump_db', 'beat_clash', 'bass_hole')}

def main():
    recs = T.load_recs()
    base_rules = json.load(open(paths.RULES))
    # never write HARD_FALLBACK into rules; the code default is off
    print(f'like1124: {len(recs)} admitted; HARD_FALLBACK=0; scorer={score.SCORER_VERSION}', flush=True)
    print(f'  rules.json untouched; adopt_to_defaults is not used', flush=True)
    rows = T.run_set_checkpointed(recs, base_rules, f'{VARIANT_PREFIX}_base', TAG['base'], workers=WORKERS)
    base = T.summarize(rows)
    print(f'BASELINE train={base["train_mean"]} test={base["test_mean"]} n_fail={base["n_fail"]}', flush=True)

    ref = default_wins()
    changed, missing, hard_fail = [], [], 0
    for r in rows:
        o = ref.get(r['id'])
        win = (r.get('pick') or {}).get('win')
        fam = (r.get('pick') or {}).get('fam')
        fb = (r.get('pick') or {}).get('hard_fallback') or {}
        if fb.get('enabled') or fb.get('replaced_by'):
            changed.append(dict(id=r['id'], why='hard_fallback_fired', fb=fb, win=win, fam=fam))
            continue
        if not o:
            missing.append(r['id']); continue
        if list(win or []) != list(o.get('win') or []):
            changed.append(dict(id=r['id'], split=r.get('split'), ref_win=o.get('win'), ref_fam=o.get('fam'),
                                win=win, fam=fam, hard=official_hard(r)))
        h = official_hard(r)
        if h.get('hard_fail'):
            hard_fail += 1
    identical = not changed and not missing
    print(f'WINDOW_CHECK vs pre-1123 default.jsonl: identical={identical} changed={len(changed)} missing={len(missing)} official_hard_fail={hard_fail}', flush=True)
    for c in changed:
        print('  DIFF', json.dumps(c, default=str), flush=True)

    spec = json.load(open(os.path.join(os.path.dirname(__file__), 'replica', 'nightly_candidates.json')))
    byname = {c['name']: c for c in spec.get('candidates') or []}
    tried = []
    for name, delta in ARMS:
        trial = copy.deepcopy(base_rules); trial.update(delta)
        r = T.run_set_checkpointed(recs, trial, f'{VARIANT_PREFIX}_{name}', TAG[name], workers=WORKERS)
        sm = T.summarize(r)
        meta = byname.get(name) or {}
        if meta.get('promotion'):
            ok, why = PJ.promotion_night_win(meta, base, sm, base_rows=rows, arm_rows=r)
            label = 'NIGHT-WIN' if ok else 'reject'
        else:
            ok = (sm['test_mean'] is not None and base['test_mean'] is not None
                  and sm['test_mean'] > base['test_mean'] + 1e-9 and sm['n_fail'] <= base['n_fail'])
            why = (f'held-out improved {base["test_mean"]} -> {sm["test_mean"]}' if ok
                   else f'held-out did not improve ({base["test_mean"]} -> {sm["test_mean"]})')
            label = 'KEEP?' if ok else 'reject'
        print(f'  {name} {delta}: train={sm["train_mean"]} test={sm["test_mean"]} fails={sm["n_fail"]} -> {label}', flush=True)
        print(f'    vs true floor train 32.40 / test 34.07; vs this baseline train {base["train_mean"]} / test {base["test_mean"]}', flush=True)
        dclash = DC.summarize(r, rows)
        print(DC.format_line(name, dclash), flush=True)
        print(f'DCLASH_COUNTS arm={name} pairs={dclash["n"]} vetoed={dclash["vetoed"]} breakdown_exits={dclash["breakdown_exits"]} '
              f'base_breakdown_exits={dclash.get("base_breakdown_exits")}', flush=True)
        tried.append(dict(name=name, delta=delta, train_mean=sm['train_mean'], test_mean=sm['test_mean'],
                          n_fail=sm['n_fail'], label=label, why=why, promotion=bool(meta.get('promotion')),
                          night_win=bool(ok and meta.get('promotion')), dclash=dclash, by_dj=sm.get('by_dj')))

    floor_ok = (abs(float(base['train_mean']) - 32.40) < 0.05 and abs(float(base['test_mean']) - 34.07) < 0.05)
    out = dict(tag='like1124', HARD_FALLBACK=0, scorer=score.SCORER_VERSION,
               baseline=base, floor_target={'train': 32.40, 'test': 34.07},
               baseline_matches_floor=floor_ok, windows_match_default_jsonl=identical,
               window_diffs=changed, official_hard_fail_baseline=hard_fail,
               arms=tried, rules_json_changed=False, adopted=False)
    dest = os.path.join(os.path.dirname(__file__), 'replica', 'like1124_summary.json')
    json.dump(out, open(dest, 'w'), indent=2, default=str)
    print('RESULT ' + json.dumps(dict(baseline=dict(train=base['train_mean'], test=base['test_mean'], n_fail=base['n_fail']),
                                      floor_ok=floor_ok, windows_ok=identical,
                                      arms={a['name']: dict(train=a['train_mean'], test=a['test_mean'],
                                                            fails=a['n_fail'], label=a['label'],
                                                            night_win=a['night_win']) for a in tried})), flush=True)
    print('wrote', dest, flush=True)

if __name__ == '__main__':
    main()
