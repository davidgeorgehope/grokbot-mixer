"""FADE=long crossfader shape (2026-11-11 long-blend RCA, Joe Syntax Hospital Mix 22:46, Shine In > Dusk To Dawn, rated 2/5).

Pros bring the incoming up EARLY to a real level (Joe: -2..-8 dB for ~17 bars) and take the outgoing out decisively on a
phrase. FADE=lin/tail keep the incoming at -30..-12 dB for the first ~13 of 32 bars and let the outgoing linger to the window
end, so a 32-bar window sounds (and the protrans scorer measures it) like an ~8-10 bar blend.

Still the ONE monotonic equal-power crossfader x(u) 0->1 (deck gains cos/sin of x), inside every guard:
- incoming rises linearly in dB from -24 dB (first beat) to sin(xp) at `rise` bars (<= 3 dB/beat, guardrail X1)
- plateau: x goes xp -> xp2 (both decks in; outgoing ~-1.4 .. -3 dB, incoming ~-5.6 .. -3 dB)
- decisive exit: the outgoing falls linearly in dB from cos(xp2) to -24 dB over `exit_` bars (<= 3 dB/bar while above -24 dB:
  test_outgoing_fader_tail_is_gradual) and is gone (x=1) `solo` bars before the window end, on a 4-bar boundary, so the
  incoming plays its own phrase solo up to its drop (STRUCT windows end on the incoming drop).
`solo` is clipped so rise + exit + 4 plateau bars always fit (a 16-bar window gets solo 0)."""
import numpy as np


def solo_bars(X, rise=2.0, exit_=8.0, solo=0.0):
    s = min(float(solo), max(0.0, X - rise - exit_ - 4))
    return s - s % 4


def xlong(u, X, rise=2.0, xp=0.35, xp2=0.5, exit_=8.0, solo=0.0, hold=0.0):
    if u <= 0:
        return 0.0
    b = u * X
    hold = max(0.0, float(hold))
    ex1 = X - solo_bars(X, rise, exit_, solo)
    ex0 = max(hold + rise + 1, ex1 - exit_)
    if b >= ex1:
        return 1.0
    if b < hold:
        return 0.0
    if b < hold + rise:
        # -24 dB at the first logged beat of the (possibly delayed) rise
        t = -24 + (20 * np.log10(np.sin(xp * np.pi / 2)) + 24) * max(0.0, b - hold - 0.25) / (rise - 0.25)
        return float(2 / np.pi * np.arcsin(min(1.0, 10 ** (t / 20))))
    if b < ex0:
        return float(xp + (xp2 - xp) * (b - hold - rise) / max(ex0 - hold - rise, 1e-9))
    a2 = 20 * np.log10(np.cos(xp2 * np.pi / 2))
    t = a2 + (-24 - a2) * (b - ex0) / max(ex1 - ex0, 1e-9)
    return float(max(xp2, 2 / np.pi * np.arccos(min(1.0, 10 ** (t / 20)))))


def exit_bar(X, rise=2.0, exit_=8.0, solo=0.0):
    """bars into the window where the outgoing is gone"""
    return X - solo_bars(X, rise, exit_, solo)


def exit_start(X, rise=2.0, exit_=8.0, solo=0.0, hold=0.0, **_):
    """bars into the window where the outgoing's exit ramp starts (end of the plateau).
    Same formula as xlong: the rise (and an optional vocal hold) have to finish first."""
    hold = max(0.0, float(hold))
    return max(hold + rise + 1, exit_bar(X, rise, exit_, solo) - exit_)


def swap_pos(X, rise=2.0, exit_=8.0, solo=0.0, hold=0.0, **_):
    """LONG_SWAP=exit (2026-11-11 long-blend RCA #2): the bass swap centred on the exit start, as a fraction of the window.
    Joe Syntax kept Shine In's lows at full until his cut, then lows and level left together; with the swap at SWAP_POS
    (0.21, bar ~7 of 32) on the plateau, ours lost Shine In's low end 1-3 bars before its 8-bar exit even began,
    so the outgoing faded twice (~11 bars). At the exit start x = xp2 (0.5), inside X1's 0.2-0.65 swap window."""
    return exit_start(X, rise, exit_, solo, hold=hold) / X


def struct_solo(al, wa, X, rise=2.0, exit_=8.0, solo=0.0, **_):
    """LONG_SOLO_STRUCT=1 (2026-11-11 long-blend RCA #1): end the outgoing's exit where its OWN energy drops, so the exit
    lands on the outgoing's phrase and its quiet bars are never faded through. Joe Syntax cut Shine In in 1 bar at its
    bar ~127, exactly where Shine In dips 4-7 dB on its own; ours (LONG_SOLO=16) faded Shine In's full-energy drop
    (bars 216-224) over 8 bars. al = the outgoing's per-bar level (dB), wa = its source bars across the window.
    First window bar j (4-bar boundary, >= rise+exit_+4) where the outgoing's next 2 bars sit >= 4 dB under its body
    (75th percentile) -> solo = X - j; no such bar -> the fixed `solo`."""
    import numpy as np
    al = np.asarray(al, float); body = float(np.percentile(al, 75)); j0 = int(np.ceil((rise + exit_ + 4) / 4) * 4)
    for j in range(j0, int(X), 4):
        k = [wa[t] for t in (j, j + 1) if t < len(wa) and 0 <= wa[t] < len(al)]
        if len(k) == 2 and float(np.mean(al[k])) <= body - 4:
            return float(X - j)
    return float(solo)


def incoming_thin_bars(al, lo, wb, X, db=4):
    """0-based window bars where the incoming is thin.

    Same rule as cap_solo_incoming: a second-half bar >= db under the incoming's own
    first-half median, all-band or low."""
    def series(arr):
        arr = np.asarray(arr, float)
        out = []
        for j in range(int(X)):
            k = wb[j] if j < len(wb) and 0 <= wb[j] < len(arr) else None
            out.append(arr[k] if k is not None else np.nan)
        return np.array(out, float)
    def idxs(arr):
        s_ = series(arr)
        half = max(4, int(X) // 2)
        if np.isfinite(s_[:half]).sum() < 2:
            return np.array([], int)
        ref = float(np.nanmedian(s_[:half]))
        return np.where((np.arange(int(X)) >= half) & (s_ < ref - db))[0]
    idx = idxs(al)
    if lo is not None:
        idx = np.unique(np.concatenate([idx, idxs(lo)]))
    return idx.astype(int)


def first_incoming_thin_bar(al, lo, wb, X, db=4):
    idx = incoming_thin_bars(al, lo, wb, X, db)
    return int(idx[0]) if len(idx) else -1


def last_incoming_thin_bar(al, lo, wb, X, db=4):
    """Last 0-based window bar where the incoming is thin, or -1."""
    idx = incoming_thin_bars(al, lo, wb, X, db)
    return int(idx[-1]) if len(idx) else -1


def cap_solo_incoming(al, lo, wb, X, rise=2.0, exit_=8.0, solo=0.0, **_):
    """Cap solo so the outgoing's exit does not finish into a later thin stretch of the incoming.

    Thin = a second-half bar >= 4 dB under the incoming's own first-half median (all-band or low),
    not under the full-track body (an intro window is often a few dB under the track's drop, and
    treating that as 'never ready' delayed the exit on Mix 08 long1c trans 0 and layered vocals).
    A mid-window crash (Bad To Me bars 16-31, E1 at 30:35; Solitude's pre-drop lows) still caps
    solo so the outgoing covers it. If the second half is as strong as the first, solo is unchanged."""
    last = last_incoming_thin_bar(al, lo, wb, X)
    if last < 0:
        return solo_bars(X, rise, exit_, solo)
    return solo_bars(X, rise, exit_, min(float(solo), max(0.0, X - (last + 1))))


def vocal_hold(vA, rvA, wa, vB, rvB, wb, X, early=8):
    """Bars to delay the incoming rise so it does not cross equal-power 0.3 while both sources
    are singing. Only a leading clash (first run starting within `early` bars): a mid-blend hold
    would drop the fader, which X1 forbids. 2026-11-11 Mix 08 long test: tail's slow rise kept
    incoming under 0.3 for the first bars; the long rise made a 1-bar and a 3-bar clash audible."""
    hits = [k for k, (xa, xb) in enumerate(zip(wa, wb))
            if k < int(X) and xa < len(vA) and xb < len(vB) and vA[xa] > rvA - 12 and vB[xb] > rvB - 12]
    early_hits = [k for k in hits if k <= early]
    if not early_hits:
        return 0
    # through the last early clash (a 1-bar gap after a weak first bar must not hide the real phrase;
    # Mix 08 long1c trans 22: hits at 0,2,3,4 — the first-run-only hold was 1 and V1 still fired)
    return int(early_hits[-1] + 1)


def bass_lead(blead=1.0, phrase=False, fade='tail'):
    """(outgoing_lead, incoming_lag) in bars for the low lanes.

    Phrase-snapped swaps already lead the outgoing by BASS_LEAD and land the incoming on the 1.
    FADE=long uses the same shape even when the swap is at POS (the exit start): a symmetric
    0.5+0.5 lead mid-crosses on the plateau at x=0.5, and two similar quiet subs summed 3.1-3.5 dB
    over the louder deck (Mix 08 long1e L1 at 2:45 and 16:00). Outgoing-leads keeps width and
    centre unchanged (X1 and the 4-bar abrupt-tail reason stay). A 2-bar swap starting on this
    exit is the long1 Ember shape that failed the 6 dB/bar rendered-tail cap, so we do not go back
    to it.

    Do not delay the outgoing down-ramp to cover a late thin stretch (Mix 08 long1g): a negative
    outgoing_lead pushed the low-lane centre to x=1.00, incoming still rose at the exit start, both
    decks carried full bass, and X1 / L1 / the ride test failed on 14+ blends. When the planned
    handoff overlaps a thin incoming stretch, move the swap earlier with swap_before_thin instead
    (Mix 08 long1f trans 12: end the 4-bar handoff at the first thin bar, centre still at x=0.46)."""
    blead = float(blead)
    if fade == 'long' or phrase:
        return (blead, 0.0)
    return (blead / 2, blead / 2)


def swap_before_thin(X, pos, first_thin, swap_w=4.0, outgoing_lead=1.0, incoming_lag=0.0, xpos=None):
    """Possibly-earlier swap centre (fraction of X) so a long-blend bass handoff ends at or
    before first_thin (0-based window bar, or -1 if none).

    Only moves when the handoff at `pos` would still be running after first_thin (outgoing
    lows already leaving during the crash — Mix 08 long1f trans 12). If the exit-start swap
    already finishes first (most Mix 08 long1f blends with a late mid-window dip), `pos` is
    unchanged. Never moves the centre later: delaying the outgoing drop to last_thin (long1g)
    parked the low-lane at x=1.00 and stacked both basses.

    The new centre is used only if the handoff stays inside the window and xpos(c/X) is in
    X1's 0.2-0.65 bass-swap band. Otherwise `pos` is left alone."""
    if first_thin is None or first_thin < 0:
        return pos
    X, pos, first_thin = float(X), float(pos), float(first_thin)
    end = pos * X + incoming_lag + swap_w / 2
    if end <= first_thin + 1e-9:
        return pos
    c = first_thin - incoming_lag - swap_w / 2
    if c < outgoing_lead + swap_w / 2 - 1e-9:
        return pos
    if c + incoming_lag + swap_w / 2 > X + 1e-9:
        return pos
    x = (c / X) if xpos is None else float(xpos(c / X))
    if not (0.2 <= x <= 0.65):
        return pos
    return c / X


def vocal_exit_params(vB, rvB, wb, X, rise=2.0, exit_=8.0, solo=0.0, hold=0.0,
                      xp=0.35, xp2=0.5, cap_solo=None, **_):
    """(solo, exit_) so the outgoing is under VOC_GAIN 0.3 on late incoming-vocal bars.

    cap_solo is a ceiling on solo (how early the exit may *end*): cap_solo_incoming's value, so
    a late vocal does not uncover a thin incoming stretch (Mix 08 long1e trans 18: cap wanted
    solo 0 to cover Solitude's pre-drop hole at 1901-1902; solo_before used to raise solo to 4
    and the official 2-bar bass gap came back). If a vocal still clashes at that ceiling,
    lengthen the exit (start earlier, keep the end). A longer exit is shallower than 3 dB/bar.
    cap_solo is None: same raise-solo behaviour as before (tests, and blends with no thin cap).
    Leading clashes are vocal_hold."""
    start = int(max(hold + rise, 8))
    hits = [k for k, xb in enumerate(wb)
            if start <= k < int(X) and xb < len(vB) and vB[xb] > rvB - 12]
    s0 = solo_bars(X, rise, exit_, solo)
    ex0 = float(exit_)
    if not hits:
        return s0, ex0

    def outgoing_ok(ss, ex):
        for k in hits:
            x = xlong(k / X, X, rise=rise, xp=xp, xp2=xp2, exit_=ex, solo=ss, hold=hold)
            if np.cos(x * np.pi / 2) > 0.3 + 1e-9:
                return False
        return True

    if cap_solo is None:
        ceiling = solo_bars(X, rise, exit_, X)  # old: may raise freely
        if outgoing_ok(s0, ex0):
            return s0, ex0
        for ss in range(int(s0) + 4, int(ceiling) + 1, 4):
            if outgoing_ok(ss, ex0):
                return float(ss), ex0
        return float(ceiling), ex0

    ceiling = solo_bars(X, rise, exit_, cap_solo)
    # may raise solo only up to the cap
    if outgoing_ok(s0, ex0):
        return s0, ex0
    for ss in range(int(s0) + 4, int(ceiling) + 1, 4):
        if outgoing_ok(ss, ex0):
            return float(ss), ex0
    # keep the cap (exit ends late enough to cover the thin stretch); lengthen the exit
    ss = float(ceiling)
    hold = max(0.0, float(hold))
    max_exit = max(ex0, X - ss - hold - rise - 1)
    max_exit = min(max_exit, max(ex0, X - rise - 4 - ss))
    for ex in range(int(ex0) + 1, int(np.floor(max_exit)) + 1):
        if outgoing_ok(ss, float(ex)):
            return ss, float(ex)
    return ss, float(max(ex0, np.floor(max_exit)))


def solo_before_incoming_vocal(vB, rvB, wb, X, rise=2.0, exit_=8.0, solo=0.0, hold=0.0,
                               xp=0.35, xp2=0.5, cap_solo=None, **_):
    """Raise solo (exit earlier) so the outgoing is already under VOC_GAIN (0.3) when the incoming
    is singing. cap_solo_incoming can delay the exit to cover a thin incoming stretch; on Mix 08
    long1c that left both decks above 0.3 on incoming-vocal bars (trans 0 at +23, trans 18 at +25,
    trans 24 at +26). Leading clashes are vocal_hold (incoming stays down). This only looks after
    the opening hold+rise (or 8 bars). The planner's vocal term never saw these bars: the plan was
    scored under FADE=tail, where the outgoing was already under 0.3 there.

    Pass cap_solo (the cap_solo_incoming result) to refuse to uncover that thin stretch; see
    vocal_exit_params. Without cap_solo this still returns only the solo, old behaviour."""
    s, _ex = vocal_exit_params(vB, rvB, wb, X, rise=rise, exit_=exit_, solo=solo, hold=hold,
                               xp=xp, xp2=xp2, cap_solo=cap_solo)
    return s
