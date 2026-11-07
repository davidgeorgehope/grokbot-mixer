#!/usr/bin/env python3
"""Isolated blend-bench sweep for mix07 r12 remaining fails. Does not full-render."""
import copy, json, os, sys, hashlib, traceback
import numpy as np
HERE = '/workspace/mixes/src2'
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.setdefault('BB_SCRATCH', '/tmp/bb_r15')
os.environ.update(LOOP32='0', ECHO_MAX='2', STRUCT='1', FADE='tail', PREF_W='0', PREFW='0',
                  SWAP_PHRASE='1', HIGH_SWAP='1', NUDGE='nudge07.json', PYTHONUNBUFFERED='1')
os.environ.pop('PAIR_TABLE', None); os.environ.pop('SOFT', None); os.environ.pop('TABLE_K', None)
import blend_bench as BB
import bassgap as G
import sections
from engine import BAR

SCR = BB.SCR
os.makedirs(SCR, exist_ok=True)
OUT = '/workspace/mixes/mix07/sweep_r15.json'
DROP_DB = 6.0
JHO, SOL = 'cxS6yd0UAxw', 'n1dOiesZS1g'
DAY, PAR = 'MoYkYkoeb84', '2s3M6oX2lfo'
JHO_EMIN, DAY_EMIN = 144, 96  # full-mix inn: JHO=80, Daydreaming=32
SRC_ALL = {}

def src_all(tid):
    if tid not in SRC_ALL:
        SRC_ALL[tid] = np.array(json.load(open(f'{HERE}/st/{tid}.json'))['bar']['all'])
    return SRC_ALL[tid]

def wkey(w):
    return [w[0], w[1], w[2], w[3], w[4]]

def dump_cands(a, b, tag):
    return BB.cands_for(a, b, tag)

def allowed_set(cs):
    return {tuple(c['win'] if isinstance(c, dict) else c) for c in (
        [dict(win=c['win']) for c in cs] if cs and isinstance(cs[0], dict) else cs)}

def drop_land(b, w):
    SB = sections.get(b)
    ib, X = w[3], w[4]
    kind = w[0]
    # lb/ab: incoming loops phrase ib for X bars then continues at ib+16; gold drop lands when ib == drop1-16
    if kind in ('lb', 'ab'):
        return ib + 16 == SB['drop1']
    return ib + X == SB['drop1']

def phrase_aligned(w):
    e, ib, X = w[1], w[3], w[4]
    return (e % 16 == 0) and (ib % 16 == 0) and (X in (16, 32)) and (w[2] is None or w[2] % 16 == 0)

def shift_meta(M, s0):
    M = copy.deepcopy(M)
    def sh_pts(pts):
        return [[p[0]-s0, p[1]] + list(p[2:]) for p in pts] if pts else pts
    for d in M['decks']:
        d['start_bar'] = d['start_bar'] - s0
        d['end_bar'] = d['end_bar'] - s0
        au = d.get('auto') or {}
        for k in list(au):
            if isinstance(au[k], list) and au[k] and isinstance(au[k][0], (list, tuple)):
                au[k] = sh_pts(au[k])
        if d.get('ib'):
            pass  # ib k0/k1 are deck-relative
    for t in M['trans']:
        for k in ('start_bar', 'end_bar', 'swap_bar', 'high_bar'):
            if t.get(k) is not None:
                t[k] = t[k] - s0
        if t.get('bass_swap'):
            t['bass_swap'] = [x - s0 for x in t['bass_swap']]
        if t.get('xfader'):
            t['xfader'] = [[p[0]-s0, p[1]] for p in t['xfader']]
    return M

def energy_events(M, wav):
    import soundfile as sf
    x, sr = sf.read(wav, dtype='float32', always_2d=True)
    bs = M['bar_sec'] * sr
    n = int(len(x) / bs)
    R = np.array([20*np.log10(np.sqrt(np.mean(x[int(i*bs):int((i+1)*bs)].mean(1)**2))+1e-9) for i in range(n)])
    ev = []
    decks = M['decks']
    echo_bars = {round(d['end_bar']) for d in decks if d.get('echo')}
    def deck_at(i):
        return [d for d in decks if d['start_bar'] <= i < d['end_bar']]
    def src_of(d, i):
        j = int(i - d['start_bar'])
        if j < 0 or j >= len(d['full_map']):
            return None
        return d['full_map'][j]
    for i in range(8, len(R)-1):
        base = np.median(R[i-8:i]); dlt = base - R[i]
        if dlt < DROP_DB or R[i-1] < base - DROP_DB:
            continue
        phr = False
        for xd in deck_at(i):
            if xd.get('acap'):
                continue
            so = src_of(xd, i)
            if not so or so[1] != 'mix':
                continue
            a = src_all(xd['id']); k = so[0]
            if k >= len(a):
                continue
            ctx = np.concatenate([a[max(0,k-8):k], a[k+1:k+9]]) if k < 8 else a[k-8:k]
            if len(ctx) and np.median(ctx) - a[k] >= dlt - 4:
                phr = True
        ech = any(abs(i - e) <= 1 for e in echo_bars)
        ev.append(dict(bar=i, drop_db=round(float(dlt),1), phrase=phr, echo=ech))
    return ev

def build_cands(a, b, emin, rated_win, extras):
    raw = dump_cands(a, b, f'dump_{a[:6]}_{b[:6]}')
    allowed = {tuple(c['win']) for c in raw}
    fams = BB.families(raw, rated_win)
    out = []
    seen = set()
    def add(fam, win, env=None, sneak=False):
        win = list(win)
        if tuple(win) not in allowed:
            return
        if win[1] < emin:
            return
        if win[4] > 16 and win[0] in ('la', 'lx') and int(os.environ.get('LOOP32', 0)) == 0:
            return
        key = (tuple(win), tuple(sorted((env or {}).items())), bool(sneak))
        if key in seen:
            return
        seen.add(key)
        out.append(dict(fam=fam, win=win, env=dict(env or {}), sneak=bool(sneak)))
    for c in fams:
        add(c['fam'], c['win'], c.get('env'), c.get('sneak'))
    for fam, win in extras:
        add(fam, win, {}, False)
        if drop_land(b, win) and win[0] == 'n':
            add(fam+'_swap_early', win, {'SWAP_POS':'0.21'}, False)
            add(fam+'_swap_late', win, {'SWAP_POS':'0.6'}, False)
    return out, raw

def eval_one(c, a, b, tag):
    rec = dict(fam=c['fam'], win=c['win'], env=c.get('env') or {}, sneak=bool(c.get('sneak')), tag=tag)
    try:
        dk, M = BB.render(c, a, b, tag)
        BB.measure(c, dk, M)
        rec['hard'] = c.get('hard') or []
        rec['feats'] = c.get('feats')
        rec['raw_m'] = c.get('raw')
        rec['tech'] = c.get('tech')
        rec['notes'] = c.get('notes')
        rec['struct_score'] = c.get('struct')
        rec['render_s'] = c.get('render_s')
        rec['mp3'] = c.get('mp3')
        wav = f'{SCR}/{tag}_master.wav'
        s0 = c['snip']['s0']
        Ms = shift_meta(M, s0)
        rec['blend'] = dict(start=int(M['trans'][0]['start_bar']), end=int(M['trans'][0]['end_bar']),
                            swap=M['trans'][0].get('swap_bar'), s0=s0)
        rec['drop_land'] = drop_land(b, c['win'])
        rec['phrase_ok'] = phrase_aligned(c['win'])
        gaps = G.check(Ms, wav)
        rec['bassgap'] = gaps
        ev = energy_events(Ms, wav)
        # only count drops that fall inside the (shifted) blend, matching mix-level concern
        ts, te = Ms['trans'][0]['start_bar'], Ms['trans'][0]['end_bar']
        bad_e = [e for e in ev if not e['phrase'] and not e['echo'] and ts-1 <= e['bar'] <= te+1]
        rec['energy'] = bad_e
        rec['energy_all'] = ev
        rec['pass_bg'] = not gaps
        rec['pass_en'] = not bad_e
        rec['ok_js'] = rec['pass_bg'] and rec['pass_en']  # JHO-Sol gates
        # Parallel alignment on overlap
        rec['align'] = align_report(Ms, wav, PAR if b == PAR else None)
        rec['pass_al'] = not rec['align']['bad']
        rec['error'] = None
    except Exception as ex:
        rec['error'] = traceback.format_exc()[-600:]
        rec['ok_js'] = False
        rec['pass_al'] = False
        rec['pass_bg'] = rec['pass_en'] = False
        rec['bassgap'] = rec['energy'] = rec['align'] = None
    return rec

def align_report(M, wav, care_id=None):
    """Subset of checks.bar_alignment_report: |lag|>10 and corr>=0.65."""
    import soundfile as sf, librosa
    x, sr = sf.read(wav, dtype='float32', always_2d=True)
    mix = x.mean(1)
    y = librosa.resample(mix, orig_sr=sr, target_sr=22050)
    hop = 64
    o = librosa.onset.onset_strength(y=y, sr=22050, hop_length=hop)
    fr = 22050 / hop
    BAR_S = M['bar_sec']
    def gain_at(d, k, bar):
        pts = (d.get('auto') or {}).get(k)
        if not pts:
            return 1.0
        return float(np.interp(bar, [p[0] for p in pts], [p[1] for p in pts]))
    def src_of(d, bar):
        j = int(bar - d['start_bar'])
        if j < 0 or j >= len(d['full_map']):
            return (None, None)
        return d['full_map'][j]
    nudges = json.load(open(os.path.join(HERE, os.environ.get('NUDGE', 'nudge.json')))) if os.path.exists(os.path.join(HERE, os.environ.get('NUDGE', 'nudge.json'))) else {}
    def nudge_ms(b, k):
        return nudges.get(b, {}).get(str(int(k)), 0)
    src_cache = {}
    def src_onset(b):
        if b not in src_cache:
            yy, srr = sf.read(f'{HERE}/st/{b}.wav', dtype='float32', always_2d=True)
            g = json.load(open(f'{HERE}/st/{b}.json'))
            yy = librosa.resample(yy.mean(1), orig_sr=srr, target_sr=22050)
            src_cache[b] = (librosa.onset.onset_strength(y=yy, sr=22050, hop_length=64), g['downs'][0])
        return src_cache[b]
    def deck_al(d, bar, nb=2, span_ms=40):
        bar = int(min(max(bar, d['start_bar']), d['end_bar']-nb))
        k, stem = src_of(d, bar)
        so, d0 = src_onset(d['id'])
        m = o[int(bar*BAR_S*fr):int((bar+nb)*BAR_S*fr)]
        best = (-1e9, 0)
        for lag_ms in range(-span_ms, span_ms+1):
            parts = []; ok = True; nbf = int(round(BAR_S*fr))
            for j in range(nb):
                jj = int(bar - d['start_bar']) + j
                kj = d['full_map'][jj][0] if 0 <= jj < len(d['full_map']) else (k or 0) + j
                i0 = int((d0 + kj*BAR - nudge_ms(d['id'], kj)/1000 + lag_ms/1000)*fr)
                if i0 < 0 or i0 + nbf > len(so):
                    ok = False; break
                parts.append(so[i0:i0+nbf])
            if not ok:
                continue
            s = np.concatenate(parts)[:len(m)]
            if len(s) < len(m) or s.std() == 0 or m.std() == 0:
                continue
            corr = float(np.corrcoef(m, s)[0,1])
            if corr > best[0]:
                best = (corr, lag_ms)
        return dict(lag=best[1], corr=round(best[0], 2))
    out = []; bad = []
    decks = [d for d in M['decks'] if not d.get('acap')]
    if len(decks) < 2:
        return dict(rows=[], bad=[])
    d, e = decks[0], decks[1]
    s = int(max(d['start_bar'], e['start_bar'])); t = int(min(d['end_bar'], e['end_bar']))
    for b in range(s, t-1):
        for D, O in ((d, e), (e, d)):
            if care_id and D['id'] != care_id:
                continue
            if gain_at(D, 'gain', b+1) < 0.5 * gain_at(O, 'gain', b+1):
                continue
            if src_of(D, b)[1] != 'mix':
                continue
            a = deck_al(D, b)
            row = dict(bar=b, deck=D['id'], lag=a['lag'], corr=a['corr'])
            out.append(row)
            if a['corr'] >= 0.65 and abs(a['lag']) > 10:
                bad.append(row)
    return dict(rows=out, bad=bad)

def diagnose_parallel():
    """Onset-vs-label for Parallel intro bars; grid residual already 0."""
    import soundfile as sf, librosa
    g = json.load(open(f'{HERE}/st/{PAR}.json'))
    y, sr = sf.read(f'{HERE}/st/{PAR}.wav', dtype='float32', always_2d=True)
    y = librosa.resample(y.mean(1), orig_sr=sr, target_sr=22050)
    hop = 64; fr = 22050/hop
    o = librosa.onset.onset_strength(y=y, sr=22050, hop_length=hop)
    d0 = g['downs'][0]
    rows = []
    for k in range(0, 40):
        i0 = int((d0 + k*BAR)*fr)
        nbf = int(round(BAR*fr))
        seg = o[i0:i0+nbf]
        if len(seg) < 10:
            continue
        # lag of max onset vs window start, search ±40 ms
        L = int(0.04*fr)
        # also compare to expected downbeat at start of window
        best = int(np.argmax(seg[:max(1, int(0.08*fr))])) if len(seg) else 0
        # xcorr vs impulse at 0
        sc = []
        for lag in range(-L, L+1):
            idx = np.clip(int(0*fr) + lag, 0, len(seg)-1)
            # mean of a 8ms window
            w = seg[max(0,idx-1):idx+2].mean() if False else (seg[idx] if 0 <= idx < len(seg) else 0)
            sc.append(w)
        lag_ms = (int(np.argmax(sc)) - L) / fr * 1000
        pk = float(seg.max()) if len(seg) else 0
        rows.append(dict(bar=k, onset_vs_label_ms=round(lag_ms,1), peak=round(pk,2)))
    return rows

def main():
    diag = diagnose_parallel()
    print('PARALLEL onset-vs-label bars 0-20:', [(r['bar'], r['onset_vs_label_ms']) for r in diag[:21]], flush=True)

    jho_extras = [
        ('r12', ['n', 192, None, 16, 16]),
        ('r13', ['n', 176, None, 32, 16]),
        ('drop16_e192', ['n', 192, None, 32, 16]),
        ('drop32_e192', ['n', 192, None, 16, 32]),
        ('drop16_e176', ['n', 176, None, 32, 16]),
        ('drop32_e176', ['n', 176, None, 16, 32]),
        ('drop16_e208', ['n', 208, None, 32, 16]),
        ('drop32_e208', ['n', 208, None, 16, 32]),
        ('drop16_e160', ['n', 160, None, 32, 16]),
        ('drop32_e160', ['n', 160, None, 16, 32]),
        ('gold_lb208', ['lb', 208, None, 32, 16]),
        ('gold_lb208_32', ['lb', 208, None, 32, 32]),
        ('n208_ib16_x16', ['n', 208, None, 16, 16]),
    ]
    day_extras = [
        ('r12', ['la', 128, 112, 0, 16]),
        ('n128_ib0_x16', ['n', 128, None, 0, 16]),
        ('drop16_e128', ['n', 128, None, 16, 16]),
        ('drop32_e128', ['n', 128, None, 0, 32]),
        ('drop16_e112', ['n', 112, None, 16, 16]),
        ('drop32_e112', ['n', 112, None, 0, 32]),
        ('drop16_e96', ['n', 96, None, 16, 16]),
        ('lb128_q16', ['lb', 128, None, 16, 16]),
        ('n128_ib32_x16', ['n', 128, None, 32, 16]),
    ]

    jc, jraw = build_cands(JHO, SOL, JHO_EMIN, ['n', 192, None, 16, 16], jho_extras)
    dc, draw = build_cands(DAY, PAR, DAY_EMIN, ['la', 128, 112, 0, 16], day_extras)
    print(f'JHO-Sol cands {len(jc)} (raw windows {len(jraw)})', flush=True)
    for c in jc:
        print('  ', c['fam'], c['win'], c['env'], 'drop_land', drop_land(SOL, c['win']), flush=True)
    print(f'Day-Par cands {len(dc)} (raw windows {len(draw)})', flush=True)
    for c in dc:
        print('  ', c['fam'], c['win'], c['env'], 'drop_land', drop_land(PAR, c['win']), flush=True)

    results = dict(parallel_onset=diag, jho=[], day=[])
    # sequential renders — more reliable with engine cache; checkpoint after each
    for i, c in enumerate(jc):
        tag = f'jho_{i}_{c["fam"]}'
        print(f'\n=== JHO {i+1}/{len(jc)} {c["fam"]} {c["win"]} {c["env"]} ===', flush=True)
        rec = eval_one(c, JHO, SOL, tag)
        print('  bg', rec.get('bassgap'), 'energy', rec.get('energy'), 'ok', rec.get('ok_js'), 'err', (rec.get('error') or '')[:120], flush=True)
        results['jho'].append(rec)
        json.dump(results, open(OUT, 'w'), indent=1, default=float)
    for i, c in enumerate(dc):
        tag = f'day_{i}_{c["fam"]}'
        print(f'\n=== DAY {i+1}/{len(dc)} {c["fam"]} {c["win"]} {c["env"]} ===', flush=True)
        rec = eval_one(c, DAY, PAR, tag)
        print('  align_bad', rec.get('align',{}).get('bad') if rec.get('align') else None, 'ok_al', rec.get('pass_al'), 'bg', rec.get('bassgap'), 'energy', rec.get('energy'), 'err', (rec.get('error') or '')[:120], flush=True)
        results['day'].append(rec)
        json.dump(results, open(OUT, 'w'), indent=1, default=float)

    j_ok = [r for r in results['jho'] if r.get('ok_js')]
    d_ok = [r for r in results['day'] if r.get('pass_al') and r.get('pass_bg') and r.get('pass_en')]
    def rank_j(r):
        return (0 if r.get('drop_land') else 1, 0 if r['win'][0]=='n' else 1, r['win'][4]*-1, r.get('raw_m',{}).get('lull_db', 99) if r.get('raw_m') else 99)
    def rank_d(r):
        return (0 if r.get('drop_land') else 1, 0 if r['win'][0]=='n' else 1, len((r.get('align') or {}).get('bad') or []))
    j_ok.sort(key=rank_j); d_ok.sort(key=rank_d)
    results['pick_jho'] = j_ok[0] if j_ok else None
    results['pick_day'] = d_ok[0] if d_ok else None
    json.dump(results, open(OUT, 'w'), indent=1, default=float)
    print('\nPICK JHO', results['pick_jho'] and {k: results['pick_jho'][k] for k in ('fam','win','env','bassgap','energy','drop_land')})
    print('PICK DAY', results['pick_day'] and {k: results['pick_day'][k] for k in ('fam','win','env','align','drop_land','bassgap','energy')})
    print('j_ok', len(j_ok), '/', len(results['jho']), 'd_ok', len(d_ok), '/', len(results['day']))

if __name__ == '__main__':
    main()
