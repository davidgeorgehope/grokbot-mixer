"""Guards for the isolated corpus_v2 pipeline."""
from __future__ import annotations
import ast
import hashlib
import json
import os
import sys

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(HERE, 'protrans'))
import corpus_v2_pipeline as P
import version_match
import real_blend
import talkover
import paths


def test_quality_gates_unchanged():
    assert version_match.Z_MIN == 6.0
    assert version_match.CC_MIN == 0.28
    assert version_match.BPM_LO == 169.0
    assert version_match.BPM_HI == 179.0
    assert real_blend.MIN_BARS == 2.5
    assert real_blend.LEVEL_DB == -12.0
    assert talkover.TALK_MIN_S == 4.0


def test_goldilocks_slot_and_id_filters():
    tracks = [
        dict(t=0, title='Artist - One'),
        dict(t=100, title='Artist - Two'),          # 100s slot, keep
        dict(t=160, title='ID'),                     # ID, drop next
        dict(t=280, title='Artist - Three'),         # from ID, drop
        dict(t=400, title='Someone - Bootleg cut'),  # bootleg incoming from Three: 120s
        dict(t=520, title='Artist - Four'),          # from bootleg, drop
        dict(t=900, title='Artist - Far'),           # 380s hole, drop
    ]
    pairs = P.goldilocks_pairs(tracks, 't_mix', 'DJ', 'https://youtu.be/x', 'x')
    titles = [(p['a']['title'], p['b']['title']) for p in pairs]
    assert titles == [('Artist - One', 'Artist - Two')]
    assert all(90 <= p['t_b'] - p['t_a'] <= 280 for p in pairs)


def test_yearmix_titles_rejected():
    assert not P.title_ok('Liquicity Yearmix 2025')
    assert not P.title_ok('Best of 2024 Drum and Bass')
    assert P.title_ok('Hospital Podcast 452 with Whiney')
    assert P.title_ok('Hybrid Minds DJ Set — Live From London')


def test_legacy_ids_cover_official_33_mixes():
    # The six official scoring mixes must never be re-ingested or trained on.
    assert 'Ea4ngKLPNMQ' in P.LEGACY_VIDEO_IDS
    assert 'zgKc7vQNrrE' in P.LEGACY_VIDEO_IDS
    assert '0yIOFIW4Eow' in P.LEGACY_VIDEO_IDS
    assert 'PZ6aQYEIqm0' in P.LEGACY_VIDEO_IDS
    assert 'nNpy62IMI-A' in P.LEGACY_VIDEO_IDS
    assert 'ifOtJV-xZ-U' in P.LEGACY_VIDEO_IDS


def test_pipeline_does_not_write_official_files():
    src = open(os.path.join(HERE, 'protrans', 'corpus_v2_pipeline.py')).read()
    tree = ast.parse(src)
    # No calls to admit.save_admitted / drop_unused_sources / check_row (caches).
    banned = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in ('save_admitted', 'drop_unused_sources', 'apply_talkover',
                             'apply_real_blend', 'process_mix'):
                banned.add(node.attr)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == 'check_row':
                banned.add('check_row')
    assert not banned, banned
    assert 'results/admitted.json' not in src or 'PROTECTED' in src
    assert 'save_admitted' not in src
    assert paths.RULES in P.PROTECTED
    assert os.path.join(paths.RESULTS, 'admitted.json') in P.PROTECTED


def test_split_is_by_mix_and_holds_out_at_least_20_percent(tmp_path, monkeypatch):
    acc = tmp_path / 'accepted.jsonl'
    rows = []
    for m in range(10):
        for i in range(3):  # 3 transitions per mix; split must still be by mix
            rows.append(dict(id=f'mix{m:02d}__{i:02d}', mix_id=f'mix{m:02d}',
                             video_id=f'vid{m:02d}', dj='DJ'))
    acc.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
    split_p = tmp_path / 'split.json'
    monkeypatch.setattr(P, 'ACCEPTED', str(acc))
    monkeypatch.setattr(P, 'SPLIT', str(split_p))
    split = P.assign_split()
    assert split['by'] == 'mix'
    assert split['n_mixes'] == 10
    assert split['n_heldout_mixes'] / split['n_mixes'] >= 0.20
    # no mix appears in both sides
    assert set(split['train_mixes']).isdisjoint(split['heldout_mixes'])
    assert set(split['train_mixes']) | set(split['heldout_mixes']) == {f'mix{m:02d}' for m in range(10)}
    # deterministic
    split2 = P.assign_split()
    assert split2['heldout_mixes'] == split['heldout_mixes']


def test_official_files_currently_untouched():
    admitted = os.path.join(paths.RESULTS, 'admitted.json')
    rules = paths.RULES
    def sha(p):
        h = hashlib.sha256()
        h.update(open(p, 'rb').read())
        return h.hexdigest()
    assert sha(admitted) == '4097926166a808eb5c0ab245b4a0fca8decaa62a6d9b44790889cce823971d8e'
    assert sha(rules) == 'fc727b3c734b363ebd7c99e2e56d8df019b5ec2dff7b069bd5c5d8e0caff7109'
    rows = json.load(open(admitted))
    assert len(rows) == 33
