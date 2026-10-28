"""pbpm must accept real ~174 DnB and reject the 124 BPM UK-breaks original Just Hold On."""
import os, sys
import pytest
SRC2 = os.environ.get('MIX_SRC', '/workspace/mixes/src2')
sys.path.insert(0, SRC2)
import pbpm

JHO_BREAKS = f'{SRC2}/wav/_K2sC9nrf_A.wav'   # Sub Focus & Wilkinson original, 124 BPM breaks
DEEPER = f'{SRC2}/wav/F1NCnCxyhqc.wav'         # Kanine & Raphaella – Deeper, 174 DnB
JHO_REMIX = f'{SRC2}/wav/cxS6yd0UAxw.wav'       # Pola & Bryson remix, 174 DnB (may be absent in older checkouts)

@pytest.mark.skipif(not os.path.exists(JHO_BREAKS), reason='breaks wav missing')
def test_rejects_just_hold_on_breaks_original():
  bpm, meta = pbpm.analyze(JHO_BREAKS)
  assert not meta['ok'], meta
  assert 'break' in meta['reason'] or 'reject' in meta['reason']
  with pytest.raises(ValueError):
    pbpm.pbpm(JHO_BREAKS)

@pytest.mark.skipif(not os.path.exists(DEEPER), reason='Deeper wav missing')
def test_accepts_deeper_dnb():
  bpm, meta = pbpm.analyze(DEEPER)
  assert meta['ok'], meta
  assert 170 <= bpm <= 178

@pytest.mark.skipif(not os.path.exists(JHO_REMIX), reason='Pola & Bryson remix wav not prepped yet')
def test_accepts_just_hold_on_pola_bryson_remix():
  bpm, meta = pbpm.analyze(JHO_REMIX)
  assert meta['ok'], meta
  assert 170 <= bpm <= 178
