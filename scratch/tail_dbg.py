import os,sys,json,numpy as np
os.environ.setdefault('NUDGE','nudge08_r9c.json');sys.path.insert(0,'.')
import engine as E,blend_gate as G;BS=E.BS
M=json.load(open('mix08_r11c_meta.json'));i=int(sys.argv[1]) if len(sys.argv)>1 else 19
s0,s1=G.clip_bounds(M,i);cm=G.shift_meta(M,i,G.crop_decks(M,s0,s1),s0,s1)
def run(M,i,tag):
  t=M['trans'][i];A=[d for d in M['decks'] if d['id']==t['a']][0];B=[d for d in M['decks'] if d['id']==t['b']][0]
  y=E.render_deck(A);dry=E.render_deck(dict(A,auto={}));d0=A['start_bar']
  db=lambda z,k:10*np.log10(np.mean(z[int((k-d0)*BS):int((k-d0+1)*BS)]**2)+1e-12)
  ks=range(int(t['start_bar']),int(t['end_bar']));G_=[db(y,k)-db(dry,k) for k in ks];ref=db(y,t['start_bar']-1);L=[db(y,k)-ref for k in ks]
  yb=E.render_deck(B);b0=B['start_bar'];dbb=lambda k:10*np.log10(np.mean(yb[int((k-b0)*BS):int((k-b0+1)*BS)]**2)+1e-12)
  print(tag,'d0',d0,'start',t['start_bar'],'ref',round(ref,1),'full',round(dbb(t['end_bar']+4),1),'lenA',len(y)/BS)
  print(' G',[round(g,1) for g in G_]);print(' L',[round(l,1) for l in L])
  print(' dry',[round(db(dry,k),1) for k in ks]);print(' B',[round(dbb(k),1) for k in ks])
  print(' sb',[A['full_map'][int(k-d0)][0] for k in ks])
run(M,i,'FULL');run(cm,0,'CLIP')
