# Interior snare wander on bars 130–134: estimator noise, not a unique ours looseness

The listen-clip median gate under `BREAKDOWN_PHASE_EST` is **4.4 ms** (isolated snares, 5 official-loud bars, same 40 ms line). The *spread* on those bars is large: ours `[-92.9, -43.5, 49.3, 91.4, 4.4]`. This note asks whether that wander is real audible looseness or a weak estimator on a half-time breakdown.

## Same bars in the pro

The pro clip, placed onto the same outgoing source bars 130–134, wanders the same way:

| src bar | ours snare xcorr (ms) | pro snare xcorr (ms) | ours peak ratio | pro peak ratio |
| ---: | ---: | ---: | ---: | ---: |
| 130 | -92.9 | -56.6 | 1.17 | 1.27 |
| 131 | -43.5 | -85.6 | 1.14 | 1.21 |
| 132 | 49.3 | 2.9 | 1.09 | 1.03 |
| 133 | 91.4 | 74.0 | 1.11 | 1.03 |
| 134 | 4.4 | -47.9 | 1.12 | 1.09 |

- Ours: n=5, median **4.4**, std 65.3, range [-92.9, 91.4], only 1/5 bars inside ±40 ms.
- Pro: n=5, median **-47.9**, std 56.1, range [-85.6, 74.0], only 1/5 bars inside ±40 ms.

A “every bar within 40 ms” or “median of these 5 bars must pass” interior rule would **fail the pro** (-47.9). The 40 ms line is a median over the estimator’s usable bars; tightening it to a per-bar cap is not the agreed pass line, and it would reject the reference mix.

## Why the lag hops: the 1-bar snare xcorr is nearly incoherent

On both mixes, 1-bar isolated-snare xcorr (1500–5000 Hz) has no sharp peak:

- Normalized correlation ~0.07–0.10.
- The winning peak is only 3–27% taller than the next peak (ratio 1.03–1.27).
- The plotted xcorr traces for bars 130–134 are multimodal noise on **both** ours (solid) and the pro (dashed). See `snare_wander_pro_vs_ours.png`.

S.P.Y’s post-drop-1 breakdown is a section-local half-time groove. Snares are sparse; incoming snare energy is still low on 130–131 (eB ~5–10× quieter than eA). A 1-bar window then locks onto whichever sidelobe is slightly taller, so the lag walks around by ~80–90 ms even when the records are already locked.

Onset-picked snares near beats 2 and 4 (independent of xcorr) show the same pattern: ours median **-5.1** ms, pro **-11.6** ms, both with large spread (ours std 62, pro std 74), and beats 2 and 4 often disagree *inside one bar*. The onset picker is not finding a stable backbeat pair in this groove either — on both mixes.

Constant-phase `beat_identity` of our render vs the pro remains **7.3 ms**.

## The render’s `interior_ok=false` (-171.2 ms) is a different, expected fail

`offset_interior_ms = -171.2` is official 1-bar **kick+snare** xcorr (prefer_interior) over the overlap, not the snare-only estimator. That half-beat hop is the original bug: breakdown kicks sit off a correct drop-locked grid. It is why `BREAKDOWN_PHASE_EST` exists. It is not a new interior failure of the snare family.

Measuring snare xcorr on *all* 32 overlap bars in ours also yields median **-171.2**. That is an artifact of the outgoing tail: `tail_exit` cuts S.P.Y at mix bar **142**, and every bar from 142–159 then sticks at -171.2 (no outgoing snare left to correlate). The pro keeps both decks in and stays a noisy wander about 0 (full-overlap snare median **-0.8** ms, family median **-2.9** ms, pass). Official-loud filtering (both decks within 20 dB) is what restricts ours to bars 130–134; that is the same loud-bar rule official kick+snare uses.

## Verdict

The 130–134 snare wander is **estimator noise from sparse half-time snares**, not a looseness unique to our mix. The pro shows the same wander, the same weak xcorr peaks, and would fail any per-bar interior cap. The honest 40 ms *median* gate already passes (ours 4.4 ms on the loud bars; pro -3.6 / -2.9 ms over the full overlap). Do not loosen the 40 ms line; do not treat the kick+snare -171.2 figure as a snare-family fail.

Plot and numbers: `snare_wander_pro_vs_ours.png`, `snare_wander_pro_vs_ours.json`.
