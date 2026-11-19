#!/usr/bin/env python3
"""DJ style inferred ONLINE from earlier transitions of the same mix (2026-11-18 late), instead of the hand-set per-mix bit.
For transition t of mix m, style(t) = share of the pro's mid-track exits (>40 bars of outgoing music left) over the transitions
of m with index < t only (index = the __NN suffix of the pair id; all admitted pairs of the mix count, not only the frozen
103). Strict ordering: nothing from t or later is read. No history -> 0.5 (unknown). K = how many most-recent earlier
transitions are used (K=3 a priori "first few"; K=all also reported).
Same protocol as policy.py: outer leave-one-DJ-out on DEV, inner C/alpha selection, conformal abstention, grouped bootstrap.
Also a model-free online rule: replica (REPLICA=1 row) iff style(t) > 0.5 with >=2 earlier transitions, else default.
Writes replica/online_style.json."""
import json, os, sys, collections, numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H)
import policy as PO, eval_gate as EG

def idx(pid): return int(pid.rsplit('__', 1)[1])

def history():
    os.chdir(PO.SRC2); import sections as S
    h = collections.defaultdict(list)
    for r in EG.pairs():
        na = S.get(r['a']).get('music_end') or 0
        h[r['mix']].append((idx(r['id']), float(na - r['pro']['out_bar'] > 40)))
    return {m: sorted(v) for m, v in h.items()}

def make_style(H_, K):
    def prior(r):
        t = idx(r['id']); past = [b for i, b in H_.get(r['mix'], []) if i < t]
        if K: past = past[-K:]
        return past
    def style(r):
        p = prior(r); return float(np.mean(p)) if p else 0.5
    return style, prior

def run(K):
    rs = PO.load_all(False); H_ = history(); style, prior = make_style(H_, K)
    allchosen = collections.defaultdict(list); order = []; folds = {}
    for d in sorted({r['dj'] for r in rs}):
        tr = [r for r in rs if r['dj'] != d]; te = [r for r in rs if r['dj'] == d]
        ch, dg = PO.policies(tr, te, style)
        ch['online_rule'] = [r['O'] if (len(prior(r)) >= 2 and style(r) > 0.5) else r['D'] for r in te]
        for k, v in ch.items(): allchosen[k] += v
        order += te; folds[d] = dict(C=dg['C'], alpha=dg['alpha'], n=len(te), used=int(sum(dg['use'])))
    res = PO.evaluate(order, allchosen)
    hist_n = collections.Counter(min(3, len(prior(r))) for r in rs)
    acc = [(style(r) > 0.5) == bool(PO.mid_exit(r)) for r in rs if prior(r)]
    return dict(K=K or 'all', n=len(rs), history_len_counts={str(k): v for k, v in sorted(hist_n.items())},
                style_predicts_this_transition=round(float(np.mean(acc)), 3), n_with_history=len(acc),
                base_rate_mid_exit=round(float(np.mean([PO.mid_exit(r) for r in rs])), 3),
                results={k: res[k] for k in ('default', 'gate_apriori', 'rule_always_replica', 'model_conformal', 'model_plain', 'online_rule')}, folds=folds)

if __name__ == '__main__':
    out = {f'K{k or "all"}': run(k) for k in (3, 0)}
    json.dump(out, open(os.path.join(H, 'online_style.json'), 'w'), indent=1, default=str)
    for k, v in out.items():
        print(k, 'acc', v['style_predicts_this_transition'], 'n', v['n_with_history'], 'base', v['base_rate_mid_exit'])
        for n, s in v['results'].items():
            d = s.get('delta_vs_default', {}).get('exit_cue', {})
            print(' ', n, 'exit_cue_mean', s['exit_cue_mean'], 'd', d.get('delta'), d.get('ci'), 'hit16', s['exit_hit16'], 'hard', s['hard_fail'], 'used', s['replica_used'])
