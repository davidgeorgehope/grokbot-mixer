#!/usr/bin/env python3
"""Clips + PNGs for netsky_hospital_classics__02 (loser) and pola_bryson_puzzlewood__02 (winner):
default vs the epg2 EXITPOS_GATE window. Tick at the blend after an 8-bar pre-roll. rules.json is not written."""
import copy, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import paths, render_planner_clips as RP, run_admitted_tune as T
RP.OUT_DIR = os.path.join(paths.DELIVER)
RP.DIAG_DIR = os.path.join(RP.OUT_DIR, 'diagnostics')
recs = {r['id']: r for r in T.load_recs()}
rules = json.load(open(paths.RULES))
assert not rules.get('EXITPOS') and not rules.get('EXITPOS_GATE') and not rules.get('SLOWDOWN')
jobs = [
    ('netsky_hospital_classics__02', 'rca_2026-11-19_epg_netsky02_default', None),
    ('netsky_hospital_classics__02', 'rca_2026-11-19_epg_netsky02_gate', {'EXITPOS': 1, 'EXITPOS_GATE': 1}),
    ('pola_bryson_puzzlewood__02', 'rca_2026-11-19_epg_pola02_default', None),
    ('pola_bryson_puzzlewood__02', 'rca_2026-11-19_epg_pola02_gate', {'EXITPOS': 1, 'EXITPOS_GATE': 1}),
]
out = []
for pid, stem, flags in jobs:
    rec = recs[pid]
    r = copy.deepcopy(rules)
    if flags: r.update(flags)
    tag = 'epg2c_' + stem[-20:]
    meta = RP.render_one(rec, r, tag, stem_name=stem)
    keep = {k: meta.get(k) for k in ('id', 'mp3', 'png', 'diag_png', 'win', 'fam', 'tick_timestamp', 'duration_s', 'lufs')}
    print(json.dumps(keep, default=str), flush=True)
    out.append(keep)
json.dump(out, open(os.path.join(RP.OUT_DIR, 'rca_2026-11-19_epg2_clips.json'), 'w'), indent=1)
print('DONE')
