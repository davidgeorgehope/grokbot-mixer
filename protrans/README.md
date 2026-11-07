# Pro-transition recreation

The engine tries to recreate a real DJ's blend from the two studio tracks
alone. We score how close it got, and we only keep general rule changes that
still hold up on DJs the tuner never trained on.

## Why this does not cheat

- The engine (`recreate.py`) never reads the pro clip. It gets the two source
  tracks and a coarse hint: how long track A had been playing when the
  tracklist lists track B. That hint is a soft cost, not a pin.
- Tuning may edit `rules.json` only (shared fade / bass-swap / hint weight /
  family preference). No per-track windows or timestamps.
- The split is **by DJ**, not by mix or by transition. A change is kept only
  if the held-out mean does not drop (`tune.py`). Every try is logged in
  `logs/tune_log.jsonl` with train and test scores.
- The similarity metric's weights in `score.py` are fixed. The tuner cannot
  move them to flatter a change.

The daily A/B taste model trained on the listener's ratings is shelved
(`PREF_W` stays 0 in the mix engine). It was around chance on leave-one-out,
so it is not used here.

## Layout

| path | role |
|---|---|
| `corpus.json` | Mix catalog, DJ split, source ids, timestamps |
| `rules.json` | General engine params the tuner may change |
| `fetch.py` | Download via the residential host (`HOST` in `config.env`) and yt-dlp with browser cookies |
| `extract.py` | Cut the pro clip around the incoming tracklist time |
| `recreate.py` | Blind candidate search + snippet render (`blend_bench` / `mix_simple`) |
| `score.py` | 0–100 similarity with a breakdown |
| `tune.py` | One pass of general-rule variants, accept iff held-out mean holds |
| `run.py` | `extract` / `sanity` / `baseline` / `tune` / `all` |
| `cleanup.py` | Drop full-mix downloads, stems, and scored renders |

Work files live under `protrans/` and `/tmp/protrans_*`. The harness does not
rewrite Mix 07 plans or existing `src2` audio. New `src2` symlinks and
stretched wavs it creates are deleted after scoring.

## Disk

Keep:

- Pro clips in `clips/`
- Source tracks the corpus actually needs, in `lib/`
- Two example pairs in `/workspace/mixes/deliver/protrans/`

Delete after use:

- Full mix files downloaded into `cache/mixes/` (shared copies under
  `pro_sets/` are left alone)
- Demucs/stem caches and `/tmp/protrans_*` renders
- Stretched `src2/st/` wavs this harness wrote

Prefer section downloads over hour-long mixes when a mix is not already on disk.

## Scoring

Over the blend window:

1. Per-stem energy curves (drums, bass, vocals, melody). Demucs when enabled;
   otherwise band-split proxies. Per-deck curves when both sources can be
   aligned into the clip.
2. Beat/phrase alignment (kick-band lag, 8 ms scale).
3. Bass-swap time (first bar incoming bass overtakes outgoing).
4. Outgoing cut time (first −6 dB from the pre-blend level).
5. Overall blend length.

Sanity: a clip vs itself should land near 100; a random other transition should
score clearly lower (`tests/test_score.py` and `run.py sanity`).

## Commands

From `/workspace/mixes`:

```
python3 protrans/tests/test_score.py
python3 protrans/run.py extract
python3 protrans/run.py sanity
python3 protrans/run.py baseline
python3 protrans/run.py tune
```

`corpus.json` `run_now` lists the pairs to recreate this run (small on
purpose: only those sources are fetched). `extract` still cuts every
adjacent listed pair from mixes we already have.

## Corpus

See `corpus.json`. Twelve official YouTube uploads across Hospital, Liquicity,
UKF, and live sets. Train/test is by DJ. A BBC Radio 1 / 1Xtra Friction mix
with official timestamps was not verified; a Netsky Boiler Room full set was
not verified either (the Hospital Classics livestream is listed instead).

## This run (7 Nov 2026, America/New_York)

Split is by DJ. Train this run: London Elektricity (Hospital Podcast 393, already on disk).
Held-out test: Wilkinson (Boomtown 2026, already on disk). Other listed DJs stay
in the catalog for later; we did not download those full mixes.

14 adjacent clips were cut (9 train, 5 test). Recreation ran on four pairs
with studio sources only:

- train `hospital_podcast393__05` Fred V — Cosmic Flowchart → S.P.Y — Don't You Leave Me (Dead Man's Chest Remix)
- train `hospital_podcast393__06` Don't You Leave Me → Grafix — Radiance
- test `wilkinson_boomtown2026__10` Yosemite (Wilkinson Remix) → Wilkinson — Used To This
- test `wilkinson_boomtown2026__33` Ultraviolet → Afterglow

Sanity on real clips: identity 100.0, random other transition 49.11.

### Scores

| | train mean | test mean |
|---|---|---|
| baseline (`BASS_SWAP_BARS=4`) | 29.52 | 26.01 |
| after (`BASS_SWAP_BARS=2`) | 29.55 | 34.97 |

Baseline per pair: train 28.87 (nat_long) and 30.17 (nat_long); test 23.83 (out_loop) and 28.19 (lx_beat).

Tried and not kept (held-out mean did not beat the 2-bar swap, or matched baseline):
`swap_pos_021` (SWAP_POS 0.21) train 29.52 / test 26.01; `hint_stronger` (hint_weight 0.4) train 29.52 / test 26.01.

The kept change is general: bass handoff length 4 bars → 2 bars in `rules.json`.
No per-track pins. Log: `logs/tune_log.jsonl`.

Example pairs (pro vs ours, after the kept rule):

- `/workspace/mixes/deliver/protrans/ex1_hospital_podcast393__05_pro.mp3`
- `/workspace/mixes/deliver/protrans/ex1_hospital_podcast393__05_ours.mp3`
- `/workspace/mixes/deliver/protrans/ex2_wilkinson_boomtown2026__10_pro.mp3`
- `/workspace/mixes/deliver/protrans/ex2_wilkinson_boomtown2026__10_ours.mp3`

### Catalog (official YouTube pages)

- Hospital Podcast 393 with London Elektricity — https://www.youtube.com/watch?v=2wXDFi2eL1U
- Hospital Podcast 400 with London Elektricity — https://www.youtube.com/watch?v=az6BZJAQCGo
- Wilkinson, Live from Boomtown 2026 — https://www.youtube.com/watch?v=ifOtJV-xZ-U
- Hospital Podcast 425 Grafix Takeover — https://www.youtube.com/watch?v=XR2FdYeJ_4U
- Hospital Podcast 452 with Whiney — https://www.youtube.com/watch?v=GwCR07oXGZs
- Hospital Podcast with Degs #478 — https://www.youtube.com/watch?v=QkzMkgg2flQ
- Liquid Drum and Bass Mix by Hybrid Minds — https://www.youtube.com/watch?v=Ea4ngKLPNMQ
- Liquicity Yearmix 2024 (Maduk) — https://www.youtube.com/watch?v=VPBc1316Tro
- Liquicity Yearmix 2025 (Maduk) — https://www.youtube.com/watch?v=g1yq9w7moFI
- Liquicity Yearmix 2022 (Andromedik) — https://www.youtube.com/watch?v=W7Q3QdLuW6w
- Joe Syntax Hospital Mix — https://www.youtube.com/watch?v=zgKc7vQNrrE
- Netsky Livestream (Hospital Classics Set) — https://www.youtube.com/watch?v=0yIOFIW4Eow

### Problems

- Scores are well below the ~80 target. Energy-curve overlap is in the 50s; beat alignment and event terms (bass-swap time, outgoing cut, blend length) often score near 0 because the pro extract and our snippet are different lengths and are not yet time-aligned before those detectors run.
- Sources were scored with band proxies, not Demucs stems (disk). `mix_simple` also needs `bar.drums`; the harness fills drums/bass/voc from those bands when stems are absent.
- `prep.py` rejected S.P.Y — Don't You Leave Me (Dead Man's Chest Remix) as not drum-and-bass (detector ~161.5). The harness force-stretched it to 174 so the engine could still blend; that official upload may be a jungle cut the DJ then sped up.
- Candidate search can crash on tracks missing a Camelot entry; `src/tests/checks.py` now treats a missing key as "not ok" instead of throwing. Mix plans that already have keys are unchanged.
- Nightly yt-dlp on the download machine pointed at a missing Python, so fetch uses Homebrew Python 3.13 plus the nightly package and Safari cookies. Older brew yt-dlp hit HTTP 403.
- This run did not yet test a third DJ (Grafix / Liquicity / UKF). Doing that needs more full-mix audio or section pulls.
- Yearmixes are catalogued but not extracted here (very short slots). Dimension / Old Guard remain unlistable (no reliable tracklist).
