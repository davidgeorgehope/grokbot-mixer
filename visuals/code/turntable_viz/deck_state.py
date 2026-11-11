#!/usr/bin/env python3
"""Two-deck state machine for the turntable visual.

A real DJ never moves a playing record. Track 0 starts on deck A. At every
transition the incoming track is loaded onto the idle deck (the one whose
record has stopped), the outgoing deck keeps playing until its exit, then it
is idle and gets the next record. So track k always lives on deck k % 2, by
construction, and decks alternate A/B/A/B.

Mix 08 (2026-11-11) broke this: build_segs.py put each segment's outgoing
track on deck A and incoming on deck B, so at every segment cut (midway
between two transitions) the record that was playing on deck B jumped to
deck A.

Helpers here are shared by build_segs.py (layout + record-swap FX windows)
and the pytest that walks a mix plan (src/tests/test_turntable_decks.py).
"""
from __future__ import annotations
import math

DECK_NAMES = 'AB'
FLY_OFF_BARS = 2.0   # outgoing record lifts and flies away over this many bars, ending at the segment cut
SPIN_IN_BARS = 3.0   # next record spins in and flips onto the idle deck over this many bars, from the cut


def exit_bar(deck):
    """Mix bar where the engine stops this deck (end of its full_map)."""
    return deck['start_bar'] + len(deck['full_map'])


def assign_slots(meta):
    """Deck slot (0 = A, 1 = B) for every track in meta['decks'], via the load-on-idle state machine.

    Raises ValueError when the plan cannot be played on two decks (a third record would be needed
    because the next track starts before the deck it must use has stopped) or when trans/decks disagree.
    """
    T, D = meta['trans'], meta['decks']
    if len(D) != len(T) + 1:
        raise ValueError(f'{len(D)} decks for {len(T)} transitions (want n+1)')
    slot = [0]                                   # track 0 on deck A
    for i, t in enumerate(T):
        if D[i]['id'] != t['a'] or D[i + 1]['id'] != t['b']:
            raise ValueError(f'trans {i} {t["a"]}->{t["b"]} does not match decks {D[i]["id"]}->{D[i + 1]["id"]}')
        idle = 1 - slot[i]                       # the deck not playing track i
        if i >= 1 and exit_bar(D[i - 1]) > D[i + 1]['start_bar']:
            raise ValueError(f'trans {i}: track {i + 1} starts at bar {D[i + 1]["start_bar"]} but deck '
                             f'{DECK_NAMES[idle]} is still playing track {i - 1} until bar {exit_bar(D[i - 1])}')
        slot.append(idle)
    return slot


def segment_cuts(meta):
    """Segment boundaries in mix bars: midpoints between consecutive transitions (same as build_segs)."""
    T = meta['trans']
    return [0.0] + [(T[i - 1]['end_bar'] + T[i]['start_bar']) / 2 for i in range(1, len(T))]


def segment_layout(meta, i, slots=None):
    """Physical layout for segment i (transition i): which meta deck index sits on deck A and B.

    Returns dict(phys=[deck_idx_on_A, deck_idx_on_B], out_deck=slot of the outgoing track).
    """
    slots = slots or assign_slots(meta)
    a, b = i, i + 1
    phys = [a, b] if slots[a] == 0 else [b, a]
    return dict(phys=phys, out_deck=slots[a])


def fx_windows(meta, i, s0, s1, slots=None):
    """Record-swap FX windows (mix bars) inside segment i = [s0, s1].

    fly_off: after track i has stopped, its record lifts off and flies away, finishing at s1 (the next cut),
             which empties that deck for track i+2.
    spin_in: from s0 (this segment's cut), track i+1's record spins in and flips onto the idle deck, seated
             before it starts playing.
    Windows are clipped so a record never moves while it plays.
    """
    slots = slots or assign_slots(meta)
    D, T = meta['decks'], meta['trans']
    out = {}
    # spin in: incoming record of this transition, from the segment start, done before it starts playing
    inc = D[i + 1]
    if i >= 1:                                  # track 0/1 are on the decks from the first frame
        a0, a1 = s0, min(s0 + SPIN_IN_BARS, inc['start_bar'] - 0.25)
        if a1 - a0 >= 0.75:
            out['spin_in'] = dict(deck=slots[i + 1], start_bar=a0, end_bar=a1, id=inc['id'])
    # fly off: outgoing record of this transition, after its exit, finishing at the segment end (the next cut)
    if i + 1 < len(T):
        og = D[i]
        f1 = s1
        f0 = max(exit_bar(og) + 0.5, s1 - FLY_OFF_BARS)
        if f1 - f0 >= 0.75:
            out['fly_off'] = dict(deck=slots[i], start_bar=f0, end_bar=f1, id=og['id'])
    return out


def deck_bar(deck, mb):
    """mix bar -> (track bar, playing). Mirrors prep.deck_bar (kept dependency-free for tests)."""
    i = mb - deck['start_bar']
    if i < 0:
        return float(deck['full_map'][0][0]), False
    if i >= len(deck['full_map']):
        return float(deck['full_map'][-1][0]) + 1, False
    k = int(math.floor(i))
    return float(deck['full_map'][k][0]) + (i - k), True


def walk_segments(timings, step=0.25):
    """Walk per-segment timing dicts (build_segs output, in order) bar by bar and list deck-rule violations.

    Rules: (1) a record (track id) only ever sits on one deck for the whole mix, so the playing record never
    changes decks, mid-play or at a segment cut; (2) consecutive tracks use different decks (A/B/A/B);
    (3) record-swap FX never move a record while it plays.
    """
    errs, home, order = [], {}, []
    for t in timings:
        s0, s1 = float(t['clip_start_bar']), float(t['clip_end_bar'])
        decks = t['decks'][:2]
        for d in decks:
            if d['id'] not in order:
                order.append(d['id'])
        n = max(1, int(round((s1 - s0) / step)))
        for k in range(n):
            mb = s0 + k * step
            for phys, d in enumerate(decks):
                tb, on = deck_bar(d, mb)
                h = home.setdefault(d['id'], phys)
                if h != phys:
                    errs.append(f'bar {mb:.2f}: {d["id"]} {"playing" if on else "shown"} on deck {DECK_NAMES[phys]} '
                                f'but it lives on deck {DECK_NAMES[h]}')
        for kind, w in (t.get('fx') or {}).items():
            d = next((x for x in decks if x['id'] == w['id']), None)
            if d is None:
                errs.append(f'fx {kind} names {w["id"]}, not on a deck in this segment'); continue
            ex = d.get('exit_bar', exit_bar(d))
            if kind == 'spin_in' and w['end_bar'] > d['start_bar']:
                errs.append(f'fx spin_in of {w["id"]} ends at bar {w["end_bar"]:.2f} after it starts ({d["start_bar"]})')
            if kind == 'fly_off' and w['start_bar'] < ex:
                errs.append(f'fx fly_off of {w["id"]} starts at bar {w["start_bar"]:.2f} before its exit ({ex})')
    for a, b in zip(order, order[1:]):
        if a in home and b in home and home[a] == home[b]:
            errs.append(f'{a} and {b} are consecutive but both on deck {DECK_NAMES[home[a]]}')
    # stop after the first few; one bad cut repeats every step
    return errs
