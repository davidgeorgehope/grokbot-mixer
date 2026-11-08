"""No see-saw / pumping between decks inside a blend (the listener, Mix 06 28:00 Remedy>Ignite rated 2: 'fighting, fading randomly in and out').
Thresholds in src2/seesaw.py: outgoing deck bar-to-bar rise <= 4.5 dB, summed-level reversals (>=2.5 dB swings) < 4, deck deltas not anti-correlated (r>-0.5 with both >=2 dB rms)."""
import json,sys;sys.path.insert(0,'/workspace/mixes/src2')
import checks as C,seesaw as S
def test_detector_regression():
  m6=json.load(open('/workspace/mixes/src2/mix06i12_meta.json'))
  assert S.blend(m6,8)['fails'], 'Remedy>Ignite (rated 2) must be flagged'
  gold=[r for r in S.check(json.load(open('/workspace/mixes/src2/mix05v2i10_meta.json'))) if r['a'].startswith('j9Au')][0]
  assert not gold['fails'], 'gold Lilies>Just Hold On must pass'
def _scorer(plan):
  import os;cw=os.getcwd();os.chdir('/workspace/mixes/src2')
  try:
    src=open('mix_simple.py').read();sv=sys.argv;sys.argv=['x','--plan',plan,'--out','/dev/null'];ns={'__name__':'t'}
    exec(compile(src[:src.index('LOOK=int(')],'mix_simple.py','exec'),ns);sys.argv=sv;return ns
  finally:os.chdir(cw)
def _rq_plan(win=None):
  p=json.load(open('/workspace/mixes/src2/plan_mix06i12.json'));q=[dict(p[8]),dict(p[9])];q[0].pop('out_win',None)
  if win:q[0]['out_win']=win
  import tempfile;f=tempfile.NamedTemporaryFile('w',suffix='.json',delete=False);json.dump(q,f);f.close();return f.name
def test_loop_fill_is_soft_penalty():
  """the listener 2026-11-01 (no hard 'never' rules): a loop over a fill (Remedy 160-175, fill 172-175) is still a candidate, just scored worse"""
  import os;f=_rq_plan();cw=os.getcwd()
  try:
    ns=_scorer(f);os.chdir('/workspace/mixes/src2')
    assert ns['loop_dip']('sObzaBqaBRQ',160)>0 and ns['loop_clean']('sObzaBqaBRQ',144)
    cs=ns['pair_cands'](0,0);la=[c for c in cs if c[1]=='la' and c[2]==(176,160)]
    assert la, 'loop over the fill must stay a candidate (soft penalty, not a refusal)'
    assert any(c[1]=='lx' for c in cs), 'beat-only synthetic outro must be offered'
  finally:os.chdir(cw);os.unlink(f)
def test_beat_outro_is_rendered_before_blend(synthetic_meta, monkeypatch):
  """A synthetic beat-only outro starts before the blend; faders stay monotonic.

  The deleted Remedy/Ignite full render is not a fixture. Check the same engine
  contract on independent sources, without rerunning a historical whole mix.
  """
  import numpy as np, engine as E, soundfile as sf
  M=synthetic_meta;A,B=M['decks'];t=M['trans'][0]
  t['start_bar']=12;t['end_bar']=24
  A['full_map']=[[k,'mix' if k<8 else 'beat'] for k in range(32)]
  xs=np.linspace(12,24,49)
  A['auto']['gain']=[[float(x),float(np.cos((x-12)/12*np.pi/2))] for x in xs]
  B['auto']['gain']=[[float(x),float(np.sin((x-12)/12*np.pi/2))] for x in xs]
  sources=[c for _,c in A['full_map']]
  assert sources.index('beat')<t['start_bar']
  assert all(c=='beat' for c in sources[8:])
  y=E.render_deck(A)
  assert np.isfinite(y).all() and np.max(np.abs(y))>0
  dry=E.render_deck(dict(A,auto={}))
  # Past the source crossfade, the dry outro really is the beat stem, not melody.
  tr=E.track(A['id']);expected=E._bars(tr,[k for k,_ in A['full_map']],tr['st']['beat'],len(dry))
  start=round(9*E.BS)
  # LX_TRIM is a static source trim, so compare after fitting one fixed gain.
  a=expected[start:];b=dry[start:];g=float(np.sum(a*b)/np.sum(a*a))
  assert np.sqrt(np.mean((b-g*a)**2))<1e-5
  levels=np.full(128,-16.)
  monkeypatch.setattr(S,'_beats',lambda _:levels)
  monkeypatch.setattr(S,'_dnb',lambda _:levels)
  assert not S.blend(M,0)['fails']
  for d,up in ((A,False),(B,True)):
    diff=np.diff(np.array(d['auto']['gain'])[:,1])
    assert (diff>=-1e-9).all() if up else (diff<=1e-9).all()
