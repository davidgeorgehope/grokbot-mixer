import sys,glob,os,time,json,numpy as np,soundfile as sf,librosa,torch
dev=sys.argv[1] if len(sys.argv)>1 else 'mps'
D=os.path.expanduser('~/ears/data'); out={}; T={}
wins=sorted(glob.glob(D+'/win/*.flac')); pros=sorted(glob.glob(D+'/pro/*.flac'))
def load(p,sr): y,s=sf.read(p,dtype='float32'); return librosa.resample(y,orig_sr=s,target_sr=sr) if s!=sr else y
# Beat This
from beat_this.inference import File2Beats
t=time.time(); f2b=File2Beats(checkpoint_path="final0",device=dev,dbn=False)
def beatm(p):
    b,db=f2b(p); ioi=np.diff(b); med=np.median(ioi)
    off=np.mean(np.abs(ioi-med)>0.06*med); cv=np.std(ioi)/np.mean(ioi)
    dbi=np.round(np.diff(db)/med); badbar=np.mean(dbi!=4) if len(dbi) else 1
    return dict(beat_cv=float(cv),beat_off=float(off),bar_bad=float(badbar),bpm=float(60/med))
for p in wins+pros: out.setdefault(os.path.basename(p),{}).update(beatm(p))
T['beat_this']=time.time()-t
# Basic Pitch
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
R={1:1,11:1,6:.5,2:.35,10:.35}
def diss(p):
    _,_,notes=predict(p,ICASSP_2022_MODEL_PATH)
    dur=sf.info(p).duration; fr=np.arange(0,dur,0.1); s=[];poly=[]
    for t0 in fr:
        pc=np.zeros(12)
        for st,en,pi,a,_ in notes:
            if st<=t0<en: pc[pi%12]+=a
        w=pc.sum(); poly.append((pc>0).sum())
        if w<=0: continue
        d=sum(pc[i]*pc[j]*R.get(abs(i-j)%12 if abs(i-j)%12<=6 else 12-abs(i-j)%12,0) for i in range(12) for j in range(i+1,12))
        # fold intervals: 11->1, 10->2
        s.append(d/w**2)
    s=np.array(s) if s else np.zeros(1)
    return dict(diss_mean=float(s.mean()),diss_p90=float(np.percentile(s,90)),poly=float(np.mean(poly)))
t=time.time()
for p in wins+pros: out[os.path.basename(p)].update(diss(p))
T['basic_pitch']=time.time()-t
# embeddings
from transformers import ClapModel,ClapProcessor,AutoModel,Wav2Vec2FeatureExtractor
def chunks(y,sr,L=10):
    n=int(L*sr); return [y[i:i+n] for i in range(0,len(y)-n+1,n//2)]
t=time.time(); cm=ClapModel.from_pretrained("laion/larger_clap_music").to(dev).eval(); cp=ClapProcessor.from_pretrained("laion/larger_clap_music")
def clap(p):
    c=chunks(load(p,48000),48000); x=cp(audios=c,sampling_rate=48000,return_tensors='pt').to(dev)
    with torch.no_grad(): e=cm.get_audio_features(**x)
    e=torch.nn.functional.normalize(e,dim=-1).cpu().numpy(); return e
EC={os.path.basename(p):clap(p) for p in wins+pros}; T['clap']=time.time()-t
t=time.time(); mm=AutoModel.from_pretrained("m-a-p/MERT-v1-95M",trust_remote_code=True).to(dev).eval(); mp=Wav2Vec2FeatureExtractor.from_pretrained("m-a-p/MERT-v1-95M",trust_remote_code=True)
def mert(p):
    es=[]
    for c in chunks(load(p,24000),24000):
        x=mp(c,sampling_rate=24000,return_tensors='pt').to(dev)
        with torch.no_grad(): h=mm(**x,output_hidden_states=True).hidden_states
        es.append(torch.stack(h)[[6,12]].mean(0).mean(1)[0].cpu().numpy())
    e=np.array(es); return e/np.linalg.norm(e,axis=1,keepdims=True)
EM={os.path.basename(p):mert(p) for p in wins+pros}; T['mert']=time.time()-t
for nm,E in (('clap',EC),('mert',EM)):
    pn=[os.path.basename(p) for p in pros]; P=np.concatenate([E[k] for k in pn]); own=np.concatenate([[i]*len(E[k]) for i,k in enumerate(pn)])
    for k,e in E.items():
        sims=e@P.T
        if k in pn: sims[:,own==pn.index(k)]=-9
        knn=1-np.sort(sims,1)[:,-5:].mean(1)
        out[k][nm+'_knn']=float(knn.mean()); out[k][nm+'_knnmax']=float(knn.max())
json.dump(dict(scores=out,time=T,dev=dev,n=len(wins)+len(pros)),open(os.path.expanduser(f'~/ears/res_{dev}.json'),'w'),indent=1)
print(T)
