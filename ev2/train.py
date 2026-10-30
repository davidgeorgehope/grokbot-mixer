"""Ears v2 trainer (runs on the GPU host, MPS). Small CNN on 8-bar log-mel windows; leave-one-set-out val."""
import numpy as np,torch,torch.nn as nn,json,sys
dev='mps' if torch.backends.mps.is_available() else 'cpu';torch.manual_seed(0)
D=np.load('train.npz');X=torch.tensor(D['X'].astype(np.float32));Y=torch.tensor(D['Y']).float();S=D['S']
X=(X+40)/20
def net():
  c=lambda i,o:nn.Sequential(nn.Conv2d(i,o,3,padding=1),nn.BatchNorm2d(o),nn.ReLU(),nn.MaxPool2d(2))
  return nn.Sequential(c(1,16),c(16,32),c(32,64),c(64,64),nn.AdaptiveAvgPool2d(1),nn.Flatten(),nn.Dropout(.3),nn.Linear(64,1))
def fit(idx,ep=25):
  m=net().to(dev);o=torch.optim.AdamW(m.parameters(),1e-3,weight_decay=1e-3);idx=np.array(idx)
  for e in range(ep):
    m.train();p=np.random.permutation(idx)
    for b in range(0,len(p),64):
      j=p[b:b+64];x=X[j].unsqueeze(1).to(dev)
      x=x+0.1*torch.randn_like(x)+ (torch.rand(len(j),1,1,1,device=dev)-.5)  # gain jitter
      l=nn.functional.binary_cross_entropy_with_logits(m(x).squeeze(1),Y[j].to(dev));o.zero_grad();l.backward();o.step()
  return m.eval()
def pred(m,Xe):
  with torch.no_grad():return torch.sigmoid(torch.cat([m(Xe[i:i+256].unsqueeze(1).to(dev)).squeeze(1).cpu() for i in range(0,len(Xe),256)])).numpy()
res={}
for s in np.unique(S):
  m=fit(np.where(S!=s)[0]);p=pred(m,X[S==s]);y=D['Y'][S==s];res[int(s)]=dict(acc=float(((p>.5)==y).mean()),n=int(len(y)));print('val set',s,res[int(s)],flush=True)
m=fit(np.arange(len(Y)));torch.save(m.state_dict(),'ears_v2.pt')
H=np.load('held.npz');ph=pred(m,(torch.tensor(H['X'].astype(np.float32))+40)/20)
blend=[float(np.percentile(ph[H['G']==g],75)) for g in range(len(H['R']))]
json.dump(dict(device=dev,loso=res,held=[dict(t=str(t),rating=float(r),current=str(c),p_bad=b) for t,r,c,b in zip(H['T'],H['R'],H['C'],blend)]),open('ears_v2_results.json','w'),indent=1)
print(open('ears_v2_results.json').read())
