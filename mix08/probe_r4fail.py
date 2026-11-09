#!/usr/bin/env python3
"""Diagnose why every r4 dry-verify failed drums_only + vocal + structure."""
import os, sys, json, time, subprocess
from collections import Counter
os.environ.pop('PSKILL', None)
os.environ.pop('PSDBG', None)
for k, v in dict(
    STRUCT='1', FADE='tail', LOOP32='0', ECHO_MAX='2', PREF_W='0', PREFW='0',
    SWAP_PHRASE='1', HIGH_SWAP='1', BASS_SWAP_BARS='2',
    PAIR_TABLE='pair_table_08.json', TABLE_K='40', DROPPEN='60', BOTHMIN='8',
    COVPEN='300', OUTPEN='300', FAMBAN='0', BADW_NEWONLY='1', WIN_TOPK='400',
    NUDGE='nudge05n.json', PREV_PLANS='plan_mix07_r17.json',
    PINW='{"j9AuFRpLk7U>cxS6yd0UAxw":["lb",176,null,48,32]}',
).items():
    os.environ[k] = v
os.chdir('/workspace/mixes/src2')
sys.path.insert(0, '.')
import plan_search as ps
ps.KILL = None
ps.DBG = None

def run_search(soft, drop_frac, bw, label):
    os.environ['SOFT'] = str(soft)
    os.environ['DROP_FRAC'] = str(drop_frac)
    os.environ['BW'] = str(bw)
    ps.SOFT = soft
    print(f'\n===== {label} SOFT={soft} DROP_FRAC={drop_frac} BW={bw} =====', flush=True)
    t0 = time.time()
    done, K, st = ps.search('plan_mix08_base.json', 60, 68, 400, BW=(float(bw),), fix_open=False)
    feas = [d for d in done if not d['fails']]
    print(f'search_s={st} wall={time.time()-t0:.1f} complete={len(done)} feasible={len(feas)}', flush=True)
    if done:
        fc = Counter(f for d in done for f in d['fails'])
        de = [d['pred']['drop_end'] for d in done]
        print('fails', dict(fc), 'drop_end', min(de), '-', max(de), 'feas max drop', max((d['pred']['drop_end'] for d in feas), default=None), flush=True)
    return done, feas

done, feas = run_search(1, '0.2', '200', 'A_r4style')
if not feas:
    print('no table-feasible plan to dry-debug', flush=True)
    # still try a single-fail plan
    cand = [d for d in done if len(d['fails']) <= 1]
    feas = cand[:1]
if feas:
    d = feas[0]
    plan = ps.to_plan(d, 'plan_mix08_base.json')
    json.dump(plan, open('/tmp/plan_mix08_r4diag.json', 'w'), indent=1)
    voc = [(w['a'], w['b'], w['voc']) for w in d['bl'] if w.get('voc')]
    print('first feasible pred', d['pred'], 'n=', len(d['seq']), 'first', d['seq'][0], 'last', d['seq'][-1], flush=True)
    print('window voc clashes', voc, 'n_voc_windows', len(voc), 'voc_bars', sum(v[2] for v in voc), flush=True)
    print('drop_ok windows', sum(ps._drop_ok(w) for w in d['bl']), 'of', len(d['bl']), flush=True)
    json.dump(plan, open('_ps_diag.json', 'w'))
    r = subprocess.run([sys.executable, 'mix_simple.py', '--plan', '_ps_diag.json', '--out', '_ps_diag', '--dry'], capture_output=True, text=True)
    print('mix_simple dry rc', r.returncode, 'err', (r.stderr or '')[-400:], flush=True)
    if r.returncode == 0:
        p = ps.predict('_ps_diag_dry')
        print('dry pred tests', p.get('tests'), flush=True)
        print('vocal_clash', p.get('vocal_clash'), flush=True)
        print('drums_only_ok', p.get('drums_only_ok'), 'drop_end table vs dry len', d['pred'].get('drop_end'), p.get('len_min'), flush=True)
        import test_release_mix02_traits as T2
        import test_release_structure_tail as TS
        import checks as C
        def show(name, fn):
            try:
                fn()
                print(f'{name}: PASS', flush=True)
            except Exception as ex:
                print(f'{name}: {type(ex).__name__}: {ex}', flush=True)
        show('drums_only', T2.test_no_long_drums_only_stretch)
        show('structure', TS.test_plan_respects_outro_and_intro)
        # vocal already printed

print('\n===== B SOFT=0 DROP_FRAC=1/3 =====', flush=True)
done0, feas0 = run_search(0, '0.333', '200', 'B_strict')
if feas0:
    print('SOFT=0 first pred', feas0[0]['pred'], 'n', len(feas0[0]['seq']), 'first', feas0[0]['seq'][0], 'last', feas0[0]['seq'][-1], flush=True)
else:
    print('SOFT=0 no table-feasible plans', flush=True)
print('DONE', flush=True)
