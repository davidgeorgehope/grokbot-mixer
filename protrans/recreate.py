"""Blind recreation: engine sees two source tracks + the tracklist time hint, never the pro clip."""
from __future__ import annotations
import json, os, sys, shutil, subprocess, tempfile
import numpy as np
import paths, cleanup

def load_rules(path=None):
    return json.load(open(path or paths.RULES))

# Defaults from the nightly protrans hill-climb (kept 2026-11-09: 2-bar bass swap, held-out 25.19 -> 26.58).
DEFAULTS = {'BASS_SWAP_BARS': 3, 'HIGH_OFS': 8}  # HIGH_OFS 8: nightly hill-climb 2026-11-10, held-out 27.97 -> 28.47; BASS_SWAP_BARS 3: nightly 2026-11-11, held-out 28.47 -> 29.51

def apply_rules(rules):
    rules = {**DEFAULTS, **(rules or {})}
    env = {}
    for k in ('FADE','BASS_SWAP_BARS','SWAP_POS','HIGH_SWAP','HIGH_OFS','STRUCT','LOOP32','LONG_RISE','LONG_XP','LONG_XP2','LONG_EXIT','LONG_SOLO'):
        if k in rules and rules[k] is not None:
            env[k] = str(rules[k])
    return env


def _ensure_bar_proxies(st_js):
    """Fill drums/bass so mix_simple can run without demucs stems.
    drums ~ hat+low (else full-band) energy; bass ~ low band; voc is left out when unknown."""
    import json
    g=json.load(open(st_js)); bar=g.get('bar') or {}
    al=bar.get('all') or []
    if 'drums' not in bar and al:
        # hat+low as a kick/hat stand-in when both exist, else all
        if bar.get('hat') and bar.get('low') and len(bar['hat'])==len(al):
            import math
            drums=[]
            for h,lo in zip(bar['hat'], bar['low']):
                drums.append(round(10*math.log10(10**(h/10)+10**(lo/10)+1e-10),2))
            bar['drums']=drums
        else:
            bar['drums']=list(al)
    if 'bass' not in bar and bar.get('low'):
        bar['bass']=list(bar['low'])
    # No vocal stand-in any more (2026-11-11 RCA): the old constant -100 'voc' made every bar count as vocal in
    # mix_simple's V term. Without vocal data mix_simple now switches the V term off for that deck and says so.
    g['bar']=bar
    tmp=st_js+f'.tmp{os.getpid()}'
    with open(tmp,'w') as f: json.dump(g, f)
    os.replace(tmp, st_js)  # atomic: concurrent readers never see a half-written file

def _prep_track(ytid, src_m4a, created):
    """Serialize prep per track: adjacent pairs share a track and parallel workers
    used to re-prep it at the same time, truncating st/{id}.json (JSONDecodeError
    on 11/37 pairs in the 7 Nov tune)."""
    import fcntl
    os.makedirs('/tmp/protrans_work', exist_ok=True)
    with open(os.path.join('/tmp/protrans_work', f'{ytid}.lock'), 'w') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        return _prep_track_locked(ytid, src_m4a, created)

def _prep_track_locked(ytid, src_m4a, created):
    """Stretch/grid into a private st/ then symlink into src2 if missing. No demucs."""
    src2 = paths.SRC2
    st_wav = os.path.join(src2, 'st', f'{ytid}.wav')
    st_js = os.path.join(src2, 'st', f'{ytid}.json')
    m4a_dst = os.path.join(src2, f'{ytid}.m4a')
    if os.path.exists(st_wav) and os.path.exists(st_js):
        _ensure_bar_proxies(st_js)
        return ytid
    os.makedirs(os.path.join(src2, 'st'), exist_ok=True)
    if not os.path.exists(m4a_dst):
        os.symlink(os.path.abspath(src_m4a), m4a_dst)
        created.append(m4a_dst); cleanup.note('src2_link', m4a_dst)
    tmp = os.path.join('/tmp/protrans_work', f'{ytid}.wav')
    os.makedirs('/tmp/protrans_work', exist_ok=True)
    os.makedirs('/tmp/protrans_bench', exist_ok=True)
    if not os.path.exists(tmp):
        subprocess.run(['ffmpeg','-v','error','-y','-i',src_m4a,'-ac','2','-ar','44100',tmp], check=True)
    # BPM then prep (writes st/{id}.* relative to cwd src2)
    r = subprocess.run(['python3','pbpm.py', tmp], cwd=src2, capture_output=True, text=True)
    bpm = None
    for tok in r.stdout.split():
        try:
            v=float(tok)
            if 140 < v < 190: bpm=v; break
        except ValueError: pass
    if bpm is None: bpm = 174.0
    pr = subprocess.run(['python3','prep.py', tmp, str(bpm)], cwd=src2, capture_output=True, text=True)
    if pr.returncode:
        err = (pr.stderr or '') + (pr.stdout or '')
        if 'prep REJECT' in err:
            fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'force_prep.py')
            subprocess.run(['python3', fp, tmp, str(bpm)], cwd=src2, check=True, capture_output=True)
        else:
            raise RuntimeError(f'prep.py failed for {ytid}: {err[-400:]}')
    subprocess.run(['python3','fixgrid.py', ytid], cwd=src2, check=True, capture_output=True)
    env=dict(os.environ); env['BF']=f'st/{ytid}.json'
    subprocess.run(['python3','barfeats.py'], cwd=src2, env=env, check=True, capture_output=True)
    _ensure_bar_proxies(st_js)
    created.append(st_wav); created.append(st_js)
    cleanup.note('src2_st', st_wav)
    try: os.remove(tmp)
    except OSError: pass
    return ytid


_PHASE_CACHE = {}
PHASE_COST_ERRORS = []  # (a, b, win, error) of phase-cost failures this process (reported in info['phase_cost_errors'])

def _phase_pick_cost(a_yt, b_yt, win, phase_pref_w, linger_pen_w, breakdown_pen_w):
    """Frequency-weighted soft preference from train pro pairings. Nothing is banned."""
    import structure as ST
    def labs(yt):
        if yt not in _PHASE_CACHE:
            st_js = os.path.join(paths.SRC2, 'st', f'{yt}.json')
            bar = ST.load_bar(st_js)
            _PHASE_CACHE[yt] = (ST.label_phases(bar), ST.detect_breakdowns(bar))
        return _PHASE_CACHE[yt]
    try:
        la, sa = labs(a_yt)
        lb, _ = labs(b_yt)
        priors = ST.load_priors(os.path.join(paths.RESULTS, 'phase_priors.json'))
        extra, _ = ST.window_phase_cost(win, la, lb, sa, priors,
                                        phase_pref_w, linger_pen_w, breakdown_pen_w)
        return float(extra)
    except Exception as e:
        # 2026-11-11 RCA: this used to return 0 silently (a TypeError on loop windows zeroed the knobs).
        # Still a soft cost (0, so one bad track can't block a pick), but logged and counted.
        PHASE_COST_ERRORS.append(dict(a=a_yt, b=b_yt, win=list(win), error=f'{type(e).__name__}: {e}'[-200:]))
        print(f'WARN phase cost failed for {a_yt}>{b_yt} {win}: {type(e).__name__}: {e}', file=sys.stderr, flush=True)
        if os.environ.get('PHASE_COST_STRICT'):
            raise
        return 0.0

# Tie-break cost per family (lower = preferred when every other term ties). Distinct on purpose; tuned via rules.json
# 'family_cost' ({fam: cost}) like any other general rule. nat_long stays the cheapest default (held-out baseline).
FAMILY_COST = {'nat_long': 0.0, 'nat_short': 0.01, 'out_loop': 0.02, 'in_loop': 0.03, 'lx_beat': 0.04,
               'cue_early': 0.05, 'cue_late': 0.06, 'phrase_cut': 0.07, 'swap_early': 0.08, 'swap_late': 0.09,
               'sneak_in': 0.10, 'rated': 0.0}

def family_cost(fam, rules=None):
    over = (rules or {}).get('family_cost') or {}
    return float(over.get(fam, FAMILY_COST.get(fam, 0.11)))

def _hint_bar(hint_sec, bar_sec=240/174):
    if hint_sec is None: return None
    return hint_sec / bar_sec

def recreate(a_yt, b_yt, a_m4a, b_m4a, hint_a_played_sec=None, rules=None, tag='pt'):
    """Pick a window/family from general rules + hint, render a snippet. Returns paths + pick info."""
    rules = rules or load_rules()
    created = []
    os.makedirs('/tmp/protrans_work', exist_ok=True)
    os.environ['BB_SCRATCH'] = '/tmp/protrans_bench'
    os.makedirs('/tmp/protrans_bench', exist_ok=True)
    os.environ['PREF_W'] = '0'
    sys.path.insert(0, paths.SRC2)
    a = _prep_track(a_yt, a_m4a, created)
    b = _prep_track(b_yt, b_m4a, created)
    import blend_bench as BB
    env = apply_rules(rules)
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    oldcwd = os.getcwd()
    try:
        os.chdir(paths.SRC2)
        cs = BB.cands_for(a, b, tag)
        fams = BB.families(cs, None)
        if not fams:
            raise RuntimeError(f'no candidate windows for {a}>{b}')
        hb = _hint_bar(hint_a_played_sec)
        hw = float(rules.get('hint_weight') or 0)
        nb = float(rules.get('near_hint_bars') or 32)
        lp = int(rules.get('length_pref') or 0)
        pref = rules.get('prefer_family')
        scored = []
        for c in fams:
            win = c['win']; cost = 0.0
            # win = [kind, out_end, loop, in_begin, X]
            if hw and hb is not None:
                cost += hw * abs(float(win[1]) - hb) / max(nb, 1)
            if lp and win[4] != lp:
                cost += 0.15
            if pref and not str(c['fam']).startswith(str(pref)):
                cost += float(rules.get('family_prior_w') or 0)
            # Loop/synthetic-outro families splice a jumped source bar at
            # the blend. A 1-beat linear overlap of uncorrelated audio
            # reads as breakup (ex2, Yosemite > Used To This, fam=out_loop).
            # This penalty is a general rule, not a per-track pin.
            kind = win[0] if win else ''
            if kind in ('la', 'lb', 'ab', 'lx'):
                cost += float(rules.get('loop_fam_pen') or 0)
            pw = float(rules.get('phase_pref_w') or 0)
            lw = float(rules.get('linger_pen_w') or 0)
            bw = float(rules.get('breakdown_pen_w') or 0)
            if pw or lw or bw:
                cost += _phase_pick_cost(a, b, win, pw, lw, bw)
            # distinct per-family cost (2026-11-11 RCA): swap_early/swap_late/sneak_in share nat_long's window, so they
            # tied it on every term and the stable sort always kept nat_long. rules.json 'family_cost' may override.
            cost += family_cost(c['fam'], rules)
            scored.append((cost, c))
        scored.sort(key=lambda x: x[0])
        pick = scored[0][1]
        # rules env first, then the family's own params on top (2026-11-11 RCA: the old update() let rules
        # overwrite swap_early/swap_late's SWAP_POS, so those families rendered exactly like nat_long)
        pick['env'] = {**env, **dict(pick.get('env') or {})}
        dk, M = BB.render(pick, a, b, tag)
        ours = pick.get('mp3')
        meta_path = os.path.join('/tmp/protrans_bench', f'{tag}_{a}_{b}_meta.json')   # for blend_diag (daily diagnostics)
        try:
            json.dump(M, open(meta_path, 'w'), default=str)
        except Exception:
            meta_path = None
        info = dict(meta_path=meta_path, a=a, b=b, fam=pick['fam'], win=pick['win'], env=pick['env'],
                    hint_a_played_sec=hint_a_played_sec, ours=ours, created=created,
                    n_cands=len(fams), phase_cost_errors=list(PHASE_COST_ERRORS),
                    halfbeat=(pick.get('timing') or {}).get('trans', {}).get('halfbeat'), hard=pick.get('hard'))
        return info
    finally:
        os.chdir(oldcwd)
        for k,v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

if __name__ == '__main__':
    print('use run.py')
