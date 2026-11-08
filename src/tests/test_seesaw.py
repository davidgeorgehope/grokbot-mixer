"""No see-saw / pumping between decks inside a blend (the listener, Mix 06 28:00 Remedy>Ignite rated 2: 'fighting, fading randomly in and out').
Thresholds in src2/seesaw.py: outgoing deck bar-to-bar rise <= 4.5 dB, summed-level reversals (>=2.5 dB swings) < 4, deck deltas not anti-correlated (r>-0.5 with both >=2 dB rms)."""
import json,sys;sys.path.insert(0,'/workspace/mixes/src2')
import checks as C,seesaw as S
def _current_meta():
  """the build under test (MIX_NAME, set by the build loops / deliver). Unset = no build under test: skip instead of judging the stale 'mixS' default"""
  import os,pytest
  n=os.environ.get('MIX_NAME');p=f'/workspace/mixes/src2/{n}_meta.json'
  if not n or not os.path.exists(p):pytest.skip('MIX_NAME not set: no build under test')
  return json.load(open(p))
def test_no_seesaw_between_decks():
  bad=[r for r in S.check(_current_meta()) if r['fails']]
  assert not bad,'\n'.join(f"{int(r['t']//60)}:{int(r['t']%60):02d} {r['a']}>{r['b']} {r['fails']} rise {r['out_rise']} wob {r['wobble']} r {r['anti_r']}" for r in bad)
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
def test_beat_outro_remedy_ignite():
  """Mix 06 28:00 Remedy>Ignite with the synthetic beat-only outro (drums+bass stem loop): W1 passes, the beat-only source is in place
  before the blend starts, and each deck's crossfader gain stays monotonic through the blend (no ducking / gain riding)"""
  from conftest import require_fixtures
  plan=json.load(open('/workspace/mixes/src2/plan_mix06i12.json'))
  require_fixtures(*(f"/workspace/mixes/src2/st/{p['id']}{ext}" for p in plan[8:10] for ext in ('.wav','.dnb.wav')))
  import os,subprocess,tempfile,numpy as np;f=_rq_plan(['lx',144,128,80,16]);out=tempfile.mkdtemp(prefix='rqlx_')+'/rq'
  try:
    subprocess.run([sys.executable,'mix_simple.py','--plan',f,'--out',out],cwd='/workspace/mixes/src2',check=True,capture_output=True)
    M=json.load(open(out+'_meta.json'));t=M['trans'][0];A,B=M['decks'];src=[c for _,c in A['full_map']]
    assert 'beat' in src and A['start_bar']+src.index('beat')<t['start_bar'], 'beat-only bars must start before the blend'
    assert all(c=='beat' for c in src[src.index('beat'):]), 'no source switch back mid-blend'
    for d,up in ((A,False),(B,True)):
      g=np.array(d['auto']['gain']);s=g[(g[:,0]>=t['start_bar'])&(g[:,0]<=t['end_bar'])][:,1];df=np.diff(s)
      assert (df>=-1e-9).all() if up else (df<=1e-9).all(), 'crossfader must be monotonic'
    r=S.blend(M,0);assert not r['fails'] and r['out_rise']<=S.OUT_RISE_DB, r
  finally:
    import shutil;shutil.rmtree(os.path.dirname(out),ignore_errors=True);os.unlink(f)
