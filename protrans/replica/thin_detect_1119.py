#!/usr/bin/env python3
"""2026-11-19 RCA follow-up: which pairs do the THIN flags touch? For each dev pair (corpus_v2, leave-one-DJ-out set) and each protrans
cohort pair, list the engine's family windows (blend_bench.families) under base / STRUCT_THIN / THIN_DROPCUE / both. Only pairs whose
family windows change need re-rendering; the rest are identical by construction. -> thin_detect_1119.json"""
import os, sys, json, subprocess
from multiprocessing import Pool
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); SRC2 = os.path.join(os.path.dirname(P), 'src2')
CFG = {'base': {}, 'A': {'STRUCT_THIN': '1'}, 'B': {'THIN_DROPCUE': '1'}, 'AB': {'STRUCT_THIN': '1', 'THIN_DROPCUE': '1'}}
if os.environ.get('TD_CFG'): CFG = json.loads(os.environ['TD_CFG'])  # 2026-11-19: reused for the STRUCTW / OUTRO_QC / SLOWDOWN arms
TAG = os.environ.get('TD_TAG', 'thin')
CODE = "import blend_bench as BB,json,sys;cs=BB.cands_for(sys.argv[1],sys.argv[2],sys.argv[3]);print('FAMS'+json.dumps({d['fam']:d['win'] for d in BB.families(cs,None)}))"
def job(a):
    pid, ya, yb = a[:3]; out = {}; created = []
    if len(a) > 3 and a[3]:  # missing st/ grid: prep the tracks exactly as recreate does (2026-11-19 fix: ~43 pairs had no st/ json)
        sys.path.insert(0, P); import recreate
        try:
            for y, src in ((ya, a[3]), (yb, a[4])):
                if not os.path.exists(os.path.join(SRC2, 'st', y + '.json')) and src and os.path.exists(src): recreate._prep_track(y, src, created)
        except Exception as ex: print('prep fail', pid, ex, flush=True)
    for c, env in CFG.items():
        e = dict(os.environ, BB_SCRATCH='/tmp/thin_detect', PREF_W='0', **env)
        for k in ('PICKER_WIN', 'ONLY', 'GATE_FEAT', 'GATE_FLIB'): e.pop(k, None)
        r = subprocess.run(['python3', '-c', CODE, ya, yb, f'td{TAG[:3]}_{pid[-12:]}_{c}'], cwd=SRC2, env=e, capture_output=True, text=True)
        l = [x for x in r.stdout.splitlines() if x.startswith('FAMS')]
        out[c] = json.loads(l[-1][4:]) if l else None
    for f in created:
        try: os.remove(f)
        except OSError: pass
    return pid, out
if __name__ == '__main__':
    sys.path.insert(0, H); os.makedirs('/tmp/thin_detect', exist_ok=True)
    import safeplace_1119 as S, run_admitted_tune as T
    import eval_gate as EG
    SRC = {p['id']: (p.get('sa'), p.get('sb')) for p in EG.pairs()}
    todo = [(r['id'], r['ya'], r['yb'], *SRC.get(r['id'], (None, None))) for r in S.dev_rows() if r['id'] in SRC] + [(r['id'], r['a']['yt'], r['b']['yt'], *SRC.get(r['id'], (None, None))) for r in T.load_recs()]
    OUT = os.path.join(H, f'{TAG}_detect_1119.json'); res = json.load(open(OUT)) if os.path.exists(OUT) else {}
    todo = [t for t in todo if t[0] not in res or any(v is None for v in res[t[0]].values())]
    with Pool(6) as pool:
        for i, (pid, o) in enumerate(pool.imap_unordered(job, todo)):
            res[pid] = o
            if i % 10 == 0: json.dump(res, open(OUT, 'w')); print(i, pid, {c: (o[c] or {}).get('nat_short') for c in o}, flush=True)
    json.dump(res, open(OUT, 'w'))
    ch = {c: sorted(k for k, o in res.items() if o.get('base') and o.get(c) and o[c] != o['base']) for c in CFG if c != 'base'}
    noaud = {t[0] for t in todo if not t[3]}  # 2026-11-19: dev rows with no audio on the box (not in eval_gate.pairs) can't be analysed or scored; count apart
    print('changed', {c: len(v) for c, v in ch.items()}, 'n', len(res), 'no_audio', sum(1 for k in res if k in noaud or (k not in SRC)),
          'failed_with_audio', sum(any(v is None for v in o.values()) for k, o in res.items() if k in SRC))
    json.dump(ch, open(os.path.join(H, f'{TAG}_changed_1119.json'), 'w'), indent=1)
