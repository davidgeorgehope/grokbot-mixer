import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt,numpy as np
# fault classes x stage coverage. 2=checked exactly, 1=weak proxy, 0=blind
stages=['pair table /\nsearch','dry\n(meta only)','render\nguardrails','render\npytest']
rows=[('vocal clash',[1,2,2,2],6,'dry'),('drums-only stretch',[1,2,0,2],3,'dry'),('see-saw',[1,2,2,2],1,'dry'),
('E4 quiet stretch (level model)',[0,2,2,2],1,'dry'),('structure (drop landing)',[1,2,0,2],1,'dry'),
('E1 energy hole (solo breakdown)',[0,0,2,2],2,'render'),('N1 entry level step',[1,1,2,2],1,'render'),
('N1 entry off grid',[0,0,2,2],1,'render'),('bass gap in overlap',[0,0,0,2],2,'render'),('level dip at EQ swap',[0,0,0,2],1,'render'),
('beats not aligned (overlap)',[0,0,1,2],1,'render'),('abrupt outgoing audio tail',[0,1,0,2],1,'render'),('true peak',[0,0,2,2],1,'render')]
fig,(ax,bx)=plt.subplots(1,2,figsize=(15,7.2),gridspec_kw=dict(width_ratios=[1.35,1]))
M=np.array([r[1] for r in rows]);cm=matplotlib.colors.ListedColormap(['#d9534f','#f0ad4e','#5cb85c'])
ax.imshow(M,cmap=cm,vmin=0,vmax=2,aspect='auto')
ax.set_xticks(range(4));ax.set_xticklabels(stages,fontsize=9);ax.set_yticks(range(len(rows)))
ax.set_yticklabels([f"{r[0]}  (x{r[2]})" for r in rows],fontsize=9)
for i,r in enumerate(rows):
  for j,v in enumerate(r[1]):ax.text(j,i,['blind','proxy','exact'][v],ha='center',va='center',fontsize=8,color='white' if v!=1 else 'black')
ax.axhline(4.5,color='k',lw=2);ax.text(3.6,2,'caught\nat dry',fontsize=8,va='center');ax.text(3.6,9,'caught only\nafter render',fontsize=8,va='center')
ax.set_title('Mix 10: which stage can see each fault class\n(xN = times it hit Mix 10)',fontsize=11)
# funnel of plans
lab=['plans passed\npair table','orders dry-tested','dry ALL OK','passed render\n+ tests']
val=[83068+118788+100743+22689+31732,56,3,0]
bx.barh(range(4)[::-1],[np.log10(v+1) for v in val],color=['#5bc0de','#5bc0de','#f0ad4e','#d9534f'])
for i,v in enumerate(val):bx.text(np.log10(v+1)+0.05,3-i,f'{v:,}',va='center',fontsize=10)
bx.set_yticks(range(4)[::-1]);bx.set_yticklabels(lab,fontsize=9);bx.set_xlim(0,6.6);bx.set_xticks([])
bx.set_title('Mix 10 funnel, searches r1 to r6 (log scale)\n22 audio faults: 12 caught at dry, 10 only after render',fontsize=11)
bx.text(0.0,-0.14,'Dry ALL OK plans: r5 (render: E1 + N1), r6 (Memory Lane\nhole, found by hand), r6c (render: 7 faults).\nRepair runs r6, r6b, r6d ended on budget.',fontsize=8.5,transform=bx.transAxes,va='top')
plt.tight_layout();plt.savefig('/workspace/mixes/deliver/protrans/diagnostics/rca_2026-11-24_mix10_failure_loop.png',dpi=110,bbox_inches='tight')
