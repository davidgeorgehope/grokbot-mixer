"""Fetch sources, cut clips, version-gate, and drop files we do not need."""
from __future__ import annotations
import json, os, sys, shutil, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, extract, fetch, version_match, cleanup

LEDGER = os.path.join(paths.RESULTS, 'admit_log.jsonl')
ADMITTED = os.path.join(paths.RESULTS, 'admitted.json')

def _log(row):
    os.makedirs(paths.RESULTS, exist_ok=True)
    with open(LEDGER,'a') as f: f.write(json.dumps(row)+'\n')
    print(row.get('verdict','?'), row.get('id'), row.get('reason') or row.get('pair'), flush=True)

def ensure_source(yt, min_duration=None):
    key = fetch.media_key(yt)
    dest = os.path.join(paths.LIB, f'{key}.m4a')
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        _reject_short_file(dest, min_duration)
        return dest
    os.makedirs(paths.LIB, exist_ok=True)
    fetch.ytdlp_remote(fetch.media_url(yt), dest)
    _reject_short_file(dest, min_duration)
    return dest


def _reject_short_file(path, min_duration):
    if not min_duration:
        return
    dur = fetch.audio_duration(path)
    if dur is not None and dur < float(min_duration):
        try:
            os.remove(path)
        except OSError:
            pass
        raise RuntimeError(f'preview too short ({dur:.1f}s < {float(min_duration):.1f}s needed)')

# Same confidence floor as the original YouTube resolver. Do not lower this.
CONFIDENT_MIN = 2


def score_search(title, r):
    """Score one search hit. Rules must stay identical to the original pick_search."""
    tl = title.lower()
    want = {'remix','vip','refix','edit','bootleg'}
    need = [w for w in want if w in tl]
    stop = {'the','and','feat','ft','featuring','with','for','you','mix','original','official','video','hq','hd'}
    toks=[t for t in ''.join(c if c.isalnum() else ' ' for c in tl).split() if len(t)>2 and t not in stop]
    core=[t for t in toks if len(t)>=4]
    rt=(r.get('title') or '').lower()
    ch=(r.get('channel') or '').lower()
    dur = fetch.parse_duration(r.get('duration')) or 0
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
    return s


def pick_search(title, results):
    best=None; best_s=-999
    for r in results:
        s = score_search(title, r)
        if best is None or s>best_s:
            best, best_s = r, s
    return best, best_s


def pick_search_ranked(title, results):
    """All hits with scores, best first. Scoring is the same as pick_search."""
    ranked = [(score_search(title, r), r) for r in results]
    ranked.sort(key=lambda x: -x[0])
    return ranked


def needed_source_duration(t_a=None, t_b=None, t_next=None, which='a'):
    """Lowest source length (seconds) so a preview can cover the blend window.

    The analysis clip is extract.PRE + extract.POST around the incoming cue.
    The outgoing also has to cover the listed slot (90-280 s). Incoming uses
    the listed slot until the next track (default 90 s).
    """
    import extract
    clip = float(extract.PRE) + float(extract.POST)
    if which == 'a':
        slot = (float(t_b) - float(t_a)) if (t_a is not None and t_b is not None) else 0.0
        return max(clip, slot)
    nxt = t_next if t_next is not None else ((float(t_b) + 90.0) if t_b is not None else None)
    slot = (float(nxt) - float(t_b)) if (nxt is not None and t_b is not None) else 90.0
    return max(clip, slot)


def fallback_queries(title):
    """Extra queries for non-YouTube sources only. YouTube keeps the original query."""
    qs = [title + ' drum and bass', title]
    cleaned = re.sub(r'\s*\[(?:forthcoming|preview|out now).*?\]\s*', ' ', title, flags=re.I)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if cleaned and cleaned != title:
        qs.extend([cleaned + ' drum and bass', cleaned])
    out, seen = [], set()
    for q in qs:
        if q and q not in seen:
            seen.add(q); out.append(q)
    return out


def _legacy_cache_path():
    return os.path.join(paths.LOGS, 'yt_search_cache.json')


def _source_cache_path():
    return os.path.join(paths.LOGS, 'source_search_cache.json')


def _load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except (ValueError, OSError):
            return default
    return default


def _save_json(path, obj):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    json.dump(obj, open(path, 'w'), indent=2)


def _preset_to_hit(preset):
    if isinstance(preset, dict) and (preset.get('id') or preset.get('yt') or preset.get('url')):
        hit = dict(preset)
        hit.setdefault('source', 'youtube' if not hit.get('source') else hit['source'])
        hit.setdefault('id', hit.get('yt') or hit.get('id'))
        hit.setdefault('url', fetch.media_url(hit))
        return hit
    if isinstance(preset, str) and preset.strip():
        s = preset.strip()
        if s.startswith('http://') or s.startswith('https://'):
            src = 'soundcloud' if 'soundcloud.com' in s.lower() else (
                'bandcamp' if 'bandcamp.com' in s.lower() else 'url')
            return dict(id=s, url=s, source=src, title='', channel='', duration='')
        return dict(id=s, url=f'https://youtu.be/{s}', source='youtube',
                    title='', channel='', duration='')
    return None


def _too_short(hit, min_duration):
    if not min_duration:
        return False
    dur = fetch.parse_duration(hit.get('duration'))
    if dur is None:
        return False  # unknown at search time; checked after download
    return dur < float(min_duration)


def _hit_from_pick(pick, source, score):
    hit = dict(pick)
    hit['source'] = source
    hit['score'] = score
    if not hit.get('url'):
        hit['url'] = fetch.media_url(hit if hit.get('source') else dict(pick, source=source))
    hit['id'] = str(hit.get('id') or '')
    return hit


def resolve_track(title, preset=None, min_duration=None):
    """Resolve a studio source, trying YouTube then SoundCloud then Bandcamp.

    The confidence gate is unchanged: pick_search score must be >= CONFIDENT_MIN.
    Hits shorter than min_duration are skipped (SoundCloud/Bandcamp previews),
    not accepted. Returns a dict with id, url, source, title, channel, duration, score.
    """
    preset_hit = _preset_to_hit(preset)
    if preset_hit:
        return preset_hit
    title = fetch.normalize_track_title(title)
    if not title:
        raise RuntimeError('empty title after normalize')
    title = fetch.strip_tracklist_tags(title) or title
    src_cache = _load_json(_source_cache_path(), {})
    yt_cache = _load_json(_legacy_cache_path(), {})
    cached = src_cache.get(title)
    if isinstance(cached, dict) and cached.get('url'):
        if not _too_short(cached, min_duration):
            return cached
    elif title in yt_cache:
        hit = _preset_to_hit(yt_cache[title])
        if hit and not _too_short(hit, min_duration):
            return hit

    last_rows = []
    last_sc = -999
    tried = []
    for source in fetch.SOURCE_ORDER:
        queries = [title + ' drum and bass'] if source == 'youtube' else fallback_queries(title)
        pick = None
        sc = -999
        rows_for_err = []
        for q in queries:
            try:
                rows = fetch.search_remote(q, n=8, source=source)
            except Exception as e:
                tried.append(f'{source}:{e}'[:120])
                continue
            rows_for_err = rows or rows_for_err
            last_rows = rows or last_rows
            ranked = pick_search_ranked(title, rows)
            for s, r in ranked:
                last_sc = max(last_sc, s)
                if s < CONFIDENT_MIN:
                    break
                if _too_short(r, min_duration):
                    tried.append(f"{source}: preview too short ({r.get('duration')}s < {min_duration}s) {r.get('title')!r}")
                    continue
                pick, sc = r, s
                break
            if pick:
                break
        if not pick:
            tried.append(f'{source}: no confident hit (best={last_sc})')
            continue
        hit = _hit_from_pick(pick, source, sc)
        src_cache[title] = hit
        _save_json(_source_cache_path(), src_cache)
        if source == 'youtube':
            yt_cache[title] = hit['id']
            _save_json(_legacy_cache_path(), yt_cache)
        print('search', title, '->', hit['source'], hit.get('id'), hit.get('title'),
              hit.get('channel'), 's', sc, flush=True)
        return hit

    titles = [r.get('title') for r in last_rows]
    raise RuntimeError(
        f'no confident search hit for {title!r} (score={last_sc}) rows={titles}'
    )


def resolve_yt(title, preset=None, min_duration=None):
    """Back-compat wrapper. YouTube hits still return the video id; others return a URL."""
    if preset and not isinstance(preset, dict):
        return preset
    hit = resolve_track(title, preset=preset, min_duration=min_duration)
    if (hit.get('source') or 'youtube') in ('youtube', 'yt'):
        return hit['id']
    return hit.get('url') or hit['id']

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
