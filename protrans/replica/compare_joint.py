#!/usr/bin/env python3
"""Side-by-side default vs JOINT_PICKER on dev-27 and the 18-pair fresh ukf mix."""
import json, os, collections, sys
import numpy as np
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H); sys.path.insert(0, os.path.join(H, 'prefs_1127'))
import census as C

def load_dev(path):
    d = json.load(open(path))
    rows = {r['id']: r for r in d['rows'] if 'v1' in r}
    picks = d.get('picks') or {}
    return d.get('summary') or {}, rows, picks

def load_fresh(path):
    rows = {json.loads(l)['id']: json.loads(l) for l in open(path)}
    return rows

def style_of(pick, sections=None):
    w = pick.get('win') or []
    if len(w) < 5: return None, None
    return w, w[4]

def main():
    dev_b = os.path.join(H, 'joint_work/measure_dev27_base27.json')
    dev_j = os.path.join(H, 'joint_work/measure_dev27_r1fix.json')
    fr_b = os.path.join(H, 'gate_ckpt/n1126f_rgdef.jsonl')
    fr_j = os.path.join(H, 'gate_ckpt/n1127f_joint_r1fix.jsonl')
    out = {}
    if os.path.exists(dev_b) and os.path.exists(dev_j):
        sb, rb, pb = load_dev(dev_b); sj, rj, pj = load_dev(dev_j)
        ids = sorted(set(rb) & set(rj))
        d1 = np.array([rj[i]['v1'] - rb[i]['v1'] for i in ids])
        d2 = np.array([rj[i]['v2'] - rb[i]['v2'] for i in ids])
        rng = np.random.RandomState(1)
        def ci(d):
            bs = [np.mean(d[rng.randint(0, len(d), len(d))]) for _ in range(2000)]
            return [round(float(d.mean()), 2), round(float(np.percentile(bs, 2.5)), 2), round(float(np.percentile(bs, 97.5)), 2)]
        def hf(rows, ids):
            return [i for i in ids if rows[i]['hc']['hard_fail']]
        def lens(picks, ids):
            return dict(collections.Counter(picks[i]['win'][4] for i in ids if i in picks and picks[i].get('win')))
        def fams(picks, ids):
            return dict(collections.Counter(picks[i].get('fam') for i in ids if i in picks))
        changed = [i for i in ids if (pj.get(i) or {}).get('win') != (pb.get(i) or {}).get('win')]
        out['dev27'] = dict(
            n=len(ids),
            default=dict(v1=sb.get('v1'), v2=sb.get('v2'), hf=sb.get('hf'), hf_ids=hf(rb, ids), lens=lens(pb, ids), fams=fams(pb, ids)),
            joint=dict(v1=sj.get('v1'), v2=sj.get('v2'), hf=sj.get('hf'), hf_ids=hf(rj, ids), lens=lens(pj, ids), fams=fams(pj, ids)),
            delta_v1=ci(d1), delta_v2=ci(d2),
            v1_wins=int((d1 > 0).sum()), v1_losses=int((d1 < 0).sum()), v1_ties=int((d1 == 0).sum()),
            new_hf=[i for i in hf(rj, ids) if i not in hf(rb, ids)],
            cleared_hf=[i for i in hf(rb, ids) if i not in hf(rj, ids)],
            changed=changed,
            changed_wins=[{'id': i, 'win_d': pb[i]['win'], 'win_j': pj[i]['win'],
                           'dv1': round(rj[i]['v1']-rb[i]['v1'], 2), 'dv2': round(rj[i]['v2']-rb[i]['v2'], 2),
                           'hf_d': rb[i]['hc']['hard_fail'], 'hf_j': rj[i]['hc']['hard_fail'],
                           'margin': (pj[i].get('rg') or {}).get('joint')} for i in changed],
        )
    if os.path.exists(fr_b) and os.path.exists(fr_j):
        fb, fj = load_fresh(fr_b), load_fresh(fr_j)
        ids = sorted(set(fb) & set(fj))
        def fhf(rows, ids):
            return [i for i in ids if (rows[i].get('hard') or {}).get('hard_fail')]
        def flens(rows, ids):
            return dict(collections.Counter((rows[i].get('win') or [0,0,0,0,16])[4] for i in ids))
        def ffam(rows, ids):
            return dict(collections.Counter(rows[i].get('fam') for i in ids))
        changed = [i for i in ids if fb[i].get('win') != fj[i].get('win')]
        out['fresh18'] = dict(
            n=len(ids),
            default=dict(hf=len(fhf(fb, ids)), hf_ids=fhf(fb, ids), lens=flens(fb, ids), fams=ffam(fb, ids)),
            joint=dict(hf=len(fhf(fj, ids)), hf_ids=fhf(fj, ids), lens=flens(fj, ids), fams=ffam(fj, ids)),
            new_hf=[i for i in fhf(fj, ids) if i not in fhf(fb, ids)],
            cleared_hf=[i for i in fhf(fb, ids) if i not in fhf(fj, ids)],
            changed=changed,
            changed_wins=[{'id': i, 'win_d': fb[i]['win'], 'win_j': fj[i]['win'],
                           'fam_d': fb[i]['fam'], 'fam_j': fj[i]['fam'],
                           'hf_d': (fb[i].get('hard') or {}).get('hard_fail'),
                           'hf_j': (fj[i].get('hard') or {}).get('hard_fail'),
                           'pump_j': (fj[i].get('hard') or {}).get('pump_db'),
                           'exit_d': (fb[i].get('err') or {}).get('exit'),
                           'exit_j': (fj[i].get('err') or {}).get('exit'),
                           'cue_d': (fb[i].get('err') or {}).get('cue'),
                           'cue_j': (fj[i].get('err') or {}).get('cue')} for i in changed],
        )
    dest = os.path.join(H, 'joint_work/compare_r1fix.json')
    json.dump(out, open(dest, 'w'), indent=1, default=str)
    print(json.dumps(out, indent=2, default=str))

if __name__ == '__main__':
    main()
