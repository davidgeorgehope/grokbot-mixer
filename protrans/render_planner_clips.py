#!/usr/bin/env python3
"""44 s, -14 LUFS clips + diagnostic figures for the 11-14 and 11-15 pairs
under the window planner. Same snippet convention as the daily clips
(8 bars of pre-roll, 16-bar blend, 8 bars after; short tick at the blend).

Writes deliver/protrans/planner_2026-11-15_<id>.mp3/.png/.json
"""
from __future__ import annotations
import json, os, sys, copy, math
import numpy as np
import soundfile as sf
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths, recreate, cleanup
import run_admitted_tune as T

PICKS = ('hybrid_minds_ukf__19', 'hybrid_minds_ukf__25')
OUT_DIR = os.path.join(paths.DELIVER)  # deliver/protrans
DIAG_DIR = os.path.join(paths.DELIVER, 'diagnostics')
TARGET_LUFS = -14.0
TICK_HZ = 1000.0
TICK_MS = 40
TICK_DB = -9.0  # short, obvious, not a blast


def _bar_sec(M):
    return float(M.get('bar_sec') or 240 / 174)


def _tick(y, sr, t_s, db=TICK_DB, ms=TICK_MS, hz=TICK_HZ):
    n = int(sr * ms / 1000)
    i0 = max(0, int(round(t_s * sr)))
    i1 = min(len(y), i0 + n)
    if i1 <= i0:
        return y
    t = np.arange(i1 - i0) / sr
    env = np.hanning(i1 - i0)
    sig = (10 ** (db / 20.0)) * env * np.sin(2 * np.pi * hz * t)
    y = np.array(y, dtype=np.float64, copy=True)
    if y.ndim == 1:
        y[i0:i1] += sig
    else:
        y[i0:i1, :] += sig[:, None]
    return y


def _loudness_match(y, sr, target=TARGET_LUFS):
    import pyloudnorm as pyln
    meter = pyln.Meter(sr)
    yy = np.asarray(y, float)
    if yy.ndim == 1:
        meas = meter.integrated_loudness(yy)
    else:
        meas = meter.integrated_loudness(yy)
    if not np.isfinite(meas):
        return y, meas, 0.0
    gain = target - meas
    out = yy * (10 ** (gain / 20.0))
    peak = np.max(np.abs(out)) if len(out) else 0
    if peak > 0.99:
        out *= 0.99 / peak
        meas2 = meter.integrated_loudness(out)
        gain = meas2 - meas if np.isfinite(meas2) else gain
    return out.astype(np.float32), float(meas), float(gain)


def _to_mp3(wav, mp3):
    import subprocess
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav, '-codec:a', 'libmp3lame', '-q:a', '2', mp3], check=True)


def render_one(rec, rules, tag, stem_name=None):
    sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
    sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
    info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                             hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
                             rules=rules, tag=tag)
    M = json.load(open(info['meta_path']))
    # engine snippet (PRE=8, blend, POST=8) lives next to the mp3 as a wav or we load the mp3
    ours = info['ours']
    base = os.path.splitext(ours)[0]
    wav = None
    for cand in (base + '_master.wav', base + '.wav', ours):
        if os.path.exists(cand):
            wav = cand
            break
    y, sr = sf.read(wav)
    t = M['trans'][0]
    bar = _bar_sec(M)
    # snippet starts PRE=8 bars before the blend; designed blend start is 8*bar
    # (blend_bench.PRE). A snap-in rise may start later than start_bar.
    pre = 8 * bar
    tick_s = pre
    # If SNAP_IN delayed the incoming, still tick at the blend window start so
    # the marker matches the daily / rca-fix convention (8-bar pre-roll).
    y2 = _tick(y, sr, tick_s)
    y2, meas, gain = _loudness_match(y2, sr, TARGET_LUFS)
    dur = len(y2) / float(sr)
    stem = os.path.join(OUT_DIR, stem_name or f"planner_2026-11-15_{rec['id']}")
    wav_out = stem + '.wav'
    mp3_out = stem + '.mp3'
    sf.write(wav_out, y2, sr)
    _to_mp3(wav_out, mp3_out)
    # diagnostic figure
    os.makedirs(DIAG_DIR, exist_ok=True)
    png_name = os.path.basename(stem) + ".png"
    png = os.path.join(DIAG_DIR, png_name)
    # also a copy next to the mp3, as the brief asked for planner_2026-11-15_*.png
    png2 = stem + '.png'
    sys.path.insert(0, paths.SRC2)
    cwd = os.getcwd(); os.chdir(paths.SRC2)
    try:
        import blend_diag
        title = (f"{rec['id']} {rec['pair']} fam={info['fam']} win={info['win']} "
                 f"planner={((info.get('planner') or {}).get('type'))}")
        summ = blend_diag.figure(M, 0, png, title, pro=rec['pro_clip'], src_a=sa, src_b=sb, ours=ours)
        import shutil
        shutil.copy2(png, png2)
    finally:
        os.chdir(cwd)
    meta = dict(
        id=rec['id'], pair=rec['pair'], fam=info['fam'], win=info['win'], env=info.get('env'),
        planner=info.get('planner'),
        src=ours, mp3=mp3_out, png=png2, diag_png=png,
        duration_s=round(dur, 3), lufs=round(TARGET_LUFS + 0, 2),
        measured_lufs_before=round(meas, 2) if meas is not None else None,
        gain_db_applied=round(gain, 2),
        tick_s=round(tick_s, 3),
        tick_timestamp=f"{int(tick_s)//60}:{int(tick_s)%60:02d}" if tick_s >= 0 else '0:00',
        designed_blend_start_s=round(pre, 3),
        start_bar=t.get('start_bar'), end_bar=t.get('end_bar'),
        bass_swap=t.get('bass_swap'), snap_in=t.get('snap_in'),
        bar_sec=bar,
    )
    # true loudness after write
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        meta['lufs'] = round(float(meter.integrated_loudness(np.asarray(y2, float))), 2)
        meta['true_peak'] = round(float(20 * np.log10(np.max(np.abs(y2)) + 1e-12)), 2)
    except Exception:
        pass
    json.dump(meta, open(stem + '.json', 'w'), indent=2, default=str)
    json.dump(summ, open(os.path.splitext(png)[0] + ".json", "w"), indent=1, default=str)
    cleanup.drop_our_src2(info.get('created') or [])
    return meta


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--ukf25-v2', action='store_true',
                    help='render only the 11-15 pair to planner_2026-11-15_ukf25_v2.mp3')
    args = ap.parse_args()
    recs = {r['id']: r for r in T.load_recs()}
    rules = json.load(open(paths.RULES))
    trial = copy.deepcopy(rules)
    trial['window_planner'] = 1
    os.makedirs(OUT_DIR, exist_ok=True)
    out = []
    if args.ukf25_v2:
        meta = render_one(recs['hybrid_minds_ukf__25'], trial, 'wpclip_ukf25v2',
                          stem_name='planner_2026-11-15_ukf25_v2')
        out.append(meta)
        print('CLIP', json.dumps({k: meta[k] for k in ('id', 'fam', 'win', 'mp3', 'png', 'duration_s', 'lufs', 'tick_timestamp', 'planner') if k in meta}, default=str), flush=True)
        json.dump(out, open(os.path.join(OUT_DIR, 'planner_2026-11-15_ukf25_v2_clip.json'), 'w'), indent=2, default=str)
        return
    for i, pid in enumerate(PICKS):
        meta = render_one(recs[pid], trial, f'wpclip{i}')
        out.append(meta)
        print('CLIP', json.dumps({k: meta[k] for k in ('id', 'fam', 'win', 'mp3', 'png', 'duration_s', 'lufs', 'tick_timestamp', 'planner') if k in meta}, default=str), flush=True)
    json.dump(out, open(os.path.join(OUT_DIR, 'planner_2026-11-15_clips.json'), 'w'), indent=2, default=str)


if __name__ == '__main__':
    main()
