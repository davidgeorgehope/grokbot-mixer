# Promotion: RIDEGATE + lock + pump previews (2026-11-26)

**Rollback:** `RIDEGATE_OFF=1` (or `git revert` of the promotion commit recorded in the mixer backup) restores the pre-ridegate engine default. `RIDEGATE_EE` and `LINGER_GUARD` stay off.

the listener (12:52 America/New_York): if it is meaningfully better, ship it. The old promotion rule (two nights + fresh + locked holdout CI + live path) is retired for this decision.

## What changed

`RIDEGATE`, `RIDEGATE_LOCK`, and `RIDEGATE_PUMP` are on in `protrans/rules.json` and `recreate.DEFAULTS`. The live (non-map) path in `recreate.py` / `mix_simple.py` is therefore the engine default. n1127's baseline is this default; remaining shadows (`ridegate_lock_pump_ee`, `profade_ex35`, and the three epg arms) compare against it.

## Evidence

- **n1125 and n1126 qualifying-night wins** on the ridegate arm (consecutive nights).
- Dev exit+cue vs default **−2.44** with 95% CI **[−4.08, −0.82]**, entirely below 0 (n1126; also beat majority −2.01 [−3.55, −0.50]). n1125 was −3.39 [−5.32, −1.38].
- Official 33-pair hard fails **2 vs default 5** (n1126 rendered ridegate).
- Live-path fresh-mix fixes (18-pair ukf set): lock preview caught `__09` (beat_clash residual −158.19 ms → default window, residual none); both-thin pump preview caught `__23` (pump 4.82 → default window, pump 2.9). No official-ride false blocks.

Fresh-set sanity (all 18 ukf pairs, eval `n1126f_rgdef`, empty variant so `rules.json` is the default): **hard fails 1 vs old default 4** (only `__16`, which already failed the old default on the same window). No new pump, clash, or vanish faults; `__14` clash and `__27`/`__30` pumps cleared. `__09` and `__23` fell back to the passing default windows. drum_linger is higher on three passing pairs (`__03` 12, `__22` 11, `__30` 12 vs p95 8.80) and structural linger fires on `__11` (8 vs p95 5.4); `LINGER_GUARD` was left off by design and these did not create official hard fails. Not reverted.
