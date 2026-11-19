#!/usr/bin/env python3
"""Default vs epg_drop clips + PNGs for two pairs the listener has not heard yet:
joe_syntax_hospital__13 (S.P.Y Seconds To Midnight -> London Elektricity Meteorites)
and hybrid_minds_ukf__00 (SpectraSoul Away With Me -> EastColors Keys).
Uses already-rendered eval snippets (8-bar pre-roll, tick at the blend). rules.json is not written."""
import json, os, sys, shutil
import numpy as np
import soundfile as sf
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths, render_planner_clips as RP

RP.OUT_DIR = os.path.join(paths.DELIVER)
RP.DIAG_DIR = os.path.join(RP.OUT_DIR, "diagnostics")
os.makedirs(RP.OUT_DIR, exist_ok=True)
os.makedirs(RP.DIAG_DIR, exist_ok=True)

LIB = os.path.join(paths.ROOT, "lib")
PAIRS = [
    dict(id="joe_syntax_hospital__13",
         pair="S.P.Y - Seconds To Midnight -> London Elektricity - Meteorites (Danny Byrd Remix)",
         ya="u6cggHmZEAs", yb="SqzxwPEa-DI",
         default=dict(stem="rca_2026-11-19_epgdrop_js13_default",
                      ours="/tmp/protrans_bench/gdefa14.mp3",
                      meta="/tmp/protrans_bench/gdefa14_u6cggHmZEAs_SqzxwPEa-DI_meta.json",
                      win=["n", 256, None, 48, 16], fam="nat_short", hard_fail=False),
         drop=dict(stem="rca_2026-11-19_epgdrop_js13_drop",
                   ours="/tmp/protrans_bench/gepg26.mp3",
                   meta="/tmp/protrans_bench/gepg26_u6cggHmZEAs_SqzxwPEa-DI_meta.json",
                   win=["n", 224, None, 48, 16], fam="nat_short", hard_fail=False)),
    dict(id="hybrid_minds_ukf__00",
         pair="SpectraSoul - Away With Me (Calibre Remix) -> EastColors - Keys",
         ya="pzFgQ7iIfXQ", yb="qeXTBEtGUtk",
         default=dict(stem="rca_2026-11-19_epgdrop_hm00_default",
                      ours="/tmp/protrans_bench/gdefa15.mp3",
                      meta="/tmp/protrans_bench/gdefa15_pzFgQ7iIfXQ_qeXTBEtGUtk_meta.json",
                      win=["n", 224, None, 8, 16], fam="nat_short", hard_fail=True),
         drop=dict(stem="rca_2026-11-19_epgdrop_hm00_drop",
                   ours="/tmp/protrans_bench/gepg27.mp3",
                   meta="/tmp/protrans_bench/gepg27_pzFgQ7iIfXQ_qeXTBEtGUtk_meta.json",
                   win=["n", 208, None, 16, 16], fam="nat_short", hard_fail=False)),
]

out = []
rules = json.load(open(paths.RULES))
assert not rules.get("EXITPOS") and not rules.get("EXITPOS_GATE") and not rules.get("EXITPOS_DROP")
for pair in PAIRS:
    src_a = os.path.join(LIB, pair["ya"] + ".m4a")
    src_b = os.path.join(LIB, pair["yb"] + ".m4a")
    for kind, j in (("default", pair["default"]), ("drop", pair["drop"])):
        y, sr = sf.read(j["ours"])
        M = json.load(open(j["meta"]))
        bar = float(M.get("bar_sec") or RP._bar_sec(M))
        tick_s = 8 * bar
        y2 = RP._tick(y, sr, tick_s)
        y2, meas, gain = RP._loudness_match(y2, sr, RP.TARGET_LUFS)
        stem = os.path.join(RP.OUT_DIR, j["stem"])
        wav = stem + ".wav"
        mp3 = stem + ".mp3"
        sf.write(wav, y2, sr)
        RP._to_mp3(wav, mp3)
        os.remove(wav)
        png = os.path.join(RP.DIAG_DIR, j["stem"] + ".png")
        png2 = stem + ".png"
        title = (f"{pair["id"]} {pair["pair"]} fam={j["fam"]} win={j["win"]} hard_fail={j["hard_fail"]}")
        cwd = os.getcwd(); sys.path.insert(0, paths.SRC2); os.chdir(paths.SRC2)
        try:
            import blend_diag
            blend_diag.figure(M, 0, png, title, pro=None, src_a=src_a, src_b=src_b, ours=j["ours"])
            if os.path.abspath(png) != os.path.abspath(png2):
                shutil.copy2(png, png2)
        finally:
            os.chdir(cwd)
        import pyloudnorm as pyln
        lufs = float(pyln.Meter(sr).integrated_loudness(np.asarray(y2, float)))
        rec = dict(id=pair["id"], pair=pair["pair"], arm=kind, win=j["win"], fam=j["fam"],
                   hard_fail=j["hard_fail"], mp3=mp3, png=png2, diag_png=png,
                   duration_s=round(len(y2)/float(sr), 3), lufs=round(lufs, 2),
                   tick_timestamp=f"{int(tick_s)//60}:{int(tick_s)%60:02d}",
                   tick_s=round(tick_s, 3), src=j["ours"], bar_sec=bar)
        print(json.dumps(rec), flush=True)
        out.append(rec)
json.dump(out, open(os.path.join(RP.OUT_DIR, "rca_2026-11-19_epgdrop_clips.json"), "w"), indent=1)
print("DONE")
