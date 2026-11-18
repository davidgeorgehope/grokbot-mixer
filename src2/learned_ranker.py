"""Learned blend-option ranker (v0).

Behind RANKER=1 / rules['RANKER']. Off by default. Scores the engine's
candidate windows plus SNAP_IN / hold / tail options from the two tracks'
structure, energy and bass, and picks one option per pair.

Training lives in protrans/train_ranker_v0.py. The official 33-pair held-out
mixes are never used as training labels. Defaults stay unchanged unless a
flagged eval clears the current floor.
"""
from __future__ import annotations

import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL_DIR = os.path.join(ROOT, 'protrans', 'ranker')
MODEL_TXT = os.path.join(MODEL_DIR, 'ranker_v0.txt')
MODEL_JOBLIB = os.path.join(MODEL_DIR, 'ranker_v0.joblib')
REPORT_PATH = os.path.join(MODEL_DIR, 'report.json')

SECS = ('intro', 'build', 'drop', 'breakdown', 'outro')
TYPES = ('outro_intro', 'drop1_end', 'breakdown_drop')
HOLD_EXTRA = 16

FEATURE_NAMES = [
    'type_outro_intro', 'type_drop1_end', 'type_breakdown_drop',
    'out_end', 'in_begin', 'xbars',
    'snap_in', 'snap_in_hold', 'tail_exit', 'fade_long',
    'intro_len_b', 'n_drops_a', 'n_drops_b', 'n_bars_a', 'n_bars_b',
    'in_rel', 'out_rel',
    'out_sec_intro', 'out_sec_build', 'out_sec_drop', 'out_sec_breakdown', 'out_sec_outro',
    'in_sec_intro', 'in_sec_build', 'in_sec_drop', 'in_sec_breakdown', 'in_sec_outro',
    'holes', 'in_vs_body', 'out_vs_body', 'out_left', 'to_outro',
    'inc_bass_ok', 'in_drop_idx', 'ib_is_start',
]


def flag_on(v=None):
    if v is None:
        v = os.environ.get('RANKER')
    return str(v).strip().lower() not in ('', '0', 'false', 'none', 'no')


def _section_at(sec, bar):
    if bar is None or not sec:
        return None
    try:
        b = float(bar)
    except (TypeError, ValueError):
        return None
    for p in sec.get('phases') or []:
        if p['start'] <= b < p['end']:
            return p['name']
    drops = [list(map(int, d)) for d in (sec.get('drops') or [])]
    for s, e in drops:
        if s <= b < e:
            return 'drop'
    intro = int(sec.get('intro_end') or sec.get('drop1') or 0)
    if b < intro:
        return 'intro'
    bd = sec.get('breakdown')
    if bd is not None and b >= int(bd):
        outro = sec.get('outro_start')
        if outro is not None and b >= int(outro):
            return 'outro'
        d2 = sec.get('drop2')
        if d2 is not None and b >= int(d2):
            return 'drop'
        return 'breakdown'
    outro = sec.get('outro_start')
    if outro is not None and b >= int(outro):
        return 'outro'
    return 'drop' if intro and b >= intro else None


def _n_bars(sec):
    return int(sec.get('music_end') or sec.get('n_bars') or 0)


def _n_drops(sec):
    if sec.get('n_drops') is not None:
        return int(sec['n_drops'])
    return len(sec.get('drops') or [])


def _holes(win, lo_a, lo_b, gap=9.84):
    if not win or lo_a is None or lo_b is None:
        return 0.0, 0.0, 0.0, 0.0
    try:
        import window_planner as WP
        feat = WP.features(dict(type='', win=list(win)),
                           {'music_end': len(lo_a), 'n_bars': len(lo_a)},
                           {'intro_end': 0, 'n_bars': len(lo_b), 'drops': []},
                           lo_a, lo_b, gap)
        # use a fuller call when we have real sections; this fallback is holes only
        return (float(feat['holes']), float(feat['in_vs_body']),
                float(feat['out_vs_body']), 1.0 if feat['inc_bass_ok'] else 0.0)
    except Exception:
        return 0.0, 0.0, 0.0, 0.0


def option_vec(sa, sb, opt, lo_a=None, lo_b=None, gap=9.84):
    """Numeric features for one candidate option. No pro-choice labels."""
    typ = opt.get('type') or ''
    win = list(opt.get('win') or ['n', 0, None, 0, 16])
    e = float(win[1] or 0)
    ib = float(win[3] or 0)
    X = float(win[4] or 16)
    na, nb = float(_n_bars(sa) or 0), float(_n_bars(sb) or 0)
    intro = float(sb.get('intro_end') or sb.get('drop1') or 0)
    outro = sa.get('outro_start')
    out_left = (na - e) if na else 0.0
    to_outro = (float(outro) - e) if outro is not None else out_left
    os_ = _section_at(sa, e - X / 2.0)
    oi = _section_at(sb, ib + X / 2.0)
    holes = in_vs = out_vs = inc = 0.0
    if lo_a is not None and lo_b is not None:
        try:
            import window_planner as WP
            c = dict(type=typ, win=win,
                     in_drop=opt.get('in_drop'), ib_is_start=opt.get('ib_is_start'),
                     drop_start=opt.get('drop_start'))
            f = WP.features(c, sa, sb, lo_a, lo_b, gap)
            holes = float(f.get('holes') or 0)
            in_vs = float(f.get('in_vs_body') or 0)
            out_vs = float(f.get('out_vs_body') or 0)
            inc = 1.0 if f.get('inc_bass_ok') else 0.0
            os_ = f.get('out_sec') or os_
            oi = f.get('in_sec') or oi
            out_left = float(f.get('out_left') if f.get('out_left') is not None else out_left)
            to_outro = float(f.get('to_outro') if f.get('to_outro') is not None else to_outro)
        except Exception:
            pass
    x = [1.0 if typ == t else 0.0 for t in TYPES]
    x += [e, ib, X]
    x += [1.0 if opt.get('snap_in') else 0.0,
          1.0 if float(opt.get('snap_in_hold') or 0) > 0 else 0.0,
          float(opt.get('tail_exit') if opt.get('tail_exit') is not None else 6),
          1.0 if str(opt.get('fade') or 'long') == 'long' else 0.0]
    x += [intro, float(_n_drops(sa)), float(_n_drops(sb)), na, nb]
    x += [ib / nb if nb else 0.0, e / na if na else 0.0]
    x += [1.0 if os_ == s else 0.0 for s in SECS]
    x += [1.0 if oi == s else 0.0 for s in SECS]
    x += [holes, in_vs, out_vs, out_left, to_outro, inc,
          float(opt.get('in_drop') or 0),
          1.0 if opt.get('ib_is_start') else 0.0]
    assert len(x) == len(FEATURE_NAMES), (len(x), len(FEATURE_NAMES))
    return x


def enumerate_options(cands, default_tail=6, default_fade='long'):
    """Expand each nominated window into fade / SNAP_IN / hold / tail variants."""
    out = []
    variants = [
        dict(snap_in=False, snap_in_hold=0, tail_exit=int(default_tail), fade=default_fade),
        dict(snap_in=False, snap_in_hold=0, tail_exit=0, fade=default_fade),
        dict(snap_in=True, snap_in_hold=0, tail_exit=int(default_tail), fade=default_fade),
        dict(snap_in=True, snap_in_hold=HOLD_EXTRA, tail_exit=int(default_tail), fade=default_fade),
    ]
    seen = set()
    for c in cands:
        base = dict(c)
        win = tuple(base.get('win') or [])
        typ = base.get('type') or _type_from_win(base)
        base['type'] = typ
        for v in variants:
            opt = dict(base, **v)
            key = (typ, win, v['snap_in'], v['snap_in_hold'], v['tail_exit'], v['fade'])
            if key in seen:
                continue
            seen.add(key)
            out.append(opt)
    return out


def _type_from_win(c):
    if c.get('type'):
        return c['type']
    return 'outro_intro'


def relevance(opt, pro):
    """Graded label from the pro's choices. Higher is closer to the pro."""
    if not pro:
        return 0
    win = opt.get('win') or [None, 0, None, 0, 16]
    ib, e, X = win[3], win[1], win[4]
    rel = 0
    pro_ib = pro.get('incoming_bar')
    pro_e = pro.get('outgoing_bar')
    if pro_ib is not None and ib is not None:
        d = abs(float(ib) - float(pro_ib))
        if d <= 16:
            rel += 1
        if d <= 8:
            rel += 1
        if d <= 4:
            rel += 2
        if d <= 2:
            rel += 1
    if pro_e is not None and e is not None:
        d = abs(float(e) - float(pro_e))
        if d <= 16:
            rel += 1
        if d <= 8:
            rel += 1
    in_sec = _section_at(pro.get('sec_b') or {}, (ib or 0) + (X or 16) / 2.0) or opt.get('in_sec')
    out_sec = _section_at(pro.get('sec_a') or {}, (e or 0) - (X or 16) / 2.0) or opt.get('out_sec')
    if pro.get('incoming_section') and in_sec == pro.get('incoming_section'):
        rel += 1
    if pro.get('outgoing_section') and out_sec == pro.get('outgoing_section'):
        rel += 1
    # SNAP_IN: pro rise is relatively steep (bass dB/beat), or overlap is short
    want_snap = bool(pro.get('want_snap'))
    if bool(opt.get('snap_in')) == want_snap:
        rel += 1
    want_hold = bool(pro.get('want_hold'))
    has_hold = float(opt.get('snap_in_hold') or 0) > 0
    if has_hold == want_hold:
        rel += 1
    # tail: prefer the variant closer to the pro's measured tail
    pro_tail = pro.get('tail_bars')
    if pro_tail is not None:
        te = float(opt.get('tail_exit') if opt.get('tail_exit') is not None else 6)
        # long pro tail -> tail_exit 0 (let it linger); short -> default cut
        want_te = 0 if float(pro_tail) >= 24 else 6
        if te == want_te:
            rel += 1
    return int(rel)


def pro_labels_from_feat(feat):
    """Build a pro-label dict from a corpus_v2 feature record."""
    cue = feat.get('cue') or {}
    rt = (feat.get('rise_tail') or {}).get('bass') or (feat.get('rise_tail') or {}).get('all') or {}
    all_rt = (feat.get('rise_tail') or {}).get('all') or {}
    sa = (feat.get('track_a') or {}).get('sections') or {}
    sb = (feat.get('track_b') or {}).get('sections') or {}
    rise = rt.get('rise_db_per_beat')
    tail = all_rt.get('tail_bars')
    ov = feat.get('overlap_bars')
    return dict(
        incoming_bar=cue.get('incoming_bar'),
        outgoing_bar=cue.get('outgoing_bar'),
        incoming_section=cue.get('incoming_section'),
        outgoing_section=cue.get('outgoing_section'),
        sec_a=sa, sec_b=sb,
        tail_bars=tail, overlap_bars=ov,
        want_snap=bool(rise is not None and float(rise) >= 0.25) or bool(ov is not None and float(ov) <= 10),
        want_hold=bool(tail is not None and float(tail) >= 24),
    )


def fade_env(opt):
    env = {}
    if opt.get('snap_in'):
        env['SNAP_IN'] = '1'
        hold = float(opt.get('snap_in_hold') or 0)
        if hold > 0:
            env['SNAP_IN_HOLD'] = str(int(hold))
        else:
            env['SNAP_IN_HOLD'] = '0'
    else:
        env['SNAP_IN'] = '0'
        env['SNAP_IN_HOLD'] = '0'
    if opt.get('tail_exit') is not None:
        env['TAIL_EXIT'] = str(int(opt['tail_exit']))
    if opt.get('fade'):
        env['FADE'] = str(opt['fade'])
    return env


class Ranker:
    def __init__(self, kind, booster=None, sk_model=None, path=None, report=None):
        self.kind = kind
        self.booster = booster
        self.sk_model = sk_model
        self.path = path
        self.report = report or {}

    def predict(self, xs):
        X = np.asarray(xs, float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if self.kind == 'lightgbm':
            return np.asarray(self.booster.predict(X), float)
        return np.asarray(self.sk_model.predict(X), float)


def load(path=None):
    report = {}
    if os.path.exists(REPORT_PATH):
        try:
            report = json.load(open(REPORT_PATH))
        except Exception:
            report = {}
    txt = path or (report.get('model_path') if report.get('kind') == 'lightgbm' else None) or MODEL_TXT
    job = MODEL_JOBLIB if not (path and str(path).endswith('.joblib')) else path
    if txt and os.path.exists(txt):
        import lightgbm as lgb
        booster = lgb.Booster(model_file=txt)
        return Ranker('lightgbm', booster=booster, path=txt, report=report)
    if os.path.exists(job):
        import joblib
        model = joblib.load(job)
        return Ranker('sklearn_hgb', sk_model=model, path=job, report=report)
    return None


def choose(sa, sb, options, lo_a=None, lo_b=None, model=None, gap=9.84):
    """Score options and return (best_option, scores, info)."""
    if not options:
        return None, [], dict(reason='no_options')
    model = model or load()
    if model is None:
        return None, [], dict(reason='no_model')
    vecs = [option_vec(sa, sb, o, lo_a, lo_b, gap) for o in options]
    scores = model.predict(vecs)
    idx = int(np.argmax(scores))
    best = options[idx]
    info = dict(
        kind=model.kind,
        n_options=len(options),
        best_score=round(float(scores[idx]), 4),
        best_type=best.get('type'),
        best_win=list(best.get('win') or []),
        best_fade=fade_env(best),
        top3=[
            dict(type=options[i].get('type'), win=list(options[i].get('win') or []),
                 snap_in=bool(options[i].get('snap_in')),
                 snap_in_hold=int(options[i].get('snap_in_hold') or 0),
                 tail_exit=int(options[i].get('tail_exit') or 0),
                 score=round(float(scores[i]), 4))
            for i in np.argsort(scores)[::-1][:3]
        ],
    )
    return best, scores, info
