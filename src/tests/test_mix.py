import glob,soundfile as sf,checks as C
def test_stretched_sources_are_44k1():
  bad=[f for f in glob.glob(f'{C.SRC}/st/*.wav') if sf.info(f).samplerate!=C.SR]
  assert not bad,f'sample-rate mismatch (plays at wrong speed/pitch): {bad}'
def test_beat_drift_across_transitions(T):
  bad=[(r['t'],r['a'],r['b'],r['drift_ms']) for r in T if r['drift_ms']>C.TOL_DRIFT_MS]; assert not bad,bad
def test_global_grid_no_drift():
  import numpy as np
  ref=C.ref_phase();dev=[(b,abs(((p-ref+43)%86.2)-43)) for b in range(0,len(C.bar_rms())-4,8) if (p:=C.phase_ms(b)) is not None]
  bad=[(round(b*C.BAR/60,2),round(d,1)) for b,d in dev if d>C.TOL_DRIFT_MS];assert len(bad)<=len(dev)*0.03,bad[:20]
def test_downbeats_aligned(T):
  assert all(float(d['start_bar']).is_integer() for d in C.decks())
  bad=[(r['t'],r['a'],r['b'],r['downbeat_A'],r['downbeat_B']) for r in T for x in (r['downbeat_A'],r['downbeat_B']) if abs(x['lag_ms'])>C.TOL_DRIFT_MS];assert not bad,bad
def test_beat_overlap_16_bars(T):
  bad=[(r['t'],r['a'],r['b'],r['overlap_bars']) for r in T if not r['echo'] and r['overlap_bars']<C.MIN_OVERLAP];assert not bad,bad
def test_no_key_clash(T):
  bad=[(r['t'],r['keys'],r['harm_overlap']) for r in T if not r['key_ok'] and r['harm_overlap']>2];assert not bad,bad
def test_anchor_tracks_long_enough():
  m=C.meta();anchors=[p['id'] for p in m['plan'] if p.get('anchor')]
  for a in anchors:
    d=[x for x in C.decks() if x['id']==a and not x['acap']][0];s=(d['end_bar']-d['start_bar'])*C.BAR
    assert s>=C.MIN_ANCHOR_S,f'{a} only {s:.0f}s'
def test_no_unintentional_energy_drops():
  bad=[e for e in C.energy_events() if not e['phrase'] and not e['echo']];assert not bad,bad
def test_no_abrupt_cuts():
  bad=[e for e in C.energy_events() if e['cut'] and not e['echo']];assert not bad,bad
  for d in C.decks():
    if d['echo'] or d['acap'] or d is C.decks()[-1]:continue
    e=d['end_bar']-0.01;lvl=max(C.gain_at(d,k,e) for k in('mid','high'))*C.gain_at(d,'gain',e)
    assert lvl<0.1 or d['end_bar']>=max(x['end_bar'] for x in C.decks())-1,f"{d['id']} ends at gain {lvl:.2f} (hard cut)"
def test_true_peak():
  tp,I=C.true_peak();assert tp<=C.TP_MAX,f'true peak {tp} dBTP (I={I} LUFS)'
def test_every_deck_on_its_planned_bar():
  bad=[]
  for d in C.decks():
    if d['acap'] or d['end_bar']-d['start_bar']<24:continue
    mid=(d['start_bar']+d['end_bar'])//2;a=C.deck_alignment(d,mid)
    if abs(a['lag_ms'])>C.TOL_DRIFT_MS:bad.append((d['id'],round(mid*C.BAR/60,2),a))
  assert not bad,bad
def test_no_vocal_clash():
  bad=[c for c in C.vocal_clashes() if not c['whitelisted'] and c['bars']>=1];assert not bad,bad
def test_mixdown_beats_aligned_every_overlap_bar():
  R=C.bar_alignment_report();bad=[r for r in R if abs(r['lag'])>C.TOL_DRIFT_MS]
  assert len(R)>50,'too few measurable overlap bars'
  assert not bad,f'{len(bad)}/{len(R)} overlap bars off by >10ms: {bad[:15]}'
