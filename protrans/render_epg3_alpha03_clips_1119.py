#!/usr/bin/env python3
"""Default vs EPG (strict EXITPOS_GATE) clips + PNGs for alpha_rhythm_imZjEt78YXs__03,
the dev pair whose default hard-fails (beat clash) and EPG does not.
Uses the already-scored eval snippets (8-bar pre-roll, tick at the blend). rules.json is not written."""
import json, os, sys, shutil
import numpy as np
import soundfile as sf
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths, render_planner_clips as RP

RP.OUT_DIR = os.path.join(paths.DELIVER)
RP.DIAG_DIR = os.path.join(RP.OUT_DIR, 'diagnostics')
os.makedirs(RP.OUT_DIR, exist_ok=True)
os.makedirs(RP.DIAG_DIR, exist_ok=True)

SRC_A = os.path.join(paths.ROOT, 'corpus_v2', 'feat_lib', 'OYVnBH2kaE4.m4a')
SRC_B = os.path.join(paths.ROOT, 'corpus_v2', 'feat_lib', 'sUa4H7HaJ9Q.m4a')
# No isolated pro clip for this corpus-v2 pair (eval_gate sets pro_clip=None).
JOBS = [
    dict(stem='rca_2026-11-19_epg_alpha03_default',
         ours='/tmp/protrans_bench/gdefa46.mp3',
         meta='/tmp/protrans_bench/gdefa46_OYVnBH2kaE4_sUa4H7HaJ9Q_meta.json',
         win=['n', 256, None, 32, 16], fam='nat_short', hard_fail=True),
    dict(stem='rca_2026-11-19_epg_alpha03_gate',
         ours='/tmp/protrans_bench/gepg31.mp3',
         meta='/tmp/protrans_bench/gepg31_OYVnBH2kaE4_sUa4H7HaJ9Q_meta.json',
         win=['n', 240, None, 32, 16], fam='nat_short', hard_fail=False),
]
PAIR = 'Larigold - Project Horizon [Celsius] -> SMP - Brighter Days on the Surface ft. Matt Freeman [Fokuz]'
out = []
for j in JOBS:
    y, sr = sf.read(j['ours'])
    M = json.load(open(j['meta']))
    bar = float(M.get('bar_sec') or RP._bar_sec(M))
    tick_s = 8 * bar
    y2 = RP._tick(y, sr, tick_s)
    y2, meas, gain = RP._loudness_match(y2, sr, RP.TARGET_LUFS)
    stem = os.path.join(RP.OUT_DIR, j['stem'])
    wav = stem + '.wav'
    mp3 = stem + '.mp3'
    sf.write(wav, y2, sr)
    RP._to_mp3(wav, mp3)
    os.remove(wav)
    png = os.path.join(RP.DIAG_DIR, j['stem'] + '.png')
    png2 = stem + '.png'
    title = (f"alpha_rhythm_imZjEt78YXs__03 {PAIR} fam={j['fam']} win={j['win']} "
             f"hard_fail={j['hard_fail']}")
    cwd = os.getcwd(); sys.path.insert(0, paths.SRC2); os.chdir(paths.SRC2)
    try:
        import blend_diag
        blend_diag.figure(M, 0, png, title, pro=None, src_a=SRC_A, src_b=SRC_B, ours=j['ours'])
        if os.path.abspath(png) != os.path.abspath(png2):
            shutil.copy2(png, png2)
    finally:
        os.chdir(cwd)
    import pyloudnorm as pyln
    lufs = float(pyln.Meter(sr).integrated_loudness(np.asarray(y2, float)))
    rec = dict(id='alpha_rhythm_imZjEt78YXs__03', pair=PAIR, win=j['win'], fam=j['fam'],
               hard_fail=j['hard_fail'], mp3=mp3, png=png2, diag_png=png,
               duration_s=round(len(y2)/float(sr), 3), lufs=round(lufs, 2),
               tick_timestamp=f"{int(tick_s)//60}:{int(tick_s)%60:02d}",
               tick_s=round(tick_s, 3), src=j['ours'])
    print(json.dumps(rec), flush=True)
    out.append(rec)
json.dump(out, open(os.path.join(RP.OUT_DIR, 'rca_2026-11-19_epg3_alpha03_clips.json'), 'w'), indent=1)
print('DONE')
