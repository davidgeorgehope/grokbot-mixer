# Learned ranker and corpus_v2

the listener, 15 November 2026, agreed to a learned-model approach after every
hand-written rule overfit the 33-pair pro corpus. Step 1 is scaling the
data. Step 2 (a small CPU ranker) starts only after 150 accepted
transitions.

## Isolation

The new dataset lives in `protrans/corpus_v2/` and is separate from the
33-pair scoring cohort. The pipeline never writes `protrans/rules.json`,
`protrans/results/admitted.json`, the official `clips/` or `lib/` trees,
or the 33-pair score checkpoints. Quality gates are unchanged: locate
z ≥ 6 and cc ≥ 0.28, native BPM 169–179, talkover veto, real-blend v3
(≥ 2.5 bars at −12 dB). Rejects are logged in
`protrans/corpus_v2/rejected.jsonl`.

The six official scoring mixes (Hybrid Minds UKF, Joe Syntax Hospital,
Netsky Hospital Classics, Maduk Liquicity Lunar 2025, Pola & Bryson
Puzzlewood, Wilkinson Boomtown 2026) are not re-ingested and are not
used to train the ranker. They stay an eval-only set.

## How a mix is admitted

Same method as the existing protrans harvesting path (`fetch.meta_remote` /
`fetch.ytdlp_remote` on the configured download host, `version_match`,
`talkover.check_clip`, `real_blend.assess`):

1. Find a tracklisted live DJ mix (YouTube chapters or timestamped
   description; yearmixes and megamixes are out).
2. Keep Goldilocks neighbours only (outgoing listed for 90–280 s, no
   IDs, no bootlegs).
3. Fetch both studio sources through the existing yt-dlp flow.
4. Admit only when alignment confidence is high and the real-blend and
   talkover gates pass.
5. Record the cue bar and section, outgoing exit section, blend length,
   rise and tail, per-band EQ, and per-track features (drops,
   breakdowns, intro length, bass per section, energy, BPM).
6. Archive source audio, the mix, and accepted clips to Google Drive
   (`gdrive:DJ Mixes Archive/protrans/corpus_v2/`), verify the copy, and
   delete the local audio so the box stays lean.

## Split

Held-out is reserved by mix, not by transition, with a fixed seed
(20261115). At least 20% of mixes with an accepted transition are
held-out. No model sees those mixes during training.

## Ranker (only at 150+ accepted)

A small CPU ranker (LightGBM LambdaMART, or a histogram-boosting
fallback) scores the engine's candidate windows per pair — cue window,
SNAP_IN or not, and the long hold — by similarity to what the pro did.
It is behind a flag with defaults unchanged. We report how often the
top pick matches the pro's incoming cue section on the held-out mixes,
and (when that flagged scorer run is done) held-out 33-pair scores
against the current floor. The flag stays off unless that evaluation
clears the floor with no failures.

## v0 ranker (17 November 2026)

the listener asked to hear a per-pair predictor sooner than 150 accepted
transitions, so a first model was trained on what was already in hand:
78 corpus_v2 accepted blends (mix-level hold-out, seed 20261115, 20%
of mixes) plus the official 33-pair TRAIN split only (21 pairs). The
official held-out mixes were not used as labels. The sixth official
scoring mixes stay eval-only.

The flag is `RANKER=1` (also `rules['RANKER']` / `rules['ranker']`).
It is off by default. When it is on, the model scores the engine's
candidate windows plus SNAP_IN, hold and tail-length options and plays
the top one for that pair. `rules.json` was not changed.

- LightGBM LambdaMART, CPU only. Model: `protrans/ranker/ranker_v0.txt`.
- Training rows: 82 transitions, 3056 candidate options.
- Corpus held-out (17 transitions / 4 mixes): top-1 incoming section
  match 0.4118, incoming cue within 8 bars 0.3529.
- Corpus train cue-within-8 0.6557 (some overfitting, as expected at
  this size).
- Top features (gain): incoming position in the track (`in_rel`,
  `in_begin`), outgoing position (`out_rel`), incoming track length,
  outgoing bass vs its body, incoming intro length, which drop the
  cue sits in, then `snap_in`.
- 33-pair eval with `BLEND_LOCK` on: held-out **30.28**, train **27.94**,
  0 fails. Floor is held-out 34.07 / train 32.40 / 0 fails. The flag
  stays off. About 40–80 labelled blends is too few for this to beat
  the current rules: mid-track `drop1_end` picks helped a few pairs
  (Joe Syntax 01 30.24 → 39.04, Pola & Bryson 02 20.54 → 31.63,
  Cinnamon → Together 26.37 → 28.71) and hurt others hard
  (We Are One → Ghetto Blaster 60.51 → 24.89, ukf 08 42.98 → 18.74).
- Retrain when corpus_v2 reaches 150 accepted.

## Commands

Long job (status file + webhook):

```
bash jobs/runjob.sh corpus-v2 python3 protrans/run_corpus_v2.py all
```

Resumable pieces: `discover`, `ingest`, `split`, `train`. Progress is
`protrans/corpus_v2/progress.json`; the compact manifest is
`protrans/corpus_v2/manifest.json`.

## Tracklist parsing (15 November 2026)

The first corpus-v2 pass ingested YouTube *chapters* whenever there were
four or more of them. On Hospital Podcasts those chapters are often
talk-segment labels ("Politics", "Cmon Cookies", "Etherwood and chat
debate"), not "Artist - Title" lines, while the official tracklist sat
in the description without timestamps. The resolver then searched those
junk or partial strings and almost every candidate failed with "no
confident search hit." Alignment quality gates were not the cause and
were not loosened.

The parser now keeps a line only when it has a timestamp and an
"Artist - Title" shape. It prefers a description or an official
Tracklist: block over chapters, and may bind official titles to chapter
*times* when they clearly line up. A mix needs at least eight such
lines. Source search uses the full "Artist - Title" string. Rejects
continue to be logged.

## Title normalizer and throughput (16 November 2026)

Track names from chapters often carry a leading `//`, bullet, list number, or leftover timestamp. Those tokens made source search miss (score -25 on a clean DC Breaks title). `fetch.normalize_track_title` now strips that junk before search, while leaving cue timestamps intact for the line parser and leaving artist names like `1991 - Nine Clouds` alone. Copies off the download host retry the copy only, without re-encoding, and subsequent ingest prefetches two studio sources at a time. Alignment and the quality gates are unchanged. A slash-resolve retry walks earlier rejects whose reason was a resolve miss with a `//` prefix.

## Studio-track sources (17 November 2026)

Source search still starts on YouTube (`ytsearch` on the download host),
with the same title/artist/duration scoring and the same confidence
floor (score ≥ 2). When YouTube has no confident hit, the resolver
tries, in order:

1. YouTube (`ytsearch`) — unchanged first source
2. SoundCloud (`yt-dlp scsearch` on the download host)
3. Bandcamp (Bandcamp's public track search, also run on the download
   host, then fetched with yt-dlp)

Tracklist label tags such as `[Forthcoming Fokuz]` or `[Celsius]` are
stripped before search and scoring only (stored titles stay as written).
Version tags like `[VIP]` or `[Remix]` are kept, because the scorer
uses them. The confidence floor is still score ≥ 2.

A later source is used only if every earlier source missed or returned
only clips shorter than the blend window. SoundCloud and Bandcamp often
serve 30–60 s previews of forthcoming tunes; those are rejected when
they are shorter than the analysis clip (`extract.PRE` + `extract.POST`,
64 s) or the listed slot for that track (outgoing 90–280 s, incoming
until the next cue). Duration is checked again after the download, so
a preview that advertises a full-track length still gets dropped.

Accepted rows record `source` and `url` on each side (`a` / `b`),
alongside the existing `yt` id (a filename key; YouTube video ids are
unchanged). Previously rejected "no confident search hit" transitions
are retried once with the new sources (`retry-resolve` / `resume`).
Quality gates (locate, BPM, talkover, real-blend) are unchanged.
