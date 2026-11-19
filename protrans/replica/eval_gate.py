#!/usr/bin/env python3
"""REPLICA gate eval (2026-11-18 night): default vs REPLICA=1 vs REPLICA=gated on the 33 protrans pairs + corpus_v2 transitions
with local audio. Primary signal = decision match to the pro (exit / cue bar error, overlap length, bass-swap timing, fade-shape
error vs the pro's per-deck curves) plus hard checks (hardcheck.py). Similarity score is recorded for protrans as a diagnostic only.
Checkpointed per (variant, pair) in replica/gate_ckpt/<variant>.jsonl. rules.json is read, never written.
usage: eval_gate.py <variant>=<json overrides> [...]   e.g.  default={} on={"REPLICA":1} gated={"REPLICA":"gated"}"""
import copy, glob, json, os, sys, time, traceback, fcntl
H = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(H); sys.path.insert(0, P); sys.path.insert(0, H)
import paths
CK = os.path.join(H, 'gate_ckpt'); os.makedirs(CK, exist_ok=True)
FEAT = os.path.join(P, 'corpus_v2', 'features'); FLIB = os.path.join(P, 'corpus_v2', 'feat_lib')

def entry_from_curves(a, b):
    import numpy as np
    a, b = np.asarray(a, float), np.asarray(b, float)
    da, db = a - np.percentile(a, 90), b - np.percentile(b, 90); ona, onb = da > -12, db > -12
    b_in = next((k for k in range(len(onb)-1) if onb[k] and onb[k+1]), None)
    return b_in, da, db

def pairs():
    import run_admitted_tune as T
    PRO = json.load(open(os.path.join(H, 'protrans_decisions.json'))); out = []
    for r in T.load_recs():
        d = PRO.get(r['id']) or {}
        if d.get('out_bar_at_entry') is None: continue
        c = d['curves']; s = d['in_entry_clip_bar'] or 0
        out.append(dict(id=r['id'], src='protrans', split=r['split'], dj=r['dj'], mix=r['id'].rsplit('__', 1)[0],
                        a=r['a']['yt'], b=r['b']['yt'], sa=os.path.join(paths.LIB, r['a']['yt'] + '.m4a'), sb=os.path.join(paths.LIB, r['b']['yt'] + '.m4a'),
                        hint=r['window'].get('hint_a_played_sec'), pro_clip=r['pro_clip'],
                        pro=dict(out_bar=d['out_bar_at_entry'], in_bar=d['in_bar_at_entry'], overlap=d.get('overlap_bars'), swap_after_entry=d.get('swap_after_entry'),
                                 curve_a=c['all_a'][s:], curve_b=c['all_b'][s:])))
    for p in sorted(glob.glob(os.path.join(FEAT, '*.json'))):
        f = json.load(open(p))
        if f.get('error'): continue
        a, b = f['track_a']['yt'], f['track_b']['yt']; sa, sb = os.path.join(FLIB, a + '.m4a'), os.path.join(FLIB, b + '.m4a')
        if not (os.path.exists(sa) and os.path.exists(sb)): continue
        cue = f['cue']; pro = dict(out_bar=cue['outgoing_bar'], in_bar=cue['incoming_bar'], overlap=f.get('overlap_bars'), swap_after_entry=None, curve_a=None, curve_b=None)
        dl = f.get('deck_levels')
        if dl and dl.get('all'):
            s, da, db = entry_from_curves(dl['all']['a'], dl['all']['b'])
            if s is not None:
                pro['curve_a'], pro['curve_b'] = da[s:].round(1).tolist(), db[s:].round(1).tolist()
                sw = (f.get('pro_decision') or {}).get('bass_swap_bar')
                if sw is not None: pro['swap_after_entry'] = round(sw - s, 1)
        out.append(dict(id=f['id'], src='corpus_v2', split='corpus', dj=f['dj'], mix=f['mix_id'], a=a, b=b, sa=sa, sb=sb, hint=None, pro_clip=None, pro=pro))
    return out

def _reuse(rec, variant, src_variant, why):
    p = os.path.join(CK, src_variant + '.jsonl')
    rows = {json.loads(l)['id']: json.loads(l) for l in open(p)} if os.path.exists(p) else {}
    r = rows.get(rec['id'])
    if r is None or r.get('error'): return None
    r = dict(r); r['variant'] = variant; r['reused_from'] = src_variant; r['reuse_why'] = why; r['sec'] = 0
    with open(os.path.join(CK, variant + '.jsonl'), 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX); f.write(json.dumps(r, default=str) + '\n')
    return r

def _lazy(rec, rules):
    """identical-window shortcut: REPLICA=gated renders exactly the default when the gate abstains; REPLICA=1 renders exactly the
    gated window when the gate passes (primary detector = same window), and the default when no window exists."""
    m = str(rules.get('REPLICA') or '').lower()
    if m not in ('gated', '1') or len(rules) and any(k for k in rules.get('_extra', [])): return None
    sys.path.insert(0, paths.SRC2); os.chdir(paths.SRC2)
    import replica_rule as RR, sections as S
    sa, sb = S.get(rec['a']), S.get(rec['b'])
    g, gi = RR.gate(sa, sb, a_id=rec['a'])
    if m == 'gated': return None if g else ('default', 'gate abstained: ' + gi['why'])
    w, _ = RR.window(sa, sb, a_id=rec['a'])
    if g: return ('gated', 'gate passed: same primary window')
    if not w: return ('default', 'no replica window')
    return None

def _worker(job):
    rec, rules, variant, tag = job
    sys.path.insert(0, P); sys.path.insert(0, H)
    import recreate, hardcheck as HC
    t0 = time.time()
    if os.environ.get('LAZY') == '1':
        try:
            lz = _lazy(rec, rules)
        except Exception:
            lz = None
        if lz:
            r = _reuse(rec, variant, ('default' if lz[0] == 'default' else 'gated') if variant in ('gated', 'on') else lz[0], lz[1])
            if r is not None: return r
    try:
        info = recreate.recreate(rec['a'], rec['b'], rec['sa'], rec['sb'], hint_a_played_sec=rec['hint'], rules=rules, tag=tag)
        os.chdir(paths.SRC2); hc = HC.check(info['meta_path']); od = HC.ours_decisions(info['meta_path'], info['win'])
        row = dict(id=rec['id'], src=rec['src'], split=rec['split'], dj=rec['dj'], mix=rec['mix'], fam=info['fam'], win=info['win'],
                   replica=info.get('replica'), hard=hc, ours={k: v for k, v in od.items() if not k.startswith('curve')},
                   fade_err=HC.fade_err(od, rec['pro']['curve_a'], rec['pro']['curve_b']), meta=info['meta_path'], mp3=info.get('ours'))
        p = rec['pro']
        row['err'] = dict(exit=abs(od['out_bar'] - p['out_bar']), cue=abs(od['in_bar'] - p['in_bar']),
                          overlap=None if od['overlap'] is None or p['overlap'] is None else abs(od['overlap'] - p['overlap']),
                          swap=None if od['swap_after_entry'] is None or p['swap_after_entry'] is None else abs(od['swap_after_entry'] - p['swap_after_entry']))
        if rec['pro_clip']:
            import score
            sc = score.score(rec['pro_clip'], info['ours'], src_a=rec['sa'], src_b=rec['sb'], use_demucs=False, cache=paths.CACHE)
            row['sim_diag'] = sc['score']
    except Exception as ex:
        row = dict(id=rec['id'], src=rec['src'], split=rec['split'], dj=rec['dj'], mix=rec['mix'], error=f'{type(ex).__name__}: {ex}'[-300:], tb=traceback.format_exc()[-600:])
    row['sec'] = round(time.time() - t0); row['variant'] = variant
    with open(os.path.join(CK, variant + '.jsonl'), 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX); f.write(json.dumps(row, default=str) + '\n')
    return row

def done(variant):
    p = os.path.join(CK, variant + '.jsonl')
    return {json.loads(l)['id'] for l in open(p)} if os.path.exists(p) else set()

if __name__ == '__main__':
    base = json.load(open(paths.RULES)); assert not base.get('REPLICA'), 'rules.json must keep REPLICA off'
    W = int(os.environ.get('WORKERS', 3)); only = os.environ.get('ONLY')
    R = pairs(); print('pairs', len(R), {s: sum(1 for r in R if r['src'] == s) for s in ('protrans', 'corpus_v2')}, flush=True)
    FZ = os.path.join(H, 'frozen_ids.json')
    if only: R = [r for r in R if r['src'] == only or r['id'] in only.split(',') or r['mix'] in only.split(',')]
    elif os.path.exists(FZ): fz = set(json.load(open(FZ))['ids']); R = [r for r in R if r['id'] in fz]
    jobs = []
    for arg in sys.argv[1:]:
        v, js = arg.split('=', 1); rr = copy.deepcopy(base); rr.update(json.loads(js)); have = done(v)
        for i, r in enumerate(R):
            if r['id'] not in have: jobs.append((r, rr, v, f'g{v[:4]}{i}'))
    print('jobs', len(jobs), flush=True)
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(max_workers=W) as ex:
        for fut in as_completed([ex.submit(_worker, j) for j in jobs]):
            r = fut.result()
            print(r['variant'], r['id'], r.get('fam'), r.get('win'), 'ERR ' + r['error'] if r.get('error') else
                  f"exit {r['err']['exit']:.0f} cue {r['err']['cue']:.0f} hard {'FAIL' if r['hard']['hard_fail'] else 'ok'} {r['sec']}s", flush=True)
