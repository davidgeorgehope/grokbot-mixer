#!/usr/bin/env python3
"""Validate blend_gate on the Mix 10 history (known late faults vs blends that rendered clean). Writes eval/blend_gate_validation_mix10.json.
Ground truth = the full-render guardrails/pytest of mix10_r6 (r6c plan) and mix10_r5 (PROGRESS_mix10.md, guard_mix10_r*/)."""
import os,sys,json,time
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)));import blend_gate as BG
KNOWN={'mix10_r6':{2:('beats not aligned 11:43','test_mixdown_beats_aligned_every_overlap_bar'),3:('bass gap 15:22','test_no_bass_gap_in_overlaps'),
  6:('N1 off grid 21:22','N1'),9:('level dip at EQ swap 30:53','test_no_level_dip_at_swap'),13:('bass gap 40:44','test_no_bass_gap_in_overlaps'),
  18:('abrupt outgoing tail 53:42','test_outgoing_audio_tail_never_drops_abruptly')},
  'mix10_r5':{7:('N1 level step +3.8 dB 18:45','N1')}}
# held-out set (routing frozen before these ran): Mix 09 r3/r4/r5 render faults, Mix 09 r5b and Mix 08 r11c delivered clean
HOLDOUT={'mix09_r3':(9.3,{0:('bass gap bar 181','test_no_bass_gap_in_overlaps'),21:('N1 off grid 57:02 + beats not aligned bar 2488','N1')}),
  'mix09_r4':(9.3,{1:('bass gap bar 357','test_no_bass_gap_in_overlaps')}),
  'mix09_r5':(8.0,{0:('bass gap bar 197','test_no_bass_gap_in_overlaps'),11:('beats not aligned bar 1431','test_mixdown_beats_aligned_every_overlap_bar')}),
  'mix09_r5b':(8.0,{}),'mix08_r11c':(9.3,{})}
SOLO={'mix10_r5':[('E1 dip 14:24 (Hayling solo breakdown)',14*60+24)]}
def main(jobs=2,names=('mix10_r6','mix10_r5'),outname='blend_gate_validation_mix10.json'):
  os.chdir(BG.HERE);out=dict(started=time.strftime('%F %T %Z'),mix_level_routing=sorted(BG.MIX_LEVEL),code=BG.code_hash(),mixes={})
  for n in names:
    gain,K=HOLDOUT[n] if n in HOLDOUT else (9.0,KNOWN[n])
    M=json.load(open(f'{n}_meta.json'));t0=time.time();R=BG.gate_plan(M,gain,os.environ.get('NUDGE','nudge08_r9c.json'),jobs=jobs,use_cache=False)
    rows=[]
    for i,r in sorted(R.items()):
      checks=sorted({f['check'] for f in r['blend_fails']})
      row=dict(trans=i,a=r['a'],b=r['b'],t=r['mix_t'],ok=r['ok'],fails=checks,mix_level=sorted({f['check'] for f in r['mix_level']}),secs=r['secs'],
        known=K[i][0] if i in K else None,expected_check=K[i][1] if i in K else None)
      row['caught']=(i in K and K[i][1] in checks);row['false_fail']=(i not in K and not r['ok'])
      row['detail']=[f for f in r['blend_fails']][:6];rows.append(row)
    bar=M['bar_sec'];cover=[]
    for what,sec in SOLO.get(n,[]):
      b=sec/bar;cover.append(dict(fault=what,in_clip=[i for i,r in R.items() if r['clip_bars'][0]<=b<r['clip_bars'][1]]))
    out['mixes'][n]=dict(gain=gain,rows=rows,wall_s=round(time.time()-t0,1),solo_faults=cover,
      caught=sum(r['caught'] for r in rows),known=len(K),false_fails=sum(r['false_fail'] for r in rows),clean=len(rows)-len(K))
    print(n,'caught',out['mixes'][n]['caught'],'/',len(K),'false fails',out['mixes'][n]['false_fails'],'/',out['mixes'][n]['clean'],flush=True)
  S=[r['secs']['total'] for m in out['mixes'].values() for r in m['rows']]
  import numpy as np;out['per_blend_s']=dict(median=float(np.median(S)),p90=float(np.percentile(S,90)),max=max(S),n=len(S),
    render_median=float(np.median([r['secs']['render'] for m in out['mixes'].values() for r in m['rows']])))
  os.makedirs(os.path.join(BG.ROOT,'eval'),exist_ok=True)
  json.dump(out,open(os.path.join(BG.ROOT,'eval',outname),'w'),indent=1,default=str);print(json.dumps(out['per_blend_s']))
if __name__=='__main__':
  j=int(sys.argv[1]) if len(sys.argv)>1 else 2
  if len(sys.argv)>2 and sys.argv[2]=='holdout':main(j,tuple(HOLDOUT),'blend_gate_validation_holdout.json')
  else:main(j)
