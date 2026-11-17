# Nightly protrans hill-climb n1117 (queued 2026-11-17 ~1:20 AM ET by the nightly routine)
Started only after the midnight tail-cap evals (tcbase_1116 / tcap4g_1116) finished, so no two tune runs overlap.
Result: protrans/results/hill_climb_n1117.json (+ line in results/hill_climb_nights.jsonl, log jobs/nightly-hill-n1117.log).
If a candidate was KEPT (held-out strictly up, n_fail not worse):
 1. write the delta into rules.json and recreate.py DEFAULTS (plan_search.py if present), with a comment line;
 2. run calibrated pytest; only keep if it passes;
 3. commit + merge to main, then run backup_mixer_to_git.sh;
 4. export best/worst held-out pro-vs-ours clip pairs; delete scratch renders;
 5. tell listener: old -> new held-out score, one plain line on what changed, clips attached.
If nothing kept: stay quiet (n1114-n1116 never ran, so this is not a plateau).
