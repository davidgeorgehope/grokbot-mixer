# Scorer audit vs the listener's ears, plus a first try at copying what pros actually do (2026-11-18)

Written 2026-11-18, around 7:10–8:30 PM ET. Read-only on `protrans/rules.json` and the defaults: nothing in either changed.
New engine behaviour is behind `REPLICA=1`, which is off by default.

## TL;DR

- **Verdict: trust the protrans score only partly.** It does pick up blends that are clearly broken (4/4 "fixed vs the clip he rated 2/5 or that clashed").
  It is close to a coin flip on the choices that matter: between two decent options it agreed with the listener **2 of 5** times.
  It has **no correlation** with his blind-test ratings (Spearman −0.14, n=7).
- The score measures how much our clip *looks like the pro clip*, not whether it sounds good.
  The clips the listener couldn't tell from the pro did score higher (37.6 vs 32.1 mean). But his 4/5 clips scored anywhere from 20 to 42.
  His 3/5 clip with a beat clash (Nov 17) was the highest-scoring daily at 56.7.
- **Misleading parts:** `outgoing_cut` (1/5 on close calls), `stem_curves` (2/5; rating rho −0.30), `beat_identity` (0/2), and `score_v2` (5/9 overall).
  **Parts that line up with him:** `beat_align` (8/9 pairs, 4/5 close calls) and `bass_swap` (5/5 close calls, but 2/4 on easy ones).
  Every split here has n ≤ 9, so none of it is significant.
- **A simpler question tracked his choices better.** We asked "how many bars away from the pro's exit and cue points is our window?"
  That agreed with the listener on **3/3** A/Bs where the window changed (planner ukf__19, planner v2 ukf__25, ranker ukf__25). The total score got 2/3.
- **What pros do vs what we do (biggest finding).** In 29 of the 33 protrans pro blends (88%), the outgoing track still had more than 40 bars of music left when the next track came in (median 92 bars, about 2 min).
  Our default plays the outgoing through its outro: the blend starts about 16 bars before its music ends. Only 13 of the 76 corpus_v2 transitions are classic outro→intro.
  This is the "safe and boring" the listener hears.

## 1. Labels found

| source | rows | can the protrans scorer score it? |
|---|---|---|
| `ratings.jsonl`, mix01–06 era (overall / timestamp ratings, ears false positives) | 15 | No: there's no pro clip to compare against |
| `ratings.jsonl`, early A/Bs (bass swap, echo-out, ab1–4, escalations 1–3, Mix 06 a+c) | 11 (+1 note) | No pro reference |
| `ratings.jsonl`, Nov 4–6 daily versions (3 pairs × 2) | 6 | No pro reference |
| `ratings.jsonl`, planner listens Nov 15 (ukf__19, ukf__25, ukf25_v2) | 3 opinions | **Yes** |
| `ratings.jsonl`, ranker v0 A/B ukf__25 (prefers B_ranker) | 1 | **Yes** |
| `protrans/log.jsonl`, daily blind tests Nov 9–17 | 9 (7 rated, 2 "can't tell"; 6 spotted the pro, 1 fooled) | **Yes** |
| `protrans/log.jsonl`, Nov 11 RCA verdicts (engine "pretty good", phrase_cut "sounds off", long 3.5, long_fix ">4, best yet") | 4 | **Yes** |
| `protrans/log.jsonl`, Nov 17 RCA fix ("beat clash is gone") | 1 | **Yes** |
| `/workspace/private`: daily keys (Nov 12–18), mix08 long A/B key, dropswap key | answer keys | mix08 long A/B and dropswap: no recorded answer; Nov 18 daily not answered yet |

There are about 60 human judgements in total. Only **19 clips** (9 blind-test "ours" clips plus 10 follow-up variants) and **9 preference pairs** can be scored, because the scorer needs a pro clip.
That is a structural limitation: the protrans score can never judge the blends in a real mix we deliver.

How each clip was scored: `audit/scorer_audit.py` re-scores the *delivered* mp3 against `rec['pro_clip']` with the current scorer (`gain-events-v3-beatid`, bands, with sources). Output is in `protrans/audit/scored_labels.json`.
The numbers differ a little from the logged ones because the delivered clips are loudness-matched, trimmed and carry a tick. For example, Nov 13 logged 12.19 and re-scored 20.14; Nov 17 logged 58.04 and re-scored 56.72.

## 2. Agreement

Preference pairs (the listener's preferred clip listed first). "Agree" means the preferred clip got the higher total score.

| preferred > other | total | agree |
|---|---|---|
| rca1111 engine ("pretty good") > phrase_cut ("sounds off") | 33.97 vs 36.18 | ✗ |
| rca1111 long (3.5) > original daily (2) | 48.22 vs 26.96 | ✓ |
| rca1111 long_fix ("best yet") > long (3.5) | 47.30 vs 48.22 | ✗ |
| rca1111 long_fix > original daily | 47.30 vs 26.96 | ✓ |
| rca1111 engine > original daily | 33.97 vs 26.96 | ✓ |
| planner ukf__19 ("really nice") > daily Nov 14 (2, "quite bad") | 25.73 vs 27.67 | ✗ |
| planner ukf25 v2 (4) > planner ukf25 v1 (3.5) | 35.98 vs 32.17 | ✓ |
| ranker B ("much much better") > default A ("super boring") | 27.94 vs 26.38 | ✓ (margin 1.6) |
| Nov 17 RCA fix ("clash gone") > Nov 17 daily (3) | 60.53 vs 56.72 | ✓ |

Overall the total score agrees on **6/9** pairs. That splits into **4/4** easy pairs (re-renders of the same window that fixed a 2/5 or a clash) and **2/5** close calls.
On the ranker pair: per pair, the scorer did rank the ranker version slightly higher. Across the cohort, ranker v0 lost (train 27.94 / held-out 30.28 vs 32.40 / 34.07).
So the "scorer said ranker is worse" verdict came from the cohort average, not from this pair.

Blind tests (n=7 rated):
- Spearman correlation of total score with his rating is −0.14 (p 0.77). For score_v2 it's +0.02.
- Ratings by score: the 4/5 clips scored 20.1, 25.9, 35.1 and 42.2. The 2/5 clips scored 27.0 and 27.7. The 3/5 clip scored 56.7.
- Clips he couldn't identify as ours (Nov 9 unsure, Nov 12 fooled, Nov 16 can't tell) averaged 37.6. Clips he spotted averaged 32.1.
  So the score does track "sounds like the pro" a bit, but not "sounds good".

Components (pairwise agreement out of 9 / close calls out of 5 / rating Spearman):

| component (weight) | all pairs | close calls | rating rho | reading |
|---|---|---|---|---|
| stem_curves (0.28) | 6/9 | 2/5 | −0.30 | Rewards matching the pro's energy shape. Misleading on taste |
| deck_curves (0.22) | 6/9 | 2/5 | +0.34 | Mixed |
| beat_align (0.15) | 8/9 | 4/5 | +0.26 | Best match to his ears (a correctness signal) |
| bass_swap (0.13) | 7/9 | 5/5 | +0.18 | Good on close calls, odd on easy ones |
| outgoing_cut (0.12) | 5/9 | 1/5 | +0.18 | Misleading |
| blend_length (0.10) | 6/9 | 3/5 | +0.02 | Noise |
| beat_identity (inside beat_align) | 4/6 | 0/2 | n/a | Misleading on close calls |
| score_v2 | 5/9 | 2/5 | +0.02 | No better than v3 |

The single biggest weight (stem_curves, 0.28) is the one that most rewards safe, pro-shaped energy curves. It is also negatively correlated with his ratings.

**Sample-size warning:** 9 pairs and 7 ratings, almost all from three pairs (ukf__25, js08, ukf__19).
Any component chosen from this table is chosen on the same data it is judged by. Treat these as hints, not findings.

## 3. Prototype: a better evaluation (not wired into tuning)

Instead of one similarity number:
1. **Correctness gates (pass/fail, never averaged):** beat clash (beat_align / per-bar offset), bass hole (summed-lows dip), level pumping. These are the things the listener always flags.
2. **Decision match to the pro (reported as bars):** outgoing exit, incoming cue, overlap length and bass-swap timing, measured from the pro clip (`replica/extract_protrans.py`).
   `audit/decision_windows.py` compares our *known* render windows with the pro's measured entry. It agreed with the listener on 3/3 pairs where the window changed (ukf__19 planner 63.5 vs 143.5 bars off; ukf25 v2 18.7 vs 143.9; ranker 63.9 vs 237.3).
3. **the listener's A/B as the final judge,** logged as labels for the ranker.
4. Keep the similarity score as a diagnostic only. Drop `outgoing_cut` and `stem_curves` from any keep/revert decision.

Decision match plus the beat_align tie-break gets 8/9 on the pairs. That is optimistic, because beat_align was picked by looking at the same pairs.
Caveat: we tried extracting decisions from *our* short clips with the same locator (`audit/decision_match.json`), but it's unreliable. In a 35–44 s clip, repeated drops look the same and the locator can land on the wrong copy (Nov 11 put our exit 50 bars off).
So for our renders we use the known engine window. The same ambiguity may affect a few pro rows (ukf__25 incoming at bar 190 looks suspicious).

## 4. Pro-replication work (started, behind `REPLICA=1`)

### Data that exists today
- **corpus_v2:** 78 accepted, 76 with usable features, 16 mixes, 7 DJs (Alpha Rhythm 20, UKF 16, SuicideSheeep 11, TheHeshBesh 10, Hospital 7, Liquicity 7, Fryett 5).
  Each row has the cue at the tracklist time (both tracks' bar and section), overlap bars, per-band rise/tail summaries, and full section maps.
  It does **not** have per-bar per-deck gain curves or the bass-swap bar. Only 4 mixes' clips and 6 full mixes are still on disk.
  The corpus-v2 job is **not running**. `jobs/corpus-v2.status` says `failed rc=1` (2026-11-17 9:41 AM ET): downloads fail because the download folder on the residential download host is missing, and progress stopped at 78 accepted (last update 2026-11-17 9:58 PM ET).
- **protrans:** 33 pairs with a pro clip and both sources. `replica/extract_protrans.py` now measures, per pair, where the incoming entered, when the outgoing was gone, the bass-swap bar and the overlap, all in track bars, plus per-deck curves. Output: `replica/protrans_decisions.json`, 33/33 extracted.
- **Features available per track:** bars, drops, breakdown, intro length, outro start, music end, and bass per section (corpus `sections_from_bar` and engine `sections.get`).

### Milestones (what was tried, why it failed, what changed)
1. **v0 regression** (`replica/fit.py`): predict exit bars-left, cue relative to drop1 and overlap from track structure, with kNN, LightGBM and a median model, evaluated leave-one-mix-out on corpus_v2.
   **Failed.** Every model was no better than the engine default. Exit error was about 50 bars, and the cue pair landed within 8 bars on 0–4%.
   Why: the exit is multimodal (pros leave at one of several drops or breakdowns), so a regression to the middle lands between them.
2. **v0b technique classifier** (`replica/style_clf.py`): mid-track exit or not, drop-anchored entry or not.
   **Failed.** It did worse than always guessing the majority answer (0.36 vs 0.57).
   Why: technique is mostly the DJ's habit, not the tracks. Alpha Rhythm exits mid-track in 0/20 transitions; Liquicity and Fryett in 100%. So "style" has to be an input knob, not something we predict from the tracks.
3. **v1 structural chooser** (`replica/struct_ranker.py`): pick which section boundary the pro used, evaluated leave-one-DJ-out.
   - Exit: within 16 bars on 33% of protrans pairs vs 6% for the default. But it was worse on corpus_v2, which is skewed by Alpha Rhythm.
   - Cue: worse than the default.
   - A plain heuristic did as well as the model on exits: start the blend at the outgoing's breakdown. That's within 16 bars on 36% of protrans and 36% of corpus_v2, with protrans median error 22 vs 76 bars for the default.
   - For the incoming cue, the current `drop1 − 16` was the best rule tested: 45% within 16 bars, ahead of drop1, drop2 and last-drop variants.
4. **REPLICA v1 rule** (`src2/replica_rule.py`, hooks in `src2/mix_simple.py` and `protrans/recreate.py`, flag `REPLICA`).
   The outgoing blends out from its breakdown (window end = breakdown + X), and the incoming drop lands at the blend end.
   Rendered A/B on **ukf__19** (the listener rated our default 2/5): the replica window was ['n',128,None,32,16] vs default ['n',176,None,32,16]. Similarity score 50.48 vs 27.93. The exit is 17 bars from the pro vs 65.
   On **js08** (rated 2/5) it **did not apply**: engine sections merge Shine In into one long drop (no second drop), so it fell back to the default. Those two clips are identical and are not for the listener.
5. **REPLICA v2:** when engine sections show a single drop, fall back to `structure.py` phase labels to find the breakdown.
   js08 now gets ['n',144,None,40,16]. Score 32.04 vs 32.66 (flat). The exit is 19 bars from the pro vs 99.
6. **Cohort check** (`eval_cohort.py rp1118_replica_v2`, rules copy `replica/rules_replica_v2.json`): see section 5.

### Known risks in the replica clips (check by ear)
- ukf__19 replica: the summed lows dip 39 dB at the blend start (outgoing breakdown plus incoming intro, both thin) until the incoming drop at the blend end. That's musically a breakdown, but it could read as a hole.
- js08: the per-bar beat-offset panel swings up to about ±150 ms on *both* the default and the replica render. It looks like a measurement issue on this pair (weak kick in xcorr), not a replica regression, but listen for a clash.

### Plan from here
- Treat style as an input. Add a "which DJ to imitate" knob (for example Hospital or Hybrid Minds), and use per-DJ priors for exit, overlap and swap within that style.
- Re-extract corpus_v2 decisions from audio (entry, gone, swap, per-deck curves) once downloads work again, so the 76+ rows have the same precise labels as protrans.
- Turn each A/B the listener answers into labels: pairwise preference plus the decision deltas.
- Evaluate by decision match to the pro, correctness gates and his ears, not the similarity mean.
- Ranker retrain still waits for about 150 accepted transitions (currently 78, job stopped).


## 5. REPLICA v2 cohort (33 protrans pairs, `jobs/replica-cohort-1118`, finished 7:35 PM ET)

| | default (d1118_base) | REPLICA=1 |
|---|---|---|
| applied | n/a | 30/33 (3 fell back to nat_short) |
| fails | 0 | 0 |
| similarity train / held-out | 32.40 / 34.07 | 31.69 / 32.81 |
| exit within 16 bars of the pro | 6% | **27%** |
| median exit error (bars) | 57.7 | **28.4** |
| cue within 16 bars of the pro | 36% | 39% |
| exit closer / further than default | n/a | 23 closer, 7 further |
| similarity per pair up / down | n/a | 14 up, 16 down |

Read: REPLICA moves our exit decision much closer to what pros actually did. The cue is unchanged by design.
On the old similarity mean it is a little lower (held-out −1.26). Under the old gate that would read "failed, revert".
This audit says that gate isn't a trustworthy judge of taste. So the next step is the listener's ears on the A/B clips, not a threshold.
It stays off by default. Per-pair table: `replica/cohort_decisions.json`.

## Files
- `protrans/audit/`: `scorer_audit.py`, `scored_labels.json`, `analyze.py`, `analysis.json`, `decision_windows.py` / `.json`, `decision_match.py` / `.json` (unreliable, see §3)
- `protrans/replica/`: `decisions.py`, `fit.py` → `eval_v0.json`, `style_clf.py` → `eval_v0b_style.json`, `struct_ranker.py` → `eval_v1_struct.json`, `extract_protrans.py` → `protrans_decisions.json`, `render_ab.py`, `rules_replica_v2.json`
- Engine (flagged, off by default): `src2/replica_rule.py`, a hook in `src2/mix_simple.py` (`pair_cands`), and a hook plus the `REPLICA` env key in `protrans/recreate.py`
- Clips: `deliver/research/2026-11-18/replica_v1/` (pair1 = ukf__19 is real; pair2 is identical, don't send) and `replica_v2/` (js08). Keys: `/workspace/private/research_2026-11-18_replica_v{1,2}_key.json`
