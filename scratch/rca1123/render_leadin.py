#!/usr/bin/env python3
"""Render STRUCT_BREAK window 160/32/32 with LEADIN_LOCK=1 (isolated overlay).
Picker decision was already made without pro audio. No rules.json write.
Exports a listen clip only if hard checks and drum alignment pass.
"""
import json, os, sys, subprocess, shutil
from pathlib import Path
import numpy as np, soundfile as sf, pyloudnorm as pyln

# Scratch and flag must be set before blend_bench is imported (it reads BB_SCRATCH at import).
os.environ['LEADIN_LOCK']='1'
os.environ['BB_SCRATCH']='/tmp/rca1123/break_leadin'
Path('/tmp/rca1123/break_leadin').mkdir(parents=True, exist_ok=True)

# Isolated overlay must win for blend_bench before recreate imports it.
sys.path.insert(0, '/workspace/mixes/protrans')
sys.path.insert(0, '/workspace/mixes/src2')
sys.path.insert(0, '/tmp/rca1123/overlay_src2')
import blend_bench
assert '/tmp/rca1123/overlay_src2' in (blend_bench.__file__ or ''), blend_bench.__file__

import paths, recreate, score

PICK='joe_syntax_hospital__13'
WIN=['n', 160, None, 32, 32]
TAG='rca23brkl'
SCR='/tmp/rca1123/break_leadin'
DIAG_TMP=Path('/tmp/rca1123/break_leadin_diag')
DIAG_KEEP=Path('/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_leadin')
DIAG_TMP.mkdir(parents=True, exist_ok=True)
DIAG_KEEP.mkdir(parents=True, exist_ok=True)
STEM='rca_2026-11-23_structbreak'
TARGET=-14.0
TICK_HZ=2000.0; TICK_MS=40; TICK_DB=-9.0
HALFBEAT_MS=60.0/174.0/2.0*1000.0
OFFSET_PASS_MS=40.0

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

os.environ['LEADIN_LOCK']='1'
recs={r['id']:r for r in __import__('run_admitted_tune',fromlist=['T']).load_recs()}
rec=recs[PICK]
rules=json.load(open(paths.RULES))
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
M=json.load(open(info['meta_path']))
print('BLEND_LOCK', (M['trans'][0].get('blend_lock')), flush=True)
print('HALFBEAT', M['trans'][0].get('halfbeat'), 'HARD', info.get('hard'), flush=True)
if list(info.get('win') or []) != WIN:
    print('ERROR window mismatch', info.get('win'), 'expected', WIN, flush=True)
    sys.exit(2)

sc=score.score(rec['pro_clip'], info['ours'], src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)
print('SCORE', sc.get('score'), 'v2', sc.get('score_v2'), flush=True)
bd=sc.get('breakdown') or sc
print('SCORE_DETAIL', json.dumps({k:bd.get(k) if isinstance(bd,dict) else None for k in
    ('beat_align','beat_off_ms','beat_lock','events_pro','events_ours','align')}, default=str)[:2000], flush=True)

ours=info['ours']
base=os.path.splitext(ours)[0]
wav=None
for cand in (base+'_master.wav', ours.replace('.mp3','_master.wav'), base+'.wav', ours):
    if os.path.exists(cand):
        wav=cand; break
y,sr=sf.read(wav)
bar=float(M.get('bar_sec') or 240/174)
pre=8*bar
piano_s=pre+16*bar
print('BAR_SEC', bar, 'TICK', pre, 'PIANO_AT', piano_s, 'dur', len(y)/sr, flush=True)

sys.path.insert(0, paths.SRC2)
cwd=os.getcwd(); os.chdir(paths.SRC2)
try:
    import blend_diag, engine as E
    png_tmp=str(DIAG_TMP/f'{STEM}.png')
    title=f"{PICK} STRUCT_BREAK+LEADIN_LOCK {WIN} score {sc.get('score')}"
    summ=blend_diag.figure(M,0,png_tmp,title,pro=rec['pro_clip'],src_a=sa,src_b=sb,ours=ours)
    json.dump(summ, open(DIAG_TMP/f'{STEM}.json','w'), default=str, indent=2)
    s0,yA,yB=blend_diag.crop_decks(M,0)
finally:
    os.chdir(cwd)

# Piano / event check on the INCOMING deck only (mix xcorr was polluted by the outgoing)
def rms_db(sig, i0, i1):
    seg=np.asarray(sig[i0:i1], float)
    if seg.ndim>1: seg=np.mean(seg,axis=1)
    return float(20*np.log10(np.sqrt(np.mean(seg**2)+1e-18)))

# mix bar 144 = Meteorites 48, crop starts at s0
ev_mix=144.0
i_ev=int((ev_mix-s0)*E.BS)
i_pre=int((ev_mix-4-s0)*E.BS)
i_lead=int((128-s0)*E.BS)
lowsB=[]
# per-bar lows of B around the event
from scipy.signal import butter, sosfilt
def band(y, lo, hi):
    y=np.mean(y,axis=1) if np.asarray(y).ndim>1 else np.asarray(y,float)
    return sosfilt(butter(2,[lo,hi],btype='band',fs=E.SR,output='sos'), y)
lowB=band(yB,40,150); midB=band(yB,300,2000)
print('B-deck bars (mix)  low_db  mid_db')
b_lows={}
for mb in range(128,161):
    a=int((mb-s0)*E.BS); b=int((mb+1-s0)*E.BS)
    ld,md=rms_db(lowB,a,b), rms_db(midB,a,b)
    b_lows[mb]=(ld,md)
    mark='EVENT' if mb==144 else ''
    print(f'  {mb}  {ld:6.1f}  {md:6.1f}  {mark}')
# lead-in ok if B is present before 144 and lows jump at/near 144
lead_mid=np.median([b_lows[m][1] for m in range(128,144)])
pre_low=np.median([b_lows[m][0] for m in range(140,144)])
ev_low=np.median([b_lows[m][0] for m in range(144,148)])
piano_ok=bool(lead_mid > -50 and (ev_low - pre_low) >= 3.0)
print('PIANO lead_mid', round(lead_mid,1), 'pre_low', round(pre_low,1), 'ev_low', round(ev_low,1), 'ok', piano_ok, flush=True)

hb=summ.get('halfbeat') or {}
off=summ.get('offset_ms_median')
clash=summ.get('clash_bars')
dip=summ.get('sum_lows_dip_db')
print('DIAG', json.dumps({k:summ.get(k) for k in
    ('halfbeat','offset_ms_median','clash_bars','sum_lows_dip_db','bass_swap','pro_lock','phrase_cut')}, default=str), flush=True)

hb_fail=bool((hb or {}).get('fail'))
off_abs=abs(float(off)) if off is not None else 999
near_half=abs(off_abs-HALFBEAT_MS)<40 or off_abs>80
align_ok=(not hb_fail) and (off_abs<=OFFSET_PASS_MS) and (not near_half)
hard=info.get('hard') or {}
hard_fail=bool(hard.get('fail') or hard.get('flagged'))
checks=dict(win=WIN, score=sc.get('score'), flag='LEADIN_LOCK=1',
            blend_lock=M['trans'][0].get('blend_lock'),
            halfbeat_fail=hb_fail, halfbeat=hb,
            offset_ms_median=off, offset_pass_ms=OFFSET_PASS_MS,
            near_halfbeat=near_half, halfbeat_ms=HALFBEAT_MS, lows_dip_db=dip, clash_bars=clash,
            hard=hard, hard_fail=hard_fail, piano_leadin_ok=piano_ok,
            piano_lead_mid_db=lead_mid, piano_pre_low_db=pre_low, piano_ev_low_db=ev_low,
            align_ok=align_ok,
            pass_listen_clip=bool(align_ok and not hard_fail and piano_ok))
json.dump(checks, open(DIAG_TMP/'checks.json','w'), indent=2, default=str)
print('CHECKS', json.dumps(checks, default=str), flush=True)

y2,meas,gain=match(tick(y,sr,pre),sr)
sf.write(str(DIAG_TMP/f'{STEM}.wav'), y2, sr)
# always copy diagnostics out of /tmp
for fn in DIAG_TMP.iterdir():
    shutil.copy2(fn, DIAG_KEEP/fn.name)
shutil.copy2(png_tmp, '/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_leadin.png')
shutil.copy2(DIAG_TMP/f'{STEM}.json', '/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_leadin.json')
shutil.copy2(DIAG_TMP/'checks.json', '/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-23_structbreak_leadin_checks.json')

if checks['pass_listen_clip']:
    OUT_DIR=paths.DELIVER
    DIAG_DIR=os.path.join(paths.DELIVER,'diagnostics')
    os.makedirs(DIAG_DIR, exist_ok=True)
    wav_out=os.path.join(OUT_DIR, STEM+'.wav')
    mp3_out=os.path.join(OUT_DIR, STEM+'.mp3')
    sf.write(wav_out,y2,sr)
    subprocess.run(['ffmpeg','-v','error','-y','-i',wav_out,'-codec:a','libmp3lame','-q:a','2',mp3_out],check=True)
    shutil.copy2(png_tmp, os.path.join(DIAG_DIR, STEM+'.png'))
    shutil.copy2(DIAG_TMP/f'{STEM}.json', os.path.join(DIAG_DIR, STEM+'.json'))
    meta=dict(id=PICK, flag='STRUCT_BREAK=1 + LEADIN_LOCK=1 (isolated)',
              fam=info.get('fam'), win=WIN, score=sc.get('score'), score_v2=sc.get('score_v2'),
              mp3=mp3_out, png=os.path.join(DIAG_DIR, STEM+'.png'),
              duration_s=len(y2)/sr, tick_s=pre, tick_timestamp=f"{int(pre//60)}:{int(pre%60):02d}",
              lufs=TARGET, lufs_before=meas, gain_db=gain, checks=checks)
    json.dump(meta, open(os.path.join(OUT_DIR, STEM+'.json'),'w'), indent=2, default=str)
    print('CLIP', mp3_out, 'png', os.path.join(DIAG_DIR, STEM+'.png'),
          'dur', round(len(y2)/sr,3), 'tick', f"{int(pre//60)}:{int(pre%60):02d}",
          'lufs', TARGET, 'score', sc.get('score'), flush=True)
else:
    print('NO_CLIP checks did not pass; diags in', DIAG_KEEP, flush=True)
