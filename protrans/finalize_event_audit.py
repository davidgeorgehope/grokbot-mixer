"""Publish the paired calibration audit and current clean-corpus baseline locally."""
import json,os,shutil
import paths,score
from run_admitted_tune import summarize

def main():
    by={}
    for l in open(os.path.join(paths.RESULTS,'event_detector_audit.jsonl')):
        r=json.loads(l)
        if not r.get('error'):by[r['id']]=r
    old_rows=json.load(open(os.path.join(paths.RESULTS,'admitted_before_version_audit.json')))
    assert set(by)=={r['id'] for r in old_rows}, (len(by),len(old_rows))
    memory=json.load(open(os.path.join(paths.RESULTS,'memory_replacement_score.json')))
    assert not memory.get('error'),memory
    current=json.load(open(os.path.join(paths.RESULTS,'admitted.json')))
    def summary(rs,key):
        return {s:dict(n=sum(r['split']==s for r in rs),mean=round(sum(r[key]['score'] for r in rs if r['split']==s)/sum(r['split']==s for r in rs),2)) for s in ('train','test')}
    rs=list(by.values())
    corrected=[memory if r['id']==memory['id'] else by[r['id']] for r in current]
    audit=dict(paired_before=summary(rs,'before'),paired_after=summary(rs,'after'),corrected_corpus_after=summary(corrected,'after'),scorer_version=score.SCORER_VERSION,weights=score.W)
    json.dump(audit,open(os.path.join(paths.RESULTS,'event_audit_summary.json'),'w'),indent=2)
    target=os.path.join(paths.RESULTS,'baseline_clean.json')
    backup=os.path.join(paths.RESULTS,'baseline_clean_before_event_audit.json')
    if not os.path.exists(backup):shutil.copy2(target,backup)
    meta={r['id']:r for r in current};out=[]
    for r in corrected:
        sc=r['after'];sc['scorer_version']=score.SCORER_VERSION
        m=meta[r['id']]
        out.append(dict(id=r['id'],split=r['split'],dj=m['dj'],pair=m['pair'],score=sc['score'],breakdown=sc['breakdown'],scorer_version=score.SCORER_VERSION))
    weighted=[dict(r,score=dict(score=r['score'])) for r in out]
    baseline=dict(summary=summarize(weighted),rows=out,source_ckpt='event_detector_audit.jsonl + memory_replacement_score.json',scorer_version=score.SCORER_VERSION,excluded_version=[r['id'] for r in json.load(open(os.path.join(paths.RESULTS,'version_rejected.json')))])
    json.dump(baseline,open(target,'w'),indent=2)
    print(json.dumps(audit,indent=2))

if __name__=='__main__':main()
