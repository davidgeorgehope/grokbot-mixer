"""Blind recreation: engine sees two source tracks + the tracklist time hint, never the pro clip."""
from __future__ import annotations
import json, os, sys, shutil, subprocess, tempfile
import numpy as np
import paths, cleanup

def load_rules(path=None):
    return json.load(open(path or paths.RULES))

def apply_rules(rules):
    env = {}
    for k in ('FADE','BASS_SWAP_BARS','SWAP_POS','HIGH_SWAP','HIGH_OFS','STRUCT','LOOP32'):
        if k in rules and rules[k] is not None:
            env[k] = str(rules[k])
    return env


def _ensure_bar_proxies(st_js):
    """Fill drums/bass/voc so mix_simple can run without demucs stems.
    drums ~ full-band energy; bass ~ low band; voc stays quiet if unknown."""
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
    if 'voc' not in bar and al:
        bar['voc']=[-100.0]*len(al)
    g['bar']=bar
    json.dump(g, open(st_js,'w'))

def _prep_track(ytid, src_m4a, created):
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
    except Exception:
        return 0.0

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
            scored.append((cost, c))
        scored.sort(key=lambda x: x[0])
        pick = scored[0][1]
        pick['env'] = dict(pick.get('env') or {})
        pick['env'].update(env)
        dk, M = BB.render(pick, a, b, tag)
        ours = pick.get('mp3')
        info = dict(a=a, b=b, fam=pick['fam'], win=pick['win'], env=pick['env'],
                    hint_a_played_sec=hint_a_played_sec, ours=ours, created=created,
                    n_cands=len(fams))
        return info
    finally:
        os.chdir(oldcwd)
        for k,v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

if __name__ == '__main__':
    print('use run.py')
