"""PICKER_STYLE_GATED is a real rules flag, off by default. Does not write rules.json."""
from __future__ import annotations
import inspect, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import recreate


def test_picker_style_gated_default_off(monkeypatch):
    monkeypatch.delenv('PICKER_STYLE_GATED', raising=False)
    assert recreate.picker_style_gated_on({}, {}) is False
    assert recreate.picker_style_gated_on({'PICKER_STYLE_GATED': 1}, {}) is True
    src = inspect.getsource(recreate.apply_rules)
    assert "'PICKER_STYLE_GATED'" in src
    env = recreate.apply_rules({})
    assert 'PICKER_STYLE_GATED' not in env
    env = recreate.apply_rules({'PICKER_STYLE_GATED': 1})
    assert env.get('PICKER_STYLE_GATED') == '1'
