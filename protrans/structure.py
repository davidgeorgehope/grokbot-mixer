"""Track phases (intro/build/drop/breakdown/outro) and breakdown/linger helpers.

Does not modify src2. Reads prepared st/*.json bar curves (drums/bass/low/all).
"""
from __future__ import annotations
import json, os
import numpy as np

BAR_SEC = 240.0 / 174.0  # 4/4 bar at 174 BPM (stretched prep)
REL_DB = 20.0

def load_bar(st_js):
    g = json.load(open(st_js))
    bar = g.get('bar') or {}
    drums = np.asarray(bar.get('drums') or bar.get('all') or [], float)
    bass = np.asarray(bar.get('bass') or bar.get('low') or drums, float)
    n = min(len(drums), len(bass))
    return dict(drums=drums[:n], bass=bass[:n], n=n, orig_bpm=g.get('orig_bpm'),
                dur=g.get('dur'), path=st_js)

def detect_breakdowns(bar, min_bars=4, drop_db=10.0, pre_window=16, active_db=-40.0):
    """Return [(start_bar, end_bar), ...] where drums or bass fall for min_bars.

    A bar is in a drop if drums or bass sit `drop_db` below the median of the
    previous `pre_window` bars, and that previous section was itself active
    (not already an intro/silence).
    """
    if isinstance(bar, dict) and 'drums' not in bar and 'bar' in bar:
        bar = load_bar(bar) if False else bar
    drums = np.asarray(bar['drums'] if isinstance(bar, dict) and 'drums' in bar else bar, float)
    if isinstance(bar, dict):
        drums = np.asarray(bar['drums'], float)
        bass = np.asarray(bar['bass'], float)
    else:
        bass = drums
    n = min(len(drums), len(bass))
    drums, bass = drums[:n], bass[:n]
    flags = np.zeros(n, dtype=bool)
    for i in range(n):
        lo = max(0, i - pre_window)
        if i - lo < 8:
            continue
        pre_d = float(np.median(drums[lo:i]))
        pre_b = float(np.median(bass[lo:i]))
        if pre_d < active_db and pre_b < active_db + 5:
            continue
        if drums[i] <= pre_d - drop_db or bass[i] <= pre_b - drop_db:
            flags[i] = True
    segs = []
    i = 0
    while i < n:
        if not flags[i]:
            i += 1
            continue
        j = i
        while j < n and flags[j]:
            j += 1
        if j - i >= min_bars:
            segs.append((int(i), int(j)))
        i = j
    # Extend each drop until drums/bass recover toward the pre-drop level
    # (so an outro that stays down is one breakdown, not a short 8-bar blip).
    ext=[]
    for s,e in segs:
        lo=max(0,s-pre_window)
        pre_d=float(np.median(drums[lo:s])) if s>lo else float(np.median(drums[:max(s,1)]))
        pre_b=float(np.median(bass[lo:s])) if s>lo else float(np.median(bass[:max(s,1)]))
        j=e
        while j<n and (drums[j] <= pre_d - drop_db*0.5 or bass[j] <= pre_b - drop_db*0.5):
            # recovered if BOTH are back
            if drums[j] > pre_d - drop_db*0.5 and bass[j] > pre_b - drop_db*0.5:
                break
            j += 1
        ext.append((s,j))
    # merge overlaps
    ext.sort()
    merged=[]
    for s,e in ext:
        if not merged or s > merged[-1][1]:
            merged.append([s,e])
        else:
            merged[-1][1]=max(merged[-1][1], e)
    return [(int(s), int(e)) for s,e in merged]

def next_breakdown(segs, after_bar):
    """First breakdown that starts at/after after_bar, or that after_bar is already inside."""
    for s, e in segs:
        if e <= after_bar:
            continue
        return (s, e)
    return None

def bars_into_breakdown(segs, play_start, play_end):
    """How many outgoing play bars sit inside a breakdown segment."""
    if play_end <= play_start:
        return 0.0, None
    best = None
    total = 0.0
    for s, e in segs:
        lo = max(play_start, s)
        hi = min(play_end, e)
        if hi > lo:
            total += hi - lo
            if best is None or s < best[0]:
                best = (s, e)
    return float(total), best

def fmt_time(sec):
    if sec is None: return None
    sec = max(0, float(sec))
    m = int(sec // 60); s = sec - 60*m
    return f"{m}:{s:04.1f}" if s < 10 else f"{m}:{s:05.1f}"


PHASES = ('intro', 'build', 'drop', 'breakdown', 'outro')

def _runs(mask, minlen=8):
    r = []; k = 0; n = len(mask)
    while k < n:
        if mask[k]:
            j = k
            while j < n and mask[j]:
                j += 1
            if j - k >= minlen:
                r.append([k, j])
            k = j
        else:
            k += 1
    m = []
    for a, b in r:
        if m and a - m[-1][1] < 4:
            m[-1][1] = b
        else:
            m.append([a, b])
    return m

def label_phases(bar):
    """Per-bar phase labels from drum/bass energy and detected breakdowns."""
    if isinstance(bar, str):
        bar = load_bar(bar)
    drums = np.asarray(bar['drums'], float)
    bass = np.asarray(bar['bass'], float)
    n = min(len(drums), len(bass))
    if n == 0:
        return []
    drums, bass = drums[:n], bass[:n]
    brks = detect_breakdowns(bar)
    loud_b = float(np.percentile(bass, 80))
    loud_d = float(np.percentile(drums, 80))
    drop_mask = (bass > loud_b - 6.0) & (drums > loud_d - 10.0)
    for s, e in brks:
        drop_mask[max(0, s):min(n, e)] = False
    drop_runs = _runs(drop_mask, 8)
    labels = ['intro'] * n
    for s, e in drop_runs:
        labels[s:e] = ['drop'] * (e - s)
    last_drop_end = max((e for s, e in drop_runs), default=0)
    for s, e in brks:
        s2, e2 = max(0, s), min(n, e)
        later_drop = any(ds >= e2 - 2 for ds, de in drop_runs)
        name = 'breakdown' if later_drop else 'outro'
        labels[s2:e2] = [name] * (e2 - s2)
    first_drop = next((i for i, p in enumerate(labels) if p == 'drop'), None)
    quiet_thr = max(float(np.percentile(drums, 30)), -48.0)
    if first_drop is None:
        i = 0
        while i < n and drums[i] < quiet_thr and bass[i] < quiet_thr + 8:
            i += 1
        for j in range(i, n):
            if labels[j] == 'intro':
                labels[j] = 'outro' if j > n * 0.6 else 'build'
    else:
        i = 0
        while i < first_drop and drums[i] < quiet_thr and bass[i] < quiet_thr + 8:
            i += 1
        for j in range(0, i):
            if labels[j] not in ('drop', 'breakdown', 'outro'):
                labels[j] = 'intro'
        for j in range(i, first_drop):
            if labels[j] not in ('drop', 'breakdown', 'outro'):
                labels[j] = 'build'
    for i in range(last_drop_end, n):
        if labels[i] in ('intro', 'build'):
            labels[i] = 'outro'
    seen_drop = False
    for i in range(n):
        if labels[i] == 'drop':
            seen_drop = True
        elif seen_drop and labels[i] == 'intro':
            labels[i] = 'build'
    return labels

def phase_at(labels, bar):
    if not labels:
        return 'intro'
    i = int(round(float(bar)))
    i = max(0, min(len(labels) - 1, i))
    return labels[i]

def first_drop_bar(labels, after=0):
    after = max(0, int(round(float(after))))
    for i in range(after, len(labels)):
        if labels[i] == 'drop':
            return i
    return None

def phase_spans(labels):
    spans = []
    i = 0
    n = len(labels)
    while i < n:
        j = i + 1
        while j < n and labels[j] == labels[i]:
            j += 1
        spans.append((labels[i], i, j))
        i = j
    return spans

def _bar(v):
    """a bar number from a window field: int, float, numpy scalar, or the engine's ('loopB', q) / [e, p] forms"""
    if isinstance(v, (list, tuple)):
        nums = [x for x in v if isinstance(x, (int, float, np.integer, np.floating)) and not isinstance(x, bool)]
        if not nums:
            raise TypeError(f'no bar number in window field {v!r}')
        return int(nums[0])
    return int(v)

def parse_window(win):
    """(kind, out_end, loop_phrase, in_begin, X) from a flat [kind, e, p, ib, X] window or the nested
    [kind, (e, p), ib, X] / ('loopB', q) forms mix_simple uses internally. 2026-11-11 RCA: int(list) here raised a
    TypeError on loop windows and recreate.py swallowed it, so loop families silently got phase cost 0."""
    win = list(win)
    if len(win) == 4 and isinstance(win[1], (list, tuple)):
        kind, (e, p), ib, X = win[0], win[1], win[2], win[3]
    elif len(win) == 5:
        kind, e, p, ib, X = win
        if isinstance(e, (list, tuple)) and len(e) == 2 and p is None:
            e, p = e
    else:
        raise ValueError(f'window must be [kind, e, p, ib, X], got {win!r}')
    return kind, _bar(e), (None if p is None else _bar(p)), _bar(ib), _bar(X)

def map_window_bars(win):
    """Approximate outgoing/incoming source bars at mixin, along the blend, and at cut.

    win = [kind, out_end, loop, in_begin, X]. Loop families use the repeated
    phrase; nothing is rejected here, this is only for soft scoring.
    """
    kind, e, p, ib, X = parse_window(win)
    def out_at(k):
        if kind in ('la', 'ab', 'lx') and p is not None:
            return int(p) + (k % 16)
        return (e - X) + k
    def in_at(k):
        if kind in ('lb', 'ab'):
            return ib + (k % 16)
        return ib + k
    return dict(mixin_out=out_at(0), mixin_in=in_at(0),
                cut_out=out_at(max(X - 1, 0)), cut_in=in_at(max(X - 1, 0)),
                out_at=out_at, in_at=in_at, X=X, e=e, ib=ib, kind=kind)

def window_landmarks(win, lab_a, lab_b, segs_a=None):
    """Phase labels and duration features implied by a planned window."""
    m = map_window_bars(win)
    drop_b = first_drop_bar(lab_b, after=0)
    # If the window starts after (or in) the first drop, use the next drop.
    if drop_b is not None and drop_b < m['mixin_in'] - 2:
        drop_b = first_drop_bar(lab_b, after=m['mixin_in'])
    k_drop = None
    if drop_b is not None:
        # bar index along blend where incoming hits that drop (linear / looped)
        if m['kind'] in ('lb', 'ab'):
            # drop only if the looped phrase contains it, else after blend
            k_drop = 0 if (m['ib'] <= drop_b < m['ib'] + 16) else m['X']
        else:
            k_drop = drop_b - m['ib']
    out_at_drop = m['out_at'](k_drop) if k_drop is not None else None
    in_at_drop = m['in_at'](k_drop) if k_drop is not None else None
    mixin_pair = (phase_at(lab_a, m['mixin_out']), phase_at(lab_b, m['mixin_in']))
    if out_at_drop is not None:
        drop_pair = (phase_at(lab_a, out_at_drop), phase_at(lab_b, in_at_drop))
    else:
        drop_pair = None
    cut_pair = (phase_at(lab_a, m['cut_out']), phase_at(lab_b, m['cut_in']))
    overflow = 0.0
    brk = None
    if segs_a:
        brk = next_breakdown(segs_a, m['mixin_out'])
        if brk:
            overflow = max(0.0, (m['e'] if m['kind'] not in ('la', 'ab', 'lx') else m['cut_out'] + 1) - brk[0])
            # for natural windows play_end is e; overflow = bars past breakdown start
            overflow = max(0.0, float(m['e']) - brk[0]) if m['kind'] == 'n' else max(0.0, float(m['cut_out']) + 1 - brk[0])
    # linger: outgoing bars after incoming drop (or after mixin if no drop)
    if k_drop is not None:
        tail_after_drop = float(m['X'] - k_drop)
    else:
        tail_after_drop = float(m['X'])
    return dict(mixin_pair=mixin_pair, drop_pair=drop_pair, cut_pair=cut_pair,
                mixin_out=m['mixin_out'], mixin_in=m['mixin_in'],
                drop_b=drop_b, k_drop=k_drop, out_at_drop=out_at_drop,
                overflow_bars=float(overflow), tail_after_drop=tail_after_drop,
                brk=brk, X=m['X'])

_PRIORS = None

def load_priors(path=None):
    global _PRIORS
    if path is None:
        path = os.path.join(os.path.dirname(__file__), 'results', 'phase_priors.json')
    if _PRIORS is not None and _PRIORS.get('_path') == path:
        return _PRIORS
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    d['_path'] = path
    _PRIORS = d
    return d

def pair_key(pair):
    if not pair or pair[0] is None or pair[1] is None:
        return None
    return f'{pair[0]}+{pair[1]}'

def _neglog(priors_section, key):
    if not priors_section or not key:
        return 0.0
    p = float(priors_section.get(key) or priors_section.get('_floor') or 1e-3)
    pmax = float(priors_section.get('_pmax') or max(priors_section.get(k, 0) for k in priors_section if not k.startswith('_')) or 1.0)
    p = max(p, 1e-6); pmax = max(pmax, p)
    return float(-np.log(p) + np.log(pmax))  # 0 at the most common pairing

def window_phase_cost(win, lab_a, lab_b, segs_a=None, priors=None,
                      phase_pref_w=1.0, linger_pen_w=0.0, breakdown_pen_w=0.0):
    """Soft, never-infinite cost. Frequent pro pairings are cheaper; nothing is banned."""
    if priors is None:
        priors = load_priors()
    lm = window_landmarks(win, lab_a, lab_b, segs_a)
    costs = []
    for section, pair in (('mixin', lm['mixin_pair']),
                          ('in_drop', lm['drop_pair']),
                          ('out_cut', lm['cut_pair'])):
        if pair is None:
            continue
        sec = (priors or {}).get(section) or {}
        costs.append(_neglog(sec, pair_key(pair)))
    phase_c = float(np.mean(costs)) if costs else 0.0
    linger_grace = float((priors or {}).get('linger_grace_bars') or 8)
    brk_grace = float((priors or {}).get('overflow_grace_bars') or 4)
    linger_c = max(0.0, float(lm['tail_after_drop']) - linger_grace) / 16.0
    brk_c = max(0.0, float(lm['overflow_bars']) - brk_grace) / 8.0
    # Contextual: overflow into an outgoing breakdown is expected when the
    # pairing itself is common (e.g. breakdown+breakdown fade). Shrink the
    # extra penalty by how typical that cut pairing is.
    cut_nl = _neglog((priors or {}).get('out_cut') or {}, pair_key(lm['cut_pair']))
    typical = 1.0 / (1.0 + cut_nl)  # ~1 when pairing is the mode
    brk_c = brk_c * (1.0 - 0.75 * typical)
    total = (phase_pref_w * phase_c) + (linger_pen_w * linger_c) + (breakdown_pen_w * brk_c)
    lm['phase_c'] = phase_c
    lm['linger_c'] = linger_c
    lm['brk_c'] = brk_c
    lm['total'] = float(total)
    return float(total), lm
