"""Tempo regression: reject 124 BPM breaks pulses; accept 174/176 DnB pulses."""
import os, sys
import pytest
SRC2 = os.environ.get('MIX_SRC', '/workspace/mixes/src2')
sys.path.insert(0, SRC2)
import pbpm

@pytest.fixture(params=[124, 174, 176])
def probe(request, tmp_path):
  import importlib.util
  from pathlib import Path
  import soundfile as sf
  spec=importlib.util.spec_from_file_location('fixture_generate',Path(__file__).parent/'fixtures/generate.py')
  gen=importlib.util.module_from_spec(spec);spec.loader.exec_module(gen)
  p=tmp_path/'pulse.flac';sf.write(p,gen.pulse(request.param),gen.SR)
  yield request.param,p
  p.unlink()

def test_tempo_acceptance_and_rejection(probe):
  expected,path=probe
  bpm,meta=pbpm.analyze(str(path))
  if expected==124:
    assert not meta['ok'],meta
    with pytest.raises(ValueError):pbpm.pbpm(str(path))
  else:
    assert meta['ok'],meta
    assert abs(bpm-expected)<1,meta
