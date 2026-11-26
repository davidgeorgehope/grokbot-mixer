#!/usr/bin/env python3
"""Load the nightly arm card and report drum_linger_bars + exit lag vs the pro.

n1127 reads candidates_n1127 from nightly_candidates.json. The n1126 list stays
in candidates / candidates_n1126. Do not write rules.json. Flags stay off unless
an arm's delta turns them on for that run.
"""
from __future__ import annotations
import json, os, statistics

H = os.path.dirname(os.path.abspath(__file__))
P = os.path.dirname(H)
CANDS_FILE = os.path.join(H, 'nightly_candidates.json')
PRO_DECISIONS = os.path.join(H, 'protrans_decisions.json')
REQUIRED_REPORT = ('v1', 'v2', 'hard_fail', 'drum_linger_bars', 'exit_lag_vs_pro')
MAX_CANDS = 6
_SPEC = None
_PRO = None


def load_spec(path=None):
    global _SPEC
    path = path or CANDS_FILE
    if _SPEC is not None and path == CANDS_FILE:
        return _SPEC
    spec = json.load(open(path))
    if path == CANDS_FILE:
        _SPEC = spec
    return spec


def card_for(tag, spec=None):
    """Return the 6-arm list for a nightly tag (e.g. n1127)."""
    spec = spec or load_spec()
    key = f'candidates_{tag}'
    if spec.get(key):
        return list(spec[key])[:MAX_CANDS]
    return list(spec.get('candidates') or [])[:MAX_CANDS]


def arm_deltas(tag, spec=None):
    return [(c['name'], dict(c.get('delta') or {})) for c in card_for(tag, spec)]


def short_render_tag(tag, name):
    """Unique short render tag so two arms cannot share a /tmp prefix."""
    parts = [p[:3] for p in str(name).split('_') if p]
    compact = ''.join(parts)[:12]
    if not compact:
        compact = 'arm'
    return f'{tag}{compact}'


def validate(spec=None, tag='n1127'):
    """Raise AssertionError if the card cannot be used as a nightly."""
    import sys
    sys.path.insert(0, P)
    import recreate
    import inspect
    spec = spec or load_spec()
    assert spec.get('adopt_to_defaults') is False, 'adopt_to_defaults must be false'
    card = card_for(tag, spec)
    assert len(card) == MAX_CANDS, f'{tag} card must have {MAX_CANDS} arms, got {len(card)}'
    names = [c['name'] for c in card]
    assert len(set(names)) == len(names), f'duplicate arm names: {names}'
    src = inspect.getsource(recreate.apply_rules)
    rules_path = None
    try:
        import paths
        rules_path = paths.RULES
    except Exception:
        pass
    rules = json.loads(open(rules_path).read()) if rules_path and os.path.exists(rules_path) else {}
    for c in card:
        assert c.get('flags_off_by_default') is True, f"{c['name']} must be off by default"
        delta = c.get('delta') or {}
        assert delta, f"{c['name']} has empty delta"
        for k, val in delta.items():
            assert f"'{k}'" in src, f"{c['name']} flag {k} is not in apply_rules"
            # Only on/off switches must be off in rules and in the default env.
            # Numeric freezes (TAIL_EXIT=6, fade slope, ...) may already be defaults.
            if val != 1 and str(val).strip().lower() not in ('1', 'true'):
                continue
            rv = rules.get(k)
            assert str(rv).strip().lower() in ('', '0', 'false', 'none', 'no') or rv is None, (
                f"{k} must not be on in rules.json"
            )
            ev = recreate.apply_rules({}).get(k)
            assert ev is None or str(ev).strip().lower() in ('', '0', 'false', 'none', 'no'), (
                f"{k} leaked into default apply_rules env"
            )
        metrics = c.get('report_metrics') or []
        for m in REQUIRED_REPORT:
            assert m in metrics, f"{c['name']} must report {m}"
    shorts = [short_render_tag(tag, n) for n in names]
    assert len(set(shorts)) == len(shorts), f'short-tag collision: {shorts}'
    return dict(tag=tag, arms=names, short_tags=shorts, n=len(card))


def exit_start(win):
    if not win or not isinstance(win, (list, tuple)) or win[0] != 'n' or len(win) < 5:
        return None
    return int(win[1]) - int(win[4]) + 1


def _pro_map():
    global _PRO
    if _PRO is None:
        _PRO = json.load(open(PRO_DECISIONS)) if os.path.exists(PRO_DECISIONS) else {}
    return _PRO


def _summarize_nums(vals):
    vals = [float(v) for v in vals if v is not None]
    if not vals:
        return dict(n=0, mean=None, med=None)
    s = sorted(vals)
    return dict(n=len(s), mean=round(sum(s) / len(s), 2),
                med=round(statistics.median(s), 2),
                min=round(s[0], 2), max=round(s[-1], 2))


def pair_linger_lag(row, built=None, pro=None, sa=None, sb=None, hiA=None, a_yt=None):
    """One pair: exit lag vs the pro and drum_linger_bars for the applied window."""
    import sys
    if H not in sys.path:
        sys.path.insert(0, H)
    import ridegate_live as RG
    win = (row.get('pick') or {}).get('win') or row.get('win')
    pid = row.get('id')
    pro = pro if pro is not None else (_pro_map().get(pid) or {}).get('out_bar_at_entry')
    ex = exit_start(win)
    lag = None if ex is None or pro is None else round(float(ex) - float(pro), 2)
    dl = None
    try:
        if built:
            sa = sa or built.get('sa')
            sb = sb or built.get('sb')
            if hiA is None:
                hiA = built.get('hiA')
            a_yt = a_yt or built.get('a_yt') or (built.get('a') or {}).get('yt')
        if hiA is None and a_yt:
            hiA = RG.load_drum_hi(a_yt)
        if sa is not None and sb is not None and win:
            dl = int(RG.drum_linger_bars(sa, sb, win, hiA))
    except Exception:
        dl = None
    return dict(id=pid, win=list(win) if win else None, exit_start=ex,
                pro_out=None if pro is None else round(float(pro), 2),
                exit_lag=lag, drum_linger_bars=dl)


def summarize_linger_and_lag(arm_rows, built_by_id=None):
    """Cohort summary of drum_linger_bars and exit lag vs the pro, from v1 pick rows."""
    built_by_id = built_by_id or {}
    pairs = [pair_linger_lag(r, built=built_by_id.get(r.get('id'))) for r in arm_rows if not r.get('error')]
    lags = [p['exit_lag'] for p in pairs if p.get('exit_lag') is not None]
    lingers = [p['drum_linger_bars'] for p in pairs if p.get('drum_linger_bars') is not None]
    over = [p['id'] for p in pairs if (p.get('drum_linger_bars') or 0) > 8.80]
    return dict(
        exit_lag_vs_pro=_summarize_nums(lags),
        drum_linger_bars=_summarize_nums(lingers),
        n_drum_linger_over_p95=len(over),
        drum_linger_over_p95=over,
        pairs=pairs,
    )
