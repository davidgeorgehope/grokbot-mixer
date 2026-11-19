"""Human / RCA-labelled cases from delivered diagnostics (titles redacted: they carry pick ids, scores and hard-check verdicts).
Labels come from the listener's ratings/comments in protrans/log.jsonl and the RCA docs. 'hard' = what the shipped hard checks said
at the time (every delivered clip passed them, which is the point: they missed the 11-17 clash and the 11-14 hole)."""
import json, os, sys
H = os.path.dirname(os.path.abspath(__file__)); D = '/workspace/mixes/deliver/protrans/diagnostics'
sys.path.insert(0, H); from redact import redact
OUT = os.path.join(H, 'redacted'); os.makedirs(OUT, exist_ok=True)
F = dict(beat_clash=False, bass_hole=False, level_pump=False, bad_cue=False)
def T(**k): return dict(F, **k)
CASES = [  # name, truth, basis, split
 ('daily_2026-11-17', T(beat_clash=True), "the listener 3/5 'There's some beat clashes'; RCA_2026-11-17 ~110-123 ms lag", 'dev'),
 ('rca_2026-11-17_after', T(), "BLEND_LOCK fix; listener: 'Yeah the beat clash is gone'", 'dev'),
 ('daily_2026-11-12', T(), 'the listener rated ours 4/5', 'dev'),
 ('daily_2026-11-15', T(), 'the listener rated ours 4/5', 'dev'),
 ('daily_2026-11-14', T(bass_hole=True, bad_cue=True), "the listener 2/5 'quite bad'; RCA_2026-11-14(+bass_cover): incoming bass-less intro under outgoing late drop, 8-10 bar summed-lows hole (22.5 dB)", 'heldout'),
 ('rca_2026-11-14_fix', T(), 'RCA fix render (hint_family: mid-track window, dip 11.9 dB); not rated by the listener', 'heldout'),
 ('daily_2026-11-13', T(), "the listener 4/5 'Really good'", 'heldout'),
 ('daily_2026-11-16', T(), "the listener could not tell ours from the pro", 'heldout'),
 ('rca_2026-11-11_engine', T(), "the listener on the rebuild: 'pretty good, that will do it'", 'heldout'),
]
PAIRS = [  # better, worse, basis, split
 ('rca_2026-11-17_after', 'daily_2026-11-17', 'beat clash fixed (the listener confirmed)', 'dev'),
 ('rca_2026-11-14_fix', 'daily_2026-11-14', 'RCA fix of bass hole / bad cue', 'heldout'),
 ('rca_2026-11-11_engine', 'rca_2026-11-11_engine_phrase_cut', "listener: engine 'pretty good', phrase_cut 'sounds off'", 'heldout'),
]
def main():
    names = {c[0] for c in CASES} | {p[0] for p in PAIRS} | {p[1] for p in PAIRS}
    for n in names: redact(os.path.join(D, n + '.png'), os.path.join(OUT, n + '.png'))
    with open(os.path.join(H, 'cases_human.jsonl'), 'w') as f:
        for n, t, b, s in CASES:
            f.write(json.dumps(dict(case='human__' + n, pair=n, split=s, source='human', png=os.path.join(OUT, n + '.png'), truth=t, truth_basis=b,
                                    hard=dict(beat_clash=False, bass_hole=False, pumping=False))) + '\n')
    with open(os.path.join(H, 'pairs_human.jsonl'), 'w') as f:
        for g, w, b, s in PAIRS:
            f.write(json.dumps(dict(case=f'hpair__{g}', better=os.path.join(OUT, g + '.png'), worse=os.path.join(OUT, w + '.png'), basis=b, split=s)) + '\n')
if __name__ == '__main__': main()
