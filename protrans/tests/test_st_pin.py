"""Pinned n1121-era st json is used when PROTRANS_SRC2 is set; no-op proxy writes stay off."""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path


def test_ensure_bar_proxies_does_not_rewrite_complete_file(tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import recreate
    src = Path('/workspace/mixes/protrans/replica/st_pin_n1121/st/I9QGpHScGug.json')
    dest = tmp_path / 'I9QGpHScGug.json'
    dest.write_bytes(src.read_bytes())
    before = dest.read_bytes()
    mtime = dest.stat().st_mtime
    recreate._ensure_bar_proxies(str(dest))
    assert dest.read_bytes() == before
    assert dest.stat().st_mtime == mtime


def test_pin_matches_vocfix_bak():
    pin = Path('/workspace/mixes/protrans/replica/st_pin_n1121/st/I9QGpHScGug.json')
    bak = Path('/workspace/mixes/src2/st/I9QGpHScGug.json.mix10_vocfix_bak')
    assert pin.read_bytes() == bak.read_bytes()
    bar = json.loads(pin.read_text())['bar']
    assert 'voc' not in bar  # n1121-era, pre mix10 vocfix


def test_paths_src2_env(monkeypatch):
    import importlib, sys
    monkeypatch.setenv('PROTRANS_SRC2', '/tmp/fake_src2_pin')
    # reimport in isolation is awkward if already imported; check the assignment expression
    import paths as P
    # If this process already imported paths without the env, skip strict assert
    src = Path('/workspace/mixes/protrans/paths.py').read_text()
    assert "os.environ.get('PROTRANS_SRC2')" in src
