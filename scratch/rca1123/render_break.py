#!/usr/bin/env python3
"""Render the STRUCT_BREAK pick (160/32/32) for js13 under default rules.
Picker decision was made by the isolated engine (DUMP_CANDS, no pro audio).
This script only forces that already-scored window via PICKER_WIN so the live
renderer (FADE=long, BLEND_LOCK, TAIL_EXIT) can be checked. No rules.json write.
Exports a listen clip only if hard checks and drum alignment pass.
"""
import json, os, sys, subprocess
from pathlib import Path
import numpy as np, soundfile as sf, pyloudnorm as pyln

sys.path.insert(0,'/workspace/mixes/protrans')
import paths, recreate, score, cleanup

PICK='joe_syntax_hospital__13'
WIN=['n', 160, None, 32, 32]
TAG='rca23brk'
SCR='/tmp/rca1123/break_render'
DIAG_TMP=Path('/tmp/rca1123/break_diag')
DIAG_TMP.mkdir(parents=True, exist_ok=True)
STEM='rca_2026-11-23_structbreak'
TARGET=-14.0
TICK_HZ=2000.0; TICK_MS=40; TICK_DB=-9.0
# alignment pass: not a half-beat, enough drum-on-drum bars for the gate to mean something,
# median offset clearly on-beat (half beat at 174 BPM is ~172 ms).
HALFBEAT_MS=60.0/174.0/2.0*1000.0  # 172.4
OFFSET_PASS_MS=40.0  # well inside the green band; do not loosen if it fails

def tick(y,sr,t_s):
    n=int(sr*TICK_MS/1000); i0=max(0,int(round(t_s*sr))); i1=min(len(y),i0+n)
    if i1<=i0: return y
    t=np.arange(i1-i0)/sr; env=np.hanning(i1-i0)
    sig=(10**(TICK_DB/20.0))*env*np.sin(2*np.pi*TICK_HZ*t)
    y=np.array(y,dtype=np.float64,copy=True)
    if y.ndim==1: y[i0:i1]+=sig
    else: y[i0:i1]+=sig[:,None]
    return y

def match(y,sr,target=TARGET):
    meter=pyln.Meter(sr); yy=np.asarray(y,float)
    meas=meter.integrated_loudness(yy)
    if not np.isfinite(meas): return yy.astype(np.float32), meas, 0.0
    out=yy*(10**((target-meas)/20.0))
    peak=np.max(np.abs(out)) if len(out) else 0
    if peak>0.99: out*=0.99/peak
    return out.astype(np.float32), float(meas), float(target-meas)

recs={r['id']:r for r in __import__('run_admitted_tune',fromlist=['T']).load_recs()}
rec=recs[PICK]
rules=json.load(open(paths.RULES))
# default rules only
pw=Path(SCR)/'picker_win.json'
pw.parent.mkdir(parents=True, exist_ok=True)
json.dump({f"{rec['a']['yt']}|{rec['b']['yt']}": WIN}, open(pw,'w'))
os.environ['PICKER_WIN']=str(pw)
os.environ['BB_SCRATCH']=SCR
os.makedirs(SCR, exist_ok=True)

sa=os.path.join(paths.LIB, rec['a']['yt']+'.m4a')
sb=os.path.join(paths.LIB, rec['b']['yt']+'.m4a')
info=recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                       hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
                       rules=rules, tag=TAG)
print('PICK', info.get('fam'), info.get('win'), 'picker', info.get('picker'), flush=True)
print('HALFBEAT', info.get('halfbeat'), 'HARD', info.get('hard'), flush=True)
if list(info.get('win') or []) != WIN:
    print('ERROR window mismatch', info.get('win'), 'expected', WIN, flush=True)
    sys.exit(2)

sc=score.score(rec['pro_clip'], info['ours'], src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
print('SCORE', sc.get('score'), 'v2', sc.get('score_v2'), flush=True)
print('ALIGN', {k:sc.get(k) for k in ('beat_align','beat_off_ms','beat_lock','lag_ms','align') if k in sc or True}, flush=True)
# print compact score breakdown
bd=sc.get('breakdown') or sc
print('SCORE_DETAIL', json.dumps({k:bd.get(k) if isinstance(bd,dict) else None for k in
    ('beat_align','beat_off_ms','beat_lock','events_pro','events_ours','align','lag_ms','peak')}, default=str)[:2000], flush=True)

ours=info['ours']
base=os.path.splitext(ours)[0]
wav=None
for cand in (base+'_master.wav', ours.replace('.mp3','_master.wav'), base+'.wav', ours):
    if os.path.exists(cand):
        wav=cand; break
print('WAV', wav, flush=True)
y,sr=sf.read(wav)
M=json.load(open(info['meta_path']))
bar=float(M.get('bar_sec') or 240/174)
pre=8*bar
# piano lead-in: Meteorites bar 48 arrives 16 bars after cue 32
piano_s=pre+16*bar
print('BAR_SEC', bar, 'TICK', pre, 'PIANO_AT', piano_s, 'dur', len(y)/sr, flush=True)

# blend_diag first (always write tmp png)
sys.path.insert(0, paths.SRC2)
cwd=os.getcwd(); os.chdir(paths.SRC2)
try:
    import blend_diag
    png_tmp=str(DIAG_TMP/f'{STEM}.png')
    title=f"{PICK} STRUCT_BREAK pick {WIN} score {sc.get('score')}"
    summ=blend_diag.figure(M,0,png_tmp,title,pro=rec['pro_clip'],src_a=sa,src_b=sb,ours=ours)
    json.dump(summ, open(DIAG_TMP/f'{STEM}.json','w'), default=str, indent=2)
finally:
    os.chdir(cwd)

# mid-band confirmation that piano (Meteorites bar 48) is at the expected clip time
try:
    import librosa
    b_wav='/workspace/mixes/src2/st/SqzxwPEa-DI.wav'
    yb,srb=sf.read(b_wav)
    if yb.ndim>1: yb=np.mean(yb,axis=1)
    # 8 bars around Meteorites 48, band 300-2000
    b0=int((48)*bar*srb); b1=int((56)*bar*srb)
    src=yb[b0:b1]
    # clip around expected piano
    c0=int((piano_s)*sr); c1=int((piano_s+8*bar)*sr)
    clip=np.mean(y,axis=1) if y.ndim>1 else y
    dest=clip[c0:c1]
    def bp(x,s):
        if len(x)<1024: return x
        return librosa.effects.preemphasis(x)  # fallback if no sosfilt
    from scipy.signal import butter, sosfilt
    def band(x,s):
        sos=butter(4,[300,2000],btype='band',fs=s,output='sos')
        return sosfilt(sos, x.astype(float))
    # resample src to sr if needed
    if srb!=sr:
        import scipy.signal as sg
        src=sg.resample(src, int(len(src)*sr/srb))
    sa_=band(src,sr); sb_=band(dest,sr)
    n=min(len(sa_),len(sb_))
    sa_,sb_=sa_[:n]-np.mean(sa_[:n]), sb_[:n]-np.mean(sb_[:n])
    denom=np.linalg.norm(sa_)*np.linalg.norm(sb_)+1e-12
    xcorr=float(np.dot(sa_,sb_)/denom)
    print('PIANO_XCORR_AT_EXPECTED', round(xcorr,3), 'n', n, flush=True)
    # also check at blend start (should be lower if lead-in worked)
    d0=int(pre*sr); d1=int((pre+8*bar)*sr)
    dest0=clip[d0:d1]
    if srb!=sr:
        pass
    # compare same src length
    dest0=band(dest0[:n] if len(dest0)>=n else np.pad(dest0,(0,n-len(dest0))),sr)
    dest0=dest0[:n]-np.mean(dest0[:n])
    x0=float(np.dot(sa_,dest0)/(np.linalg.norm(sa_)*np.linalg.norm(dest0)+1e-12))
    print('PIANO_XCORR_AT_BLEND_START', round(x0,3), flush=True)
except Exception as ex:
    print('PIANO_XCORR_FAILED', type(ex).__name__, ex, flush=True)
    xcorr=None; x0=None

hb=summ.get('halfbeat') or {}
off=summ.get('offset_ms_median')
clash=summ.get('clash_bars')
dip=summ.get('sum_lows_dip_db')
print('DIAG', json.dumps({k:summ.get(k) for k in
    ('halfbeat','offset_ms_median','clash_bars','sum_lows_dip_db','bass_swap','pro_lock','phrase_cut')}, default=str), flush=True)

# hard / alignment decision
hb_fail=bool((hb or {}).get('fail'))
hb_note=(hb or {}).get('note') or ''
few_drums='< 4 drum-on-drum' in hb_note or 'few' in hb_note
off_abs=abs(float(off)) if off is not None else 999
near_half=abs(off_abs-HALFBEAT_MS)<40 or off_abs>80
align_ok=(not hb_fail) and (not few_drums) and (off_abs<=OFFSET_PASS_MS) and (not near_half)
# mix_simple hard
hard=info.get('hard') or {}
hard_fail=bool(hard.get('fail') or hard.get('hard') or (isinstance(hard,dict) and hard.get('flagged')))
piano_ok=(xcorr is not None and x0 is not None and xcorr>x0 and xcorr>=0.1)

checks=dict(win=WIN, score=sc.get('score'), halfbeat_fail=hb_fail, halfbeat=hb,
            few_drum_on_drum=few_drums, offset_ms_median=off, offset_pass_ms=OFFSET_PASS_MS,
            near_halfbeat=near_half, halfbeat_ms=HALFBEAT_MS, lows_dip_db=dip, clash_bars=clash,
            hard=hard, hard_fail=hard_fail, piano_xcorr_expected=xcorr, piano_xcorr_start=x0,
            piano_leadin_ok=piano_ok, align_ok=align_ok,
            pass_listen_clip=bool(align_ok and not hard_fail and piano_ok))
json.dump(checks, open(DIAG_TMP/'checks.json','w'), indent=2, default=str)
print('CHECKS', json.dumps(checks, default=str), flush=True)

# always keep tmp wav/png; ship to deliver only on pass
y2,meas,gain=match(tick(y,sr,pre),sr)
wav_tmp=str(DIAG_TMP/f'{STEM}.wav')
sf.write(wav_tmp,y2,sr)
if checks['pass_listen_clip']:
    OUT_DIR=paths.DELIVER
    DIAG_DIR=os.path.join(paths.DELIVER,'diagnostics')
    os.makedirs(DIAG_DIR, exist_ok=True)
    wav_out=os.path.join(OUT_DIR, STEM+'.wav')
    mp3_out=os.path.join(OUT_DIR, STEM+'.mp3')
    sf.write(wav_out,y2,sr)
    subprocess.run(['ffmpeg','-v','error','-y','-i',wav_out,'-codec:a','libmp3lame','-q:a','2',mp3_out],check=True)
    import shutil
    shutil.copy2(png_tmp, os.path.join(DIAG_DIR, STEM+'.png'))
    shutil.copy2(DIAG_TMP/f'{STEM}.json', os.path.join(DIAG_DIR, STEM+'.json'))
    meta=dict(id=PICK, flag='STRUCT_BREAK=1 (isolated picker; live render of that window)',
              fam=info.get('fam'), win=WIN, score=sc.get('score'), score_v2=sc.get('score_v2'),
              mp3=mp3_out, png=os.path.join(DIAG_DIR, STEM+'.png'),
              duration_s=len(y2)/sr, tick_s=pre, tick_timestamp=f"{int(pre//60)}:{int(pre%60):02d}",
              lufs=TARGET, lufs_before=meas, gain_db=gain, checks=checks)
    json.dump(meta, open(os.path.join(OUT_DIR, STEM+'.json'),'w'), indent=2, default=str)
    print('CLIP', mp3_out, 'png', os.path.join(DIAG_DIR, STEM+'.png'),
          'dur', round(len(y2)/sr,3), 'tick', f"{int(pre//60)}:{int(pre%60):02d}",
          'lufs', TARGET, 'score', sc.get('score'), flush=True)
else:
    print('NO_CLIP checks did not pass; png/wav left in', DIAG_TMP, flush=True)

# provsours (tmp always; deliver only on pass)
try:
    sys.path.insert(0,'/workspace/mixes/protrans')
    import provsours
    # best-effort
    print('PROVSOURS skip-if-api-unknown', flush=True)
except Exception as ex:
    print('PROVSOURS', ex, flush=True)
