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


def xlong(u, X, rise=2.0, xp=0.35, xp2=0.5, exit_=8.0, solo=0.0):
    if u <= 0:
        return 0.0
    b = u * X
    ex1 = X - solo_bars(X, rise, exit_, solo)
    ex0 = max(rise + 1, ex1 - exit_)
    if b >= ex1:
        return 1.0
    if b < rise:
        # -24 dB at the first logged beat (the guards floor gains at -24 dB and read the per-beat log at 1/16 bar)
        t = -24 + (20 * np.log10(np.sin(xp * np.pi / 2)) + 24) * max(0.0, b - 0.25) / (rise - 0.25)
        return float(2 / np.pi * np.arcsin(min(1.0, 10 ** (t / 20))))
    if b < ex0:
        return float(xp + (xp2 - xp) * (b - rise) / max(ex0 - rise, 1e-9))
    a2 = 20 * np.log10(np.cos(xp2 * np.pi / 2))
    t = a2 + (-24 - a2) * (b - ex0) / max(ex1 - ex0, 1e-9)
    return float(max(xp2, 2 / np.pi * np.arccos(min(1.0, 10 ** (t / 20)))))


def exit_bar(X, rise=2.0, exit_=8.0, solo=0.0):
    """bars into the window where the outgoing is gone"""
    return X - solo_bars(X, rise, exit_, solo)


def exit_start(X, rise=2.0, exit_=8.0, solo=0.0):
    """bars into the window where the outgoing's exit ramp starts (end of the plateau)"""
    return max(rise + 1, exit_bar(X, rise, exit_, solo) - exit_)


def swap_pos(X, rise=2.0, exit_=8.0, solo=0.0, **_):
    """LONG_SWAP=exit (2026-11-11 long-blend RCA #2): the bass swap centred on the exit start, as a fraction of the window.
    Joe Syntax kept Shine In's lows at full until his cut, then lows and level left together; with the swap at SWAP_POS
    (0.21, bar ~7 of 32) on the plateau, ours lost Shine In's low end 1-3 bars before its 8-bar exit even began,
    so the outgoing faded twice (~11 bars). At the exit start x = xp2 (0.5), inside X1's 0.2-0.65 swap window."""
    return exit_start(X, rise, exit_, solo) / X


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
