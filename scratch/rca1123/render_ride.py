#!/usr/bin/env python3
"""Render STRUCT_BREAK window 160/32/32 with LEADIN_LOCK + ONBEAT_RIDE + BASS_FILL_GAPS.

Isolated overlay; picker window already chosen from structure (no pro audio at pick).
Persistent scratch under /workspace/mixes/scratch (not /tmp, not dist/build/out/.cache).
Exports a listen clip only if hard checks, on-beat alignment, piano lead-in, and bass hole pass.
Does not write rules.json or change defaults.
"""
import json, os, sys, subprocess, shutil
from pathlib import Path
import numpy as np, soundfile as sf, pyloudnorm as pyln

ROOT = Path('/workspace/mixes/scratch/rca1123')
OVERLAY = ROOT / 'overlay_src2'
SCR = str(ROOT / 'ride')
DIAG_TMP = ROOT / 'ride_diag'
DIAG_KEEP = Path('/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_ride')
STEM = 'rca_2026-11-23_structbreak'
PICK = 'joe_syntax_hospital__13'
WIN = ['n', 160, None, 32, 32]
TAG = 'rca23ride'
TARGET = -14.0
TICK_HZ = 2000.0
TICK_MS = 40
TICK_DB = -9.0
HALFBEAT_MS = 60.0 / 174.0 / 2.0 * 1000.0
OFFSET_PASS_MS = 40.0
HOLE_PASS_DB = 6.0  # existing thin / body-6 line, not loosened

os.environ['LEADIN_LOCK'] = '1'
os.environ['ONBEAT_RIDE'] = '1'
os.environ['BASS_FILL_GAPS'] = '1'
os.environ['BB_SCRATCH'] = SCR
Path(SCR).mkdir(parents=True, exist_ok=True)
DIAG_TMP.mkdir(parents=True, exist_ok=True)
DIAG_KEEP.mkdir(parents=True, exist_ok=True)

# Overlay blend_bench and isolated recreate must win before live modules.
sys.path.insert(0, '/workspace/mixes/protrans')
sys.path.insert(0, '/workspace/mixes/src2')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(OVERLAY))

import blend_bench
assert 'scratch/rca1123/overlay_src2' in (blend_bench.__file__ or ''), blend_bench.__file__
import recreate
assert 'scratch/rca1123/recreate.py' in (recreate.__file__ or ''), recreate.__file__
import paths, score
import onbeat_ride

def tick(y, sr, t_s):
    n = int(sr * TICK_MS / 1000)
    i0 = max(0, int(round(t_s * sr)))
    i1 = min(len(y), i0 + n)
    if i1 <= i0:
        return y
    t = np.arange(i1 - i0) / sr
    env = np.hanning(i1 - i0)
    sig = (10 ** (TICK_DB / 20.0)) * env * np.sin(2 * np.pi * TICK_HZ * t)
    y = np.array(y, dtype=np.float64, copy=True)
    if y.ndim == 1:
        y[i0:i1] += sig
    else:
        y[i0:i1] += sig[:, None]
    return y

def match(y, sr, target=TARGET):
    meter = pyln.Meter(sr)
    yy = np.asarray(y, float)
    meas = meter.integrated_loudness(yy)
    if not np.isfinite(meas):
        return yy.astype(np.float32), meas, 0.0
    out = yy * (10 ** ((target - meas) / 20.0))
    peak = np.max(np.abs(out)) if len(out) else 0
    if peak > 0.99:
        out *= 0.99 / peak
    return out.astype(np.float32), float(meas), float(target - meas)

def rms_db(sig, i0, i1):
    seg = np.asarray(sig[i0:i1], float)
    if seg.ndim > 1:
        seg = np.mean(seg, axis=1)
    return float(20 * np.log10(np.sqrt(np.mean(seg ** 2) + 1e-18)))

recs = {r['id']: r for r in __import__('run_admitted_tune', fromlist=['T']).load_recs()}
rec = recs[PICK]
rules = json.load(open(paths.RULES))
pw = Path(SCR) / 'picker_win.json'
json.dump({f"{rec['a']['yt']}|{rec['b']['yt']}": WIN}, open(pw, 'w'))
os.environ['PICKER_WIN'] = str(pw)
os.environ['BB_SCRATCH'] = SCR
os.makedirs(SCR, exist_ok=True)

sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                         hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
                         rules=rules, tag=TAG)
print('PICK', info.get('fam'), info.get('win'), 'picker', info.get('picker'), flush=True)
print('BB_SCRATCH', os.environ.get('BB_SCRATCH'), 'meta', info.get('meta_path'), flush=True)
M = json.load(open(info['meta_path']))
print('BLEND_LOCK', (M['trans'][0].get('blend_lock')), flush=True)
print('ONBEAT_RIDE', json.dumps({k: (M['trans'][0].get('onbeat_ride') or {}).get(k)
                                 for k in ('applied', 'why', 'n_conf', 'median_abs', 'after')}, default=str), flush=True)
print('BASS_FILL', M['trans'][0].get('bass_fill') or M['trans'][0].get('bass_fill_gaps'), flush=True)
print('HALFBEAT', M['trans'][0].get('halfbeat'), 'HARD', info.get('hard'), flush=True)
if list(info.get('win') or []) != WIN:
    print('ERROR window mismatch', info.get('win'), 'expected', WIN, flush=True)
    sys.exit(2)

sc = score.score(rec['pro_clip'], info['ours'], src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
print('SCORE', sc.get('score'), 'v2', sc.get('score_v2'), flush=True)
bd = sc.get('breakdown') or sc
print('SCORE_DETAIL', json.dumps({k: bd.get(k) if isinstance(bd, dict) else None for k in
    ('beat_align', 'beat_off_ms', 'beat_lock', 'events_pro', 'events_ours', 'align')}, default=str)[:2000], flush=True)

ours = info['ours']
base = os.path.splitext(ours)[0]
wav = None
for cand in (base + '_master.wav', ours.replace('.mp3', '_master.wav'), base + '.wav', ours):
    if os.path.exists(cand):
        wav = cand
        break
y, sr = sf.read(wav)
bar = float(M.get('bar_sec') or 240 / 174)
pre = 8 * bar
piano_s = pre + 16 * bar
print('BAR_SEC', bar, 'TICK', pre, 'PIANO_AT', piano_s, 'dur', len(y) / sr, 'wav', wav, flush=True)

sys.path.insert(0, paths.SRC2)
onbeat_ride.install_engine_hook()
cwd = os.getcwd()
os.chdir(paths.SRC2)
try:
    import blend_diag, engine as E
    png_tmp = str(DIAG_TMP / f'{STEM}.png')
    title = f"{PICK} STRUCT_BREAK+LEADIN_LOCK+ONBEAT_RIDE+BASS_FILL_GAPS {WIN} score {sc.get('score')}"
    summ = blend_diag.figure(M, 0, png_tmp, title, pro=rec['pro_clip'], src_a=sa, src_b=sb, ours=ours)
    json.dump(summ, open(DIAG_TMP / f'{STEM}.json', 'w'), default=str, indent=2)
    s0, yA, yB = blend_diag.crop_decks(M, 0)
    t0 = M['trans'][0]
    s, e = t0['start_bar'], t0['end_bar']
    # trustworthy 1-bar xcorr (interior peak when the official hop is at the edge)
    beat = E.BAR
    nb = yA.shape[0] // E.BS
    bars = list(range(int(s - s0), int(e - s0)))
    offs_off = blend_diag.bar_offsets(yA, yB, bars, E.BS, beat, win_bars=1, prefer_interior=False)
    offs_int = blend_diag.bar_offsets(yA, yB, bars, E.BS, beat, win_bars=1, prefer_interior=True)
    recs_ob = onbeat_ride.measure(yA, yB, s0, s, e, E.BS, E.SR)
finally:
    os.chdir(cwd)

from scipy.signal import butter, sosfilt

def band(y, lo, hi):
    y = np.mean(y, axis=1) if np.asarray(y).ndim > 1 else np.asarray(y, float)
    return sosfilt(butter(2, [lo, hi], btype='band', fs=E.SR, output='sos'), y)

# Piano / event check on the incoming deck only
lowB = band(yB, 40, 150)
midB = band(yB, 300, 2000)
print('B-deck bars (mix)  low_db  mid_db')
b_lows = {}
for mb in range(128, 161):
    a = int((mb - s0) * E.BS)
    b = int((mb + 1 - s0) * E.BS)
    ld, md = rms_db(lowB, a, b), rms_db(midB, a, b)
    b_lows[mb] = (ld, md)
    mark = 'EVENT' if mb == 144 else ''
    print(f'  {mb}  {ld:6.1f}  {md:6.1f}  {mark}')
lead_mid = np.median([b_lows[m][1] for m in range(128, 144)])
pre_low = np.median([b_lows[m][0] for m in range(140, 144)])
ev_low = np.median([b_lows[m][0] for m in range(144, 148)])
piano_ok = bool(lead_mid > -50 and (ev_low - pre_low) >= 3.0)
print('PIANO lead_mid', round(lead_mid, 1), 'pre_low', round(pre_low, 1), 'ev_low', round(ev_low, 1), 'ok', piano_ok, flush=True)

# Summed lows dip + post-swap hole (the actual bass gap after A is swapped/tailed out)
lowA = band(yA, 30, 150)
def bar_low(sig, mb):
    a = int((mb - s0) * E.BS)
    b = int((mb + 1 - s0) * E.BS)
    return rms_db(sig, a, b)
sumlo = {mb: 20 * np.log10(np.sqrt(10 ** (bar_low(lowA, mb) / 10) + 10 ** (bar_low(lowB, mb) / 10) + 1e-18))
         for mb in range(int(s0), int(t0['end_bar']) + 1)}
pre_vals = [sumlo[mb] for mb in range(int(s) - 2, int(s)) if mb in sumlo]
blend_vals = [sumlo[mb] for mb in range(int(s), int(e)) if mb in sumlo]
official_dip = (max(pre_vals) - min(blend_vals)) if pre_vals and blend_vals else None
swap1 = float((t0.get('bass_swap') or [s, s])[1])
exit_bar = float((t0.get('tail_exit') or {}).get('exit_bar') or (swap1 + 6))
pre_swap = [sumlo[mb] for mb in range(int(s), int(np.ceil(swap1))) if mb in sumlo]
post_swap = [sumlo[mb] for mb in range(int(np.ceil(swap1)), int(e)) if mb in sumlo]
hole_db = None if not pre_swap or not post_swap else float(np.median(pre_swap) - min(post_swap))
min_post = None if not post_swap else float(min(post_swap))
min_post_bar = None if not post_swap else int(np.ceil(swap1)) + int(np.argmin(post_swap))
print('LOWS official_dip', None if official_dip is None else round(official_dip, 1),
      'hole_db', None if hole_db is None else round(hole_db, 1),
      'min_post', None if min_post is None else round(min_post, 1),
      'at', min_post_bar, 'swap1', swap1, 'exit', exit_bar, flush=True)

conf = [r for r in recs_ob if r.get('conf')]
ob_res = [r['residual_ms'] for r in conf]
ob_med = None if not ob_res else float(np.median(ob_res))
ob_max = None if not ob_res else float(np.max(np.abs(ob_res)))
ob_std = None if not ob_res else float(np.std(ob_res))
print('ONBEAT conf', len(conf), 'median', ob_med, 'max_abs', ob_max, 'std', ob_std, 'rows', conf, flush=True)

def nanmed(a):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return None if len(a) == 0 else float(np.median(a))

off = summ.get('offset_ms_median')
off_1bar = nanmed(offs_off)
off_interior = nanmed(offs_int)
print('OFFSET official', off, '1bar', None if off_1bar is None else round(off_1bar, 1),
      'interior', None if off_interior is None else round(off_interior, 1), flush=True)

hb = summ.get('halfbeat') or {}
clash = summ.get('clash_bars')
dip = summ.get('sum_lows_dip_db')
print('DIAG', json.dumps({k: summ.get(k) for k in
    ('halfbeat', 'offset_ms_median', 'clash_bars', 'sum_lows_dip_db', 'bass_swap', 'pro_lock', 'phrase_cut')}, default=str), flush=True)

hb_fail = bool((hb or {}).get('fail'))
# Alignment gate: trustworthy estimators at the existing 40 ms line.
# Official 1-bar xcorr is reported but is known to hop on half-time breakdowns;
# it is not loosened, and a hop is not treated as a pass by itself.
ob_ok = bool(ob_res) and abs(ob_med) <= OFFSET_PASS_MS and ob_max <= OFFSET_PASS_MS
interior_ok = off_interior is not None and abs(off_interior) <= OFFSET_PASS_MS
align_ok = (not hb_fail) and ob_ok and interior_ok
bass_ok = hole_db is not None and hole_db <= HOLE_PASS_DB
hard = info.get('hard') or {}
hard_fail = bool(hard.get('fail') or hard.get('flagged'))
checks = dict(
    win=WIN, score=sc.get('score'), score_v2=sc.get('score_v2'),
    flags='LEADIN_LOCK=1 ONBEAT_RIDE=1 BASS_FILL_GAPS=1',
    scratch=SCR, meta=info.get('meta_path'),
    blend_lock=M['trans'][0].get('blend_lock'),
    onbeat_ride={k: (M['trans'][0].get('onbeat_ride') or {}).get(k)
                 for k in ('applied', 'why', 'n_conf', 'median_abs', 'max_abs', 'after')},
    bass_fill=M['trans'][0].get('bass_fill') or M['trans'][0].get('bass_fill_gaps'),
    halfbeat_fail=hb_fail, halfbeat=hb,
    offset_ms_median=off, offset_1bar_ms=None if off_1bar is None else round(off_1bar, 1),
    offset_interior_ms=None if off_interior is None else round(off_interior, 1),
    offset_pass_ms=OFFSET_PASS_MS,
    onbeat_n=len(conf), onbeat_median_ms=None if ob_med is None else round(ob_med, 1),
    onbeat_max_abs_ms=None if ob_max is None else round(ob_max, 1),
    onbeat_std_ms=None if ob_std is None else round(ob_std, 1),
    onbeat_rows=conf,
    halfbeat_ms=HALFBEAT_MS,
    lows_dip_db=dip, lows_dip_recomputed=None if official_dip is None else round(official_dip, 1),
    hole_db=None if hole_db is None else round(hole_db, 1),
    hole_pass_db=HOLE_PASS_DB, min_post_low_db=None if min_post is None else round(min_post, 1),
    min_post_bar=min_post_bar, clash_bars=clash,
    hard=hard, hard_fail=hard_fail,
    piano_leadin_ok=piano_ok,
    piano_lead_mid_db=lead_mid, piano_pre_low_db=pre_low, piano_ev_low_db=ev_low,
    onbeat_ok=ob_ok, interior_ok=interior_ok, bass_ok=bass_ok, align_ok=align_ok,
    pass_listen_clip=bool(align_ok and bass_ok and not hard_fail and piano_ok),
)
json.dump(checks, open(DIAG_TMP / 'checks.json', 'w'), indent=2, default=str)
print('CHECKS', json.dumps(checks, default=str), flush=True)

y2, meas, gain = match(tick(y, sr, pre), sr)
sf.write(str(DIAG_TMP / f'{STEM}.wav'), y2, sr)
for fn in DIAG_TMP.iterdir():
    shutil.copy2(fn, DIAG_KEEP / fn.name)
shutil.copy2(png_tmp, '/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_ride.png')
shutil.copy2(DIAG_TMP / f'{STEM}.json', '/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_ride.json')
shutil.copy2(DIAG_TMP / 'checks.json', '/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_ride_checks.json')

if checks['pass_listen_clip']:
    OUT_DIR = paths.DELIVER
    DIAG_DIR = os.path.join(paths.DELIVER, 'diagnostics')
    os.makedirs(DIAG_DIR, exist_ok=True)
    wav_out = os.path.join(OUT_DIR, STEM + '.wav')
    mp3_out = os.path.join(OUT_DIR, STEM + '.mp3')
    sf.write(wav_out, y2, sr)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', wav_out, '-codec:a', 'libmp3lame', '-q:a', '2', mp3_out], check=True)
    shutil.copy2(png_tmp, os.path.join(DIAG_DIR, STEM + '.png'))
    shutil.copy2(DIAG_TMP / f'{STEM}.json', os.path.join(DIAG_DIR, STEM + '.json'))
    meta = dict(id=PICK, flag='STRUCT_BREAK=1 + LEADIN_LOCK=1 + ONBEAT_RIDE=1 + BASS_FILL_GAPS=1 (isolated)',
                fam=info.get('fam'), win=WIN, score=sc.get('score'), score_v2=sc.get('score_v2'),
                mp3=mp3_out, png=os.path.join(DIAG_DIR, STEM + '.png'),
                duration_s=len(y2) / sr, tick_s=pre, tick_timestamp=f"{int(pre // 60)}:{int(pre % 60):02d}",
                lufs=TARGET, lufs_before=meas, gain_db=gain, checks=checks)
    json.dump(meta, open(os.path.join(OUT_DIR, STEM + '.json'), 'w'), indent=2, default=str)
    print('CLIP', mp3_out, 'png', os.path.join(DIAG_DIR, STEM + '.png'),
          'dur', round(len(y2) / sr, 3), 'tick', f"{int(pre // 60)}:{int(pre % 60):02d}",
          'lufs', TARGET, 'score', sc.get('score'), flush=True)
else:
    print('NO_CLIP checks did not pass; diags in', DIAG_KEEP, flush=True)
    sys.exit(0)  # job succeeded as a check run; no clip is not a crash
