# RCA 2026-11-26: ridegate live holdout (2nd opening)

Holdout-3 finished `rc=0` at 10:37 America/New_York and did **not** pass. The pinned live render had already matched the map (`25/25`). `rules.json` was not edited. The holdout was not reopened after this look.

Raw exit+cue vs default: **-3.61 [-8.66, 0.05]** (upper bound already ≥ 0). After official hard-check veto: **-0.06 [-0.23, 0.0]**. Promotion rule is CI entirely below 0.

## 1. Veto summary: `checked 7, veto 34, not_rendered 29`

The n1126 locked holdout is **56 pairs / 12 mixes**. Ridegate on the official built rows moved **36** and abstained on **20**. Pack vs `picker_1126` holdout: **56/56**.

`eval_gate.py` has **no render budget**. The log is `pairs 152` (33 protrans + 119 corpus_v2 with audio) then `jobs 24`. `ONLY` was all 56 holdout ids; only **12 pairs** have both tracks on disk, so 12 × 2 arms = 24 jobs. Those 12 are exactly the four mixes that had audio at the 11-19 first opening (`hospital_records_Lm2VlTogWvY`, `hospital_records_zYANUM_lubI`, `liquicity_EuPkz0GFI4g`, `liquicity_nYOcD3qTdg0`). The other eight mixes (44 pairs) are missing **78** unique source files (needed 101 yts; 23 present in `feat_lib` / `nightly_1119_work/src`).

Of the 36 moved pairs:

| bucket | n | meaning |
|---|---|---|
| `not_rendered` | 29 | no local audio, never sent to `eval_gate` |
| `checked` | 7 | rendered under `RIDEGATE=1` |
| `not_applied` | 5 | rendered window ≠ official pack window |
| `new_hard_fail` | 1 | live hard-failed and default did not (`nYOcD3qTdg0__34`; also in the 5 not-applied) |
| applied, clean | 2 | `EuPkz0GFI4g__38` and `__48` |
| `veto` | 34 | 29 not_rendered + 5 not_applied |

Veto policy (same as 11-19): a new hard fail, **or a pick that did not apply**, **or missing default hard-check**, reverts that pair to default before the CI. So 34/36 moved pairs were forced back to default, and the after-veto CI collapsed toward zero. That is conservative, but it is **not** 34 hard-check failures.

This is **not** an `eval_gate` budget bug. It is a **procedure mismatch**:

- The 11-19 first opening **defined** the locked set as the 14 pairs / 4 mixes that had audio (“2 of 9 rendered picks newly hard-failed”).
- The n1126 holdout grew to 56 pairs / 12 mixes without restoring the new mixes’ audio. CI was computed on all 56, then 29 official moves were silently treated as vetoes because they were never rendered.

A second, separate bug made the 7 “checked” numbers the wrong windows (next section). And `hospital_records_zYANUM_lubI__01` hard-failed under `RIDEGATE=1` but is **invisible** in `new_hard_fail`: the official pack abstained, so the veto loop skipped it.

Latent `eval_gate` issue (did not bite this run, because all defaults finished before the live arm reused the same tags): the worker tag is `g{variant[:4]}{i}`, and both `n1126h_default` and `n1126h_ridegate_live` share the prefix `n112`, so they write `/tmp/protrans_bench/gn112*`. Tags must include the full variant name.

## 2. The two hard fails (audio, not just the flag)

**All 12 live windows, and all 12 defaults, are 16-bar blends.** Window format is `['n', exit_bar, None, incoming_start, X]`. The `48` that shows up on 10/12 live renders is the **incoming cue start bar**, not a 48-bar blend. Defaults use incoming starts 0/8/16/24/32. Bar length 1.379 s (174 BPM); every blend is 22.07 s.

### `hospital_records_zYANUM_lubI__01` — pumping, just over p95

- Official pack: **abstain** (`p_leave=0.525`, theta=0.6). Should have rendered the default.
- Live render: `['n', 184, None, 48, 16]` (exit 169, cue 49). Default (passed): `['n', 176, None, 32, 16]` (exit 161, cue 33).
- Official hard check, re-run on the rendered decks: `pumping=True`, `pump_db=4.7` vs pro **p95=4.54** (margin **+0.16 dB**). Beat clash / bass hole / incoming vanish all clean. Default `pump_db=3.7` (under p95).
- Measured V-dip on the summed decks: **4.71 dB** at **track bar 175** (clip bar 15; **+20.69 s** into the 44 s clip; 7 bars into the blend). Neighbors −16.0 / −16.9 dB, trough −21.7 dB. Real dip, not a test artifact.
- Placement: blend **track bars 168–184**, clip time **11.03–33.10 s**. Outgoing `GE0_v5mRz34`: drop `40–176`, `outro_start=168`. Incoming `Li4QIYhK_gg`: `intro_end=drop1=48`, drop `48–96`. So the live window starts exactly at the outgoing outro and lands exactly on the incoming first drop. The dip sits on the outgoing drop edge (bar 175, one bar before the drop run ends). Default would have stayed inside that drop (`160–176`) and cued the incoming intro (`32–48`).
- This is **ride over-firing**, not a longer blend. On live features `p_leave` fell to **0.405** and the pack rode; the official built row abstained. Because the veto loop skipped official abstains, this fail did not enter `new_hard_fail`.

### `liquicity_nYOcD3qTdg0__34` — beat clash (half-beat)

- Official pack want: `['n', 136, None, 32, 16]` (exit 121, cue 33, `p_leave=0.264`). **Never rendered.**
- Live render: `['n', 128, None, 48, 16]` (exit 113, cue 49). Default (passed): `['n', 128, None, 0, 16]` (same exit, cue 1).
- Official hard check, re-run on the rendered decks: `beat_clash=True`, `halfbeat_fail=True`. Meta: `lag_ms=127.71`, `dphase_ms=-150.9` (−0.438 beats), `r0=0.274`, `rh=0.351`, `strength=4.342`. Pump 4.0 dB (under p95 4.54). Default had no clash, pump 2.5 dB.
- Placement: blend **track bars 112–128**, clip time **11.03–33.10 s**. Outgoing `EIWyuA1eFd4`: still in **drop2** (`104–136`; `outro_start=120`). Incoming `gOpAr0UiT6Q`: **entire 16 bars are the breakdown** (`breakdown=48`, `drop2=64`, drops `16–48` and `64–112`). First half of the blend: outgoing still −18 to −25 dB over a quiet incoming breakdown (−45 to −28 dB).
- This is the same shape as the listener’s 10:24 America/New_York note on `hybrid_minds_ukf__40`, logged in `protrans/log.jsonl` as `outgoing_drums_linger_under_incoming_breakdown`. The live cue snapped to bar 48 (the breakdown), while the official want (`ib=32`) would have landed in the end of the incoming first drop. Default cued the intro (`ib=0`).

## 3. Why live disagreed with the official 56/56 pack decisions

`ridegate_live._index_built()` **skips `set=='holdout'`** (so the live path cannot be used as a per-pair holdout map). At holdout render time, `maybe_apply` therefore built a fresh `row_from_default` from **live** `sections.get()` + the engine default.

On the 12 pairs that had audio, that live-feature predict **exactly** matches every rendered window, and **10/12 disagree** with the official built-row decision. Five official abstains became rides (`p_leave` systematically lower, e.g. 0.525→0.405, 0.626→0.421, 0.580→0.273; theta=0.6). Ten of twelve live cues landed on incoming bar 48 (drop1 or breakdown), vs a spread of 0–32 on default.

So the hard-check veto was not testing the windows whose CI was reported. It tested a more aggressive live-feature policy, then marked mismatches `not_applied` and reverted them, and never scored the official want window on `nYOcD3qTdg0__34`.

## 4. Proposed general fix (no pair pins)

1. **Evaluate the windows the CI is about.** For a holdout / pack veto, inject the official built-row pack window (or use the built snapshot row in `row_for_render` when one exists, including holdout — features, not a map). Compute after-veto CI only from pairs whose official window was actually rendered and hard-checked. Missing audio must not be coded as a hard-check veto that zeroes the CI; either restore sources, or explicitly restrict the set (as 11-19 did: 14 pairs / 4 mixes).
2. **Don’t skip holdout in `_index_built` for feature lookup.** Leaving it out is what turned a 56/56 pack into 10/12 different rendered windows and into ride over-firing. Unseen pairs with no snapshot row still go through `row_from_default`.
3. **General linger guard** (picker or legal check, not a pair list): deprefer / refuse a cue that sits in the incoming breakdown while the outgoing is still in a drop. That is the listener’s `outgoing_drums_linger_under_incoming_breakdown` note, and it is exactly `nYOcD3qTdg0__34`.
4. **Fix `eval_gate` tags** so variant names cannot collide (`g{variant[:4]}{i}` is unsafe).

## 5. Next validation (do not reopen the holdout)

Do **not** reopen the locked holdout. A properly sized non-holdout check, once the corpus-v2 job (still running at the time of this write-up) is no longer using the machine:

- **Set:** `picker_1126_fresh.json` — 18 pairs, one mix (`ukf_drum_bass_wVp_VlkWqxI`), already used for the n1126 fresh-mix pass. Audio is local. Not the locked Liquicity/Hospital set.
- **Arms:** default vs `RIDEGATE=1`, unique `eval_gate` tags, official hard checks.
- **Report:** (a) live `maybe_apply` window vs pack-on-built-row window, (b) new official hard fails vs default, (c) whether live cues land in incoming breakdowns under an outgoing drop, (d) v1 and hard-check counts only — no promotion decision.

A later, larger corpus_v2 non-holdout slice with local audio can follow the same script. No heavy job was launched in this chunk.

## Files

- `protrans/replica/nightly_1126_work/holdout_1126_live_summary.json`
- `protrans/replica/nightly_1126_work/hc_veto_1126_holdout.json`
- `protrans/replica/gate_ckpt/n1126h_{default,ridegate_live}.jsonl`
- On-disk live audio (default overwrote the same tags, then live wrote last): `/tmp/protrans_bench/gn1122_*` (`zYANUM__01`), `/tmp/protrans_bench/gn11211_*` (`nYOcD3qTdg0__34`)
