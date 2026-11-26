"""Missing audio is not_evaluated, not a veto; CI uses only evaluable pairs."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'replica'))
import holdout_1126_live as H


def _pair(i, win=None, is_default=False):
    return dict(id=i, mix='m',
                ridegate=dict(win=win, is_default=is_default, exit=10, cue=1, X=16),
                default=dict(win=None, is_default=True, exit=10, cue=1, X=16),
                pro_out=10, pro_in=1)


def _row(win, hard_fail=False):
    return dict(win=win, fam='ridegate_live', hard=dict(hard_fail=hard_fail,
                beat_clash=False, bass_hole=False, pumping=False, incoming_vanish=False))


def test_missing_render_is_not_evaluated_not_veto():
    want = ['n', 32, None, 16, 16]
    pp = [_pair('a', want), _pair('b', is_default=True), _pair('c', want)]
    PF = {'c': _row(want, hard_fail=False)}
    DF = {'c': _row(['n', 16, None, 0, 16], hard_fail=False)}
    recs, cnt = H.classify_veto(pp, PF, DF)
    by = {r['id']: r for r in recs}
    assert by['a']['status'] == 'not_evaluated'
    assert by['a']['evaluable'] is False
    assert by['a']['veto'] is False
    assert by['b']['status'] == 'abstain' and by['b']['evaluable'] is True and by['b']['veto'] is False
    assert by['c']['status'] == 'checked' and by['c']['evaluable'] is True and by['c']['applied'] is True
    assert cnt['not_evaluated'] == 1
    assert cnt['evaluable'] == 2
    assert cnt['veto'] == 0
    assert cnt['moved'] == 2
    ev = [p for p in pp if by[p['id']]['evaluable']]
    assert [p['id'] for p in ev] == ['b', 'c']


def test_new_hard_fail_and_not_applied_are_vetoes_among_evaluable():
    w1, w2 = ['n', 32, None, 16, 16], ['n', 48, None, 16, 16]
    pp = [_pair('ok', w1), _pair('hf', w1), _pair('miss', w1), _pair('abs', is_default=True)]
    PF = {
        'ok': _row(w1, hard_fail=False),
        'hf': _row(w1, hard_fail=True),
        'miss': _row(w2, hard_fail=False),  # rendered a different window
    }
    DF = {k: _row(['n', 16, None, 0, 16], hard_fail=False) for k in ('ok', 'hf', 'miss')}
    recs, cnt = H.classify_veto(pp, PF, DF)
    by = {r['id']: r for r in recs}
    assert by['ok']['veto'] is False and by['ok']['evaluable'] is True
    assert by['hf']['new_hard_fail'] is True and by['hf']['veto'] is True and by['hf']['evaluable'] is True
    assert by['miss']['applied'] is False and by['miss']['veto'] is True and by['miss']['evaluable'] is True
    assert 'not_evaluated' not in (by['ok']['status'], by['hf']['status'], by['miss']['status'])
    assert cnt['veto'] == 2
    assert cnt['evaluable'] == 4  # 3 checked + 1 abstain
    assert cnt['not_evaluated'] == 0
    assert cnt['new_hard_fail'] == 1
    assert cnt['not_applied'] == 1


def test_eval_gate_tags_unique_per_full_variant():
    import eval_gate as E
    t1 = E.job_tag('n1126h_default', 0)
    t2 = E.job_tag('n1126h_ridegate_live', 0)
    assert t1 != t2
    assert t1 != E.job_tag('n1126h_default', 1)
    assert 'n1126h_default' in t1
    assert 'n1126h_ridegate_live' in t2
    # the old 4-char prefix collided
    assert not (t1[1:5] == t2[1:5] and t1 == t2)
