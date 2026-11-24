# RCA: why Mix 10 keeps failing in a new place

Written 2026-11-24 ET. Scope: every Mix 10 search, dry, render, and repair job from 11/20 to 11/24 (r1 to r6e).
Sources: `PROGRESS_mix10.md`, `jobs/*mix10*.log` and `.status`, `src2/plan_mix10_r*.json`, `src2/plan_search.py`, `src2/repair.py`, `mix10/render10*.sh`, `src/guardrails.py`, `src/build_qa/`.
Chart: `deliver/protrans/diagnostics/rca_2026-11-24_mix10_failure_loop.png` (script: `docs/rca_mix10_chart.py`).

## Short answer

Mix 10 has four judges of "good", and each one sees less than the next:

1. The pair table and the search score each blend with cheap proxies.
2. The dry check (`plan_search.dry` → `predict`) runs the meta-only release tests on a plan with no audio.
3. The render guardrails (`src/guardrails.py`) measure the mastered mix.
4. The release pytest (`src/build_qa`, plus `src/tests`) measures the rendered decks and mix.

Each fix so far made one judge agree with the next one for one fault. The next build then failed on a fault that only a later judge can see. Ten of the 22 audio faults in Mix 10 were invisible to every stage before render. All three plans that passed the dry check failed after render or by hand inspection. Pass rate from dry ALL OK to delivered: 0 of 3.

## 1. What each stage checks

### Pair table and search (`plan_search.table`, `search`)

- Key compatibility (`camelot_ok`), and ban lists (`--ban`, `seesaw_ban_10.json`, render-proved bad windows).
- Per-window features stored in the table: `voc`, `bob`, `mel`, `drift`, `beatless`, `dip`, `step`, `pen`, and the top-K windows per pair (`TABLE_K=40`).
- Path checks during search: `_drums_solo_ok` (an audibility model in which both decks count as audible for the whole blend), `_rep_prefix_ok`, the drop and outro fractions, coverage, and the `_window_entry_cliff` veto (added 11/23).
- Cost terms: the soft costs above plus pro shape and phase.

### Dry check (`predict`, 13 gates, about 92 s on an idle box)

`beatless`, `coverage`, `drums_only`, `anchors`, `vocal`, `keys`, `E4` (a level model), `entry_cliff`, `structure`, `fader_tail` (the fader curve, not the audio), `lengths_vary`, `seesaw`, and `variety`.
All of them read only the plan meta and the cached per-bar features. None of them reads rendered audio.

### Render guardrails (`src/guardrails.py`, 21 checks, 17 that fail)

Failing: E1, E2, E3, E4, N1 (grid and level step), G1, K1, L1, V1, P1, X1, C1, C2, S1, T1, J1, W1. Warning only: O1, R1, F1, BM1.

### Release pytest (`src/build_qa`, 46 tests, plus `src/tests` unit tests; 436 to 443 collected)

Audio-dependent tests include `test_no_bass_gap_in_overlaps`, `test_no_level_dip_at_swap`, `test_true_peak`, `test_mixdown_beats_aligned_every_overlap_bar`, `test_outgoing_audio_tail_never_drops_abruptly`, `test_beat_drift_across_transitions`, `test_no_unintentional_energy_drops`, `test_no_abrupt_cuts`, `test_backbeats_line_up_through_every_blend`, and `test_guardrails_zero_failures`.

### Matrix: which stage can see which Mix 10 fault

"exact" means the same function or measurement as the gate that failed. "proxy" means a cheaper estimate that can disagree. "blind" means no check.

| Fault class | Hits in Mix 10 | Table and search | Dry | Guardrails | Pytest | Caught at |
|---|---|---|---|---|---|---|
| Vocal clash | 6 (r1 2, r3 2, r4 2) | proxy | exact | exact | exact | dry |
| Drums-only stretch | 3 (r1, r3, r6 rewindow) | proxy | exact | blind | exact | dry |
| See-saw | 1 (r1) | proxy (ban list) | exact | exact | exact | dry |
| E4 quiet stretch | 1 (r6 rewindow) | blind | exact | exact | exact | dry |
| Structure (drop landing) | 1 (r6 rewindow) | proxy | exact | blind | exact | dry |
| E1 energy hole from a solo breakdown | 2 (r5 Hayling, r6 Memory Lane) | blind | blind | exact | exact | render, or by hand |
| N1 entry level step | 1 (r5) | proxy (`STEPMAX` 9.5 dB) | proxy (`entry_cliff`, added after r5) | exact (3.83 dB) | exact | render |
| N1 entry off grid | 1 (r6c) | blind | blind | exact | exact | render |
| Bass gap in overlap | 2 (r6c) | blind | blind | blind | exact | render |
| Level dip at EQ swap | 1 (r6c) | blind | blind | blind | exact | render |
| Beats not aligned in overlap | 1 (r6c) | blind | blind | proxy (F1, warning) | exact | render |
| Abrupt outgoing audio tail | 1 (r6c) | blind | proxy (fader curve) | blind | exact | render |
| True peak | 1 (r6c) | blind | blind | exact | exact | render |

Totals:

- 22 audio faults: 12 caught at dry, 10 caught only after render (9 by the render tests, 1 by hand inspection of the r6 Memory Lane window that would have failed E1).
- 8 of 13 fault classes have no pre-render check at all.
- Plans: 357,020 passed the pair table across r1 and r3 to r6. 56 orders were dry-tested. 3 passed dry (r5, r6, r6c). 0 passed render.
- Repair: 3 of 3 repair runs that were allowed to finish (r6, r6b, r6d) ended with untried or unresolved pairs on budget.
- Of the 12 dry-caught faults, 7 come from the search disagreeing with the dry check on the same fault (audibility model, top-K truncation, stale table, missing features). Only 5 are honest "this window is bad and the search knew it might be".

## 2. Root causes

### Root cause 1: the pre-render gate cannot see the audio faults that fail the build

`predict` runs only the meta-level tests. The render gates measure audio: per-bar loudness, sub-bass energy per deck, true peak, the rendered tail, and grid phase of the decks. A plan can pass dry and still be certain to fail. That happened to r5, r6, and r6c. Every fix of this kind (vocfix, `entry_cliff`, the solo-hole scan) added one more proxy for one more fault, so the next render failed on the next fault class in the blind rows.

### Root cause 2: the search uses a third, cheaper definition of "good" that drifts from the dry check

The search and the dry check disagreed on the same faults four separate ways:

- r1 and r3 drums-only: the search counts the fading outgoing deck as audible, and the dry check does not.
- r3 vocal: the search wrote windows that were not in the table's top-40, so their stored `voc` was never checked.
- r4 vocal: `search10.sh` re-sourced `env10.sh` and silently reverted `PAIR_TABLE` to the pre-vocfix table.
- r1 vocal: five tracks had lost `bar.voc`, and the dry check counts missing vocal data as vocal everywhere.

Thresholds also differ by design: `STEPMAX` is 9.5 dB in the search and 3.83 dB in N1. Each check exists in two or three copies, and the copies drift.

### Root cause 3: repair is local, greedy, slow, and checks its work with the blind judge

`repair.py` takes render culprits and tries new windows or swaps, one pair at a time. It accepts a try when the whole-mix dry check is `all_ok`. That dry check cannot see bass gaps, swap dips, grid offsets, or tails (root cause 1), so "fixed" is not evidence. Only another full render can confirm it.

Each try is a full-mix `mix_simple --dry` plus `predict`. That took 92 s on an idle box (r5) and 650 s per dry under load (r6: 1,305 s for two parallel dries; load average 10 to 11 on 8 cores from the nightly, corpus-v2, and Mix 10 at once). At about 10 minutes per try, the 1,800 s cap allowed 3 tries in r6d. Three pairs were fixed, three were marked `budget` with 0 tries, `resolved` was false, and no plan was written. r6 and r6b ended the same way, first on max-dry starvation and then on one unfixable pair. The 11/24 fix (fewest-tries-first, one guaranteed try per pair, always write the best plan and `.hist.json`) treats the starvation. It does not change the 10-minute cost per try or the blind acceptance test.

### Root cause 4: mix-level faults are treated as pair faults

Two of the render faults are not properties of a blend:

- E1 holes come from a track's own mid-track breakdown left solo between two blends (Hayling src bars 111 to 127, Memory Lane 128 to 143). No pair window can fix them. Only the order and the entry and exit points can. The search has no per-track "deep breakdown exposed solo" model, so every one of the 22,689 r5 pool plans exposed the Hayling hole, and every one of the 14,219 r6 pool plans with Memory Lane used the window that starts in its hole.
- True peak (−0.8 dBTP against −1.0) comes from master gain and MP3 encoding. `master.sh` limits at 0.78 linear (about −2.2 dBFS) and the MP3 encode overshoots. The fix is a fixed gain rule, not a blend change. Today it costs one extra QA pass ("remaster at 8.0").

### Contributing: the outer loop is expensive, so every mistake costs hours

The full-mix render takes about 3 minutes. Guardrails, per-deck renders, and pytest take 35 minutes to 4.5 hours under load. r6c went from plan to verdict in 4 h 51 m (02:21 to 07:12 ET). With that cost per lesson, and each render teaching one or two new fault classes, the loop moves slowly.

## 3. Structural fixes, ranked by impact

### Fix 1 (highest impact): a blend-clip verifier with a proof cache

Render each blend window by itself: 16 bars before the blend to 8 bars after, both decks, with the real fader, EQ swap, nudges, and master chain at the planned gain. Run the same per-transition audio checks on that clip that the release gates use: `checks.transitions()` rows (bass gap, swap dip, drift, beat alignment, tail), and guardrails E1, E3, N1, F1, G1, L1, C1, C2, S1, J1, and W1 for that transition. Cache the result keyed by `(a, b, window, nudge, gain, feature signature, check-code hash)`.

Use it in three places:

1. Search (lazy mode): after the search proposes a plan, verify its 23 blends in parallel. Add failing windows to the bad-window set and search again. Repeat until a plan has every blend proven.
2. Repair: accept a try only when the replaced blend passes the clip verifier, then run one full dry for the global gates. Seconds per try, instead of 10 minutes.
3. Over time, the cache fills with proven windows, so later mixes reuse them.

Cost estimate:

- Engineering: 1.5 to 2 days. `mix_simple` needs a `--clip a>b` mode (bar range plus context), and the check functions need to take a clip meta instead of a whole-mix meta.
- Runtime: about 30 to 60 s per blend on an idle core (render about 5 s, checks the rest). A 23-blend plan takes about 5 to 10 minutes on 4 cores. One full render plus QA takes 50 minutes to 5 hours.
- Eager prefill of the top 8 windows for every key-compatible pair (about 1,044 pairs, about 8,300 windows) would take about 70 to 140 CPU hours. Do not prefill. Use lazy verification and let the cache grow.

Expected effect on Mix 10: every r6c fault (bass gaps, swap dip, N1 grid, beat alignment, tail) and the r5 N1 step would have been caught before render. That covers 7 of the 10 render-only faults.

### Fix 2: one shared check library used by every stage

Define each check once in a registry with its input level: `track` (features), `blend` (clip audio), `plan` (meta), or `mix` (mastered audio). The search, the dry check, the clip verifier, the guardrails, and pytest call the same function with the same threshold. Add a contract test that fails when a release gate has no pre-render twin and is not declared `mix`-level. This ends the drift in root cause 2 (`STEPMAX` 9.5 against 3.83, two audibility models, top-K truncation).

Hash the check code and the feature content into `table_key`, so a stale table or env re-source cannot be reused silently. Make `search10.sh`-style wrappers refuse to start when `PAIR_TABLE` does not match the crate and feature signature.

Cost: about 1 day, mostly moving code. No threshold changes.

### Fix 3: handle mix-level faults where they actually live

- Solo breakdown exposure: precompute a per-track "deep breakdown" mask (bars that are more than 6 dB under the track's 30 s median with drums gone, from the cached per-bar features). Make it a hard veto in the search: a plan may not leave those bars solo. This is the same E1 rule, applied to the track. It would have rejected Hayling and Memory Lane placements in seconds instead of after a render. Cost: half a day.
- True peak: choose the master gain with a short pre-pass. Encode the loudest 60 s of the raw mix at the candidate gain, measure the true peak, and step down until the true peak is at or under −1.0 dBTP. The approved mastering chain stays unchanged. Only the gain value is chosen by rule. Cost: a few hours.

### Fix 4: make repair global and fast

- Use the clip verifier (Fix 1) as the per-try check. Run the full dry once per accepted round.
- When a pair fails on every window tried, send it back to the search as a banned pair with the bad-window set, instead of more local swaps.
- Run dry and QA jobs only when the load average is under the core count, or at a lower nice level than the nightly. Dry time was 7 times longer under load (92 s against 650 s).

Cost: half a day to 1 day, after Fix 1.

### Order and total cost

| Order | Fix | Engineering | Faults it would have caught early |
|---|---|---|---|
| 1 | Blend-clip verifier and proof cache | 1.5 to 2 days | 7 of 10 render-only faults |
| 2 | Solo breakdown veto and true-peak gain rule | about 1 day | the other 3 (2 E1, 1 true peak) |
| 3 | Shared check library and content-hashed cache keys | about 1 day | 7 of 12 dry faults (search and dry drift) |
| 4 | Global, clip-checked repair and load-aware scheduling | 0.5 to 1 day | the 3 repair budget failures |

Total: about 4 to 5 days of work. After that, a full render becomes a confirmation step instead of the place where the system learns.

## 4. What did not cause this

- Thresholds were not too tight. Every gate is at its calibrated value (pro p95 where calibrated), and no fix loosened one.
- The track list was not the main problem. Two tracks (Hayling and Memory Lane) had real solo-breakdown holes, but those are the class that Fix 3 handles.
- The 11/21 to 11/23 usage outage slowed r3 (search depth 20 went from 25,816 s to 108,200 s). It did not cause a fault.

## Numbers used

- Search table-feasible plans: r1 83,068; r3 118,788; r4 100,743; r5 22,689; r6 31,732 (total 357,020). r2 was stopped early.
- Orders dry-tested: r1 4, r3 6, r4 40, r5 2, r6 2, r6 rewindow 1, r6c 1 (56).
- Dry time per order: 92 s to 167 s (r1, r4, r5), 650 s (r6, under load).
- r5 render: 7 failed, 424 passed (5 of the failures were unrelated test bugs, since fixed). Guardrails E1 14:24, N1 18:45.
- r6c render: 6 failed, 430 passed. Faults: bass gaps at 15:22 and 40:44, swap dip at 30:53, N1 grid at 21:22, beat alignment at 11:43, abrupt tail at 53:42, true peak −0.8 dBTP.
- Repair: r6 43, 0, and 0 tries across its 3 pairs. r6b 11, 2, and 13 tries, one pair unresolved. r6d 5 dries in 54 min, 3 pairs at 0 tries.
