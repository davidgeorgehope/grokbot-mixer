#!/usr/bin/env python3
"""Fresh-mix validation report: default vs RIDEGATE vs RIDEGATE+LINGER_GUARD.

Does not open the locked holdout. Does not write rules.json.
usage: compare_ridegate_fresh.py
"""
from __future__ import annotations
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, H); sys.path.insert(0, os.path.dirname(H))
import ridegate_live as RG
import holdout_1126_live as HV

W = os.path.join(H, 'nightly_1126_work')
CK = os.path.join(H, 'gate_ckpt')
FRESH = 'ukf_drum_bass_wVp_VlkWqxI'
ARMS = dict(default='n1126f_default', ridegate='n1126f_ridegate_live', linger='n1126f_ridegate_linger')


def _ckpt(name):
    p = os.path.join(CK, name + '.jsonl')
    out = {}
    if not os.path.exists(p):
        return out
    for line in open(p):
        r = json.loads(line)
        out[r['id']] = r
    return out


def main():
    pf = json.load(open(os.path.join(W, 'picker_1126_fresh.json')))
    pp = [p for p in pf['per_pair'] if p['mix'] == FRESH or p['id'].startswith(FRESH)]
    pack = RG.load_pack()
    built = {r['id']: r for r in RG.load_all_built() if r['id'] in {p['id'] for p in pp} or (r['set'] == 'fresh' and r.get('mix') == FRESH)}
    if not built:
        built = {r['id']: r for r in RG.load_all_built() if r['set'] == 'fresh'}
    DF, RF, LF = _ckpt(ARMS['default']), _ckpt(ARMS['ridegate']), _ckpt(ARMS['linger'])
    cal = RG.load_linger_cal()
    thr = float(cal.get('threshold', cal.get('p95', 0)))
    rows = []
    for p in pp:
        i = p['id']
        r = built.get(i)
        dec = RG.predict_rows(pack, [r])[0] if r else None
        official = None
        if dec:
            if dec.get('win') and not dec.get('is_default'):
                official = list(dec['win'])
            elif r:
                official = ['n', int(r['dex'] + r['dX'] - 1), None, int(r['dcue'] - 1), int(r['dX'])]
        rec = dict(id=i, official_win=official, official_abstain=bool(dec.get('is_default')) if dec else None,
                   official_p_leave=(dec or {}).get('p_leave'))
        for name, tab in (('default', DF), ('ridegate', RF), ('linger', LF)):
            rr = tab.get(i)
            if not rr or rr.get('error'):
                rec[name] = dict(status='not_evaluated', error=(rr or {}).get('error'))
                continue
            win = list(rr.get('win') or [])
            sa, sb = (r['sa'], r['sb']) if r else (None, None)
            lb = RG.linger_bars(sa, sb, win) if sa and win else None
            rec[name] = dict(status='rendered', fam=rr.get('fam'), win=win,
                             hard_fail=bool((rr.get('hard') or {}).get('hard_fail')),
                             flags={k: (rr.get('hard') or {}).get(k) for k in
                                    ('beat_clash', 'bass_hole', 'pumping', 'incoming_vanish', 'pump_db')},
                             linger_bars=lb, linger_over_p95=bool(lb is not None and lb > thr),
                             agree_official=bool(official and win == official))
        rows.append(rec)

    def _arm(name):
        ev = [r for r in rows if r.get(name, {}).get('status') == 'rendered']
        ne = [r for r in rows if r.get(name, {}).get('status') != 'rendered']
        defn = 'default'
        new_hf = [r['id'] for r in ev
                  if r[name].get('hard_fail') and not (r.get(defn) or {}).get('hard_fail')
                  and (r.get(defn) or {}).get('status') == 'rendered']
        agree = [r['id'] for r in ev if r[name].get('agree_official')]
        land = [r['id'] for r in ev if r[name].get('linger_bars')]
        over = [r['id'] for r in ev if r[name].get('linger_over_p95')]
        return dict(n_rendered=len(ev), n_not_evaluated=len(ne),
                    n_agree_official=len(agree), agree_rate=round(len(agree) / len(ev), 4) if ev else None,
                    new_hard_fail=new_hf, n_new_hard_fail=len(new_hf),
                    breakdown_cue_landings=land, n_breakdown_cue=len(land),
                    linger_over_p95=over, n_linger_over_p95=len(over))

    out = dict(
        mix=FRESH, n_pairs=len(pp),
        linger_cal=dict(p95=cal.get('p95'), threshold=thr, pro_rate=cal.get('pro'),
                        our_default_rate=cal.get('our_default'), our_ridegate_rate=cal.get('our_ridegate')),
        default=_arm('default'), ridegate=_arm('ridegate'), linger=_arm('linger'),
        pairs=rows,
        note='not_evaluated (missing audio or failed render) is not a veto. Locked holdout was not opened. rules.json was not written.',
    )
    dest = os.path.join(W, 'ridegate_fresh_validate.json')
    json.dump(out, open(dest, 'w'), indent=1, default=str)
    print('FRESH_VALIDATE', json.dumps({k: out[k] for k in ('mix', 'n_pairs', 'default', 'ridegate', 'linger') if k != 'pairs'}), flush=True)
    print('wrote', dest, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
