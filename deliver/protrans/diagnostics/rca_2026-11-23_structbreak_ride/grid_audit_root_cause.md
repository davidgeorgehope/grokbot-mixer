# Grid audit: why the official offset stays ~147 ms

Pair: S.P.Y – Seconds To Midnight → London Elektricity – Meteorites (Danny Byrd Remix), Joe Syntax Hospital Mix transition 13. Written 2026-11-23 20:28 America/New_York.

## Root cause

The official blend_diag median of **146.6 ms** (pass line 40 ms) is stable across the lead-in and ride renders because those two renders share the same constant LEADIN_LOCK and the ride never applied. It is **not** a whole-track downbeat flipped by half a beat (172 ms), and it is **not** BPM or metronome drift (both stored grids are a perfect 174.000 pulse).

S.P.Y's **post-drop-1 breakdown [128, 160]** is a section-local half-time groove on an otherwise correct drop-locked grid:

- Isolated **kicks** in that region sit near half a beat off the stored downbeats (region fold peak around beat 2.5; phrase phase walks from +21.6 ms on bars 128–135 to +129.3 ms on 136–143, toward ±172 ms, then recovers into drop 2).
- Isolated **snares** stay near the grid.
- The existing kick-on-1 / snare-on-2-and-4 template prefers a half-beat shift **only in this region** (margin +1.21, above the 0.5 line). Prep's half-beat check is **global** and is won by the on-grid drops, so `half_off` stays false and the grid is not shifted. That is the right call: flipping the track would break drop 1, drop 2, and the snares.

Official `blend_diag` then measures a **2-bar kick+snare xcorr** on the five loud overlap bars 130–134 and reports the median of `[91.4, -111.7, 161.1, 161.1, 146.6]` = **146.6 ms**. A 1-bar window on the same bars is **88.5 ms** — the outgoing phase walking after the locked first phrase, plus some hops, not a clean half-beat lock.

## Against the pro

The 64-second pro clip shows the same thing: of six strong S.P.Y breakdown kicks that land in the clip, four sit near half a beat off the stored grid (abs median 155 ms); snares stay on-beat (median −31 ms). After aligning ours to the pro, `beat_identity` differs by **7.3 ms**. The constant lead-in lock already matches how the pro placed the two records.

Meteorites is not flipped either. Its snares are clearly on 2 and 4 (global template margin −5.6). The high global kick off-beat ratio (1.38) is syncopated drop kicks. The piano half-time [48, 61] is on the stored grid (phase −21.6 ms, strength 5.1).

## What this means for the ride and for a clip

ONBEAT_RIDE needed four bars where **both** decks have a kick within 40 ms of the downbeat. It found three (residuals +16.1, −46.4, −20.3 ms) and correctly refused to apply. That floor was not loosened.

Chasing 146.6 ms with another constant lock, or loosening the ride so it can follow S.P.Y's later breakdown kicks, would move Meteorites off its on-grid piano phrase and away from the pro. No listen clip.

The piano lead-in check failed this run because BASS_FILL_GAPS already has lows up at mix 140–144, so the 3 dB lows jump at bar 48 disappeared (pre −26.9, event −25.0). The mid band at mix 144 still rises (−24.1 vs lead-in mid −30.6): the piano is there. Bass hole check passed (hole_db −18.5). No hard fail.

## General analysis fix (not a per-track pin)

When the outgoing overlap is a post-drop half-time breakdown (section-local half-beat margin ≥ 0.5, or an existing half-time section), official kick+snare xcorr is the wrong estimator. Prefer isolated snares and/or on-beat-only kick lags, and use pro `beat_identity` as the placement check. Do not re-grid a breakdown independently of its drops. Keep the incoming lock anchored to the lead-in phrase, not to later outgoing kick syncopation.

Scripts and numbers: `scratch/rca1123/grid_audit.py`, `scratch/rca1123/grid_audit_pro.py`, and `deliver/protrans/diagnostics/rca_2026-11-23_structbreak_ride/grid_audit_root_cause.json`.
