"""Complete nightly hill-climb n1127 on pinned src2_pin_n1121 (HARD_FALLBACK=0).

Runs baseline + the 6 arms in replica/nightly_candidates.json -> candidates_n1127:
  epg_strict, epg_drop, epg_stack, ridegate_lock_pump_ee, profade_ex35 (baseline is the promoted ridegate default)
Scores official v1 and v2 with CIs, official hard checks, plus drum_linger_bars and
exit lag vs the pro on every arm. Writes results/hill_climb_n1127.json and
results/n1127_v1_v2_summary.json. Does not write rules.json or adopt defaults.
"""
from __future__ import annotations
import copy, fcntl, glob, json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import st_pin

os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
os.environ['HARD_FALLBACK'] = '0'
os.environ.pop('HARDCHECK_TEST_FORCE_WIN', None)
os.environ.pop('PICKER_STYLE_GATED', None)
os.environ.pop('PICKER_STYLE_GATED_MAP', None)
for _k in ('RIDEGATE','RIDEGATE_LOCK','RIDEGATE_PUMP','RIDEGATE_EE','RIDEGATE_PACK','LINGER_GUARD','PRO_FADE','EARLY_EXIT'):
    os.environ.pop(_k, None)

import paths, tune, score, score_v2 as S2
import run_admitted_tune as T
import promotion_judge as PJ
import dclash_report as DC
import sys as _sys
_sys.path.insert(0, os.path.join(HERE, "replica"))
import nightly_card as NCard

MAX_CANDS = 6
TAG = 'n1127'
CANDS_FILE = os.path.join(HERE, 'replica', 'nightly_candidates.json')
BENCH = '/tmp/protrans_bench'

SHORT_TAG = {
    'base': 'n27b',
    'epg_strict': 'n27es',
    'epg_drop': 'n27ed',
    'epg_stack': 'n27ek',
    'ridegate_lock_pump': 'n27rlp',
    'ridegate_lock_pump_ee': 'n27rle',
    'profade_ex35': 'n27pf',
}


def pick_workers():
    st = os.path.join(paths.MIXES, 'jobs', 'picker-followup-pinned-1125.status')
    try:
        if os.path.exists(st) and open(st).read().startswith('running'):
            return 2
    except Exception:
        pass
    return 3


def v2_ckpt_path(variant):
    os.makedirs(T.CKPT, exist_ok=True)
    return os.path.join(T.CKPT, f'{variant}_v2.jsonl')


def load_v2_ckpt(variant):
    p = v2_ckpt_path(variant)
    by = {}
    if not os.path.exists(p):
        return by
    for line in open(p):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get('id') and row.get('official_v2_version') == S2.VERSION:
            by[row['id']] = row
    return by


def append_v2_ckpt(variant, row):
    p = v2_ckpt_path(variant)
    raw = json.dumps(row, default=str) + '\n'
    with open(p, 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())


def _v2_hc_worker(payload):
    rec, v1_row, variant = payload
    import os, sys, glob, json
    os.environ['PROTRANS_SRC2'] = st_pin.ensure_shadow()
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.join(HERE, 'replica'))
    import paths, score_v2 as S2, hardcheck as HC
    os.chdir(paths.SRC2)
    if paths.SRC2 not in sys.path:
        sys.path.insert(0, paths.SRC2)
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
    sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    ours = v1_row.get('ours')
    v1_sc = v1_row.get('score')
    if v1_row.get('error') or not ours or not os.path.exists(ours):
        out = dict(id=rec['id'], split=rec['split'], dj=rec['dj'],
                   official_v2_version=S2.VERSION,
                   error=v1_row.get('error') or 'missing render for v2')
        append_v2_ckpt(variant, out)
        return out
    try:
        r2 = S2.score_v2(rec['pro_clip'], ours, sa, sb, v1=v1_sc, use_demucs=False, cache=paths.CACHE)
        metas = [x for x in sorted(glob.glob(os.path.splitext(ours)[0] + '_*_meta.json'))
                 if not x.endswith('_dry_meta.json')]
        hc = HC.check(metas[0]) if metas else dict(error='no meta')
        out = dict(
            id=rec['id'],
            split=rec['split'],
            dj=rec['dj'],
            fam=(v1_row.get('pick') or {}).get('fam'),
            win=(v1_row.get('pick') or {}).get('win'),
            v1=v1_sc['score'] if isinstance(v1_sc, dict) else v1_sc,
            official_v2=r2['official_v2'],
            official_v2_version=r2['official_v2_version'],
            placement_parts=(r2.get('placement') or {}).get('parts'),
            hardcheck=hc,
        )
        append_v2_ckpt(variant, out)
        return out
    except Exception as e:
        out = dict(id=rec['id'], split=rec['split'], dj=rec['dj'],
                   official_v2_version=S2.VERSION,
                   error=f'{type(e).__name__}: {e}'[-400:])
        append_v2_ckpt(variant, out)
        return out


def score_v2_and_hc(recs, v1_rows, variant, workers=2):
    by_id = {r['id']: r for r in v1_rows}
    have = load_v2_ckpt(variant)
    todo = [(rec, by_id[rec['id']], variant) for rec in recs if rec['id'] not in have]
    print(f'  {variant} v2+hc: {len(have)} cached, {len(todo)} todo (workers={workers})', flush=True)
    if todo:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_v2_hc_worker, p) for p in todo]
            for fut in as_completed(futs):
                got = fut.result()
                if got.get('error'):
                    print(f"    V2 FAIL {got['id']} {got['error']}", flush=True)
                else:
                    hc = got.get('hardcheck') or {}
                    hf = 'HF' if hc.get('hard_fail') else 'ok'
                    print(f"    v2 {got['split']:5} {got['id']:36} v1={got['v1']:5.2f} v2={got['official_v2']:5.2f} {hf}", flush=True)
    have = load_v2_ckpt(variant)
    return [have[r['id']] for r in recs if r['id'] in have]


def clean_tag_files(short_tag):
    if not short_tag or not os.path.isdir(BENCH):
        return
    n = 0
    for p in glob.glob(os.path.join(BENCH, f'{short_tag}*')):
        try:
            os.remove(p)
            n += 1
        except OSError:
            pass
    print(f'  cleaned {n} temp bench files for prefix {short_tag}', flush=True)


def summarize_v2(v2_rows):
    ok = [r for r in v2_rows if r.get('official_v2') is not None and not r.get('error')]
    tr = [r for r in ok if r.get('split') == 'train']
    te = [r for r in ok if r.get('split') == 'test']
    mean = lambda xs: None if not xs else round(float(np.mean(xs)), 2)
    by_dj = {}
    for r in ok:
        by_dj.setdefault(r['dj'], []).append(r)
    hcs = [r.get('hardcheck') or {} for r in v2_rows if not r.get('error')]
    fails = [
        dict(
            id=r['id'], split=r.get('split'), fam=r.get('fam'), win=r.get('win'),
            v1=r.get('v1'), v2=r.get('official_v2'),
            beat_clash=(r.get('hardcheck') or {}).get('beat_clash'),
            residual_lag_ms=(r.get('hardcheck') or {}).get('residual_lag_ms'),
            halfbeat_fail=(r.get('hardcheck') or {}).get('halfbeat_fail'),
            bass_hole=(r.get('hardcheck') or {}).get('bass_hole'),
            lows_dip_db=(r.get('hardcheck') or {}).get('lows_dip_db'),
            pumping=(r.get('hardcheck') or {}).get('pumping'),
            pump_db=(r.get('hardcheck') or {}).get('pump_db'),
        )
        for r in v2_rows if (r.get('hardcheck') or {}).get('hard_fail')
    ]
    hc_summary = dict(
        n=len(hcs),
        hard_fail=sum(bool(h.get('hard_fail')) for h in hcs),
        beat_clash=sum(bool(h.get('beat_clash')) for h in hcs),
        bass_hole=sum(bool(h.get('bass_hole')) for h in hcs),
        pumping=sum(bool(h.get('pumping')) for h in hcs),
        hc_errors=sum(bool(h.get('error')) for h in hcs),
        fails=fails,
    )
    v2_summary = dict(
        version=S2.VERSION,
        n=len(ok),
        n_fail=sum(1 for r in v2_rows if r.get('error')),
        train_n=len(tr),
        test_n=len(te),
        train_mean=mean([r['official_v2'] for r in tr]),
        test_mean=mean([r['official_v2'] for r in te]),
        all_mean=mean([r['official_v2'] for r in ok]),
        by_dj={dj: dict(n=len(vs), mean=mean([r['official_v2'] for r in vs]), split=vs[0].get('split'))
               for dj, vs in sorted(by_dj.items())},
    )
    return v2_summary, hc_summary


def paired_v2_ci(base_v2, arm_v2, split):
    B = [dict(id=r['id'], split=r['split'], score=r['official_v2']) for r in base_v2 if r.get('official_v2') is not None]
    A = [dict(id=r['id'], split=r['split'], score=r['official_v2']) for r in arm_v2 if r.get('official_v2') is not None]
    return PJ.paired_delta_ci(B, A, split)


def main():
    spec = json.load(open(CANDS_FILE))
    NCard.validate(spec, TAG)
    card = NCard.card_for(TAG, spec)
    cands = [(c['name'], c['delta']) for c in card][:MAX_CANDS]
    byname = {c['name']: c for c in card}
    adopt = bool(spec.get('adopt_to_defaults'))
    assert not adopt, 'adopt_to_defaults must be false'
    assert [n for n, _ in cands] == [c['name'] for c in card], 'n1127 card failed to load'

    recs = T.load_recs()
    base_rules = json.load(open(paths.RULES))
    print(f'nightly {TAG}: {len(recs)} admitted; PROTRANS_SRC2={paths.SRC2}; HARD_FALLBACK={os.environ.get("HARD_FALLBACK")}', flush=True)
    assert paths.SRC2 == '/workspace/mixes/src2_pin_n1121', f'wrong SRC2: {paths.SRC2}'

    # 1. Baseline
    w = pick_workers()
    base_rows = T.run_set_checkpointed(recs, base_rules, f'{TAG}_base', SHORT_TAG['base'], workers=w)
    base = T.summarize(base_rows)
    print(f'BASELINE v1 train={base["train_mean"]} test={base["test_mean"]} n_fail={base["n_fail"]}', flush=True)
    base_v2_rows = score_v2_and_hc(recs, base_rows, f'{TAG}_base', workers=w)
    base_v2, base_hc = summarize_v2(base_v2_rows)
    base_ll = NCard.summarize_linger_and_lag(base_rows)
    print(f'BASELINE v2 train={base_v2["train_mean"]} test={base_v2["test_mean"]} hc_fail={base_hc["hard_fail"]} '
          f'exit_lag={base_ll["exit_lag_vs_pro"]} drum_linger={base_ll["drum_linger_bars"]}', flush=True)
    clean_tag_files(SHORT_TAG['base'])

    # 2. All 6 candidate arms
    tried = []
    night_wins = []
    kept = None
    arms_detail = {}

    for name, delta in cands:
        w = pick_workers()
        trial = copy.deepcopy(base_rules)
        trial.update(delta)
        arm_rows = T.run_set_checkpointed(recs, trial, f'{TAG}_{name}', SHORT_TAG[name], workers=w)
        sm = T.summarize(arm_rows)
        arm_v2_rows = score_v2_and_hc(recs, arm_rows, f'{TAG}_{name}', workers=w)
        arm_v2, arm_hc = summarize_v2(arm_v2_rows)
        linger_lag = NCard.summarize_linger_and_lag(arm_rows)
        clean_tag_files(SHORT_TAG[name])

        meta = byname.get(name) or {}
        if meta.get('promotion'):
            ok, why = PJ.promotion_night_win(meta, base, sm, base_rows=base_rows, arm_rows=arm_rows)
            label = 'NIGHT-WIN' if ok else 'reject'
        else:
            ok = (sm['test_mean'] is not None and base['test_mean'] is not None
                  and sm['test_mean'] > base['test_mean'] + 1e-9 and sm['n_fail'] <= base['n_fail'])
            why = (f'held-out improved {base["test_mean"]} -> {sm["test_mean"]}' if ok
                   else f'held-out did not improve ({base["test_mean"]} -> {sm["test_mean"]})')
            label = 'KEEP?' if ok else 'reject'

        v1_ci = dict(
            train=PJ.paired_delta_ci(base_rows, arm_rows, 'train'),
            test=PJ.paired_delta_ci(base_rows, arm_rows, 'test'),
        )
        v2_ci = dict(
            train=paired_v2_ci(base_v2_rows, arm_v2_rows, 'train'),
            test=paired_v2_ci(base_v2_rows, arm_v2_rows, 'test'),
        )
        dclash = DC.summarize(arm_rows, base_rows)
        print(f'  {name} {delta}: v1 train={sm["train_mean"]} test={sm["test_mean"]} | '
              f'v2 train={arm_v2["train_mean"]} test={arm_v2["test_mean"]} | '
              f'hc_fail={arm_hc["hard_fail"]} (clash={arm_hc["beat_clash"]} hole={arm_hc["bass_hole"]} pump={arm_hc["pumping"]}) | '
              f'exit_lag={linger_lag["exit_lag_vs_pro"]} drum_linger={linger_lag["drum_linger_bars"]} -> {label}', flush=True)

        row = dict(
            name=f'{TAG}_{name}',
            delta=delta,
            train_mean=sm['train_mean'],
            test_mean=sm['test_mean'],
            by_dj=sm['by_dj'],
            kept=bool(ok and (not meta.get('promotion') or adopt)),
            promotion=bool(meta.get('promotion')),
            night_win=bool(ok and meta.get('promotion')),
            floor_test=base['test_mean'],
            why=why,
            scorer_version=score.SCORER_VERSION,
            nightly=TAG,
            dclash=dclash,
            v1_ci=v1_ci,
            v2=arm_v2,
            v2_ci=v2_ci,
            hardcheck=arm_hc,
            drum_linger_bars=linger_lag['drum_linger_bars'],
            exit_lag_vs_pro=linger_lag['exit_lag_vs_pro'],
            linger_lag=linger_lag,
        )
        tune.log_row(row)
        tried.append(row)
        arms_detail[name] = dict(v1=sm, v1_ci=v1_ci, v2=arm_v2, v2_ci=v2_ci, hardcheck=arm_hc, dclash=dclash, drum_linger_bars=linger_lag["drum_linger_bars"], exit_lag_vs_pro=linger_lag["exit_lag_vs_pro"], linger_lag=linger_lag, label=label, why=why)
        if ok and meta.get('promotion'):
            night_wins.append(dict(name=name, delta=delta, summary=sm, why=why))

    out = dict(
        tag=TAG,
        baseline=base,
        baseline_v2=base_v2,
        baseline_hardcheck=base_hc,
        baseline_drum_linger_bars=base_ll['drum_linger_bars'],
        baseline_exit_lag_vs_pro=base_ll['exit_lag_vs_pro'],
        base_rules=base_rules,
        tried=tried,
        kept=kept,
        night_wins=night_wins,
        promoted=False,
        rules_json_changed=False,
        ts=time.strftime('%Y-%m-%d %H:%M %Z'),
    )
    hc_path = os.path.join(paths.RESULTS, f'hill_climb_{TAG}.json')
    json.dump(out, open(hc_path, 'w'), indent=2, default=str)

    nights_p = os.path.join(paths.RESULTS, 'hill_climb_nights.jsonl')
    existing_tags = set()
    if os.path.exists(nights_p):
        for l in open(nights_p):
            if l.strip():
                try:
                    existing_tags.add(json.loads(l).get('tag'))
                except Exception:
                    pass
    nw = night_wins[0] if night_wins else None
    if TAG not in existing_tags:
        with open(nights_p, 'a') as f:
            f.write(json.dumps(dict(
                tag=TAG, kept=bool(kept), base_test=base['test_mean'],
                new_test=(nw['summary']['test_mean'] if nw else None),
                kept_name=None,
                night_win=bool(night_wins),
                night_win_name=nw['name'] if nw else None,
                night_win_names=[x['name'] for x in night_wins],
                n_tried=len(tried),
            )) + '\n')

    rep_p = os.path.join(paths.RESULTS, f'{TAG}_v1_v2_summary.json')
    json.dump(dict(
        tag=TAG,
        ts=out['ts'],
        src2=paths.SRC2,
        hard_fallback=os.environ.get('HARD_FALLBACK'),
        baseline=dict(v1=base, v2=base_v2, hardcheck=base_hc, drum_linger_bars=base_ll['drum_linger_bars'], exit_lag_vs_pro=base_ll['exit_lag_vs_pro']),
        arms=arms_detail,
        night_wins=[x['name'] for x in night_wins],
        rules_json_changed=False,
        adopted=False,
    ), open(rep_p, 'w'), indent=2, default=str)
    print('RESULT ' + json.dumps(dict(
        tag=TAG,
        base_v1=f"{base['train_mean']}/{base['test_mean']}",
        base_v2=f"{base_v2['train_mean']}/{base_v2['test_mean']}",
        night_wins=[x['name'] for x in night_wins],
        hc_path=hc_path,
        rep_path=rep_p,
    )), flush=True)


if __name__ == '__main__':
    main()
