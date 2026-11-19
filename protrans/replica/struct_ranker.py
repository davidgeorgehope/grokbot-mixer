"""REPLICA v1: pick the pro's exit / cue as a *structural* choice (which section boundary), not a regression.
Candidates = phase boundaries of each track (+ engine-default positions). Pointwise logistic model on
boundary features; evaluated leave-one-DJ-out. Train: corpus_v2 (76, tracklist anchor) + protrans (33, measured entry)."""
import json, os, sys, numpy as np
from collections import defaultdict
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
from decisions import load
PHASES = ['intro', 'build', 'drop', 'breakdown', 'outro']

def cands_out(sa):
    end = sa['music_end']; out = {}
    for p in sa['phases']:
        out.setdefault(p['start'], p)
    out.setdefault(max(end - 16, 0), None); out.setdefault(max(end - 32, 0), None)
    drops = [d[0] if isinstance(d, (list, tuple)) else d for d in sa.get('drops') or []]
    res = []
    for b in sorted(out):
        if b < 16: continue
        ph = next((p['name'] for p in sa['phases'] if p['start'] <= b < p['end']), 'outro')
        prev = next((p['name'] for p in sa['phases'] if p['start'] < b <= p['end']), 'intro')
        left = end - b
        n_drops_after = sum(1 for d in drops if d >= b)
        f = [left / 64.0, b / max(end, 1), float(n_drops_after == 0), float(n_drops_after), float(left <= 40)] + \
            [float(ph == x) for x in PHASES] + [float(prev == x) for x in PHASES]
        res.append((b, f))
    return res

def cands_in(sb):
    drops = [d[0] if isinstance(d, (list, tuple)) else d for d in sb.get('drops') or []] or [sb.get('drop1') or 32]
    pos = {0}
    for p in sb['phases']: pos.add(p['start'])
    for di, d in enumerate(drops[:3]):
        for o in (-32, -16, -8, 0): pos.add(d + o)
    res = []
    n = sb['n_bars']
    for b in sorted(x for x in pos if 0 <= x < n - 32):
        rel = [(b - d) for d in drops]; k = int(np.argmin(np.abs(rel)))
        ph = next((p['name'] for p in sb['phases'] if p['start'] <= b < p['end']), 'intro')
        f = [b / 64.0, rel[k] / 32.0, float(k == 0), float(k >= 1), float(abs(rel[k]) <= 4), float(rel[k] < 0)] + [float(ph == x) for x in PHASES]
        res.append((b, f))
    return res

def rows():
    out = []
    for r in load():
        out.append(dict(id=r['id'], dj=r['dj'], src='corpus_v2', sa=r['sec_a'], sb=r['sec_b'], out=r['out_bar'], inn=r['in_bar']))
    pd = json.load(open(os.path.join(H, 'protrans_decisions.json')))
    for k, v in pd.items():
        if v.get('error') or v.get('out_bar_at_entry') is None or not v['sec_a'].get('phases') or not v['sec_b'].get('phases'): continue
        out.append(dict(id=k, dj=v['dj'], src='protrans', sa=v['sec_a'], sb=v['sec_b'], out=v['out_bar_at_entry'], inn=v['in_bar_at_entry']))
    return out

def fit_pick(train, test, which):
    from sklearn.linear_model import LogisticRegression
    X, y = [], []
    for r in train:
        cs = cands_out(r['sa']) if which == 'out' else cands_in(r['sb']); tgt = r['out'] if which == 'out' else r['inn']
        if not cs: continue
        best = int(np.argmin([abs(b - tgt) for b, _ in cs]))
        for i, (b, f) in enumerate(cs): X.append(f); y.append(int(i == best and abs(b - tgt) <= 8))
    m = LogisticRegression(C=0.5, max_iter=3000, class_weight='balanced').fit(np.array(X), np.array(y))
    picks = {}
    for r in test:
        cs = cands_out(r['sa']) if which == 'out' else cands_in(r['sb'])
        if not cs: continue
        p = m.predict_proba(np.array([f for _, f in cs]))[:, 1]; picks[r['id']] = cs[int(np.argmax(p))][0]
    return picks, m

def default_pick(r, which):
    if which == 'out': return r['sa']['music_end'] - 16          # engine STRUCT: blend starts 16 bars before music end
    return max((r['sb'].get('drop1') or 16) - 16, 0)                 # incoming drop lands at blend end

def evaluate():
    R = rows(); djs = sorted({r['dj'] for r in R}); res = {}
    for which in ('out', 'in'):
        model_err, def_err, oracle_err = {}, {}, {}
        for dj in djs:
            tr = [r for r in R if r['dj'] != dj]; te = [r for r in R if r['dj'] == dj]
            picks, _ = fit_pick(tr, te, which)
            for r in te:
                tgt = r['out'] if which == 'out' else r['inn']
                model_err[r['id']] = (r['src'], abs(picks[r['id']] - tgt)) if r['id'] in picks else None
                def_err[r['id']] = (r['src'], abs(default_pick(r, which) - tgt))
                cs = cands_out(r['sa']) if which == 'out' else cands_in(r['sb'])
                oracle_err[r['id']] = (r['src'], min(abs(b - tgt) for b, _ in cs) if cs else None)
        def summ(E, src):
            e = np.array([v[1] for v in E.values() if v and v[0] == src and v[1] is not None])
            return dict(n=len(e), within8=round(float((e <= 8).mean()), 3), within16=round(float((e <= 16).mean()), 3), median=round(float(np.median(e)), 1))
        res[which] = {src: dict(model=summ(model_err, src), default=summ(def_err, src), oracle_best_candidate=summ(oracle_err, src)) for src in ('corpus_v2', 'protrans')}
    return res

if __name__ == '__main__':
    r = evaluate(); print(json.dumps(r, indent=1)); json.dump(r, open(os.path.join(H, 'eval_v1_struct.json'), 'w'), indent=1)
