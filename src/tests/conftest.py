import pytest

@pytest.fixture
def audio_workspace(tmp_path, monkeypatch):
  """Independent, small source stems; caches and cwd never escape this test."""
  import importlib.util, pathlib, sys
  path = pathlib.Path(__file__).parent / 'fixtures' / 'generate.py'
  spec = importlib.util.spec_from_file_location('fixture_generate', path)
  gen = importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)
  gen.build(tmp_path)
  monkeypatch.syspath_prepend(str(pathlib.Path(__file__).resolve().parents[2] / 'src2'))
  import engine, beatmelody, beatstem
  monkeypatch.setattr(engine, '_cache', {})
  monkeypatch.setattr(engine, 'NUDGE', {})
  monkeypatch.setattr(beatmelody, '_D', {})
  monkeypatch.setattr(beatstem, '_G', {})
  monkeypatch.chdir(tmp_path)
  yield tmp_path
  # pytest retains temp directories across sessions; generated stems must not accumulate.
  import shutil
  engine._cache.clear(); beatmelody._D.clear(); beatstem._G.clear()
  shutil.rmtree(tmp_path)

@pytest.fixture
def synthetic_meta(audio_workspace):
  import numpy as np
  xs = [[k/4, k/64] for k in range(65)]
  decks = [dict(id=name, start_bar=0, end_bar=32,
       full_map=[[k, 'mix'] for k in range(32)], acap=False, echo=False,
       auto={'gain': [[x, float(np.cos(v*np.pi/2) if i==0 else np.sin(v*np.pi/2))]
                       for x,v in xs]})
       for i,name in enumerate(['fixture_out', 'fixture_in'])]
  return dict(bar_sec=240/174, decks=decks,
      trans=[dict(a='fixture_out', b='fixture_in', start_bar=0, end_bar=16, tech='blend')])
