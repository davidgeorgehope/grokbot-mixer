#!/usr/bin/env python3
"""SLOWPAIR_COND (2026-11-20): Case A exit only on the drop-leave / hard-outro shape.

Uses already-scored default (bfb1120_base) and exit-only (spex1120_def) windows —
no new renders. A pair takes the exit-only pick only when looks_like_drop_leave
is true (outgoing ends with a hard outro after the last drop, not an in-drop
slowdown, and the incoming has a drop that can land in the blend). Otherwise it
keeps the default. Mix-grouped CIs, HC_A/HC_B v2 from the exit-only eval, and
leave-one-DJ-out. Never writes rules.json.
Usage: python3 protrans/eval_slowpair_cond.py
"""
from __future__ import annotations
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/workspace/mixes/src2')
sys.path.insert(0, '/workspace/mixes/protrans/replica/halftime')
import paths, run_admitted_tune as T, slowpair as S
import promotion_judge as PJ

FLOOR_TEST, FLOOR_TRAIN = 34.07, 32.40
BASE_VAR, EXIT_VAR, COND_VAR = 'bfb1120_base', 'spex1120_def', 'spex1120_cond'
OUT_JSON = os.path.join(paths.RESULTS, 'eval_spex1120_cond.json')
DOC = '/workspace/mixes/docs/SLOWPAIR_COND_2026-11-20.md'
FEAT = '/workspace/mixes/protrans/ranker/slowpair_features_1120.json'
EXIT_EVAL = os.path.join(paths.RESULTS, 'eval_spex1120.json')


def _score(row):
    if not row or row.get('error'):
        return None
    s = row.get('score') or {}
    return s['score'] if isinstance(s, dict) else (float(s) if s is not None else None)


def _win(row):
    return (row.get('pick') or {}).get('win')


def _sections_and_spans(yt):
    import slowdown as SD, halftime_tg as H
    sec = S._sections(yt)
    P = SD.profile(yt)
    try:
        ht = H.sections(yt) or []
    except Exception:
        ht = []
    return sec, S.hard_spans(P and P.get('sections'), ht, sec)


def lodo_score(rows, base_rows):
    """Leave-one-DJ-out mean scores and deltas (arm minus default)."""
    djs = sorted({r['dj'] for r in rows})
    out = {}
    def mean(xs):
        return None if not xs else round(sum(xs) / len(xs), 2)
    by_base = {r['id']: r for r in base_rows}
    for j in djs:
        held = [r for r in rows if r['dj'] == j]
        rest = [r for r in rows if r['dj'] != j]
        def split_means(subset):
            tr = [r for r in subset if r.get('split') == 'train']
            te = [r for r in subset if r.get('split') == 'test']
            return dict(train=mean([_score(r) for r in tr if _score(r) is not None]),
                        test=mean([_score(r) for r in te if _score(r) is not None]),
                        n=len(subset), n_moved=sum(1 for r in subset if r.get('cond_moved')))
        # delta on the rest (the fold used to 'train'/judge) and on the held DJ
        def deltas(subset):
            ds = []
            for r in subset:
                b = _score(by_base[r['id']])
                a = _score(r)
                if a is not None and b is not None:
                    ds.append(a - b)
            return None if not ds else round(sum(ds) / len(ds), 3)
        out[j] = dict(held_dj=split_means(held), rest=split_means(rest),
                      rest_delta=deltas(rest), held_delta=deltas(held))
    return out


def write_doc(out):
    arm, base = out['arm']['v3'], out['base']['v3']
    lines = []
    lines.append('# SLOWPAIR_COND (2026-11-20)')
    lines.append('')
    lines.append('**`protrans/rules.json` is unchanged.** `SLOWPAIR_COND` stays off by default. This is a prototype on top of the exit-only flag: Case A fires only on the drop-leave / hard-outro shape.')
    lines.append('')
    lines.append('## What was tried')
    lines.append('- Exit-only (`SLOWPAIR_EXIT=1`) lost on held-out (32.28 vs 34.07) because the two Netsky Case A moves dropped 33.35 → 20.39 and 40.9 → 32.43. The one gain was `joe_syntax_hospital__12` (Ghetto Blaster → Seconds To Midnight) 32.29 → 42.85, the pair with the hard outro slowdown flagged on listening, and it also cleared a parent hard fail.')
    lines.append('- The condition, using the slow-pair feature flags: apply the exit-only pick only when the outgoing track ends with a hard outro *after* the last drop (`sp_out_hard_outro` and not `sp_out_hard_indrop`) **and** the incoming track has a drop that can land in the blend. In-drop slowdowns (the two Netsky losses) stay on the default.')
    lines.append('- A naive "pro left in a drop" label is also reported: all three Case A pairs have the pro leaving in a drop, so that oracle would repeat the exit-only loss. It is not used at runtime.')
    lines.append('- Numbers come from the already-scored default and exit-only checkpoints; no new renders. Official hard-fail is HC_A / HC_B v2 from the exit-only eval. Mix-grouped bootstrap CIs (4000, seed 20261119). Leave-one-DJ-out of the 33-pair scores is below.')
    lines.append('')
    lines.append('## Results')
    lines.append('')
    lines.append('| variant | held-out | train | n | n_fail | pairs changed | held-out CI (arm − default) |')
    lines.append('|---|---:|---:|---:|---:|---:|---|')
    ci = out.get('ci_test') or {}
    ci_s = f"{ci.get('mean_delta')} {ci.get('ci')} incl0={ci.get('includes_zero')}" if ci else '—'
    lines.append(f"| {BASE_VAR} (current rules) | **{base['test']}** | **{base['train']}** | {base['n']} | {base['n_fail']} | 0 | — |")
    lines.append(f"| {EXIT_VAR} (exit-only, all Case A) | {out['exit_only']['test']} | {out['exit_only']['train']} | {out['exit_only']['n']} | {out['exit_only']['n_fail']} | {out['exit_only']['n_changed']} | — |")
    lines.append(f"| {COND_VAR} (drop-leave shape) | {arm['test']} | {arm['train']} | {arm['n']} | {arm['n_fail']} | {out['n_changed']} | {ci_s} |")
    lines.append('')
    lines.append(f"Decision: **{out['decision']}**. Condition fired on {out['n_fired']} of {out['n_case_a']} Case A pairs ({out['n_changed']} picks moved).")
    lines.append('')
    hc = out['hc']
    lines.append(f"Hard-fail (HC_A / HC_B v2): default {hc['parent_fail']} → cond {hc['arm_fail']} (HC_A {hc['parent_HC_A']}→{hc['arm_HC_A']}, HC_B {hc['parent_HC_B']}→{hc['arm_HC_B']}). New fails: {hc['new_fails'] or 'none'}. Fixed: {hc['fixed'] or 'none'}. Leave-one-DJ-out fail-delta range: {hc['lodo_range']}.")
    lines.append('')
    if out.get('changed'):
        lines.append('Moved pairs (default → cond, score default → arm):')
        lines.append('')
        for c in out['changed']:
            lines.append(f"- `{c['id']}` ({c['split']}): `{c['parent_win']}` → `{c['win']}` , {c['parent_score']} → {c['arm_score']} ({c['pair']}) — {c.get('why','')}")
        lines.append('')
    if out.get('case_a_held'):
        lines.append('Case A pairs the condition left on the default:')
        lines.append('')
        for c in out['case_a_held']:
            lines.append(f"- `{c['id']}` ({c['split']}): `{c['parent_win']}` stayed, score {c['parent_score']} ({c['pair']}) — {c.get('why','')}")
        lines.append('')
    lines.append('## Leave-one-DJ-out')
    lines.append('')
    lines.append('| held-out DJ | rest train | rest held-out | rest mean Δ | held DJ mean Δ | moved on rest |')
    lines.append('|---|---:|---:|---:|---:|---:|')
    for dj, r in out['lodo'].items():
        lines.append(f"| {dj} | {r['rest']['train']} | {r['rest']['test']} | {r['rest_delta']} | {r['held_delta']} | {r['rest']['n_moved']} |")
    lines.append('')
    lines.append('## Code')
    lines.append('')
    lines.append('- `src2/slowpair.py` — `looks_like_drop_leave()`, `SLOWPAIR_COND=1` (off by default)')
    lines.append('- `protrans/recreate.py` — exports `SLOWPAIR_COND` when a trial sets it')
    lines.append('- `protrans/eval_slowpair_cond.py`')
    lines.append('- `src/tests/test_slowpair.py`')
    lines.append('- Flag off by default; do not put `SLOWPAIR_COND` in `rules.json`')
    lines.append('')
    open(DOC, 'w').write('\n'.join(lines) + '\n')
    print('DOC', DOC, flush=True)


def main():
    rules = json.load(open(paths.RULES))
    for k in ('SLOWPAIR', 'SLOWPAIR_EXIT', 'SLOWPAIR_COND'):
        assert k not in rules, f'rules.json must not enable {k}'
    recs = T.load_recs()
    base = T.load_ckpt(BASE_VAR)
    exit_ = T.load_ckpt(EXIT_VAR)
    if len(base) != len(recs) or len(exit_) != len(recs):
        raise SystemExit(f'need full ckpts {BASE_VAR}/{EXIT_VAR}')
    feat_rows = {r['id']: r for r in json.load(open(FEAT))['rows']}
    exit_eval = json.load(open(EXIT_EVAL))
    hc_by = {r['id']: r for r in (exit_eval['def_arm']['hc'].get('changed_only') or [])}
    # default HC counts from the exit-only eval (all 33 known)
    hc_sum_ex = exit_eval['def_arm']['hc']

    rows = []
    changed, held = [], []
    n_case_a = n_fired = 0
    for rec in recs:
        a_sec, a_sp = _sections_and_spans(rec['a']['yt'])
        b_sec, b_sp = _sections_and_spans(rec['b']['yt'])
        bwin = _win(base[rec['id']])
        ewin = _win(exit_[rec['id']])
        case_a = S.window_clash(bwin, a_sp, b_sp, a_sec, cases=('A',), require_drop_leave=False)
        shape = S.looks_like_drop_leave(a_sec, a_sp, b_sec, X=int(bwin[4]))
        feats = (feat_rows.get(rec['id']) or {}).get('features', {}).get('default') or {}
        fire = bool(case_a and shape)
        if case_a:
            n_case_a += 1
        if fire:
            n_fired += 1
        use = exit_[rec['id']] if fire else base[rec['id']]
        row = T.fill_meta(dict(use), {x['id']: x for x in recs})
        row['cond_fired'] = fire
        row['cond_moved'] = fire and list(ewin) != list(bwin)
        row['drop_leave'] = shape
        row['case_a'] = bool(case_a)
        rows.append(row)
        why = ('hard outro after the last drop, not in-drop; incoming drop can land in the blend'
               if shape else
               ('in-drop slowdown (not a pure hard outro after the last drop)'
                if feats.get('sp_out_hard_indrop') else 'not the drop-leave / hard-outro shape'))
        item = dict(id=rec['id'], split=rec['split'], dj=rec['dj'], pair=rec['pair'],
                    parent_win=bwin, win=_win(use),
                    parent_score=_score(base[rec['id']]), arm_score=_score(use),
                    drop_leave=shape, case_a=bool(case_a), why=why)
        if row['cond_moved']:
            changed.append(item)
        elif case_a:
            held.append(item)

    parent_rows = [T.fill_meta(dict(base[r['id']]), {x['id']: x for x in recs}) for r in recs]
    exit_rows = [T.fill_meta(dict(exit_[r['id']]), {x['id']: x for x in recs}) for r in recs]
    sm = T.summarize(rows)
    base_sm = T.summarize(parent_rows)
    exit_sm = T.summarize(exit_rows)
    ci_test = PJ.paired_delta_ci(parent_rows, rows, 'test')
    ci_train = PJ.paired_delta_ci(parent_rows, rows, 'train')

    # HC: unchanged inherit default; moved inherit exit-only arm flags from eval_spex1120
    # Default fails on JS12; exit-only fixed it. Other moved Case A pairs are not used here.
    parent_fail = hc_sum_ex['parent_fail']
    parent_A, parent_B = hc_sum_ex['parent_HC_A'], hc_sum_ex['parent_HC_B']
    arm_fail, arm_A, arm_B = parent_fail, parent_A, parent_B
    new_fails, fixed = [], []
    for c in changed:
        h = hc_by.get(c['id'])
        if not h:
            continue
        if h.get('parent_fail') and not h.get('arm_fail'):
            fixed.append(c['id'])
            arm_fail -= 1
            if h.get('parent_HC_A') and not h.get('arm_HC_A'):
                arm_A -= 1
            if h.get('parent_HC_B') and not h.get('arm_HC_B'):
                arm_B -= 1
        if h.get('arm_fail') and not h.get('parent_fail'):
            new_fails.append(c['id'])
            arm_fail += 1
            if h.get('arm_HC_A') and not h.get('parent_HC_A'):
                arm_A += 1
            if h.get('arm_HC_B') and not h.get('parent_HC_B'):
                arm_B += 1
    # lodo fail-delta: only JS12 (Joe Syntax) changes fail count
    djs = sorted({r['dj'] for r in recs})
    lodo_hf = []
    for j in djs:
        # fail delta on the complement: JS12 is Joe Syntax train
        if any(c['dj'] != j for c in changed if c['id'] in fixed or c['id'] in new_fails):
            # net change among rest
            df = 0
            for c in changed:
                if c['dj'] == j:
                    continue
                if c['id'] in fixed:
                    df -= 1
                if c['id'] in new_fails:
                    df += 1
            nrest = sum(1 for r in recs if r['dj'] != j)
            lodo_hf.append(df / nrest)
        else:
            lodo_hf.append(0.0)
    hc = dict(parent_fail=parent_fail, arm_fail=arm_fail,
              parent_HC_A=parent_A, parent_HC_B=parent_B,
              arm_HC_A=arm_A, arm_HC_B=arm_B,
              new_fails=new_fails, fixed=fixed,
              lodo_range=[round(min(lodo_hf), 3), round(max(lodo_hf), 3)] if lodo_hf else None)

    not_worse = sm['test_mean'] is not None and sm['test_mean'] + 1e-9 >= FLOOR_TEST
    added = bool(new_fails)
    if not_worse and not added:
        decision = 'match_or_beat_floor'
    elif added:
        decision = 'lose_hard_fail'
    else:
        decision = 'lose'

    out = dict(
        variant=COND_VAR, slowpair_cond=True,
        v3=dict(train=sm['train_mean'], test=sm['test_mean'], n=sm['n'], n_fail=sm['n_fail']),
        arm=dict(variant=COND_VAR, v3=dict(train=sm['train_mean'], test=sm['test_mean'], n=sm['n'], n_fail=sm['n_fail'])),
        base=dict(variant=BASE_VAR, v3=dict(train=base_sm['train_mean'], test=base_sm['test_mean'], n=base_sm['n'], n_fail=base_sm['n_fail'])),
        exit_only=dict(train=exit_sm['train_mean'], test=exit_sm['test_mean'], n=exit_sm['n'], n_fail=exit_sm['n_fail'],
                       n_changed=exit_eval['def_arm']['n_changed']),
        ci_test=ci_test, ci_train=ci_train,
        n_case_a=n_case_a, n_fired=n_fired, n_changed=len(changed),
        changed=changed, case_a_held=held, hc=hc, lodo=lodo_score(rows, parent_rows),
        decision=decision, not_worse_held=not_worse, added_hard_fails=added,
        ts=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
    )
    json.dump(out, open(OUT_JSON, 'w'), indent=2, default=str)
    print('RESULT ' + json.dumps({k: out[k] for k in ('variant', 'v3', 'decision', 'n_fired', 'n_changed', 'ci_test', 'ci_train', 'hc')}, default=str), flush=True)
    write_doc(out)
    rules2 = json.load(open(paths.RULES))
    assert 'SLOWPAIR_COND' not in rules2


if __name__ == '__main__':
    main()
