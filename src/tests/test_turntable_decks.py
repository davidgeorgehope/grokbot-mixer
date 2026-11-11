"""Twin-turntable visual: the playing record never changes decks, and decks alternate A/B/A/B.

Mix 08 v2 showed the bug: at every segment cut (midway between two blends) the record that had just
taken over on deck B jumped to deck A, because build_segs.py always put the outgoing track on deck A.
"""
import copy, json, os, subprocess, sys
import pytest

TT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'visuals', 'code', 'turntable_viz'))
sys.path.insert(0, TT)
import deck_state as ds  # noqa: E402

MIX08_META = '/workspace/mixes/src2/mix08_r11c_meta.json'


def synth_meta(n_tracks=6, bar_sec=1.38, track_bars=160, blend=32):
    """n tracks of track_bars each; every blend is the last `blend` bars of the outgoing track."""
    decks = [dict(id=f'trk{k:02d}', start_bar=k * (track_bars - blend), full_map=[[j, 1.0] for j in range(track_bars)], auto={})
             for k in range(n_tracks)]
    trans = [dict(a=decks[k - 1]['id'], b=decks[k]['id'], start_bar=decks[k]['start_bar'],
                  end_bar=decks[k]['start_bar'] + blend, xfader=[]) for k in range(1, n_tracks)]
    return dict(bar_sec=bar_sec, decks=decks, trans=trans, len_sec=(decks[-1]['start_bar'] + track_bars) * bar_sec)


def build(meta, tmp_path):
    mp = tmp_path / 'meta.json'; mp.write_text(json.dumps(meta))
    out = tmp_path / 'segs'
    subprocess.run([sys.executable, os.path.join(TT, 'build_segs.py'), str(mp), '/nonexistent.mp3', str(out)],
                   check=True, capture_output=True, text=True)
    S = json.load(open(out / 'segs.json'))
    return [json.load(open(s['timing'])) for s in S['segs']]


def test_slots_alternate():
    m = synth_meta()
    assert ds.assign_slots(m) == [0, 1, 0, 1, 0, 1]


def test_walk_plan_record_never_changes_deck(tmp_path):
    tims = build(synth_meta(), tmp_path)
    assert ds.walk_segments(tims) == []
    # per segment: deck A always holds an even track, deck B an odd one
    for t in tims:
        ids = [d['id'] for d in t['decks']]
        assert int(ids[0][3:]) % 2 == 0 and int(ids[1][3:]) % 2 == 1, ids
        assert t['titles']['deck'][t['out_deck']] == t['titles']['out']


def test_walker_catches_mix08_bug(tmp_path):
    """The old layout (outgoing always on deck A) must be flagged at the first cut."""
    tims = build(synth_meta(), tmp_path)
    legacy = copy.deepcopy(tims)
    for t in legacy:
        if t['out_deck'] == 1:
            t['decks'] = t['decks'][::-1]
    errs = ds.walk_segments(legacy)
    assert any('lives on deck' in e for e in errs), errs


def test_fx_windows_never_move_a_playing_record(tmp_path):
    tims = build(synth_meta(), tmp_path)
    assert any('spin_in' in (t.get('fx') or {}) for t in tims)
    assert any('fly_off' in (t.get('fx') or {}) for t in tims)
    for t in tims:
        for w in (t.get('fx') or {}).values():
            d = next(x for x in t['decks'] if x['id'] == w['id'])
            assert t['decks'].index(d) == w['deck']          # FX act on the record's own deck


def test_three_records_at_once_is_rejected():
    m = synth_meta()
    m['decks'][2]['start_bar'] = m['decks'][0]['start_bar'] + 10   # track 2 starts while track 0 still plays
    with pytest.raises(ValueError):
        ds.assign_slots(m)


@pytest.mark.skipif(not os.path.exists(MIX08_META), reason='Mix 08 meta not on this box')
def test_mix08_plan_with_fix(tmp_path):
    tims = build(json.load(open(MIX08_META)), tmp_path)
    assert len(tims) == 25
    assert ds.walk_segments(tims) == []
    assert [t['out_deck'] for t in tims] == [i % 2 for i in range(25)]
