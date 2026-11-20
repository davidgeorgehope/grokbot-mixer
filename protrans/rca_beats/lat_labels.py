import sys,json
sys.path.insert(0,'/workspace/mixes/src2'); import os; os.chdir('/workspace/mixes/src2')
import blend_diag as BD, drumclash as DC
L=[('hm09 B delivered','/tmp/protrans_bench/n1120b16_J3oTRY7AdE4_ksVDZt9_0J4_meta.json'),('JS12 A','/tmp/protrans_bench/lab_joe_syntax_hospital__12_meta.json'),('WAO B','/tmp/protrans_bench/lab_joe_syntax_hospital__11_meta.json'),('hm13 B','/tmp/protrans_bench/lab_hybrid_minds_ukf__13_meta.json')]
for nm,p in L:
    M=json.load(open(p)); s0,A,B=BD.crop_decks(M,0); t=M['trans'][0]
    r=DC.rendered_lattice(A,B,s0,float(t['start_bar']),float(t['end_bar'])); rows=r.pop('rows')
    print(nm,r); print('   ',[(x['bar'],x['n'],x.get('off_share'),x.get('med_dev_ms')) for x in rows if x['n']])
