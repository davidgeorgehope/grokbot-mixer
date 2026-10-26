"""Guardrails (src/guardrails.py) must report zero failures for the mix under test, and must still FAIL the
v1 render of dj-mix-03-60 at every spot the listener rated bad (regression against eval/example_ratings.jsonl)."""
import json,os,checks as C
FIX=os.path.join(os.path.dirname(__file__),'fixtures','guardrails_dj-mix-03-60_v1_rated.json')
sec=lambda t:int(t.split(':')[0])*60+int(t.split(':')[1])
def test_guardrails_zero_failures():
  p=f'{C.SRC}/guard_{C.NAME}/guardrails.json';assert os.path.exists(p),'run src/guardrails.py first (render_and_test4.sh does)'
  g=json.load(open(p));assert g['mix']==C.NAME
  assert g['n_fail']==0,[(f['check'],f['t'],f['msg']) for f in g['failures']][:25]
def test_guardrails_catch_listener_bad_spots():
  g=json.load(open(FIX))
  for t0,t1,what in [(13*60,14*60+40,'Deeper -> Just Hold On (horrible)'),(32*60,33*60+10,'Surrender -> Come Together stop-start'),(36*60,39*60+30,'In The Shadows fade -> Saviour (weird)')]:
    hits=[f for f in g['failures'] if t0<=f['sec']<=t1 or t0<=sec(f['t_end'])<=t1]
    assert hits,f'guardrails missed {what}'
