# Mixing rules (hard)

These rules come from real listener feedback (see TASTE.md). Guardrails enforce the ones marked [check].

1. **At least 60 minutes.** Listeners want a full hour of music. Check the length with `mix3.py --dry`. Aim for 18–22 tracks.
2. **No echo-outs and no stop-start.** [X1] "If this is stop this track / play this track, that's not mixing." Don't use `tech: echo` unless the step has `allow_echo` and the listener has signed off on that specific transition.
3. **Real overlapping blends.** [O1] Both decks must be at musical level (within 12 dB of the outgoing body) for at least 8 bars. Use `pre` 16–32. The 3-band bass swap means only one bassline plays at a time [L1].
4. **The outgoing track keeps its groove** [C2, C1]. It must stay within 10 dB of its body through the first half of the overlap, and it holds its mids and highs for 8 bars after the swap. Its record pauses inside the window get phrase-looped.
5. **Build into every drop; never just land on one.** [D1] Use `build: true` (HPF sweep, riser, impact on the one) or a ramp of at least 3 dB over the previous 8 bars. "It just dropped" was the complaint that started this rule.
6. **Never fade to silence, and never play a record's own dead tail.** [E1, E2, S1] The tail gets trimmed and runway comes from a drums-stem loop instead.
7. **Never two lead vocals at once.** [V1] Per-bar demucs vocal muting handles this automatically.
8. **Harmonic flow.** [K1] Keep Camelot distance at 2 steps or fewer across any harmonic overlap. For bigger jumps use `tail_drums: "early"` (drum bridge, no harmonic overlap) or reorder (`order.py`).
9. **Tight timing.** [F1, N1, G1] Flams at 15 ms or less, entries at 10 ms or less, grid jitter at 8 ms or less. Fix with warp nudges (`autofix.py`), not by loosening thresholds.
10. **Loops only when there's no runway.** Loop-extension uses clean drums-stem sections and is penalised by the eval as overuse.
11. **Vary techniques** (the eval rewards variety), but never at the cost of rules 2–9.
12. **Loudness**: about −9 LUFS integrated, true peak at or below −1 dBTP [P1].

## Pro-DJ reference (`eval/pro_profile.json`, 77 transitions from 4 pro liquid/DnB sets)
| metric | p25 | median | p75 |
|---|---|---|---|
| overlap (bars) | 8 | 14 | 24 |
| bass-swap length (bars) | 2 | 4 | 10 |
| swap position in overlap (0–1) | 0.06 | 0.58 | 0.93 |
| swap → drop (bars) | −1 | 8 | 27 |
| low-end dip at swap (dB) | −12.6 | −8.9 | −5.3 |
| energy delta (dB) | −1.1 | −0.2 | 0.9 |
| Camelot distance | 1 | (mean 2.4) | |

Takeaways: pros overlap for about 16 bars, swap the bass quickly, and keep energy flat (±1 dB) across transitions. Transitions land on 32-beat phrases.
