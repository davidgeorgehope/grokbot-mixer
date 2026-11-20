#!/usr/bin/env python3
"""SLOWPAIR exit-only (2026-11-20): Case A exit moves, no Case B cue moves.

Two arms, same 33-pair cohort and scorer:
  spex1120_def  — current rules + SLOWPAIR=1 + SLOWPAIR_EXIT=1
  spex1120_stk  — that, on top of epg_stack (EXITPOS+GATE+DROP)

Seeds unchanged (no Case A clash) rows from bfb1120_base / n1120_epg_stack.
Writes results, a placement table, mix-grouped CIs, HC_A/HC_B v2 on moved
pairs, a ranker feature table, and docs/SLOWPAIR_EXIT_2026-11-20.md.
Never writes rules.json. Clips only if an arm is not worse on held-out and
adds no hard fails.
Usage: python3 protrans/eval_slowpair_exit.py
"""
from __future__ import annotations
import copy, json, os, pickle, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/workspace/mixes/src2')
sys.path.insert(0, '/workspace/mixes/protrans/replica')
sys.path.insert(0, '/workspace/mixes/protrans/replica/halftime')
import paths, run_admitted_tune as T, slowpair as S
import promotion_judge as PJ

DAY = '2026-11-20'
BASE_VAR = 'bfb1120_base'
STACK_VAR = 'n1120_epg_stack'
DEF_ARM = 'spex1120_def'
STK_ARM = 'spex1120_stk'
FLOOR_TEST, FLOOR_TRAIN = 34.07, 32.40
OUT_JSON = os.path.join(paths.RESULTS, 'eval_spex1120.json')
DOC = '/workspace/mixes/docs/SLOWPAIR_EXIT_2026-11-20.md'
FEAT_TABLE = '/workspace/mixes/protrans/ranker/slowpair_features_1120.json'
HT_SCAN = os.path.join(paths.RESULTS, 'ht_scan_1120.json')
CLIP_DIR = os.path.join(paths.DELIVER, 'protrans')
KEY_PATH = f'/workspace/private/research_{DAY}_spex_key.json'
GB_ID = 'joe_syntax_hospital__12'


def _assert_rules_clean():
    rules = json.load(open(paths.RULES))
    for k in ('SLOWPAIR', 'SLOWPAIR_EXIT', 'EXITPOS', 'EXITPOS_GATE', 'EXITPOS_DROP'):
        assert k not in rules, f'rules.json must not enable {k}'
    return rules


def _sections_and_spans(yt):
    import slowdown as SD, halftime_tg as H
    sec = S._sections(yt)
    P = SD.profile(yt)
    try:
        ht = H.sections(yt) or []
    except Exception:
        ht = []
    return sec, S.hard_spans(P and P.get('sections'), ht, sec)


def _win(row):
    return (row.get('pick') or {}).get('win')


def _score(row):
    if not row or row.get('error'):
        return None
    s = row.get('score') or {}
    return s['score'] if isinstance(s, dict) else (float(s) if s is not None else None)


def clash_row(rec, win):
    a_sec, a_sp = _sections_and_spans(rec['a']['yt'])
    b_sec, b_sp = _sections_and_spans(rec['b']['yt'])
    both = S.window_clash(win, a_sp, b_sp, a_sec, cases=('A', 'B'))
    only_a = S.window_clash(win, a_sp, b_sp, a_sec, cases=('A',))
    return dict(id=rec['id'], split=rec['split'], dj=rec['dj'], pair=rec['pair'],
                parent_win=list(win) if win else None,
                clash_both=both, clash_a=only_a,
                a_hard=a_sp, b_hard=b_sp, a_yt=rec['a']['yt'], b_yt=rec['b']['yt'])


def seed_unchanged(recs, parent, arm, clash_rows):
    have = T.load_ckpt(arm)
    seeded = []
    for rec, row in zip(recs, clash_rows):
        if rec['id'] in have:
            continue
        if row['clash_a']:
            continue
        src = dict(parent[rec['id']])
        src['seeded_from'] = src.get('seeded_from') or 'parent'
        src['slowpair'] = dict(changed=False, reason='default_ok_exit_only',
                               default_win=row['parent_win'], cases=['A'])
        T.append_ckpt(arm, src)
        seeded.append(rec['id'])
    return seeded


def _mmss(t):
    if t is None:
        return None
    return f'{int(t // 60)}:{int(t % 60):02d}'


def _bar_s(yt):
    p = os.path.join(paths.SRC2, 'st', yt + '.json')
    return 4 * json.load(open(p))['per']


def _span_reason(win, a_sec, b_sec, a_sp, b_sp, ht=None):
    kind, a0, a1, b0, b1, X, ea, ib = S.win_ranges(win)
    bits = []
    cl = S.window_clash(win, a_sp, b_sp, a_sec, cases=('A', 'B'))
    if cl and 'A' in cl['cases']:
        hits = cl['A']
        sp = hits[0]['span']
        labs = ','.join(sp.get('labels') or [])
        bits.append(f"outgoing hard {sp['kind']} {sp['start']}-{sp['end']} ({labs}), overlap {hits[0]['overlap']} bars"
                    + (', blend starts inside it' if hits[0].get('start_inside') else ''))
    elif any(S.overlap_bars(a0, a1, s['start'], s['end']) > 0 for s in a_sp):
        for s in a_sp:
            o = S.overlap_bars(a0, a1, s['start'], s['end'])
            if o:
                bits.append(f"outgoing {s['kind']} {s['start']}-{s['end']} grazes {o} bars (under the Case A cover)")
                break
    if cl and 'B' in cl['cases']:
        hits = cl['B']
        sp = hits[0]['span']
        labs = ','.join(sp.get('labels') or [])
        bits.append(f"incoming hard {sp['kind']} {sp['start']}-{sp['end']} ({labs}) under a still-hot outgoing drop, overlap {hits[0]['overlap']}")
    # ht-scan spans that touch the window, even if not 'hard'
    if ht:
        for side, yt, s0, s1 in (('out', None, a0, a1), ('in', None, b0, b1)):
            pass
        ya, yb = None, None
    return '; '.join(bits) or 'no hard-span clash'


def _ht_touch(yt, s0, s1, scan):
    row = (scan or {}).get(yt) or {}
    bits = []
    for name, key in (('slowdown', 'slow'), ('half-time', 'ht')):
        for sp in row.get(key) or []:
            if isinstance(sp, dict):
                a, b = sp.get('start'), sp.get('end')
            elif isinstance(sp, (list, tuple)) and len(sp) >= 2:
                a, b = sp[0], sp[1]
            else:
                continue
            if a is None or b is None:
                continue
            o = S.overlap_bars(s0, s1, int(a), int(b))
            if o:
                bits.append(f"{name} {int(a)}-{int(b)} overlaps {o} bars")
    return bits


def placement_row(who, rec, win, scan, why=''):
    import provsours as PV
    if not win:
        return dict(who=who, win=None)
    ya, yb = rec['a']['yt'], rec['b']['yt']
    kind, a0, a1, b0, b1, X, ea, ib = S.win_ranges(win)
    r = PV.row(who, ya, yb, a0, a1, ib, None, None, why)
    r['win'] = list(win)
    r['exit_bar'] = a1
    r['cue_bar'] = ib
    r['blend_start_bar'] = a0
    r['out_time'] = _mmss(a0 * _bar_s(ya))
    r['out_exit_time'] = _mmss(a1 * _bar_s(ya))
    r['in_time'] = _mmss(ib * _bar_s(yb))
    r['ht_out'] = _ht_touch(ya, a0, a1, scan)
    r['ht_in'] = _ht_touch(yb, ib, ib + X, scan)
    return r


def pro_placement(rec, scan):
    import provsours as PV
    dec = json.load(open(os.path.join(os.path.dirname(__file__), 'replica', 'protrans_decisions.json')))
    D = dec.get(rec['id'])
    if not D or D.get('out_bar_at_entry') is None:
        return dict(who='pro', win=None)
    ya, yb = rec['a']['yt'], rec['b']['yt']
    a0, a1, b0 = D['out_bar_at_entry'], D['out_bar_at_gone'], D['in_bar_at_entry']
    meta_p = os.path.join(os.path.dirname(rec['pro_clip']), 'meta.json')
    mix_t = None
    if os.path.exists(meta_p):
        meta = json.load(open(meta_p))
        t0 = meta.get('pro_clip_start')
        bs = _bar_s(ya)
        if t0 is not None and D.get('in_entry_clip_bar') is not None:
            mix_t = t0 + D['in_entry_clip_bar'] * bs
    r = PV.row('pro', ya, yb, a0, a1, b0, D.get('out_bar_at_swap'), mix_t, 'what the DJ did')
    r['win'] = None
    r['exit_bar'] = a1
    r['cue_bar'] = b0
    r['blend_start_bar'] = a0
    r['out_time'] = _mmss(a0 * _bar_s(ya))
    r['out_exit_time'] = _mmss(a1 * _bar_s(ya))
    r['in_time'] = _mmss(b0 * _bar_s(yb))
    r['mix_time'] = _mmss(mix_t)
    X = a1 - a0
    r['ht_out'] = _ht_touch(ya, a0, a1, scan)
    r['ht_in'] = _ht_touch(yb, b0, b0 + X, scan)
    return r


def load_hc_index():
    """Map (id, win-tuple) -> flags from any existing arr_*.pkl."""
    import final_eval as FE
    cache = os.path.join(os.path.dirname(__file__), 'replica', 'hc2_cache')
    idx = {}
    if not os.path.isdir(cache):
        return idx
    for fn in os.listdir(cache):
        if not (fn.startswith('arr_') and fn.endswith('.pkl')):
            continue
        path = os.path.join(cache, fn)
        try:
            arr = pickle.load(open(path, 'rb'))
        except Exception:
            continue
        for pid, a in arr.items():
            win = a.get('win')
            if not win:
                continue
            key = (pid, tuple(list(win) if not isinstance(win, list) else [tuple(x) if isinstance(x, list) else x for x in win]))
            try:
                idx.setdefault(key, FE.flags(a))
            except Exception:
                continue
    return idx


def _win_key(pid, win):
    w = []
    for x in win:
        w.append(tuple(x) if isinstance(x, list) else x)
    return (pid, tuple(w))


def hc_from_meta(meta_path, win, rec, hard_v1=None):
    import hardcheck as HC
    import hardcheck_v2 as V
    import final_eval as FE
    import blend_diag as BD
    from engine import BS, BAR
    if hard_v1 is None:
        hard_v1 = HC.check(meta_path)
    M = json.load(open(meta_path))
    t = M['trans'][0]
    s0, A, B = BD.crop_decks(M, 0)
    f = V.deck_feats_b(A, B, BS, BAR / 4)
    arr = dict(s=int(float(t['start_bar']) - s0), e=int(float(t['end_bar']) - s0),
               lows=f['lows'], lag=f['lag'], xr=f['xr'],
               aud=V.audible_mask(f['allA'], f['allB']), hard_v1=hard_v1,
               dj=rec.get('dj'), mix=rec['id'].rsplit('__', 1)[0], win=list(win))
    return FE.flags(arr), arr


def compute_hc(rec, win, rules, tag, hc_idx):
    key = _win_key(rec['id'], win)
    if key in hc_idx:
        return hc_idx[key], 'cache'
    # render this window's rules and compute
    import recreate
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
    sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    old = os.getcwd()
    try:
        info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                                 hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
                                 rules=rules, tag=tag)
        if list((info.get('win') or [])) != list(win):
            # still score the actually rendered window, but flag the mismatch
            flags, _arr = hc_from_meta(info['meta_path'], info['win'], rec)
            flags = dict(flags)
            flags['_win_mismatch'] = dict(wanted=list(win), got=list(info['win']))
            return flags, 'render_mismatch'
        os.chdir(paths.SRC2)
        flags, _arr = hc_from_meta(info['meta_path'], info['win'], rec)
        return flags, 'render'
    finally:
        os.chdir(old)


def lodo_hf_range(rows):
    """Leave-one-DJ-out range of (arm_fail - parent_fail) on HC_B (official)."""
    djs = sorted({r['dj'] for r in rows})
    if len(djs) < 2:
        return None
    vals = []
    for j in djs:
        sub = [r for r in rows if r['dj'] != j]
        if not sub:
            continue
        vals.append(sum(int(r['arm_fail']) - int(r['parent_fail']) for r in sub) / len(sub))
    return [round(min(vals), 3), round(max(vals), 3)] if vals else None


def build_feature_table(recs, base, stack, scan):
    import learned_ranker as LR
    rows = []
    for rec in recs:
        a_sec, a_sp = _sections_and_spans(rec['a']['yt'])
        b_sec, b_sp = _sections_and_spans(rec['b']['yt'])
        wins = {}
        bw = _win(base[rec['id']])
        sw = _win(stack[rec['id']]) if rec['id'] in stack else None
        if bw:
            wins['default'] = bw
        if sw:
            wins['epg_stack'] = sw
        item = dict(id=rec['id'], split=rec['split'], dj=rec['dj'], pair=rec['pair'],
                    a_hard=a_sp, b_hard=b_sp, features={})
        for lab, w in wins.items():
            d = LR.slowpair_feature_dict(w, a_sp, b_sp, a_sec)
            d['win'] = list(w)
            item['features'][lab] = d
        rows.append(item)
    out = dict(written=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
               note='Hard-span / slow-pair flags for the next learned-ranker retrain. Live v0 FEATURE_NAMES are unchanged. Official 33-pair held-out mixes are not training labels.',
               feature_names=list(LR.SLOWPAIR_FEATURE_NAMES),
               n=len(rows), rows=rows)
    os.makedirs(os.path.dirname(FEAT_TABLE), exist_ok=True)
    json.dump(out, open(FEAT_TABLE, 'w'), indent=2, default=str)
    return FEAT_TABLE, out


def maybe_clips(arm_name, trial, parent_rules, recs_by_id, changed, label_arm, label_parent):
    if not changed:
        return None
    # most-changed pair that has a slowdown at the exit; prefer Ghetto Blaster
    def has_slow_exit(c):
        rec = recs_by_id[c['id']]
        _sec, a_sp = _sections_and_spans(rec['a']['yt'])
        win = c['win']
        kind, a0, a1, b0, b1, X, ea, ib = S.win_ranges(win)
        return any(s['kind'] == 'slow' and S.overlap_bars(a0, a1, s['start'], s['end']) > 0 for s in a_sp)

    ranked = sorted(changed, key=lambda c: abs((c.get('arm_score') or 0) - (c.get('parent_score') or 0)), reverse=True)
    pick = None
    if any(c['id'] == GB_ID and has_slow_exit(c) for c in changed):
        pick = next(c for c in changed if c['id'] == GB_ID)
    else:
        pick = next((c for c in ranked if has_slow_exit(c)), ranked[0] if ranked else None)
    if not pick:
        return None
    import random
    import render_planner_clips as RP
    import blend_diag as BD
    os.makedirs(CLIP_DIR, exist_ok=True)
    RP.OUT_DIR = CLIP_DIR
    RP.DIAG_DIR = CLIP_DIR
    _fig = BD.figure
    def _blind(M, i, png, title, **kw):
        return _fig(M, i, png, os.path.basename(png).rsplit('.', 1)[0], **kw)
    BD.figure = _blind
    rec = recs_by_id[pick['id']]
    rng = random.SystemRandom()
    flip = rng.random() < 0.5
    sides = {'A': (label_arm, trial), 'B': (label_parent, parent_rules)} if flip else {'A': (label_parent, parent_rules), 'B': (label_arm, trial)}
    key = {}
    for ab, (name, rr) in sides.items():
        stem = f'spex_{DAY}_{ab}'
        meta = RP.render_one(rec, rr, f'spex{ab}', stem_name=stem)
        key[ab] = dict(variant=name, win=meta['win'], fam=meta['fam'],
                       bass_swap=meta.get('bass_swap'), mp3=meta['mp3'], png=meta['png'])
        pub = {kk: vv for kk, vv in meta.items() if kk not in ('env', 'win', 'fam', 'start_bar', 'end_bar', 'bass_swap', 'src', 'planner')}
        json.dump(pub, open(os.path.join(CLIP_DIR, stem + '.json'), 'w'), indent=2, default=str)
        wav = os.path.join(CLIP_DIR, stem + '.wav')
        if os.path.exists(wav):
            os.remove(wav)
        print('CLIP', ab, meta['mp3'], meta['png'], flush=True)
    # placement PNG for this pair
    try:
        import provsours as PV
        ours = {label_parent: pick['parent_win'], label_arm: pick['win']}
        PV.make(pick['id'], f'spex_{DAY}', ours, CLIP_DIR)
    except Exception as ex:
        print('PROVSOURS_FAIL', type(ex).__name__, ex, flush=True)
    payload = dict(pick=pick['id'], pair=rec['pair'], arm=arm_name, **key)
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    json.dump(payload, open(KEY_PATH, 'w'), indent=2, default=str)
    print('KEY', KEY_PATH, flush=True)
    BD.figure = _fig
    return dict(pick=pick['id'], pair=rec['pair'], arm=arm_name,
                A=os.path.join(CLIP_DIR, f'spex_{DAY}_A.mp3'),
                B=os.path.join(CLIP_DIR, f'spex_{DAY}_B.mp3'),
                A_png=os.path.join(CLIP_DIR, f'spex_{DAY}_A.png'),
                B_png=os.path.join(CLIP_DIR, f'spex_{DAY}_B.png'),
                key=KEY_PATH)


def summarise_arm(name, recs, parent, rows, clash_rows, parent_rules, trial, hc_idx, scan, parent_label):
    sm = T.summarize(rows)
    parent_rows = [T.fill_meta(dict(parent[r['id']]), {x['id']: x for x in recs}) for r in recs]
    parent_sm = T.summarize(parent_rows)
    arm_by = {r['id']: r for r in rows}
    changed, unmoved = [], []
    for rec, cr in zip(recs, clash_rows):
        row = arm_by[rec['id']]
        win = _win(row)
        base_win = cr['parent_win']
        moved = list(win) != list(base_win) if win and base_win else False
        case = ','.join((cr['clash_a'] or cr['clash_both'] or {}).get('cases') or []) or None
        item = dict(id=rec['id'], split=rec['split'], dj=rec['dj'], pair=rec['pair'], case=case,
                    parent_win=base_win, win=win,
                    parent_score=_score(parent[rec['id']]),
                    arm_score=_score(row))
        if moved:
            changed.append(item)
        elif cr['clash_a']:
            unmoved.append(item)

    ci_test = PJ.paired_delta_ci(parent_rows, rows, 'test')
    ci_train = PJ.paired_delta_ci(parent_rows, rows, 'train')

    # hard checks: unchanged inherit parent; changed get computed
    hc_rows = []
    for rec in recs:
        row = arm_by[rec['id']]
        pwin = _win(parent[rec['id']])
        awin = _win(row)
        moved = list(awin) != list(pwin) if awin and pwin else False
        parent_flags = None
        arm_flags = None
        src_p = src_a = None
        if not moved and pwin:
            # Unchanged windows: reuse a cached official flag if we have one.
            # Do not re-render the whole cohort; unknown unchanged stays unknown.
            pk = _win_key(rec['id'], pwin)
            ak = _win_key(rec['id'], awin) if awin else None
            parent_flags = hc_idx.get(pk)
            arm_flags = hc_idx.get(ak) if ak else parent_flags
            src_p = src_a = 'cache' if parent_flags is not None else 'unknown_unchanged'
            if parent_flags is not None and arm_flags is None:
                arm_flags = parent_flags
        else:
            if pwin:
                parent_flags, src_p = compute_hc(rec, pwin, parent_rules, f'hcp{name[-3:]}{rec["id"][-3:]}', hc_idx)
                hc_idx[_win_key(rec['id'], pwin)] = parent_flags
            if awin:
                arm_flags, src_a = compute_hc(rec, awin, trial, f'hca{name[-3:]}{rec["id"][-3:]}', hc_idx)
                hc_idx[_win_key(rec['id'], awin)] = arm_flags
        pf = bool((parent_flags or {}).get('HC_A') or (parent_flags or {}).get('HC_B')) if parent_flags else None
        af = bool((arm_flags or {}).get('HC_A') or (arm_flags or {}).get('HC_B')) if arm_flags else None
        hc_rows.append(dict(id=rec['id'], split=rec['split'], dj=rec['dj'], moved=moved,
                            parent_HC_A=None if not parent_flags else bool(parent_flags.get('HC_A')),
                            parent_HC_B=None if not parent_flags else bool(parent_flags.get('HC_B')),
                            arm_HC_A=None if not arm_flags else bool(arm_flags.get('HC_A')),
                            arm_HC_B=None if not arm_flags else bool(arm_flags.get('HC_B')),
                            parent_fail=pf, arm_fail=af, src_parent=src_p, src_arm=src_a,
                            parent_flags=parent_flags, arm_flags=arm_flags))

    known = [r for r in hc_rows if r['parent_fail'] is not None and r['arm_fail'] is not None]
    new_fails = [r['id'] for r in known if r['arm_fail'] and not r['parent_fail']]
    fixed = [r['id'] for r in known if r['parent_fail'] and not r['arm_fail']]
    added = len(new_fails) > 0
    hc_sum = dict(
        n_known=len(known), n_unknown=len(hc_rows) - len(known),
        parent_HC_A=sum(int(r['parent_HC_A']) for r in known if r['parent_HC_A'] is not None),
        parent_HC_B=sum(int(r['parent_HC_B']) for r in known if r['parent_HC_B'] is not None),
        arm_HC_A=sum(int(r['arm_HC_A']) for r in known if r['arm_HC_A'] is not None),
        arm_HC_B=sum(int(r['arm_HC_B']) for r in known if r['arm_HC_B'] is not None),
        parent_fail=sum(int(r['parent_fail']) for r in known),
        arm_fail=sum(int(r['arm_fail']) for r in known),
        new_fails=new_fails, fixed=fixed, added_hard_fails=added,
        lodo_range=lodo_hf_range(known),
        changed_only=[r for r in hc_rows if r['moved']],
    )

    # placement for every moved pair
    recs_by = {r['id']: r for r in recs}
    place = []
    for c in changed:
        rec = recs_by[c['id']]
        a_sec, a_sp = _sections_and_spans(rec['a']['yt'])
        b_sec, b_sp = _sections_and_spans(rec['b']['yt'])
        why_parent = _span_reason(c['parent_win'], a_sec, b_sec, a_sp, b_sp)
        why_arm = _span_reason(c['win'], a_sec, b_sec, a_sp, b_sp)
        place.append(dict(
            id=c['id'], split=c['split'], pair=c['pair'],
            parent_score=c['parent_score'], arm_score=c['arm_score'],
            pro=pro_placement(rec, scan),
            ours=placement_row(parent_label, rec, c['parent_win'], scan, why_parent),
            variant=placement_row(name, rec, c['win'], scan, why_arm),
        ))

    not_worse_held = sm['test_mean'] is not None and sm['test_mean'] + 1e-9 >= FLOOR_TEST
    # vs this arm's parent held-out as well
    not_worse_parent = (sm['test_mean'] is not None and parent_sm['test_mean'] is not None
                        and sm['test_mean'] + 1e-9 >= parent_sm['test_mean'])
    decision = 'match_or_beat_floor' if (not_worse_held and not added) else (
        'not_worse_than_parent' if (not_worse_parent and not added) else 'lose')
    if added:
        decision = 'lose_hard_fail'
    elif not not_worse_held:
        decision = 'lose' if not not_worse_parent else 'below_floor_not_worse_than_parent'

    return dict(
        name=name, v3=dict(train=sm['train_mean'], test=sm['test_mean'], n=sm['n'], n_fail=sm['n_fail']),
        parent=dict(variant=parent_label, v3=dict(train=parent_sm['train_mean'], test=parent_sm['test_mean'],
                                                  n=parent_sm['n'], n_fail=parent_sm['n_fail'])),
        ci_test=ci_test, ci_train=ci_train,
        n_clash_a=sum(1 for r in clash_rows if r['clash_a']),
        n_clash_a_test=sum(1 for r in clash_rows if r['clash_a'] and r['split'] == 'test'),
        n_changed=len(changed), n_changed_test=sum(1 for c in changed if c['split'] == 'test'),
        changed=changed, clashed_unmoved=unmoved, hc=hc_sum, placement=place,
        decision=decision, not_worse_held=not_worse_held, not_worse_parent=not_worse_parent,
        added_hard_fails=added,
    )


def write_doc(out):
    lines = []
    lines.append('# SLOWPAIR exit-only (2026-11-20)')
    lines.append('')
    lines.append('**`protrans/rules.json` is unchanged.** `SLOWPAIR` and `SLOWPAIR_EXIT` stay off by default. This arm only does Case A exit moves; Case B cue moves are off.')
    lines.append('')
    lines.append('## What was tried')
    lines.append('- The combined `SLOWPAIR=1` flag lost (held-out 32.11 vs 34.07) after 11 picks moved. The likely drag was Case B cue moves that fight the outro-over-intro default.')
    lines.append('- Exit-only (`SLOWPAIR=1`, `SLOWPAIR_EXIT=1`) keeps the hard-span detector and Case A (start inside, or at least 12 bars of, an outgoing hard outro / in-drop). Starting a few bars before the slowdown is still allowed. Case B is ignored.')
    lines.append('- Two bases: the current default, and epg_stack (`EXITPOS` + `EXITPOS_GATE` + `EXITPOS_DROP`), because drop-fade exits were preferred 5/5 on listening.')
    lines.append('- Same 33-pair cohort and scorer. Mix-grouped bootstrap CIs (4000, seed 20261119) of arm minus the parent. Official hard-fail is HC_A / HC_B v2 on moved windows (unchanged windows keep the parent result).')
    lines.append('')
    lines.append('## Results')
    lines.append('')
    lines.append('| variant | held-out | train | n | n_fail | pairs changed | held-out CI (arm − parent) |')
    lines.append('|---|---:|---:|---:|---:|---:|---|')
    lines.append(f"| {BASE_VAR} (current rules) | **{FLOOR_TEST}** | **{FLOOR_TRAIN}** | 33 | 0 | 0 | — |")
    for arm in (out['def_arm'], out['stk_arm']):
        ci = arm.get('ci_test') or {}
        ci_s = f"{ci.get('mean_delta')} {ci.get('ci')} incl0={ci.get('includes_zero')}" if ci else '—'
        lines.append(f"| {arm['name']} | {arm['v3']['test']} | {arm['v3']['train']} | {arm['v3']['n']} | {arm['v3']['n_fail']} | {arm['n_changed']} | {ci_s} |")
    # also show stack parent
    stk_p = out['stk_arm']['parent']['v3']
    lines.append(f"| {STACK_VAR} (parent of the stacked arm) | {stk_p['test']} | {stk_p['train']} | {stk_p['n']} | {stk_p['n_fail']} | 0 | — |")
    lines.append('')
    for key, title in (('def_arm', 'On the current default'), ('stk_arm', 'On epg_stack')):
        arm = out[key]
        lines.append(f"### {title} (`{arm['name']}`)")
        lines.append('')
        lines.append(f"Decision: **{arm['decision']}**. Case A clashes on the parent window: {arm['n_clash_a']} of 33 (held-out {arm['n_clash_a_test']} of 12). Picks moved: {arm['n_changed']} (held-out {arm['n_changed_test']}).")
        lines.append('')
        hc = arm['hc']
        lines.append(f"Hard-fail (HC_A / HC_B v2, {hc['n_known']} windows with a known parent and arm result; {hc['n_unknown']} unchanged windows had no cached flags and were not re-rendered): parent {hc['parent_fail']} → arm {hc['arm_fail']} (HC_A {hc['parent_HC_A']}→{hc['arm_HC_A']}, HC_B {hc['parent_HC_B']}→{hc['arm_HC_B']}). New fails: {hc['new_fails'] or 'none'}. Fixed: {hc['fixed'] or 'none'}. Leave-one-DJ-out fail-delta range: {hc['lodo_range']}.")
        lines.append('')
        if arm.get('changed'):
            lines.append('Changed pairs (parent → exit-only, score parent → arm):')
            lines.append('')
            for c in arm['changed']:
                lines.append(f"- `{c['id']}` ({c['split']}, {c.get('case','?')}): `{c['parent_win']}` → `{c['win']}` , {c['parent_score']} → {c['arm_score']} ({c['pair']})")
            lines.append('')
        if arm.get('clashed_unmoved'):
            lines.append('Parent Case A clashed but the pick did not move:')
            lines.append('')
            for c in arm['clashed_unmoved']:
                lines.append(f"- `{c['id']}` ({c['split']}): `{c['parent_win']}` ({c['pair']})")
            lines.append('')
        if arm.get('placement'):
            lines.append('Placement (pro vs parent vs exit-only). Bars are each track\'s own bars; out_time / in_time are track time at the blend start / cue; mix_time is the pro set time when known.')
            lines.append('')
            cols = ['who', 'exit_bar', 'cue_bar', 'blend_start_bar', 'out_time', 'in_time', 'mix_time', 'out_start_section', 'in_start_section', 'out_last_drop_played', 'ht_out', 'ht_in', 'why']
            for p in arm['placement']:
                lines.append(f"#### `{p['id']}` — {p['pair']} ({p['split']}, {p['parent_score']} → {p['arm_score']})")
                lines.append('')
                lines.append('| ' + ' | '.join(cols) + ' |')
                lines.append('|' + '---|' * len(cols))
                for r in (p['pro'], p['ours'], p['variant']):
                    vals = []
                    for c in cols:
                        v = r.get(c)
                        if isinstance(v, list):
                            v = '; '.join(v) if v else ''
                        vals.append(str(v))
                    lines.append('| ' + ' | '.join(vals) + ' |')
                lines.append('')
    if out.get('clips'):
        c = out['clips']
        lines.append('## Clips')
        lines.append('')
        lines.append(f"Blind A/B for `{c['pick']}` ({c['pair']}), arm `{c['arm']}`. Files in `deliver/protrans/`. The key is only under `/workspace/private/`.")
        lines.append('')
        lines.append(f"- {c.get('A')}")
        lines.append(f"- {c.get('B')}")
        lines.append(f"- {c.get('A_png')}")
        lines.append(f"- {c.get('B_png')}")
        lines.append('')
    else:
        lines.append('## Clips')
        lines.append('')
        lines.append('No clips: neither arm was both not-worse on held-out against the 34.07 floor and free of new hard fails, or no pair moved.' if not out.get('clip_skipped') else out['clip_skipped'])
        lines.append('')
    lines.append('## Ranker features')
    lines.append('')
    lines.append(f"Slow-pair and hard-section flags are in `{FEAT_TABLE}` (`sp_case_a`, `sp_case_b`, cover, start-inside, incoming overlap, outgoing-hot, half-time, outro / in-drop / intro flags). The live v0 ranker feature width is unchanged; no retrain was run.")
    lines.append('')
    lines.append('## Code')
    lines.append('')
    lines.append('- `src2/slowpair.py` — `SLOWPAIR_EXIT=1` / `allowed_cases()` (Case A only)')
    lines.append('- `protrans/recreate.py` — exports `SLOWPAIR_EXIT` when a trial sets it')
    lines.append('- `protrans/eval_slowpair_exit.py`, `protrans/eval_slowpair_exit.sh`')
    lines.append('- `src/tests/test_slowpair.py`')
    lines.append('- `src2/learned_ranker.py` — `SLOWPAIR_FEATURE_NAMES` (retrain helper only)')
    lines.append('- Flags off by default; do not put `SLOWPAIR` or `SLOWPAIR_EXIT` in `rules.json`')
    lines.append('')
    open(DOC, 'w').write('\n'.join(lines) + '\n')
    print('DOC', DOC, flush=True)


def main():
    rules = _assert_rules_clean()
    recs = T.load_recs()
    base = T.load_ckpt(BASE_VAR)
    stack = T.load_ckpt(STACK_VAR)
    if len(base) != len(recs):
        raise SystemExit(f'base ckpt {BASE_VAR} has {len(base)} of {len(recs)} pairs')
    if len(stack) != len(recs):
        raise SystemExit(f'stack ckpt {STACK_VAR} has {len(stack)} of {len(recs)} pairs')

    scan = json.load(open(HT_SCAN)) if os.path.exists(HT_SCAN) else {}
    def_clash = [clash_row(r, _win(base[r['id']])) for r in recs]
    stk_clash = [clash_row(r, _win(stack[r['id']])) for r in recs]
    print(f"default Case A clash {sum(1 for r in def_clash if r['clash_a'])} of 33; "
          f"stack Case A clash {sum(1 for r in stk_clash if r['clash_a'])} of 33", flush=True)

    seeded_d = seed_unchanged(recs, base, DEF_ARM, def_clash)
    seeded_s = seed_unchanged(recs, stack, STK_ARM, stk_clash)
    print(f'seeded {len(seeded_d)} unchanged onto {DEF_ARM} from {BASE_VAR}', flush=True)
    print(f'seeded {len(seeded_s)} unchanged onto {STK_ARM} from {STACK_VAR}', flush=True)

    workers = int(os.environ.get('SP_WORKERS', 1))
    trial_def = copy.deepcopy(rules)
    trial_def['SLOWPAIR'] = 1
    trial_def['SLOWPAIR_EXIT'] = 1
    trial_stk = copy.deepcopy(trial_def)
    trial_stk['EXITPOS'] = 1
    trial_stk['EXITPOS_GATE'] = 1
    trial_stk['EXITPOS_DROP'] = 1

    rows_def = T.run_set_checkpointed(recs, trial_def, DEF_ARM, 'sxdef', workers=workers)
    rows_stk = T.run_set_checkpointed(recs, trial_stk, STK_ARM, 'sxstk', workers=workers)

    _assert_rules_clean()
    hc_idx = load_hc_index()
    print(f'hc cache entries {len(hc_idx)}', flush=True)

    def_sum = summarise_arm(DEF_ARM, recs, base, rows_def, def_clash, rules, trial_def, hc_idx, scan, BASE_VAR)
    stk_sum = summarise_arm(STK_ARM, recs, stack, rows_stk, stk_clash, {**rules, 'EXITPOS': 1, 'EXITPOS_GATE': 1, 'EXITPOS_DROP': 1},
                            trial_stk, hc_idx, scan, STACK_VAR)

    feat_path, _feat = build_feature_table(recs, base, stack, scan)
    print('FEATURES', feat_path, flush=True)

    clips = None
    clip_skipped = None
    # Prefer a floor-clearing arm; otherwise skip clips
    candidates = []
    for arm, trial, parent_rules, parent_label in (
        (def_sum, trial_def, rules, 'default'),
        (stk_sum, trial_stk, {**rules, 'EXITPOS': 1, 'EXITPOS_GATE': 1, 'EXITPOS_DROP': 1}, 'epg_stack'),
    ):
        if arm['not_worse_held'] and not arm['added_hard_fails'] and arm['changed']:
            candidates.append((arm, trial, parent_rules, parent_label))
    if candidates:
        # prefer the default-base arm if both qualify; clip the most-changed slowdown-at-exit pair
        arm, trial, parent_rules, parent_label = candidates[0]
        try:
            clips = maybe_clips(arm['name'], trial, parent_rules, {r['id']: r for r in recs},
                                arm['changed'], arm['name'], parent_label)
        except Exception as e:
            print('CLIP_FAIL', type(e).__name__, e, flush=True)
            clip_skipped = f'Clip render failed: {type(e).__name__}: {e}'
    else:
        clip_skipped = 'No clips: neither arm was not-worse on held-out against the 34.07 floor with no new hard fails, or no pair moved.'

    out = dict(
        variant='spex1120', slowpair_exit=True,
        floor=dict(test=FLOOR_TEST, train=FLOOR_TRAIN),
        def_arm=def_sum, stk_arm=stk_sum,
        features=feat_path, clips=clips, clip_skipped=clip_skipped,
        ts=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
    )
    # shrink hc flags in the written JSON (keep summaries + changed_only without raw arrays)
    for arm in (out['def_arm'], out['stk_arm']):
        slim = []
        for r in arm['hc'].get('changed_only') or []:
            slim.append({k: r[k] for k in r if k not in ('parent_flags', 'arm_flags')} |
                        dict(parent_flags={k: (r.get('parent_flags') or {}).get(k) for k in ('HC_A', 'HC_B', 'hole_v2', 'clash_v1', 'clash_v2', 'halfbeat', 'pump', 'hole_score', 'med_lag') if r.get('parent_flags')},
                             arm_flags={k: (r.get('arm_flags') or {}).get(k) for k in ('HC_A', 'HC_B', 'hole_v2', 'clash_v1', 'clash_v2', 'halfbeat', 'pump', 'hole_score', 'med_lag') if r.get('arm_flags')}))
        arm['hc']['changed_only'] = slim

    json.dump(out, open(OUT_JSON, 'w'), indent=2, default=str)
    print('RESULT ' + json.dumps({
        'def': {k: def_sum[k] for k in ('name', 'v3', 'decision', 'n_changed', 'added_hard_fails', 'ci_test')},
        'stk': {k: stk_sum[k] for k in ('name', 'v3', 'decision', 'n_changed', 'added_hard_fails', 'ci_test')},
    }, default=str), flush=True)
    write_doc(out)
    _assert_rules_clean()


if __name__ == '__main__':
    main()
