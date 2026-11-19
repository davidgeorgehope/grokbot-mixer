#!/usr/bin/env python3
"""2026-11-19 RCA: today's pair (joe_syntax_hospital__12, Ghetto Blaster -> Seconds To Midnight) with SLOWDOWN=1 (rules.json + flag, not
written back). Same snippet convention as the daily clips (8 bars pre-roll, blend, 8 after; tick at the blend start; -14 LUFS) + blend_diag
PNG, the pair score, and the pro-vs-ours timeline PNG with the slowdown marked."""
import copy, json, os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import paths, render_planner_clips as RP, run_admitted_tune as T, score
OUT = os.path.join(paths.DELIVER); PID = 'joe_syntax_hospital__12'
RP.OUT_DIR = OUT; RP.DIAG_DIR = os.path.join(OUT, 'diagnostics')
rec = {r['id']: r for r in T.load_recs()}[PID]; rules = json.load(open(paths.RULES)); assert not rules.get('SLOWDOWN')
trial = copy.deepcopy(rules); trial['SLOWDOWN'] = 1
meta = RP.render_one(rec, trial, 'slowfix19', stem_name='rca_2026-11-19_slowfix')
sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a'); sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
w = meta['win']; print('META', json.dumps({k: meta.get(k) for k in ('mp3', 'png', 'win', 'fam', 'tick_timestamp', 'duration_s', 'lufs', 'bass_swap')}, default=str), flush=True)
subprocess.run([sys.executable, os.path.join(HERE, 'replica', 'halftime', 'pro_vs_ours_png.py'), os.path.join(OUT, 'diagnostics', 'rca_2026-11-19_slowfix_timeline.png'),
                rec['a']['yt'], rec['b']['yt'], json.dumps({'A': [189, 208], 'B': [140, 159], 'swapA': 193}),
                json.dumps({'ours default (heard)': {'A': [208, 224], 'B': [48, 64]}, 'SLOWDOWN fix': {'A': [int(w[1]) - int(w[4]), int(w[1])], 'B': [int(w[3]), int(w[3]) + int(w[4])]}}),
                'outgoing: Cyantific - Ghetto Blaster', 'incoming: S.P.Y - Seconds To Midnight'], check=True)
print('DONE')
