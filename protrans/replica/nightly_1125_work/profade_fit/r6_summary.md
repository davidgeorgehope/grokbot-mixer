# r6 early-exit pro fade grid (dev-27)

Written 2026-11-26 10:05 EST (America/New_York). `fit-pro-fade-6` finished rc=0 at 09:41 EST. This note only reads that job's outputs. It does not render, and it does not touch the live ridegate render job.

All three arms used the same 27 windows (`dev27_picks_ee_r7.json`), with `EARLY_EXIT=1`, `TAIL_EXIT=6`, and `PRO_FADE_RESPECT_EXIT=1`. Base has pro fade off. fit2 and ex35 use the learned fade (`ENTRY_DB=-8.5`, `SHELF_DB=-10`, `HIGH_OFS=7`, `BASS_CUT_DB=-24`); ex35 is fit2 with `EXIT_SLOPE=3.5` instead of 2.5. 26/27 windows are 16-bar `nat_short`; one (`liquiddnbftw_m6m836_Ic7M__16`) is a 32-bar `cue_early`. Official v1/v2 are higher-is-better. Hard checks are official `hardcheck.check` (pro p95). l1a is the audible-L1 gate (not an official hard check); it stayed at 0.

## Totals (n=27, 0 errors)

| arm | official v1 | official v2 | mae_bass | mae_all | mae_mids | mae_high | hard fails | hole | pump | vanish | beat | l1 raw | l1a |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| r6_ee_base | 41.59 | 42.75 | 10.39 | 2.96 | 3.45 | 6.28 | 5 | 1 | 4 | 0 | 0 | 1 | 0 |
| r6_ee_fit2 | 41.37 | 42.13 | 9.55 | 3.24 | 3.52 | 3.52 | 4 | 1 | 3 | 0 | 0 | 2 | 0 |
| r6_ee_ex35 | 41.48 | 42.25 | 9.44 | 3.05 | 3.30 | 3.34 | 4 | 1 | 3 | 0 | 0 | 3 | 0 |

Versus base, ex35 is a little worse on official v1 (−0.11) and v2 (−0.50), clearly closer on bass MAE (−0.95) and high-band curve MAE (6.28 → 3.34), and one official hard fail lighter (5 → 4). Incoming vanish is 0 on every arm. l1a is 0 on every arm; raw L1 flags go 1 → 3 on ex35, all in the quiet-bass region the audible gate already ignores. fit2 is the same hard-check picture as ex35 and a bit worse on every score and MAE than ex35, so ex35 remains the better of the two fade shapes (same conclusion as the earlier r5 grid without early exit).

Hard-fail IDs:

- Hole (all three arms): `liquiddnbftw_m6m836_Ic7M__03`.
- Pump (all three): `liquiddnbftw_m6m836_Ic7M__10`, `alpha_rhythm_u3OiUhgnfkE__04`, `alpha_rhythm_u3OiUhgnfkE__07`.
- Pump on base only, cleared by both fade arms: `alpha_rhythm_u3OiUhgnfkE__11` (pump 5.2 dB on base, just over the 4.54 pro p95; 4.4 dB on fit2/ex35).

## How much the fade actually changes the audio

The r6 renderer deleted the mp3s after scoring, so this is not a waveform residual like the pola02 A/B (that pair differed only 10–32 s, about 1 dB of level, residual about −28 dB, and the listener heard a near-tie). Two proxies, both computed here, no new renders:

1. **Xfader-shape residual** (reconstructed). Equal-power deck gains from `FADE=long` (`LONG_XP=0.45`, solo clipped by window length) versus the stored ex35 pro-fade xfader, with `RESPECT_EXIT` honoured when `exit_bar` is set. Residual is 10 log10 of mean uncorrelated mix-difference power over the blend. “Over a meaningful span” means at least 6 s (about 4.3 bars at 174 bpm) where the instantaneous residual is greater than −20 dB.
   - 22/27 (81%) meet that fader-shape test. Every unclipped 16-bar window lands on the same number: residual −16.5 dB, outgoing gain gap 3.2 dB, loud span 7.2 s. The six `RESPECT_EXIT` clips are quieter (residual −17.5 to −19.5 dB); five of those six fall short of the 6 s span.
   - Treat 81% as an **upper bound on the fader shape alone**. It is almost the same curve on every 16-bar window, and it does not include the +7 dB high lane or the −24 dB bass cut, which can add more (or, if the fade has no room, still add nothing).

2. **Realized official v1 movement**, scored on the actual r6 renders (this is what moved when the files still existed):
   - 11/27 (41%) have |Δv1| ≥ 1.0; 8 of those 11 pass official hard checks and l1a.
   - 3/27 (11%) have |Δv1| ≥ 2.0; 2 of those 3 are clean (`__14` +7.07, `__04` −9.97). The third is `__10` (+2.77) and still pumps.
   - Median |Δv1| = 0.74; mean Δv1 = −0.12. The pola02 near-tie was Δv1 ≈ 0.2 with a −28 dB waveform residual, so a 0.2–0.5 official-v1 gap is not evidence the fade is hearable.

`PRO_FADE_RESPECT_EXIT` clipped 6/27 fades (`exit_bar` set). That is the pola02 failure mode: the early exit / tail already used the window, and the learned fade had almost no room left. The only 32-bar blend (`__16`) is in that clipped set (window 128–160, fade ends at 144).

## A/B candidates (ex35 vs base, official hard checks clean, l1a clean)

Do not send another near-tie. Preferred order:

1. **`liquiddnbftw_m6m836_Ic7M__14`** — the clearest real change that still passes. Official v1 62.69 → 69.76 (+7.07), official v2 70.33 → 77.55, bass MAE 10.20 → 9.22, hole/pump/vanish clean, l1a 0. Sixteen-bar window 192–208, fade clipped at 206. Use this one first.
2. **`sirenity_ofcHup56lME__23`** — official v1 42.27 → 44.22 (+1.95), official v2 45.66 → 46.09, bass MAE 10.42 → 9.46, unclipped 16-bar window, all hard checks clean, l1a 0.
3. **`sirenity_ofcHup56lME__52`** — official v1 45.20 → 46.67 (+1.47), official v2 slightly down (45.52 → 45.20), bass MAE 10.42 → 9.46, unclipped 16-bar, official hard checks clean, l1a 1.38 (under the 3 dB audible gate).
4. **`liquiddnbftw_m6m836_Ic7M__16`** — the only 32-bar window, and the closest to the listener's "does the amount over time match the pros?" question. Official v1 29.84 → 30.80 (+0.96), official v2 27.48 → 27.94, bass MAE 10.64 → 10.17, hard checks clean. `RESPECT_EXIT` cuts the fade at bar 144 (half the window). Xfader residual −19.5 dB over 7.2 s — just over the −20 dB line, so measure the actual clips before sending. This is the one most at risk of another pola02-like near-tie.

Do **not** send **`liquiddnbftw_m6m836_Ic7M__04`** as a “is the fade better?” test: official v1 53.48 → 43.51 (−9.97) and official v2 49.84 → 35.73, with clean hard checks. If we ever listen to it, it is a “the fade can also hurt” check, not a promo clip.

Before any of these go out, measure the two mp3s the same way as pola02 (span, level gap, residual dB) and drop the pair if they are not audibly distinct across a meaningful span.

## Recommendation

**n1127 shadow, keep the flag off, do not drop the idea, do not turn it on by default, and do not restrict it to “ride blends only” from this cohort.**

Why not drop: bass and high-band curve match to the pro improved, one official pump was cleared (`__11`, 5.2 → 4.4 dB), vanish and l1a stayed at 0, and at least one clean blend (`__14`) moved official v1 by seven points. That is a real effect, just not a free win.

Why not default on: official v1/v2 on the 27 went slightly *down*, one blend lost about 10 official v1 points, and most of this set is 16-bar outro-intro windows where `RESPECT_EXIT` plus a short window leave a pola02-like risk if we A/B at random.

Why not “ride blends only”: these 27 are almost all 16-bar `nat_short` outros, not mid-track rides, so this grid cannot support that split. The one longer window (`__16`) is the more relevant case for “fade amount over time,” and even there the exit was clipped to 16 bars.

What to do: keep the existing n1127 shadow spec (ee_r7 + ex35 + `RESPECT_EXIT=1`, still off by default). If an A/B is worth the listener's ear, render `__14` first (and only if a preflight residual says the clips actually differ). Leave `rules.json` and defaults alone.

Supporting numbers: `rows.jsonl` (r6 summaries and per-pair rows) and `r6_curve_diff.json` (xfader residual plus official-v1 deltas) beside this file.
