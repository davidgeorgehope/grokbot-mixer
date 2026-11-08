"""Old metric scores cannot be resumed into a new calibration round."""
import os,sys,json
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import run_admitted_tune as R
import score


def test_checkpoint_rejects_previous_scorer(tmp_path,monkeypatch):
    monkeypatch.setattr(R,'CKPT',str(tmp_path))
    rows=[dict(id='old',score=dict(score=100)),
          dict(id='new',score=dict(score=20,scorer_version=score.SCORER_VERSION)),
          dict(id='flat',score=20,scorer_version=score.SCORER_VERSION)]
    (tmp_path/'test.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    assert set(R.load_ckpt('test')) == {'new','flat'}


def test_old_decisions_are_not_replayed_as_new_metric(tmp_path,monkeypatch):
    monkeypatch.setattr(R.paths,'LOGS',str(tmp_path))
    rows=[dict(name='old',delta={'length_pref':32},kept=True),
          dict(name='new',delta={'length_pref':16},kept=False,scorer_version=score.SCORER_VERSION)]
    (tmp_path/'tune_log.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    assert [r['name'] for r in R.decided_variants()] == ['new']
