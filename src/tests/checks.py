"""Mix QA checks. Config via env: MIX_SRC (render dir), MIX_NAME (meta prefix), MIX_WAV (mastered wav), MIX_MP3."""
import os,json,subprocess,re,functools,numpy as np,soundfile as sf,librosa,glob
from scipy.signal import butter,sosfiltfilt
SRC=os.environ.get('MIX_SRC','/workspace/mixes/src2');NAME=os.environ.get('MIX_NAME','mix2b')
WAV=os.environ.get('MIX_WAV',f'{SRC}/master.wav');MP3=os.environ.get('MIX_MP3','/workspace/mixes/dj-mix-02b.mp3')
T=174.0;BEAT=60/T;BAR=4*BEAT;SR=44100
TOL_DRIFT_MS=10;MIN_ANCHOR_S=210;MIN_OVERLAP=16;DROP_DB=6;CUT_DB=15;TP_MAX=-1.0
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
  pts=d['auto'][k];
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
    r['downbeat_A']=deck_alignment(A,t['swap_bar']-12);r['downbeat_B']=deck_alignment(B,t['swap_bar']+12)
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
def deck_alignment(d,bar,nb=8,span_ms=None):
  """Cross-correlate the mix against the deck's own source at the bar it should be playing.
  Returns lag (beats, ms) of best match; 0 beats & |ms|<=10 means the downbeat/bar is where the plan says."""
  bar=int(min(max(bar,d['start_bar']),d['end_bar']-nb))
  k,stem=src_of(d,bar)
  o,fr=onset();so,d0=src_onset(d['id'])
  m=o[int(bar*BAR*fr):int((bar+nb)*BAR*fr)];best=(-1e9,0)
  R=span_ms or 3*int(BEAT*1000)
  for lag_ms in range(-R,R+1,1 if span_ms else 2):
    # compare where the engine actually reads: bar by bar, each with its own source bar and warp nudge
    parts=[];ok=True;nbf=int(round(BAR*fr))
    for j in range(nb):
      kj=d['full_map'][int(bar-d['start_bar'])+j][0] if int(bar-d['start_bar'])+j<len(d['full_map']) else k+j
      i0=int((d0+kj*BAR-nudge_ms(d['id'],kj)/1000+lag_ms/1000)*fr)
      if i0<0 or i0+nbf>len(so):ok=False;break
      parts.append(so[i0:i0+nbf])
    if not ok:continue
    s=np.concatenate(parts)[:len(m)]
    if len(s)<len(m):continue
    c=float(np.corrcoef(m,s)[0,1]) if s.std()>0 else -1
    if c>best[0]:best=(c,lag_ms)
  return dict(lag_ms=best[1],corr=round(best[0],2))

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
def bar_alignment_report():
  """For every bar where 2+ decks overlap: cross-correlate the mixdown onset envelope with each audible deck's source (2-bar window, ±40 ms)."""
  out=[];seen=set()
  for d in decks():
    if d['acap']:continue
    for e in decks():
      if e is d or e['acap'] or (e['id'],d['id']) in seen:continue
      s=int(max(d['start_bar'],e['start_bar']));t=int(min(d['end_bar'],e['end_bar']))
      if t-s<2:continue
      seen.add((d['id'],e['id']))
      for b in range(s,t-1):
        for D in (d,e):
          if src_of(D,b)[1]!='mix':continue  # stems (drum loops) don't share the full-mix source's onset shape -> xcorr is biased; F1/G1 guardrails cover them
          a=deck_alignment(D,b,2,span_ms=40)
          if a['corr']>=0.6: out.append(dict(bar=b,deck=D['id'],lag=a['lag_ms'],corr=a['corr']))
  return out
