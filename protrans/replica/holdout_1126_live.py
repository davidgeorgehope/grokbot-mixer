#!/usr/bin/env python3
"""n1126 locked-holdout evaluation for ridegate live vs default (2nd+ opening).

Follows the 11-19 procedure, adapted to the n1126 tools: picker_1126.py holdout,
analyze_1126.py holdout (mix-grouped bootstrap, 4000 draws, seed 20261126), render
moved picks and defaults for official hard-check veto, recompute exit+cue CI,
append locked_holdout_opens, and if it passes write a promotion recommendation in docs.

Does not write rules.json or change defaults. Do not run until the live protrans
render has been confirmed to match the map render.

usage: holdout_1126_live.py
"""
from __future__ import annotations
import json, os, sys, subprocess, collections, hashlib, numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

H = os.path.dirname(os.path.abspath(__file__))
P0 = os.path.dirname(H)
ROOT = os.path.dirname(P0)
W = os.path.join(H, 'nightly_1126_work')
sys.path.insert(0, H); sys.path.insert(0, P0)
import paths

ET = ZoneInfo('America/New_York')
SEED = 20261126
NB = 4000
RULES_SHA_EXPECTED = None  # filled at start from the live file; must not change


def _now():
    return datetime.now(ET).strftime('%Y-%m-%d %H:%M %Z')


def _sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd, cwd, env=None):
    print('RUN', ' '.join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    if r.returncode != 0:
        raise SystemExit(f'command failed rc={r.returncode}: {" ".join(cmd)}')


def _ckpt(path):
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path):
        r = json.loads(line)
        out[r['id']] = r
    return out


def _boot_ec(pp, use):
    """Mix-grouped bootstrap of mean exit+cue delta (arm-or-default after use() minus default)."""
    def ec(p, arm_on):
        x = p['ridegate'] if arm_on else p['default']
        return (abs(x['exit'] - p['pro_out']) + abs(x['cue'] - p['pro_in'])) / 2
    A = np.array([ec(p, use(p)) - ec(p, False) for p in pp])
    idx = collections.defaultdict(list)
    for i, p in enumerate(pp):
        idx[p['mix']].append(i)
    gs = sorted(idx, key=str)
    rng = np.random.default_rng(SEED)
    BS = [np.concatenate([idx[gs[m]] for m in rng.choice(len(gs), len(gs))]) for _ in range(NB)]
    s = [A[ii].mean() for ii in BS]
    return [round(float(A.mean()), 2), round(float(np.percentile(s, 2.5)), 2), round(float(np.percentile(s, 97.5)), 2)]


def _ci_pass(triple):
    return triple[1] < 0 and triple[2] < 0


def classify_veto(per_pair, PF, DF):
    """Hard-check veto for moved official windows.

    Missing audio / a missing or failed render is 'not_evaluated', never a veto
    and never a revert. After-veto CI must be computed only on evaluable pairs
    (abstains, plus moved pairs where both arms rendered).
    """
    recs, cnt = [], collections.Counter()
    cnt['n'] = len(per_pair)
    for p in per_pair:
        i, rg = p['id'], p['ridegate']
        if rg.get('is_default') or not rg.get('win'):
            recs.append(dict(id=i, status='abstain', evaluable=True, veto=False))
            cnt['abstain'] += 1
            cnt['evaluable'] += 1
            continue
        cnt['moved'] += 1
        rec = dict(id=i, want=rg['win'])
        if i not in PF or PF[i].get('error') or i not in DF or DF[i].get('error'):
            rec['status'] = 'not_evaluated'
            rec['evaluable'] = False
            rec['veto'] = False
            rec['why'] = 'missing_render' if (i not in PF or (PF.get(i) or {}).get('error')) else 'missing_default'
            cnt['not_evaluated'] += 1
            recs.append(rec)
            continue
        rr = PF[i]
        rec['got'] = rr.get('win')
        rec['applied'] = bool(rr.get('win') and list(rr['win']) == list(rg['win']))
        rec['fam'] = rr.get('fam')
        ph = (rr.get('hard') or {})
        dh = (DF[i].get('hard') or {})
        rec['pick_hard_fail'] = bool(ph.get('hard_fail'))
        rec['def_hard_fail'] = bool(dh.get('hard_fail'))
        rec['new_hard_fail'] = bool(rec['pick_hard_fail'] and rec['def_hard_fail'] is False)
        rec['flags'] = {k: ph.get(k) for k in ('beat_clash', 'bass_hole', 'pumping', 'incoming_vanish', 'hard_fail')}
        rec['status'] = 'checked'
        rec['evaluable'] = True
        rec['veto'] = bool(rec['new_hard_fail'] or not rec['applied'])
        cnt['checked'] += 1
        cnt['evaluable'] += 1
        cnt['veto'] += int(rec['veto'])
        cnt['new_hard_fail'] += int(rec['new_hard_fail'])
        cnt['not_applied'] += int(not rec['applied'])
        recs.append(rec)
    return recs, cnt


def main():
    cmp_p = os.path.join(W, 'ridegate_live_vs_map_render.json')
    cmp = json.load(open(cmp_p))
    if not cmp.get('match'):
        print('REFUSE holdout: live render does not match the map render', cmp, flush=True)
        return 2
    rules_path = paths.RULES
    sha0 = _sha(rules_path)
    rules = json.load(open(rules_path))
    if rules.get('RIDEGATE') or rules.get('PICKER_STYLE_GATED'):
        raise SystemExit('rules.json unexpectedly has a picker flag on; refusing to open the holdout')
    print('rules.json sha', sha0, 'mtime unchanged check at end', flush=True)

    env = os.environ.copy()
    for k in ('PICKER_STYLE_GATED', 'PICKER_STYLE_GATED_MAP', 'PICKER_INJECT_CS', 'PICKER_WIN', 'RIDEGATE', 'RIDEGATE_PACK'):
        env.pop(k, None)

    _run([sys.executable, os.path.join(H, 'picker_1126.py'), 'holdout'], cwd=H, env=env)
    _run([sys.executable, os.path.join(H, 'analyze_1126.py'), 'holdout'], cwd=H, env=env)

    pj = json.load(open(os.path.join(W, 'picker_1126_holdout.json')))
    an = json.load(open(os.path.join(W, 'analysis_1126_holdout.json')))
    raw = an['deltas']['ridegate_vs_default']['exit_cue']
    print('RAW ridegate_vs_default exit+cue', raw, flush=True)

    # Live pack vs picker_1126 holdout ridegate (same all-dev fit; should agree)
    sys.path.insert(0, H)
    import ridegate_live as RG
    rows = [r for r in RG.load_all_built() if r['set'] == 'holdout']
    pack = RG.load_pack()
    live = {r['id']: d for r, d in zip(rows, RG.predict_rows(pack, rows))}
    ref = {p['id']: p['ridegate'] for p in pj['per_pair']}
    agr, n = 0, 0
    disagree = []
    for p in pj['per_pair']:
        n += 1
        ok = RG._same(live[p['id']], ref[p['id']])
        agr += int(ok)
        if not ok:
            disagree.append(dict(id=p['id'], why=RG.why_disagree(
                dict(exit=live[p['id']]['exit'], cue=live[p['id']]['cue'], X=live[p['id']]['X'],
                     win=live[p['id']].get('win'), abstain=bool(live[p['id']].get('is_default')),
                     p_leave=live[p['id']].get('p_leave')),
                dict(exit=ref[p['id']]['exit'], cue=ref[p['id']]['cue'], X=ref[p['id']]['X'],
                     win=ref[p['id']].get('win'), abstain=bool(ref[p['id']].get('is_default')),
                     p_leave=ref[p['id']].get('p_leave')))))
    pack_agree = dict(n=n, agree=agr, rate=round(agr / n, 4) if n else None, disagree=disagree)
    print('LIVE_PACK vs picker_1126 holdout ridegate', pack_agree, flush=True)

    ids = [p['id'] for p in pj['per_pair']]
    moved = [p['id'] for p in pj['per_pair'] if not p['ridegate'].get('is_default') and p['ridegate'].get('win')]
    src = os.path.join(H, 'nightly_1119_work', 'src')
    env2 = dict(env)
    env2['EXTRA_SRC'] = src
    env2['ONLY'] = ','.join(ids)
    env2['WORKERS'] = os.environ.get('WORKERS', '2')
    _run([sys.executable, os.path.join(H, 'eval_gate.py'),
          'n1126h_default={}', 'n1126h_ridegate_live={"RIDEGATE":1}'], cwd=H, env=env2)

    DF = _ckpt(os.path.join(H, 'gate_ckpt', 'n1126h_default.jsonl'))
    PF = _ckpt(os.path.join(H, 'gate_ckpt', 'n1126h_ridegate_live.jsonl'))
    veto_pairs, cnt = classify_veto(pj['per_pair'], PF, DF)
    ev_ids = {r['id'] for r in veto_pairs if r.get('evaluable')}
    ev_pairs = [p for p in pj['per_pair'] if p['id'] in ev_ids]
    V = {r['id']: r['veto'] for r in veto_pairs if r.get('evaluable')}
    raw_evaluable = _boot_ec(ev_pairs, lambda p: (not p['ridegate'].get('is_default')))
    after = _boot_ec(ev_pairs, lambda p: (not p['ridegate'].get('is_default')) and (not V.get(p['id'], False)))
    raw_ok = _ci_pass(raw)
    ev_ok = _ci_pass(raw_evaluable)
    after_ok = _ci_pass(after)
    veto = dict(counts=dict(cnt), pairs=veto_pairs,
                after_veto=dict(delta_exit_cue=after, pass_ci=after_ok, n=len(ev_pairs)),
                raw=dict(delta_exit_cue=raw, pass_ci=raw_ok, n=pj['n']),
                raw_evaluable=dict(delta_exit_cue=raw_evaluable, pass_ci=ev_ok, n=len(ev_pairs)),
                pack_agree=pack_agree, n=pj['n'], mixes=pj['mixes'])
    json.dump(veto, open(os.path.join(W, 'hc_veto_1126_holdout.json'), 'w'), indent=1, default=str)
    print('VETO', json.dumps(veto['counts']),
          'raw_all', raw, 'raw_evaluable', raw_evaluable, 'after_veto', after,
          'pass', after_ok, 'raw_pass', raw_ok, flush=True)

    # Log the opening (2nd). Do not touch frozen arms, promotion rule text, or rules.json.
    crit_p = os.path.join(H, 'promotion_criteria.json')
    crit = json.load(open(crit_p))
    entry = dict(
        when=_now(),
        by='ridegate-live-render-holdout job (picker_1126.py holdout + analyze_1126.py holdout + official hard-check veto)',
        pairs=pj['n'],
        mixes=pj['mixes'],
        candidate='n1126 ridegate live (RIDEGATE flag, all-dev pack, non-map path)',
        result=f"raw exit+cue delta {raw[0]} [{raw[1]}, {raw[2]}]; after official hard-check veto {after[0]} [{after[1]}, {after[2]}]; pack_agree {pack_agree['agree']}/{pack_agree['n']}",
        pass_raw=raw_ok,
        pass_after_veto=after_ok,
        note='2nd opening of the Liquicity/Hospital locked holdout (first opening 2026-11-19 did not pass). CI must be entirely below 0. rules.json and defaults were not changed.',
    )
    crit.setdefault('locked_holdout_opens', []).append(entry)
    json.dump(crit, open(crit_p, 'w'), indent=2)
    print('LOGGED locked_holdout_opens', entry['when'], 'pass_after_veto', after_ok, flush=True)

    sha1 = _sha(rules_path)
    if sha1 != sha0:
        raise SystemExit('rules.json changed during the holdout run; this is not allowed')

    rec_path = None
    if after_ok:
        rec_path = _write_recommendation(pj, an, raw, after, veto, pack_agree)
        print('WROTE recommendation', rec_path, flush=True)
    else:
        print('Holdout did not pass (after-veto CI is not entirely below 0). No promotion recommendation. rules.json unchanged.', flush=True)

    json.dump(dict(raw=raw, after=after, pass_raw=raw_ok, pass_after_veto=after_ok,
                   pack_agree=pack_agree, logged=entry, recommendation=rec_path,
                   rules_sha=sha0),
              open(os.path.join(W, 'holdout_1126_live_summary.json'), 'w'), indent=1, default=str)
    return 0 if after_ok else 0  # evaluation finished; a fail is a result, not a job failure


def _write_recommendation(pj, an, raw, after, veto, pack_agree):
    fresh = json.load(open(os.path.join(W, 'analysis_1126_fresh.json')))
    fr = fresh['deltas']['ridegate_vs_default']['exit_cue']
    cv = json.load(open(os.path.join(W, 'analysis_1126_cv.json')))
    cv_d = cv['deltas']['ridegate_vs_default']['exit_cue']
    rec = os.path.join(ROOT, 'docs', 'PROMOTION_REC_RIDEGATE_N1126.md')
    text = f"""# Promotion recommendation: ridegate (n1126 live path)

Written {_now()}. This is a recommendation only. `protrans/rules.json` and all defaults are unchanged; promotion is for the owner to decide.

## Why it is eligible to be decided now

- Two consecutive qualifying nights: n1125 and n1126, primary arm `ridegate` (style-free gated exit ranker + ride-vs-leave gate, cue = gated cue ranker, X stays at the default).
- Live (non-map) path exists behind the `RIDEGATE` flag (off by default), with tests passing (85/85) and pack agreement 33/33 vs the n1126 map and 1001/1001 vs leave-one-DJ-out CV. The n1126 pinned-set render with `RIDEGATE=1` (map flags off) matched the map-based ridegate render on official v1 scores, windows, and official hard checks.
- Locked holdout, **2nd opening** ({_now()}): ridegate live vs default, exit+cue mix-grouped bootstrap (4000 draws, seed 20261126). Raw {raw[0]} [{raw[1]}, {raw[2]}]. After the official hard-check veto (same rule as 11-19: a new hard fail, or a pick that did not apply, reverts to default): {after[0]} [{after[1]}, {after[2]}]. The after-veto CI lies entirely below 0.
- Fresh-mix pass (already done on n1126, mix `ukf_drum_bass_wVp_VlkWqxI`, 18 transitions): ridegate vs default exit+cue point estimate {fr[0]} (indicative pair-bootstrap [{fr[1]}, {fr[2]}]), which meets the qualifying-night rule (point estimate vs default ≤ 0). Dev CV the same night was {cv_d[0]} [{cv_d[1]}, {cv_d[2]}].

## What promotion would mean

Turn `RIDEGATE` on in the flag/defaults mechanism (`protrans/rules.json`) so the listener's mixes use the live pack at render time. Do not keep using `PICKER_STYLE_GATED_MAP`. This document does not make that change.

## Holdout note

This is a repeated look at the Liquicity / Hospital Records locked holdout (14 pairs, mixes: {', '.join(pj['mixes'])}). First opening was 2026-11-19 and did not pass. Live pack vs `picker_1126` holdout ridegate decisions: {pack_agree['agree']}/{pack_agree['n']}. Veto counts: {json.dumps(veto['counts'])}.
"""
    open(rec, 'w').write(text)
    nightly = os.path.join(ROOT, 'docs', 'NIGHTLY_2026-11-26.md')
    if os.path.exists(nightly):
        with open(nightly, 'a') as f:
            f.write(f"""

## Locked holdout (2nd opening) and promotion recommendation

{_now()}. The live `RIDEGATE` path is in place and the pinned-set live render matched the map render. The locked holdout was then opened for the second time (first opening 2026-11-19 did not pass). Ridegate live vs default, exit+cue: raw {raw[0]} [{raw[1]}, {raw[2]}]; after official hard-check veto {after[0]} [{after[1]}, {after[2]}] (CI entirely below 0). Fresh-mix pass was already done tonight (`ukf_drum_bass_wVp_VlkWqxI`, {fr[0]} [{fr[1]}, {fr[2]}]). **Recommendation: eligible to promote `RIDEGATE`; `rules.json` was not edited in this work.** Full write-up: `docs/PROMOTION_REC_RIDEGATE_N1126.md`.
""")
    return rec


if __name__ == '__main__':
    raise SystemExit(main() or 0)
