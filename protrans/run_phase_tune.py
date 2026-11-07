"""Tune frequency-weighted phase preferences after the main admitted tuner.

Does not start if another recreate/tune job is still running.
Keep a change only when the held-out (Wilkinson+Netsky) mean does not drop.
"""
from __future__ import annotations
import copy, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import run_admitted_tune as T
import tune

LOCK = os.path.join(paths.RESULTS, 'phase_tune.lock')

def busy():
    import subprocess
    out = subprocess.check_output(['pgrep', '-af', 'run_admitted_tune.py'], text=True)
    mine = str(os.getpid())
    others = [ln for ln in out.splitlines() if 'run_admitted_tune.py' in ln and mine not in ln]
    return others

def variants():
    return [
        ('phase_pref_04', {'phase_pref_w': 0.4}),
        ('phase_pref_08', {'phase_pref_w': 0.8}),
        ('phase_pref_12', {'phase_pref_w': 1.2}),
        ('linger_03', {'linger_pen_w': 0.3}),
        ('linger_06', {'linger_pen_w': 0.6}),
        ('break_03', {'breakdown_pen_w': 0.3}),
        ('break_06', {'breakdown_pen_w': 0.6}),
    ]

def export_examples(recs, current, tes_rows):
    import shutil, recreate, score
    tes = [r for r in tes_rows if r.get('score') and not r.get('error')]
    def sc(r):
        s = r['score']
        return s['score'] if isinstance(s, dict) else s
    tes.sort(key=sc, reverse=True)
    dest = os.path.join(paths.DELIVER, 'protrans')
    os.makedirs(dest, exist_ok=True)
    # clear previous example mp3s but keep folder
    picks = []
    if tes:
        picks.append(('best_test', tes[0]))
        picks.append(('worst_test', tes[-1]))
    out = []
    recs_by_id = {r['id']: r for r in recs}
    for tag, row in picks:
        rec = recs_by_id[row['id']]
        sa = os.path.join(paths.LIB, rec['a']['yt'] + '.m4a')
        sb = os.path.join(paths.LIB, rec['b']['yt'] + '.m4a')
        info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                                 hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
                                 rules=current, tag='ex' + tag)
        pro = rec['pro_clip']
        ours = info['ours']
        dpro = os.path.join(dest, f'{tag}_pro.mp3')
        dours = os.path.join(dest, f'{tag}_ours.mp3')
        subprocess_ffmpeg(pro, dpro)
        subprocess_ffmpeg(ours, dours)
        out.append(dict(tag=tag, id=row['id'], pair=rec['pair'], score=row.get('score'),
                        pick=dict(fam=info.get('fam'), win=info.get('win')),
                        pro=dpro, ours=dours))
        try:
            if ours and os.path.exists(ours):
                os.remove(ours)
        except OSError:
            pass
    return out

def subprocess_ffmpeg(src, dst):
    import subprocess
    if src.endswith('.mp3'):
        import shutil
        shutil.copy2(src, dst)
        return
    subprocess.run(['ffmpeg','-v','error','-y','-i',src,'-codec:a','libmp3lame','-q:a','2',dst], check=True)

def main():
    if busy():
        print('another admitted tuner is running; not starting phase tune yet', flush=True)
        sys.exit(2)
    if not os.path.exists(os.path.join(paths.RESULTS, 'phase_priors.json')):
        raise SystemExit('need results/phase_priors.json first')
    recs = T.load_recs()
    current = json.load(open(paths.RULES))
    # floor from last kept tune_state
    st = json.load(open(T.STATE)) if os.path.exists(T.STATE) else {}
    floor = (st.get('after') or st.get('current_sum') or {}).get('test_mean')
    if floor is None:
        floor = 23.03
    train_floor = (st.get('after') or {}).get('train_mean')
    print(f'phase tune start; rules={current}; floor_test={floor} train={train_floor}', flush=True)
    decided = {d['name'] for d in T.decided_variants()}
    kept=[]; rejected=[]
    current_sum = st.get('after') or dict(test_mean=floor, train_mean=train_floor)
    for name, delta in variants():
        if name in decided:
            print(f'SKIP {name}', flush=True)
            continue
        print(f'=== TRY {name} {delta} ===', flush=True)
        trial = copy.deepcopy(current)
        trial.update(delta)
        rows = T.run_set_checkpointed(recs, trial, name, name[:8])
        sm = T.summarize(rows)
        print(f'  {name} train={sm["train_mean"]} test={sm["test_mean"]} by_dj={sm["by_dj"]}', flush=True)
        accept = sm['test_mean'] is not None and sm['test_mean'] + 1e-9 >= floor and (
            sm['test_mean'] > floor + 1e-9 or (sm['train_mean'] or -1) > (current_sum.get('train_mean') or -1) + 1e-9)
        rec = dict(name=name, delta=delta, summary=sm, kept=bool(accept), floor_test=floor,
                   train_mean=sm['train_mean'], test_mean=sm['test_mean'], by_dj=sm['by_dj'])
        if accept:
            rec['why'] = 'held-out mean did not drop'
            current = trial
            current_sum = sm
            floor = sm['test_mean']
            kept.append(rec)
            json.dump(current, open(paths.RULES, 'w'), indent=2)
            print(f'  KEEP {name}: test -> {sm["test_mean"]}', flush=True)
        else:
            rec['why'] = f'held-out mean dropped or no gain ({floor} -> {sm["test_mean"]})'
            rejected.append(rec)
            print(f'  REJECT {name}: {rec["why"]}', flush=True)
        tune.log_row(dict(name=name, delta=delta, train_mean=sm['train_mean'], test_mean=sm['test_mean'],
                          by_dj=sm['by_dj'], kept=accept, floor_test=rec['floor_test'], why=rec['why']))
    print('=== PHASE EXAMPLES ===', flush=True)
    tes_rows = T.run_set_checkpointed([r for r in recs if r['split']=='test'], current, 'phase_final_test', 'pfin')
    examples = export_examples(recs, current, tes_rows)
    report = dict(rules=current, after=current_sum, kept=kept, rejected=rejected, examples=examples,
                  before_floor=st.get('after'), ts=time.strftime('%Y-%m-%d %H:%M %Z'))
    json.dump(report, open(os.path.join(paths.RESULTS, 'phase_tune.json'), 'w'), indent=2)
    print(json.dumps({k: report[k] for k in ('rules','after','examples')}, indent=2, default=str), flush=True)

if __name__ == '__main__':
    main()
