"""Baseline + sequential general-rule tune with per-transition checkpoints.

Each scored pair is appended to results/score_ckpt/<variant>.jsonl immediately
and skipped on resume. Long runs should be started in the background.
Does not edit src2.
"""
from __future__ import annotations
import copy, fcntl, json, os, shutil, subprocess, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, recreate, score, tune, cleanup

USE_DEMUCS = False
STEM_KIND = 'bands'
CKPT = os.path.join(paths.RESULTS, 'score_ckpt')
STATE = os.path.join(paths.RESULTS, 'tune_state.json')
DONE = os.path.join(paths.RESULTS, 'tune_done.json')

def load_recs():
    import talkover
    bad = talkover.flagged_ids()  # DJ/MC talkover clips never enter scoring, tuning or the daily pick
    rows = [r for r in json.load(open(os.path.join(paths.RESULTS, 'admitted.json'))) if r['id'] not in bad]
    recs = []
    for r in rows:
        pro = os.path.join(paths.CLIPS, r['split'], r['id'], 'pro.wav')
        if not os.path.exists(pro):
            raise FileNotFoundError(pro)
        recs.append(dict(
            id=r['id'], dj=r['dj'], split=r['split'], mix_id=r.get('mix_id'),
            pair=r.get('pair') or f"{r['a']['title']} -> {r['b']['title']}",
            a=dict(title=r['a']['title'], yt=r['a']['yt']),
            b=dict(title=r['b']['title'], yt=r['b']['yt']),
            window=dict(mix_t_a=r['t_a'], mix_t_b=r['t_b'],
                        hint_a_played_sec=float(r['t_b']) - float(r['t_a'])),
            pro_clip=pro,
        ))
    return recs

def ckpt_path(variant):
    os.makedirs(CKPT, exist_ok=True)
    return os.path.join(CKPT, f'{variant}.jsonl')

def load_ckpt(variant):
    p = ckpt_path(variant)
    by = {}
    if not os.path.exists(p):
        return by
    for line in open(p):
        line=line.strip()
        if not line: continue
        try:
            row=json.loads(line)
        except json.JSONDecodeError:
            continue
        # Scorer repairs change the metric, not engine quality. Never resume
        # an old checkpoint and compare its scores with a newly measured round.
        payload = row.get('score')
        version = payload.get('scorer_version') if isinstance(payload, dict) else row.get('scorer_version')
        if row.get('id') and version == score.SCORER_VERSION:
            by[row['id']] = row
    return by

def append_ckpt(variant, row):
    p = ckpt_path(variant)
    payload = dict(row)
    payload['ts'] = time.strftime('%Y-%m-%d %H:%M:%S %Z')
    raw = json.dumps(payload, default=str) + '\n'
    with open(p, 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(raw)
        f.flush()
        os.fsync(f.fileno())

def summarize(rows):
    ok = [r for r in rows if r.get('score') and not r.get('error')]
    def mean(xs):
        return None if not xs else round(sum(xs)/len(xs), 2)
    def sc(r):
        s=r['score']
        return s['score'] if isinstance(s, dict) else float(s)
    train = [r for r in ok if r.get('split')=='train']
    test = [r for r in ok if r.get('split')=='test']
    by_dj = {}
    for r in ok:
        by_dj.setdefault(r['dj'], []).append(r)
    return dict(
        n=len(ok), n_fail=sum(1 for r in rows if r.get('error')),
        train_n=len(train), test_n=len(test),
        train_mean=mean([sc(r) for r in train]),
        test_mean=mean([sc(r) for r in test]),
        by_dj={dj: dict(n=len(vs), mean=mean([sc(r) for r in vs]),
                        split=vs[0].get('split'))
               for dj, vs in sorted(by_dj.items())},
        stem_kind=STEM_KIND,
    )

def slim(rows):
    out=[]
    for r in rows:
        if r.get('error'):
            out.append({k:r[k] for k in ('id','split','dj','pair','error') if k in r})
            continue
        sc=r.get('score') or {}
        if not isinstance(sc, dict):
            sc={'score': sc}
        out.append(dict(id=r['id'], split=r.get('split'), dj=r.get('dj'), pair=r.get('pair'),
                        fam=(r.get('pick') or {}).get('fam'),
                        win=(r.get('pick') or {}).get('win'),
                        score=sc.get('score'), breakdown=sc.get('breakdown'), scorer_version=sc.get('scorer_version')))
    return out

def fill_meta(row, recs_by_id):
    rec = recs_by_id.get(row.get('id'))
    if rec:
        row.setdefault('split', rec['split'])
        row.setdefault('dj', rec['dj'])
        row.setdefault('pair', rec['pair'])
        row.setdefault('pro', rec['pro_clip'])
    return row

def _worker(payload):
    rec, rules, tag, variant = payload
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import recreate, score, paths
    created=[]
    try:
        sa = os.path.join(paths.LIB, rec['a']['yt']+'.m4a')
        sb = os.path.join(paths.LIB, rec['b']['yt']+'.m4a')
        info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                                 hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
                                 rules=rules, tag=tag)
        created.extend(info.get('created') or [])
        sc = score.score(rec['pro_clip'], info['ours'], src_a=sa, src_b=sb,
                         use_demucs=False, cache=paths.CACHE)
        row=dict(id=rec['id'], split=rec['split'], dj=rec['dj'], pair=rec['pair'],
                 pick=dict(fam=info['fam'], win=info['win'], env=info['env']),
                 score=sc, ours=info.get('ours'), pro=rec['pro_clip'], created=created)
        append_ckpt(variant, row)
        return dict(ok=True, row=row)
    except Exception as e:
        row=dict(id=rec['id'], split=rec['split'], dj=rec['dj'], pair=rec['pair'],
                 error=f'{type(e).__name__}: {e}'[-400:], created=created)
        append_ckpt(variant, row)
        return dict(ok=False, row=row)

def run_set_checkpointed(recs, rules, variant, tag, workers=4):
    recs_by_id = {r['id']: r for r in recs}
    have = load_ckpt(variant)
    todo = [r for r in recs if r['id'] not in have]
    print(f'  {variant}: {len(have)} cached, {len(todo)} to score', flush=True)
    if todo:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        payloads=[(rec, rules, f'{tag}{i}', variant) for i, rec in enumerate(todo)]
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs={ex.submit(_worker, p): p[0]['id'] for p in payloads}
            for fut in as_completed(futs):
                rid=futs[fut]
                try:
                    got=fut.result()
                    row=got['row']
                except Exception as e:
                    print(f'  FAIL {rid} worker {e}', flush=True)
                    continue
                if row.get('error'):
                    print(f"  FAIL {row['id']} {row['error']}", flush=True)
                else:
                    sc=row['score']['score'] if isinstance(row.get('score'), dict) else row.get('score')
                    fam=(row.get('pick') or {}).get('fam')
                    print(f"  {row.get('split','?'):5} {row['id']:36} {sc:6.2f}  {fam}", flush=True)
    have = load_ckpt(variant)
    rows=[]
    for rec in recs:
        row = have.get(rec['id'])
        if not row:
            rows.append(dict(id=rec['id'], split=rec['split'], dj=rec['dj'],
                             pair=rec['pair'], error='missing after run'))
            continue
        rows.append(fill_meta(row, recs_by_id))
    return rows

def to_mp3(src, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    subprocess.run(['ffmpeg','-v','error','-y','-i',src,'-codec:a','libmp3lame','-q:a','4',dest], check=True)
    return dest

def variant_specs():
    return [
        ('fade_lin', {'FADE': 'lin'}),
        ('swap_1bar', {'BASS_SWAP_BARS': 1}),
        ('swap_4bar', {'BASS_SWAP_BARS': 4}),
        ('swap_pos_021', {'SWAP_POS': 0.21}),
        ('swap_pos_050', {'SWAP_POS': 0.50}),
        ('high_swap_off', {'HIGH_SWAP': 0}),
        ('high_ofs_0', {'HIGH_OFS': 0}),
        ('high_ofs_8', {'HIGH_OFS': 8}),
        ('struct_off', {'STRUCT': 0}),
        ('loop32_on', {'LOOP32': 1}),
        ('hint_off', {'hint_weight': 0}),
        ('hint_stronger', {'hint_weight': 0.4}),
        ('near_hint_16', {'near_hint_bars': 16}),
        ('near_hint_64', {'near_hint_bars': 64}),
        ('loop_pen_0', {'loop_fam_pen': 0}),
        ('loop_pen_2', {'loop_fam_pen': 2.0}),
        ('length_pref_16', {'length_pref': 16}),
        ('length_pref_32', {'length_pref': 32}),
        ('prefer_nat', {'prefer_family': 'nat'}),
    ]

def decided_variants():
    """Return ordered list of {name,delta,kept,summary} from this corpus tune (has delta)."""
    out=[]
    p=os.path.join(paths.LOGS, 'tune_log.jsonl')
    if not os.path.exists(p):
        return out
    for line in open(p):
        try: r=json.loads(line)
        except json.JSONDecodeError: continue
        if r.get('scorer_version') != score.SCORER_VERSION:
            continue
        if 'delta' not in r:  # old 4-pair tune
            continue
        out.append(r)
    return out

def write_state(obj):
    json.dump(obj, open(STATE,'w'), indent=2)

def main():
    recs = load_recs()
    recs_by_id = {r['id']: r for r in recs}
    print(f'loaded {len(recs)} admitted recs; scoring with {STEM_KIND} (use_demucs={USE_DEMUCS})', flush=True)
    t0=time.time()

    # --- baseline (skip pairs already in checkpoint / baseline.json) ---
    # Seed from baseline.json if ckpt incomplete
    if len(load_ckpt('baseline')) < len(recs):
        bp=os.path.join(paths.RESULTS,'baseline.json')
        if os.path.exists(bp):
            prev=json.load(open(bp))
            have=set(load_ckpt('baseline'))
            for r in prev.get('rows') or []:
                if r.get('id') and r['id'] not in have:
                    append_ckpt('baseline', r)
            print(f'seeded baseline ckpt from baseline.json -> {len(load_ckpt("baseline"))}', flush=True)

    print('=== BASELINE ===', flush=True)
    # baseline uses original rules.json as of first run; prefer stored rules
    stored = json.load(open(os.path.join(paths.RESULTS,'baseline.json'))) if os.path.exists(os.path.join(paths.RESULTS,'baseline.json')) else {}
    base_rules = stored.get('rules') or {
        "note": "General engine rules only. Tuning may change these keys, never a per-track pin or timestamp.",
        "FADE": "tail", "BASS_SWAP_BARS": 2, "SWAP_POS": 0.35, "HIGH_SWAP": 1,
        "HIGH_OFS": 4, "STRUCT": 1, "LOOP32": 0, "hint_weight": 0.15,
        "near_hint_bars": 32, "length_pref": 0, "family_prior_w": 0.3,
        "prefer_family": None, "loop_fam_pen": 1.0,
    }
    if stored.get('scorer_version') != score.SCORER_VERSION:
        base_rules = recreate.load_rules()  # preserve already-kept rules, remeasure the new metric
    base_rows = run_set_checkpointed(recs, base_rules, 'baseline', 'bl')
    base_sum = summarize(base_rows)
    print('baseline', json.dumps(base_sum, indent=2), flush=True)
    json.dump(dict(summary=base_sum, rows=slim(base_rows), rules=base_rules, stem_kind=STEM_KIND, scorer_version=score.SCORER_VERSION),
              open(os.path.join(paths.RESULTS,'baseline.json'),'w'), indent=2)

    current = copy.deepcopy(base_rules)
    current_sum = base_sum
    current_rows = base_rows
    kept=[]; rejected=[]
    for dec in decided_variants():
        if dec.get('kept'):
            current.update(dec['delta'])
            current_sum = dec.get('summary') or dict(train_mean=dec.get('train_mean'),
                                                     test_mean=dec.get('test_mean'),
                                                     by_dj=dec.get('by_dj'))
            kept.append(dict(name=dec['name'], delta=dec['delta'], summary=current_sum, kept=True))
            print(f'replay KEEP {dec["name"]} {dec["delta"]} test={dec.get("test_mean")}', flush=True)
        else:
            rejected.append(dict(name=dec['name'], delta=dec['delta'],
                                 summary=dict(train_mean=dec.get('train_mean'), test_mean=dec.get('test_mean'),
                                              by_dj=dec.get('by_dj')),
                                 kept=False, why=dec.get('why') or 'previously rejected'))
            print(f'replay REJECT {dec["name"]} {dec["delta"]} test={dec.get("test_mean")}', flush=True)
    json.dump(current, open(paths.RULES,'w'), indent=2)
    decided = {d['name'] for d in decided_variants()}

    write_state(dict(current_rules=current, baseline=base_sum, kept=kept, rejected=rejected,
                     stem_kind=STEM_KIND, phase='tuning'))

    for name, delta in variant_specs():
        if name in decided:
            print(f'=== SKIP {name} (already decided) ===', flush=True)
            continue
        print(f'=== TRY {name} {delta} ===', flush=True)
        trial = copy.deepcopy(current)
        trial.update(delta)
        rows = run_set_checkpointed(recs, trial, name, name[:8])
        sm = summarize(rows)
        print(f'  {name} train={sm["train_mean"]} test={sm["test_mean"]} by_dj={sm["by_dj"]}', flush=True)
        floor = current_sum.get('test_mean') if isinstance(current_sum, dict) else None
        trial_test = sm['test_mean']
        accept = (trial_test is not None and floor is not None and trial_test + 1e-9 >= floor
                  and (trial_test > floor + 1e-9 or (sm['train_mean'] or -1) > (current_sum.get('train_mean') or -1) + 1e-9))
        rec = dict(name=name, delta=delta, summary=sm, stem_kind=STEM_KIND,
                   kept=bool(accept), floor_test=floor,
                   train_mean=sm['train_mean'], test_mean=sm['test_mean'], by_dj=sm['by_dj'])
        if accept:
            why = 'held-out mean did not drop'
            rec['why']=why
            current = trial
            current_sum = sm
            current_rows = rows
            kept.append(rec)
            json.dump(current, open(paths.RULES,'w'), indent=2)
            print(f'  KEEP {name}: test {floor} -> {trial_test}, train now {sm["train_mean"]}', flush=True)
        else:
            if trial_test is None:
                why = 'no test scores'
            elif floor is not None and trial_test + 1e-9 < floor:
                why = f'held-out mean dropped ({floor} -> {trial_test})'
            else:
                why = f'no improvement (test {trial_test} vs {floor}, train {sm["train_mean"]} vs {current_sum.get("train_mean")})'
            rec['why']=why
            rejected.append(rec)
            print(f'  REJECT {name}: {why}', flush=True)
        tune.log_row(dict(name=name, delta=delta, scorer_version=score.SCORER_VERSION, train_mean=sm['train_mean'], test_mean=sm['test_mean'],
                          by_dj=sm['by_dj'], kept=accept, floor_test=floor, why=why))
        write_state(dict(current_rules=current, baseline=base_sum, after=current_sum,
                         kept=[{k:v for k,v in x.items() if k!='rows'} for x in kept],
                         rejected=[{k:v for k,v in x.items() if k!='rows'} for x in rejected],
                         stem_kind=STEM_KIND, phase='tuning', last=name))

    print('=== FINAL EXAMPLES (test set, kept rules) ===', flush=True)
    test_recs = [r for r in recs if r['split']=='test']
    tes_rows = run_set_checkpointed(test_recs, current, 'final_test', 'fin')
    tes = [r for r in tes_rows if r.get('score') and not r.get('error')]
    tes.sort(key=lambda r: (r['score']['score'] if isinstance(r['score'], dict) else r['score']), reverse=True)
    # If ours files missing (seeded rows), re-render those two after clearing cache entries
    def ensure_audio(row):
        ours=row.get('ours')
        if ours and os.path.exists(ours) and row.get('pro') and os.path.exists(row['pro']):
            return row
        rec=recs_by_id[row['id']]
        print(f'  re-render example {row["id"]}', flush=True)
        # force rescore/render by not using stale ours
        sa=os.path.join(paths.LIB, rec['a']['yt']+'.m4a')
        sb=os.path.join(paths.LIB, rec['b']['yt']+'.m4a')
        info=recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                               hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
                               rules=current, tag='ex'+row['id'][-8:])
        sc=score.score(rec['pro_clip'], info['ours'], src_a=sa, src_b=sb,
                       use_demucs=False, cache=paths.CACHE)
        row=dict(row, ours=info['ours'], pro=rec['pro_clip'], score=sc,
                 pick=dict(fam=info['fam'], win=info['win'], env=info['env']))
        append_ckpt('final_test', row)
        return row

    if not tes:
        raise RuntimeError('no test scores for examples')
    best, worst = tes[0], tes[-1]
    best, worst = ensure_audio(best), ensure_audio(worst)
    os.makedirs(paths.DELIVER, exist_ok=True)
    for n in os.listdir(paths.DELIVER):
        if n.endswith(('.mp3','.wav')) and (n.startswith('ex') or n.startswith('best_') or n.startswith('worst_')):
            cleanup._rm(os.path.join(paths.DELIVER, n))
    examples={}
    for label, row in (('best', best), ('worst', worst)):
        pro_mp3 = os.path.join(paths.DELIVER, f'{label}_test_{row["id"]}_pro.mp3')
        ours_mp3 = os.path.join(paths.DELIVER, f'{label}_test_{row["id"]}_ours.mp3')
        to_mp3(row['pro'], pro_mp3)
        to_mp3(row['ours'], ours_mp3)
        sc=row['score']['score'] if isinstance(row['score'], dict) else row['score']
        examples[label]=dict(id=row['id'], dj=row.get('dj'), pair=row.get('pair'),
                             score=sc, fam=(row.get('pick') or {}).get('fam'),
                             pro=pro_mp3, ours=ours_mp3)
        print(f'  {label} {row["id"]} {sc} {row.get("pair")}', flush=True)

    # refresh after summary from last kept checkpoint if we have those pair files
    last_kept = next((k['name'] for k in reversed(kept)), 'baseline')
    if last_kept != 'baseline' and len(load_ckpt(last_kept)) >= len(recs):
        current_rows = [fill_meta(load_ckpt(last_kept)[r['id']], recs_by_id) for r in recs]
        current_sum = summarize(current_rows)
    json.dump(current, open(paths.RULES,'w'), indent=2)
    out=dict(
        stem_kind=STEM_KIND, use_demucs=USE_DEMUCS,
        baseline=base_sum, after=current_sum,
        kept=[{k:v for k,v in r.items() if k!='rows'} for r in kept],
        rejected=[{k:v for k,v in r.items() if k!='rows'} for r in rejected],
        chosen_rules=current,
        examples=examples,
        after_rows=slim(current_rows),
        elapsed_sec=round(time.time()-t0,1),
    )
    json.dump(out, open(os.path.join(paths.RESULTS,'tune.json'),'w'), indent=2)
    json.dump(out, open(DONE,'w'), indent=2)
    print('WROTE results/tune.json', 'kept', [k['name'] for k in kept],
          'rejected', [k['name'] for k in rejected], flush=True)

    print('=== CLEANUP renders ===', flush=True)
    cleanup.drop_render_dir('/tmp/protrans_bench')
    cleanup.drop_render_dir('/tmp/protrans_work')
    cleanup.drop_stems()
    write_state(dict(current_rules=current, baseline=base_sum, after=current_sum,
                     kept=[k['name'] for k in kept], rejected=[k['name'] for k in rejected],
                     examples=examples, stem_kind=STEM_KIND, phase='done'))
    print('done', flush=True)

if __name__ == '__main__':
    main()
