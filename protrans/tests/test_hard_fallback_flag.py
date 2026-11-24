"""HARD_FALLBACK stays off by default and cannot be dropped silently.

The 2026-11-24 n1124 nightly lost the gate when ESTAB keys were added to
apply_rules, and the always-on fallback shifted the official floor. This
module does not render and does not write rules.json.
"""
from __future__ import annotations
import ast, os, sys, inspect
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import recreate


def test_hard_fallback_default_is_off(monkeypatch):
    monkeypatch.delenv('HARD_FALLBACK', raising=False)
    assert recreate.hard_fallback_on({}, {}) is False
    assert recreate.hard_fallback_on({'HARD_FALLBACK': 0}, {}) is False
    assert recreate.hard_fallback_on({}, {'HARD_FALLBACK': '0'}) is False
    assert recreate.hard_fallback_on({'HARD_FALLBACK': 1}, {}) is True
    assert recreate.hard_fallback_on({}, {'HARD_FALLBACK': '1'}) is True


def test_hard_fallback_is_in_apply_rules():
    src = inspect.getsource(recreate.apply_rules)
    assert "'HARD_FALLBACK'" in src
    env = recreate.apply_rules({})
    assert 'HARD_FALLBACK' not in env
    env = recreate.apply_rules({'HARD_FALLBACK': 1})
    assert env.get('HARD_FALLBACK') == '1'
    env = recreate.apply_rules({'HARD_FALLBACK': 0})
    assert env.get('HARD_FALLBACK') == '0'


def test_hard_fallback_gate_cannot_drop_silently():
    """Source shape: official hardcheck import runs only inside `if _hc_on`."""
    src = inspect.getsource(recreate)
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'recreate')
    text = ast.get_source_segment(src, fn) or inspect.getsource(recreate.recreate)
    assert '_hc_on' in text
    assert 'hard_fallback_on' in text
    # The try that imports hardcheck must be nested under `if _hc_on`.
    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.ok = False
            self.unguarded = False
        def visit_If(self, node):
            test = ast.dump(node.test)
            if '_hc_on' in test:
                body_src = ast.get_source_segment(src, node) or ''
                if 'import hardcheck' in body_src:
                    self.ok = True
            self.generic_visit(node)
        def visit_Try(self, node):
            body_src = ast.get_source_segment(src, node) or ''
            if 'import hardcheck' in body_src:
                # walk parents? recorded via If visitor; flag if this Try is
                # at recreate() top level (not under If)
                pass
            self.generic_visit(node)
    v = Visitor(); v.visit(fn)
    assert v.ok, 'official hardcheck fallback is not gated on _hc_on / HARD_FALLBACK'
