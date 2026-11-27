"""n1128 card loads the skipped n1127 shadows and is what the launcher renders."""
import json, os, sys, pathlib, inspect
HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'replica'))
import nightly_card as NCard
import nightly_hill_climb as HC
import recreate


def test_n1128_card_includes_skipped_shadows_and_bass_wait():
    info = NCard.validate(tag='n1128')
    assert 'ridegate_lock_pump_ee' in info['arms']
    assert 'profade_ex35' in info['arms']
    assert 'bass_wait' in info['arms']
    assert info['arms'][0:3] == ['epg_strict', 'epg_drop', 'epg_stack']
    assert len(info['arms']) == 6
    assert len(set(info['short_tags'])) == 6
    names = [n for n, _ in HC.candidates('n1128')]
    assert names == info['arms']
    # n1127 card is frozen and still the one a 11-27 hill-climb would read
    n1127 = [c['name'] for c in NCard.card_for('n1127')]
    assert n1127 == ['epg_strict', 'epg_drop', 'epg_stack', 'ridegate_lock_pump_ee', 'profade_ex35']
    assert 'bass_wait' not in n1127
    card = {c['name']: c for c in NCard.card_for('n1128')}
    assert card['ridegate_lock_pump_ee']['delta'] == {'RIDEGATE_EE': 1}
    assert card['bass_wait']['delta'] == {'BASS_WAIT': 1}
    assert card['bass_wait']['shadow'] is True
    assert card['bass_wait']['flags_off_by_default'] is True
    src = inspect.getsource(recreate.apply_rules)
    assert "'BASS_WAIT'" in src
    env = recreate.apply_rules({})
    assert not recreate._flag_on(env.get('BASS_WAIT'))
    import paths
    rules = json.loads(pathlib.Path(paths.RULES).read_bytes())
    assert 'BASS_WAIT' not in rules
    assert rules.get('RIDEGATE') == 1


def test_n1128_launcher_reads_the_card_not_a_hardcoded_list():
    sh = (HERE / 'replica' / 'run_nightly_card.sh').read_text()
    wrap = (HERE / 'replica' / 'run_render_1128.sh').read_text()
    py = (HERE / 'n1128_run.py').read_text()
    def commands(text):
        return "\n".join(l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#"))
    # Comments may mention the n1127 bug; the commands themselves must not hardcode those arms.
    assert "dclash_land" not in commands(sh)
    assert "dclash_land" not in commands(wrap)
    assert "card_for" in py
    assert "run_nightly_card.sh" in wrap
    assert "n1128_run.py" in sh or "${TAG}_run.py" in sh
    # the n1127 one-off script stays as history; it is not the n1128 entry point
    old = (HERE / "replica" / "run_render_1127.sh").read_text()
    assert "dclash_land6" in commands(old)
