"""n1127 card loads, flags stay off, and linger/lag reporting is wired."""
import json, os, sys, pathlib
HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'replica'))
import nightly_card as NCard
import nightly_hill_climb as HC
import recreate
import inspect


def test_n1127_card_loads_and_flags_stay_off():
    info = NCard.validate(tag='n1127')
    assert info['arms'] == [
        'epg_strict', 'epg_drop', 'epg_stack',
        'ridegate_lock_pump_ee', 'profade_ex35',
    ]
    assert 1 <= len(info['short_tags']) <= 6
    assert len(set(info['short_tags'])) == len(info['short_tags'])
    spec = NCard.load_spec()
    assert spec.get('adopt_to_defaults') is False
    # n1126 card is preserved and is what a 11-26 hill-climb would still read
    n1126 = [c['name'] for c in NCard.card_for('n1126', spec)]
    assert n1126 == [
        'epg_strict', 'epg_drop', 'epg_stack',
        'djbal_cue_struct_compat', 'early_exit', 'ee_r7',
    ]
    # hill_climb date card
    names = [n for n, _ in HC.candidates('n1127')]
    assert names == info['arms']
    names26 = [n for n, _ in HC.candidates('n1126')]
    assert names26 == n1126
    assert 'ridegate_lock_pump' not in info['arms']  # now the baseline, not a shadow
    assert HC._short_tag('n1127', 'ridegate_lock_pump_ee') != HC._short_tag('n1127', 'profade_ex35')


def test_n1127_shadow_deltas_and_rules_untouched():
    card = {c['name']: c for c in NCard.card_for('n1127')}
    assert card['ridegate_lock_pump_ee']['shadow'] is True
    assert card['ridegate_lock_pump_ee']['promotion'] is False
    assert card['ridegate_lock_pump_ee']['delta'] == {'RIDEGATE_EE': 1}
    ex = card['profade_ex35']['delta']
    assert ex['PRO_FADE'] == 1 and ex['PRO_FADE_EXIT_SLOPE'] == 3.5
    assert ex['PRO_FADE_RESPECT_EXIT'] == 1
    assert ex['PICKER_STYLE_GATED_MAP'] == 'replica/picker_early_exit_r7_windows.json'
    src = inspect.getsource(recreate.apply_rules)
    for k in list(card['ridegate_lock_pump_ee']['delta']) + list(ex):
        assert f"'{k}'" in src
    env = recreate.apply_rules({})
    # New engine default is on; EE / linger / pro-fade stay off.
    assert recreate._flag_on(env.get('RIDEGATE'))
    assert recreate._flag_on(env.get('RIDEGATE_LOCK'))
    assert recreate._flag_on(env.get('RIDEGATE_PUMP'))
    for k in ('RIDEGATE_EE', 'LINGER_GUARD', 'PRO_FADE', 'EARLY_EXIT'):
        assert not recreate._flag_on(env.get(k))
    import paths
    rules = json.loads(pathlib.Path(paths.RULES).read_bytes())
    assert rules.get('RIDEGATE') == 1 and rules.get('RIDEGATE_LOCK') == 1 and rules.get('RIDEGATE_PUMP') == 1
    assert 'RIDEGATE_EE' not in rules and 'LINGER_GUARD' not in rules
    assert 'PRO_FADE' not in rules


def test_linger_lag_report_fields():
    rows = [
        dict(id='toy_a', pick={'win': ['n', 176, None, 32, 16]}),
        dict(id='toy_b', pick={'win': ['n', 128, None, 8, 16]}),
    ]
    # no built rows / no pro ids: still returns the two summary keys
    out = NCard.summarize_linger_and_lag(rows, built_by_id={})
    assert 'drum_linger_bars' in out and 'exit_lag_vs_pro' in out
    assert 'pairs' in out
    # known lag when pro out bar is supplied via the pair helper
    rec = NCard.pair_linger_lag(rows[0], pro=97.1)
    assert rec['exit_start'] == 161
    assert rec['exit_lag'] == 63.9
    # empty / default summaries have n=0, not missing keys
    empty = NCard.summarize_linger_and_lag([])
    assert empty['exit_lag_vs_pro']['n'] == 0
    assert empty['drum_linger_bars']['n'] == 0
