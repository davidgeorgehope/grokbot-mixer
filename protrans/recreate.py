"""Blind recreation: engine sees two source tracks + the tracklist time hint, never the pro clip."""
from __future__ import annotations
import json, os, sys, shutil, subprocess, tempfile
import numpy as np
import paths, cleanup

def load_rules(path=None):
    return json.load(open(path or paths.RULES))

# Defaults from the nightly protrans hill-climb (kept 2026-11-09: 2-bar bass swap, held-out 25.19 -> 26.58).
DEFAULTS = {'BASS_SWAP_BARS': 3, 'HIGH_OFS': 8, 'LONG_SOLO': 16, 'LONG_SWAP': 'exit', 'LONG_SOLO_STRUCT': 1, 'linger_pen_w': 0.15}  # linger_pen_w 0.15: nightly hill-climb 2026-11-13, held-out 32.24 -> 33.84 (soft cost for windows that leave the outgoing track lingering past its phrase);  # LONG_*: 2026-11-11 long-blend RCA, only act with FADE=long (rules.json; held-out 30.09 -> 30.75, the listener 'best one yet'); HIGH_OFS 8: nightly hill-climb 2026-11-10, held-out 27.97 -> 28.47; BASS_SWAP_BARS 3: nightly 2026-11-11, held-out 28.47 -> 29.51

def apply_rules(rules):
    rules = {**DEFAULTS, **(rules or {})}
    env = {}
    for k in ('FADE','BASS_SWAP_BARS','SWAP_POS','HIGH_SWAP','HIGH_OFS','STRUCT','LOOP32','LONG_RISE','LONG_XP','LONG_XP2','LONG_EXIT','LONG_SOLO','LONG_SWAP','LONG_SOLO_STRUCT','TAIL_EXIT','TAIL_RATE','TAIL_SHALLOW','TAIL_SHALLOW_CAP','TAIL_SHALLOW_GATE','SNAP_IN','SNAP_IN_DB','SNAP_IN_HOLD','BASS_COVER','BASS_COVER_DB','WINDOW_PLANNER','RANKER','FINE_PHASE','FINE_PHASE_MIN_MS','FINE_PHASE_MIN_STRENGTH','BLEND_LOCK','BLEND_LOCK_MIN_MS','BLEND_LOCK_MAX_MS'):
        if k in rules and rules[k] is not None:
            env[k] = str(rules[k])
    # rules.json / cohort trials use lowercase window_planner; mix_simple
    # pair_cands reads WINDOW_PLANNER. Without this alias, mid-track incoming
    # starts past bar 80 never entered cs (ukf__25 v2 stayed on the intro).
    if 'WINDOW_PLANNER' not in env and rules.get('window_planner') is not None:
        env['WINDOW_PLANNER'] = str(rules['window_planner'])
    if 'RANKER' not in env and rules.get('ranker') is not None:
        env['RANKER'] = str(rules['ranker'])
    if 'RANKER' not in env and rules.get('RANKER') is not None:
        env['RANKER'] = str(rules['RANKER'])
    if env.get('FADE')=='graphcut':
        env['GRAPH_CUT']='1'
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
               'sneak_in': 0.10, 'rated': 0.0, 'hint_long': 0.0, 'hint_short': 0.01,
               'plan_breakdown_drop': 0.01, 'plan_drop1_end': 0.01}  # plan_*: 2026-11-15 window planner, same costs as nat_short; only offered when window_planner is on

def family_cost(fam, rules=None):
    over = (rules or {}).get('family_cost') or {}
    return float(over.get(fam, FAMILY_COST.get(fam, 0.11)))

def _hint_bar(hint_sec, bar_sec=240/174):
    if hint_sec is None: return None
    return hint_sec / bar_sec

def _flag_on(v):
    return str(v).strip().lower() not in ('', '0', 'false', 'none', 'no')

def hint_families(cs, hint_bar, near_bars=32):
    """Natural windows whose outgoing end is near the tracklist time hint.

    families() picks the lowest engine-cost window per family. STRUCT's 300-point
    bonus makes that the outro-over-intro window on almost every pair, so the
    hint never competes. Off by default (rules hint_family); 2026-11-14 RCA.
    """
    if hint_bar is None or not cs:
        return []
    out = []
    near_bars = max(float(near_bars), 1.0)
    for fam, pred in (('hint_short', lambda w: w[0] == 'n' and w[4] == 16),
                      ('hint_long', lambda w: w[0] == 'n' and w[4] >= 32)):
        pool = [c for c in cs if pred(c['win'])]
        if not pool:
            continue
        near = [c for c in pool if abs(float(c['win'][1]) - hint_bar) <= near_bars]
        if near:
            best = min(near, key=lambda c: c['cost'])
        else:
            best = min(pool, key=lambda c: (abs(float(c['win'][1]) - hint_bar), c['cost']))
        out.append(dict(fam=fam, win=list(best['win']), env={}))
    return out

def _body(lo):
    import numpy as np
    lo = np.asarray(lo, float)
    return float(np.percentile(lo, 75)) if len(lo) else -20.0

def incoming_hole_bars(win, lo_a, lo_b, gap=9.84):
    """Bars where the incoming is thin (>gap under its body) while the outgoing still
    has bass (within gap/2 of its body). gap defaults to bassgap.GAP_DB, the pro p95.
    Counts an engine hole, not a breakdown both records already have. 2026-11-14 RCA.
    """
    if not win or lo_a is None or lo_b is None:
        return 0
    kind, e, _p, ib, X = win[0], int(win[1]), win[2], win[3], int(win[4])
    if kind != 'n' or ib is None:
        return 0
    ib = int(ib)
    import numpy as np
    lo_a = np.asarray(lo_a, float); lo_b = np.asarray(lo_b, float)
    body_a, body_b = _body(lo_a), _body(lo_b)
    n = 0
    for k in range(X):
        ia, ibk = e - X + k, ib + k
        oa = float(lo_a[ia]) if 0 <= ia < len(lo_a) else -120.0
        ob = float(lo_b[ibk]) if 0 <= ibk < len(lo_b) else -120.0
        if ob < body_b - gap and oa >= body_a - gap / 2.0:
            n += 1
    return n

def _bar_low(yt):
    p = os.path.join(paths.SRC2, 'st', f'{yt}.json')
    if not os.path.exists(p):
        return None
    try:
        lo = (json.load(open(p)).get('bar') or {}).get('low')
        return lo
    except Exception:
        return None

def add_hint_families(fams, cs, hint_bar, near_bars=32, enabled=False,
                      lo_a=None, lo_b=None, gap=9.84):
    """Append hint_short / hint_long when enabled, skipping windows already nominated.

    When source lows are given, this is a per-pair choice, not a blanket swap:
    mid-track windows are only added if the default natural window has an engine
    bass hole (>1 bar) and the hint window has strictly fewer hole bars.
    the listener, 2026-11-15: blend technique depends on the tracks, not a fixed rule.
    """
    if not enabled:
        return list(fams)
    fams = list(fams)
    def_holes = None
    if lo_a is not None and lo_b is not None:
        def_win = None
        for name in ('nat_short', 'nat_long'):
            hit = next((c for c in fams if c.get('fam') == name), None)
            if hit is not None:
                def_win = hit['win']
                break
        if def_win is None:
            return fams
        def_holes = incoming_hole_bars(def_win, lo_a, lo_b, gap)
        if def_holes <= 1:
            return fams
    have = {tuple(c['win']) for c in fams}
    for c in hint_families(cs, hint_bar, near_bars):
        if def_holes is not None and incoming_hole_bars(c['win'], lo_a, lo_b, gap) >= def_holes:
            continue
        key = tuple(c['win'])
        if key not in have:
            fams.append(c)
            have.add(key)
    return fams

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
        # When RANKER=1, pair_cands also adds mid-track windows (planner_extra).
        # Keep the default family shortlist on the non-extra windows so the
        # baseline pick matches RANKER=0.
        ranker_preview = _flag_on(env.get('RANKER') or (rules or {}).get('RANKER') or (rules or {}).get('ranker'))
        fams = BB.families([c for c in cs if not c.get('planner_extra')] if ranker_preview else cs, None)
        if not fams:
            raise RuntimeError(f'no candidate windows for {a}>{b}')
        hb = _hint_bar(hint_a_played_sec)
        hw = float(rules.get('hint_weight') or 0)
        nb = float(rules.get('near_hint_bars') or 32)
        # hint_family is off by default: STRUCT's bonus otherwise hides every
        # mid-track window from this shortlist (2026-11-14 RCA).
        # Per-pair: only nominate a mid-track window when the default one has an
        # engine bass hole (outgoing still has body, incoming thin). Off by default.
        gap = 9.84
        try:
            import bassgap as _bg
            gap = float(_bg.GAP_DB)
        except Exception:
            pass
        fams = add_hint_families(fams, cs, hb, nb, enabled=_flag_on(rules.get('hint_family')),
                                 lo_a=_bar_low(a), lo_b=_bar_low(b), gap=gap)
        # window_planner is off by default: nominates mid-track section windows
        # and chooses per pair from track features (2026-11-15). Not a blanket swap.
        # The default window is whatever this cost loop already picks (usually
        # nat_short under length_pref=16), not the first nat_* in families().
        planner_choice = None
        planner_on = _flag_on(rules.get('window_planner'))
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
        if planner_on:
            import window_planner as _WP
            import sections as _SEC
            _sa, _sb = _SEC.get(a), _SEC.get(b)
            _loa, _lob = _bar_low(a), _bar_low(b)
            _def = pick['win']
            planner_choice = _WP.select(_def, _sa, _sb, _loa, _lob, gap=gap)
            base_wins = {tuple(c.get('win') or []) for c in cs if not c.get('planner_extra')}
            if planner_choice and planner_choice.get('type') not in (None, 'outro_intro') and planner_choice.get('win'):
                want = tuple(planner_choice['win'])
                allow = want in base_wins or _WP.is_extended_ok(planner_choice)
                if allow and any(tuple(c.get('win') or []) == want for c in cs):
                    extra = _WP.add_families([], [c for c in cs if tuple(c.get('win') or []) == want],
                                             _sa, _sb, lo_a=_loa, lo_b=_lob, enabled=True, gap=gap)
                    for c in extra:
                        # same cost terms as the loop above, so apply_choice can see the family
                        win = c['win']; cost = 0.0
                        if hw and hb is not None:
                            cost += hw * abs(float(win[1]) - hb) / max(nb, 1)
                        if lp and win[4] != lp:
                            cost += 0.15
                        kind = win[0] if win else ''
                        if kind in ('la', 'lb', 'ab', 'lx'):
                            cost += float(rules.get('loop_fam_pen') or 0)
                        pw = float(rules.get('phase_pref_w') or 0)
                        lw = float(rules.get('linger_pen_w') or 0)
                        bw = float(rules.get('breakdown_pen_w') or 0)
                        if pw or lw or bw:
                            cost += _phase_pick_cost(a, b, win, pw, lw, bw)
                        cost += family_cost(c['fam'], rules)
                        scored.append((cost, c))
            pick = _WP.apply_choice(scored, planner_choice, _def, base_wins=base_wins)
        # rules env first, then the family's own params on top (2026-11-11 RCA: the old update() let rules
        # overwrite swap_early/swap_late's SWAP_POS, so those families rendered exactly like nat_long)
        # Only fold the planner's fade onto a mid-track pick that was actually
        # applied. Merging SNAP_IN onto a fallback outro-intro stay was the
        # ukf__25 v2 hook bug (intro window + SNAP_IN scored 16.10).
        fade = {}
        if (planner_choice and pick and pick.get('planner')
                and planner_choice.get('type') not in (None, 'outro_intro')):
            fade = dict(planner_choice.get('fade_env') or {})
        # RANKER=1 (off by default): score engine candidate windows + SNAP_IN /
        # hold / tail options and pick one per pair. Does not change defaults.
        ranker_info = None
        ranker_on = _flag_on(env.get('RANKER') or rules.get('RANKER') or rules.get('ranker'))
        if ranker_on:
            import learned_ranker as _LR
            import window_planner as _WP
            import sections as _SEC
            _sa, _sb = _SEC.get(a), _SEC.get(b)
            _loa, _lob = _bar_low(a), _bar_low(b)
            default_tail = int(float((pick.get('env') or {}).get('TAIL_EXIT') or env.get('TAIL_EXIT') or rules.get('TAIL_EXIT') or 6))
            default_fade = str((pick.get('env') or {}).get('FADE') or env.get('FADE') or rules.get('FADE') or 'long')
            nom = []
            try:
                nom = _WP.nominate(_sa, _sb, X=int((pick.get('win') or [None,0,None,0,16])[4] or 16))
            except Exception:
                nom = []
            # Keep default window in the option set even if nominate missed it.
            if pick.get('win'):
                nom = [dict(type='outro_intro', win=list(pick['win']))] + [c for c in nom if list(c.get('win') or []) != list(pick['win'])]
            options = _LR.enumerate_options(nom, default_tail=default_tail, default_fade=default_fade)
            best, _scores, ranker_info = _LR.choose(_sa, _sb, options, _loa, _lob, gap=gap)
            if best and best.get('win'):
                want = tuple(best['win'])
                # Prefer an already-scored family with this window; otherwise add one.
                hit = next((c for _, c in scored if tuple(c.get('win') or []) == want), None)
                if hit is None:
                    hit = dict(fam='ranker_' + str(best.get('type') or 'pick'), win=list(best['win']), env={})
                    # Only render windows the engine already scored (in cs), so
                    # mix_simple --plan will accept them. Mid-track extras are in
                    # cs when RANKER=1 (pair_cands engine_cands hook).
                    if any(tuple(c.get('win') or []) == want for c in cs):
                        scored.append((0.0, hit))
                    else:
                        ranker_info = dict(ranker_info or {}, applied=False, reason='win_not_in_cs')
                        hit = None
                if hit is not None:
                    pick = dict(hit)
                    fade = dict(_LR.fade_env(best))
                    pick['ranker'] = dict(ranker_info or {}, type=best.get('type'), applied=True)
        pick['env'] = {**env, **dict(pick.get('env') or {}), **fade}
        # FADE=graphcut is a renderer flag: keep it on top of any family FADE so a cohort
        # eval compares the same windows under a different handover, not a different family.
        if str((rules or {}).get('FADE'))=='graphcut' or env.get('GRAPH_CUT')=='1':
            pick['env']['FADE']='graphcut'; pick['env']['GRAPH_CUT']='1'
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
                    halfbeat=(pick.get('timing') or {}).get('trans', {}).get('halfbeat'), hard=pick.get('hard'),
                    planner=(planner_choice if planner_choice else pick.get('planner')),
                    ranker=(ranker_info if ranker_on else None))
        return info
    finally:
        os.chdir(oldcwd)
        for k,v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

if __name__ == '__main__':
    print('use run.py')
