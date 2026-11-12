"""Regression: FADE=long bass cover must not recreate Mix 08 long1g's X1/L1 failure.

Uses the real Mix 08 long-blend transition windows and xfaders (long1f, and long1g if present)
and the current fade_long.swap_before_thin + bass_lead to rebuild low lanes, then checks:
- xfader exists and is monotonic 0->1
- X1 bass-swap centre is in 0.2-0.65 and each low lane goes 1->0 / 0->1 inside the blend
- both low lanes are not fully up for more than 2 bars (the doubled-bass / L1 class)
- trans 12's handoff ends at or before Bad To Me's first thin bar (the long1f gap)
Does not render audio and does not import mix_simple (that would re-render)."""
import json, os, sys
import numpy as np
import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
SRC2 = os.path.join(ROOT, 'src2')
sys.path.insert(0, SRC2)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'src', 'tests'))
import fade_long as FL
import engine as E
import test_crossfader as X1

LONG1F = os.path.join(SRC2, 'mix08_long1f_meta.json')
LONG1G = os.path.join(SRC2, 'mix08_long1g_meta.json')
pytestmark = pytest.mark.skipif(not os.path.exists(LONG1F), reason='mix08_long1f meta missing')


def _wb(meta, i):
    t, dB = meta['trans'][i], meta['decks'][i + 1]
    s, e = int(t['start_bar']), int(t['end_bar'])
    fm, ds = dB['full_map'], dB['start_bar']
    return [fm[int(b - ds)][0] if 0 <= int(b - ds) < len(fm) else -1 for b in range(s, e)], s, e


def _first_thin(meta, i):
    t = meta['trans'][i]
    wb, s, e = _wb(meta, i)
    g = E.track(t['b'])['g']['bar']
    return FL.first_incoming_thin_bar(np.array(g['all'], float), np.array(g.get('low', g['all']), float), wb, e - s)


def _xpos_of(t):
    xs = np.asarray(t['xfader'], float)
    s, e = t['start_bar'], t['end_bar']
    X = e - s
    def xpos(u):
        return float(np.interp(s + u * X, xs[:, 0], xs[:, 1]))
    return xpos


def _ramp(c, up, w):
    return [[c - w / 2 + w * j / 16, float((1 - np.cos(np.pi * j / 16)) / 2 if up else (1 + np.cos(np.pi * j / 16)) / 2)] for j in range(17)]


def relane(meta):
    """Copy meta and rebuild every low lane from current swap_before_thin + bass_lead."""
    import copy
    M = copy.deepcopy(meta)
    for d in M['decks']:
        if 'auto' in d:
            d['auto']['low'] = []
    for i, t in enumerate(M['trans']):
        s, e = int(t['start_bar']), int(t['end_bar'])
        X, SW = e - s, float(t.get('swap_w') or 4)
        lead = FL.bass_lead(1.0, phrase=bool(t.get('swap_phrase')), fade=t.get('fade', 'long'))
        pos = (t['swap_bar'] - s) / X
        first = _first_thin(meta, i)
        pos = FL.swap_before_thin(X, pos, first, swap_w=SW, outgoing_lead=lead[0], incoming_lag=lead[1], xpos=_xpos_of(t))
        c = s + pos * X
        t['swap_bar'] = s + int(round(pos * X))
        if t.get('fade') == 'long' and not t.get('swap_phrase'):
            t['swap_ofs'] = 0.0
        t['bass_swap'] = [round(c - lead[0] - SW / 2, 3), round(c + lead[1] + SW / 2, 3)]
        at = t['swap_bar'] + t.get('swap_ofs', 0)
        M['decks'][i]['auto'].setdefault('low', []).extend(_ramp(at - lead[0], False, SW))
        M['decks'][i + 1]['auto'].setdefault('low', []).extend(_ramp(at + lead[1], True, SW))
    for d in M['decks']:
        lo = d.get('auto', {}).get('low') or []
        d['auto']['low'] = sorted(lo, key=lambda p: p[0])
    return M


def _doubled_bars(t, dA, dB):
    s, e = t['start_bar'], t['end_bar']
    bars = np.arange(s, e)
    def lv(d):
        lo = np.asarray(d['auto']['low'], float)
        return np.interp(bars + 0.5, lo[:, 0], lo[:, 1])
    a, b = lv(dA), lv(dB)
    return int(np.sum((a > 0.5) & (b > 0.5)))


def _check(M, label):
    assert all(len(t.get('xfader') or []) >= 2 for t in M['trans']), f'{label}: empty xfader'
    hits = X1.run(M)
    assert hits == [], f'{label} X1: {hits[:8]}'
    bad = []
    for i, t in enumerate(M['trans']):
        k = _doubled_bars(t, M['decks'][i], M['decks'][i + 1])
        if k > 2:
            bad.append((i, t['a'], t['b'], k, t['bass_swap']))
    assert not bad, f'{label} doubled bass >2 bars: {bad}'


def test_long1f_windows_replanned_pass_x1_and_do_not_double_bass():
    os.chdir(SRC2)
    raw = json.load(open(LONG1F))
    # recorded long1f already passed X1; the relaned copy is what a new render would write
    _check(relane(raw), 'long1f-relane')
    M = relane(raw)
    t = M['trans'][12]
    first = _first_thin(raw, 12)
    assert first >= 0
    assert t['bass_swap'][1] <= raw['trans'][12]['start_bar'] + first + 1e-9, (t['bass_swap'], first)
    # L1 blends 0 and 6 must keep the long1f swap (no thin incoming)
    for i in (0, 6):
        assert M['trans'][i]['swap_bar'] == raw['trans'][i]['swap_bar']
        assert M['trans'][i]['bass_swap'] == raw['trans'][i]['bass_swap']


@pytest.mark.skipif(not os.path.exists(LONG1G), reason='mix08_long1g meta missing')
def test_long1g_recorded_lanes_fail_x1_and_relane_repairs_them():
    """Pin the regression: the recorded long1g lanes are what we must not ship again."""
    os.chdir(SRC2)
    raw = json.load(open(LONG1G))
    hits = X1.run(raw)
    assert hits, 'expected recorded long1g to fail X1'
    _check(relane(raw), 'long1g-relane')
