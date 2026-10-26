import itertools,random,json
T={'luB7w7JBT14':('1A',3,'High Contrast – Around Me (ft. Dawn Joseph)'),'FYpf8-UvCUk':('4A',3,'Grafix – Half Life'),'YNz30crm5g0':('7B',1,'Etherwood – Souvenirs (ft. Zara Kershaw)'),'NaY3x3GRDF4':('7B',4,'Sub Focus & Metrik – Trip'),
'gbD9mt0T10g':('10B',2,'Hybrid Minds – Better Now (ft. Lily Denning)'),'7Itbo72XEz4':('4A',2,'Zero T & Aaliyah Esprit – When My Love'),'onLHBSeOOJg':('3A',2,'Son, Lottie Franklin – Fine Line'),
'j9AuFRpLk7U':('1A',3,'goddard. – Lillies (ft. Jazmine Johnson)'),'xENmcMSvZFI':('1A',5,'Sub Focus & Dimension – Ready To Fly'),
'5gFutO20uKA':('8A',3,'goddard. – Green Light (ft. Megan Linnell)'),'b7GXbX0kvcY':('11A',3,'Kaimen – Hopeless (ft. Nathan Rogue & Lottie Franklin)'),'1q43f05ChUs':('6A',4,'Bladerunner x Exile x Jess Robyn – In Your Eyes')}
def kc(a,b):
  na,ma=int(a[:-1]),a[-1];nb,mb=int(b[:-1]),b[-1];d=min((na-nb)%12,(nb-na)%12)
  if ma==mb: return {0:0,1:0.2,2:0.8}.get(d,1.5)
  if d==0:return 0.25
  if d==1:return 0.6
  return 1.5
def cost(o):
  c=0
  for a,b in zip(o,o[1:]):
    c+=kc(T[a][0],T[b][0]);de=T[b][1]-T[a][1];c+=0.3*max(0,-de)+0.2*max(0,abs(de)-1)
  c+=0.5*T[o[0]][1]+0.5*(5-T[o[-1]][1])
  return c
ks=list(T);best=None
random.seed(1)
for r in range(300):
  o=ks[:];random.shuffle(o);c=cost(o)
  for it in range(4000):
    i,j=sorted(random.sample(range(len(o)),2));n=o[:i]+o[i:j+1][::-1]+o[j+1:];cn=cost(n)
    if cn<=c:o,c=n,cn
  if best is None or c<best[0]:best=(c,o)
c,o=best;print(round(c,2))
for a,b in zip(o,o[1:]+[None]):print(T[a][0],T[a][1],T[a][2],'| next kc',kc(T[a][0],T[b][0]) if b else '')
json.dump(dict(order=o,meta=T),open('order2.json','w'),indent=1)
