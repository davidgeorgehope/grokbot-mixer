"""LEVEL_COMP is a research incoming-fader pull-forward; off by default; apply_rules may pass it."""
from __future__ import annotations
import inspect, json, os, pathlib, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src2'))
import recreate
import level_comp
import paths


def test_level_comp_default_off(monkeypatch):
    monkeypatch.delenv('LEVEL_COMP', raising=False)
    monkeypatch.delenv('LEVEL_COMP_TRIG', raising=False)
    monkeypatch.delenv('LEVEL_COMP_CAP', raising=False)
    assert level_comp.on() is False
    monkeypatch.setenv('LEVEL_COMP', '1')
    assert level_comp.on() is True
    monkeypatch.delenv('LEVEL_COMP', raising=False)
    src = inspect.getsource(recreate.apply_rules)
    assert "'LEVEL_COMP'" in src and "'LEVEL_COMP_TRIG'" in src and "'LEVEL_COMP_CAP'" in src
    assert 'LEVEL_COMP' not in recreate.apply_rules({})
    assert recreate.apply_rules({'LEVEL_COMP': 1}).get('LEVEL_COMP') == '1'
    p = pathlib.Path(paths.RULES)
    before, mtime = p.read_bytes(), p.stat().st_mtime
    recreate.apply_rules({})
    recreate.apply_rules({'LEVEL_COMP': 1})
    assert p.stat().st_mtime == mtime
    assert p.read_bytes() == before
    rules = json.loads(before)
    assert 'LEVEL_COMP' not in rules
    assert rules.get('RIDEGATE') == 1
