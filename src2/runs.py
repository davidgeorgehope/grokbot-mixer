import json,numpy as np
def runs_of(b):
  g=json.load(open(f'st/{b}.json'));lo=np.array(g['bar']['low']);bass=lo>np.percentile(lo,90)-8
  runs=[];i=0
  while i<len(bass):
    if bass[i]:
      j=i
      while j<len(bass) and (bass[j] or (j+1<len(bass) and bass[j+1]) or (j+2<len(bass) and bass[j+2])):j+=1
      if j-i>=8:runs.append([i,j])
      i=j
    else:i+=1
  return runs,len(bass)
if __name__=='__main__':
  for b in json.load(open('order2.json'))['order']:print(b,runs_of(b))
