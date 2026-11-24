"""Mix 10 r5: planner must reject an outgoing energy cliff at blend entry (guardrail N1).
The +3.8 dB master step at 18:45 was Strings Of Life bar 79 dropping 12.9 dB before
Just Hold On entered; a 7.1 dB cliff on the same mix (City Life -> Deeper) rendered clean.
ENTRY_CLIFF_DB=8 is that split. Does not change guardrail N1_db=3.83.
"""
import json, os, sys
import numpy as np
import pytest

sys.path.insert(0, '/workspace/mixes/src2')
import plan_search as PS

def test_entry_cliff_db_default():
  assert PS.ENTRY_CLIFF_DB == 8

def test_entry_prev_matches_entry_step_rule():
  # lb / n: prev is the bar before the outgoing window start
  wa, _ = PS.windows('lb', 112, None, 80, 32)
  assert wa[0] == 80 and PS.entry_prev('lb', 112, wa) == 79
  wa, _ = PS.windows('n', 176, None, 16, 32)
  assert PS.entry_prev('n', 176, wa) == wa[0] - 1
  # looped outgoing: prev is the real exit bar minus one
  assert PS.entry_prev('la', 176, [160]) == 175

def test_r5_n1_window_is_an_entry_cliff():
  """Strings Of Life -> Just Hold On lb 112/80/32, the r5 N1 fail."""
  src = '/workspace/mixes/src2/st/AC3eEHeLd8A.json'
  if not os.path.exists(src):
    pytest.skip('crate stems not present')
  al = np.array(json.load(open(src))['bar']['all'], float)
  wa, _ = PS.windows('lb', 112, None, 80, 32)
  cliff = PS.entry_cliff(al, PS.entry_prev('lb', 112, wa))
  assert cliff > PS.ENTRY_CLIFF_DB, f'expected Strings bar 79 cliff > {PS.ENTRY_CLIFF_DB}, got {cliff}'

def test_r5_citylife_deeper_cliff_is_under_the_cap():
  """City Life -> Deeper had a 7.1 dB pre-entry dip and did not fail N1."""
  src = '/workspace/mixes/src2/st/HpfQ0bus688.json'
  if not os.path.exists(src):
    pytest.skip('crate stems not present')
  al = np.array(json.load(open(src))['bar']['all'], float)
  # r5: City Life out_win n,192,None,48,32 -> wa starts at 160, prev=159
  wa, _ = PS.windows('n', 192, None, 48, 32)
  cliff = PS.entry_cliff(al, PS.entry_prev('n', 192, wa))
  assert cliff <= PS.ENTRY_CLIFF_DB, f'City Life prev=159 should stay under the cap, got {cliff}'

def test_r5_meta_plan_entry_cliffs_flags_the_n1_blend():
  meta = '/workspace/mixes/src2/mix10_r5_meta.json'
  if not os.path.exists(meta):
    pytest.skip('r5 meta not present')
  M = json.load(open(meta))
  cliffs = PS.plan_entry_cliffs(M)
  pairs = {(c['a'], c['b']) for c in cliffs}
  assert ('AC3eEHeLd8A', 'cxS6yd0UAxw') in pairs
  # City Life -> Deeper must not be flagged
  assert ('HpfQ0bus688', 'F1NCnCxyhqc') not in pairs
