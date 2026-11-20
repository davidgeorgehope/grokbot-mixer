#!/usr/bin/env python3
"""SLOWPAIR (2026-11-20) like-for-like cohort: current rules.json vs rules + SLOWPAIR=1.

Seeds pairs whose default window does not clash (so the flag cannot change the pick) from
bfb1120_base. Scores the rest with 1 worker by default (box is shared with n1120).
Writes results/eval_sp1120_pair.json, optionally cuts blind clips, and writes
docs/SLOWPAIR_2026-11-20.md. Never writes rules.json.
Usage: python3 protrans/eval_slowpair.py
"""
from __future__ import annotations
import copy, json, os, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/workspace/mixes/src2')
sys.path.insert(0, '/workspace/mixes/protrans/replica/halftime')
import paths, run_admitted_tune as T, slowpair as S

BASE_VAR = 'bfb1120_base'
VAR = 'sp1120_pair'
DAY = '2026-11-20'
OUT_JSON = os.path.join(paths.RESULTS, f'eval_{VAR}.json')
CLASH_JSON = os.path.join(paths.RESULTS, 'slowpair_clash_1120.json')
DOC = '/workspace/mixes/docs/SLOWPAIR_2026-11-20.md'
FLOOR_TEST, FLOOR_TRAIN = 34.07, 32.40


def _sections_and_spans(yt):
    import slowdown as SD, halftime_tg as H
    sec = S._sections(yt)
    P = SD.profile(yt)
    try:
        ht = H.sections(yt) or []
    except Exception:
        ht = []
    return sec, S.hard_spans(P and P.get('sections'), ht, sec)


def clash_table(recs, base):
    rows = []
    for r in recs:
        win = (base[r['id']].get('pick') or {}).get('win')
        a_sec, a_sp = _sections_and_spans(r['a']['yt'])
        b_sec, b_sp = _sections_and_spans(r['b']['yt'])
        cl = S.window_clash(win, a_sp, b_sp, a_sec)
        rec = dict(id=r['id'], split=r['split'], dj=r['dj'], pair=r['pair'],
                   default_win=list(win), clash=cl, a_hard=a_sp, b_hard=b_sp)
        rows.append(rec)
    json.dump(rows, open(CLASH_JSON, 'w'), indent=2, default=str)
    return rows


def seed_unchanged(recs, base, clash_rows):
    have = T.load_ckpt(VAR)
    seeded = []
    for rec, row in zip(recs, clash_rows):
        if rec['id'] in have:
            continue
        if row['clash']:
            continue
        src = dict(base[rec['id']])
        src['seeded_from'] = BASE_VAR
        src['slowpair'] = dict(changed=False, reason='default_ok', default_win=row['default_win'])
        T.append_ckpt(VAR, src)
        seeded.append(rec['id'])
    return seeded


def write_doc(out):
    base, arm = out['base']['v3'], out['arm']['v3']
    beat = out['decision'] == 'match_or_beat'
    lines = []
    lines.append(f'# SLOWPAIR (2026-11-20 midnight research)')
    lines.append('')
    if beat:
        lines.append(f"**Outcome: matches or beats the default on held-out** (test {arm['test']} vs floor {FLOOR_TEST}; train {arm['train']} vs {FLOOR_TRAIN}). The flag stays off by default; `protrans/rules.json` is unchanged. Blind A/B clips are in `deliver/research/{DAY}/` with the key under `/workspace/private/` only.")
    else:
        lines.append(f"**Outcome: nothing kept. `protrans/rules.json` is unchanged** (no `SLOWPAIR` key). The `SLOWPAIR=1` flag stays off by default.")
        lines.append('')
        lines.append(f"Held-out {arm['test']} vs default {FLOOR_TEST}; train {arm['train']} vs {FLOOR_TRAIN}.")
    lines.append('')
    lines.append('## What was tried')
    lines.append("- the listener's note: bringing a mix in over a hard slowdown sounds weird. The earlier `SLOWDOWN=1` flag only penalises a blend that *starts* inside an outgoing outro / in-drop slowdown, treats every 8-bar snare dip the same, and never looks at the incoming track. It was already scored on 2026-11-19 (held-out flat at 34.07; train 33.19 because Ghetto Blaster moved).")
    lines.append('- Shorter-tail was not retried: `TAIL_EXIT=6` is already the default (docs/TAILEXIT_2026-11-15.md).')
    lines.append('- `SLOWPAIR=1` (off by default, hook in `protrans/recreate.py`, logic in `src2/slowpair.py`) is pair-aware:')
    lines.append('  - Hard spans (pre-declared): half-time sections from `halftime_tg.py`; `slowdown.py` runs of at least 16 bars that are outro, in-drop or breakdown; intro-only runs of at least 24 bars.')
    lines.append('  - Case A: the blend starts inside an outgoing hard outro / in-drop, or at least 12 bars of the window sit in one. Starting a few bars before the slowdown (the Ghetto Blaster fix) is allowed. Breakdowns stay allowed.')
    lines.append('  - Case B: the incoming cue sits on a hard span for at least 8 bars, **and** the outgoing is still in a drop. Outro-over-intro stays the safe default once the outgoing has left its drop.')
    lines.append('- Detector input: `ht-scan-1120` (job done 12:03 AM ET). Alternative windows come from already-scored engine candidates, with the last-drop payoff guard when the exit moves earlier.')
    lines.append('')
    lines.append('## Results')
    lines.append('')
    lines.append('| variant | held-out | train | n | n_fail | pairs changed |')
    lines.append('|---|---:|---:|---:|---:|---:|')
    lines.append(f"| {BASE_VAR} (current rules) | **{base['test']}** | **{base['train']}** | {base['n']} | {base['n_fail']} | 0 |")
    lines.append(f"| {VAR} (`SLOWPAIR=1`) | {arm['test']} | {arm['train']} | {arm['n']} | {arm['n_fail']} | {out['n_changed']} |")
    lines.append('')
    lines.append(f"Default windows that clash with the rule: {out['n_clash']} of 33 (Case A {out['n_clash_A']}, Case B {out['n_clash_B']}); held-out {out['n_clash_test']} of 12. Pairs whose pick actually moved: {out['n_changed']} (held-out {out['n_changed_test']}).")
    lines.append('')
    if out.get('changed'):
        lines.append('Changed pairs (default → SLOWPAIR, score default → arm):')
        lines.append('')
        for c in out['changed']:
            lines.append(f"- `{c['id']}` ({c['split']}, {c.get('case','?')}): `{c['default_win']}` → `{c['win']}` , {c['base_score']} → {c['arm_score']} ({c['pair']})")
        lines.append('')
    if out.get('clashed_unmoved'):
        lines.append('Default clashed but the pick did not move (no legal alternative inside the engine-cost slack / payoff guard):')
        lines.append('')
        for c in out['clashed_unmoved']:
            lines.append(f"- `{c['id']}` ({c['split']}, {c.get('case','?')}): `{c['default_win']}` ({c['pair']})")
        lines.append('')
    if not beat:
        lines.append('## Why it missed, and what is next')
        lines.append('')
        why = out.get('why') or 'The moved windows did not beat the default on the held-out similarity score.'
        lines.append(why)
        lines.append('')
        lines.append('Next: keep the hard-span features (outgoing outro/in-drop cover, incoming hard intro under a still-hot outgoing drop, half-time flags) as inputs to the model picker, instead of a hand cost that always avoids them. Case A alone is the closer reading of the listener\'s note and only fires on a few pairs; a Case-A-only arm is the obvious follow-up if the combined flag lost because of Case B cue moves.')
        lines.append('')
    lines.append('## Code')
    lines.append('')
    lines.append('- `src2/slowpair.py` — hard spans, clash, alternative, rerank')
    lines.append('- `protrans/recreate.py` — `SLOWPAIR=1` hook (off by default)')
    lines.append('- `protrans/eval_slowpair.py`, `protrans/eval_slowpair.sh`')
    lines.append('- `src/tests/test_slowpair.py`')
    lines.append('- Flag off by default; do not put `SLOWPAIR` in `rules.json`')
    lines.append('')
    os.makedirs(os.path.dirname(DOC), exist_ok=True)
    open(DOC, 'w').write('\n'.join(lines) + '\n')
    print('DOC', DOC, flush=True)


def maybe_clips(out, recs_by_id):
    if out['decision'] != 'match_or_beat' or not out.get('changed'):
        return None
    # one Case A and one held-out Case B if they exist, else the first two changed
    ch = out['changed']
    picks = []
    a = next((c for c in ch if c.get('case') == 'A'), None)
    b = next((c for c in ch if c.get('case') == 'B' and c['split'] == 'test'), None)
    if a: picks.append(a['id'])
    if b and b['id'] not in picks: picks.append(b['id'])
    for c in ch:
        if len(picks) >= 2: break
        if c['id'] not in picks: picks.append(c['id'])
    if not picks:
        return None
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import render_slowpair_clips as RC
    RC.main(picks)
    return picks


def main():
    rules = json.load(open(paths.RULES))
    assert 'SLOWPAIR' not in rules, 'rules.json must not enable SLOWPAIR'
    recs = T.load_recs()
    base = T.load_ckpt(BASE_VAR)
    if len(base) != len(recs):
        raise SystemExit(f'base ckpt {BASE_VAR} has {len(base)} of {len(recs)} pairs')
    clash_rows = clash_table(recs, base)
    n_clash = sum(1 for r in clash_rows if r['clash'])
    nA = sum(1 for r in clash_rows if r['clash'] and r['clash']['cases'] == ['A'])
    nB = sum(1 for r in clash_rows if r['clash'] and r['clash']['cases'] == ['B'])
    n_clash_test = sum(1 for r in clash_rows if r['clash'] and r['split'] == 'test')
    print(f'clash {n_clash} of 33 (A {nA}, B {nB}); held-out {n_clash_test} of 12', flush=True)
    seeded = seed_unchanged(recs, base, clash_rows)
    print(f'seeded {len(seeded)} unchanged from {BASE_VAR}', flush=True)

    trial = copy.deepcopy(rules)
    trial['SLOWPAIR'] = 1
    workers = int(os.environ.get('SP_WORKERS', 1))
    rows = T.run_set_checkpointed(recs, trial, VAR, VAR[:6], workers=workers)
    sm = T.summarize(rows)
    arm_by = {r['id']: r for r in rows}
    changed, unmoved = [], []
    for rec, cr in zip(recs, clash_rows):
        row = arm_by[rec['id']]
        win = (row.get('pick') or {}).get('win')
        base_win = cr['default_win']
        moved = list(win) != list(base_win) if win and base_win else False
        sp = row.get('slowpair') or {}
        case = ','.join((cr['clash'] or {}).get('cases') or []) or None
        item = dict(id=rec['id'], split=rec['split'], pair=rec['pair'], case=case,
                    default_win=base_win, win=win,
                    base_score=(base[rec['id']].get('score') or {}).get('score'),
                    arm_score=(row.get('score') or {}).get('score') if not row.get('error') else None)
        if moved:
            changed.append(item)
        elif cr['clash']:
            unmoved.append(item)

    def sc(r):
        s = r.get('score') or {}
        return s['score'] if isinstance(s, dict) else None

    # recompute means in case some seeded rows use the same scorer
    base_sm = T.summarize([T.fill_meta(dict(base[r['id']]), {x['id']: x for x in recs}) for r in recs])
    decision = 'match_or_beat' if (sm['test_mean'] is not None and sm['test_mean'] >= FLOOR_TEST) else 'lose'
    why = None
    if decision == 'lose':
        drops = [c for c in changed if c['arm_score'] is not None and c['base_score'] is not None and c['arm_score'] < c['base_score'] - 0.05]
        gains = [c for c in changed if c['arm_score'] is not None and c['base_score'] is not None and c['arm_score'] > c['base_score'] + 0.05]
        testd = [c for c in drops if c['split'] == 'test']
        bits = [f"Held-out {sm['test_mean']} vs {FLOOR_TEST} ({sm['test_mean']-FLOOR_TEST:+.2f})."]
        bits.append(f"{len(changed)} picks moved ({len(gains)} gained, {len(drops)} lost on the similarity score); {len(unmoved)} clashing defaults had no legal alternative.")
        if testd:
            w = min(testd, key=lambda c: (c['arm_score'] or 0) - (c['base_score'] or 0))
            bits.append(f"Worst held-out move: `{w['id']}` {w['base_score']} → {w['arm_score']} ({w['pair']}).")
        if any(c.get('case') == 'B' for c in drops):
            bits.append("Case B cue moves (skip a hard incoming intro while the outgoing is still in a drop) are the likely drag: they fight the outro-over-intro default on pairs where the scorer still likes the later bars of a long intro.")
        if any(c.get('case') == 'A' for c in drops):
            bits.append("Case A exit moves also lost on at least one pair.")
        why = ' '.join(bits)

    out = dict(
        variant=VAR, bass_fill=False, slowpair=True,
        v3=dict(train=sm['train_mean'], test=sm['test_mean'], n=sm['n'], n_fail=sm['n_fail']),
        by_dj=sm['by_dj'],
        base=dict(variant=BASE_VAR, v3=dict(train=base_sm['train_mean'], test=base_sm['test_mean'], n=base_sm['n'], n_fail=base_sm['n_fail'])),
        arm=dict(variant=VAR, v3=dict(train=sm['train_mean'], test=sm['test_mean'], n=sm['n'], n_fail=sm['n_fail'])),
        n_clash=n_clash, n_clash_A=nA, n_clash_B=nB, n_clash_test=n_clash_test,
        n_changed=len(changed), n_changed_test=sum(1 for c in changed if c['split'] == 'test'),
        changed=changed, clashed_unmoved=unmoved, decision=decision, why=why,
        ts=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
    )
    json.dump(out, open(OUT_JSON, 'w'), indent=2, default=str)
    print('RESULT ' + json.dumps({k: out[k] for k in ('variant', 'v3', 'decision', 'n_clash', 'n_changed', 'why')}, default=str), flush=True)
    write_doc(out)
    if decision == 'match_or_beat':
        try:
            picks = maybe_clips(out, {r['id']: r for r in recs})
            out['clips'] = picks
            json.dump(out, open(OUT_JSON, 'w'), indent=2, default=str)
        except Exception as e:
            print('CLIP_FAIL', type(e).__name__, e, flush=True)
    # confirm rules.json still clean
    rules2 = json.load(open(paths.RULES))
    assert 'SLOWPAIR' not in rules2, 'eval must not write SLOWPAIR into rules.json'


if __name__ == '__main__':
    main()
