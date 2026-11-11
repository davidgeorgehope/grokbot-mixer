"""The mix engine (crossfader only, the listener 2026-10-28): two decks, ONE crossfader x(t) 0->1 per blend,
deck gains derived only from x (equal-power), channel faders at unity, no stems/EQ/ducking in playback.
Vocal clashes avoided by choosing mix points from full-track analysis; else loop a clean instrumental
phrase (seams overlap-added at bar boundaries).
Blend length: XBARS (default 32) per blend, falling back to 16 (the minimum) only when no clean 32-bar window exists.
Bass handoff (BASS_SWAP_BARS, default 2; 0 = off): the only EQ move, tied to the crossfader. When x passes SWAP_POS
(default 0.35, Raveform median ~0.36) the outgoing deck's low band (<150 Hz) ramps 1->0 while the incoming one ramps
0->1 (raised cosine, monotonic), so one bassline plays at a time.
Phrase-snapped bass swap (SWAP_PHRASE, default on since Mix 05; 0 = older mixes): on beat-on-beat blends (both decks drum >= half the blend) the
handoff starts on the 4-bar phrase boundary (crossfader x 0.2-0.65) where the two basslines double and drop out least.
Raveform (38 reliable DnB blends): pros swap lows in <=2 bars half the time, median ~21% into the blend.
Separate high swap (HIGH_SWAP, default on since Mix 05; 0 = older mixes): on beat-on-beat blends a second EQ lane on the
>2 kHz band (engine HIGH_XO) hands the hats/air over in the 2 bars starting on a 4-bar phrase boundary HIGH_OFS bars (default +4) from the
bass swap: incoming highs held back until then, outgoing highs out after, so the two top ends never stack (Raveform: highs
cross >=4 bars from the lows in 64% of pro blends). Pros' earlier bass point is SWAP_POS=0.21.
Delay-tail exit (ECHO_OUT, default on since Mix 05; 0 = older mixes): on at most ECHO_SHARE (default 10%, Raveform: 5-15% of pro DnB exits) of blends, spaced
>=4 blends apart, the outgoing deck's final bar feeds a 1-beat feedback delay (-6 dB per repeat, 300-6000 Hz) whose wet tail plays only
after its crossfader end (engine.echo_tail): first where the outgoing track runs out of music soonest (no runway), else for variety.
Window choice uses cached Demucs activity maps (bar.voc, bar.bass) for analysis only."""
import numpy as np,soundfile as sf,json,sys,os
from engine import track,render_deck,SR,BAR,BEAT,BS
plan=json.load(open(sys.argv[sys.argv.index('--plan')+1]));OUT=sys.argv[sys.argv.index('--out')+1]
X=int(sys.argv[sys.argv.index('--xbars')+1]) if '--xbars' in sys.argv else int(os.environ.get('XBARS',32))
POS=float(os.environ.get('SWAP_POS',0.35))  # bass handoff centre as a fraction of the blend (Raveform median ~0.36)
POS0=POS
ids=[p['id'] for p in plan]
def A_(b):
  t=track(b);al=np.array(t['g']['bar']['all'],float);return t,al,np.percentile(al,75),np.array(t['vact'],bool),t['nb']
def tail0(al,body):
  loud=np.where(al>body-20)[0];return int(loud[-1])+1 if len(loud) else len(al)
LOOPDIP=float(os.environ.get('LOOP_DIP_DB',4))  # the listener 2026-11-01 (Mix 06 28:00 Remedy loop 160-175 had a fill ~7 dB down at 172-175)
def loop_dip(b,p,key='all'):
  """dB by which the quietest bar of 16-bar phrase p sits more than LOOP_DIP_DB under the phrase median (0 = clean, no fill/breakdown).
  A soft preference since 2026-11-01 (listener: no hard 'never' rules): scored with DIPPEN per dB, never a refusal."""
  al=np.array(track(b)['g']['bar'][key],float)[p:p+16]
  return 99.0 if len(al)<16 else max(0.0,float(np.median(al))-LOOPDIP-float(np.min(al)))
def loop_clean(b,p):return loop_dip(b,p)==0
DIPPEN=float(os.environ.get('DIPPEN',12))
def clean_phrases(b):
  t,al,body,v,nb=A_(b);return [p for p in range(0,nb-15,16) if v[p:p+16].sum()<=1 and al[p:p+16].mean()>body-6]
# synthetic beat-only outro ('lx', the listener 2026-11-01 "loop just the beat arrangement"): the outgoing plays its full mix to bar e, fades
# (LX_XF bars, ending at e) to its drums+bass stem, plays LX_PRE beat-only bars, then the blend runs over the same 16-bar beat phrase p.
# Stem source only, switched before the blend starts: inside the blend each deck still has one monotonic crossfader, no ducking.
LX=int(os.environ.get('LX',1));LX_PRE=int(os.environ.get('LX_PRE',8));LX_XF=int(os.environ.get('LX_XF',2));LXPEN=float(os.environ.get('LXPEN',50))
import beatstem
def beat_phrases(b,e,ia):
  """phrase starts p (p<=e-16, up to 64 bars back) with a clean beat loop (beatstem.lx_len: 16 bars, else its clean first 8)"""
  return [p for p in range(e-16,max(ia,16,e-64)-1,-16) if beatstem.lx_len(b,p,LOOPDIP)]
def lx_wa(b,p,X):L=beatstem.lx_len(b,p,LOOPDIP);return [p+((LX_PRE+k)%L) for k in range(X)]
NOVOC=set()  # tracks currently scored as beat-only: no vocal activity
VOCOFF=set()  # tracks without vocal data: the V (vocal clash) term is off for them, recorded in the plan meta
# per-track in/out plan: score every phrase-aligned candidate window by simulating the guardrails
# (V1 vocal clash, L1 double bass, O1 both audible >=8 bars, C2 outgoing not too quiet) under the crossfader.
ANCH={p['id'] for p in plan if p.get('anchor')};NOIN={p['id'] for p in plan if p.get('anchor_in') is False};HEAVY=float(os.environ.get('HEAVY',-6))
OUTMAX={p['id']:p['out_max'] for p in plan if 'out_max' in p}  # opt-in plan cap on a track's out bar (its tail fades below musical level)
SW=float(os.environ.get('BASS_SWAP_BARS',4));SW0=SW  # 4 since 2026-10-31: 2-bar swaps took 6.6-7.8 dB off the outgoing in one bar (abrupt-fade rule)
def F(b):
  g=track(b)['g']['bar'];al=np.array(g['all'],float);lo=np.array(g['low'],float);v=np.array(g.get('voc',[-100]*len(al)),float)
  bs=np.array(g['bass'],float) if 'bass' in g else None
  bact=(bs>np.percentile(bs,90)-10) if bs is not None else (lo-al>HEAVY)
  hi=10*np.log10(np.maximum(10**(al/10)-10**(lo/10),1e-10))  # level above the bass band (what stays audible through the handoff)
  if b in NOVOC:v=np.full(len(al),-100.)
  # no vocal data (protrans prep wrote a constant -100 stand-in; NOVOC beat-only outros): with rv = percentile(v,95) every bar
  # counted as 'vocal' (2026-11-11 RCA: V=20 on every 32-bar window, real overlap unchecked). Now: no V term for that deck (VOCOFF).
  if len(v)!=len(al) or float(np.ptp(v))==0:
    if b not in NOVOC:VOCOFF.add(b)
    return hi,lo,v,float('inf'),bact
  return hi,lo,v,float(np.percentile(v,95)),bact
_ON={}
def onsets(b):  # per-bar onset envelope (cached), used only to predict guardrail R1 (drums fighting)
  if b in _ON:return _ON[b]
  import onsets as _onsetlib;_ON[b]=_onsetlib.ensure(b);return _ON[b]
def rxc(a,b,wa,wb):
  """drum-fight R: median per-bar onset xcorr between the decks, best lag within +-BEAT/8 (unchanged pass criterion, RPEN below 0.25)"""
  return rxc_lags(a,b,wa,wb)['r0']
import halfbeat as _HB
def rxc_lags(a,b,wa,wb,both_drums=False):
  """per-bar onset xcorr between the decks searched over +-BEAT/2 (halfbeat.deck_lags; 2026-11-11 RCA: Shine In sat 158 ms =
  0.46 beat off Dusk To Dawn, outside the old +-BEAT/8 search, and R=0.42 passed). r0 is the unchanged drum-fight R."""
  mask=None
  if both_drums:dA,dB=drums_on(a),drums_on(b);mask=[xa<len(dA) and xb<len(dB) and dA[xa] and dB[xb] for xa,xb in zip(wa,wb)]
  return _HB.deck_lags(onsets(a),onsets(b),wa,wb,mask)
def halfbeat(a,b,wa,wb):
  """render-time half-beat check over the overlap (drum-on-drum bars): fail when the decks line up better half a beat apart"""
  return _HB.blend_check(a,b,list(wa),list(wb))  # drum-phase basis (halfbeat.blend_check); the lag xcorr rides along in the dict
_DR={}
def drums_on(i):  # per source bar: drums within 8 dB of the record's drum body (Mix 02 trait: long drums-together blends)
  if i not in _DR:d=np.array(json.load(open(f'st/{i}.json'))['bar']['drums']);_DR[i]=d>np.percentile(d,75)-8
  return _DR[i]
DRUMPEN=float(os.environ.get('DRUMPEN',0))  # 0 = baseline behaviour
SNAP=int(os.environ.get('SWAP_PHRASE',1))  # default on for Mix 05+ (the listener A/B 2026-10-29 'b was smoother'); 0 reproduces older mixes
def bob(a,b,wa,wb):  # beat-on-beat blend: both decks drum for at least half of it
  dA,dB=drums_on(a),drums_on(b);return sum(xa<len(dA) and xb<len(dB) and dA[xa] and dB[xb] for xa,xb in zip(wa,wb))>=X/2
HSW=int(os.environ.get('HIGH_SWAP',1));HOFS=int(os.environ.get('HIGH_OFS',4))
def high_at(a,b,wa,wb,c,on):
  """high-band swap centre (bars into the blend): a 4-bar boundary at least 4 bars from the bass swap, inside x 0.1-0.9, where
  neither top end is thin (outgoing above-bass level in the 2 bars before, incoming in the 2 bars after, within 6 dB of its body;
  a thin side made a -3.3 dB dip on paper), then nearest c+HOFS (else c-HOFS)"""
  if not(HSW and on):return None
  hA,hB=F(a)[0],F(b)[0];bodA,bodB=np.percentile(hA,75),np.percentile(hB,75)
  def thin(h):return sum(hA[wa[k]]<bodA-6 for k in range(max(0,h-2),h))+sum(hB[wb[k]]<bodB-6 for k in range(h,min(X,h+2)))
  # X1 reads the swap *centre* (ramp starts at high_bar+1 over 2 bars, centre = h+2). Checking x at h
  # allowed FADE=long to place a late high swap at x=0.90 (2026-11-11 Mix 08 long test). Omit the swap if none fit.
  ok=[h for h in range(4,X,4) if abs(h-c)>=4 and 0.1<=_xpos((h+2)/X)<=0.9]  # crossfader x at the centre, not blend fraction
  return min(ok,key=lambda h:(thin(h),abs(h-(c+HOFS)),abs(h-(c-HOFS)))) if ok else None
def swap_at(a,b,wa,wb):
  """bass handoff centre in bars into the blend: POS*X, or with SWAP_PHRASE the best 4-bar phrase boundary on beat-on-beat blends"""
  # FADE=long already places the handoff in x-space (LONG_SWAP=exit: fade_long.swap_pos, centre at the
  # exit start, x=xp2=0.5). The tail planner's 4-bar phrase snap assumes x≈u, and with a 4-bar swap
  # plus a vocal hold or a short plateau it can have zero candidates (Mix 08 long1b, ValueError).
  if FADE=='long':return POS*X
  if not(SNAP and SW>0):return POS*X
  bA,bB=F(a)[4],F(b)[4]
  lA,lB=F(a)[1],F(b)[1];bodA,bodB=np.percentile(lA,75),np.percentile(lB,75)
  def thin(c):return sum(lA[wa[k]]<bodA-6 for k in range(max(0,c-2),c))+sum(lB[wb[k]]<bodB-6 for k in range(c,min(X,c+2)))  # low end not yet/no longer at body level next to the swap: dip (Mix 03 v2 36:47, -3.2 dB)
  QDB=float(os.environ.get('SWAP_QUIET_DB',999))  # opt-in (e.g. 15): on, held-out 30.09 -> 29.50 (2026-11-11; Pola & Bryson swap on Closer to Home's bar 32 bass fill is what the pro did), so off by default
  def quiet(c,centred=False):  # incoming bars inside the handoff whose low band sits >= SWAP_QUIET_DB under its body (2026-11-11 RCA: the swap landed on Dusk To Dawn bar 44, -35 dB: an 18 dB hole)
    lo_=c-SW/2 if centred else c;return sum(wb[k]<len(lB) and lB[wb[k]]<bodB-QDB for k in range(max(0,int(np.floor(lo_))),min(X,int(np.ceil(lo_+SW))+1)))
  if not bob(a,b,wa,wb):
    # SWAP_THIN (2026-11-01, Mix 05 v2 v4 24:46 2s3M>nT25 -6.2 dB energy drop): non beat-on-beat blends used POS*X blindly, so the
    # outgoing bass went at bar ~6 while nT25's intro had no bass yet (-29 vs -17 dB) = a hole. Hand the bass over where the incoming
    # actually has low end; if it never does inside the blend, keep it on the outgoing as late as possible (it fades with the fader).
    if not int(os.environ.get('SWAP_THIN',1)):return POS*X
    _hl=float(os.environ.get('BASS_LEAD',1))/2;cs=[c for c in range(2,int(X-SW)+1) if 0.2<=_xpos((c+SW/2-_hl)/X) and _xpos((c+SW/2+_hl)/X)<=0.65]  # v6r4: off-phrase picks render with lead (BLEAD/2 each side), so BOTH decks' swap centres must sit in X1's window (r4 incoming at x=0.68)  # X1 window; off-phrase picks are treated like POS swaps (not phrase-snapped)  # X1: swap centred at crossfader x 0.2-0.65
    def hole(c):return sum(lB[wb[k]]<bodB-6 and lA[wa[k]]>=bodA-6 for k in range(int(c+SW/2),X))  # bars with no bass after the handoff that the outgoing still had
    if (a=='j9AuFRpLk7U' and b=='cxS6yd0UAxw') or not cs:return POS*X  # gold blend untouched
    if hole(POS*X)<int(os.environ.get('SWAP_HOLE_BARS',3)) and (quiet(POS*X,True)==0 or all(quiet(c) for c in cs)):return POS*X  # only real holes / quiet bars
    best=min(cs,key=lambda c:(quiet(c),hole(c),thin(c),abs(c-POS*X)))
    return best if (quiet(best),hole(best))<(quiet(POS*X,True),hole(POS*X)) else POS*X
  def bad(c):return 2*thin(c)+3*quiet(c)+sum(2*(c<=k<c+SW and bA[xa] and bB[xb])+((k<c and not bA[xa]) or (k>=c and not bB[xb])) for k,(xa,xb) in enumerate(zip(wa,wb)))
  return min((c for c in range(4,X,4) if 0.2<=_xpos((c+SW/2)/X)<=0.65),key=lambda c:(bad(c),abs(c-POS*X)))
FADE=os.environ.get('FADE','tail');FADE0=FADE;FDB=float(os.environ.get('FADE_DB',22))  # 'tail' (default 2026-10-31): blend of the linear position and a -FDB*u^1.5 dB outgoing tail, weighted by u; 'lin' = old linear position (outgoing gone ~10 bars after the swap, -7..-11 dB/bar in Mix 05)
# FADE=long (2026-11-11 long-blend RCA): early-in plateau + decisive outgoing exit on a phrase (fade_long.py). Same single crossfader.
import fade_long as _FL
LG=dict(rise=float(os.environ.get('LONG_RISE',2)),xp=float(os.environ.get('LONG_XP',0.35)),xp2=float(os.environ.get('LONG_XP2',0.5)),
        exit_=float(os.environ.get('LONG_EXIT',8)),solo=float(os.environ.get('LONG_SOLO',0)))
LG0=dict(LG);LGST=int(os.environ.get('LONG_SOLO_STRUCT',0))  # 1: exit ends where the outgoing's own energy drops (fade_long.struct_solo), else LONG_SOLO
LGSW=os.environ.get('LONG_SWAP','')  # 'exit': under FADE=long the bass swap centres on the exit start (fade_long.swap_pos), opt-in
def _xpos(u):  # shared by score() and the render. Pure -30*u^1.5 tail failed X1 (incoming +4.5 dB/beat early) and C2 (outgoing -10.6 dB at mid-blend) on the Mix 06 render;
  # (u, u**1.5, D24 still gave X1 3.1 dB/beat on 16-bar blends in render c)
  if FADE=='long':return _FL.xlong(u,X,**LG)
  if FADE=='lin' or u>=1:return u
  w=u**1.4;return float((1-w)*u+w*2/np.pi*np.arccos(10**(-FDB*u**1.7/20)))  # tuned at guardrail resolution (1/16 bar): X=16 incoming <=2.9 dB/beat, outgoing <=2.9 dB/bar, -4.2 dB mid-blend
PIN={p['id']:p for p in plan if 'fade' in p or 'swap_bars' in p or 'swap_pos' in p}  # per-outgoing overrides: a pinned blend keeps its fader / bass swap / swap centre
def _ctx(a,wa=None,b=None,wb=None):
  global FADE,SW,POS;q=PIN.get(a,{}) if a else {};FADE=q.get('fade',FADE0);SW=float(q.get('swap_bars',SW0));POS=float(q.get('swap_pos',POS0))
  # FADE=long + a 2-bar bass handoff stacked on the exit took 6.4 dB off Ember in one bar (Mix 08 long test).
  # 4-bar swaps have been the default since 2026-10-31 for this reason; PIN can still force 2.
  if FADE=='long' and 'swap_bars' not in q and SW<4:SW=4.0
  LG['solo']=LG0['solo'];LG['hold']=0.0;LG['exit_']=LG0['exit_']
  if a and wa is not None and FADE=='long' and LGST:
    LG['solo']=_FL.struct_solo(np.array(track(a)['g']['bar']['all'],float),list(wa),X,**LG0)
    if b and wb is not None:
      g=track(b)['g']['bar']
      LG['solo']=_FL.cap_solo_incoming(np.array(g['all'],float),np.array(g.get('low',g['all']),float),list(wb),X,**{**LG0,'solo':LG['solo']})
  if a and wa is not None and b and wb is not None and FADE=='long':
    *_u,vA,rvA,_ba=F(a);*_u,vB,rvB,_bb=F(b)
    LG['hold']=float(_FL.vocal_hold(vA,rvA,list(wa),vB,rvB,list(wb),X))
    # After a delayed exit to cover a thin incoming, keep the outgoing under 0.3 before the
    # incoming starts singing (Mix 08 long1c V1 at 3:06 / 43:36 / 59:48) without uncovering
    # that thin stretch (long1e trans 18: raising solo re-opened the 1901 bass gap). If a late
    # vocal still clashes at the cap, lengthen the exit instead of ending it earlier.
    cap=LG['solo']
    LG['solo'],ex=_FL.vocal_exit_params(vB,rvB,list(wb),X,**{**LG0,'solo':LG['solo'],'hold':LG['hold'],'cap_solo':cap})
    LG['exit_']=ex
  if a and FADE=='long' and LGSW=='exit' and 'swap_pos' not in q:POS=_FL.swap_pos(X,**LG)
def score(a,b,wa,wb,refA):
  _ctx(a,wa,b,wb)
  try:return _score(a,b,wa,wb,refA)
  finally:_ctx(None)
def _score(a,b,wa,wb,refA):
  c=swap_at(a,b,wa,wb);ce=c+(SW/2 if c!=POS*X else 0);h=high_at(a,b,wa,wb,c,HSW and bob(a,b,wa,wb))
  alA,loA,vA,rvA,bA=F(a);alB,loB,vB,rvB,bB=F(b);V=L=C=both=G=SG=0
  dA,dB=drums_on(a),drums_on(b);DT=run=0
  for xa,xb in zip(wa,wb):run=run+1 if xa<len(dA) and xb<len(dB) and dA[xa] and dB[xb] else 0;DT=max(DT,run)  # longest straight drums-together run
  for k,(xa,xb) in enumerate(zip(wa,wb)):
    x=_xpos((k+0.5)/X);ga,gb=np.cos(x*np.pi/2),np.sin(x*np.pi/2);da,dbb=20*np.log10(ga+1e-9),20*np.log10(gb+1e-9)
    LA,LB=alA[xa]+da,alB[xb]+dbb
    if LA>refA-12 and LB>refA-12:both+=1
    if k<X/2 and LA<refA-10:C+=1
    if vA[xa]>rvA-12 and ga>0.3 and vB[xb]>rvB-12 and gb>0.3:V+=1
    if SW>0:  # with the bass handoff only the swap bars can double up; elsewhere the bassline must not drop out
      if abs(k+0.5-ce)<SW/2+0.5:
        if bA[xa] and bB[xb]:L+=1
      elif (k<c and not bA[xa]) or (k>=c and not bB[xb]):
        G+=1;SG+=int(c<=k<c+4)  # incoming has no bass right after the handoff: audible energy drop
    elif loA[xa]-alA[xa]>HEAVY and loB[xb]-alB[xb]>HEAVY and min(loA[xa]+da,loB[xb]+dbb)>refA-12:L+=1
  return dict(c=c,h=h,V=V,L=L,C=C,both=both,G=G,SG=SG,pen=float(os.environ.get('SGPEN',15))*SG+float(os.environ.get('VPEN',100))*V+4*L+float(os.environ.get('BOTHPEN',15))*max(0,10-both)+3*C+float(os.environ.get('GAPPEN',0.5))*G+DRUMPEN*max(0,16-DT),DT=DT)
CUEW=float(os.environ.get('CUEW',0))  # pro cue-point term (cue.py, Raveform-trained); 0 = off until the listener hears the A/B
if CUEW>0:
  import cue;CM=cue.load();_CX={}
  def cue_pen(a,ea):  # 0 when the outgoing record ends where the model's pros end it, 1 at its least pro-like spot (mix-in model lost to a plain 8%-position rule, so it isn't used)
    if a not in _CX:g=track(a)['g']['bar'];_CX[a]=cue.track_feats(g['all'],g['low'],g['hat'])
    return 1-cue.pctl(CM,'out',_CX[a],ea)
import sections;STRUCT=int(os.environ.get('STRUCT',1));STRUCTW=float(os.environ.get('STRUCTW',300));STRK=set()
XT={};inn={ids[0]:0};outs={};loops={};notes={};info_={}
def pair_cands(i,ia0):
  """all scored windows for blend i given where track i starts (ia0); sorted best first"""
  global X
  a,b=ids[i],ids[i+1];ta,ala,ba,va,na=A_(a);tb,alb,bb,vb,nb=A_(b)
  ia=ia0[1]+16 if isinstance(ia0,tuple) else ia0;res=[]
  e_max=min(tail0(ala,ba),na,OUTMAX.get(a,na));e_max-=e_max%16
  minlen=160 if a in ANCH else 96-X  # anchors: >=160 bars (~220 s) of their own music, blend included
  emin=max(ia+minlen,ia+int((e_max-ia)*0.5));emin+=(-emin)%16;emin=min(emin,e_max)
  XMAX=X
  for X in sorted({XMAX,16},reverse=True):  # 32-bar blend preferred; 16 is the minimum when no clean 32-bar window exists
    cands=[]
    for e in range(e_max,emin-1,-16):
      for ib in range(0,min(81,nb-3*X),16):cands.append(('n',e,ib))
    if STRUCT:  # outro-over-intro (default 2026-10-31): outgoing plays its whole outro to its music end; incoming starts so its drop lands there
      SA,SB=sections.get(a),sections.get(b);es=min(e_max,(SA['music_end']//8)*8);ibs=SB['drop1']-X
      if ibs>=0 and es-X>=ia+16 and ibs+X<nb:cands.append(('n',es,ibs));STRK.add(('n',a,b,es,ibs,X))
      if SB['drop1']-16>=16 and es-X>=ia+16:cands.append(('lb',es,SB['drop1']-16));STRK.add(('lb',a,b,es,SB['drop1']-16,X))  # gold (the listener 5/5, Mix 05 55:10 -> Just Hold On): incoming loops its last intro phrase, drop lands as the outgoing's music ends
    eml=max(ia+16,emin-X) if a in ANCH else emin  # anchors: looped bars count toward their >=160 bars of airtime
    for e in range(e_max,eml-1,-16):  # outgoing plays to e, then repeats the 16-bar phrase just before e (p=e-16) under the blend; jumping further back sounds wrong (the listener 2026-10-28)
      for p in [e-16] if e-16>=max(ia,16) else []:  # a fill/level drop inside the loop is penalised (DIPPEN), not refused
        if X>16 and not int(os.environ.get('LOOP32',1)):continue  # 32-bar outgoing repeat: allowed again 2026-10-31 12:30 (listener: loops are fine), capped by the variety rule
        for ib in range(0,min(81,nb-3*X),16):cands.append(('la',(e,p),ib))
    for e in range(e_max,emin-1,-16):
      for q in range(16,min(97,nb-4*X),16):cands.append(('lb',e,q))  # incoming plays phrase q first, continues q+16
    if LX and not (X>16 and not int(os.environ.get('LOOP32',1))):
      for e in range(e_max,eml-1,-16):
        for p in beat_phrases(a,e,ia)[:1]:  # nearest clean beat phrase before the out point
          for ib in range(0,min(81,nb-3*X),16):cands.append(('lx',(e,p),ib))
    cpa=[p for p in clean_phrases(a) if p>=max(ia,16)];cpb=[q for q in clean_phrases(b) if 16<=q<min(97,nb-4*X)]
    for e in range(e_max,emin-1,-16):  # both decks loop a clean instrumental phrase (only when neither has vocal-free runway)
      for p in [p for p in cpa if p==e-16]:
        for q in cpb:cands.append(('ab',(e,p),q))
    if b in ANCH and b not in NOIN:  # incoming anchor: start early enough to keep >=160 bars of its own music
      bmx=min(tail0(alb,bb),nb)-160;cands=[c for c in cands if c[2]<=max(0,bmx)] or cands
    LW=float(os.environ.get('LW',0.4))
    for kind,e,ib in cands:
      if kind=='lx':e,p=e;wa=lx_wa(a,p,X);ea=e;NOVOC.add(a)
      elif kind in('la','ab'):e,p=e;wa=[p+(k%16) for k in range(X)];ea=e
      else:wa=range(e-X,e);ea=e
      q=ib;wb=[q+(k%16) for k in range(X)] if kind in('lb','ab') else range(q,q+X)
      ha=F(a)[0];ref=float(np.median(ha[max(ia,ea-X-8):ea-X])) if kind not in('la','ab','lx') else float(np.median(ha[e-8:e]))
      r=score(a,b,list(wa),list(wb),ref);NOVOC.discard(a)
      step=(max(abs(np.median(ala[e-4:e])-np.median(ala[p:p+4])),abs(np.mean(ala[e-2:e])-np.mean(ala[p:p+2]))) if kind in('la','ab') else 0)+(abs(alb[q]-alb[q+15]) if kind in('lb','ab') else 0)  # level jump at the loop seam
      if kind=='lx':dra=np.array(track(a)['g']['bar']['drums'],float);step+=abs(np.mean(dra[e-2:e])-np.mean(dra[p:p+2]))  # beat seam e-1 -> p
      r['pen']+=float(os.environ.get('SEAMPEN',8))*max(0,step-2);r['R']=round(rxc(a,b,list(wa),list(wb)),3);r['pen']+=float(os.environ.get('RPEN',300))*max(0,0.25-r['R']);r['HB']=halfbeat(a,b,list(wa),list(wb))
      skipped=(e_max-ea)+ib  # bars of music not heard
      if kind in('la','ab'):r['pen']+=DIPPEN*loop_dip(a,p)
      if kind=='ab':r['pen']+=DIPPEN*loop_dip(b,q)
      seq=[(e-1 if kind in('la','ab') else wa[0]-1)]+list(wa)[:X//2+2];seq=[k for k in seq if 0<=k<len(ha)]
      jump=max([abs(ha[seq[k]]-ha[seq[k-1]]) for k in range(1,len(seq))]+[0])  # outgoing level jumps across entry / first half (guardrail N1, C1)
      r['pen']+=float(os.environ.get('SEAMPEN',8))*max(0,jump-3)
      hole=int(any(alb[k]<float(os.environ.get('HOLE_DB',-31)) for k in range(q+X,min(q+X+96,tail0(alb,bb)))))  # incoming would play a near-silent bar of its own (guardrail E2)
      r['pen']+=float(os.environ.get('HOLEPEN',0))*hole
      if step>float(os.environ.get('SEAMMAX',2)) or r['both']<int(os.environ.get('BOTHMIN',11)):r['pen']+=float(os.environ.get('HARDPEN',60))  # hard limits: guardrail N1 (3 dB step) and O1 (>=8 bars)
      if CUEW>0:r['cue']=round(cue_pen(a,ea),3);r['pen']+=CUEW*r['cue']
      sc=(r['pen']+(float(os.environ.get('SHORTPEN',6)) if X<XMAX else 0)+LW*skipped+float(os.environ.get('LOOPPEN',40))*{'n':0,'la':1,'lb':1,'ab':2,'lx':0}[kind]+(LXPEN if kind=='lx' else 0),-ea,str(ib))
      if (kind,a,b,ea,ib,X) in STRK:sc=(sc[0]-STRUCTW-(float(os.environ.get('LOOPPEN',40)) if kind=='lb' else 0),)+sc[1:]  # blend length chosen per pair from structure + fit (the listener 2026-10-31)
      res.append((sc,kind,(e,p) if kind in('la','ab','lx') else e,ib,r,X))
  X=XMAX;res.sort(key=lambda t:t[0]);return res
def win_key(c):return [c[1],*(c[2] if isinstance(c[2],tuple) else (c[2],None)),c[3],c[5]]  # [kind, out bar, loop phrase, in bar, blend bars]
def nxt_inn(c):return ("loopB",c[3]) if c[1] in("lb","ab") else c[3]
LOOK=int(os.environ.get("LOOKAHEAD",8))
KIND={};LXD=set()
for i in range(len(ids)-1):
  a,b=ids[i],ids[i+1];cs=pair_cands(i,inn[a])
  if os.environ.get("DUMP_CANDS"):json.dump([dict(win=win_key(c),cost=float(c[0][0]),pen=float(c[4]['pen'])) for c in cs],open(os.environ["DUMP_CANDS"],'w'));sys.exit()  # blend_bench.py: all scored windows of the first pair
  if os.environ.get("DBG_PAIR")==f"{a}>{b}":[print("DBG",round(c[0][0],1),c[1],c[2],c[3],c[5],round(c[4]["pen"],1),file=sys.stderr) for c in cs[:8]]
  W=plan[i].get('out_win')  # opt-in: the window plan_search.py chose for this blend (renders exactly what was planned)
  if W:
    best=next((c for c in cs if win_key(c)==W),None)
    if best is None:sys.exit(f'plan window {W} for {a}>{b} is no longer allowed : re-run plan_search.py')
  elif i+1<len(ids)-1 and LOOK>1:best=min(cs[:LOOK],key=lambda c:c[0][0]+pair_cands(i+1,nxt_inn(c))[0][0][0])  # 1-step lookahead: do not starve the next blend
  else:best=cs[0]
  _,kind,e,ib,r,xt=best;XT[(a,b)]=xt;n=[]
  if kind=='ab':e,p=e;loops[a]=p;n.append(f'outgoing plays to bar {e}, then repeats its clean phrase {p}-{p+16}; incoming loops its clean phrase {ib}-{ib+16} through the blend, then continues from bar {ib+16}');ib=('loopB',ib)
  elif kind=='lx':e,p=e;loops[a]=p;LXD.add(a);n.append(f'outgoing plays to bar {e}, fades over {LX_XF} bars to its drums+bass stem, then loops that beat-only phrase {p}-{p+beatstem.lx_len(a,p,LOOPDIP)} ({LX_PRE} bars before the blend, then under it): synthetic outro, real one too short or holds a fill')
  elif kind=='la':e,p=e;loops[a]=p;n.append(f'outgoing plays to bar {e}, then repeats its 16-bar phrase {p}-{p+16} under the blend (cleaner window than its real outro)')
  elif kind=='lb':n.append(f'incoming plays its 16-bar phrase {ib}-{ib+16} through the blend, then continues from bar {ib+16}');ib=('loopB',ib)
  else:n.append(f'mix points from full-track analysis: outgoing out at bar {e}, incoming in at bar {ib}')
  outs[a]=e;inn[b]=ib;KIND[(a,b)]=kind;notes[(a,b)]=(n,r['V']);info_[(a,b)]=r
  print('choose',a,b,kind,xt,r,file=sys.stderr)
outs[ids[-1]]=tail0(*A_(ids[-1])[1:3])
# build deck maps (src bar list) ; deck plays inn..out, outgoing loop appended for X bars
decks=[];start=0
for i,b in enumerate(ids):
  ib=inn[b]
  xi=XT.get((ids[i-1],b),X) if i else X;xo=XT.get((b,ids[i+1]),X) if i<len(ids)-1 else 0
  if isinstance(ib,tuple):m=[ib[1]+(k%16) for k in range(xi)];first=ib[1]+16;m+=list(range(first,outs[b]))
  else:m=list(range(ib,outs[b]))
  fm=[[s,'mix'] for s in m]
  if b in loops and i<len(ids)-1:
    if b in LXD:L=beatstem.lx_len(b,loops[b],LOOPDIP);fm+=[[loops[b]+(k%L),'beat'] for k in range(LX_PRE+xo)]
    else:fm+=[[loops[b]+(k%16),'mix'] for k in range(xo)]
  decks.append(dict(id=b,start_bar=start,full_map=fm));start=start+len(fm)-xo
  if b in LXD:decks[-1]['lx_xf']=LX_XF
import os;sys.path.insert(0,'../src/tests');os.environ.setdefault('MIX_SRC','.');import checks as _C;KEYS=_C.keys()
trans=[]
for i in range(len(ids)-1):
  A,B=decks[i],decks[i+1];X=XT[(A['id'],B['id'])];s=B['start_bar'];e=s+X
  wa_=[A['full_map'][int(s-A['start_bar'])+k][0] for k in range(X) if 0<=int(s-A['start_bar'])+k<len(A['full_map'])]
  wb_=[B['full_map'][int(s-B['start_bar'])+k][0] for k in range(X) if 0<=int(s-B['start_bar'])+k<len(B['full_map'])]
  _ctx(A['id'],wa_,B['id'],wb_)
  xs=[[s+k/4,round(_xpos(k/(4*X)) if k<4*X else 1.0,5)] for k in range(4*X+1)]  # crossfader position per beat, 0->1 (single equal-power control)
  n,cl=notes[(A['id'],B['id'])]
  trans.append(dict(swap_w=SW,fade=FADE,tech=f'{X}-bar crossfader blend (equal-power, single control)'+(f' + {SW:g}-bar bass handoff' if SW>0 else ''),a=A['id'],b=B['id'],start_bar=s,swap_bar=s+int(round(info_[(A['id'],B['id'])]['c'])),high_bar=None if info_[(A['id'],B['id'])]['h'] is None else s+info_[(A['id'],B['id'])]['h'],swap_ofs=float(SW/2 if (SNAP and SW>0 and info_[(A['id'],B['id'])]['c']!=POS*X) else 0),swap_phrase=bool(SNAP and info_[(A['id'],B['id'])]['c']!=POS*X and info_[(A['id'],B['id'])]['c']%4==0),end_bar=e,xfader=xs,vocal_clash_bars=cl,halfbeat=info_[(A['id'],B['id'])].get('HB'),keys=f"{KEYS.get(A['id'])}->{KEYS.get(B['id'])}",key_ok=bool(_C.camelot_ok(KEYS.get(A['id']),KEYS.get(B['id']))),pitch_shift_semitones=0,bass_swap=[s+round(POS*X)-SW/2,s+round(POS*X)+SW/2] if SW>0 else None,notes=n or ['vocal-free mix points chosen from full-track analysis']))
HBG=int(os.environ.get('HALFBEAT_GATE',1))  # 2026-11-11 RCA: a blend whose decks align better half a beat apart is a train-wreck the +-BEAT/8 guards can't see
_hbf=[t for t in trans if (t.get('halfbeat') or {}).get('fail')]
for t in _hbf:print(f"HALFBEAT FAIL {t['a']}>{t['b']}: decks align better half a beat apart (r0={t['halfbeat']['r0']} rh={t['halfbeat']['rh']} lag={t['halfbeat']['lag_ms']} ms over {t['halfbeat']['bars']} drum bars); re-grid with halfbeat.py --apply",file=sys.stderr)
if _hbf and HBG and '--dry' not in sys.argv:sys.exit(3)
EO=int(os.environ.get('ECHO_OUT',1));ESH=float(os.environ.get('ECHO_SHARE',0.1))  # echo default on for Mix 05+ (the listener A/B 2026-10-29 'that's nice'); 0 reproduces older mixes
EOUT=dict(bars=1,delay_beats=float(os.environ.get('ECHO_BEATS',1)),fb=0.5,wet_db=float(os.environ.get('ECHO_WET',-6)),lo=300.0,hi=6000.0,tail_bars=4)
def echo_pick():
  """blends that get a delay-tail exit: outgoing ends on its own music (no loop), its last bar has body above the bass (else the
  echo is inaudible), incoming has no vocal in the 2 bars after the blend (the tail is -30 dB a bar in); plan 'echo_out' true/false forces/forbids.
  Shortest runway (bars of loud music the outgoing still had) first, at most ESH of blends, >=4 blends apart."""
  if not EO:return set()
  c=[]
  for i,t in enumerate(trans):
    a,b=t['a'],t['b'];f=plan[i].get('echo_out')
    if f is False or KIND[(a,b)]!='n':continue
    _,al,body,_,_=A_(a);ha=F(a)[0];e=outs[a];X_=int(t['end_bar']-t['start_bar']);vb=track(b)['vact']
    if not f and (ha[e-1]<np.percentile(ha,75)-6 or any(vb[s] for s,_ in decks[i+1]['full_map'][X_:X_+2] if s<len(vb))):continue
    c.append((not f,tail0(al,body)-e,i))
  got=set()
  for _,_,i in sorted(c):
    if len(got)<min(int(os.environ.get('ECHO_MAX',2)),max(1,round(ESH*len(trans)))) and all(abs(i-j)>=4 for j in got):got.add(i)
  return got
EOS=echo_pick()
for i in EOS:trans[i]['echo_out']=True;trans[i]['tech']+=' + 1-bar delay-tail exit'
_ctx(None)
BLEAD=float(os.environ.get('BASS_LEAD',1));LEADOFF=set(x for x in os.environ.get('BASS_LEAD_OFF','').split(',') if x)  # per-pair opt-out (blend_loop picks)
def gA(x):return float(np.cos(x*np.pi/2))
def gB(x):return float(np.sin(x*np.pi/2))
for i,d in enumerate(decks):
  g=[]
  if i>0:g+=[[p[0],gB(p[1])] for p in trans[i-1]['xfader']]
  if i<len(decks)-1:g+=[[p[0],gA(p[1])] for p in trans[i]['xfader']]
  d['auto']={'gain':g}
  if SW>0:
    lo=[]
    def ramp(c,up,w=SW):
      return [[c-w/2+w*j/16,round(float((1-np.cos(np.pi*j/16))/2 if up else (1+np.cos(np.pi*j/16))/2),5)] for j in range(17)]
    def at(t):return t['swap_bar']+t.get('swap_ofs',t['swap_w']/2 if t['swap_phrase'] else 0)  # 2026-11-01 v6r3: any non-POS pick (phrase OR SWAP_THIN) is a swap START, as score()/hole() assume (ce=c+SW/2); off-phrase picks were centred 2 bars early -> 24:48/40:38 holes  # phrase-snapped swaps start ON the boundary (incoming bass lands on the 1, not a bar early)
    # BASS_LEAD (2026-11-01, Mix 05 v2 i18 L1 x3): the two lows used to ramp on the SAME raised cosine, so mid-swap both sat at
    # -6 dB ('both decks carry full bass'). Outgoing low now leads by LEAD bars (same 4-bar shape, still monotonic): they cross ~-10 dB.
    def lead(t):
      if t['a'] in PIN or f"{t['a']}>{t['b']}" in LEADOFF:return (0.0,0.0)
      # FADE=long: outgoing lows leave first, even when the swap is at POS (exit start), so the
      # mid-cross is not two equal plateau faders (Mix 08 long1e L1). Phrase-snapped unchanged.
      return _FL.bass_lead(BLEAD,phrase=bool(t.get('swap_phrase')),fade=t.get('fade',FADE))
    if i>0:lo+=ramp(at(trans[i-1])+lead(trans[i-1])[1],True,trans[i-1]['swap_w'])
    if i<len(decks)-1:lo+=ramp(at(trans[i])-lead(trans[i])[0],False,trans[i]['swap_w'])
    d['auto']['low']=lo
    hi=([] if i==0 or trans[i-1]['high_bar'] is None else ramp(trans[i-1]['high_bar']+1,True,2))+([] if i==len(decks)-1 or trans[i]['high_bar'] is None else ramp(trans[i]['high_bar']+1,False,2))
    if hi:d['auto']['high']=hi
  if i in EOS:d['echo_out']=dict(EOUT)
  d['end_bar']=d['start_bar']+len(d['full_map']);d['echo']=False;d['label']='';d['map']=d['full_map'][:1]+d['full_map'][-1:];d['acap']=False;d['drop_bar']=None
if SW0>0 or PIN:  # trans['bass_swap'] = the low lanes as rendered (2026-11-11 RCA: it reported POS*X, 213.5-216.5, while the lanes ran 225.5-229.5)
  for t in trans:
    if t['swap_w']>0:
      _c=t['swap_bar']+t.get('swap_ofs',t['swap_w']/2 if t['swap_phrase'] else 0);_l=lead(t)
      t['bass_swap']=[round(_c-_l[0]-t['swap_w']/2,3),round(_c+_l[1]+t['swap_w']/2,3)]
for t in trans:
  t['vocal_data']={t['a']:t['a'] not in VOCOFF,t['b']:t['b'] not in VOCOFF}
  if t['a'] in VOCOFF or t['b'] in VOCOFF:t['notes']=list(t['notes'])+['vocal overlap not checked: no vocal data for '+', '.join(x for x in (t['a'],t['b']) if x in VOCOFF)]
# beats -> melody-only fixes (beatmelody.py, 2026-11-02): plan step 'bm_fix' ('dswap' | 'dswap_beat' | 'ib' | 'ib+dswap'), or env BM_FIX on every BM1 blend
import beatmelody as _BMX
_BMM=dict(decks=decks,trans=trans,bar_sec=BAR);_bmenv=os.environ.get('BM_FIX','')
_bmcases={r['trans'] for r in _BMX.bm1(_BMM)} if _bmenv else set()
for i in range(len(trans)):
  f=plan[i].get('bm_fix') or (_bmenv if i in _bmcases else '')
  if f:
    try:_BMX.apply(_BMM,i,f)
    except ValueError as ex:print('bm_fix skipped',trans[i]['a'],'>',trans[i]['b'],ex,file=sys.stderr)
if '--dry' in sys.argv:
  for t in trans:print(round(t['start_bar']*BAR/60,2),t['a'],'->',t['b'],t['vocal_clash_bars'],t['notes'])
  print('len min',round((decks[-1]['end_bar'])*BAR/60,2))
  json.dump(dict(engine='simple_crossfader',eq_mode=dict(SWAP_PHRASE=SNAP,HIGH_SWAP=HSW,HIGH_OFS=HOFS,SWAP_POS=POS,ECHO_OUT=EO,VARIETY=1,STRUCT=STRUCT,FADE=os.environ.get('FADE','tail'),LOOP32=int(os.environ.get('LOOP32',1))),decks=decks,trans=trans,fx=[],plan=plan,bar_sec=BAR,len_sec=decks[-1]['end_bar']*BAR,dry=True),open(OUT+'_dry_meta.json','w'),default=float);sys.exit()
total=decks[-1]['end_bar'];N=int(total*BS)+SR;M=np.zeros((N,2),np.float32)
import engine
for j,d in enumerate(decks):
  y=render_deck(d);i0=int(round(d['start_bar']*BS));M[i0:i0+len(y)]+=y[:N-i0]
  need={x['id'] for x in decks[j+1:]}
  for k in list(engine._cache):
    if k not in need:engine._cache[k]['st'].clear()
sf.write(OUT+'_raw.wav',M,SR,subtype='FLOAT')
try:
  import cleanup_round_wavs as _CR
  _k,_r=_CR.cleanup(os.path.basename(OUT))
  if _r:print('cleanup_round_wavs kept',sorted(_k),'removed',_r,flush=True)
except Exception as _ex:
  print('cleanup_round_wavs skipped',_ex,file=sys.stderr)
json.dump(dict(engine='simple_crossfader',eq_mode=dict(SWAP_PHRASE=SNAP,HIGH_SWAP=HSW,HIGH_OFS=HOFS,SWAP_POS=POS,ECHO_OUT=EO,VARIETY=1,STRUCT=STRUCT,FADE=os.environ.get('FADE','tail'),LOOP32=int(os.environ.get('LOOP32',1))),decks=decks,trans=trans,fx=[],plan=plan,bar_sec=BAR,len_sec=len(M)/SR),open(OUT+'_meta.json','w'),indent=1,default=float)
print('len min',round(len(M)/SR/60,2))
for t in trans:print(round(t['start_bar']*BAR/60,2),t['a'],'->',t['b'],t['vocal_clash_bars'],t['notes'])
