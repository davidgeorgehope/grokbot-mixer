"""Checkpointed paired scorer audit; no engine rule or score-weight tuning."""
import os,sys,json,importlib.util,traceback
from concurrent.futures import ProcessPoolExecutor,as_completed
import paths,recreate,score
OUT=os.path.join(paths.RESULTS,'event_detector_audit.jsonl')

def worker(row):
    spec=importlib.util.spec_from_file_location('old_score',os.path.join(paths.RESULTS,'score_before_event_calibration.py'))
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    cid=row['id'];sa=os.path.join(paths.LIB,row['a']['yt']+'.m4a');sb=os.path.join(paths.LIB,row['b']['yt']+'.m4a')
    info=None
    try:
        info=recreate.recreate(row['a']['yt'],row['b']['yt'],sa,sb,hint_a_played_sec=row['t_b']-row['t_a'],rules=recreate.load_rules(),tag='events_'+cid)
        pro=row.get('pro_clip') or os.path.join(paths.CLIPS,row['split'],cid,'pro.wav')
        before=old.score(pro,info['ours'],sa,sb,use_demucs=False)
        after=score.score(pro,info['ours'],sa,sb,use_demucs=False)
        return dict(id=cid,split=row['split'],before=before,after=after)
    except Exception:
        return dict(id=cid,split=row['split'],error=traceback.format_exc())
    finally:
        if info:
            import glob
            for p in glob.glob('/tmp/protrans_bench/events_'+cid+'*'):
                if os.path.isfile(p):os.remove(p)

if __name__=='__main__':
    import talkover
    bad=talkover.flagged_ids()
    rows=[r for r in json.load(open(os.path.join(paths.RESULTS,'admitted.json'))) if r['id'] not in bad]
    have={json.loads(l)['id'] for l in open(OUT) if not json.loads(l).get('error')} if os.path.exists(OUT) else set()
    with ProcessPoolExecutor(max_workers=3) as ex:
        for f in as_completed([ex.submit(worker,r) for r in rows if r['id'] not in have]):
            r=f.result()
            with open(OUT,'a') as out:out.write(json.dumps(r)+'\n')
            print(r['id'],r.get('error') or (r['before']['score'],r['after']['score']),flush=True)
