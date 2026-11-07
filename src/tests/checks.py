"""Mix QA checks. Config via env: MIX_SRC (render dir), MIX_NAME (meta prefix), MIX_WAV (mastered wav), MIX_MP3."""
import os,json,subprocess,re,functools,numpy as np,soundfile as sf,librosa,glob
from scipy.signal import butter,sosfiltfilt
SRC=os.environ.get('MIX_SRC','/workspace/mixes/src2');NAME=os.environ.get('MIX_NAME','mixS')
WAV=os.environ.get('MIX_WAV',f'{SRC}/{NAME}_master.wav');MP3=os.environ.get('MIX_MP3','/workspace/mixes/dj-mix-03-60.mp3')
T=174.0;BEAT=60/T;BAR=4*BEAT;SR=44100
TOL_DRIFT_MS=10;MIN_ANCHOR_S=210;MIN_OVERLAP=16;CUT_DB=15;TP_MAX=-1.0
# 2026-11-07 pro calibration (37 admitted clips in protrans/results/admitted.json):
# non-phrase energy_events at 6.0 dB passed only 27/37 (73%). the listener confirmed the
# Mix 07 r12 Just Hold On→Solitude 6.2 dB dip is fine, so 6 dB was over-strict.
# Per-transition max non-phrase drop: p50=0.0 p90=9.58 p95=12.2 p100=14.98 dB
# (10 fails: 6.04, 6.26, 7.44, 7.75, 8.01, 9.52, 9.66, 11.93, 13.27, 14.98).
# DROP_DB=12.2 lets 35/37 (~95%) of pro transitions pass. Beat-align 10 ms TOL
# is unchanged: the under-report on Daydreaming→Parallel was search width / low-corr
# skipping / missing inter-deck phase, not the 10 ms gate (pros were not used to loosen it).
DROP_DB=12.2
CORR_MIN=0.65          # body mix-vs-source: below this at 0 is no-info, not a fail
INTERDECK_CORR=0.35    # inter-deck peak recorded if corr reaches this (not a hard fail)
PHASE_BEATS=(-4,-3,-2,-1,1,2,3,4)  # extra downbeat/bar-phase centers to search
TAIL_BARS=5            # last N overlap bars: end-of-overlap drift / phase-slip
TAIL_CORR_MIN=0.55     # tail audible floor (r12 Parallel tail locks at 0.62 / -24 ms)
@functools.lru_cache()
def meta(): return json.load(open(f'{SRC}/{NAME}_meta.json'))
@functools.lru_cache()
def keys():
  K=json.load(open(f'{SRC}/keys_full.json'));out={}
  for b,v in K.items():
    votes=[x[0] for x in v.values()];out[b]=max(set(votes),key=votes.count)
  out.update(json.load(open(os.path.join(os.path.dirname(__file__),'keys_extra.json'))))  # curated tracklist keys win
  return out
def camelot_ok(a,b):
  if not a or not b: return False
  na,la=int(a[:-1]),a[-1];nb,lb=int(b[:-1]),b[-1]
  if a==b:return True
  if la==lb and (na-nb)%12 in (1,11):return True
  return na==nb
@functools.lru_cache()
def audio():
  info=sf.info(WAV);assert info.samplerate==SR;m=np.empty(info.frames,np.float32);i=0
  for blk in sf.blocks(WAV,blocksize=SR*60,dtype='float32',always_2d=True):m[i:i+len(blk)]=blk.mean(1);i+=len(blk)
  return m[:i]
@functools.lru_cache()
def onset():
  y=librosa.resample(audio(),orig_sr=SR,target_sr=22050);hop=64
  return onset_chunked(y,22050,hop),22050/hop
def onset_chunked(y,sr,hop,n_fft=2048,F=60000):
  """Same result as librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop) (center=True, constant pad, ref=1, top_db=80),
  but the mel spectrogram is built in frame-aligned chunks so a 60+ min mix fits in RAM (full STFT would be ~11 GB)."""
  yp=np.pad(y,n_fft//2,mode='constant');nfr=1+(len(yp)-n_fft)//hop;fb=librosa.filters.mel(sr=sr,n_fft=n_fft);M=[]
  for f0 in range(0,nfr,F):
    f1=min(nfr,f0+F);seg=yp[f0*hop:(f1-1)*hop+n_fft]
    S=np.abs(librosa.stft(seg,n_fft=n_fft,hop_length=hop,center=False))**2;M.append((fb@S).astype(np.float32))
  return librosa.onset.onset_strength(S=librosa.power_to_db(np.concatenate(M,axis=1)),sr=sr,hop_length=hop)
@functools.lru_cache()
def bar_rms():
  m=audio();n=int(len(m)/SR/BAR)
  return np.array([20*np.log10(np.sqrt(np.mean(m[int(i*BAR*SR):int((i+1)*BAR*SR)]**2))+1e-9) for i in range(n)])
def phase_ms(b0,nb=4):
  o,fr=onset();per=BEAT/4;  # 16th fold (8th fold aliases kick/snare/hat in DnB)
  i0=int(b0*BAR*fr);seg=o[i0:int((b0+nb)*BAR*fr)]
  if len(seg)<10 or seg.max()<=0:return None
  offs=np.arange(-per/2,per/2,0.001);g=np.arange(0,nb*BAR,per)
  sc=[seg[np.clip(np.round((g+x)*fr).astype(int),0,len(seg)-1)].mean() for x in offs]
  s=np.array(sc);
  if s.max()<1.3*s.mean():return None  # beatless
  return float(offs[s.argmax()]*1000)
@functools.lru_cache()
def ref_phase():
  ph=[p for p in (phase_ms(b) for b in range(0,len(bar_rms())-4,16)) if p is not None];return float(np.median(ph))
def decks(): return meta()['decks']
@functools.lru_cache(None)
def src_bars(b): return np.array(json.load(open(f'{SRC}/st/{b}.json'))['bar']['all'])
def deck_at(bar):
  return [d for d in decks() if d['start_bar']<=bar<d['end_bar']]
def src_of(d,bar): return d['full_map'][int(bar-d['start_bar'])]
def gain_at(d,k,bar):
  pts=d['auto'].get(k)
  if not pts:return 1.0
  return float(np.interp(bar,[p[0] for p in pts],[p[1] for p in pts]))
def kick_fold(b0,nb=8):
  m=audio();lo=sosfiltfilt(butter(2,120,'low',fs=SR,output='sos'),m[int(b0*BAR*SR):int((b0+nb)*BAR*SR)])
  e=np.array([np.sqrt(np.mean(lo[int(i*BEAT*SR):int((i+1)*BEAT*SR)]**2)) for i in range(nb*4)])
  if len(e)<nb*4:return None
  f=e.reshape(nb,4).mean(0);return f/ (f.sum()+1e-9)
def overlap_bars(A,B):
  s=max(A['start_bar'],B['start_bar']);e=min(A['end_bar'],B['end_bar']);return max(0,e-s)
def harmonic_overlap(A,B):
  s=max(A['start_bar'],B['start_bar']);e=min(A['end_bar'],B['end_bar']);n=0
  for b in range(int(s),int(e)):
    a=src_of(A,b)[1];bb=src_of(B,b)[1]
    if a in('mix','vocals') and bb in('mix','vocals') and gain_at(A,'mid',b+.5)>0.05 and gain_at(B,'mid',b+.5)>0.05:n+=1
  return n
def find(id_,near):
  c=[d for d in decks() if d['id']==id_ and not d['acap']];return min(c,key=lambda d:abs(d['start_bar']-near) if d['start_bar']<=near+64 else 1e9)
def transitions():
  out=[]
  for t in meta()['trans']:
    A=find(t['a'],t['start_bar']);B=[d for d in decks() if d['id']==t['b'] and not d['acap'] and abs(d['start_bar']-t['start_bar'])<1][0]
    echo='echo' in t['tech'];r=dict(a=t['a'],b=t['b'],tech=t['tech'],t=f"{int(t['start_bar']*BAR//60)}:{int(t['start_bar']*BAR%60):02d}")
    ref=ref_phase();ph=[phase_ms(b) for b in range(int(t['start_bar'])-8,int(t['end_bar'])+8,4) if not (echo and t['swap_bar']-1<=b<t['swap_bar']+4)]  # echo tail bars are free-running by design
    dev=[abs(((p-ref+43)%86.2)-43) for p in ph if p is not None];r['grid_phase_dev_ms']=round(max(dev),1) if dev else 0
    # drift = how far each audible deck sits from where its own source says it should be, 4-bar windows through the transition
    lags=[]
    for D in (A,B):
      for b0 in range(int(max(D['start_bar'],t['start_bar']-8)),int(min(D['end_bar'],t['end_bar']+8))-4+1,4):
        if src_of(D,b0)[1]!='mix':continue
        a=deck_alignment(D,b0,4,span_ms=40)
        if a['corr']>=0.8: lags.append(abs(a['lag_ms']))  # only windows where this deck is clearly audible/dominant
    r['drift_ms']=max(lags) if lags else 0;r['drift_windows']=len(lags)
    # whole-mix grid continuity is enforced by guardrails G1 (16th-fold, jitter<8 ms, abs<15 ms per the listener's spec); grid_phase_dev_ms kept as info only
    # Fine ±40 ms only: a default ±3-beat search locks onto a wrong-period peak (e.g. +328 ms / 1 beat at corr 0.52) and hides as a 'downbeat error'.
    r['downbeat_A']=deck_alignment(A,t['swap_bar']-12,span_ms=40);r['downbeat_B']=deck_alignment(B,t['swap_bar']+12,span_ms=40)
    r['overlap_bars']=0 if echo else overlap_bars(A,B);r['echo']=echo
    ka,kb=keys().get(t['a']),keys().get(t['b']);r['keys']=f'{ka}->{kb}';r['key_ok']=camelot_ok(ka,kb);r['harm_overlap']=harmonic_overlap(A,B)
    out.append(r)
  return out
def energy_events():
  R=bar_rms();ev=[];echo_bars={round(d['end_bar']) for d in decks() if d['echo']}
  for i in range(8,len(R)-1):
    base=np.median(R[i-8:i]);d=base-R[i]
    if d<DROP_DB or R[i-1]<base-DROP_DB: continue
    # intentional = the record itself breaks down there (its own phrase-boundary breakdown), not something the mix created
    phr=False
    for x in deck_at(i):
      if x['acap'] or src_of(x,i)[1]!='mix':continue
      a=src_bars(x['id']);k=src_of(x,i)[0]
      ctx=np.concatenate([a[max(0,k-8):k],a[k+1:k+9]]) if k<8 else a[k-8:k]
      if len(ctx) and np.median(ctx)-a[k]>=d-4:phr=True
    ech=any(abs(i-e)<=1 for e in echo_bars)
    ev.append(dict(bar=i,t=f'{int(i*BAR//60)}:{int(i*BAR%60):02d}',drop_db=round(float(d),1),phrase=phr,echo=ech,cut=float(R[i-1]-R[i])>CUT_DB))
  return ev
def true_peak():
  o=subprocess.run(['ffmpeg','-nostats','-i',MP3,'-af','ebur128=peak=true','-f','null','-'],capture_output=True,text=True).stderr
  s=o[o.rfind('Summary'):];return float(re.search(r'Peak:\s+(-?[\d.]+|-inf)',s.split('True peak')[1]).group(1)),float(re.search(r'I:\s+(-?[\d.]+)',s).group(1))

@functools.lru_cache(None)
def src_onset(b):
  y,sr=sf.read(f'{SRC}/st/{b}.wav',dtype='float32',always_2d=True);assert sr==SR,f'{b} at {sr} Hz'
  g=json.load(open(f'{SRC}/st/{b}.json'));y=librosa.resample(y.mean(1),orig_sr=SR,target_sr=22050)
  return librosa.onset.onset_strength(y=y,sr=22050,hop_length=64),g['downs'][0]
@functools.lru_cache()
def _nudges():
  f=os.path.join(SRC,os.environ.get('NUDGE','nudge.json'));return json.load(open(f)) if os.path.exists(f) else {}
def nudge_ms(b,k):return _nudges().get(b,{}).get(str(k),0)
def deck_alignment(d,bar,nb=8,span_ms=None,center_ms=0):
  """Cross-correlate the mix against the deck's own source at the bar it should be playing.
  Returns lag (ms) of best match; 0 beats & |ms|<=10 means the downbeat/bar is where the plan says.
  center_ms shifts the search window (used to probe whole-beat / half-bar / bar phase errors)."""
  bar=int(min(max(bar,d['start_bar']),d['end_bar']-nb))
  k,stem=src_of(d,bar)
  o,fr=onset();so,d0=src_onset(d['id'])
  m=o[int(bar*BAR*fr):int((bar+nb)*BAR*fr)];best=(-1e9,0)
  R=span_ms or 3*int(BEAT*1000)
  step=1 if span_ms else 2
  for lag_ms in range(int(center_ms)-R,int(center_ms)+R+1,step):
    # compare where the engine actually reads: bar by bar, each with its own source bar and warp nudge
    parts=[];ok=True;nbf=int(round(BAR*fr))
    for j in range(nb):
      kj=d['full_map'][int(bar-d['start_bar'])+j][0] if int(bar-d['start_bar'])+j<len(d['full_map']) else k+j
      i0=int((d0+kj*BAR-nudge_ms(d['id'],kj)/1000+lag_ms/1000)*fr)
      if i0<0 or i0+nbf>len(so):ok=False;break
      parts.append(so[i0:i0+nbf])
    if not ok:continue
    s=np.concatenate(parts)
    n=min(len(m),len(s))
    if n<int(0.9*nb*nbf):continue
    mm,ss=m[:n],s[:n]
    if mm.std()==0 or ss.std()==0:continue
    c=float(np.corrcoef(mm,ss)[0,1])
    if np.isnan(c):continue
    if c>best[0]:best=(c,lag_ms)
  return dict(lag_ms=best[1],corr=round(best[0],2))

def deck_phase_alignment(d,bar,nb=2):
  """Mix-vs-source with a fine ±40 ms peak plus extra centers at ±1..4 beats.
  A 1-beat (345 ms) error used to hide as ~0 ms because bar_alignment_report
  only searched ±40 ms (and F1 folds phase into a 16th). Even multiples of a
  beat (2 = half-bar/snare period, 4 = bar) are periodic aliases in DnB and are
  recorded but not preferred over a good lock at 0."""
  fine=deck_alignment(d,bar,nb,span_ms=40,center_ms=0)
  best=dict(fine); best['lag_0']=fine['lag_ms']; best['corr_0']=fine['corr']
  for bt in PHASE_BEATS:
    alt=deck_alignment(d,bar,nb,span_ms=20,center_ms=int(round(bt*BEAT*1000)))
    if alt['corr']>best['corr']:
      best.update(alt)
  best['beat_off']=round(best['lag_ms']/(BEAT*1000),2)
  return best

def _src_onset_at(d,bar,nb,lag_ms,fr,so,d0):
  k,stem=src_of(d,bar)
  parts=[];nbf=int(round(BAR*fr))
  for j in range(nb):
    jj=int(bar-d['start_bar'])+j
    kj=d['full_map'][jj][0] if 0<=jj<len(d['full_map']) else k+j
    i0=int((d0+kj*BAR-nudge_ms(d['id'],kj)/1000+lag_ms/1000)*fr)
    if i0<0 or i0+nbf>len(so):return None
    parts.append(so[i0:i0+nbf])
  return np.concatenate(parts)

def interdeck_phase(A,B,bar,nb=2):
  """Planned-source vs planned-source downbeat phase (does not depend on which
  deck currently dominates the mixdown). Search ±40 ms around 0 and ±1..4 beats."""
  fr=22050/64
  soA,d0A=src_onset(A['id']);soB,d0B=src_onset(B['id'])
  best=(-1e9,0)
  centers=[0]+[int(round(bt*BEAT*1000)) for bt in PHASE_BEATS]
  for c0 in centers:
    span=40 if c0==0 else 20
    for lag in range(c0-span,c0+span+1,2):
      a=_src_onset_at(A,bar,nb,0,fr,soA,d0A)
      b=_src_onset_at(B,bar,nb,lag,fr,soB,d0B)
      if a is None or b is None:continue
      n=min(len(a),len(b));a,b=a[:n],b[:n]
      if a.std()==0 or b.std()==0:continue
      c=float(np.corrcoef(a,b)[0,1])
      if c>best[0]:best=(c,lag)
  c0=None
  a0=_src_onset_at(A,bar,nb,0,fr,soA,d0A); b0=_src_onset_at(B,bar,nb,0,fr,soB,d0B)
  if a0 is not None and b0 is not None:
    n=min(len(a0),len(b0)); a0,b0=a0[:n],b0[:n]
    if a0.std()>0 and b0.std()>0: c0=round(float(np.corrcoef(a0,b0)[0,1]),2)
  return dict(lag_ms=best[1],corr=round(best[0],2),beat_off=round(best[1]/(BEAT*1000),2),
              lag_0=0,corr_0=-1.0 if c0 is None else c0)

# ---------- vocal clash (demucs vocal stems) ----------
@functools.lru_cache(None)
def src_voc(b):
  g=json.load(open(f'{SRC}/st/{b}.json'))['bar'];v=np.array(g.get('voc',[-100]*len(g['all'])))
  return v,float(np.percentile(v,95))
VOC_REL_DB=12   # a bar "has vocal" if its vocal-stem energy is within 12 dB of the track's own loud-vocal level
VOC_GAIN=0.3    # ...and the deck's effective vocal gain is above this
def vocal_bars(d):
  v,ref=src_voc(d['id']);out=set()
  for i,(k,stem) in enumerate(d['full_map']):
    bar=d['start_bar']+i
    if stem not in('mix','vocals') or k>=len(v):continue
    g=gain_at(d,'gain',bar+.5)*max(gain_at(d,'mid',bar+.5),gain_at(d,'high',bar+.5))*(gain_at(d,'voc',bar+.5) if stem=='mix' else 1)
    if v[k]>ref-VOC_REL_DB and g>VOC_GAIN: out.add(int(bar))
  return out
def vocal_clashes():
  """bars where 2+ decks are audibly singing. Whitelisted = an acapella deck from a plan step marked acap_whitelist, keys compatible."""
  wl={p['id'] for p in meta()['plan'] if p.get('acap_whitelist')}
  plan_ids=[p['id'] for p in meta()['plan']]
  D=[d for d in decks()];VB=[vocal_bars(d) for d in D];res=[]
  for i in range(len(D)):
    for j in range(i+1,len(D)):
      both=VB[i]&VB[j]
      if not both:continue
      a,b=D[i],D[j];ac=a if a['acap'] else b if b['acap'] else None;other=b if ac is a else a
      ok=False
      if ac is not None:
        host=other['id'];ok=host in wl and camelot_ok(keys()[ac['id']],keys()[host])
      res.append(dict(a=a['id'],b=b['id'],bars=len(both),t=f"{int(min(both)*BAR//60)}:{int(min(both)*BAR%60):02d}",acapella=ac is not None,whitelisted=ok))
  return res
# ---------- per-bar beat alignment on the final mixdown ----------
def bar_alignment_report(deck_pair=None):
  """Overlap beat / downbeat phase, scored per bar (2-bar rolling window;
  1-bar at the last overlap bar). Does not average over the whole overlap.

  For each overlap bar: (1) mix-vs-source with a wide phase search (±40 ms around
  0 and around ±1..4 beats) for every deck that is not >6 dB under the other;
  (2) inter-deck planned-source phase when both decks are present (diagnostic).

  Fail/no-info policy lives in alignment_failures: body low-corr is no-info;
  the last TAIL_BARS use a slightly lower audible floor so end-of-overlap
  drift (tempo ramp, loop splice, swap_pos, grid ending) cannot hide.

  deck_pair=(A,B) optional: only that overlap (used by the trainwreck regression)."""
  out=[];seen=set()
  pairs=[]
  if deck_pair:
    pairs=[tuple(deck_pair)]
  else:
    for d in decks():
      if d.get('acap'):continue
      for e in decks():
        if e is d or e.get('acap') or (e['id'],d['id']) in seen:continue
        seen.add((d['id'],e['id']));pairs.append((d,e))
  for d,e in pairs:
    s0=int(max(d['start_bar'],e['start_bar']));t0=int(min(d['end_bar'],e['end_bar']))
    if t0-s0<2:continue
    for b in range(s0,t0):
      nb=2 if b+2<=t0 else 1
      for D,O in ((d,e),(e,d)):
        if src_of(D,b)[1]!='mix':continue
        if gain_at(D,'gain',b+1)<0.5*gain_at(O,'gain',b+1):continue
        a=deck_phase_alignment(D,b,nb)
        out.append(dict(bar=b,deck=D['id'],lag=a['lag_ms'],corr=a['corr'],
                        beat_off=a.get('beat_off'),lag_0=a.get('lag_0',a['lag_ms']),
                        corr_0=a.get('corr_0',a['corr']),kind='mix',
                        overlap_start=s0,overlap_end=t0,tail=b>=t0-TAIL_BARS,
                        window_bars=nb))
      gD,gE=gain_at(d,'gain',b+1),gain_at(e,'gain',b+1)
      if gD>=0.15 and gE>=0.15 and src_of(d,b)[1]=='mix' and src_of(e,b)[1]=='mix':
        p=interdeck_phase(d,e,b,nb)
        out.append(dict(bar=b,deck=f"{d['id']}>{e['id']}",lag=p['lag_ms'],corr=p['corr'],
                        beat_off=p.get('beat_off'),lag_0=p.get('lag_0',0),corr_0=p.get('corr_0',-1),
                        kind='interdeck',overlap_start=s0,overlap_end=t0,
                        tail=b>=t0-TAIL_BARS,window_bars=nb))
  return out

def _odd_beat_off(lag_ms):
  """True when |lag| is a downbeat/phase error, not a DnB periodic alias.

  Onset xcorr on DnB often prefers the 2-beat snare period or the 4-beat bar
  even when the tracks are actually locked (wrong-period peak). Those even
  aliases are not fails by themselves. Odd-beat (1, 3) and half-beat (0.5,
  1.5, 2.5) offsets are — they are the heard trainwreck / wrong-downbeat case.
  """
  b=abs(lag_ms)/(BEAT*1000.0)
  nearest_even=round(b/2.0)*2.0
  return abs(b-nearest_even)>0.15

def alignment_failures(rows=None):
  """Rows that fail the calibrated beat/phase gate. 10 ms TOL unchanged.

  Each bar is judged on its own rolling window; the last TAIL_BARS of an overlap
  use a slightly lower audible floor. There is no overlap-wide average, so
  end-of-overlap drift / phase slip cannot hide behind a good early lock.

  Mix-vs-source:
    - corr_0 below the audible floor → no-info (skip). Body floor CORR_MIN;
      tail floor TAIL_CORR_MIN so a late fade that still locks (e.g. 0.62) with
      |lag_0| > 10 ms is a fail (r12 Daydreaming→Parallel last ~5 bars).
    - corr_0 at/above the floor and |lag_0| > 10 ms → fail (drift / phase slip).
    - a stronger odd-beat (1, 3, 0.5, 1.5) peak while |lag_0| <= 10 ms is a
      DnB alias, not a fail (r17 Parallel→Inside bar 1211). Even-beat 2/4
      aliases are likewise periodicity, not fails.

  Inter-deck source-vs-source is recorded but not a hard fail (two different
  tracks' drums often xcorr better at ±1/±3 even when each is locked to the mix).
  """
  rows=bar_alignment_report() if rows is None else rows
  bad=[]
  for r in rows:
    c0=r.get('corr_0'); c0=-1.0 if c0 is None else c0
    l0=r.get('lag_0', 0)
    if r.get('kind')=='interdeck':
      # Reported for diagnosis. Do not fail the mix on inter-deck alone.
      continue
    t0=r.get('overlap_end')
    tail=bool(r.get('tail')) if 'tail' in r else (t0 is not None and r['bar']>=t0-TAIL_BARS)
    floor=TAIL_CORR_MIN if tail else CORR_MIN
    if c0<floor:
      continue  # no-info (search miss / other deck dominating / dissimilar patterns)
    if abs(l0)>TOL_DRIFT_MS:
      bad.append(r)
      continue
    # A stronger odd-beat xcorr peak while |lag_0| <= 10 ms is a DnB alias
    # (heard-OK r17 Parallel→Inside bar 1211: l0=-2 ms / c0=0.62 vs 3-beat 0.79).
    # A real 1-beat wreck cannot lock at 0 within 10 ms with corr_0 above the floor.
  return bad
