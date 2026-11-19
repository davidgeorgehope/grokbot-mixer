#!/usr/bin/env python3
"""2026-11-19: two short clips (8-bar pre-roll, blend, 8 after, tick at the blend, -14 LUFS) + blend_diag PNGs
for joe_syntax_hospital__01, the clean earlier-exit case (default vs EXITPOS). rules.json is not written."""
import copy, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import paths, render_planner_clips as RP, run_admitted_tune as T
OUT = os.path.join(paths.DELIVER)
RP.OUT_DIR = OUT
RP.DIAG_DIR = os.path.join(OUT, 'diagnostics')
PID = 'joe_syntax_hospital__01'
rec = {r['id']: r for r in T.load_recs()}[PID]
rules = json.load(open(paths.RULES))
assert not rules.get('EXITPOS') and not rules.get('EXITPOS_GATE')
meta_d = RP.render_one(rec, rules, 'epg19def', stem_name='rca_2026-11-19_ep_js01_default')
print('DEFAULT', json.dumps({k: meta_d.get(k) for k in ('mp3', 'png', 'win', 'fam', 'tick_timestamp', 'duration_s')}, default=str), flush=True)
trial = copy.deepcopy(rules); trial['EXITPOS'] = 1
meta_e = RP.render_one(rec, trial, 'epg19ep', stem_name='rca_2026-11-19_ep_js01_ep')
print('EP', json.dumps({k: meta_e.get(k) for k in ('mp3', 'png', 'win', 'fam', 'tick_timestamp', 'duration_s')}, default=str), flush=True)
print('DONE')
