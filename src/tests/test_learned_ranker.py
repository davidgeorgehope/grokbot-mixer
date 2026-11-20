"""Guards for the v0 learned ranker: flag off by default, no official-file writes,
features do not include pro-choice labels, backup excludes corpus runtime state.
"""
from __future__ import annotations
import ast
import hashlib
import os
import sys

import numpy as np

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(HERE, 'src2'))
sys.path.insert(0, os.path.join(HERE, 'protrans'))
import learned_ranker as LR
import recreate
import paths


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv('RANKER', raising=False)
    assert LR.flag_on() is False
    assert LR.flag_on('0') is False
    assert LR.flag_on('') is False
    assert LR.flag_on('1') is True


def test_option_vec_has_no_pro_labels():
    sa = dict(n_bars=200, music_end=200, intro_end=16, drop1=16, breakdown=80,
              drop2=112, outro_start=176, drops=[[16, 80], [112, 176]],
              phases=[{'name': 'intro', 'start': 0, 'end': 16},
                      {'name': 'drop', 'start': 16, 'end': 80},
                      {'name': 'breakdown', 'start': 80, 'end': 112},
                      {'name': 'drop', 'start': 112, 'end': 176},
                      {'name': 'outro', 'start': 176, 'end': 200}],
              n_drops=2)
    sb = dict(sa)
    opt = dict(type='outro_intro', win=['n', 192, None, 16, 16],
               snap_in=False, snap_in_hold=0, tail_exit=6, fade='long')
    x = LR.option_vec(sa, sb, opt)
    assert len(x) == len(LR.FEATURE_NAMES)
    # feature names must describe the tracks / window, never the pro cue
    banned = ('delta_bars', 'pro_', 'label', 'relevance', 'incoming_section_pro')
    assert all(b not in n for n in LR.FEATURE_NAMES for b in banned)


def test_relevance_prefers_closer_cue():
    pro = dict(incoming_bar=16, outgoing_bar=192, incoming_section='intro',
               outgoing_section='outro', want_snap=False, want_hold=False, tail_bars=30)
    close = dict(type='outro_intro', win=['n', 192, None, 16, 16],
                 snap_in=False, snap_in_hold=0, tail_exit=0, fade='long')
    far = dict(type='breakdown_drop', win=['n', 80, None, 96, 16],
               snap_in=True, snap_in_hold=16, tail_exit=6, fade='long')
    assert LR.relevance(close, pro) > LR.relevance(far, pro)


def test_apply_rules_passes_ranker_and_default_rules_unchanged():
    env = recreate.apply_rules({'RANKER': 1, 'FADE': 'long'})
    assert env.get('RANKER') == '1'
    env2 = recreate.apply_rules({'ranker': 0})
    assert env2.get('RANKER') == '0'
    env3 = recreate.apply_rules({})
    assert 'RANKER' not in env3
    # official rules.json is unchanged (BLEND_LOCK still the default, no RANKER key)
    rules = __import__('json').load(open(paths.RULES))
    assert 'RANKER' not in rules and 'ranker' not in rules
    assert int(rules.get('BLEND_LOCK') or 0) == 1
    sha = hashlib.sha256(open(paths.RULES, 'rb').read()).hexdigest()
    assert sha == 'ab435c6af95499056936978adc9fcea1d4e3bfb4c5af00795ff396dd5cccfef8'


def test_sections_from_bar_accepts_ndarray():
    import corpus_v2_pipeline as P
    rng = np.random.default_rng(0)
    drums = rng.normal(-20, 5, 128)
    drums[32:80] = -8
    drums[96:120] = -8
    bass = drums + rng.normal(0, 1, 128)
    sec = P.sections_from_bar(dict(drums=drums, bass=bass, n=128))
    assert sec['n_bars'] == 128
    assert sec['n_drops'] >= 1
    assert 'phases' in sec


def test_backup_excludes_corpus_runtime_state():
    script = open('/workspace/backup_mixer_to_git.sh').read()
    for name in ('queue.json', 'progress.json', 'work/', 'meta_cache/',
                 'accepted.jsonl', 'rejected.jsonl', 'feat_lib/'):
        assert f'protrans/corpus_v2/{name}' in script, name
    gi = open(os.path.join(HERE, '.gitignore')).read()
    assert 'protrans/corpus_v2/queue.json' in gi
    assert 'protrans/corpus_v2/progress.json' in gi
    pub = open('/workspace/publish_mixer_public.sh').read()
    assert 'queue.json' in pub


def test_slowpair_features_do_not_change_v0_width():
    sa = dict(drops=[[48, 112], [144, 192]], music_end=235, drop1=48, n_bars=235, intro_end=40, outro_start=198)
    sb = dict(drops=[[64, 128]], music_end=224, drop1=64, n_bars=224, intro_end=64)
    opt = dict(type='outro_intro', win=['n', 224, None, 48, 16], snap_in=False, tail_exit=6, fade='long')
    x = LR.option_vec(sa, sb, opt)
    assert len(x) == len(LR.FEATURE_NAMES)
    # Ghetto Blaster-shaped outgoing hard outro
    import slowpair as S
    a_sp = S.hard_spans(slow=[[198, 235]], ht=[], sec=sa)
    v = LR.slowpair_vec(opt['win'], a_sp, [], sa)
    assert len(v) == len(LR.SLOWPAIR_FEATURE_NAMES)
    d = LR.slowpair_feature_dict(opt['win'], a_sp, [], sa)
    assert d['sp_case_a'] == 1.0 and d['sp_case_b'] == 0.0
    assert d['sp_out_start_inside'] == 1.0
    ext = LR.option_vec_with_slowpair(sa, sb, opt, a_spans=a_sp, b_spans=[])
    assert len(ext) == len(LR.FEATURE_NAMES) + len(LR.SLOWPAIR_FEATURE_NAMES)
    assert ext[:len(x)] == x

