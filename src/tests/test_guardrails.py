"""Guardrails (src/guardrails.py) must report zero failures for the mix under test, and must still FAIL the
v1 render of dj-mix-03-60 at every spot the listener rated bad (regression against eval/example_ratings.jsonl).
R1/T1 must catch the 124 BPM UK-breaks Just Hold On when that deck is present; the Pola & Bryson 174
remix (cxS6yd0UAxw) is the fix and must not trip them."""
import json,os,checks as C
FIX=os.path.join(os.path.dirname(__file__),'fixtures','guardrails_dj-mix-03-60_v1_rated.json')
sec=lambda t:int(t.split(':')[0])*60+int(t.split(':')[1])
def test_guardrails_zero_failures():
  p=f'{C.SRC}/guard_{C.NAME}/guardrails.json';assert os.path.exists(p),'run src/guardrails.py first (render_and_test.sh does)'
  g=json.load(open(p));assert g['mix']==C.NAME
  assert g['n_fail']==0,[(f['check'],f['t'],f['msg']) for f in g['failures']][:25]
def test_guardrails_catch_listener_bad_spots():
  g=json.load(open(FIX))
  for t0,t1,what in [(13*60,14*60+40,'Deeper -> Just Hold On (horrible)'),(32*60,33*60+10,'Surrender -> Come Together stop-start'),(36*60,39*60+30,'In The Shadows fade -> Saviour (weird)')]:
    hits=[f for f in g['failures'] if t0<=f['sec']<=t1 or t0<=sec(f['t_end'])<=t1]
    assert hits,f'guardrails missed {what}'
  # If the current mix still uses the 124 BPM breaks original, R1/T1 must fail it.
  cur=f'{C.SRC}/guard_{C.NAME}/guardrails.json'
  assert os.path.exists(cur),'run src/guardrails.py on the current mix first'
  g2=json.load(open(cur))
  meta=json.load(open(f'{C.SRC}/{C.NAME}_meta.json'))
  ids={d['id'] for d in meta['decks']}
  if '_K2sC9nrf_A' in ids:
    hits=[f for f in g2['failures'] if f['check'] in ('R1','T1') and '_K2sC9nrf_A' in f.get('msg','')]
    assert hits,f'R1/T1 missed breaks-original Just Hold On on {C.NAME}'
    assert any(f['check']=='R1' for f in hits)
  if 'cxS6yd0UAxw' in ids:
    # T1 must not reject the 174 remix; R1 on its *entry* from Deeper must be clean (the car-crash spot).
    t1=[f for f in g2['failures'] if f['check']=='T1' and 'cxS6yd0UAxw' in f.get('msg','')]
    assert not t1,f'Pola & Bryson remix incorrectly failed T1: {t1}'
    r1_in=[f for f in g2['failures'] if f['check']=='R1' and 'F1NCnCxyhqc vs cxS6yd0UAxw' in f.get('msg','')]
    assert not r1_in,f'Deeper -> Pola & Bryson remix still R1-fails (car crash not fixed): {r1_in}'
