"""BASS_WAIT is off by default; apply_rules may pass it; it does not write rules.json."""
from __future__ import annotations
import inspect, json, os, pathlib, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'src2'))
import recreate
import bass_wait
import paths


def test_bass_wait_default_off(monkeypatch):
    monkeypatch.delenv('BASS_WAIT', raising=False)
    monkeypatch.delenv('BASS_WAIT_DB', raising=False)
    monkeypatch.delenv('BASS_WAIT_OFF', raising=False)
    assert bass_wait.on() is False
    monkeypatch.setenv('BASS_WAIT', '1')
    assert bass_wait.on() is True
    monkeypatch.setenv('BASS_WAIT_OFF', '1')
    assert bass_wait.on() is False
    monkeypatch.delenv('BASS_WAIT_OFF', raising=False)
    monkeypatch.delenv('BASS_WAIT', raising=False)
    src = inspect.getsource(recreate.apply_rules)
    assert "'BASS_WAIT'" in src and "'BASS_WAIT_DB'" in src
    assert 'BASS_WAIT' not in recreate.apply_rules({})
    assert recreate.apply_rules({'BASS_WAIT': 1}).get('BASS_WAIT') == '1'
    p = pathlib.Path(paths.RULES)
    before, mtime = p.read_bytes(), p.stat().st_mtime
    recreate.apply_rules({})
    recreate.apply_rules({'BASS_WAIT': 1})
    assert p.stat().st_mtime == mtime
    assert p.read_bytes() == before
    rules = json.loads(before)
    assert 'BASS_WAIT' not in rules
    assert rules.get('RIDEGATE') == 1


def _toy(cut0=8.0, w=4.0, start=0.0, end=16.0, arrived=12):
    """Incoming lows thin until `arrived`, then at body. Outgoing cut starts at cut0."""
    lo = np.full(32, -8.0)
    lo[:arrived] = -30.0  # thin until arrival; drop body ~ -8
    # full_map: mix bar k -> source bar k
    fm = [[k, 'mix'] for k in range(32)]
    dA = dict(id='A', start_bar=start, full_map=fm, auto={'low': [[cut0 - 2, 1], [cut0, 1], [cut0 + w, 0], [end, 0]]})
    dB = dict(id='B', start_bar=start, full_map=fm, auto={'low': []})
    t = dict(a='A', b='B', start_bar=start, end_bar=end, swap_w=w, bass_swap=[cut0, cut0 + w], notes=[])
    return [dA, dB], [t], {'B': lo}


def test_bass_wait_delays_outgoing_cut_until_incoming_present():
    decks, trans, lows = _toy(cut0=8.0, arrived=12)
    log = bass_wait.apply(decks, trans, lows.__getitem__, db=6.0)
    assert log[0]['wait'] is True
    assert trans[0]['bass_swap'][0] >= 11.5
    pts = decks[0]['auto']['low']
    # outgoing still at unity before the delayed cut
    import numpy as np
    g_at_9 = float(np.interp(9.0, [p[0] for p in pts], [p[1] for p in pts]))
    assert g_at_9 > 0.9


def test_bass_wait_skips_cut_when_incoming_never_arrives():
    decks, trans, lows = _toy(cut0=8.0, arrived=12)
    # Drop body lives far after the window+16 search, so nothing in-range is "present".
    lo = np.full(80, -30.0)
    lo[60:72] = -8.0
    lows['B'] = lo
    decks[1]['full_map'] = [[k, 'mix'] for k in range(80)]
    log = bass_wait.apply(decks, trans, lows.__getitem__, db=6.0,
                          secs_of=lambda _id: {'drops': [[60, 72]]})
    assert log[0]['wait'] is True
    assert trans[0]['bass_swap'] is None
    assert trans[0]['swap_w'] == 0.0
