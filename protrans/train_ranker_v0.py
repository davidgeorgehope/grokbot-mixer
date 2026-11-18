#!/usr/bin/env python3
"""Train a v0 learned ranker on corpus_v2 accepted transitions plus the
official 33-pair TRAIN split only (held-out official mixes stay eval-only).

Split of corpus_v2 is by mix, at least 20%, seed 20261115.
Writes protrans/ranker/ranker_v0.txt and report.json. Does not change
rules.json or defaults.
"""
from __future__ import annotations
import json, os, sys, collections
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'src2'))
import paths
import corpus_v2_pipeline as P
import learned_ranker as LR
import window_planner as WP

SEED = 20261115
os.environ.setdefault('OMP_NUM_THREADS', '2')


def _lo_from_st(yt, src2=None):
    src2 = src2 or paths.SRC2
    p = os.path.join(src2, 'st', f'{yt}.json')
    if not os.path.exists(p):
        return None
    try:
        bar = (json.load(open(p)).get('bar') or {})
        lo = bar.get('low') or bar.get('bass')
        return None if lo is None else np.asarray(lo, float)
    except Exception:
        return None


def _sec_from_st(yt, src2=None):
    src2 = src2 or paths.SRC2
    cwd = os.getcwd()
    try:
        os.chdir(src2)
        import sections
        return sections.get(yt)
    except Exception:
        return {}
    finally:
        os.chdir(cwd)


def _spans_to_sec(spans, drops=None):
    if not spans:
        return {}
    phases = [{'name': n, 'start': int(s), 'end': int(e)} for n, s, e in spans]
    n = phases[-1]['end']
    drops = drops or [(int(s), int(e)) for n, s, e in spans if n == 'drop']
    first = drops[0][0] if drops else 0
    brk = next((int(s) for n, s, e in spans if n == 'breakdown'), None)
    outro = next((int(s) for n, s, e in spans if n == 'outro'), None)
    d2 = drops[1][0] if len(drops) > 1 else None
    return dict(n_bars=n, intro_end=first, drop1=first, breakdown=brk, drop2=d2,
                outro_start=outro, music_end=n, drops=[list(d) for d in drops],
                phases=phases, intro_len=first, n_drops=len(drops))


def corpus_examples(split, which):
    mix_set = set(split['train_mixes'] if which == 'train' else split['heldout_mixes'])
    out = []
    for rec in P.load_jsonl(P.ACCEPTED):
        if rec.get('video_id') in P.LEGACY_VIDEO_IDS:
            continue
        if rec['mix_id'] not in mix_set:
            continue
        fp = os.path.join(P.FEATURES, rec['id'] + '.json')
        if not os.path.exists(fp):
            continue
        feat = json.load(open(fp))
        sa = (feat.get('track_a') or {}).get('sections') or {}
        sb = (feat.get('track_b') or {}).get('sections') or {}
        if not sa or not sb:
            continue
        cands = feat.get('candidates') or []
        if not cands:
            try:
                cands = WP.nominate(sa, sb, X=16)
            except Exception:
                continue
        # unify candidate dicts (feature-file variants already have snap flags)
        base = [c for c in cands if not c.get('snap_in') and not c.get('snap_in_hold')]
        if not base:
            base = cands
        opts = LR.enumerate_options(base)
        pro = LR.pro_labels_from_feat(feat)
        if pro.get('incoming_bar') is None and pro.get('outgoing_bar') is None:
            continue
        out.append(dict(id=rec['id'], mix_id=rec['mix_id'], source='corpus_v2',
                        split=which, sa=sa, sb=sb, opts=opts, pro=pro,
                        lo_a=None, lo_b=None))
    return out


def legacy_train_examples():
    """Official 33-pair TRAIN split only, from phase_stats + src2 sections."""
    admitted = {r['id']: r for r in json.load(open(os.path.join(paths.RESULTS, 'admitted.json')))}
    phase = json.load(open(os.path.join(paths.RESULTS, 'phase_stats.json')))
    rows = {r['id']: r for r in phase.get('rows') or []}
    out = []
    for pid, rec in admitted.items():
        if rec.get('split') != 'train':
            continue
        pr = rows.get(pid)
        if not pr:
            continue
        sa = _sec_from_st(rec['a']['yt']) or _spans_to_sec(pr.get('spans_a') or [])
        sb = _sec_from_st(rec['b']['yt']) or _spans_to_sec(pr.get('spans_b') or [])
        if not sa or not sb:
            continue
        try:
            cands = WP.nominate(sa, sb, X=16)
        except Exception:
            cands = []
        if not cands:
            # always include a dummy outro-intro so the pair still trains fade/tail
            e = int(sa.get('music_end') or sa.get('n_bars') or 0)
            ib = max(0, int(sb.get('drop1') or sb.get('intro_end') or 0) - 16)
            cands = [dict(type='outro_intro', win=['n', (e // 8) * 8, None, (ib // 8) * 8, 16])]
        opts = LR.enumerate_options(cands)
        bars = pr.get('bars') or {}
        phases = pr.get('phases') or {}
        mixin = phases.get('mixin') or [None, None]
        tail = pr.get('tail_after_in_drop_bars')
        if tail is None:
            tail = pr.get('tail_raw_bars')
        pro = dict(
            incoming_bar=bars.get('mixin_in'),
            outgoing_bar=bars.get('mixin_out'),
            incoming_section=mixin[1] if len(mixin) > 1 else None,
            outgoing_section=mixin[0] if mixin else None,
            sec_a=sa, sec_b=sb,
            tail_bars=tail,
            overlap_bars=None,
            want_snap=bool(tail is not None and float(tail) <= 10),
            want_hold=bool(tail is not None and float(tail) >= 24),
        )
        out.append(dict(id=pid, mix_id=rec.get('mix_id'), source='legacy_train',
                        split='train', sa=sa, sb=sb, opts=opts, pro=pro,
                        lo_a=_lo_from_st(rec['a']['yt']), lo_b=_lo_from_st(rec['b']['yt'])))
    return out


def _pack(examples):
    X, y, qid, groups, rows = [], [], [], [], []
    for ex in examples:
        if not ex['opts']:
            continue
        vecs = [LR.option_vec(ex['sa'], ex['sb'], o, ex.get('lo_a'), ex.get('lo_b')) for o in ex['opts']]
        rels = [LR.relevance(o, ex['pro']) for o in ex['opts']]
        if max(rels) <= 0:
            continue
        X.extend(vecs)
        y.extend(rels)
        qid.extend([ex['id']] * len(vecs))
        groups.append(len(vecs))
        rows.append(ex)
    return (np.asarray(X, float), np.asarray(y, int), qid, groups, rows)


def _top1(examples, predict):
    """Held-out cue top-1: incoming bar within 8, and section match."""
    sec, close, n = [], [], 0
    for ex in examples:
        if not ex['opts']:
            continue
        vecs = [LR.option_vec(ex['sa'], ex['sb'], o, ex.get('lo_a'), ex.get('lo_b')) for o in ex['opts']]
        scores = predict(vecs)
        best = ex['opts'][int(np.argmax(scores))]
        pro = ex['pro']
        n += 1
        ib = (best.get('win') or [None, 0, None, 0, 16])[3]
        pro_ib = pro.get('incoming_bar')
        close.append(1.0 if (pro_ib is not None and abs(float(ib) - float(pro_ib)) <= 8) else 0.0)
        in_sec = LR._section_at(ex['sb'], float(ib) + 8)
        sec.append(1.0 if pro.get('incoming_section') and in_sec == pro['incoming_section'] else 0.0)
    return dict(n=n,
                top1_section_match=None if not sec else round(float(np.mean(sec)), 4),
                top1_within_8bars=None if not close else round(float(np.mean(close)), 4))


def train(X, y, groups):
    os.makedirs(LR.MODEL_DIR, exist_ok=True)
    try:
        import lightgbm as lgb
        dtrain = lgb.Dataset(X, label=y, group=groups, feature_name=list(LR.FEATURE_NAMES))
        # small n: shallow trees, larger min_data so we do not memorise 40-80 pairs
        params = dict(objective='lambdarank', metric='ndcg', ndcg_eval_at=[1, 3],
                      learning_rate=0.05, num_leaves=8, min_data_in_leaf=4,
                      max_depth=4, feature_fraction=0.8, verbose=-1,
                      force_col_wise=True, seed=SEED)
        booster = lgb.train(params, dtrain, num_boost_round=120)
        booster.save_model(LR.MODEL_TXT)
        gain = booster.feature_importance(importance_type='gain')
        imp = sorted(zip(LR.FEATURE_NAMES, [int(v) for v in gain]), key=lambda t: -t[1])
        def predict(xs):
            return booster.predict(np.asarray(xs, float))
        return dict(kind='lightgbm', model_path=LR.MODEL_TXT, predict=predict,
                    feature_importance=[{'name': n, 'gain': g} for n, g in imp])
    except Exception as e:
        print('lightgbm unavailable or failed, sklearn fallback:', e, flush=True)
        from sklearn.ensemble import HistGradientBoostingRegressor
        import joblib
        model = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.08,
                                              max_iter=150, min_samples_leaf=4,
                                              random_state=SEED)
        model.fit(X, y)
        joblib.dump(model, LR.MODEL_JOBLIB)
        def predict(xs):
            return model.predict(np.asarray(xs, float))
        return dict(kind='sklearn_hgb', model_path=LR.MODEL_JOBLIB, predict=predict,
                    feature_importance=[])


def main():
    split = P.assign_split()  # writes split.json; by mix, seed 20261115, >=20%
    corpus_tr = corpus_examples(split, 'train')
    corpus_ho = corpus_examples(split, 'heldout')
    legacy = legacy_train_examples()
    train_ex = corpus_tr + legacy
    X, y, qid, groups, used = _pack(train_ex)
    if not len(y):
        report = dict(trained=False, reason='no_training_rows',
                      n_corpus_train=len(corpus_tr), n_corpus_heldout=len(corpus_ho),
                      n_legacy_train=len(legacy))
        os.makedirs(LR.MODEL_DIR, exist_ok=True)
        json.dump(report, open(LR.REPORT_PATH, 'w'), indent=2)
        print('RANKER', json.dumps(report), flush=True)
        return 2
    model = train(X, y, groups)
    ho = _top1(corpus_ho, model['predict'])
    tr = _top1(corpus_tr, model['predict'])
    # also report how often the top option differs from the default (first outro-intro, no snap, tail 6)
    n_diff = 0
    diffs = []
    for ex in corpus_ho + corpus_tr + legacy:
        if not ex['opts']:
            continue
        vecs = [LR.option_vec(ex['sa'], ex['sb'], o, ex.get('lo_a'), ex.get('lo_b')) for o in ex['opts']]
        scores = model['predict'](vecs)
        best = ex['opts'][int(np.argmax(scores))]
        default = next((o for o in ex['opts'] if o.get('type') == 'outro_intro'
                        and not o.get('snap_in') and int(o.get('tail_exit') or 6) == 6), ex['opts'][0])
        same = (best.get('type') == default.get('type')
                and list(best.get('win')) == list(default.get('win'))
                and bool(best.get('snap_in')) == bool(default.get('snap_in'))
                and int(best.get('snap_in_hold') or 0) == int(default.get('snap_in_hold') or 0)
                and int(best.get('tail_exit') or 6) == int(default.get('tail_exit') or 6))
        if not same:
            n_diff += 1
            if len(diffs) < 12:
                diffs.append(dict(id=ex['id'], source=ex['source'],
                                  default=dict(type=default.get('type'), win=default.get('win'),
                                               snap_in=bool(default.get('snap_in')),
                                               hold=int(default.get('snap_in_hold') or 0),
                                               tail=int(default.get('tail_exit') or 6)),
                                  pick=dict(type=best.get('type'), win=best.get('win'),
                                            snap_in=bool(best.get('snap_in')),
                                            hold=int(best.get('snap_in_hold') or 0),
                                            tail=int(best.get('tail_exit') or 6))))
    report = dict(
        trained=True, kind=model['kind'], model_path=model['model_path'],
        seed=SEED, held_out_by='mix', held_out_frac=P.HELD_OUT_MIX_FRAC,
        n_train_candidates=int(len(y)),
        n_train_transitions=len(set(qid)),
        n_corpus_train=len(corpus_tr), n_corpus_heldout=len(corpus_ho),
        n_legacy_train=len(legacy),
        n_train_mixes=split.get('n_train_mixes'),
        n_heldout_mixes=split.get('n_heldout_mixes'),
        heldout_mixes=split.get('heldout_mixes'),
        train_mixes=split.get('train_mixes'),
        corpus_heldout=ho, corpus_train=tr,
        n_diff_from_default=n_diff,
        n_scored_for_diff=len(corpus_ho) + len(corpus_tr) + len(legacy),
        example_diffs=diffs,
        feature_importance=model['feature_importance'][:12],
        flag='RANKER', flag_default=0,
        floor={'held_out': 34.07, 'train': 32.40, 'n_fail': 0},
        note='v0 trained before the 150-accepted target. Official 33-pair held-out mixes were not used as labels.',
    )
    json.dump(report, open(LR.REPORT_PATH, 'w'), indent=2)
    print('RANKER', json.dumps({k: report[k] for k in report if k not in ('train_mixes', 'heldout_mixes', 'example_diffs')}, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
