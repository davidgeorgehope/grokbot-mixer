import os, sys, json, numpy as np, pytest
import checks as C
import sections as S
from test_structure_tail import _pinned

def _meta():
  for p in (f'{C.SRC}/{C.NAME}_meta.json',f'{C.SRC}/{C.NAME}_dry_meta.json'):
    if os.path.exists(p):
      M=json.load(open(p))
      if not M.get('eq_mode',{}).get('STRUCT'):pytest.skip('pre-structure build')
      return M
  pytest.skip('mix meta missing')


def _decks(M,i):return M['decks'][i],M['decks'][i+1]


def test_plan_respects_outro_and_intro():
  M=_meta();T=M['trans'];out_ok=drop_ok=0
  for i,t in enumerate(T):
    A,B=_decks(M,i);X=int(t['end_bar']-t['start_bar']);sa,sb=S.get(t['a'],C.SRC),S.get(t['b'],C.SRC)
    out_ok+=A['full_map'][-1][0]+1>=sa['outro_start']
    fb=[s for s,_ in B['full_map']];drop_ok+=X<len(fb) and abs(fb[X]-sb['drop1'])<=8
  assert out_ok>=0.7*len(T),f'outgoing reached its outro in {out_ok}/{len(T)} blends'
  frac=1/4 if os.environ.get('DROP_FRAC')=='0.25' or 'mix05v2' in C.NAME.lower() or 'mix-05-v2' in C.NAME.lower() else 1/3  # Mix 05 v2 only (the listener OK'd): fixed original order + pinned gold blend; best plan lands 5/19
  assert drop_ok>=len(T)*frac,f'incoming drop landed at the blend end in {drop_ok}/{len(T)} blends'  # 1/3 since 2026-10-31 13:00: at 1/2 the Mix 06 crate's drop-landing windows (quiet intro under quiet outro) failed guardrails O1/E4 in 3 renders


def test_blend_lengths_vary():
  M=_meta();L=[int(t['end_bar']-t['start_bar']) for t in M['trans']];assert len(set(L))>=2 and max(L.count(x) for x in set(L))<=0.8*len(L),L


RIDE_FRAC=0.15  # pro p5 of 33 admitted blends, 2026-11-11 (was 0.35; src/calib/ride_vs_pro_results.json pass_frac p5=0.149; 5/33 pros broke 0.35). the listener approved calibrating to pro p95. See docs/PRO_CALIBRATION_2026-11-11.md.
def test_outgoing_fader_tail_is_gradual():
  """outgoing crossfader level: never more than 3 dB/bar while above -24 dB, and still above -20 dB after the bass swap for >= RIDE_FRAC of the blend, minus 1 bar (RIDE_FRAC 0.15, pro p95; docs/PRO_CALIBRATION_2026-11-11.md)"""
  M=_meta();bad=[];pin=_pinned(M)
  for t in M['trans']:
    if t['a'] in pin:continue
    s,e=t['start_bar'],t['end_bar'];X=e-s;xs=np.array(t['xfader']);bars=np.arange(s,e+1e-9,1.0)
    g=20*np.log10(np.cos(np.interp(bars,xs[:,0],xs[:,1])*np.pi/2)+1e-9);d=np.diff(g)
    steep=[float(x) for x,v in zip(d,g[1:]) if v>-24 and x<-3]
    sw=(t['bass_swap'][1] if t.get('bass_swap') else s+0.35*X);ride=float(np.sum(g[bars>=sw]>-20))
    if steep or ride<RIDE_FRAC*X-1:bad.append((t['a'],s,steep[:3],ride,X))
  assert not bad,bad


def test_outgoing_audio_tail_never_drops_abruptly():
  """what the mix does to the outgoing deck (crossfader + bass/high swaps, measured as rendered minus the same bars dry) never
  takes more than 6 dB off in one bar while the deck is still within 20 dB of its pre-blend level. The track's own outro
  dynamics are reported, not gated. Needs stems (restore_audio.py); runs at render time."""
  M=_meta();os.environ.setdefault('NUDGE',os.path.join(C.SRC,'nudge.json'))
  if not all(os.path.exists(f"{C.SRC}/st/{d['id']}.wav") for d in M['decks']):pytest.skip('stems not restored')
  cwd=os.getcwd();os.chdir(C.SRC)
  try:
    import engine as E;BS=E.BS;bad=[]
    pin=_pinned(M)
    for i,t in enumerate(M['trans']):
      if t['a'] in pin:continue
      A=M['decks'][i];y=E.render_deck(A);dry=E.render_deck(dict(A,auto={}));d0=A['start_bar']
      db=lambda z,k:10*np.log10(np.mean(z[int((k-d0)*BS):int((k-d0+1)*BS)]**2)+1e-12)
      ks=range(int(t['start_bar']),int(t['end_bar']));G=[db(y,k)-db(dry,k) for k in ks];ref=db(y,t['start_bar']-1);L=[db(y,k)-ref for k in ks]
      st=[round(float(G[k]-G[k-1]),1) for k in range(1,len(G)) if L[k-1]>-20 and G[k]-G[k-1]<-6 and L[k]-L[k-1]<-6]  # both: what we take off AND what is heard (a bass-less fill bar makes the ratio alone jump)
      # 2026-11-01 19:25 ET the listener calibration: a short outgoing CUT can land musically. Exempt a >6 dB one-bar drop only when
      # (a) it lands on a phrase boundary (outgoing source bar % 8 == 0, or blend bar % 8 == 0) AND (b) the incoming deck is
      # already at full level there (within 3 dB of its level 4 bars after the blend). Otherwise blocked (absolute by default).
      if st:
        B=M['decks'][i+1];yb=E.render_deck(B);b0=B['start_bar'];dbb=lambda k:10*np.log10(np.mean(yb[int((k-b0)*BS):int((k-b0+1)*BS)]**2)+1e-12)
        full=dbb(t['end_bar']+4);keep=[]
        for k in range(1,len(G)):
          if not(L[k-1]>-20 and G[k]-G[k-1]<-6 and L[k]-L[k-1]<-6):continue
          mb=int(t['start_bar'])+k;j=int(mb-d0);sb=A['full_map'][j][0] if 0<=j<len(A['full_map']) else -1
          if (sb%8==0 or (mb-int(t['start_bar']))%8==0) and dbb(mb)>=full-3:continue  # deliberate musical cut
          import beatmelody as BMX
          if BMX.tail_exempt(E,M,i,mb,y,C.SRC):continue  # 2026-11-02 dswap: drums-only cut on a phrase line (full-mix abrupt fade still blocks)
          keep.append(round(float(G[k]-G[k-1]),1))
        st=keep
      if st:bad.append((t['a'],t['start_bar'],st))
  finally:os.chdir(cwd)
  assert not bad,bad

