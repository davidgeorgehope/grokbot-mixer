"""Beats -> melody-only blends (the listener 2026-11-02, Mix 06 v2 A/B: "if you blend from a song with beats into a solid melody only
section and gently fade it, it's not great ... it's ok to loop into beats too").
The outgoing drums fade slowly over the incoming track's beatless intro/breakdown, so for bars neither deck carries a clear groove.
The gradual-fade rule stays; this module adds
  * bm1(M)              detector: overlap bars with outgoing drums ON and incoming drums OFF (both decks audible) for >= BM_MIN bars
                        -> warning code BM1 'beats into melody, groove gap' (guardrails WARN_ONLY, eval/fix_playbook.json)
  * ib (incoming beat loop): the incoming track's own drums+bass stem (beatstem.py, st/<id>.dnb.wav) looped from a later clean phrase,
                        on its own grid, under its beatless bars, handing over to its real drums when they arrive. Mirror of the
                        outgoing beat-only outro 'lx': one static trim (like LX_TRIM) and a 16th-grid re-phase (like _lx_shift).
  * dswap (drum swap on a phrase line): the outgoing drums+bass stem is fast-faded (DSWAP_XF bars, default 1) out on a phrase
                        boundary at the bar the incoming beat arrives (real drums, or the ib loop once it is up in the mix);
                        the outgoing melody keeps its gradual crossfader tail. TAIL (test_structure_tail) exempts exactly this:
                        the drop must disappear when the dswap is removed (so a full-mix abrupt fade still blocks) and the
                        incoming deck must carry a beat at that bar.
Both are deck-level keys rendered by engine.render_deck (d['ib'], d['dswap']); apply(M,i,mode) adds them to a meta (dry or full).
mix_simple.py applies plan step 'bm_fix' ('ib' | 'dswap' | 'ib+dswap') or env BM_FIX (to every BM1 blend)."""
import os,json,numpy as np
BM_MIN=int(os.environ.get('BM_MIN',4));AUD=10**(-20/20)
_D={}
def drums(b,src='.'):
  """per source bar: (drums dB, on mask = within 8 dB of the track's 75th pct, off mask = > 14 dB under it)"""
  if (b,src) not in _D:
    d=np.array(json.load(open(f'{src}/st/{b}.json'))['bar']['drums'],float);ref=np.percentile(d,75);_D[(b,src)]=(d,d>ref-8,d<ref-18)
  return _D[(b,src)]
def gain_at(d,bar):
  p=d['auto'].get('gain') or []
  return float(np.interp(bar,[q[0] for q in p],[q[1] for q in p])) if p else 1.0
def src_at(d,bar):
  j=int(bar-d['start_bar']);fm=d['full_map'];return fm[j] if 0<=j<len(fm) else (None,None)
def beat_in(d,mb,src='.'):
  """True when deck d carries a beat at mix bar mb: its own drums are on there, or its ib loop covers that bar"""
  j=int(mb-d['start_bar']);ib=d.get('ib')
  if ib and ib['k0']<=j<ib['k1']:return True
  s,_=src_at(d,mb);on=drums(d['id'],src)[1]
  return s is not None and 0<=s<len(on) and bool(on[s])
def gap_bars(M,i,src='.'):
  """overlap bars of blend i where outgoing drums are on, incoming drums are off (and no ib loop), both decks audible"""
  t=M['trans'][i];A,B=M['decks'][i],M['decks'][i+1];bad=[]
  for mb in range(int(t['start_bar']),int(t['end_bar'])):
    sa,ka=src_at(A,mb);sb,_=src_at(B,mb)
    if sa is None or sb is None:continue
    if ka=='beat' or A.get('dswap') and mb>=A['dswap']['bar']:a_on=ka=='beat' and not A.get('dswap')
    else:a_on=bool(drums(A['id'],src)[1][min(sa,len(drums(A['id'],src)[1])-1)])
    j=mb-B['start_bar'];ibc=B.get('ib') and B['ib']['k0']<=j<B['ib']['k1']
    b_off=bool(drums(B['id'],src)[2][min(sb,len(drums(B['id'],src)[2])-1)]) and not ibc
    if a_on and b_off and gain_at(A,mb+.5)>AUD and gain_at(B,mb+.5)>AUD:bad.append(mb)
  return bad
def runs(bars):
  out=[];
  for b in bars:
    if out and b==out[-1][1]:out[-1][1]=b+1
    else:out.append([b,b+1])
  return out
def bm1(M,src='.',nmin=None):
  """BM1 cases: [{trans, a, b, bar0, bar1, bars, t (mm:ss)}] for runs >= BM_MIN bars"""
  nmin=nmin or BM_MIN;BAR=M.get('bar_sec',240/174.);res=[]
  for i,t in enumerate(M['trans']):
    for b0,b1 in runs(gap_bars(M,i,src)):
      if b1-b0>=nmin:s=b0*BAR;res.append(dict(trans=i,a=t['a'],b=t['b'],bar0=b0,bar1=b1,bars=b1-b0,sec=round(s,1),t=f'{int(s//60)}:{int(s%60):02d}'))
  return res
def first_beat(d,src='.',k_from=0):
  """first deck index >= k_from where the deck's own drums are on for 2 bars running (its real beat arrives)"""
  on=drums(d['id'],src)[1];fm=d['full_map']
  for k in range(k_from,len(fm)-1):
    s0,s1=fm[k][0],fm[k+1][0]
    if fm[k][1]=='mix' and s0<len(on) and s1<len(on) and on[s0] and on[s1]:return k
  return None
def _steady_bass(b,p,L,tol=6.0):
  import beatstem,engine as E,soundfile as sf,bassgap as G
  y,_=sf.read(beatstem.ensure(b),dtype='float32',always_2d=True);tr=E.track(b)
  nb=int((len(y)/E.SR-tr['d0'])/E.BAR);al=G.bar_db(y,E.SR,E.BAR*E.SR,0,nb,ofs=tr['d0']*E.SR);ref=np.nanpercentile(al,75)
  db=al[p:p+L];return bool(len(db)==L and np.all(np.isfinite(db)) and db.min()>=ref-tol)  # every bar within tol of the track's groove bass
def loop_src(b,after,src='.',nth=1):
  """a later clean beat phrase of track b (phrase-aligned, beatstem.lx_len >= 8) at/after source bar `after`"""
  import beatstem
  cwd=os.getcwd();os.chdir(src)
  try:
    nb=len(drums(b,'.')[0])
    for p in list(range((after+7)//8*8,nb-8,8)):
      L=beatstem.lx_len(b,p)
      # BASSGAP (2026-11-02 19:33 ET): the loop phrase must carry steady bass (q_cZ phrase 64-80 had a 12-bar bass break, so the
      # loop left a <150 Hz hole under the AC cut). Shrink to the longest steady 16/8/4 from p, else skip the phrase.
      while L and not _steady_bass(b,p,L):L=L//2 if L>4 else 0
      if L:
        nth-=1
        if nth<=0:return p,L
  finally:os.chdir(cwd)
  return None
def apply(M,i,mode,src='.'):
  """add ib / dswap to blend i of meta M (in place). returns notes; raises ValueError when the option is not realisable here"""
  t=M['trans'][i];A,B=M['decks'][i],M['decks'][i+1];s,e=int(t['start_bar']),int(t['end_bar']);notes=[]
  # variants (the listener 2026-11-02 14:03 ET: options, not rules): 'dswap@-1' / 'dswap@+1' (1 bar early/late), 'dswap@next' (next phrase line),
  # 'ib:8' (8-bar loop), 'ib@2' (2nd clean beat phrase as loop source). Combine with '+', e.g. 'ib:8+dswap@next'.
  opt={};modes=[]
  for m in mode.split('+'):
    base=m.split('@')[0].split(':')[0];modes.append(base)
    if '@' in m:opt[base+'@']=m.split('@')[1]
    if ':' in m:opt[base+':']=int(m.split(':')[1].split('@')[0])
  k1=first_beat(B,src)
  if 'ib' in modes:
    if k1 is None or k1<BM_MIN:raise ValueError(f'ib: {B["id"]} has its beat from deck bar {k1}: nothing to fill')
    pl=loop_src(B['id'],B['full_map'][k1][0],src,int(opt.get('ib@',1)))
    if not pl:raise ValueError(f'ib: no clean beat phrase in {B["id"]}')
    p,L=pl;L=min(L,opt.get('ib:',L));B['ib']=dict(p=p,L=L,k0=0,k1=k1,xf=float(os.environ.get('IB_XF',0.25)))
    notes.append(f"incoming beat loop: {B['id']} drums+bass phrase {p}-{p+L} looped under its beatless bars {B['full_map'][0][0]}-{B['full_map'][k1-1][0]}, handing over to its real drums at mix bar {B['start_bar']+k1}")
  if 'dswap' in modes or 'dswap_beat' in modes:
    # the listener 2026-11-02 14:00 ET: default = cut the outgoing beat almost as soon as the incoming melody hits ("like dropping into the
    # next track"): phrase line NEAREST the melody entry (incoming crossfader >= -6 dB). 'dswap_beat' = cut where the incoming beat
    # arrives (real drums or the ib loop once up in the mix).
    if any(c=='beat' for _,c in A['full_map']):raise ValueError('dswap: outgoing is an lx beat-only outro')
    ent=next((mb for mb in range(s,e) if gain_at(B,mb)>=0.5),e)
    if 'dswap_beat' in modes and not B.get('ib'):
      if k1 is None or B['start_bar']+k1>=e:raise ValueError(f'dswap_beat: {B["id"]} beat arrives after the blend; needs ib')
      arr=B['start_bar']+k1;mb=next((x for x in range(arr,e) if (x-s)%4==0),None)
    else:
      ph=[x for x in range(s+4,e) if (x-s)%4==0];mb=min(ph,key=lambda x:(abs(x-ent),x)) if ph else None
    o=opt.get('dswap@')
    if mb is not None and o:mb={'-1':mb-1,'+1':mb+1,'next':mb+4}.get(o,mb)
    if mb is None or not s<mb<e:raise ValueError('dswap: no phrase line inside the blend')
    A['dswap']=dict(bar=mb,xf=float(os.environ.get('DSWAP_XF',1)),at='beat' if 'dswap_beat' in modes else 'melody',entry=ent)
    notes.append(f"drum swap: outgoing {A['id']} drums+bass out over {A['dswap']['xf']:g} bar on the phrase line at mix bar {mb} (incoming {'beat' if 'dswap_beat' in modes else 'melody entry'} bar {ent if 'dswap_beat' not in modes else mb}); melody keeps its gradual tail")
  if B.get('ib') and A.get('dswap'):
    # BASSGAP (the listener 2026-11-02 19:33 ET, AC card: <150 Hz hole 0:23-0:28 between the outgoing cut and the ib bass arriving via the
    # low swap): the incoming bass lane must be fully open by the cut, so the ib loop's bass takes over at/before the outgoing drop.
    import math;c=A['dswap']['bar'];r=lambda a,b,up:[[a+q/4,round((0.5-0.5*math.cos(math.pi*q/(4*(b-a))))if up else(0.5+0.5*math.cos(math.pi*q/(4*(b-a)))),5)] for q in range(int(4*(b-a))+1)]
    B['auto']['low']=r(c-2,c,True)+[p for p in (B['auto'].get('low') or []) if p[0]>=e]  # keep the next blend's lane
    A['auto']['low']=[p for p in (A['auto'].get('low') or []) if p[0]<c-2]+[[c-2,1.0]]+r(c,c+2,False)
    notes.append(f"bass lanes: incoming {B['id']} (ib loop) bass fully in by the cut at mix bar {c}; outgoing low lane out {c}-{c+2} (its drums+bass stem is already cut over {c}-{c+1})")
  t.setdefault('notes',[]);t['notes']=list(t['notes'])+notes;t['bm_fix']=mode
  return notes
def tail_exempt(E,M,i,mb,y_with,src='.'):
  """TAIL exemption for a >6 dB one-bar outgoing drop at mix bar mb: a drums-only cut (A['dswap'] at mb or mb-1, on a phrase line)
  with the beat carried by the incoming deck there. y_with = rendered deck A. The same deck rendered WITHOUT the dswap must not
  show the drop (else it is a full-mix abrupt fade and still blocks)."""
  A,B,t=M['decks'][i],M['decks'][i+1],M['trans'][i];ds=A.get('dswap')
  if not ds or not(ds['bar']<=mb<=ds['bar']+max(1,int(np.ceil(ds['xf'])))):return False
  if (ds['bar']-int(t['start_bar']))%4 and (src_at(A,ds['bar'])[0] or 1)%8:return False
  if not(beat_in(B,mb,src) or (ds.get('at')=='melody' and abs(ds['bar']-ds.get('entry',ds['bar']))<=2)):return False  # beat carried by the incoming, or a deliberate drop into its melody entry
  y0=E.render_deck(dict(A,dswap=None));dry=E.render_deck(dict(A,auto={},dswap=None));d0=A['start_bar'];BS=E.BS
  db=lambda z,k:10*np.log10(np.mean(z[int((k-d0)*BS):int((k-d0+1)*BS)]**2)+1e-12)
  return not((db(y0,mb)-db(dry,mb))-(db(y0,mb-1)-db(dry,mb-1))<-6 and db(y0,mb)-db(y0,mb-1)<-6)
if __name__=='__main__':
  import sys
  for f in sys.argv[1:]:
    for r in bm1(json.load(open(f))):print(f,r)
