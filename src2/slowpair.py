"""SLOWPAIR (2026-11-20 midnight research, off by default): pair-aware hard slowdown / half-time handling.

the listener's note: bringing a mix in over a hard slowdown sounds weird. The earlier SLOWDOWN=1 flag only
penalises a blend that *starts* inside an outgoing outro / in-drop slowdown, treats every 8-bar
snare dip the same, and never looks at the incoming track. This flag is tighter and pair-aware.

Hard spans (pre-declared, not fitted to scores):
  - half-time sections from protrans/replica/halftime/halftime_tg.py (the detector's own min length is 8)
  - slowdown.py sections of at least HARD_BARS (16) that are outro, in-drop, or breakdown
  - intro-only slowdowns of at least INTRO_HARD_BARS (24)

Clash (the thing that sounds weird):
  A: the blend starts inside an outgoing hard outro or in-drop span, or at least
     CASE_A_COVER (12) bars of the window sit in one. Starting a few bars before the
     slowdown (the 2026-11-19 Ghetto Blaster fix, 10 bars of overlap) is allowed.
     Outgoing breakdowns stay allowed (pros use them; SLOWDOWN already left them alone).
  B: overlap with an incoming hard span is >= OVERLAP (8) bars, AND the outgoing is still
     hot (at least half of the outgoing window sits inside a drop). Outro-over-intro stays
     the safe default when the outgoing has already left its drop. The payoff guard only
     applies when the alternative exits earlier than the default.

The hook in protrans/recreate.py (not mix_simple) adds COST (1.0) to a clashing family's pick
cost and nominates one 'slowpair' alternative from already-scored engine candidates:
  A: latest same-length natural exit whose Case A overlap is < OVERLAP and whose blend start
     is at or after the last 8 bars of A's last drop (payoff guard)
  B only: same exit if possible, a cue with Case B overlap < OVERLAP, preferring B's drop in
     the window
SLOWPAIR_EXIT=1 (off by default) is the exit-only arm: only Case A is a clash, so cue moves
are never applied. SLOWPAIR_COND=1 (off by default) is the conditional arm: Case A only
fires when the outgoing track ends with a hard outro after the last drop (not an in-drop
slowdown) and the incoming track has a drop that can land in the blend — the Ghetto Blaster
shape, where a DJ leaves in the last drop rather than riding the hard outro. All flags stay
out of rules.json.
Engine-cost slack is PEN_SLACK (15), same idea as CONSONANCE, except a same-exit Case B
cue move is allowed to lose the 300 outro-over-intro engine bonus. Not in rules.json.
"""
from __future__ import annotations
import os, json
from functools import lru_cache

HARD_BARS = 16
INTRO_HARD_BARS = 24
OVERLAP = 8
CASE_A_COVER = 12
COST = 1.0
PEN_SLACK = 15.0
SRC2 = '/workspace/mixes/src2'
HT = '/workspace/mixes/protrans/replica/halftime'


def flag_on(v=None):
    v = os.environ.get('SLOWPAIR') if v is None else v
    return str(v or '').strip().lower() not in ('', '0', 'false', 'none', 'no', 'off')


def exit_only(v=None):
    """SLOWPAIR_EXIT=1: Case A (exit moves) only; Case B cue moves are off."""
    v = os.environ.get('SLOWPAIR_EXIT') if v is None else v
    return str(v or '').strip().lower() not in ('', '0', 'false', 'none', 'no', 'off')


def allowed_cases(v=None):
    return ('A',) if exit_only(v) or cond_on(v) else ('A', 'B')


def cond_on(v=None):
    """SLOWPAIR_COND=1: Case A only on the drop-leave / hard-outro shape."""
    v = os.environ.get('SLOWPAIR_COND') if v is None else v
    return str(v or '').strip().lower() not in ('', '0', 'false', 'none', 'no', 'off')


def incoming_drop_can_land(b_sec, X=16):
    """True if some incoming cue lets a drop start sit in an X-bar blend (at least 4 bars)."""
    starts = []
    if (b_sec or {}).get('drop1') is not None:
        starts.append(int(b_sec['drop1']))
    for x, _y in (b_sec or {}).get('drops') or []:
        starts.append(int(x))
    X = int(X or 16)
    for d1 in starts:
        # ib = max(0, d1 - (X - 4)) places the drop in the window when d1 >= 0
        if d1 >= 0:
            return True
    return False


def looks_like_drop_leave(a_sec, a_spans, b_sec, X=16):
    """Outgoing ends with a hard outro after the last drop (not an in-drop slowdown),
    and the incoming has a drop that can land in the blend."""
    drops = list((a_sec or {}).get('drops') or [])
    last_end = drops[-1][1] if drops else None
    pure_outro = False
    for s in a_spans or []:
        labs = set(s.get('labels') or [])
        if 'outro' in labs and 'in_drop' not in labs:
            if last_end is None or int(s['start']) >= int(last_end) - 2:
                pure_outro = True
                break
    return bool(pure_outro and incoming_drop_can_land(b_sec, X=X))


def overlap_bars(s0, e0, s1, e1):
    return max(0, min(e0, e1) - max(s0, s1))


def classify_span(a, b, drops, music_end):
    labels = set()
    first = min((x for x, y in drops), default=None)
    last_end = max((y for x, y in drops), default=None)
    if first is not None and b <= first + 2:
        labels.add('intro')
    if music_end is not None and a >= music_end - 32:
        labels.add('outro')
    if last_end is not None and a >= last_end - 8:
        labels.add('outro')
    if any(not (b <= x or a >= y) for x, y in drops):
        labels.add('in_drop')
    for i in range(len(drops) - 1):
        if a >= drops[i][1] - 2 and b <= drops[i + 1][0] + 2:
            labels.add('breakdown')
    if not labels:
        labels.add('other')
    return labels


def is_hard(labels, length, kind='slow'):
    if kind == 'ht':
        return length >= 8
    if length >= INTRO_HARD_BARS and 'intro' in labels:
        return True
    if length >= HARD_BARS and (labels - {'intro', 'other'}):
        return True
    return False


def hard_spans(slow=None, ht=None, sec=None):
    """Build the hard-span list from already-loaded detector output (no I/O)."""
    drops = list((sec or {}).get('drops') or [])
    end = (sec or {}).get('music_end')
    out = []
    for a, b in ht or []:
        labs = classify_span(a, b, drops, end) | {'ht'}
        if is_hard(labs, b - a, 'ht'):
            out.append(dict(start=int(a), end=int(b), kind='ht', labels=sorted(labs)))
    for a, b in slow or []:
        labs = classify_span(a, b, drops, end)
        if is_hard(labs, b - a, 'slow'):
            out.append(dict(start=int(a), end=int(b), kind='slow', labels=sorted(labs)))
    out.sort(key=lambda s: (s['start'], s['end']))
    return out


def win_ranges(win):
    kind, e, p, ib, X = win[0], win[1], win[2], win[3], int(win[4])
    if isinstance(e, (list, tuple)):
        ea = int(e[0])
    else:
        ea = int(e)
    ib = int(ib)
    return kind, ea - X, ea, ib, ib + X, X, ea, ib


def outgoing_hot(a0, a1, sec):
    drops = list((sec or {}).get('drops') or [])
    if a1 <= a0:
        return False
    n = sum(1 for k in range(int(a0), int(a1)) if any(x <= k < y for x, y in drops))
    return n >= 0.5 * (a1 - a0)


def _hits(spans, s, e, want_labels=None):
    hits = []
    for sp in spans:
        o = overlap_bars(s, e, sp['start'], sp['end'])
        if o < OVERLAP:
            continue
        labs = set(sp['labels'])
        if want_labels is not None and labs.isdisjoint(want_labels):
            continue
        hits.append(dict(span=sp, overlap=o))
    return hits


def case_a_hits(spans, a0, a1):
    """Start-inside a hard outro/in-drop, or cover of at least CASE_A_COVER bars."""
    hits = []
    for sp in spans:
        if set(sp['labels']).isdisjoint({'outro', 'in_drop'}):
            continue
        o = overlap_bars(a0, a1, sp['start'], sp['end'])
        start_inside = sp['start'] <= a0 < sp['end']
        if start_inside or o >= CASE_A_COVER:
            hits.append(dict(span=sp, overlap=o, start_inside=start_inside))
    return hits


def window_clash(win, a_spans, b_spans, a_sec, cases=None, b_sec=None, require_drop_leave=None):
    """Return a clash dict or None. Pure; no I/O.

    `cases` defaults to allowed_cases() (both A and B, or only A when SLOWPAIR_EXIT=1
    or SLOWPAIR_COND=1). When require_drop_leave is true (default: cond_on()), Case A
    only counts if looks_like_drop_leave(a_sec, a_spans, b_sec).
    """
    kind, a0, a1, b0, b1, X, ea, ib = win_ranges(win)
    allow = set(cases if cases is not None else allowed_cases())
    if require_drop_leave is None:
        require_drop_leave = cond_on()
    found = {}
    a_hits = case_a_hits(a_spans, a0, a1)
    if a_hits and 'A' in allow:
        if require_drop_leave and not looks_like_drop_leave(a_sec, a_spans, b_sec, X=X):
            a_hits = []
        if a_hits:
            found['A'] = a_hits
    # Case B: incoming hard span under a still-hot outgoing drop.
    if 'B' in allow and outgoing_hot(a0, a1, a_sec):
        b_hits = _hits(b_spans, b0, b1, want_labels=None)
        if b_hits:
            found['B'] = b_hits
    if not found:
        return None
    return dict(cases=sorted(found), A=found.get('A'), B=found.get('B'))


def payoff_floor(sec):
    drops = list((sec or {}).get('drops') or [])
    return (drops[-1][1] - 8) if drops else 0


def _engine_cost(cs, win):
    if not cs or win is None:
        return None
    kind, a0, a1, b0, b1, X, ea, ib = win_ranges(win)
    hits = []
    for c in cs:
        w = c['win']
        if w[0] != kind or int(w[4]) != X:
            continue
        we = int(w[1][0] if isinstance(w[1], (list, tuple)) else w[1])
        if we == ea and int(w[3]) == ib:
            hits.append(c)
    return min(c['cost'] for c in hits) if hits else None


def pick_alt(cs, default_win, a_spans, b_spans, a_sec, b_sec, slack=PEN_SLACK, cases=None, require_drop_leave=None):
    """Choose one already-scored natural alternative, or None."""
    clash = window_clash(default_win, a_spans, b_spans, a_sec, cases=cases, b_sec=b_sec, require_drop_leave=require_drop_leave)
    if not clash:
        return None, dict(reason='default_ok')
    kind, a0, a1, b0, b1, X, ea, ib = win_ranges(default_win)
    ref = _engine_cost(cs, default_win)
    lde = payoff_floor(a_sec)
    d1 = (b_sec or {}).get('drop1')
    pool = []
    for c in cs or []:
        w = c['win']
        if w[0] != 'n' or int(w[4]) != X:
            continue
        we = int(w[1])
        wi = int(w[3])
        # Payoff only when the alternative exits earlier than the default (Case A).
        # A same-exit cue change must be allowed to keep the default's own start.
        if we < ea and we - X < lde:
            continue
        # Same-exit Case B cue moves often lose the 300 outro-over-intro engine bonus
        # (the new cue sits past the intro). Slack stays in force for exit changes.
        if not (we == ea and 'B' in clash['cases'] and 'A' not in clash['cases']):
            if ref is not None and c['cost'] > ref + slack:
                continue
        if window_clash(w, a_spans, b_spans, a_sec, cases=cases, b_sec=b_sec, require_drop_leave=require_drop_leave):
            continue
        pool.append(c)
    if not pool:
        return None, dict(reason='no_alt', clash=clash)
    case_a = 'A' in clash['cases']

    def key(c):
        we, wi = int(c['win'][1]), int(c['win'][3])
        drop_in = 1 if (d1 is not None and wi <= d1 <= wi + X - 4) else 0
        if case_a:
            return (we, drop_in, -c['cost'])
        return (int(we == ea), drop_in, -abs(we - ea), -c['cost'])

    best = max(pool, key=key)
    return list(best['win']), dict(reason='ok', clash=clash, n_alt=len(pool), engine=best['cost'])


def rerank(scored, cs, a_spans, b_spans, a_sec, b_sec, base_cost=None, cases=None, require_drop_leave=None):
    """scored: list of (cost, dict with fam/win). Returns (new_scored, info)."""
    if not scored:
        return scored, dict(reason='no_scored')
    default = min(scored, key=lambda x: x[0])
    def_win = list(default[1]['win'])
    alt, info = pick_alt(cs, def_win, a_spans, b_spans, a_sec, b_sec, cases=cases, require_drop_leave=require_drop_leave)
    info['default_fam'] = default[1].get('fam')
    info['default_win'] = def_win
    scored = list(scored)
    if alt is not None and not any(list(c['win']) == list(alt) for _, c in scored):
        cost = base_cost(alt, 'slowpair') if base_cost else default[0]
        scored.append((cost, dict(fam='slowpair', win=list(alt), env={})))
        info['nominated'] = list(alt)
    new = []
    terms = {}
    for cost, c in scored:
        cl = window_clash(c['win'], a_spans, b_spans, a_sec, cases=cases, b_sec=b_sec, require_drop_leave=require_drop_leave)
        t = COST if cl else 0.0
        terms[c.get('fam', '?')] = dict(term=t, base=round(float(cost), 4), clash=cl is not None, win=list(c['win']))
        new.append((cost + t, c))
    new.sort(key=lambda x: x[0])
    pick = new[0][1]
    info['pick_fam'] = pick.get('fam')
    info['pick_win'] = list(pick['win'])
    info['changed'] = list(pick['win']) != def_win or pick.get('fam') != default[1].get('fam')
    info['terms'] = terms
    return new, info


# --- track I/O, used by the recreate hook; tests inject spans and skip this ---

def _sections(yt):
    p = os.path.join(SRC2, 'st', yt + '.sections.json')
    return json.load(open(p)) if os.path.exists(p) else {}


@lru_cache(maxsize=256)
def spans_for(yt):
    sys_path_inserted = False
    import sys
    if HT not in sys.path:
        sys.path.insert(0, HT)
        sys_path_inserted = True
    try:
        import slowdown as SD
        import halftime_tg as H
        P = SD.profile(yt)
        slow = (P or {}).get('sections') or []
        try:
            ht = H.sections(yt) or []
        except Exception:
            ht = []
        return tuple((s['start'], s['end'], s['kind'], tuple(s['labels']))
                     for s in hard_spans(slow, ht, _sections(yt)))
    finally:
        pass


def _span_dicts(yt):
    return [dict(start=a, end=b, kind=k, labels=list(labs)) for a, b, k, labs in spans_for(yt)]


def plan_pair(cs, default_win, a, b, scored=None, base_cost=None, cases=None, require_drop_leave=None):
    """High-level hook used by recreate.py. a, b are YouTube ids."""
    if cases is None:
        cases = allowed_cases()
    if require_drop_leave is None:
        require_drop_leave = cond_on()
    a_sec, b_sec = _sections(a), _sections(b)
    a_sp, b_sp = _span_dicts(a), _span_dicts(b)
    if scored is None:
        alt, info = pick_alt(cs, default_win, a_sp, b_sp, a_sec, b_sec, cases=cases, require_drop_leave=require_drop_leave)
        info['a_hard'] = a_sp
        info['b_hard'] = b_sp
        info['cases'] = list(cases)
        info['drop_leave'] = looks_like_drop_leave(a_sec, a_sp, b_sec)
        return alt, info
    new, info = rerank(scored, cs, a_sp, b_sp, a_sec, b_sec, base_cost=base_cost, cases=cases, require_drop_leave=require_drop_leave)
    info['a_hard'] = a_sp
    info['b_hard'] = b_sp
    info['cases'] = list(cases)
    info['drop_leave'] = looks_like_drop_leave(a_sec, a_sp, b_sec)
    return new, info
