#!/usr/bin/env python3
"""Decision-level eval of the joint picker vs the live ridegate pack and the engine default.
Dev uses out-of-fold scores; fresh / official-33 use the full ensemble. No holdout."""
import json, os, sys, glob, gzip, collections
import numpy as np
H = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, H); sys.path.insert(0, os.path.dirname(H))
import joint_picker as J, ridegate_live as R, picker_1119 as P
sys.path.insert(0, os.path.join(H, 'prefs_1127')); import census as C
import lightgbm as lgb

def load_models(d=os.path.join(J.WORK, 'models' + os.environ.get('JOINT_TAG', ''))):
    return [lgb.Booster(model_str=gzip.open(f, 'rt').read()) for f in sorted(glob.glob(os.path.join(d, 'm*.txt.gz')))]

def pick(S, tau):
    j = int(np.argmax(S)); return j if S[j] - S[0] > tau else 0

def main():
    z, off = J._load(J.WORK); meta = json.load(open(os.path.join(J.WORK, 'meta.json')))
    oof = {int(k): np.array(v) for k, v in json.load(open(os.path.join(J.WORK, 'cv_oof' + os.environ.get('JOINT_TAG', '') + '.json')))['oof'].items()}
    ms = load_models()
    rows = {r['id']: r for r in R.load_all_built() if r['set'] in ('dev', 'fresh', 'protrans')}
    pack = R.load_pack()
    def err(r, w):
        e, ib, X = w[1], w[3], w[4]
        ex, cu = e - X + 1, ib + 1
        ov = float(r.get('pro_ov') or 16); px = 8 if ov <= 11 else 16 if ov <= 23 else 32
        return P.acc_err(ex, r['pro_out'], P.bnd_a(r['sa'])) + P.acc_err(cu, r['pro_in'], P.bnd_b(r['sb'])), int(X == px)
    def defwin(r): return ['n', int(r['dex'] + r['dX'] - 1), None, int(r['dcue'] - 1), int(r['dX'])]
    # scores per group
    S = {}
    for g, m in enumerate(meta):
        if m['set'] == 'dev' and g in oof: S[g] = oof[g]
        elif m['set'] in ('fresh', 'protrans'): S[g] = J.ens_scores(ms, z['X'][off[g]:off[g + 1]])
    taus = [-1e9, 0, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 1e9]
    devg = [g for g in S if meta[g]['set'] == 'dev']
    tau_err = {t: np.mean([err(rows[meta[g]['id']], meta[g]['T'][pick(S[g], t)]['win'])[0] for g in devg]) for t in taus}
    tau = min(tau_err, key=tau_err.get)
    res = dict(tau=tau, tau_dev_err={str(k): round(v, 2) for k, v in tau_err.items()}, sets={})
    old_rows = [rows[meta[g]['id']] for g in S if meta[g]['set'] in ('fresh', 'protrans')]
    old_dec = {r['id']: d for r, d in zip(old_rows, R.predict_rows(pack, old_rows))}
    picks = {}
    for st in ('dev', 'fresh', 'protrans'):
        gs = [g for g in S if meta[g]['set'] == st]
        lenagree = collections.defaultdict(lambda: [0, 0])
        acc = collections.defaultdict(list); sty = collections.defaultdict(collections.Counter); xs = collections.defaultdict(collections.Counter)
        for g in gs:
            r = rows[meta[g]['id']]
            wj = meta[g]['T'][pick(S[g], tau)]['win']; picks[meta[g]['id']] = wj
            cand = dict(joint=wj, default=defwin(r))
            if st != 'dev':
                d = old_dec[r['id']]; cand['ridegate'] = d['win'] if not d.get('is_default') and d.get('win') else defwin(r)
            ov = r.get('pro_ov')
            if ov: cand['pro'] = ['n', int(r['pro_out'] - 1 + round(ov)), None, int(r['pro_in'] - 1), int(round(ov))]
            if ov:
                pb = 8 if ov <= 11 else 16 if ov <= 23 else 32
                lenagree[pb][1] += 1; lenagree[pb][0] += int((8 if wj[4] <= 11 else 16 if wj[4] <= 23 else 32) == pb)
            for k, w in cand.items():
                if k != 'pro':
                    e, xm = err(r, w); acc[k + '_err'].append(e); acc[k + '_lenhit'].append(xm)
                sty[k][C.style(r['sa'], r['sb'], w[1] - w[4], w[3], w[4])] += 1
                xs[k][8 if w[4] <= 11 else 16 if w[4] <= 23 else 32] += 1
        res['sets'][st] = dict(n=len(gs), **{k: round(float(np.mean(v)), 3) for k, v in acc.items()},
                               styles={k: {s: round(c / len(gs), 3) for s, c in sorted(v.items())} for k, v in sty.items()},
                               len_agree_by_pro_len={str(b): f'{a}/{n}' for b, (a, n) in sorted(lenagree.items())},
                               lengths={k: {str(s): round(c / len(gs), 3) for s, c in sorted(v.items())} for k, v in xs.items()})
    # paired bootstrap (fresh): joint vs ridegate err
    for st in ('fresh', 'protrans'):
        gs = [g for g in S if meta[g]['set'] == st]
        d = []
        for g in gs:
            r = rows[meta[g]['id']]; od = old_dec[r['id']]
            ow = od['win'] if not od.get('is_default') and od.get('win') else defwin(r)
            d.append(err(r, picks[r['id']])[0] - err(r, ow)[0])
        d = np.array(d); rng = np.random.RandomState(1)
        bs = [np.mean(d[rng.randint(0, len(d), len(d))]) for _ in range(2000)]
        res['sets'][st]['joint_minus_ridegate_err'] = [round(float(d.mean()), 2), round(float(np.percentile(bs, 2.5)), 2), round(float(np.percentile(bs, 97.5)), 2)]
    json.dump(res, open(os.path.join(J.WORK, 'eval' + os.environ.get('JOINT_TAG', '') + '.json'), 'w'), indent=1)
    json.dump(picks, open(os.path.join(J.WORK, 'picks' + os.environ.get('JOINT_TAG', '') + '.json'), 'w'))
    print(json.dumps(res, indent=1))

if __name__ == '__main__':
    main()
