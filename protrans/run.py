"""CLI: extract clips, recreate blindly, score, tune once. Disk-tight."""
from __future__ import annotations
import argparse, json, os, sys, shutil, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, extract, score, fetch, recreate, cleanup, tune

def _load():
    return json.load(open(paths.CORPUS))

def _mix_audio(m):
    p = m.get('local_mix')
    if p and not os.path.isabs(p):
        p = os.path.join(paths.MIXES, p)
    if p and os.path.exists(p):
        return p, False
    # download only a cache copy, caller must delete after extract
    dest = os.path.join(paths.CACHE, 'mixes', f"{m['id']}.m4a")
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return dest, True
    if not m.get('url'):
        return None, False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    fetch.ytdlp_remote(m['url'], dest)
    cleanup.note('mix_dl', dest)
    return dest, True

def cmd_extract(C, only_ready=True):
    recs = []
    for m in C['mixes']:
        trans = extract.transitions_from_mix(m)
        if not trans: continue
        audio, downloaded = _mix_audio(m)
        if not audio:
            print('no mix audio', m['id']); continue
        try:
            for rec in trans:
                # skip pairs with no source ids if we only want runnable ones
                if only_ready and not (rec['a'].get('yt') and rec['b'].get('yt')):
                    continue
                r = extract.extract_one(rec, audio)
                recs.append(r)
                print('clip', r['id'], r['a']['title'], '->', r['b']['title'])
        finally:
            cleanup.drop_full_mix(audio, downloaded)
    json.dump(recs, open(os.path.join(paths.RESULTS, 'extracted.json'),'w'), indent=2)
    print('extracted', len(recs))
    return recs

def _src_path(yt):
    p = os.path.join(paths.LIB, f'{yt}.m4a')
    return p if os.path.exists(p) else None

def ensure_source(yt, url=None):
    dest = os.path.join(paths.LIB, f'{yt}.m4a')
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return dest
    url = url or f'https://www.youtube.com/watch?v={yt}'
    os.makedirs(paths.LIB, exist_ok=True)
    fetch.ytdlp_remote(url, dest)
    cleanup.note('source', dest, keep=True)
    return dest

def _score_pair(pro, ours, sa=None, sb=None):
    return score.score(pro, ours, src_a=sa, src_b=sb, use_demucs=False, cache=paths.CACHE)

def cmd_sanity(C):
    recs = json.load(open(os.path.join(paths.RESULTS, 'extracted.json'))) if os.path.exists(os.path.join(paths.RESULTS,'extracted.json')) else []
    recs = [r for r in recs if os.path.exists(r.get('pro_clip',''))]
    out = {}
    if recs:
        a = recs[0]['pro_clip']
        out['identity'] = _score_pair(a, a)
        if len(recs) > 1:
            out['random'] = _score_pair(a, recs[-1]['pro_clip'])
        print('identity', out['identity']['score'], 'random', out.get('random',{}).get('score'))
    json.dump(out, open(os.path.join(paths.RESULTS,'sanity.json'),'w'), indent=2)
    return out

def _run_one(rec, rules, tag, created_acc):
    sa = ensure_source(rec['a']['yt'])
    sb = ensure_source(rec['b']['yt'])
    rec['a']['src'] = sa; rec['b']['src'] = sb
    info = recreate.recreate(rec['a']['yt'], rec['b']['yt'], sa, sb,
                             hint_a_played_sec=rec['window'].get('hint_a_played_sec'),
                             rules=rules, tag=tag)
    created_acc.extend(info.get('created') or [])
    sc = _score_pair(rec['pro_clip'], info['ours'], sa, sb)
    return dict(id=rec['id'], split=rec['split'], dj=rec['dj'],
                pair=f"{rec['a']['title']} -> {rec['b']['title']}",
                pick=dict(fam=info['fam'], win=info['win'], env=info['env']),
                score=sc, ours=info['ours'], pro=rec['pro_clip'])

def cmd_baseline(C, keep=2, keep_prep=True):
    recs = json.load(open(os.path.join(paths.RESULTS,'extracted.json')))
    run_ids = C.get('run_now') or [r['id'] for r in recs if r.get('split')=='train'][:3]
    recs = [r for r in recs if r['id'] in run_ids or (not C.get('run_now') and r['a'].get('yt') and r['b'].get('yt'))]
    # honour run_now if present
    if C.get('run_now'):
        recs = [r for r in recs if r['id'] in C['run_now']]
        # also allow reconstructing from extract if run_now listed
        have = {r['id'] for r in recs}
        for rid in C['run_now']:
            if rid in have: continue
    rules = recreate.load_rules()
    created = []
    rows = []
    try:
        for i, rec in enumerate(recs):
            try:
                row = _run_one(rec, rules, f'pt{i}', created)
                rows.append(row)
                print(rec['split'], rec['id'], row['score']['score'], row['pick']['fam'])
            except Exception as e:
                print('FAIL', rec['id'], e)
                rows.append(dict(id=rec['id'], split=rec.get('split'), error=str(e)[-300:]))
    finally:
        # copy example pairs then delete other renders
        examples = []
        ok = [r for r in rows if r.get('ours') and r.get('pro')]
        pick = []
        for spl in ('train','test'):
            hit = next((r for r in ok if r.get('split')==spl), None)
            if hit: pick.append(hit)
        if len(pick) < keep:
            pick += [r for r in ok if r not in pick][:keep-len(pick)]
        os.makedirs(paths.DELIVER, exist_ok=True)
        for j, r in enumerate(pick, 1):
            pro_mp3 = os.path.join(paths.DELIVER, f'ex{j}_{r["id"]}_pro.mp3')
            ours_mp3 = os.path.join(paths.DELIVER, f'ex{j}_{r["id"]}_ours.mp3')
            subprocess_ffmpeg = __import__('subprocess')
            subprocess_ffmpeg.run(['ffmpeg','-v','error','-y','-i',r['pro'],'-codec:a','libmp3lame','-q:a','4',pro_mp3], check=True)
            shutil.copy2(r['ours'], ours_mp3)
            r['example'] = dict(pro=pro_mp3, ours=ours_mp3)
            examples += [pro_mp3, ours_mp3]
        cleanup.drop_render_dir('/tmp/protrans_bench', keep_examples=[r['ours'] for r in pick if r.get('ours')])
        cleanup.drop_render_dir('/tmp/protrans_work')
        cleanup.drop_stems()
        # Keep prep files for a following tune pass; tune deletes them.
        if not keep_prep:
            for p in created:
                if p.endswith('.wav') or (p.endswith('.json') and '/st/' in p.replace('\\','/')):
                    cleanup._rm(p)
                elif p.endswith('.m4a') and os.path.abspath(p).startswith(os.path.abspath(paths.SRC2)):
                    if os.path.islink(p): cleanup._rm(p)
    by = {'train':[], 'test':[]}
    for r in rows:
        if r.get('score') and r.get('split') in by:
            by[r['split']].append(r)
    summary = dict(train_n=len(by['train']), test_n=len(by['test']),
                   train_mean=tune.mean_score(by['train']), test_mean=tune.mean_score(by['test']),
                   rows=[{k:v for k,v in r.items() if k not in ('pro',)} for r in rows])
    json.dump(summary, open(os.path.join(paths.RESULTS,'baseline.json'),'w'), indent=2)
    print('baseline train', summary['train_mean'], 'n', summary['train_n'], 'test', summary['test_mean'], 'n', summary['test_n'])
    return summary

def cmd_tune(C):
    recs = json.load(open(os.path.join(paths.RESULTS,'extracted.json')))
    run_ids = C.get('run_now')
    if run_ids:
        recs = [r for r in recs if r['id'] in run_ids]
    base = recreate.load_rules()
    results = []
    created = []
    try:
        for var in tune.variants(base):
            rows = []
            for i, rec in enumerate(recs):
                if not rec['a'].get('yt'): continue
                try:
                    rows.append(_run_one(rec, var['rules'], f't{var["name"]}{i}', created))
                except Exception as e:
                    print('tune fail', var['name'], rec['id'], e)
            tr = [r for r in rows if r.get('split')=='train' and r.get('score')]
            te = [r for r in rows if r.get('split')=='test' and r.get('score')]
            row = dict(name=var['name'], rules=var['rules'],
                       train_mean=tune.mean_score(tr), test_mean=tune.mean_score(te),
                       train_n=len(tr), test_n=len(te))
            results.append(row)
            tune.log_row(row)
            print('variant', row['name'], 'train', row['train_mean'], 'test', row['test_mean'])
    finally:
        cleanup.drop_render_dir('/tmp/protrans_bench')
        cleanup.drop_stems()
        for p in created:
            if p.endswith('.wav') or (p.endswith('.json') and '/st/' in p.replace('\\','/')):
                cleanup._rm(p)
            elif p.endswith('.m4a') and os.path.abspath(p).startswith(os.path.abspath(paths.SRC2)) and os.path.islink(p):
                cleanup._rm(p)
    best, why = tune.pick(results)
    if best['name'] != 'baseline':
        json.dump(best['rules'], open(paths.RULES,'w'), indent=2)
    out = dict(results=results, chosen=best['name'], why=why, chosen_rules=best['rules'])
    json.dump(out, open(os.path.join(paths.RESULTS,'tune.json'),'w'), indent=2)
    print('chosen', best['name'], why)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['extract','sanity','baseline','tune','all'])
    args = ap.parse_args()
    C = _load()
    if args.cmd in ('extract','all'): cmd_extract(C, only_ready=False)
    if args.cmd in ('sanity','all'): cmd_sanity(C)
    if args.cmd in ('baseline','all'): cmd_baseline(C)
    if args.cmd in ('tune','all'): cmd_tune(C)

if __name__ == '__main__':
    main()
