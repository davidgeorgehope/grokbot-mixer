"""Per-transition 'listen proxy': re-render the two decks of every transition SEPARATELY from the meta
(same engine), then per overlap bar measure what the summed mix can't show:
  flam_ms   - onset cross-correlation lag between deck A and deck B (beats landing apart)
  chroma    - cosine of A/B chroma where both decks have harmonic content (key clash proxy -> 1-cos)
  low_both  - bars where both decks carry real sub/bass (<150 Hz) energy at once (bass doubling)
  voc_both  - bars where both decks have strong vocals
  hole      - bars where summed level drops >6 dB under the pre-transition level (energy hole)"""
import os,sys,json,functools,numpy as np,librosa
from scipy.signal import butter,sosfiltfilt
SRC=os.environ.get('MIX_SRC','/workspace/mixes/src2');NAME=os.environ.get('MIX_NAME','mix360')
SR=44100;BAR=4*60/174.0
@functools.lru_cache()
def meta(): return json.load(open(f'{SRC}/{NAME}_meta.json'))
def _render(d):
  cwd=os.getcwd();os.chdir(SRC);sys.path.insert(0,SRC)
  try:
    import engine
    D=engine.Deck(d['id'],d['start_bar'],0,0);D.map=[tuple(x) for x in d['full_map']]
    D.auto={k:[tuple(p) for p in v] for k,v in d['auto'].items()};y=D.render().mean(1).astype(np.float32)
    engine._cache.clear();return y
  finally: os.chdir(cwd)
LP=butter(4,150,'low',fs=SR,output='sos')
def bar_feats(y,start_bar,bars):
  out=[]
  for m in bars:
    i=int(round((m-start_bar)*BAR*SR));seg=y[i:i+int(BAR*SR)]
    if len(seg)<int(BAR*SR*0.9):out.append(None);continue
    rms=float(np.sqrt(np.mean(seg**2))+1e-9);low=float(np.sqrt(np.mean(sosfiltfilt(LP,seg)**2))+1e-9)
    s22=librosa.resample(seg,orig_sr=SR,target_sr=22050)
    on=librosa.onset.onset_strength(y=s22,sr=22050,hop_length=64)
    ch=librosa.feature.chroma_cqt(y=s22,sr=22050,hop_length=512).mean(1)
    out.append(dict(rms=rms,low=low,on=on,ch=ch))
  return out
def xlag_ms(a,b,maxms=60):
  fr=22050/64;L=int(maxms/1000*fr);a=(a-a.mean())/(a.std()+1e-9);b=(b-b.mean())/(b.std()+1e-9);n=min(len(a),len(b))
  best=max(range(-L,L+1),key=lambda k:np.dot(a[max(0,k):n+min(0,k)],b[max(0,-k):n-max(0,k)]))
  c=np.dot(a[max(0,best):n+min(0,best)],b[max(0,-best):n-max(0,best)])/n;return best/fr*1000,float(c)
def analyse(ti):
  m=meta();t=m['trans'][ti];D=m['decks']
  A=[d for d in D if d['id']==t['a'] and d['start_bar']<t['start_bar']+1 and not d['acap']][-1]
  B=[d for d in D if d['id']==t['b'] and abs(d['start_bar']-t['start_bar'])<1e-6][0]
  s,e=int(t['start_bar']),int(min(A['end_bar'],t['end_bar']))
  ya,yb=_render(A),_render(B);bars=list(range(s,e))
  fa=bar_feats(ya,A['start_bar'],bars);fb=bar_feats(yb,B['start_bar'],bars)
  pre=bar_feats(ya,A['start_bar'],range(s-8,s));ref=20*np.log10(np.median([p['rms'] for p in pre if p]))
  R=[]
  for m_,a,b in zip(bars,fa,fb):
    if not a or not b:continue
    r=dict(bar=m_,t=f"{int(m_*BAR//60)}:{int(m_*BAR%60):02d}")
    la,lb=20*np.log10(a['rms']),20*np.log10(b['rms']);r['lvlA'],r['lvlB']=round(la,1),round(lb,1)
    both=la>ref-14 and lb>ref-14
    if both and a['on'].std()>0 and b['on'].std()>0:
      r['flam_ms'],r['xc']=[round(x,2) for x in xlag_ms(a['on'],b['on'])]
    r['chroma']=round(float(np.dot(a['ch'],b['ch'])/(np.linalg.norm(a['ch'])*np.linalg.norm(b['ch'])+1e-9)),2) if both else None
    r['lowA'],r['lowB']=round(20*np.log10(a['low']),1),round(20*np.log10(b['low']),1)
    r['low_both']=bool(r['lowA']>ref-12 and r['lowB']>ref-12)
    r['sum_db']=round(20*np.log10(np.sqrt(np.mean((ya[int(round((m_-A['start_bar'])*BAR*SR)):][:int(BAR*SR)]+yb[int(round((m_-B['start_bar'])*BAR*SR)):][:int(BAR*SR)])**2))+1e-9)-ref,1)
    R.append(r)
  return dict(i=ti,a=t['a'],b=t['b'],tech=t['tech'],t=f"{int(t['start_bar']*BAR//60)}:{int(t['start_bar']*BAR%60):02d}",bars=R)
if __name__=='__main__':
  for ti in map(int,sys.argv[1:]):
    r=analyse(ti);print(r['t'],r['a'],'->',r['b'],r['tech'])
    for b in r['bars']:print(' ',b)
def phase_ms_env(on,fr=22050/64,per=60/174/2):
  offs=np.arange(-per/2,per/2,0.001);g=np.arange(0,BAR,per)
  s=np.array([on[np.clip(np.round((g+x)*fr).astype(int),0,len(on)-1)].mean() for x in offs])
  return None if s.max()<1.3*s.mean() else float(offs[s.argmax()]*1000)
def report(ti):
  """per-transition summary used by test_deck_pair_listen_proxy"""
  m=meta();t=m['trans'][ti];D=m['decks']
  A=[d for d in D if d['id']==t['a'] and d['start_bar']<t['start_bar']+1 and not d['acap']][-1]
  B=[d for d in D if d['id']==t['b'] and abs(d['start_bar']-t['start_bar'])<1e-6][0]
  s=int(t['start_bar']);e=int(min(A['end_bar'],t['end_bar']));sw=int(t['swap_bar'])
  ya,yb=_render(A),_render(B);bars=list(range(s-8,max(e,sw+8)))
  fa=bar_feats(ya,A['start_bar'],bars);fb=bar_feats(yb,B['start_bar'],bars)
  db=lambda f:20*np.log10(f['rms']) if f else -120
  ref=np.median([db(f) for f in fa[:8]]);flams=[];gaps=[];rows=[]
  for m_,a,b in zip(bars,fa,fb):
    la,lb=db(a),db(b);row=dict(bar=m_,t=f"{int(m_*BAR//60)}:{int(m_*BAR%60):02d}",A=round(la-ref,1),B=round(lb-ref,1))
    if s<=m_<e and a and b and la>ref-12 and lb>ref-12 and abs(la-lb)<12:
      pa,pb=phase_ms_env(a['on']),phase_ms_env(b['on'])
      if pa is not None and pb is not None:row['flam']=round(abs(((pa-pb+43.1)%86.2)-43.1),1);flams.append(row['flam'])
    rows.append(row)
  la=[r['A'] for r in rows if s<=r['bar']<e]
  for i in range(1,len(la)-1):
    if la[i]<-30 and max(la[i+1:])>la[i]+12:gaps.append(rows[[r['bar'] for r in rows].index(s)+i]['t'])
  sumdb=lambda r0,r1:float(np.median([10*np.log10(10**(r['A']/10)+10**(r['B']/10)) for r in rows if r0<=r['bar']<r1]))
  drop=round(sumdb(sw,sw+8)-sumdb(sw-8,sw),1)
  bad_flam=[r for r in rows if r.get('flam',0)>15]
  return dict(i=ti,t=f"{int(s*BAR//60)}:{int(s*BAR%60):02d}",a=t['a'],b=t['b'],tech=t['tech'],flam_med=round(float(np.median(flams)),1) if flams else None,
    flam_bars=len(flams),flam_bad=[(r['t'],r['flam']) for r in bad_flam],gaps=gaps,drop_gain_db=drop,rows=rows)
KLP=butter(4,120,'low',fs=SR,output='sos');BEATS=60/174
def kick_env(seg):
  k=sosfiltfilt(KLP,seg);s22=librosa.resample(k,orig_sr=SR,target_sr=22050)
  return librosa.onset.onset_strength(y=s22,sr=22050,hop_length=64,n_mels=16,fmax=200)
def snare_env(seg):
  s22=librosa.resample(seg,orig_sr=SR,target_sr=22050)
  return librosa.onset.onset_strength(y=s22,sr=22050,hop_length=64,fmin=1000) if False else librosa.onset.onset_strength(y=s22,sr=22050,hop_length=64)
def beat_phase(on,fr=22050/64,per=BEATS,nb=1):
  """phase (ms) of onset energy folded at the BEAT period (no 8th-note ambiguity), None if beatless"""
  offs=np.arange(-per/2,per/2,0.002);g=np.arange(0,nb*BAR-1e-6,per)
  s=np.array([on[np.clip(np.round((g+x)*fr).astype(int),0,len(on)-1)].mean() for x in offs])
  return None if s.max()<1.6*np.median(s) else float(offs[s.argmax()]*1000)
def deck_selfcheck(d,y=None):
  """within-track glitch scan of one deck rendered alone: per bar beat phase (2-bar windows) vs the mix grid,
  plus level step at each bar boundary. Catches nudge/loop/stretch artifacts anywhere, not only in transitions."""
  y=_render(d) if y is None else y;n=int(d['end_bar']-d['start_bar']);rows=[]
  for k in range(0,n-1):
    i=int(round(k*BAR*SR));seg=y[i:i+int(2*BAR*SR)]
    if len(seg)<int(2*BAR*SR):break
    lv=20*np.log10(np.sqrt(np.mean(seg[:int(BAR*SR)]**2))+1e-9)
    p=beat_phase(snare_env(seg),nb=2);src=d['full_map'][k]
    rows.append(dict(bar=d['start_bar']+k,t=f"{int((d['start_bar']+k)*BAR//60)}:{int((d['start_bar']+k)*BAR%60):02d}",src=src,lvl=round(lv,1),ph=None if p is None else round(p,0)))
  return rows
