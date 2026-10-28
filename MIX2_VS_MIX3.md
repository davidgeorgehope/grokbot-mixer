# Mix 02 vs Mix 03: what Mix 02 did right

Mixes compared: Mix 02 (dj-mix-02b, 36:18, 14 tracks), old Mix 03 (mix360f, 63:43, 20 tracks, stem/ducking engine), and new Mix 03 (mixT, 51:30, 19 tracks, crossfader engine).
Data: /workspace/m23/metrics.json (made by compare.py and drops.py). The old engines were read from git and were not restored.

| metric | Mix 02 | old 03 | new 03 |
|---|---|---|---|
| blend length (bars) | 40–56 (mean 40) | 16 + 16 tail | 16 or 32 (9/18 at 32) |
| time with two decks playing | 27% | 22% | 12% |
| automation travel per min | 51 | 293 (per-beat vocal ducking) | 1.4 |
| FX events | few (5 risers, 4 vocal mutes) | 57 (riser on every transition) | 0 |
| drums-only bars (longest run) | 28 (4) | 112 (14, at 22:57–25:18) | 58 (4) |
| bass overlap | 0 | 0 | 0 |
| vocal-overlap bars | 7 (an intentional acapella at 32:02) | 1 | 6 |
| gain jumps >3 dB per min | 3.0 | 3.1 | 3.3 |
| minutes per track | 2.6 | 3.2 | 2.7 |
| share of each track's loud "body" played (mean) | 0.86 | 0.90 | 0.74 |
| longest energy lull (>6 dB under mix median) | 5 bars | 18 bars @19:33 | 17.5 bars @15:24 |
| current guardrails, failures excluding X1 (no crossfader log) | 15* | 19* | 0 |

*For the old mixes, the deck-level checks re-render the decks with the current engine, so those counts are approximate. The audio-level checks (E1, E2, E4) are exact.
Old 03 audio problems: near-silence at 26:39–26:46 (E2 ×8), the lull at 19:15–19:58, and bass doubling at 19:58.

## Top differences
1. **Long beat-through overlaps.** Mix 02 keeps both tracks running together for 40–56 bars (27% of the mix). Old 03 used 16-bar blends with FX layered on top. New 03 is back to 16–32 bars, but only 12% of the time has both decks playing. To hear it, compare Mix 02 at 3:39 and 16:19 with new 03 at 5:08 and 8:49.
2. **Processing in old 03.** It had per-beat vocal ducking (15 blends), 57 FX, 16 "near-silent bar" edits and drums-stem loop extensions. Two places to hear it: 22:57–25:18 (drums only) and 26:39 (near-silence). New 03 dropped all of that, which is why it sounds closer to Mix 02.
3. **No energy lulls in Mix 02.** Old 03 dips at 19:15–19:58. New 03 dips at 15:06–16:10, where Always Be's breakdown runs into the Supernova intro.
4. **Mix 02 plays the body of each track.** It plays 86% of each track's loud section on average. New 03 plays 74%: Always Be 34%, Strings Of Life 47% (it lasts only 1:50, from 11:02 to 12:52), Supernova 55%, Deeper 56%.
5. **Mix 02 handled key clashes with echo-outs and double drops** (10B→4A at 18:42). New 03 avoids clashes by choosing harmonic mix points, so it has no K1 fails.

## Turned into checks
- guardrails **E4 "long lull"**: fails when 3 s loudness stays more than 6 dB under the mix median for more than 8 bars, outside the first and last 45 s. Mix 02 passes; old 03 and new 03 fail.
- tests/test_mix02_traits.py:
  - each track gets its body: mean ≥0.8, min ≥0.5;
  - at least half of the blends are ≥32 bars;
  - no drums-only run of ≥8 bars.
  - Mix 02 passes all three. Old 03 fails the drums-only test. New 03 fails the body test.
- I tried an engine default: a lull penalty in mix_simple's pair scoring (sag/SAGPEN). It did not work. The test render (mixU) still had a 17-bar lull at 16:30 and added a vocal-clash fail, beat-alignment fails, a body-coverage fail and a 32-bar-blend fail. I removed it.
- **Result:** the delivered Mix 03 now fails E4 and the body test. Neither was relaxed. Fixing them needs a plan change (where Always Be and Strings Of Life sit and their entry/exit points).
