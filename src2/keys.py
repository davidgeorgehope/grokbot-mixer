import essentia.standard as es,glob,json,os,sys
CAM={('C','major'):'8B',('G','major'):'9B',('D','major'):'10B',('A','major'):'11B',('E','major'):'12B',('B','major'):'1B',('F#','major'):'2B',('Gb','major'):'2B',('C#','major'):'3B',('Db','major'):'3B',('G#','major'):'4B',('Ab','major'):'4B',('D#','major'):'5B',('Eb','major'):'5B',('A#','major'):'6B',('Bb','major'):'6B',('F','major'):'7B',
('A','minor'):'8A',('E','minor'):'9A',('B','minor'):'10A',('F#','minor'):'11A',('Gb','minor'):'11A',('C#','minor'):'12A',('Db','minor'):'12A',('G#','minor'):'1A',('Ab','minor'):'1A',('D#','minor'):'2A',('Eb','minor'):'2A',('A#','minor'):'3A',('Bb','minor'):'3A',('F','minor'):'4A',('C','minor'):'5A',('G','minor'):'6A',('D','minor'):'7A'}
src=sys.argv[1] if len(sys.argv)>1 else 'full'
out={}
for f in sorted(glob.glob('st/*.wav')):
  b=os.path.basename(f)[:-4]
  if b.endswith('_in'):continue
  a=es.MonoLoader(filename=f,sampleRate=44100)()
  r={}
  for p in ['edma','bgate','krumhansl','temperley']:
    k,s,st=es.KeyExtractor(profileType=p,sampleRate=44100)(a);r[p]=(CAM[(k,s)],k+' '+s,round(st,2))
  out[b]=r;print(b,r,flush=True)
json.dump(out,open(f'keys_{src}.json','w'),indent=1)
