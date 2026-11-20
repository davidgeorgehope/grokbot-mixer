"""Pro-p95 calibration of drumclash. No engine/default writes.
Pro decks are aligned via source spectral chunk lines (with onset fine lag), then their gains are fit by nonnegative spectra.
The same measurement is applied to isolated rendered engine decks. A confidence failure is unmeasured, not a clean pass."""
import os,sys,json
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__)); PT=os.path.dirname(HERE)
sys.path[:0]=[PT,'/workspace/mixes/src2','/workspace/mixes/src/eval']
import drumclash as DC, score as S, diagnose_gap as DG, control_curves as CC
import run_admitted_tune as T

def assess(a,b,sr=22050,bar0=0):
    ea,eb=DC._env_from_audio(a),DC._env_from_audio(b)
    period=60/174; bar=4*period; W=int(round(2*bar/DC.DT)); nb=int(min(len(a),len(b))/sr/bar)
    def rms(y):
        return np.array([np.sqrt(np.mean(y[int(k*bar*sr):int((k+1)*bar*sr)]**2)+1e-12) for k in range(nb)])
    ra,rb=rms(a),rms(b); refa=np.percentile(ra,95); refb=np.percentile(rb,95); rows=[]
    for k in range(nb):
        if ra[k] < refa*.1 or rb[k] < refb*.1: continue
        i=int(k*bar/DC.DT); x,y=ea[i:i+W],eb[i:i+W]
        if min(len(x),len(y))<W//2:continue
        lag,cp,c0=DC.xcorr(x,y,period)
        off=(abs(lag)>DC.OFF_MS and cp-c0>DC.GAIN_MIN) or c0<DC.C0_MIN
        rows.append(dict(bar=k+bar0,lag_ms=round(lag,1),c_peak=round(cp,3),c0=round(c0,3),off=bool(off)))
    s=DC.summarize(rows);s['rows']=rows;return s

def pro(rec):
    y=S._load(rec['pro_clip']);Fm,em=CC.bandpow(y),S._fine_env(y);aligned=[];lines=[]
    for nm in ('a','b'):
        path=os.path.join(PT,'lib',rec[nm]['yt']+'.m4a'); ln=S._deck_line(y,Fm,em,path)
        if not ln or ln['r']<.2:return dict(error='deck not located '+nm, line=ln)
        src=S._load(path);t=(np.arange(len(y))/S.SR-ln['a'])/ln['s']; aligned.append(np.interp(t,np.arange(len(src))/S.SR,src,left=0,right=0).astype(np.float32));lines.append(ln)
    gains,_,times,hop=DG.band_gains(y,*aligned)
    tt=np.arange(len(y))/S.SR
    decks=[src*np.interp(tt,times,gains['all'][nm]) for src,nm in zip(aligned,('a','b'))]
    r=assess(*decks);r['lines']=lines;return r

def ours(rec,row):
    os.environ['BB_SCRATCH']='/tmp/protrans_bench';os.makedirs('/tmp/protrans_bench',exist_ok=True)
    import recreate,paths,blend_bench as BB,blend_diag as BD
    created=[]
    for nm in ('a','b'):recreate._prep_track(rec[nm]['yt'],os.path.join(paths.LIB,rec[nm]['yt']+'.m4a'),created)
    c=dict(row['pick']);c['env']=dict(c['env']);env=c['env'];old={k:os.environ.get(k) for k in env};os.environ.update(env)
    cwd=os.getcwd();os.chdir(paths.SRC2)
    try:
        dk,M=BB.render(c,rec['a']['yt'],rec['b']['yt'],f'dcal{os.getpid()}');s0,a,b=BD.crop_decks(M,0)
        import librosa
        r=assess(librosa.resample(a.mean(1),orig_sr=44100,target_sr=22050),librosa.resample(b.mean(1),orig_sr=44100,target_sr=22050),bar0=s0)
        r['win']=c['win'];r['lock']=M['trans'][0].get('blend_lock');r['meta']=f'/tmp/protrans_bench/dcal{os.getpid()}_{rec["a"]["yt"]}_{rec["b"]["yt"]}_meta.json'
        json.dump(M,open(r['meta'],'w'));return r
    finally:
        os.chdir(cwd)
        for k,v in old.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v

if __name__=='__main__':
    baseline=T.load_ckpt('n1120_base');out=[]
    for rec in T.load_recs():
        f=os.path.join(HERE,'cal_'+rec['id']+'.json')
        r=json.load(open(f)) if os.path.exists(f) else dict(id=rec['id'],split=rec['split'])
        if any(nm not in r or 'error' in r[nm] for nm in ('pro','ours')):
            for nm,fn in [('pro',lambda:pro(rec)),('ours',lambda:ours(rec,baseline[rec['id']]))]:
                if nm in r and 'error' not in r[nm]:continue
                try:r[nm]=fn()
                except Exception as e:r[nm]=dict(error=type(e).__name__+': '+str(e)[-300:])
            json.dump(r,open(f,'w'),indent=1)
        out.append(r);print(r['id'],{nm:{k:v for k,v in r[nm].items() if k not in ('rows','lines','lock')} for nm in ('pro','ours')},flush=True)
    vals=[r['pro']['score'] for r in out if 'score' in r['pro']];p95=float(np.percentile(vals,95));fails={nm:[r['id'] for r in out if r[nm].get('score',-1)>p95] for nm in ('pro','ours')}
    summary=dict(n_pro=len(vals),pro_p95=p95,flag_rule='score > pro_p95',flagged=fails,errors={nm:[r['id'] for r in out if 'error' in r[nm]] for nm in ('pro','ours')})
    json.dump(dict(summary=summary,rows=out),open(os.path.join(HERE,'detector_calibration.json'),'w'),indent=1);print('SUMMARY',summary,flush=True)
