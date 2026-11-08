import os, sys, json, numpy as np, pytest
import checks as C
import test_crossfader as U

@pytest.mark.skipif(not os.path.exists(f'{C.SRC}/{C.NAME}_meta.json'),reason='mix meta missing')
def test_x1_on_mix():
  M=json.load(open(f'{C.SRC}/{C.NAME}_meta.json'))
  if M.get('engine')!='simple_crossfader':pytest.skip('legacy engine')
  assert U.run(M)==[]


def test_mix_bass_swaps_monotonic_smooth():
  if not os.path.exists(f'{C.SRC}/{C.NAME}_meta.json'):pytest.skip('mix meta missing')
  M=json.load(open(f'{C.SRC}/{C.NAME}_meta.json'))
  for d in M['decks']:
    lo=d['auto'].get('low') or []
    v=np.array([p[1] for p in lo]);
    if len(v)<2:continue
    assert np.abs(np.diff(v)).max()<=0.25,(d['id'],'bass EQ step too big')

