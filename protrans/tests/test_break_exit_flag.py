"""BREAK_EXIT nominates drop-1-end / gap-end exits; off by default; does not force a pick."""
from __future__ import annotations
import inspect, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import recreate


def test_break_exit_default_off(monkeypatch):
    monkeypatch.delenv('BREAK_EXIT', raising=False)
    assert recreate.break_exit_on({}, {}) is False
    assert recreate.break_exit_on({'BREAK_EXIT': 1}, {}) is True
    src = inspect.getsource(recreate.apply_rules)
    assert "'BREAK_EXIT'" in src
    assert 'BREAK_EXIT' not in recreate.apply_rules({})
    assert recreate.apply_rules({'BREAK_EXIT': 1}).get('BREAK_EXIT') == '1'


def test_lsb_optimist_anchors():
    # ksVDZt9_0J4: drop 1 ends 128, next drop starts 176 (breakdown fills the gap).
    # Pro labels are not inputs.
    import os
    os.chdir('/workspace/mixes/src2')
    assert recreate.break_exit_anchors('ksVDZt9_0J4') == [128, 176]


def test_add_break_exit_families_does_not_replace_existing():
    cs = [
        dict(fam='n', win=['n', 256, None, 32, 16], cost=1.0),
        dict(fam='n', win=['n', 160, None, 32, 32], cost=5.0),  # out_bar=129, near 128
        dict(fam='n', win=['n', 192, None, 16, 16], cost=4.0),  # out_bar=177, near 176
    ]
    fams = [dict(fam='nat_short', win=['n', 256, None, 32, 16], env={})]
    off = recreate.add_break_exit_families(fams, cs, 'unused', enabled=False)
    assert off == fams
    # fake anchors
    def fake(_yt):
        return [128, 176]
    recreate.break_exit_anchors, old = fake, recreate.break_exit_anchors
    try:
        on = recreate.add_break_exit_families(list(fams), cs, 'x', enabled=True)
    finally:
        recreate.break_exit_anchors = old
    wins = [c['win'] for c in on if c.get('fam') == 'break_exit']
    assert ['n', 160, None, 32, 32] in wins
    assert ['n', 192, None, 16, 16] in wins
    assert on[0]['fam'] == 'nat_short'  # default family still first; pick is not forced
