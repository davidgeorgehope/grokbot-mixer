"""Resume the staged held-out growth using the existing ingestion pipeline only.

No alternate downloader, authentication flow, or scheduling is introduced.
Run with jobs/runjob.sh; a transport failure stops the run and is reported.
"""
import json, os
import admit, fetch, paths, cleanup

if __name__ == '__main__':
    q = json.load(open(os.path.join(paths.RESULTS, 'growth_queue.json')))
    train_djs = {r['dj'] for r in admit.load_admitted() if r['split'] == 'train'}
    for s in q['sets']:
        if s['dj'] in train_djs:
            raise ValueError('held-out DJ leakage: ' + s['dj'])
        # Confirm the actual set metadata through the normal transport first.
        meta = fetch.meta_remote('https://www.youtube.com/watch?v=' + s['yt'])
        dest = os.path.join(paths.CACHE, 'mixes', s['yt'] + '.m4a')
        try:
            fetch.ytdlp_remote(meta['webpage_url'], dest)
            results = admit.process_mix(s['id'], s['candidates'], dest, delete_mix=True)
            with open(os.path.join(paths.RESULTS, 'growth_ingestion.jsonl'), 'a') as out:
                for r in results: out.write(json.dumps(r) + '\n')
        finally:
            cleanup.drop_full_mix(dest, downloaded=True)
