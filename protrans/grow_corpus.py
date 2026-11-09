"""Resume staged held-out growth via the existing ingestion pipeline only.

Uses fetch.meta_remote / fetch.ytdlp_remote and admit.process_mix so every
candidate still faces version, talkover and real-blend gates. New DJs are
forced into split=test; a DJ already present in train is refused. Progress
and transport failures are written under results/ and jobs/.
"""
from __future__ import annotations
import json, os, traceback, time
import admit, fetch, paths, cleanup

QUEUE = os.path.join(paths.RESULTS, 'growth_queue.json')
PROGRESS = os.path.join(paths.RESULTS, 'growth_progress.json')
INGEST_LOG = os.path.join(paths.RESULTS, 'growth_ingestion.jsonl')


def load_progress():
    return json.load(open(PROGRESS)) if os.path.exists(PROGRESS) else dict(sets={}, candidates={})


def save_progress(p):
    tmp = PROGRESS + '.tmp'
    json.dump(p, open(tmp, 'w'), indent=2)
    os.replace(tmp, PROGRESS)


def heldout_count():
    return sum(1 for r in admit.load_admitted() if r.get('split') == 'test')


if __name__ == '__main__':
    q = json.load(open(QUEUE))
    progress = load_progress()
    train_djs = {r['dj'] for r in admit.load_admitted(filtered=False) if r.get('split') == 'train'}
    target = int(q.get('target_heldout') or 10)
    print(f'start held-out={heldout_count()} target={target} train_djs={sorted(train_djs)}', flush=True)
    for s in q['sets']:
        if s['dj'] in train_djs:
            raise SystemExit(f'held-out DJ leakage refused: {s["dj"]}')
        # Force held-out split on every candidate regardless of queued value.
        for c in s['candidates']:
            c['split'] = 'test'
            c['dj'] = s['dj']
        sid = s['id']
        st = progress['sets'].setdefault(sid, {})
        if st.get('status') == 'done':
            print('skip finished set', sid, flush=True)
            continue
        url = 'https://www.youtube.com/watch?v=' + s['yt']
        try:
            print('meta', sid, url, flush=True)
            meta = fetch.meta_remote(url)
            st['meta'] = dict(id=meta.get('id'), title=meta.get('title'),
                              channel=meta.get('channel'), duration=meta.get('duration'),
                              chapters=len(meta.get('chapters') or []))
            save_progress(progress)
            dest = os.path.join(paths.CACHE, 'mixes', s['yt'] + '.m4a')
            if not (os.path.exists(dest) and os.path.getsize(dest) > 1000):
                print('download', sid, dest, flush=True)
                fetch.ytdlp_remote(meta.get('webpage_url') or url, dest)
            st['downloaded'] = dest
            st['bytes'] = os.path.getsize(dest)
            save_progress(progress)
            print('admit', sid, 'candidates', len(s['candidates']), flush=True)
            results = admit.process_mix(sid, s['candidates'], dest, delete_mix=True)
            with open(INGEST_LOG, 'a') as out:
                for r in results:
                    out.write(json.dumps(r) + '\n')
                    progress['candidates'][r['id']] = dict(
                        verdict=r.get('verdict'), reason=r.get('reason'),
                        split=r.get('split'), dj=r.get('dj'))
            st['status'] = 'done'
            st['n_results'] = len(results)
            st['n_admit'] = sum(1 for r in results if r.get('verdict') == 'admit')
            save_progress(progress)
            print('set done', sid, 'admit', st['n_admit'], 'held-out now', heldout_count(), flush=True)
            if heldout_count() >= target:
                print('target reached', heldout_count(), flush=True)
                break
        except Exception as e:
            st['status'] = 'failed'
            st['error'] = f'{type(e).__name__}: {e}'[:500]
            st['traceback'] = traceback.format_exc()[-1500:]
            save_progress(progress)
            print('FAILED', sid, st['error'], flush=True)
            raise
    summary = dict(heldout=heldout_count(), target=target, ts=time.strftime('%Y-%m-%d %H:%M:%S %Z'),
                   sets=progress['sets'], admitted_ids=[r['id'] for r in admit.load_admitted() if r.get('split')=='test'])
    json.dump(summary, open(os.path.join(paths.RESULTS, 'growth_summary.json'), 'w'), indent=2)
    print(json.dumps(summary, indent=2), flush=True)
