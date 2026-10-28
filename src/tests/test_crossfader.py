"""X1 crossfader guardrail (the listener 2026-10-28): one monotonic x(t) per blend, deck gains only from x."""
import os,json,re,sys,numpy as np,pytest
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC=os.environ.get('MIX_SRC','/workspace/mixes/src2');NAME=os.environ.get('MIX_NAME','mixS');BAR=4*60/174.0
src=open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'guardrails.py')).read()
ns={'np':np};exec(src[src.index('def x1_check'):src.index('x1_check(M,fail,BAR)')],ns);x1=ns['x1_check']
def run(M):
  f=[];x1(M,lambda *a,**k:f.append(a),BAR);return f
def synth(xs):
  return dict(trans=[dict(a='A',b='B',start_bar=0,end_bar=16,xfader=xs)],decks=[
    dict(id='A',start_bar=-10,end_bar=16,auto={'gain':[[p[0],float(np.cos(p[1]*np.pi/2))] for p in xs]}),
    dict(id='B',start_bar=0,end_bar=40,auto={'gain':[[p[0],float(np.sin(p[1]*np.pi/2))] for p in xs]})])
def test_x1_passes_linear_equal_power():
  assert run(synth([[k/4,k/64] for k in range(65)]))==[]
def test_x1_fails_non_monotonic():
  xs=[[k/4,k/64] for k in range(65)];xs[30][1]=0.2
  assert run(synth(xs))
def test_x1_fails_steep_step():
  xs=[[0,0],[7.9,0],[8,1],[16,1]]
  assert run(synth(xs))
def test_x1_fails_extra_automation():
  M=synth([[k/4,k/64] for k in range(65)]);M['decks'][0]['auto']['voc']=[[4,1],[5,0.2]]
  assert run(M)
@pytest.mark.skipif(not os.path.exists(f'{SRC}/{NAME}_meta.json'),reason='mix meta missing')
def test_x1_on_mix():
  M=json.load(open(f'{SRC}/{NAME}_meta.json'))
  if M.get('engine')!='simple_crossfader':pytest.skip('legacy engine')
  assert run(M)==[]
