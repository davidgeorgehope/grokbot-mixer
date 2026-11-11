"""BASSGAP check (the listener 2026-11-02 19:33 ET): in every blend overlap, low-end (<150 Hz) energy per bar of the mixdown must not fall
>GAP_DB below its neighbours (median of the bars within +-4 outside the dip) for more than 1 bar, unless both source tracks
themselves dip there (a deliberate breakdown in the source)."""
import numpy as np,soundfile as sf
from scipy.signal import butter,sosfilt
GAP_DB=9.84  # pro p95 of 33 admitted blends, 2026-11-10 (was 8.0; src/calib/guard_vs_pro_results.json p95=9.839). the listener heard the flagged Mix 08 r11c blends and said they were fine. See docs/PRO_CALIBRATION_2026-11-10.md.
def bar_db(x,sr,bs,b0,b1,ofs=0):
  sos=butter(4,150,'low',fs=sr,output='sos');out=[]
  for b in range(b0,b1):
    i=int(round(ofs+b*bs));seg=x[max(0,i):i+int(bs)]
    if len(seg)<bs*0.5:out.append(np.nan);continue
    z=sosfilt(sos,seg.mean(1) if seg.ndim>1 else seg);out.append(10*np.log10(np.mean(z**2)+1e-12))
  return np.array(out)
def gaps(db,b0):
  """runs (start_bar,len,depth) where a bar sits >GAP_DB under the median of its +-4 neighbours"""
  low=[];n=len(db)
  for k in range(n):
    nb=[db[j] for j in range(max(0,k-4),min(n,k+5)) if abs(j-k)>=1]
    low.append(np.isfinite(db[k]) and db[k]<np.nanmedian(nb)-GAP_DB)
  out=[];k=0
  while k<n:
    if low[k]:
      j=k
      while j<n and low[j]:j+=1
      out.append((b0+k,j-k));k=j
    else:k+=1
  return out
def src_dip(d,mb,L):
  """deliberate source breakdown: the deck's own track (full mix, pre-fader) dips >=GAP_DB/2 at the same source bars"""
  import engine as E
  k=int(mb-d['start_bar']);fm=d['full_map']
  if not 0<=k<len(fm):return True  # deck not playing there -> not its gap
  tr=E.track(d['id']);x=tr['st']['mix'];sr=E.SR;bs=E.BAR*sr;sb=[fm[j][0] for j in range(max(0,k-4),min(len(fm),k+L+4))]
  db=np.array([bar_db(x,sr,bs,b,b+1,ofs=tr['d0']*sr)[0] for b in sb]);i=k-max(0,k-4);ref=np.nanmedian(np.r_[db[:i],db[i+L:]])
  return bool(np.nanmin(db[i:i+L])<ref-GAP_DB/2)
def check(M,wav,src_db=src_dip):
  """returns list of failing gaps (trans index, mix bar, bars). src_db(deck,mixbar)->source low dB, for the breakdown exemption"""
  x,sr=sf.read(wav,dtype='float32',always_2d=True);bs=M['bar_sec']*sr;bad=[]
  for i,t in enumerate(M['trans']):
    b0,b1=int(t['start_bar'])-4,int(t['end_bar'])+4;db=bar_db(x,sr,bs,b0,b1)
    for s,L in gaps(db,b0):
      if L<=1 or s+L<=t['start_bar'] or s>=t['end_bar']:continue
      if src_db and all(src_db(M['decks'][j],s,L) for j in (i,i+1)):continue
      bad.append((i,s,L))
  return bad
