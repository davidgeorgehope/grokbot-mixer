# Mixing rules (hard)

These rules come from listener feedback (see TASTE.md). Guardrail IDs are in brackets.

1. **At least 60 minutes**, about 18–22 tracks.
2. **One crossfader per blend** [X1]. Each blend has a single monotonic equal-power x(t) 0→1 over 16 bars on a phrase boundary. Gains come only from x: no channel-fader moves, no ducking, no mutes, no stems, no echo-outs, no stop-start.
3. **Constant per-track level.** Each track is normalised once to -16 LUFS and never ridden.
4. **Real overlap** [O1]. Both decks play at musical level for at least 8 bars.
5. **The outgoing track keeps its groove** [C2, C1, E3]. It stays within 10 dB of its body for the first half of the blend.
6. **Mix points are vocal-free** [V1]. Never two singers at once. Pick a different window instead of muting.
7. **One bassline at a time** [L1]. Pick windows where at most one deck has a full low end.
8. **Loop clean phrases, never dead tails** [S1, J1, E1, E2]. If a track's outro is busy or silent, repeat one of its clean instrumental 16-bar phrases (1-beat overlap-add seams).
9. **Harmonic flow** [K1]. Camelot distance of 2 or less per blend. Reorder with `order.py` if needed.
10. **Tight timing** [F1, N1, G1, R1, T1]. Fix timing with warp nudges, and drop tracks that aren't DnB.
11. **Loudness**: about -9 LUFS integrated and true peak at or below -1 dBTP [P1].
