"""Fetch sources, cut clips, version-gate, and drop files we do not need."""
from __future__ import annotations
import json, os, sys, shutil, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, extract, fetch, version_match, cleanup

LEDGER = os.path.join(paths.RESULTS, 'admit_log.jsonl')
ADMITTED = os.path.join(paths.RESULTS, 'admitted.json')

def _log(row):
    os.makedirs(paths.RESULTS, exist_ok=True)
    with open(LEDGER,'a') as f: f.write(json.dumps(row)+'\n')
    print(row.get('verdict','?'), row.get('id'), row.get('reason') or row.get('pair'), flush=True)

def ensure_source(yt):
    dest = os.path.join(paths.LIB, f'{yt}.m4a')
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return dest
    os.makedirs(paths.LIB, exist_ok=True)
    fetch.ytdlp_remote(f'https://youtu.be/{yt}', dest)
    # drop remote copy
    return dest

def pick_search(title, results):
    tl = title.lower()
    want = {'remix','vip','refix','edit','bootleg'}
    need = [w for w in want if w in tl]
    stop = {'the','and','feat','ft','featuring','with','for','you','mix','original','official','video','hq','hd'}
    toks=[t for t in ''.join(c if c.isalnum() else ' ' for c in tl).split() if len(t)>2 and t not in stop]
    core=[t for t in toks if len(t)>=4]
    best=None; best_s=-999
    for r in results:
        rt=(r.get('title') or '').lower()
        ch=(r.get('channel') or '').lower()
        try: dur=float(r.get('duration') or 0)
        except (TypeError, ValueError): dur=0
        s=0
        if any(x in rt for x in ('lyric','nightcore','8d audio','sped up','slowed','mashup','yearmix','best of')): s -= 8
        if dur and dur > 600: s -= 15
        for w in need:
            if w in rt: s += 4
            else: s -= 4
        if 'remix' in rt and 'remix' not in tl: s -= 5
        if 'mashup' in rt: s -= 8
        hit=sum(1 for tok in toks if tok in rt)
        miss=sum(1 for tok in toks if tok not in rt)
        s += hit * 2
        s -= miss * 2
        s -= sum(5 for tok in core if tok not in rt)
        if any(k in ch for k in ('hospital','med school','ram record','liquicity','ukf','shogun','critical music','spearhead')):
            s += 3
        if best is None or s>best_s:
            best, best_s = r, s
    return best, best_s


def resolve_yt(title, preset=None):
    if preset: return preset
    cache_p = os.path.join(paths.LOGS, 'yt_search_cache.json')
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    if title in cache: return cache[title]
    rows = fetch.search_remote(title + ' drum and bass', n=8)
    pick, sc = pick_search(title, rows)
    if not pick or sc < 2:
        raise RuntimeError(f'no confident search hit for {title!r} (score={sc}) rows={[r.get("title") for r in rows]}')
    cache[title]=pick['id']
    os.makedirs(paths.LOGS, exist_ok=True)
    json.dump(cache, open(cache_p,'w'), indent=2)
    print('search', title, '->', pick['id'], pick.get('title'), pick.get('channel'), 's', sc, flush=True)
    return pick['id']

def load_admitted(filtered=True):
    rows = json.load(open(ADMITTED)) if os.path.exists(ADMITTED) else []
    if not filtered:
        return rows
    import talkover, real_blend
    bad = talkover.flagged_ids()
    return [r for r in rows if r['id'] not in bad and real_blend.eligible(r)]


def apply_real_blend():
    import real_blend
    rows = load_admitted(filtered=False)
    keep, drop = [], []
    for row in rows:
        result = real_blend.check_row(row)
        row['real_blend'] = result
        (drop if result['flagged'] else keep).append(row)
    p = os.path.join(paths.RESULTS, 'real_blend_rejected.json')
    old = json.load(open(p)) if os.path.exists(p) else []
    merged = {r['id']: r for r in old + drop}
    json.dump(list(merged.values()), open(p, 'w'), indent=2)
    save_admitted(keep)
    return keep, drop

def apply_talkover(rows=None):
    """Drop talkover-flagged rows from admitted.json into results/talkover_rejected.json."""
    import talkover
    rows = load_admitted(filtered=False) if rows is None else rows
    bad = talkover.flagged_ids()
    keep = [r for r in rows if r['id'] not in bad]
    drop = [r for r in rows if r['id'] in bad]
    p = os.path.join(paths.RESULTS, 'talkover_rejected.json')
    old = json.load(open(p)) if os.path.exists(p) else []
    seen = {r['id'] for r in old}
    json.dump(old + [r for r in drop if r['id'] not in seen], open(p, 'w'), indent=2)
    save_admitted(keep)
    return keep, drop

def save_admitted(rows):
    json.dump(rows, open(ADMITTED,'w'), indent=2)

def sources_in_use(rows):
    used=set()
    for r in rows:
        if r.get('a',{}).get('yt'): used.add(r['a']['yt'])
        if r.get('b',{}).get('yt'): used.add(r['b']['yt'])
    return used

def drop_unused_sources(keep):
    if not os.path.isdir(paths.LIB): return
    for n in os.listdir(paths.LIB):
        if not n.endswith('.m4a'): continue
        yt=n[:-4]
        if yt not in keep:
            cleanup._rm(os.path.join(paths.LIB, n))
            print('drop unused source', yt, flush=True)

def process_pair(c, mix_audio):
    rec = dict(
        id=c['id'], mix_id=c['mix_id'], dj=c['dj'], split=c['split'],
        a=dict(title=c['a']['title'], yt=c['a']['yt'], t=c['t_a']),
        b=dict(title=c['b']['title'], yt=c['b']['yt'], t=c['t_b']),
        window=dict(mix_t_a=c['t_a'], mix_t_b=c['t_b'], mix_t_next=c.get('t_next', c['t_b']+90),
                    hint_a_played_sec=c['t_b']-c['t_a']),
    )
    rec = extract.extract_one(rec, mix_audio)
    sa = ensure_source(rec['a']['yt'])
    sb = ensure_source(rec['b']['yt'])
    gate = version_match.match_pair(rec['pro_clip'], sa, sb, incoming_off=extract.PRE)
    row = dict(
        id=rec['id'], dj=c['dj'], split=c['split'], mix_id=c['mix_id'],
        mix_url=c.get('mix_url'), pair=f"{c['a']['title']} -> {c['b']['title']}",
        t_a=c['t_a'], t_b=c['t_b'],
        a=dict(title=c['a']['title'], yt=c['a']['yt']),
        b=dict(title=c['b']['title'], yt=c['b']['yt']),
        gate=gate, pro_clip=rec['pro_clip'],
        verdict='admit' if gate.get('passed') else 'reject',
        reason='; '.join(gate.get('reasons') or []) or None,
    )
    if gate.get('passed'):
        import talkover
        tk = talkover.check_row(row)
        row['talkover'] = {k: tk.get(k) for k in ('talk_s', 'talk_frac', 'flagged')}
        if tk.get('flagged'):
            row['verdict'] = 'reject'; row['reason'] = f"dj_talkover {tk['talk_s']}s"
            gate['passed'] = False
    if gate.get('passed'):
        import real_blend
        blend = real_blend.check_row(row)
        row['real_blend'] = blend
        if blend['flagged']:
            row['verdict'] = 'reject'
            row['reason'] = 'not_real_blend: ' + blend['reason']
            gate['passed'] = False
    if not gate.get('passed'):
        # drop clip if rejected
        shutil.rmtree(os.path.dirname(rec['pro_clip']), ignore_errors=True)
        row['pro_clip']=None
    _log(row)
    return row

def process_mix(mix_id, candidates, mix_path, delete_mix=True):
    admitted = load_admitted()
    have={r['id'] for r in admitted}
    rejected_path = os.path.join(paths.RESULTS, 'version_rejected.json')
    if os.path.exists(rejected_path):
        have.update(r['id'] for r in json.load(open(rejected_path)))
    results=[]
    for c in candidates:
        if c['id'] in have:
            print('skip already admitted', c['id'], flush=True)
            continue
        # resolve ids
        try:
            c['a']['yt']=resolve_yt(c['a']['title'], c['a'].get('yt'))
            c['b']['yt']=resolve_yt(c['b']['title'], c['b'].get('yt'))
        except Exception as e:
            row=dict(id=c['id'], dj=c.get('dj'), split=c.get('split'), mix_id=mix_id,
                     pair=f"{c['a']['title']} -> {c['b']['title']}", t_a=c['t_a'], t_b=c['t_b'],
                     verdict='reject', reason=f'resolve: {e}'[:300])
            _log(row); results.append(row); continue
        try:
            row=process_pair(c, mix_path)
        except Exception as e:
            row=dict(id=c['id'], dj=c.get('dj'), split=c.get('split'), mix_id=mix_id,
                     pair=f"{c['a']['title']} -> {c['b']['title']}", t_a=c['t_a'], t_b=c['t_b'],
                     verdict='reject', reason=f'error: {e}'[:300])
            _log(row)
        results.append(row)
        have.add(c['id'])
        if row.get('verdict')=='admit':
            admitted.append({k:row[k] for k in row if k!='gate'} | {'gate': row.get('gate')})
            save_admitted(admitted)
        keep=sources_in_use(admitted)
        pending=[x for x in candidates if x['id'] not in have]
        for x in pending:
            if x['a'].get('yt'): keep.add(x['a']['yt'])
            if x['b'].get('yt'): keep.add(x['b']['yt'])
        drop_unused_sources(keep)
    drop_unused_sources(sources_in_use(load_admitted()))
    if delete_mix and mix_path:
        # only delete if under pro_sets or cache/mixes
        ap=os.path.abspath(mix_path)
        allow=[os.path.abspath(os.path.join(paths.MIXES,'pro_sets')),
               os.path.abspath(os.path.join(paths.CACHE,'mixes'))]
        if any(ap.startswith(a+os.sep) or os.path.dirname(ap)==a for a in allow):
            cleanup._rm(ap)
            print('deleted mix', ap, flush=True)
    return results

if __name__ == '__main__':
    print('import admit helpers')
