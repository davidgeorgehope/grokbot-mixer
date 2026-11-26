"""The mix engine (crossfader only, the listener 2026-10-28): two decks, ONE crossfader x(t) 0->1 per blend,
deck gains derived only from x (equal-power), channel faders at unity, no stems/EQ/ducking in playback.
Vocal clashes avoided by choosing mix points from full-track analysis; else loop a clean instrumental
phrase (seams overlap-added at bar boundaries).
Blend length: XBARS (default 32) per blend, falling back to 16 (the lowest) only when no clean 32-bar window exists.
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
  if _longish():return POS*X
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
# FADE=graphcut (2026-11-13, off by default): per-band min-cut handover (fade_graphcut.py). Plans like FADE=long; does not change the default or rules.json.
GC=os.environ.get('GRAPH_CUT','0')=='1' or FADE0=='graphcut'
def _longish():return FADE in ('long','graphcut')
import fade_long as _FL
LG=dict(rise=float(os.environ.get('LONG_RISE',2)),xp=float(os.environ.get('LONG_XP',0.35)),xp2=float(os.environ.get('LONG_XP2',0.5)),
        exit_=float(os.environ.get('LONG_EXIT',8)),solo=float(os.environ.get('LONG_SOLO',0)))
LG0=dict(LG);LGST=int(os.environ.get('LONG_SOLO_STRUCT',0))  # 1: exit ends where the outgoing's own energy drops (fade_long.struct_solo), else LONG_SOLO
LGSW=os.environ.get('LONG_SWAP','')  # 'exit': under FADE=long the bass swap centres on the exit start (fade_long.swap_pos), opt-in
def _xpos(u):  # shared by score() and the render. Pure -30*u^1.5 tail failed X1 (incoming +4.5 dB/beat early) and C2 (outgoing -10.6 dB at mid-blend) on the Mix 06 render;
  # (u, u**1.5, D24 still gave X1 3.1 dB/beat on 16-bar blends in render c)
  if _longish():return _FL.xlong(u,X,**LG)
  if FADE=='lin' or u>=1:return u
  w=u**1.4;return float((1-w)*u+w*2/np.pi*np.arccos(10**(-FDB*u**1.7/20)))  # tuned at guardrail resolution (1/16 bar): X=16 incoming <=2.9 dB/beat, outgoing <=2.9 dB/bar, -4.2 dB mid-blend
PIN={p['id']:p for p in plan if 'fade' in p or 'swap_bars' in p or 'swap_pos' in p}  # per-outgoing overrides: a pinned blend keeps its fader / bass swap / swap centre
def _ctx(a,wa=None,b=None,wb=None):
  global FADE,SW,POS;q=PIN.get(a,{}) if a else {};FADE=q.get('fade',FADE0);SW=float(q.get('swap_bars',SW0));POS=float(q.get('swap_pos',POS0))
  # FADE=long + a 2-bar bass handoff stacked on the exit took 6.4 dB off Ember in one bar (Mix 08 long test).
  # 4-bar swaps have been the default since 2026-10-31 for this reason; PIN can still force 2.
  if _longish() and 'swap_bars' not in q and SW<4:SW=4.0
  # BASS_COVER (2026-11-14 RCA, off by default): if the incoming has no body-level
  # bass in the overlap, skip the mid-window handoff and leave lows on the outgoing
  # (they fade with the fader). Same 6 dB thin line as SWAP_THIN. Does not move the
  # crossfader (not SNAP_IN / TAIL_SHALLOW). A PIN swap_bars still wins. X1 is
  # honoured: no low-lane move means no swap-centre check.
  if a and b and wb is not None and 'swap_bars' not in q and int(os.environ.get('BASS_COVER',0) or 0):
    g=track(b)['g']['bar']
    if _FL.incoming_no_bass(np.array(g.get('low',g['all']),float),list(wb),X,db=float(os.environ.get('BASS_COVER_DB',6) or 6)):
      SW=0.0
  LG['solo']=LG0['solo'];LG['hold']=0.0;LG['exit_']=LG0['exit_']
  if a and wa is not None and _longish() and LGST:
    LG['solo']=_FL.struct_solo(np.array(track(a)['g']['bar']['all'],float),list(wa),X,**LG0)
    if b and wb is not None:
      g=track(b)['g']['bar']
      LG['solo']=_FL.cap_solo_incoming(np.array(g['all'],float),np.array(g.get('low',g['all']),float),list(wb),X,**{**LG0,'solo':LG['solo']})
  if a and wa is not None and b and wb is not None and _longish():
    *_u,vA,rvA,_ba=F(a);*_u,vB,rvB,_bb=F(b)
    LG['hold']=float(_FL.vocal_hold(vA,rvA,list(wa),vB,rvB,list(wb),X))
    # After a delayed exit to cover a thin incoming, keep the outgoing under 0.3 before the
    # incoming starts singing (Mix 08 long1c V1 at 3:06 / 43:36 / 59:48) without uncovering
    # that thin stretch (long1e trans 18: raising solo re-opened the 1901 bass gap). If a late
    # vocal still clashes at the cap, lengthen the exit instead of ending it earlier.
    cap=LG['solo']
    LG['solo'],ex=_FL.vocal_exit_params(vB,rvB,list(wb),X,**{**LG0,'solo':LG['solo'],'hold':LG['hold'],'cap_solo':cap})
    LG['exit_']=ex
  if a and _longish() and LGSW=='exit' and 'swap_pos' not in q:
    POS=_FL.swap_pos(X,**LG)
    if b and wb is not None and SW>0:
      g=track(b)['g']['bar']
      first=_FL.first_incoming_thin_bar(np.array(g['all'],float),np.array(g.get('low',g['all']),float),list(wb),X)
      _ol,_il=_FL.bass_lead(float(os.environ.get('BASS_LEAD',1)),phrase=False,fade='long')
      POS=_FL.swap_before_thin(X,POS,first,swap_w=SW,outgoing_lead=_ol,incoming_lag=_il,xpos=lambda u:_FL.xlong(u,X,**LG))
def score(a,b,wa,wb,refA):
  _ctx(a,wa,b,wb)
  try:return _score(a,b,wa,wb,refA)
  finally:_ctx(None)
def _score(a,b,wa,wb,refA):
  _ee_info=None;_ee_pts=None;_sw_eff=SW
  _is_ee_cand=__import__('early_exit').flag_on() and a not in PIN and b not in PIN and (X>=__import__('early_exit').MIN_BLEND_BARS or (a,b,('n',int(wa[-1])+1,None,int(wb[0]),int(X))) in _EE_PICKER_WINS)
  if _is_ee_cand:
    _na=A_(a)[4]
    import early_exit as _EE
    if _na-(wa[-1]+1)>=_EE.MIN_REM_BARS:
      _sb=sections.get(b);_d1b=_sb.get('drop1');_ib0=wb[0]
      _kd=float(_d1b)-float(_ib0) if (_d1b is not None and 4<=_d1b-_ib0<=X-8) else min(16.0,max(8.0,round(X*0.4)))
      _xs_ee,_ee_info=_EE.build_xfader(0.0,float(X),_kd)
      _ee_pts=([p[0] for p in _xs_ee],[p[1] for p in _xs_ee])
      c=_ee_info['sw_c'];ce=_ee_info['sw_c'];_sw_eff=_ee_info['sw'];h=None
  if _ee_info is None:
    c=swap_at(a,b,wa,wb);ce=c+(SW/2 if c!=POS*X else 0);h=high_at(a,b,wa,wb,c,HSW and bob(a,b,wa,wb))
  alA,loA,vA,rvA,bA=F(a);alB,loB,vB,rvB,bB=F(b);V=L=C=both=G=SG=0
  dA,dB=drums_on(a),drums_on(b);DT=run=0
  for xa,xb in zip(wa,wb):run=run+1 if xa<len(dA) and xb<len(dB) and dA[xa] and dB[xb] else 0;DT=max(DT,run)  # longest straight drums-together run
  for k,(xa,xb) in enumerate(zip(wa,wb)):
    x=float(np.interp(k+0.5,_ee_pts[0],_ee_pts[1])) if _ee_pts is not None else _xpos((k+0.5)/X)
    ga,gb=np.cos(x*np.pi/2),np.sin(x*np.pi/2);da,dbb=20*np.log10(ga+1e-9),20*np.log10(gb+1e-9)
    LA,LB=alA[xa]+da,alB[xb]+dbb
    if LA>refA-12 and LB>refA-12:both+=1
    if k<X/2 and LA<refA-10:C+=1
    if vA[xa]>rvA-12 and ga>0.3 and vB[xb]>rvB-12 and gb>0.3:V+=1
    if _sw_eff>0:  # with the bass handoff only the swap bars can double up; elsewhere the bassline must not drop out
      if abs(k+0.5-ce)<_sw_eff/2+0.5:
        if bA[xa] and bB[xb]:L+=1
      elif (k<c and not bA[xa]) or (k>=c and not bB[xb]):
        G+=1;SG+=int(c<=k<c+4)  # incoming has no bass right after the handoff: audible energy drop
    elif loA[xa]-alA[xa]>HEAVY and loB[xb]-alB[xb]>HEAVY and min(loA[xa]+da,loB[xb]+dbb)>refA-12:L+=1
  _pvd=None;_pld=None;_dpen=DRUMPEN*max(0,16-DT)
  if _ee_info is not None:
    _pvd,_pld=__import__('early_exit').predict_dips(alA,loA,alB,loB,wa,wb,_ee_pts,_ee_info)
  return dict(c=c,h=h,V=V,L=L,C=C,both=both,G=G,SG=SG,early_exit=int(_ee_info is not None),pred_vdip=_pvd,pred_ldip=_pld,drum_pen=round(_dpen,2),pen=float(os.environ.get('SGPEN',15))*SG+float(os.environ.get('VPEN',100))*V+4*L+float(os.environ.get('BOTHPEN',15))*max(0,10-both)+3*C+float(os.environ.get('GAPPEN',0.5))*G+_dpen,DT=DT)
CUEW=float(os.environ.get('CUEW',0))  # pro cue-point term (cue.py, Raveform-trained); 0 = off until the listener hears the A/B
if CUEW>0:
  import cue;CM=cue.load();_CX={}
  def cue_pen(a,ea):  # 0 when the outgoing record ends where the model's pros end it, 1 at its least pro-like spot (mix-in model lost to a plain 8%-position rule, so it isn't used)
    if a not in _CX:g=track(a)['g']['bar'];_CX[a]=cue.track_feats(g['all'],g['low'],g['hat'])
    return 1-cue.pctl(CM,'out',_CX[a],ea)
import sections;STRUCT=int(os.environ.get('STRUCT',1));STRUCTW=float(os.environ.get('STRUCTW',300));STRK=set()
# THIN swap (2026-11-19 RCA Ghetto Blaster -> Seconds To Midnight, research, off by default). A window's swap bars are "thin" when BOTH
# decks' lows sit more than THIN_DB (6 dB, the existing BASS_COVER / DROP_SWAP thin line) under their own body (75th pct of per-bar lows)
# over the middle half of the window. STRUCT_THIN=1: the outro-over-intro bonus is scaled by STRUCT_THIN_W (0) on thin windows.
# THIN_DROPCUE=1: on a thin outro-over-intro window, the bonus moves to the already-scored cue(s) at the same exit whose incoming drop1
# lands inside the overlap (ib <= drop1 <= ib + X - 4), so the outgoing still plays to its music end (its last drop is not cut).
STRUCT_THIN=int(os.environ.get('STRUCT_THIN',0));THIN_DROPCUE=int(os.environ.get('THIN_DROPCUE',0));THIN_DB=float(os.environ.get('THIN_DB',6));STRUCT_THIN_W=float(os.environ.get('STRUCT_THIN_W',0))
THIN_LOG=[]
# SLOWDOWN=1 (2026-11-19 RCA, research, off by default): the outgoing's half-time / no-snare sections (protrans/replica/halftime/slowdown.py).
# On dev, pros start a blend inside an outgoing OUTRO or in-drop slowdown 2.9% of the time vs 12.4% for our default (mix-grouped CI of the
# difference -17.6..-1.9 pts); outgoing BREAKDOWNS are a normal pro blend spot, so they are not penalised. A window whose blend starts inside
# an outgoing outro / in-drop slowdown gets +STRUCTW (cancels the outro-over-intro bonus). If the bonus window is hit, the bonus moves to the
# pro-like alternative: the latest grid exit whose blend starts before the slowdown but not before the last 8 bars of the outgoing's last drop
# (payoff guard), with the incoming cued so its drop1 lands as the blend ends (pre-drop over the last drop's tail).
SLOWDOWN=int(os.environ.get('SLOWDOWN',0));SLOW_LOG=[]
# STRUCTW ablation (2026-11-19, listener: why the 300 bonus?). STRUCTB = size of the outro-over-intro bonus only (default = STRUCTW, so the
# slowdown / payoff guards keep their 300). STRUCT_COND=1: the bonus applies only when the outgoing's blend bars have full drums (median kicks
# >= 0.6 x its drop median and median strong snares >= 0.35 x its drop mean) and the window touches no slowdown section (halftime/slowdown.py).
# OUTRO_QC=1 (2026-11-19, the listener's design call): keep the bonus but scale it by 1 - deduction, the deduction fitted from pro data on the
# outgoing's outro bars (slowdown, drums / snare out, level drop, early fade, thin lows; protrans/replica/halftime/outro_qc.py).
OUTRO_QC=int(os.environ.get('OUTRO_QC',0));QC_LOG=[];_QCC={}
def outro_qc(a,s,e):
  k=(a,s,e)
  if k not in _QCC:
    try:
      sys.path.insert(0,'/workspace/mixes/protrans/replica/halftime');import outro_qc as _OQ
      d,f=_OQ.deduction(a,s,e);_QCC[k]=d;QC_LOG.append(dict(a=a,s=s,e=e,ded=round(d,3),f=f))
    except Exception as ex:print('OUTRO_QC failed',a,ex,file=sys.stderr);_QCC[k]=0.0
  return _QCC[k]
# EXITPOS=1 (2026-11-19, research, off by default): replaces the rigid outro-over-intro bonus with a pro-fitted, structure-based score of
# where a blend works (protrans/replica/halftime/exitpos.py: where A is left vs its last drop / breakdowns / outro, whether B's drop lands
# inside the blend, B entering in a drop or breakdown), leave-one-DJ-out weights per outgoing track, scaled so its spread equals STRUCTW.
# Guards kept as hard +2*STRUCTW: the blend may not start before the last 8 bars of A's last drop (payoff), B may not enter after its first
# drop (cue skip). The SLOWDOWN rule still applies; its bonus-move is off under EXITPOS (there is no bonus to move).
# EXITPOS_GATE=1 (2026-11-19, research, off by default): keep the outro-over-intro window as the safe default. An EXITPOS alternative is used
# only when it exits earlier, A's last drop has played to its end, B's first drop lands inside the blend, and a leave-one-DJ-out logistic
# (halftime/exitpos_gate.py) says the alternative is closer to a good blend than the default.
EXITPOS=int(os.environ.get('EXITPOS',0));EXITPOS_GATE=int(os.environ.get('EXITPOS_GATE',0));EXITPOS_DROP=int(os.environ.get('EXITPOS_DROP',0));EP_LOG=[];EPG_LOG=[]
def exitpos_term(a,b,ea,ib,X,emx=None):
  try:
    sys.path.insert(0,'/workspace/mixes/protrans/replica/halftime');import exitpos as _EP
    SA_,SB_=sections.get(a),sections.get(b);u,scale=_EP.score(a,SA_,SB_,ea,ib,X,me=emx)
    dr=SA_.get('drops') or [];lde=dr[-1][1] if dr else SA_['music_end'];d1=SB_.get('drop1')
    # payoff guard v2 (11-19 12:40): A must play its last drop to its end (or to the latest exit this pair allows) and the blend may
    # overlap at most the last 32 bars of that drop. v1 (start >= lde-8) was infeasible for tracks that end right after their last drop,
    # so it hit every window and stopped guarding.
    lim=min(lde,emx) if emx else lde
    g=2*STRUCTW if (ea<lim or ea-X<lde-32 or (d1 is not None and ib>d1)) else 0.0
    return g-scale*u
  except Exception as ex:
    print('EXITPOS failed',a,b,ex,file=sys.stderr);return 0.0
STRUCTB=float(os.environ.get('STRUCTB',STRUCTW));STRUCT_COND=int(os.environ.get('STRUCT_COND',0));_SCC={}
# STRUCT_MID=1 (2026-11-23, research, off by default): when the outgoing track has a post-drop
# breakdown with at least STRUCT_MID_MIN_HT (24) bars of half-time in a gap of at least
# STRUCT_MID_MIN_GAP (16) (protrans/replica/halftime/struct_mid.py; S.P.Y bars 128-160 is the
# prototype), the outro-over-intro bonus is STRUCT_MID_B (100) instead of STRUCTB, and exits at
# drop-1 end or breakdown end get a competing STRUCT_MID_W (100) bonus. The first loose gate
# (gap>=16 or 8 bars of HT) raised exit error 30.7->55.58 on the 19 fresh pairs (errors; lower
# is better) and was tightened by leave-one-mix-out. Pick time uses track structure only; pro
# labels are never inputs. Not all-or-nothing (STRUCTB=0 also made overall error worse).
STRUCT_MID=int(os.environ.get('STRUCT_MID',0));STRUCT_MID_B=float(os.environ.get('STRUCT_MID_B',100));STRUCT_MID_W=float(os.environ.get('STRUCT_MID_W',100))
_SM=None
if STRUCT_MID:
  sys.path.insert(0,'/workspace/mixes/protrans/replica/halftime')
  import struct_mid as _SM
def struct_full(a,s,e):
  k=(a,s,e)
  if k in _SCC:return _SCC[k]
  ok=True
  try:
    sys.path.insert(0,'/workspace/mixes/protrans/replica/halftime');import slowdown as _SD
    P=_SD.profile(a);dr=sections.get(a).get('drops') or []
    if P and dr:
      K=np.asarray(P['kicks'],float);S=np.asarray(P['snare_strong'],float);db=[i for x,y in dr for i in range(x,min(y,len(K)))]
      w=[i for i in range(max(0,s),min(e,len(K)))]
      if w and db:ok=bool(np.median(K[w])>=0.6*np.median(K[db]) and np.median(S[w])>=0.35*np.mean(S[db]) and not any(x<e and s<y for x,y in P['sections']))
  except Exception as ex:print('STRUCT_COND profile failed',a,ex,file=sys.stderr)
  _SCC[k]=ok;return ok
def slow_secs(a):
  try:
    sys.path.insert(0,'/workspace/mixes/protrans/replica/halftime');import slowdown as _SD
    P=_SD.profile(a);dr=sections.get(a).get('drops') or []
    if not P or not dr:return []
    out=[]
    for x,y in P['sections']:
      if y<=dr[0][0]+2:continue  # intro
      if x>=dr[-1][1]-4 or any(p<=x and y<=q for p,q in dr):out.append((x,y))  # outro or in-drop half-time (breakdowns are fine)
    return out
  except Exception as ex:
    print('SLOWDOWN profile failed',a,ex,file=sys.stderr);return []
def thin_swap(a,b,wa,wb):
  ga,gb=track(a)['g']['bar'],track(b)['g']['bar'];la=np.asarray(ga.get('low',ga['all']),float);lb=np.asarray(gb.get('low',gb['all']),float)
  wa,wb=list(wa),list(wb);q=len(wa)//4;sa=[k for k in wa[q:len(wa)-q] if 0<=k<len(la)];sb=[k for k in wb[q:len(wb)-q] if 0<=k<len(lb)]
  if not sa or not sb:return False
  return bool(np.median(la[sa])-np.percentile(la,75)<-THIN_DB and np.median(lb[sb])-np.percentile(lb,75)<-THIN_DB)
XT={};inn={ids[0]:0};outs={};loops={};notes={};info_={}
LAND_EXTRA_WINS=set()
PLANNER_EXTRA_WINS=set()  # windows only added by window_planner.engine_cands (past bar-80 / before emin)
_EE_PICKER_WINS=set()
def pair_cands(i,ia0):
  """all scored windows for blend i given where track i starts (ia0); sorted best first"""
  global X
  global PLANNER_EXTRA_WINS, LAND_EXTRA_WINS, _EE_PICKER_WINS
  PLANNER_EXTRA_WINS=set();LAND_EXTRA_WINS=set();_EE_PICKER_WINS=set()
  a,b=ids[i],ids[i+1];ta,ala,ba,va,na=A_(a);tb,alb,bb,vb,nb=A_(b)
  ia=ia0[1]+16 if isinstance(ia0,tuple) else ia0;res=[]
  e_max=min(tail0(ala,ba),na,OUTMAX.get(a,na));e_max-=e_max%16
  minlen=160 if a in ANCH else 96-X  # anchors: >=160 bars (~220 s) of their own music, blend included
  emin=max(ia+minlen,ia+int((e_max-ia)*0.5));emin+=(-emin)%16;emin=min(emin,e_max)
  XMAX=X
  _ee_xs=set()
  if __import__('early_exit').flag_on() and os.environ.get('PICKER_INJECT_CS')=='1' and os.environ.get('PICKER_STYLE_GATED_MAP'):
    try:
      import json as _js_ee
      _tab_ee=_js_ee.load(open(os.environ['PICKER_STYLE_GATED_MAP']))
      _w0_ee=(_tab_ee.get('by_yt') or {}).get(f'{a}|{b}') or _tab_ee.get(f'{a}|{b}')
      _rk_ee=(_tab_ee.get('ranked_by_yt') or {}).get(f'{a}|{b}') or []
      _ee_flag=(_tab_ee.get('ee_by_yt') or {}).get(f'{a}|{b}')
      _has_ee_map='ee_by_yt' in _tab_ee
      for _w_ee in ([_w0_ee] if _w0_ee else [])+list(_rk_ee):
        if _w_ee and _w_ee[0]=='n':
          _xw=int(_w_ee[4])
          if _xw>=36 or (_ee_flag and _xw>=20) or (not _has_ee_map and _xw in (20,24,28)):
            _ee_xs.add(_xw)
            _EE_PICKER_WINS.add((a,b,('n',int(_w_ee[1]),None,int(_w_ee[3]),_xw)))
    except Exception:
      pass
  for X in sorted({XMAX,16}|_ee_xs,reverse=True):  # 32-bar blend preferred; 16 is the lowest when no clean 32-bar window exists
    _std_x=X in (XMAX,16)
    cands=[]
    if _std_x:
      for e in range(e_max,emin-1,-16):
        for ib in range(0,min(81,nb-3*X),16):cands.append(('n',e,ib))
      if STRUCT:  # outro-over-intro (default 2026-10-31): outgoing plays its whole outro to its music end; incoming starts so its drop lands there
        SA,SB=sections.get(a),sections.get(b);es=min(e_max,(SA['music_end']//8)*8);ibs=SB['drop1']-X
        if ibs>=0 and es-X>=ia+16 and ibs+X<nb:cands.append(('n',es,ibs));STRK.add(('n',a,b,es,ibs,X))
        if __import__('drop_swap').flag_on() and ibs>=0 and es-X>=ia+16:  # DROP_SWAP (2026-11-18 research, off by default): incoming intro has no bass -> also try the cue whose drop lands on the bass swap
          import drop_swap as _DS;_wa=list(range(es-X,es));_wb=list(range(ibs,ibs+X));_ctx(a,_wa,b,_wb)
          try:_c=swap_at(a,b,_wa,_wb);_sw=SW
          finally:_ctx(None)
          _gb=track(b)['g']['bar'];_ibd=_DS.recue(np.array(_gb.get('low',_gb['all']),float),SB['drop1'],X,ibs,_c,_sw,nb)
          if _ibd is not None:cands.append(('n',es,_ibd));STRK.add(('n',a,b,es,_ibd,X));print('DROP_SWAP',a,b,'X',X,'cue',ibs,'->',_ibd,'swap',round(_c,2),file=sys.stderr)
        if SB['drop1']-16>=16 and es-X>=ia+16:cands.append(('lb',es,SB['drop1']-16));STRK.add(('lb',a,b,es,SB['drop1']-16,X))  # gold (the listener 5/5, Mix 05 55:10 -> Just Hold On): incoming loops its last intro phrase, drop lands as the outgoing's music ends
      if __import__('window_planner').flag_on(os.environ.get('WINDOW_PLANNER')) or __import__('learned_ranker').flag_on(os.environ.get('RANKER')):  # mid-track section windows: planner or RANKER=1 (both off by default)
        import window_planner as _WP, sections as _SEC
        have=set(cands)
        for kind,e,ib in _WP.engine_cands(_SEC.get(a), _SEC.get(b), X, e_max=e_max, ia=ia):
          if (kind,e,ib) not in have:
            cands.append((kind,e,ib)); have.add((kind,e,ib))
            # win_key form for kind 'n': [kind, e, None, ib, X]
            PLANNER_EXTRA_WINS.add((kind, e, None, ib, X))
      if __import__('replica_rule').flag_on():  # REPLICA v1 pro-replication window (2026-11-18, off by default)
        import replica_rule as _RR, sections as _SEC
        have=set(cands)
        for kind,e,ib in _RR.engine_cands(_SEC.get(a), _SEC.get(b), X, e_max=e_max, ia=ia, a_id=a):
          if (kind,e,ib) not in have:
            cands.append((kind,e,ib)); have.add((kind,e,ib)); PLANNER_EXTRA_WINS.add((kind, e, None, ib, X))
      if __import__('replica_rule').drop_mode()!='off':  # DROPCAND drop-exit / drop-cue windows (2026-11-18, off by default)
        import replica_rule as _RR, sections as _SEC
        have=set(cands)
        for kind,e,ib in _RR.drop_engine_cands(_SEC.get(a), _SEC.get(b), X, e_max=e_max, ia=ia):
          if (kind,e,ib) not in have:
            cands.append((kind,e,ib)); have.add((kind,e,ib)); PLANNER_EXTRA_WINS.add((kind, e, None, ib, X))
      if os.environ.get('PLAN_LAND','0') not in ('','0'):  # PLAN_LAND (2026-11-20 beats RCA, off by default): 'landing' breakdown fades for the DRUMCLASH veto fallback only
        # outgoing exits where one of its breakdowns ends (= start of a drop, the X bars before it outside every drop); incoming cue =
        # one of its drop starts minus X (the X bars before it outside every drop). 8-bar phrase granularity, may be off the 16-bar grid
        # (pola04: B drop at 56 -> cue 40/24). Marked land_extra: recreate keeps them out of the default families.
        import sections as _SEC
        _SA,_SB=_SEC.get(a),_SEC.get(b);_ind=lambda S,k:any(lo<=k<hi for lo,hi in (S.get('drops') or []))
        have=set(cands)
        for _e in sorted({lo for lo,hi in (_SA.get('drops') or [])}):
          if _e%8 or _e>e_max or _e<emin or _e-X<ia+16 or any(_ind(_SA,k) for k in range(_e-X,_e)):continue
          for _d in sorted({lo for lo,hi in (_SB.get('drops') or [])}):
            _ib=_d-X
            if _ib<0 or _ib%8 or _ib+3*X>nb or any(_ind(_SB,k) for k in range(_ib,_d)):continue
            if ('n',_e,_ib) not in have:
              cands.append(('n',_e,_ib));have.add(('n',_e,_ib));PLANNER_EXTRA_WINS.add(('n',_e,None,_ib,X));LAND_EXTRA_WINS.add(('n',_e,None,_ib,X))
      if os.environ.get('PICKER_WIN'):  # PICKER_WIN=<json {"a|b": [kind,e,null,ib,X]}> (2026-11-19 nightly, off by default): learned picker's window as a candidate
        import json as _js
        _w=_js.load(open(os.environ['PICKER_WIN'])).get(f'{a}|{b}')
        if _w and int(_w[4])==X and ('n',int(_w[1]),int(_w[3])) not in set(cands):
          cands.append(('n',int(_w[1]),int(_w[3]))); PLANNER_EXTRA_WINS.add(('n',int(_w[1]),None,int(_w[3]),X))
    if os.environ.get('PICKER_INJECT_CS')=='1' and os.environ.get('PICKER_STYLE_GATED_MAP'):
      import json as _js
      _tab=_js.load(open(os.environ['PICKER_STYLE_GATED_MAP']))
      _w0=(_tab.get('by_yt') or {}).get(f'{a}|{b}') or _tab.get(f'{a}|{b}')
      _rks=(_tab.get('ranked_by_yt') or {}).get(f'{a}|{b}') or []
      _all_pw=([_w0] if _w0 else [])+list(_rks)
      _have_pw=set(cands)
      for _w in _all_pw:
        if _w and _w[0]=='n' and int(_w[4])==X:
          _ee,_ib=int(_w[1]),int(_w[3])
          if 16<=_ee-X and _ee<=na and 0<=_ib and _ib+X<=nb-16 and ('n',_ee,_ib) not in _have_pw:
            cands.append(('n',_ee,_ib)); _have_pw.add(('n',_ee,_ib)); PLANNER_EXTRA_WINS.add(('n',_ee,None,_ib,X))
    if _std_x:
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
    THINK=set();DCUE=set();LDE=None
    if STRUCT_THIN or THIN_DROPCUE:
      for (k_,a_,b_,es_,ib_,X_) in list(STRK):
        if a_!=a or b_!=b or X_!=X:continue
        wa_=range(es_-X,es_);wb_=[ib_+(k%16) for k in range(X)] if k_=='lb' else range(ib_,ib_+X)
        if thin_swap(a,b,wa_,wb_):
          THINK.add((k_,a,b,es_,ib_,X));d1_=sections.get(b)['drop1']
          if THIN_DROPCUE:
            for (kk,ee,qq) in cands:
              if kk=='n' and ee==es_ and qq<=d1_<=qq+X-4 and ('n',a,b,ee,qq,X) not in STRK:DCUE.add(('n',a,b,ee,qq,X))
      THIN_LOG.append(dict(a=a,b=b,X=X,thin=sorted(map(str,THINK)),dropcue=sorted(map(str,DCUE))))
      _dra=sections.get(a).get('drops') or [];LDE=(_dra[-1][1]-8) if (_dra and THINK and STRUCT_THIN) else None  # payoff guard: with the bonus gone, never trade the outgoing's last drop for it
      if THINK:print('THIN',a,b,'X',X,'thin',sorted(THINK),'dropcue',sorted(DCUE),file=sys.stderr)
    SLOWS=[];SLOWALT=set();LDE2=None
    if SLOWDOWN:
      SLOWS=slow_secs(a);_dra=sections.get(a).get('drops') or []
      if SLOWS and _dra:
        LDE2=_dra[-1][1]-8;d1b_=sections.get(b)['drop1']
        hit=[k6 for k6 in STRK if k6[1]==a and k6[2]==b and k6[5]==X and any(x<=k6[3]-X<y for x,y in SLOWS)]
        if hit:
          s0=min(x for x,y in SLOWS if x>=LDE2) if any(x>=LDE2 for x,y in SLOWS) else None
          if s0 is not None:
            alts=[ee for (kk,ee,qq) in cands if kk=='n' and LDE2<=ee-X<s0]
            ib_=d1b_-X
            if alts and ib_>=0 and ib_+X<nb:
              ee=max(alts)
              if ('n',ee,ib_) not in set(cands):cands.append(('n',ee,ib_))
              SLOWALT.add(('n',a,b,ee,ib_,X))
        if not hit:LDE2=None  # payoff guard only where the slowdown actually displaced the bonus window
        SLOW_LOG.append(dict(a=a,b=b,X=X,slow=SLOWS,hit=[str(h) for h in hit],alt=[str(h) for h in SLOWALT]))
        print('SLOWDOWN',a,b,'X',X,'slow',SLOWS,'bonus window hit',hit,'alt',sorted(SLOWALT),file=sys.stderr)
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
      _jp=float(os.environ.get('SEAMPEN',8))*max(0,jump-3);r['jump_pen']=round(_jp,2);r['pen']+=_jp
      hole=int(any(alb[k]<float(os.environ.get('HOLE_DB',-31)) for k in range(q+X,min(q+X+96,tail0(alb,bb)))))  # incoming would play a near-silent bar of its own (guardrail E2)
      r['pen']+=float(os.environ.get('HOLEPEN',0))*hole
      _sf=int(step>float(os.environ.get('SEAMMAX',2)));r['seam_fail']=_sf;_bm=min(8,int(os.environ.get('BOTHMIN',11))) if r.get('early_exit') else int(os.environ.get('BOTHMIN',11))
      if _sf or r['both']<_bm:r['pen']+=float(os.environ.get('HARDPEN',60))  # hard limits: guardrail N1 (3 dB step) and O1 (>=8 bars)
      if CUEW>0:r['cue']=round(cue_pen(a,ea),3);r['pen']+=CUEW*r['cue']
      sc=(r['pen']+(float(os.environ.get('SHORTPEN',6)) if X<XMAX else 0)+LW*skipped+float(os.environ.get('LOOPPEN',40))*{'n':0,'la':1,'lb':1,'ab':2,'lx':0}[kind]+(LXPEN if kind=='lx' else 0),-ea,str(ib))
      _k6=(kind,a,b,ea,ib,X)
      if __import__('energy_stab').on():  # ESTAB (2026-11-24 midnight research, off by default): predicted energy-dip cost, src2/energy_stab.py
        _ec,_ed=__import__('energy_stab').cost(track(a)['g']['bar'],track(b)['g']['bar'],list(wa),list(wb));r['estab_dip']=round(_ed,2);sc=(sc[0]+_ec,)+sc[1:]
      if SLOWS and kind in ('n','lb') and any(x<=ea-X<y for x,y in SLOWS):sc=(sc[0]+STRUCTW,)+sc[1:]  # SLOWDOWN: blend may not start inside the outgoing's outro / in-drop slowdown
      if SLOWALT and _k6 in SLOWALT and not EXITPOS:sc=(sc[0]-STRUCTW,)+sc[1:]
      if EXITPOS:sc=(sc[0]+exitpos_term(a,b,ea,ib,X,e_max),)+sc[1:]
      if LDE2 is not None and ea-X<LDE2:sc=(sc[0]+STRUCTW,)+sc[1:]  # SLOWDOWN payoff guard: never start before the last 8 bars of A's last drop  # SLOWDOWN: pro-like alternative inherits the outro-over-intro bonus
      if LDE is not None and ea-X<LDE:sc=(sc[0]+STRUCTW,)+sc[1:]  # STRUCT_THIN payoff guard (2026-11-19): blend may not start before A's last drop has played (its last 8 bars may overlap)
      if _k6 in STRK:
        _bw=STRUCTB if not (STRUCT_COND and not struct_full(a,ea-X,ea)) else 0.0
        if STRUCT_MID and _SM is not None and _SM.pocket(a) is not None and _bw>0:_bw=STRUCT_MID_B
        if EXITPOS:_bw=0.0
        if OUTRO_QC and _bw>0:_bw*=1-outro_qc(a,ea-X,ea)
        if _k6 in THINK and THIN_DROPCUE and DCUE:_bw=0.0  # THIN_DROPCUE: the bonus moves to the drop-in-overlap cue(s)
        elif _k6 in THINK and STRUCT_THIN:_bw=STRUCTW*STRUCT_THIN_W
        sc=(sc[0]-_bw-(float(os.environ.get('LOOPPEN',40)) if kind=='lb' and _bw>0 else 0),)+sc[1:]
      elif _k6 in DCUE and not EXITPOS:sc=(sc[0]-STRUCTW,)+sc[1:]  # blend length chosen per pair from structure + fit (the listener 2026-10-31)
      if STRUCT_MID and _SM is not None and kind in ('n','lb') and _SM.mid_exit(a,ea):
        sc=(sc[0]-STRUCT_MID_W,)+sc[1:]
      res.append((sc,kind,(e,p) if kind in('la','ab','lx') else e,ib,r,X))
  X=XMAX;res.sort(key=lambda t:t[0])
  if EXITPOS and EXITPOS_GATE and EXITPOS_DROP and res:
    def _sea(c):
      e=c[2];return (e[0] if isinstance(e,tuple) else e,c[3],c[5],c[1])
    def _sdcost(c):
      sc,kind,e,ib,r,X=c;ea=_sea(c)[0];term=exitpos_term(a,b,ea,ib,X,e_max);bonus=0.0
      if (kind,a,b,ea,ib,X) in STRK:
        bonus=STRUCTB
        if OUTRO_QC and bonus>0:bonus*=1-outro_qc(a,ea-X,ea)
      return (sc[0]-term-bonus,)+sc[1:]
    try:
      sys.path.insert(0,'/workspace/mixes/protrans/replica/halftime')
      import exitpos_drop as _ED, exitpos_gate as _EG
      def _sfam(xpred):
        cands=[c for c in res if _sea(c)[3]=='n' and xpred(_sea(c)[2])]
        if not cands:return None,None,False,dict(reason='no_cand',arm='none')
        dwin=min(cands,key=_sdcost);default=_sea(dwin)[:3]
        # Drop owns last-drop-end windows; strict owns post-drop windows. Disjoint hard_ok.
        # If drop wants a window but is blocked (pro_outro / known hard fail), fall through to strict.
        d_alts=[c for c in cands if _ED.hard_ok_drop(_sea(c)[:3],default,sections.get(a),sections.get(b))]
        g_alts=[c for c in cands if _EG.hard_ok(_sea(c)[:3],default,sections.get(a),sections.get(b))]
        info=dict(arm='none')
        altw=None
        if d_alts:
          ac=min(d_alts,key=lambda c:c[0]);dalt=_sea(ac)[:3]
          take,dinfo=_ED.should_switch_drop(default,dalt,sections.get(a),sections.get(b),ya=a,yb=b)
          info['drop']=dict(alt=list(dalt),take=bool(take and dalt!=default),**{k:v for k,v in dinfo.items()})
          if take and dalt!=default:
            return default,dalt,True,dict(arm='drop',reason=dinfo.get('reason','drop_end'),**{k:v for k,v in dinfo.items() if k!='reason'})
        else:
          info['drop']=dict(reason='no_alt')
        if g_alts:
          ac=min(g_alts,key=lambda c:c[0]);galt=_sea(ac)[:3]
          take,ginfo=_EG.should_switch(default,galt,sections.get(a),sections.get(b),ya=a)
          info['strict']=dict(alt=list(galt),take=bool(take and galt!=default),**{k:v for k,v in ginfo.items()})
          if take and galt!=default:
            return default,galt,True,dict(arm='strict',reason=ginfo.get('reason','gate'),**{k:v for k,v in ginfo.items() if k!='reason'})
        else:
          info['strict']=dict(reason='no_alt')
        return default,altw,False,dict(reason=(info.get('drop') or info.get('strict') or {}).get('reason','none'),**info)
      d16,a16,t16,i16=_sfam(lambda X:X==16)
      d32,a32,t32,i32=_sfam(lambda X:X>=32)
      boost=set()
      if t16 and a16:boost.add(tuple(a16))
      if t32 and a32:boost.add(tuple(a32))
      new=[]
      for c in res:
        ea,ib,X,kind=_sea(c)
        if kind=='n' and (ea,ib,X) in boost:
          sc=c[0];new.append(((sc[0]-10*STRUCTW,)+sc[1:],)+c[1:])
        else:
          new.append((_sdcost(c),)+c[1:])
      res=new
      res.sort(key=lambda t:t[0])
      rec=dict(a=a,b=b,stack=True,default=list(d16) if d16 else (list(d32) if d32 else None),alt=list(a16) if a16 else (list(a32) if a32 else None),take=bool(t16 or t32),reason=('short:'+((i16 or {}).get('arm','')+':'+(i16 or {}).get('reason','')) if t16 else ('long:'+((i32 or {}).get('arm','')+':'+(i32 or {}).get('reason','')) if t32 else (i16 or i32 or {}).get('reason','none'))),short=dict(default=list(d16) if d16 else None,alt=list(a16) if a16 else None,take=t16,**(i16 or {})),long=dict(default=list(d32) if d32 else None,alt=list(a32) if a32 else None,take=t32,**(i32 or {})))
      EPG_LOG.append(rec)
      print('EXITPOS_STACK',a,b,'short',d16,a16,t16,i16,'long',d32,a32,t32,i32,file=sys.stderr)
      _lf=os.environ.get('EPG_LOG_FILE')
      if _lf:
        import json as _j
        with open(_lf,'a') as _f:_f.write(_j.dumps(rec)+chr(10))
    except Exception as ex:
      print('EXITPOS_STACK failed',a,b,ex,file=sys.stderr)
  if EXITPOS and EXITPOS_GATE and not EXITPOS_DROP and res:
    def _ea(c):
      e=c[2];return (e[0] if isinstance(e,tuple) else e,c[3],c[5],c[1])
    def _dcost(c):
      sc,kind,e,ib,r,X=c;ea=_ea(c)[0];term=exitpos_term(a,b,ea,ib,X,e_max);bonus=0.0
      if (kind,a,b,ea,ib,X) in STRK:
        bonus=STRUCTB
        if OUTRO_QC and bonus>0:bonus*=1-outro_qc(a,ea-X,ea)
      return (sc[0]-term-bonus,)+sc[1:]
    try:
      sys.path.insert(0,'/workspace/mixes/protrans/replica/halftime');import exitpos_gate as _EG
      def _fam(xpred):
        cands=[c for c in res if _ea(c)[3]=='n' and xpred(_ea(c)[2])]
        if not cands:return None,None,False,dict(reason='no_cand')
        dwin=min(cands,key=_dcost);default=_ea(dwin)[:3]
        alts=[c for c in cands if _EG.hard_ok(_ea(c)[:3],default,sections.get(a),sections.get(b))]
        if not alts:return default,None,False,dict(reason='no_alt')
        ac=min(alts,key=lambda c:c[0]);altw=_ea(ac)[:3]
        take,info=_EG.should_switch(default,altw,sections.get(a),sections.get(b),ya=a)
        return default,altw,bool(take and altw!=default),info
      d16,a16,t16,i16=_fam(lambda X:X==16)
      d32,a32,t32,i32=_fam(lambda X:X>=32)
      boost=set()
      if t16 and a16:boost.add(tuple(a16))
      if t32 and a32:boost.add(tuple(a32))
      new=[]
      for c in res:
        ea,ib,X,kind=_ea(c)
        if kind=='n' and (ea,ib,X) in boost:
          sc=c[0];new.append(((sc[0]-10*STRUCTW,)+sc[1:],)+c[1:])
        else:
          new.append((_dcost(c),)+c[1:])
      res=new
      res.sort(key=lambda t:t[0])
      rec=dict(a=a,b=b,default=list(d16) if d16 else (list(d32) if d32 else None),alt=list(a16) if a16 else (list(a32) if a32 else None),take=bool(t16 or t32),reason=('short:'+i16.get('reason','') if t16 else ('long:'+i32.get('reason','') if t32 else (i16 or i32 or {}).get('reason','none'))),short=dict(default=list(d16) if d16 else None,alt=list(a16) if a16 else None,take=t16,**i16),long=dict(default=list(d32) if d32 else None,alt=list(a32) if a32 else None,take=t32,**i32))
      EPG_LOG.append(rec)
      print('EXITPOS_GATE',a,b,'short',d16,a16,t16,i16,'long',d32,a32,t32,i32,file=sys.stderr)
      _lf=os.environ.get('EPG_LOG_FILE')
      if _lf:
        import json as _j
        with open(_lf,'a') as _f:_f.write(_j.dumps(rec)+chr(10))
    except Exception as ex:
      print('EXITPOS_GATE failed',a,b,ex,file=sys.stderr)
  if EXITPOS and EXITPOS_DROP and not EXITPOS_GATE and res:
    def _dea(c):
      e=c[2];return (e[0] if isinstance(e,tuple) else e,c[3],c[5],c[1])
    def _ddcost(c):
      sc,kind,e,ib,r,X=c;ea=_dea(c)[0];term=exitpos_term(a,b,ea,ib,X,e_max);bonus=0.0
      if (kind,a,b,ea,ib,X) in STRK:
        bonus=STRUCTB
        if OUTRO_QC and bonus>0:bonus*=1-outro_qc(a,ea-X,ea)
      return (sc[0]-term-bonus,)+sc[1:]
    try:
      sys.path.insert(0,'/workspace/mixes/protrans/replica/halftime');import exitpos_drop as _ED
      def _dfam(xpred):
        cands=[c for c in res if _dea(c)[3]=='n' and xpred(_dea(c)[2])]
        if not cands:return None,None,False,dict(reason='no_cand')
        dwin=min(cands,key=_ddcost);default=_dea(dwin)[:3]
        alts=[c for c in cands if _ED.hard_ok_drop(_dea(c)[:3],default,sections.get(a),sections.get(b))]
        if not alts:return default,None,False,dict(reason='no_alt')
        ac=min(alts,key=lambda c:c[0]);altw=_dea(ac)[:3]
        take,info=_ED.should_switch_drop(default,altw,sections.get(a),sections.get(b),ya=a,yb=b)
        return default,altw,bool(take and altw!=default),info
      d16,a16,t16,i16=_dfam(lambda X:X==16)
      d32,a32,t32,i32=_dfam(lambda X:X>=32)
      boost=set()
      if t16 and a16:boost.add(tuple(a16))
      if t32 and a32:boost.add(tuple(a32))
      new=[]
      for c in res:
        ea,ib,X,kind=_dea(c)
        if kind=='n' and (ea,ib,X) in boost:
          sc=c[0];new.append(((sc[0]-10*STRUCTW,)+sc[1:],)+c[1:])
        else:
          new.append((_ddcost(c),)+c[1:])
      res=new
      res.sort(key=lambda t:t[0])
      rec=dict(a=a,b=b,default=list(d16) if d16 else (list(d32) if d32 else None),alt=list(a16) if a16 else (list(a32) if a32 else None),take=bool(t16 or t32),reason=('short:'+i16.get('reason','') if t16 else ('long:'+i32.get('reason','') if t32 else (i16 or i32 or {}).get('reason','none'))),short=dict(default=list(d16) if d16 else None,alt=list(a16) if a16 else None,take=t16,**i16),long=dict(default=list(d32) if d32 else None,alt=list(a32) if a32 else None,take=t32,**i32))
      EPG_LOG.append(rec)
      print('EXITPOS_DROP',a,b,'short',d16,a16,t16,i16,'long',d32,a32,t32,i32,file=sys.stderr)
      _lf=os.environ.get('EPG_LOG_FILE')
      if _lf:
        import json as _j
        with open(_lf,'a') as _f:_f.write(_j.dumps(rec)+chr(10))
    except Exception as ex:
      print('EXITPOS_DROP failed',a,b,ex,file=sys.stderr)
  return res
def win_key(c):return [c[1],*(c[2] if isinstance(c[2],tuple) else (c[2],None)),c[3],c[5]]  # [kind, out bar, loop phrase, in bar, blend bars]
def nxt_inn(c):return ("loopB",c[3]) if c[1] in("lb","ab") else c[3]
LOOK=int(os.environ.get("LOOKAHEAD",8))
KIND={};LXD=set()
for i in range(len(ids)-1):
  a,b=ids[i],ids[i+1];cs=pair_cands(i,inn[a])
  if os.environ.get("DUMP_CANDS"):json.dump([dict(win=win_key(c),cost=float(c[0][0]),pen=float(c[4]['pen']),V=int(c[4].get('V',0)),L=int(c[4].get('L',0)),SG=int(c[4].get('SG',0)),R=float(c[4].get('R',1.0)),HB=bool((c[4].get('HB') or {}).get('flagged')),both=int(c[4].get('both',X)),seam_fail=int(c[4].get('seam_fail',0)),early_exit=int(c[4].get('early_exit',0)),pred_vdip=c[4].get('pred_vdip'),pred_ldip=c[4].get('pred_ldip'),drum_pen=c[4].get('drum_pen'),jump_pen=c[4].get('jump_pen'),planner_extra=tuple(win_key(c)) in PLANNER_EXTRA_WINS,land_extra=tuple(win_key(c)) in LAND_EXTRA_WINS) for c in cs],open(os.environ["DUMP_CANDS"],'w'));sys.exit()  # blend_bench.py: all scored windows of the first pair
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
  trans.append(dict(swap_w=SW,fade=FADE,tech=f'{X}-bar crossfader blend (equal-power, single control)'+(f' + {SW:g}-bar bass handoff' if SW>0 else ''),a=A['id'],b=B['id'],start_bar=s,swap_bar=s+int(round(info_[(A['id'],B['id'])]['c'])),early_exit_cand=bool(info_[(A['id'],B['id'])].get('early_exit')),high_bar=None if info_[(A['id'],B['id'])]['h'] is None else s+info_[(A['id'],B['id'])]['h'],swap_ofs=float(SW/2 if (SNAP and SW>0 and info_[(A['id'],B['id'])]['c']!=POS*X) else 0),swap_phrase=bool(SNAP and info_[(A['id'],B['id'])]['c']!=POS*X and info_[(A['id'],B['id'])]['c']%4==0),end_bar=e,xfader=xs,vocal_clash_bars=cl,halfbeat=info_[(A['id'],B['id'])].get('HB'),keys=f"{KEYS.get(A['id'])}->{KEYS.get(B['id'])}",key_ok=bool(_C.camelot_ok(KEYS.get(A['id']),KEYS.get(B['id']))),pitch_shift_semitones=0,bass_swap=[s+round(POS*X)-SW/2,s+round(POS*X)+SW/2] if SW>0 else None,notes=n or ['vocal-free mix points chosen from full-track analysis']))
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
  def ramp(c,up,w=4.0):
    return [[c-w/2+w*j/16,round(float((1-np.cos(np.pi*j/16))/2 if up else (1+np.cos(np.pi*j/16))/2),5)] for j in range(17)]
  def at(t):return t['swap_bar']+t.get('swap_ofs',t['swap_w']/2 if t['swap_phrase'] else 0)  # 2026-11-01 v6r3: any non-POS pick (phrase OR SWAP_THIN) is a swap START, as score()/hole() assume (ce=c+SW/2); off-phrase picks were centred 2 bars early -> 24:48/40:38 holes  # phrase-snapped swaps start ON the boundary (incoming bass lands on the 1, not a bar early)
  # BASS_LEAD (2026-11-01, Mix 05 v2 i18 L1 x3): the two lows used to ramp on the SAME raised cosine, so mid-swap both sat at
  # -6 dB ('both decks carry full bass'). Outgoing low now leads by LEAD bars (same 4-bar shape, still monotonic): they cross ~-10 dB.
  def lead(t):
    if t['a'] in PIN or f"{t['a']}>{t['b']}" in LEADOFF:return (0.0,0.0)
    # FADE=long: outgoing lows leave first, even when the swap is at POS (exit start), so the
    # mid-cross is not two equal plateau faders (Mix 08 long1e L1). Phrase-snapped unchanged.
    # A thin incoming stretch is handled by moving the swap earlier (swap_before_thin in _ctx),
    # not by delaying the outgoing down-ramp (that was Mix 08 long1g's X1/L1 regression).
    return _FL.bass_lead(BLEAD,phrase=bool(t.get('swap_phrase')),fade='long' if (t.get('fade',FADE) in ('long','graphcut') or _longish()) else t.get('fade',FADE))
  # Low lanes follow each blend's own swap_w (BASS_COVER may set swap_w=0 after _ctx resets the global SW).
  lo=[]
  if i>0 and trans[i-1]['swap_w']>0:lo+=ramp(at(trans[i-1])+lead(trans[i-1])[1],True,trans[i-1]['swap_w'])
  if i<len(decks)-1 and trans[i]['swap_w']>0:lo+=ramp(at(trans[i])-lead(trans[i])[0],False,trans[i]['swap_w'])
  if lo:d['auto']['low']=lo
  # MID_HOLD (2026-11-25 midnight research, off by default): incoming 150 Hz-2 kHz band held MID_HOLD_DB under the
  # crossfader until the bass swap, then opened on the SAME raised cosine as the incoming low lane, so melody/vocal
  # mids land with the bassline on the phrase instead of creeping in at the plateau (RCA 2026-11-23 'random piano').
  # Pro corpus (860 corpus_v2 deck-gain curves): incoming mids reach full level with the bass (median 0 bars, IQR -1..+3)
  # and sit ~2.6 dB under the incoming highs before that. Kim, Yang & Nam (NIME 2021): DJs ride EQs in ~72% of transitions.
  if os.environ.get('MID_HOLD','0')=='1' and i>0 and trans[i-1]['swap_w']>0:
    _g0=10**(-float(os.environ.get('MID_HOLD_DB',6))/20)
    d['auto']['mid']=[[p[0],round(_g0+(1-_g0)*p[1],5)] for p in ramp(at(trans[i-1])+lead(trans[i-1])[1],True,trans[i-1]['swap_w'])]
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
TE=float(os.environ.get('TAIL_EXIT',0) or 0)  # 2026-11-15 research, off by default: outgoing gone N bars after the bass swap (tail_exit.py)
if TE>0 and not GC:
  import tail_exit as _TE
  _TE.apply(decks,trans,TE,rate=float(os.environ.get('TAIL_RATE',2.75)),skip=set(PIN))
TS=float(os.environ.get('TAIL_SHALLOW',0) or 0)  # 2026-11-15 research, off by default: max outgoing fall (dB/bar) after the exit starts; residual extends past the window (tail_shape.py)
if TS>0 and not GC:
  import tail_shape as _TS
  _ts_cap=float(os.environ.get('TAIL_SHALLOW_CAP',0) or 0) or None  # 2026-11-16 research, off by default: residual gone by window end + N bars
  _ts_gate=os.environ.get('TAIL_SHALLOW_GATE','') or None  # 2026-11-16 research, off by default: 'end' = only blends whose exit already sits at the window end
  _TS.apply(decks,trans,TS,skip=set(PIN),cap=_ts_cap,gate=_ts_gate)
SI=float(os.environ.get('SNAP_IN',0) or 0)  # 2026-11-15 research, off by default: late legal incoming snap + shallow outgoing hold (snap_in.py)
if SI>0 and not GC:
  import snap_in as _SI
  _si_hold=float(os.environ.get('SNAP_IN_DB',12) or 12)
  _si_rate=float(os.environ.get('TAIL_SHALLOW',0) or 0) or _SI.RATE
  _si_extra=float(os.environ.get('SNAP_IN_HOLD',0) or 0)
  _SI.apply(decks,trans,hold_db=_si_hold,rate=_si_rate,skip=set(PIN),hold_extra=_si_extra)
if __import__('early_exit').flag_on() and not GC:
  import early_exit as _EE
  EE_LOG=_EE.apply(decks,trans,secs_of=sections.get,skip=set(PIN))
  for _r in EE_LOG:print('EARLY_EXIT',_r,file=sys.stderr)
if __import__('pro_fade').flag_on() and not GC:
  import pro_fade as _PF
  def _pf_lows(x):
    g=track(x)['g']['bar'];return g.get('low',g['all'])
  PF_LOG=_PF.apply(decks,trans,skip=set(PIN),lows_of=_pf_lows)
  for _r in PF_LOG:print('PRO_FADE',_r,file=sys.stderr)
# beats -> melody-only fixes (beatmelody.py, 2026-11-02): plan step 'bm_fix' ('dswap' | 'dswap_beat' | 'ib' | 'ib+dswap'), or env BM_FIX on every BM1 blend
import beatmelody as _BMX
_BMM=dict(decks=decks,trans=trans,bar_sec=BAR);_bmenv=os.environ.get('BM_FIX','')
_bmcases={r['trans'] for r in _BMX.bm1(_BMM)} if _bmenv else set()
for i in range(len(trans)):
  f=plan[i].get('bm_fix') or (_bmenv if i in _bmcases else '')
  if f:
    try:_BMX.apply(_BMM,i,f)
    except ValueError as ex:print('bm_fix skipped',trans[i]['a'],'>',trans[i]['b'],ex,file=sys.stderr)
if GC:
  import fade_graphcut as _GC
  _GC.apply(decks,trans)
# BLEND_LOCK must run before --dry exits: blend_bench.render (official recreate/eval)
# always plans with --dry and then engine.render_deck. If the lock is only applied
# on the full-mix path, dry_meta never gets blend_lock_ms and the official clip
# is a no-op (2026-11-17 RCA, We Are One -> Ghetto Blaster stayed 123 ms apart).
# BASS_FILL (2026-11-20 midnight research, off by default): src2/bass_fill.py. Render-only; windows, swap and fader unchanged.
if int(os.environ.get('BASS_FILL',0) or 0) and not GC:
  import bass_fill as _BF
  def _bf_lows(x):
    g=track(x)['g']['bar'];return g.get('low',g['all'])
  BF_LOG=_BF.apply(decks,trans,_bf_lows,db=float(os.environ.get('BASS_FILL_DB',6) or 6),skip=set(PIN),secs_of=lambda x:sections.get(x))
  for _r in BF_LOG:print('BASS_FILL',_r,file=sys.stderr)
import finephase as _FP
if _FP.lock_flag_on():
  _FP.lock_decks(decks,trans)
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
