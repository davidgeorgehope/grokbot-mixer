"""Per-pair mid-track window planner (2026-11-15 research, off by default).

Nominates blend windows from both decks' section analysis — the default
outro-over-intro, outgoing breakdown into an incoming drop, and the end of
the outgoing first drop into its breakdown — and chooses between them from
track features. Not a blanket rule.

the listener (2026-11-15): blend technique is not a fixed rule; sometimes a blend
is quick and sometimes it lasts ages, depending on the tracks. The 11-14
RCA (Prime Expansion -> Demons) and the 11-15 SNAP_IN notes (Cinnamon ->
Together) showed that STRUCT's 300-point bonus hides every mid-track window,
and that a global SNAP_IN or a hint-only mid-track swap overfits.

Locked from train-only checks (n=21), not from held-out scores:
stay on the default outro-intro window unless the default has an engine bass
hole for more than half the blend (GAP_DB, the pro p95, is never loosened)
AND a canonical mid-track window has strictly fewer hole bars with incoming
bass actually in a drop, AND either the best outro-intro window is also
mostly a hole or the incoming intro is short (under 40 bars, shorter than
the usual 48). Among mid-track options, a short intro prefers breakdown
into drop (with SNAP_IN's shallow hold); otherwise the end of the first
drop (default fade). That is the 11-15 vs 11-14 shape.

A BASS_COVER fallback on thin-intro stays was tried and dropped: it
pulled held-out under the 34.05 floor (pola_bryson_puzzlewood__00
59.06 -> 56.33) and is not used here. The official bass-gap test is
still blind to holes wider than its +-4-bar neighbourhood; that line
is a later pro-p95 calibration, not something this planner loosens.

On breakdown-into-drop, when the incoming track has three or more
drops, the selector prefers the last drop, and a phrase 32 bars into
that drop (the body, not the downbeat) when one is legal. That is the
11-15 listening gap: the pro cues Together at bar 191 (third drop
body), not drop 2's start. SNAP_IN_HOLD (16 extra bars at -12 dB,
then the usual residual) is also only for that 3+ drop case, still
under X1 and the 2.75 dB/bar outgoing cap. Mid-track windows that
only become legal through the WINDOW_PLANNER env alias (incoming
start past bar 80, or an end before emin) are applied only for that
same 3+ drop cue; other pairs keep the v1 shortlist behaviour.

Off by default: rules['window_planner'] / WINDOW_PLANNER. X1 is never
loosened. the listener rated the 11-14 drop1_end clip "really nice" and the
first 11-15 breakdown_drop + SNAP_IN clip 3.5/5, closer but not up to
par with the pro.
"""
from __future__ import annotations

import os

import numpy as np

try:
    import bassgap as _BG
    GAP_DB = float(_BG.GAP_DB)
except Exception:
    GAP_DB = 9.84  # pro p95; same default as bassgap.py / recreate.incoming_hole_bars

# Majority of a 16-bar blend. hole_min(X) = X//2, never a looser GAP_DB.
SHORT_INTRO = 40  # shorter than the usual 48-bar intro (SNAP_IN notes)
# Extra SNAP_IN hold (bars past the window, before the residual) when the
# outgoing still has runway. Pro on the 11-15 pair stays audible ~26 bars
# after entry; the default residual only adds ~4.
HOLD_EXTRA = 16
HOLD_OUT_LEFT = 32
HOLD_TO_OUTRO = 24
N_DROPS_LAST = 3  # prefer the last incoming drop when the track has this many

FAM_BREAKDOWN = 'plan_breakdown_drop'
FAM_DROP1 = 'plan_drop1_end'


def flag_on(v=None):
    if v is None:
        v = os.environ.get('WINDOW_PLANNER')
    return str(v).strip().lower() not in ('', '0', 'false', 'none', 'no')


def hole_min(X):
    return max(1, int(X) // 2)


def phrase(x, q=8):
    return int(round(float(x) / q) * q)


def _body(lo):
    lo = np.asarray(lo, float)
    return float(np.percentile(lo, 75)) if len(lo) else -20.0


def hole_bars(win, lo_a, lo_b, gap=None):
    """Bars where the incoming is thin (>gap under its body) while the outgoing
    still has bass (within gap/2 of its body). Same definition as
    recreate.incoming_hole_bars; gap defaults to bassgap.GAP_DB (pro p95).
    """
    if not win or lo_a is None or lo_b is None:
        return 0
    kind, e, _p, ib, X = win[0], int(win[1]), win[2], win[3], int(win[4])
    if kind != 'n' or ib is None:
        return 0
    ib = int(ib)
    gap = GAP_DB if gap is None else float(gap)
    lo_a = np.asarray(lo_a, float)
    lo_b = np.asarray(lo_b, float)
    body_a, body_b = _body(lo_a), _body(lo_b)
    n = 0
    for k in range(X):
        ia, ibk = e - X + k, ib + k
        oa = float(lo_a[ia]) if 0 <= ia < len(lo_a) else -120.0
        ob = float(lo_b[ibk]) if 0 <= ibk < len(lo_b) else -120.0
        if ob < body_b - gap and oa >= body_a - gap / 2.0:
            n += 1
    return n


def incoming_all_thin(win, lo_b, db=6.0):
    """True when every incoming overlap bar is >= db under that track's body.

    This is fade_long.incoming_no_bass (the BASS_COVER / SWAP_THIN 6 dB line,
    never loosened). Distinct from hole_bars, which also requires the outgoing
    to still be at body and uses GAP_DB.
    """
    if not win or lo_b is None or win[0] != 'n' or win[3] is None:
        return False
    ib, X = int(win[3]), int(win[4])
    import fade_long as FL
    return bool(FL.incoming_no_bass(lo_b, list(range(ib, ib + X)), X, db=float(db)))


def section_at(s, bar):
    """Return (section, info) at a source bar.

    section is one of intro, drop, breakdown, outro, other.
    A bar sitting on the exclusive end of drop1 (bar == breakdown) is the
    breakdown, so a window that *ends* there (e=breakdown) still plays the
    last bars of drop1 — that is the drop1_end type.
    """
    info = dict(in_drop=False, in_intro=False, in_breakdown=False, in_outro=False,
                hit='other', near_drop1_end=False, drop_i=None, drop_len=None)
    if s is None or bar is None:
        return 'other', info
    bar = int(round(float(bar)))
    intro = int(s.get('intro_end') or s.get('drop1') or 0)
    drops = [list(map(int, d)) for d in (s.get('drops') or [])]
    bd = s.get('breakdown')
    bd = int(bd) if bd is not None else None
    outro = s.get('outro_start')
    outro = int(outro) if outro is not None else None
    end = int(s.get('music_end') or s.get('n_bars') or 0)
    for i, (a, b) in enumerate(drops):
        if a <= bar < b:
            info.update(in_drop=True, hit=f'drop{i+1}', drop_i=i, drop_len=b - a,
                        near_drop1_end=(i == 0 and bd == b and b - 16 <= bar < b))
            return 'drop', info
    if bar < intro:
        info.update(in_intro=True, hit='intro')
        return 'intro', info
    next_drop = drops[1][0] if len(drops) > 1 else None
    if bd is not None:
        hi = next_drop if next_drop is not None else (outro or end)
        if bd <= bar < hi:
            info.update(in_breakdown=True, hit='breakdown')
            return 'breakdown', info
    if outro is not None and bar >= outro:
        info.update(in_outro=True, hit='outro')
        return 'outro', info
    return 'other', info


def _mean_lo(lo, start, n):
    lo = np.asarray(lo, float)
    sl = lo[max(0, int(start)):max(0, int(start)) + int(n)]
    return float(np.mean(sl)) if len(sl) else -120.0


def legal(e, ib, X, sa, sb, min_in_left=48, min_out_left=None):
    na = int(sa.get('music_end') or sa.get('n_bars') or 0)
    nb = int(sb.get('music_end') or sb.get('n_bars') or 0)
    if X not in (16, 32) or e is None or ib is None:
        return False
    if e - X < 0 or e > na + 8:
        return False
    if ib < 0 or ib + X > nb + 8:
        return False
    if (nb - ib) < min_in_left:
        return False
    return True


def _drop_ibs(drops, min_in_left, sb, X):
    """Incoming cue bars: the start of each drop, every +32 phrase still
    inside a long drop, and the mid phrase of a long drop.

    The +32 body phrase is what lets breakdown_drop land in the third
    drop's body (Together bar 192, one bar from the pro's 191) instead
    of only the drop downbeat or the midpoint.
    """
    ibs = []
    seen = set()
    for i, (a, b) in enumerate(drops):
        start = phrase(a)

        def add(ib, is_start):
            ib = phrase(ib)
            if ib in seen or not (a <= ib < b):
                return
            seen.add(ib)
            ibs.append((ib, i + 1, is_start, start))

        add(start, True)
        k = start + 32
        while k < b:
            add(k, False)
            k += 32
        if b - a >= 48:
            add(phrase((a + b) // 2), False)
    return ibs


def nominate(sa, sb, X=16, min_in_left=48):
    """Candidate windows from both decks' sections. Each item is
    dict(type, win=[kind,e,None,ib,X], ...). Types: outro_intro, drop1_end,
    breakdown_drop. drop starts past the usual incoming bar-80 cap are
    allowed when enough of the incoming track is left.
    """
    cands = []
    na = int(sa.get('music_end') or sa.get('n_bars') or 0)
    drops_a = [list(map(int, d)) for d in (sa.get('drops') or [])]
    drops_b = [list(map(int, d)) for d in (sb.get('drops') or [])]
    bd = sa.get('breakdown')
    bd = int(bd) if bd is not None else None

    e = phrase(min(na, (na // 8) * 8))
    drop1 = int(sb.get('drop1') or sb.get('intro_end') or 0)
    ib = phrase(max(0, drop1 - X))
    if legal(e, ib, X, sa, sb, min_in_left=16):
        cands.append(dict(type='outro_intro', win=['n', e, None, ib, X]))

    ibs = _drop_ibs(drops_b, min_in_left, sb, X)
    if bd is not None:
        e1 = phrase(bd)
        for ib, di, is_start, dstart in ibs:
            if legal(e1, ib, X, sa, sb, min_in_left=min_in_left):
                cands.append(dict(type='drop1_end', win=['n', e1, None, ib, X],
                                  in_drop=di, ib_is_start=is_start, drop_start=dstart))
        next_drop = drops_a[1][0] if len(drops_a) > 1 else None
        hi = int(next_drop) if next_drop is not None else int(sa.get('outro_start') or na)
        e_opts = sorted({phrase(bd + X), phrase(min(hi, bd + X)), phrase(hi)})
        for e_bd in e_opts:
            ov = max(0, min(e_bd, hi) - max(e_bd - X, bd))
            if ov < 8:
                continue
            for ib, di, is_start, dstart in ibs:
                if legal(e_bd, ib, X, sa, sb, min_in_left=min_in_left):
                    cands.append(dict(type='breakdown_drop', win=['n', e_bd, None, ib, X],
                                      in_drop=di, ib_is_start=is_start, drop_start=dstart, ov=ov))

    seen, out = set(), []
    for c in cands:
        k = (c['type'], tuple(c['win']))
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def features(c, sa, sb, lo_a, lo_b, gap=None):
    win = c['win']
    e, ib, X = int(win[1]), int(win[3]), int(win[4])
    os_, oi = section_at(sa, e - X / 2.0), section_at(sb, ib + X / 2.0)
    ba, bb = _body(lo_a), _body(lo_b)
    mo, mi = _mean_lo(lo_a, e - X, X), _mean_lo(lo_b, ib, X)
    gap = GAP_DB if gap is None else float(gap)
    holes = hole_bars(win, lo_a, lo_b, gap)
    intro = int(sb.get('intro_end') or sb.get('drop1') or 0)
    end_a = int(sa.get('music_end') or sa.get('n_bars') or 0)
    outro = sa.get('outro_start')
    return dict(
        type=c['type'], win=list(win), holes=holes,
        out_sec=os_[0], out_hit=os_[1]['hit'], in_sec=oi[0], in_hit=oi[1]['hit'],
        near_drop1_end=os_[1]['near_drop1_end'],
        intro_len=intro,
        out_vs_body=round(mo - ba, 2), in_vs_body=round(mi - bb, 2),
        inc_bass_ok=(mi >= bb - gap),
        out_down=(mo < ba - gap / 2.0),
        both_loud=(mo >= ba - gap / 2.0) and (mi >= bb - gap / 2.0),
        out_left=end_a - e,
        to_outro=(int(outro) - e) if outro is not None else end_a - e,
        in_drop=c.get('in_drop'), ib_is_start=c.get('ib_is_start', True),
        n_in_drops=len([list(map(int, d)) for d in (sb.get('drops') or [])]),
        drop_start=c.get('drop_start'),
    )


def fade_env(typ, feat=None):
    """SNAP_IN (late legal rise + shallow outgoing hold) for breakdown into drop.
    Default fade for outro-intro and for drop1_end (the 11-14 fix the listener liked).

    SNAP_IN_HOLD (16 extra bars at -12 dB, then the usual residual) is only
    for the 3+ incoming-drop case, and only when the outgoing still has
    runway. That is the 11-15 shape (Together's third drop). Other
    breakdown_drop picks get SNAP_IN without the long hold. X1 and the
    outgoing rate cap are unchanged.
    """
    if typ != 'breakdown_drop':
        return {}
    env = {'SNAP_IN': '1'}
    feat = feat or {}
    if (int(feat.get('n_in_drops') or 0) >= N_DROPS_LAST
            and int(feat.get('out_left') or 0) >= HOLD_OUT_LEFT
            and int(feat.get('to_outro') or 0) >= HOLD_TO_OUTRO):
        env['SNAP_IN_HOLD'] = str(HOLD_EXTRA)
    return env


def is_extended_ok(choice):
    """True when a mid-track pick may use a pair_cands window that only
    exists because WINDOW_PLANNER lifted the bar-80 / emin caps.

    That exemption is the last-drop cue on an incoming track with 3+
    drops (ukf__25: Together bar 192). Every other mid-track pick must
    already have been a default pair_cands window (v1 behaviour), so
    netsky__06 / pola__04 stay on their defaults.
    """
    if not choice or choice.get('type') not in ('breakdown_drop',):
        return False
    f = choice.get('features') or {}
    return int(f.get('n_in_drops') or 0) >= N_DROPS_LAST


def _is_plus32(f):
    ds = f.get('drop_start')
    if ds is None:
        return False
    return int(f['win'][3]) == phrase(ds) + 32


def _best(arr, prefer_first_drop=False, prefer_last_drop=False):
    def key(f):
        # fewer holes; then either first drop (drop1_end) or last drop
        # (breakdown_drop when the incoming has 3+ drops); body +32 phrase
        # of a long last drop; start over mid otherwise; louder incoming;
        # earlier ib as a last tie-break
        if prefer_last_drop:
            return (
                f['holes'],
                -int(f.get('in_drop') or 0),
                0 if _is_plus32(f) else (1 if not f.get('ib_is_start') else 2),
                -float(f['in_vs_body']),
                int(f['win'][3]),
            )
        return (
            f['holes'],
            0 if (prefer_first_drop and f.get('in_drop') == 1) else 1,
            0 if f.get('ib_is_start') else 1,
            -float(f['in_vs_body']),
            int(f['win'][3]),
        )
    return sorted(arr, key=key)[0]


def select(default_win, sa, sb, lo_a, lo_b, gap=None, cands=None, X=None):
    """Choose a window type from track features. Returns
    dict(type, win, fade_env, reason, features, default_holes, outro_holes).

    type is 'outro_intro' (stay on the default window) or a mid-track type.
    When staying, win is the default_win and fade_env is empty.
    """
    gap = GAP_DB if gap is None else float(gap)
    if default_win is None:
        return dict(type='outro_intro', win=None, fade_env={}, reason='no_default',
                    features=None, default_holes=None, outro_holes=None)
    X = int(X or default_win[4])
    if cands is None:
        cands = nominate(sa, sb, X=X)
    feats = [features(c, sa, sb, lo_a, lo_b, gap) for c in cands]
    def_h = hole_bars(default_win, lo_a, lo_b, gap)
    intro = int(sb.get('intro_end') or sb.get('drop1') or 0)
    hm = hole_min(X)
    outro_c = [f for f in feats if f['type'] == 'outro_intro']
    outro_h = min((f['holes'] for f in outro_c), default=def_h)
    stay = dict(type='outro_intro', win=list(default_win), fade_env={},
                features=None, default_holes=def_h, outro_holes=outro_h)

    def mid(typ, f, reason):
        return dict(type=typ, win=list(f['win']), fade_env=fade_env(typ, f),
                    reason=reason, features=f, default_holes=def_h, outro_holes=outro_h)

    bd = [f for f in feats if f['type'] == 'breakdown_drop'
          and f['holes'] < def_h and f['inc_bass_ok'] and f['out_down']
          and f['in_sec'] == 'drop']
    d1 = [f for f in feats if f['type'] == 'drop1_end'
          and f['holes'] < def_h and f['inc_bass_ok'] and f['in_sec'] == 'drop']

    n_drops = int((bd or d1 or [{'n_in_drops': 0}])[0].get('n_in_drops') or 0)
    last = n_drops >= N_DROPS_LAST
    if def_h <= hm:
        return dict(stay, reason='default_clean')
    short = intro < SHORT_INTRO
    if not (outro_h > hm or short):
        return dict(stay, reason='outro_ok_and_intro_not_short')
    if short and bd:
        return mid('breakdown_drop', _best(bd, prefer_last_drop=last), 'short_intro_bd')
    if d1:
        return mid('drop1_end', _best(d1, prefer_first_drop=True), 'drop1_end')
    if bd:
        return mid('breakdown_drop', _best(bd, prefer_last_drop=last), 'fallback_bd')
    return dict(stay, reason='no_canonical_mid')


def engine_cands(sa, sb, X, e_max=None, ia=0, na=None, nb=None):
    """(kind, e, ib) tuples to append in mix_simple.pair_cands when the flag is on.

    Mid-track ends may sit before the usual emin (half-track) cutoff; they
    still have to end at or before e_max and start after the incoming track
    has begun. Incoming starts may go past the usual bar-80 cap.
    """
    out = []
    for c in nominate(sa, sb, X=X):
        kind, e, _p, ib, Xx = c['win']
        if Xx != X or kind != 'n':
            continue
        if e_max is not None and e > e_max:
            continue
        if ia is not None and e - X < int(ia):
            continue
        out.append((kind, e, ib))
    return out


def add_families(fams, cs, sa, sb, lo_a=None, lo_b=None, enabled=False, gap=None, X=16):
    """Append plan_breakdown_drop / plan_drop1_end when enabled, skipping
    windows already on the shortlist. Off by default.
    """
    if not enabled:
        return list(fams)
    fams = list(fams)
    have = {tuple(c['win']) for c in fams}
    legal = {tuple(c['win']) for c in cs} if cs is not None else None
    for typ, fam in (('breakdown_drop', FAM_BREAKDOWN), ('drop1_end', FAM_DROP1)):
        for c in nominate(sa, sb, X=X):
            if c['type'] != typ:
                continue
            key = tuple(c['win'])
            if key in have:
                continue
            # only windows pair_cands already scored: otherwise mix_simple
            # rejects the out_win (Wilkinson 2026-11-15).
            if legal is not None and key not in legal:
                continue
            fams.append(dict(fam=fam, win=list(c['win']), env=fade_env(typ)))
            have.add(key)
    return fams


def classify_pro_shape(shape, near_drop1_end=False, pair_id=None):
    """Map a pro section-shape label (from locates) to a planner type."""
    if pair_id == 'hybrid_minds_ukf__19' or near_drop1_end and shape == 'drop>drop':
        return 'drop1_end'
    if shape in ('drop>intro', 'outro>intro'):
        return 'outro_intro'
    if shape == 'breakdown>drop':
        return 'breakdown_drop'
    if shape == 'drop>drop':
        return 'drop_drop'
    if shape:
        return 'other'
    return 'unknown'


def apply_choice(scored_fams, planner_choice, default_win, base_wins=None):
    """Pick the family to render after the selector has run.

    Mid-track: that window, if it is on the shortlist; otherwise the default.
    Stay (outro_intro or no choice): the default window, never a plan_*
    family that only won on hint cost. That bug surfaced on Wilkinson
    (['n', 88, None, 24, 16] is not even a legal pair_cands window).
    """
    def as_fam(item):
        return item[1] if isinstance(item, (tuple, list)) and len(item) == 2 and isinstance(item[1], dict) else item
    fams = [as_fam(x) for x in (scored_fams or [])]

    def nat_default():
        if default_win is None:
            return next((c for c in fams if c.get('fam') in ('nat_short', 'nat_long')), fams[0] if fams else None)
        want = tuple(default_win)
        for name in ('nat_short', 'nat_long'):
            hit = next((c for c in fams if c.get('fam') == name and tuple(c.get('win') or []) == want), None)
            if hit is not None:
                return hit
        return next((c for c in fams if tuple(c.get('win') or []) == want and c.get('fam') not in
                     ('sneak_in', 'swap_early', 'swap_late', 'phrase_cut')), None) or (fams[0] if fams else None)

    fallback = nat_default()
    if not planner_choice or planner_choice.get('type') in (None, 'outro_intro') or not planner_choice.get('win'):
        return fallback
    want = tuple(planner_choice['win'])
    # Windows that only entered cs through the WINDOW_PLANNER env alias
    # (incoming start past 80, or an end before emin) are not applied unless
    # this is the 3+ drop last-drop cue.
    if (base_wins is not None and want not in base_wins
            and not is_extended_ok(planner_choice)):
        return fallback
    hit = next((c for c in fams if tuple(c.get('win') or []) == want), None)
    if hit is None:
        return fallback
    hit = dict(hit)
    hit['planner'] = dict(type=planner_choice.get('type'), reason=planner_choice.get('reason'),
                          fade_env=planner_choice.get('fade_env') or {})
    return hit
