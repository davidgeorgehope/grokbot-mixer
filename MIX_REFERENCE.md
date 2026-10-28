# Reference mixes: what Mix 01 and Mix 02 did right (vs Mix 03)

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

## Mix 01 (added 2026-10-28)
Mix 01 = dj-mix-01, 26:12, 7 tracks. Engine read from git (yt-dj-crate af99da8, `src/mix.py`, 82 lines), not restored.
Data: /workspace/m1 (mix01_engine_meta.json = the engine's own log; mix01_meta.py rebuilds a mix_simple-style meta in /tmp/m1;
beatless.py; e4.py). Source tracks are no longer on disk (YouTube re-download blocked), so per-bar drums/vocals come from an
htdemucs split of the Mix 01 master. Overlap bars can't be split per deck, except onLHB->j9Au, where both decks have stem analyses.

**What the Mix 01 engine did:** It played every track almost whole, from the first phrase after the audio starts to the last phrase that leaves 16 bars before the end. Every blend was 16 bars on a phrase. The track was split at 180 Hz: the incoming highs came in on a sqrt curve over 8 bars, the bass swapped in 1 beat at bar 8, and then the outgoing highs faded over 8 bars. Each track was set to -16 LUFS. There was no crossfader lane, FX, ducking, loops, stems or scoring. Tracks played in a hand-picked order, and an onset xcorr nudged alignment by up to 20 ms.

| metric | Mix 01 | Mix 02 | new 03 (mixT) | mixLen15 |
|---|---|---|---|---|
| blend length (bars) | 16 ×6 | 40–56 | 16/32 | — |
| time with two decks playing | 8% | 27% | 12% | — |
| automation | 2 lanes/blend (highs, bass) | 51 travel/min | 1.4 | — |
| FX / ducking / stem loops | 0 / 0 / 0 | few | 0 | — |
| gain jumps >3 dB per min | 2.1 | 3.0 | 3.3 | — |
| body coverage (mean, min) | 0.99, 0.96 | 0.86 | 0.74 | — |
| minutes per track | 3.7 | 2.6 | 2.7 | — |
| longest lull (E4) | 5.4 bars @18:45, pass | 5.3 bars, pass | 17.5 bars, fail | — |
| drums-only run ≥8 bars | none, pass | none | — | — |
| bass overlap | ≤1 beat by construction | 0 | 0 | — |
| vocal-stem present in blend bars | 70% (one deck; can't split) | 7 bars two-deck | 6 bars | — |
| blend bars with drums in the mix at all | ≤35% | — | — | — |
| blend bars with **both** decks drumming | ≤35% (upper bound) | 66% | 46% | 48% |
| blends with ≥16 straight both-drumming bars | ≤1/6 (6:26) | 7/12 | 6/18 | 6/19 |
| beatless-led blends (>50% of overlap one/both decks beatless) | 4/6 | 3/10 | 8/18 | 9/19 |

The Mix 01 blends at 3:18, 11:35, 15:26 and 18:23 sit on drumless intros and outros (mix drums stem 25–36 dB under its median). 6:26 is drums all the way through, and 21:53 is half. The 18:23 deck-level check gives 0/16 both-drumming bars.

`test_mix02_traits.py` on Mix 01: body pass, drums-only pass, **32-bar share FAIL** (all blends are 16 bars). E4: pass.

### The 3 traits shared by Mix 01 and Mix 02 (later mixes lack the first two)
1. **Each track plays its body.** Coverage is 0.99 and 0.86, against 0.74 for new 03. The test already exists.
2. **No long energy lull.** Both max out around 5 bars, while old 03 and new 03 run 17+. The E4 test already exists.
3. **Plain processing.** Neither has drums-only stem loops, near-silence edits or per-beat ducking, and the bass never stacks. Covered by X1 and the drums-only test.

No new test was added. The extra traits are not shared: Mix 01 is 16-bar and mostly beatless, and Mix 02 is long and beat-on-beat. So the test file kept its name.

### Beatless blends: data and proposal (not applied)
- The hypothesis that the newer engine forbids beatless blends is not supported. mixT and mixLen15 already have 8–9 of about 19 beatless-led blends, more than Mix 02's 3/10.
- What the later mixes lack is long beat-on-beat overlap. Mix 02 has 7 of 12 blends with 16 or more both-drumming bars, against 6 of 18–19.
- Proposed additive tests, keeping every existing test:
  - `test_beat_on_beat_blends`: at least half the blends have 16 or more straight bars with both decks drumming. Mix 02 passes at 7/12, and mixT and mixLen15 fail. Mix 01 fails too. That's intended, because the listener wants more beat-on-beat than Mix 01.
  - `test_beatless_blend_cap`: no more than 1/3 of blends are beatless-led. Mix 02 passes at 0.30. Mix 01 (0.67), mixT and mixLen15 (0.44–0.47) fail. the listener's "about 1 in 4" would fail Mix 02 as well, so 1/3 is the honest cap from the data.
- Guardrail scope (proposal, not yet verified against the code): if F1, G1 or R1, or mix_simple's R1 predictor, score bars where a deck has no drums, limit them to both-drumming bars, because onset xcorr on a drumless deck is noise. E4 needs no change: Mix 01's beatless blends pass it.
