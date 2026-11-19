"""CONSONANCE cohort report (2026-11-19): per-pair deltas vs baseline, gate fire count, family changes, must-pass and
diagnostic medians from results/eval_tailexit_<variant>.json. Usage: python3 protrans/consonance_report.py base var [var...]"""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import paths, run_admitted_tune as T

def main(base, *vars_):
    recs = {r['id']: r for r in T.load_recs()}; B = T.load_ckpt(base); out = {}
    for v in vars_:
        V = T.load_ckpt(v); rows = []
        for rid, rv in V.items():
            rb = B.get(rid)
            if not rb: continue
            sb, sv = rb['score']['score'], rv['score']['score']; c = rv.get('consonance') or {}
            rows.append(dict(id=rid, split=recs[rid]['split'], pair=recs[rid]['pair'], base=round(sb, 2), var=round(sv, 2), d=round(sv - sb, 2),
                             fam_b=rb['pick']['fam'], fam_v=rv['pick']['fam'], win_b=rb['pick']['win'], win_v=rv['pick']['win'],
                             changed=rb['pick']['win'] != rv['pick']['win'], r_def=c.get('r_default'),
                             r_pick=((c.get('terms') or {}).get(rv['pick']['fam']) or {}).get('r')))
        ch = [r for r in rows if r['changed']]
        summ = dict(n=len(rows), fired=len(ch), fired_train=sum(r['split'] == 'train' for r in ch), fired_test=sum(r['split'] == 'test' for r in ch),
                    better=sum(r['d'] > 0.005 for r in ch), worse=sum(r['d'] < -0.005 for r in ch),
                    fam_v={f: sum(r['fam_v'] == f for r in rows) for f in sorted({r['fam_v'] for r in rows})},
                    mean_d_changed=round(float(np.mean([r['d'] for r in ch])), 2) if ch else None,
                    r_ratio_median_changed=round(float(np.median([r['r_pick'] / r['r_def'] for r in ch if r['r_pick'] and r['r_def']])), 3) if ch else None)
        for f in (base, v):
            p = os.path.join(paths.RESULTS, f'eval_tailexit_{f}.json')
            if os.path.exists(p): summ['diag_' + f] = json.load(open(p))['summary']
        out[v] = dict(summary=summ, rows=sorted(rows, key=lambda r: r['d']))
        print('VARIANT', v, json.dumps(summ, default=str))
        for r in sorted(ch, key=lambda r: r['d']):
            print(f"  {r['split']:5} {r['id']:30} {r['base']:6.2f} -> {r['var']:6.2f} ({r['d']:+.2f})  {r['fam_b']}{r['win_b']} -> {r['fam_v']}{r['win_v']}  R {r['r_def']} -> {r['r_pick']}  | {r['pair']}")
    json.dump(out, open(os.path.join(paths.RESULTS, 'consonance_report_1119.json'), 'w'), indent=1, default=str)

if __name__ == '__main__':
    main(*sys.argv[1:])
