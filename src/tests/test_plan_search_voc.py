"""Mix 10 r4: the cached pair table must not keep pre-vocfix V=0 after a track
gains real bar.voc, and the planner V term must use the same audibility
thresholds as the dry vocal test (checks.vocal_bars: 12 dB below p95, gain>0.3)."""
import json, os, sys
import numpy as np
import pytest

sys.path.insert(0, '/workspace/mixes/src2')
import plan_search as PS
import checks as C


def test_feat_sig_changes_when_voc_appears(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  st = tmp_path / 'st'
  st.mkdir()
  n = 32
  body = dict(all=[-20.0] * n, low=[-22.0] * n, hat=[-40.0] * n, drums=[-24.0] * n, bass=[-22.0] * n)
  json.dump(dict(bar=dict(body)), open(st / 't1.json', 'w'))
  a = PS._feat_sig(['t1'])
  assert a[0][1] == 'no_voc'
  voc = [-80.0] * 16 + [-22.0] * 16
  json.dump(dict(bar=dict(body, voc=voc)), open(st / 't1.json', 'w'))
  b = PS._feat_sig(['t1'])
  assert b[0][1] == 'voc' and b != a


def test_table_key_includes_feat_sig(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  (tmp_path / 'st').mkdir()
  base = tmp_path / 'base.json'
  json.dump([{'id': 't1'}], open(base, 'w'))
  # table_key also stats source files in cwd; stub the ones it mtimes
  for name in ('mix_simple.py', 'cue_model.json', 'pair_feats.py', 'plan_search.py'):
    (tmp_path / name).write_text('')
  n = 16
  json.dump(dict(bar=dict(all=[-20]*n, drums=[-24]*n)), open(tmp_path / 'st' / 't1.json', 'w'))
  k0 = PS.table_key(str(base), ids=['t1'])
  json.dump(dict(bar=dict(all=[-20]*n, drums=[-24]*n, voc=[-80]*8+[-20]*8)), open(tmp_path / 'st' / 't1.json', 'w'))
  k1 = PS.table_key(str(base), ids=['t1'])
  assert k0 != k1 and '_feat_sig' or True
  assert k0 != k1


def test_vocal_xfade_matches_checks_thresholds():
  assert C.VOC_REL_DB == 12 and C.VOC_GAIN == 0.3
  # 16-bar equal-power blend: both faders exceed 0.3 on k=4..11
  X = 16
  vA = np.full(32, -80.0); vB = np.full(32, -80.0)
  # loud vocal only on outgoing bars 20-27 and incoming 4-11 (the overlap of the window)
  wa = list(range(16, 32)); wb = list(range(0, 16))
  vA[20:28] = -22.0
  vB[4:12] = -22.0
  rvA, rvB = -22.0, -22.0
  n = PS.vocal_xfade_count(vA, rvA, wa, vB, rvB, wb)
  assert n == 8  # k=4..11
  # no overlap: incoming vocal only at the start (gb<=0.3)
  vB[:] = -80.0
  vB[0:3] = -22.0
  assert PS.vocal_xfade_count(vA, rvA, wa, vB, rvB, wb) == 0


def test_r4_afterglow_windows_are_vocal_on_current_features():
  """The two r4 dry-failing windows must not score V=0 once Afterglow has real voc.
  Skips if the production stems are not on this box."""
  src = '/workspace/mixes/src2'
  paths = [f'{src}/st/q_IuTV23x7Q.json', f'{src}/st/I9QGpHScGug.json', f'{src}/st/SqzxwPEa-DI.json']
  if not all(os.path.exists(p) for p in paths):
    pytest.skip('crate stems not present')
  def load(b):
    v = np.array(json.load(open(f'{src}/st/{b}.json'))['bar']['voc'], float)
    return v, float(np.percentile(v, 95))
  cases = [
    ('q_IuTV23x7Q', 'I9QGpHScGug', ['n', 208, None, 16, 16]),
    ('I9QGpHScGug', 'SqzxwPEa-DI', ['la', 112, 96, 64, 16]),
  ]
  for a, b, w in cases:
    if 'voc' not in json.load(open(f'{src}/st/{a}.json'))['bar'] or 'voc' not in json.load(open(f'{src}/st/{b}.json'))['bar']:
      pytest.skip(f'missing voc on {a} or {b}')
    kind, e, p, ib, X = w
    wa, wb = PS.windows(kind, e, p, ib, X)
    vA, rvA = load(a); vB, rvB = load(b)
    n = PS.vocal_xfade_count(vA, rvA, wa, vB, rvB, wb)
    assert n >= 1, f'{a}>{b} {w} scored V={n} after vocfix; r4 dry failed this window'
