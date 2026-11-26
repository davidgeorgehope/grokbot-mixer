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
    for k in ('FADE','BASS_SWAP_BARS','SWAP_POS','HIGH_SWAP','HIGH_OFS','HIGH_GATE','STRUCT','LOOP32','LONG_RISE','LONG_XP','LONG_XP2','LONG_EXIT','LONG_SOLO','LONG_SWAP','LONG_SOLO_STRUCT','TAIL_EXIT','TAIL_RATE','TAIL_SHALLOW','TAIL_SHALLOW_CAP','TAIL_SHALLOW_GATE','SNAP_IN','SNAP_IN_DB','SNAP_IN_HOLD','BASS_COVER','BASS_COVER_DB','WINDOW_PLANNER','RANKER','FINE_PHASE','FINE_PHASE_MIN_MS','FINE_PHASE_MIN_STRENGTH','BLEND_LOCK','BLEND_LOCK_MIN_MS','BLEND_LOCK_MAX_MS','HALFBEAT_LOCK','HALFBEAT_LOCK_MAX_MS','DROP_SWAP','REPLICA','REPLICA_X','DROPCAND','STRUCT_THIN','THIN_DROPCUE','THIN_DB','STRUCT_THIN_W','SLOWDOWN','STRUCTW','STRUCTB','STRUCT_COND','STRUCT_MID','STRUCT_MID_B','STRUCT_MID_W','STRUCT_MID_MIN_GAP','STRUCT_MID_MIN_HT','OUTRO_QC','EXITPOS','EXITPOS_GATE','EXITPOS_DROP','BASS_FILL','BASS_FILL_DB','SLOWPAIR','SLOWPAIR_EXIT','SLOWPAIR_COND','DRUMCLASH','DRUMCLASH_W','PLAN_LAND','ESTAB','ESTAB_W','ESTAB_DB','HARD_FALLBACK','PICKER_STYLE_GATED','PICKER_STYLE_GATED_MAP','PICKER_INJECT_CS','BREAK_EXIT','MID_HOLD','MID_HOLD_DB','EARLY_EXIT','EARLY_EXIT_HOLD_DB','EARLY_EXIT_RATE','PRO_FADE','PRO_FADE_ENTRY_DB','PRO_FADE_SHELF_DB','PRO_FADE_EXIT_SLOPE','PRO_FADE_HIGH_OFS','PRO_FADE_BASS_CUT_DB','PRO_FADE_BASS_REL','PRO_FADE_BASS_SW','PRO_FADE_BASS_REL_MID','PRO_FADE_RESPECT_EXIT','RIDEGATE','RIDEGATE_PACK','LINGER_GUARD'):
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
    drums ~ hat+low (else full-band) energy; bass ~ low band; voc is left out when unknown.
    Only writes the file when a missing drums/bass key was actually filled. A no-op
    rewrite used to bump mtimes on every official recreate and race Mix 10 jobs
    that own live src2/st json (2026-11-24)."""
    import json
    g=json.load(open(st_js)); bar=g.get('bar') or {}
    al=bar.get('all') or []
    changed=False
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
        changed=True
    if 'bass' not in bar and bar.get('low'):
        bar['bass']=list(bar['low'])
        changed=True
    # No vocal stand-in any more (2026-11-11 RCA): the old constant -100 'voc' made every bar count as vocal in
    # mix_simple's V term. Without vocal data mix_simple now switches the V term off for that deck and says so.
    if not changed:
        return
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
               'plan_breakdown_drop': 0.01, 'plan_drop1_end': 0.01, 'break_exit': 0.01,
               'cons_cue': 0.05, 'slowpair': 0.01}  # cons_cue: 2026-11-19 CONSONANCE research family (same cost as cue_early); only offered when CONSONANCE=1  # slowpair: 2026-11-20 SLOWPAIR research family (same cost as nat_short); only offered when SLOWPAIR=1  # plan_*: 2026-11-15 window planner, same costs as nat_short; only offered when window_planner is on

def family_cost(fam, rules=None):
    over = (rules or {}).get('family_cost') or {}
    return float(over.get(fam, FAMILY_COST.get(fam, 0.11)))

def _hint_bar(hint_sec, bar_sec=240/174):
    if hint_sec is None: return None
    return hint_sec / bar_sec

def _flag_on(v):
    return str(v).strip().lower() not in ('', '0', 'false', 'none', 'no')

def hard_fallback_on(rules=None, env=None):
    """Official hard-check fallback. Off by default (HARD_FALLBACK=0) so the
    baseline floor stays like-for-like. Promotion candidate on its own; do not
    write rules.json."""
    env = env or {}
    rules = rules or {}
    return _flag_on(env.get('HARD_FALLBACK') or rules.get('HARD_FALLBACK') or os.environ.get('HARD_FALLBACK'))

def picker_style_gated_on(rules=None, env=None):
    """Style-gated learned picker. Off by default. Do not write rules.json."""
    env = env or {}
    rules = rules or {}
    return _flag_on(env.get('PICKER_STYLE_GATED') or rules.get('PICKER_STYLE_GATED') or os.environ.get('PICKER_STYLE_GATED'))

def picker_inject_cs_on(rules=None, env=None):
    """Inject mapped picker_style_gated window into candidate set cs if missing (legal natural windows only). Off by default."""
    env = env or {}
    rules = rules or {}
    return _flag_on(env.get('PICKER_INJECT_CS') or rules.get('PICKER_INJECT_CS') or os.environ.get('PICKER_INJECT_CS'))


def ridegate_live_on(rules=None, env=None):
    """Live (non-map) ridegate picker. Off by default. Do not write rules.json."""
    env = env or {}
    rules = rules or {}
    return _flag_on(env.get('RIDEGATE') or rules.get('RIDEGATE') or os.environ.get('RIDEGATE'))

def linger_guard_on(rules=None, env=None):
    """Linger guard (incoming breakdown under outgoing drop). Off by default. Do not write rules.json."""
    env = env or {}
    rules = rules or {}
    return _flag_on(env.get('LINGER_GUARD') or rules.get('LINGER_GUARD') or os.environ.get('LINGER_GUARD'))

def _picker_style_gated_map_path(env=None):
    env = env or os.environ
    override = (env or {}).get('PICKER_STYLE_GATED_MAP') or os.environ.get('PICKER_STYLE_GATED_MAP')
    if override:
        if not os.path.isabs(override) and not os.path.exists(override):
            cand = os.path.join(os.path.dirname(os.path.abspath(__file__)), override)
            if os.path.exists(cand):
                return cand
        return override
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'replica', 'picker_style_gated_windows.json')


def _effective_compat_pen(c):
    if not c:
        return 30.0
    p = float(c.get('pen', 30.0))
    # mix_simple adds HARDPEN=60 on an internal BOTHMIN=11 soft threshold even when O1 (>=8) & N1 (seam<=2) pass.
    # Strip that internal 60-pt surcharge when comparing compatibility unless a seam jump (seam_fail) triggered it.
    if int(c.get('both', 16)) < 11 and not c.get('seam_fail') and p >= 60.0:
        p -= 60.0
    # In post-drop-1 breakdown early-exit blends, Track A deliberately has low/no drums before incoming drops;
    # R>=0.25 and drumclash still guard rhythm compatibility, so strip DRUMPEN from early_exit pen comparisons.
    if c.get('early_exit'):
        if c.get('drum_pen'):
            p -= float(c.get('drum_pen', 0.0))
        if c.get('jump_pen'):
            p -= float(c.get('jump_pen', 0.0))
    return p


def select_compatible_picker_window(a, b, ranked, cs, default_win, dc_eval=None):
    """Pick the highest-ranked window from ranked that passes blend compatibility at that bar
    (vocal clash V, halfbeat HB, drum-onset R, overlap both, guardrail pen, predicted vdip, drumclash).
    Returns (hit_dict, rank_idx, tried_log) or (None, None, tried_log) to fall back to base."""
    def_c = next((c for c in cs if list(c.get('win') or []) == list(default_win or [])), None)
    def_pen_raw = float(def_c.get('pen', 30.0)) if def_c else 30.0
    def_pen_eff = _effective_compat_pen(def_c)
    def_V = int(def_c.get('V', 0)) if def_c else 0
    def_R = float(def_c.get('R', 0.25)) if def_c else 0.25
    def_both = int(def_c.get('both', 16)) if def_c else 16
    tried = []
    for idx, raw_w in enumerate(ranked or []):
        want = [raw_w[0], int(raw_w[1]), None, int(raw_w[3]), int(raw_w[4])]
        hit = next((c for c in cs if list(c.get('win') or []) == want), None)
        if hit is None:
            tried.append(dict(rank=idx, win=want, reason='not_in_cs'))
            continue
        is_ee = bool(hit.get('early_exit'))
        r_floor = 0.25 if is_ee else min(0.25, def_R)
        both_floor = min(8, def_both) if is_ee else 11
        pen_cap = max((def_pen_eff if is_ee else def_pen_raw) + 35.0, 90.0)
        reasons = []
        if int(hit.get('V', 0)) > def_V:
            reasons.append(f'V={hit.get("V")}>{def_V}')
        if bool(hit.get('HB')):
            reasons.append('HB')
        if float(hit.get('R', 1.0)) < r_floor:
            reasons.append(f'R={hit.get("R"):.2f}<{r_floor:.2f}')
        if int(hit.get('both', 16)) < both_floor:
            reasons.append(f'both={hit.get("both")}<{both_floor}')
        hit_pen = _effective_compat_pen(hit) if is_ee else float(hit.get('pen', 0.0))
        if hit_pen > pen_cap:
            reasons.append(f'pen={hit_pen:.1f}>{pen_cap:.1f}')
        if is_ee and hit.get('pred_vdip') is not None and float(hit.get('pred_vdip')) > 4.2:
            reasons.append(f'pred_vdip={hit.get("pred_vdip"):.2f}>4.20')
        if is_ee and hit.get('pred_ldip') is not None and float(hit.get('pred_ldip')) > 32.0:
            reasons.append(f'pred_ldip={hit.get("pred_ldip"):.1f}>32.0')
        if not reasons and dc_eval is not None:
            try:
                dc = dc_eval(a, b, want)
                if dc is not None and dc.get('level') in ('flag', 'clash'):
                    reasons.append(f'drumclash={dc.get("level")}')
            except Exception:
                pass
        if not reasons:
            tried.append(dict(rank=idx, win=want, ok=True, pen=hit.get('pen'), R=hit.get('R'), V=hit.get('V')))
            return hit, idx, tried
        tried.append(dict(rank=idx, win=want, ok=False, reasons=reasons, pen=hit.get('pen')))
    return None, None, tried


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

def break_exit_on(rules=None, env=None):
    """Nominate drop-1-end / post-drop-gap-end exits as a family. Off by default.
    The engine or official score still chooses; this does not force the pick.
    Do not write rules.json."""
    env = env or {}
    rules = rules or {}
    return _flag_on(env.get('BREAK_EXIT') or rules.get('BREAK_EXIT') or os.environ.get('BREAK_EXIT'))

def break_exit_anchors(a_yt):
    """Outgoing drop-1 end and the start of the next drop (end of the post-drop
    breakdown / half-time gap). Track structure only; pro labels are not inputs."""
    sa = {}
    try:
        st = os.path.join(getattr(__import__('paths'), 'SRC2', '/workspace/mixes/src2'), 'st', f'{a_yt}.sections.json')
        if os.path.exists(st):
            sa = json.load(open(st)) or {}
        else:
            import sys
            src2 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src2')
            if src2 not in sys.path:
                sys.path.insert(0, src2)
            import sections as _SEC
            sa = _SEC.get(a_yt) or {}
    except Exception:
        return []
    anchors = []
    drops = sa.get('drops') or []
    if drops:
        anchors.append(int(drops[0][1]))
        if len(drops) > 1:
            anchors.append(int(drops[1][0]))
    elif sa.get('breakdown'):
        anchors.append(int(sa['breakdown']))
    return sorted({int(x) for x in anchors if x})

def _win_out_bar(win):
    if not win or win[0] != 'n' or win[1] is None or win[4] is None:
        return None
    return int(win[1]) - int(win[4]) + 1

def add_break_exit_families(fams, cs, a_yt, enabled=False, tol=8):
    """Append a break_exit family per anchor when a natural window in cs exits
    within tol bars. Already-nominated windows are skipped. Never replaces the
    default first pick by itself."""
    if not enabled:
        return list(fams)
    anchors = break_exit_anchors(a_yt)
    if not anchors:
        return list(fams)
    fams = list(fams)
    have = {tuple(c.get('win') or []) for c in fams}
    nats = [c for c in cs if (c.get('win') or [''])[0] == 'n'
            and not c.get('planner_extra') and not c.get('land_extra')]
    for anc in anchors:
        cands = [c for c in nats if _win_out_bar(c.get('win')) is not None
                 and abs(_win_out_bar(c['win']) - anc) <= tol]
        if not cands:
            continue
        best = min(cands, key=lambda c: c.get('cost', 1e9))
        key = tuple(best['win'])
        if key in have:
            continue
        fams.append(dict(fam='break_exit', win=list(best['win']), env={}))
        have.add(key)
    return fams

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
        # PLAN_LAND (off by default): landing breakdown-fade windows exist only for the DRUMCLASH_LAND veto fallback; keep them out of
        # every default path so non-vetoed pairs pick exactly as before
        cs_land = [c for c in cs if c.get('land_extra')]
        cs = [c for c in cs if not c.get('land_extra')]
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
        # BREAK_EXIT=1 (off by default, 2026-11-24): nominate drop-1-end /
        # post-drop-gap-end exits as a family so the engine or official score
        # can choose them (ukf__10: pro left at breakdown ~133, default stayed
        # on the outro at 241). Does not force the pick. Do not write rules.json.
        be_info = None
        if break_exit_on(rules, env):
            be_info = dict(enabled=True, anchors=break_exit_anchors(a))
            fams = add_break_exit_families(fams, cs, a, enabled=True)
            be_info['nominated'] = [c['win'] for c in fams if c.get('fam') == 'break_exit']
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
        # CONSONANCE=1 (off by default, 2026-11-19 research): psychoacoustic roughness between the two decks'
        # mid-band spectral peaks over the blend (src2/consonance.py, after Gebhardt, Davies & Seeber 2016).
        # Adds W*log(R/R_default) to each family's pick cost and nominates one 'cons_cue' window. Not in rules.json.
        cons_info = None
        if _flag_on(env.get('CONSONANCE') or rules.get('CONSONANCE') or os.environ.get('CONSONANCE')):
            import consonance as _CO
            _w = _CO.weight(rules.get('CONSONANCE_W', os.environ.get('CONSONANCE_W')))
            _def = min(scored, key=lambda x: x[0])[1]
            r_ref = _CO.win_roughness(a, b, _def['win'])
            cons_info = dict(w=_w, default_fam=_def['fam'], default_win=list(_def['win']), r_default=r_ref, terms={})
            _cw, _cr = _CO.cons_cue(cs, _def['win'], a, b, pen_slack=float(rules.get('CONS_PEN_SLACK', 15)))
            if _cw is not None and not any(list(c['win']) == list(_cw) for _, c in scored):
                _c = dict(fam='cons_cue', win=list(_cw), env={})
                # exactly the same pick-cost terms as the family loop above (hint, length_pref, prefer_family, loop, phase/linger, family)
                _cost = 0.0
                if hw and hb is not None:
                    _cost += hw * abs(float(_cw[1]) - hb) / max(nb, 1)
                if lp and _cw[4] != lp:
                    _cost += 0.15
                if pref and not str(_c['fam']).startswith(str(pref)):
                    _cost += float(rules.get('family_prior_w') or 0)
                if _cw[0] in ('la', 'lb', 'ab', 'lx'):
                    _cost += float(rules.get('loop_fam_pen') or 0)
                _pw, _lw, _bw = float(rules.get('phase_pref_w') or 0), float(rules.get('linger_pen_w') or 0), float(rules.get('breakdown_pen_w') or 0)
                if _pw or _lw or _bw:
                    _cost += _phase_pick_cost(a, b, _cw, _pw, _lw, _bw)
                _cost += family_cost('cons_cue', rules)
                scored.append((_cost, _c)); cons_info['cons_cue'] = dict(win=list(_cw), r=_cr, base_cost=round(_cost, 4))
            new_scored = []
            for cost, c in scored:
                r = _cr if c['fam'] == 'cons_cue' else _CO.win_roughness(a, b, c['win'])
                t = _CO.cost_term(r, r_ref, _w)
                cons_info['terms'][c['fam']] = dict(r=r, term=round(t, 4), base=round(cost, 4))
                new_scored.append((cost + t, c))
            scored = new_scored
        # SLOWPAIR=1 (off by default, 2026-11-20 research): pair-aware hard slowdown / half-time
        # handling (src2/slowpair.py). Adds COST to a clashing family and nominates one 'slowpair'
        # alternative from already-scored engine candidates. SLOWPAIR_EXIT=1 keeps only Case A
        # (exit moves; no cue moves). SLOWPAIR_COND=1 further limits Case A to the drop-leave /
        # hard-outro shape. Not in rules.json.
        sp_info = None
        if _flag_on(env.get('SLOWPAIR') or rules.get('SLOWPAIR') or os.environ.get('SLOWPAIR') or env.get('SLOWPAIR_COND') or rules.get('SLOWPAIR_COND') or os.environ.get('SLOWPAIR_COND')):
            import slowpair as _SP
            def _sp_cost(win, fam):
                c = dict(fam=fam, win=list(win), env={})
                cost = 0.0
                if hw and hb is not None:
                    cost += hw * abs(float(win[1]) - hb) / max(nb, 1)
                if lp and win[4] != lp:
                    cost += 0.15
                if pref and not str(fam).startswith(str(pref)):
                    cost += float(rules.get('family_prior_w') or 0)
                if win[0] in ('la', 'lb', 'ab', 'lx'):
                    cost += float(rules.get('loop_fam_pen') or 0)
                _pw = float(rules.get('phase_pref_w') or 0); _lw = float(rules.get('linger_pen_w') or 0); _bw = float(rules.get('breakdown_pen_w') or 0)
                if _pw or _lw or _bw:
                    cost += _phase_pick_cost(a, b, win, _pw, _lw, _bw)
                cost += family_cost(fam, rules)
                return cost
            scored, sp_info = _SP.plan_pair(cs, min(scored, key=lambda x: x[0])[1]['win'], a, b, scored=scored, base_cost=_sp_cost)
        # DRUMCLASH=1 (off by default, 2026-11-20 beats RCA; src2/drumclash.py): confidence-gated drum-on-drum train-wreck detector on
        # each family's window (decks' own percussive kick/snare onsets as the engine places them; lock fallback applied, residual
        # decides). level 'clash' (> HIGH, majority of bars agree) gets DRUMCLASH_W x (1 + confidence), very heavy; 'gray' (pro p95..HIGH)
        # gets DRUMCLASH_GRAY_W x confidence; 'clean' is never touched. When every family is 'clash' the
        # lowest-engine-cost unflagged natural window from cs (one deck carries the drums, or the decks lock) is nominated as 'clash_alt'.
        clash_info = None
        if _flag_on(env.get('DRUMCLASH') or rules.get('DRUMCLASH') or os.environ.get('DRUMCLASH')):
            import drumclash as _DC
            _W = float(rules.get('DRUMCLASH_W') or os.environ.get('DRUMCLASH_W') or 5.0)
            _GW = float(rules.get('DRUMCLASH_GRAY_W') or os.environ.get('DRUMCLASH_GRAY_W') or 0.1)
            clash_info = dict(w=_W, gray_w=_GW, terms={})
            _new = []
            for cost, c in scored:
                v = (_DC.window_eval_pt if _DC.KIND == 'lattice' else _DC.window_eval)(a, b, c['win'])
                if v is not None:
                    clash_info['terms'][c['fam']] = dict(win=list(c['win']), confidence=v['confidence'], level=v['level'], flagged=v['flagged'],
                                                         raw=v['raw']['confidence'], fallback_lock_ms=v.get('fallback_lock_ms'), kind=v['raw'].get('kind'))
                    if _DC.KIND == 'lattice':
                        # pick time is an upper bound (unity levels, no fader): mild only; the render hard check below is the veto
                        if v['level'] != 'clean':
                            cost += _GW * v['confidence']
                    elif v['level'] == 'clash':      # v2: majority of drum-on-drum bars agree on one kick+snare offset: veto-level
                        cost += _W * (1.0 + v['confidence'])
                    elif v['level'] == 'gray':     # above the pro p95 but not a majority: mild, near-tie breaker only
                        cost += _GW * v['confidence']
                _new.append((cost, c))
            scored = _new
            if clash_info['terms'] and all(t['level'] == 'clash' for t in clash_info['terms'].values()):
                _have = {tuple(c['win']) for _, c in scored}
                _alts = sorted((c for c in cs if (c.get('win') or [''])[0] == 'n' and tuple(c['win']) not in _have and not c.get('planner_extra')),
                               key=lambda c: c['cost'])
                _base = min(x for x, _ in scored) - _W  # best clashing family's cost without the clash penalty
                for c in _alts[:40]:
                    v = (_DC.window_eval_pt if _DC.KIND == 'lattice' else _DC.window_eval)(a, b, c['win'])
                    if v is not None and v['level'] == 'clean':
                        _alt = dict(fam='clash_alt', win=list(c['win']), env={})
                        scored.append((max(_base, 0.0) + 0.3 + family_cost('nat_short', rules), _alt))
                        clash_info['clash_alt'] = dict(win=list(c['win']), confidence=v['confidence'], n_dd=v['n_dd'], engine_cost=round(float(c['cost']), 4))
                        break
        scored.sort(key=lambda x: x[0])
        pick = scored[0][1]
        engine_default_win = list(pick.get('win') or [])
        if cons_info is not None:
            cons_info['pick_fam'] = pick['fam']; cons_info['changed'] = list(pick['win']) != cons_info['default_win'] or pick['fam'] != cons_info['default_fam']
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
        # REPLICA=1 (off by default, 2026-11-18): pro-replication window from track structure
        # (src2/replica_rule.py). Applied only when the engine scored that exact window.
        replica_info = None
        if _flag_on(env.get('REPLICA') or rules.get('REPLICA')):
            import replica_rule as _RR
            import sections as _SEC
            _gated = _RR.mode(env.get('REPLICA') or rules.get('REPLICA')) == 'gated'
            _fb = None if _gated else a  # gated: primary detector only (no fine-fallback breakdown)
            if _gated:
                want, _gi = _RR.gate(_SEC.get(a), _SEC.get(b), a_id=a); why = _gi
            else:
                want, why = _RR.window(_SEC.get(a), _SEC.get(b), a_id=a)
            replica_info = dict(want=want, why=why, applied=False, mode='gated' if _gated else 'on')
            if want:
                hit = next((c for c in cs if list(c.get('win') or []) == list(want)), None)
                if hit is None and want[4] == 32:
                    want16, why16 = _RR.window(_SEC.get(a), _SEC.get(b), X=16, a_id=_fb)
                    hit = next((c for c in cs if want16 and list(c.get('win') or []) == list(want16)), None)
                    if hit is not None: want, why = want16, why16
                if hit is not None:
                    pick = dict(fam='replica_bd_drop', win=list(want), env={}); fade = {}
                    replica_info = dict(want=want, why=why, applied=True)
                else:
                    replica_info['reason'] = 'win_not_in_cs'
        # DROPCAND=exit|cue (off by default, 2026-11-18 late): force the drop-exit / drop-cue window when the engine scored it
        drop_info = None
        _dm = None
        if env.get('DROPCAND') or rules.get('DROPCAND'):
            import replica_rule as _RR
            import sections as _SEC
            _dm = _RR.drop_mode(env.get('DROPCAND') or rules.get('DROPCAND'))
        if _dm in ('exit', 'cue'):
            hit = None
            for _X in (16, 32):
                want, why = _RR.drop_window(_SEC.get(a), _SEC.get(b), _dm, X=_X)
                hit = next((c for c in cs if want and list(c.get('win') or []) == list(want)), None)
                if hit is not None: break
            drop_info = dict(mode=_dm, want=want, why=why, applied=hit is not None)
            if hit is not None:
                pick = dict(fam='drop_' + _dm, win=list(want), env={}); fade = {}
            else:
                drop_info['reason'] = 'win_not_in_cs'
        # PICKER_WIN (off by default, 2026-11-19 nightly): play the learned picker's window for this pair when the engine scored it
        picker_info = None
        if os.environ.get('PICKER_WIN'):
            _pw = json.load(open(os.environ['PICKER_WIN'])).get(f'{a}|{b}')
            if _pw:
                hit = next((c for c in cs if list(c.get('win') or []) == [_pw[0], int(_pw[1]), None, int(_pw[3]), int(_pw[4])]), None)
                picker_info = dict(want=_pw, applied=hit is not None)
                if hit is not None:
                    pick = dict(fam='picker', win=list(hit['win']), env={}); fade = {}
        # PICKER_STYLE_GATED=1 (off by default, 2026-11-24): play the style-gated
        # learned picker's window when the engine scored it. Window map is
        # replica/picker_style_gated_windows.json (override PICKER_STYLE_GATED_MAP).
        # Does not write rules.json. Abstains if the pair or window is missing.
        if picker_style_gated_on(rules, env):
            _mp = _picker_style_gated_map_path(env)
            _pw, _ranked = None, None
            try:
                _tab = json.load(open(_mp))
                _pw = (_tab.get('by_yt') or {}).get(f'{a}|{b}') or _tab.get(f'{a}|{b}')
                _ranked = (_tab.get('ranked_by_yt') or {}).get(f'{a}|{b}')
            except Exception as _ex:
                picker_info = dict(enabled=True, error=f'{type(_ex).__name__}: {_ex}', map=_mp)
                _pw, _ranked = None, None
            if _ranked:
                import drumclash as _DCp
                _dc_fn = _DCp.window_eval_pt if getattr(_DCp, 'KIND', None) == 'lattice' else _DCp.window_eval
                hit, r_idx, tried = select_compatible_picker_window(a, b, _ranked, cs, pick.get('win'), dc_eval=_dc_fn)
                if hit is not None:
                    injected = bool(hit.get('planner_extra'))
                    picker_info = dict(enabled=True, want=list(hit['win']), rank_idx=r_idx, applied=True, injected_cs=injected, map=_mp, tried=tried)
                    pick = dict(fam='picker_style_gated', win=list(hit['win']), env={}); fade = {}
                else:
                    picker_info = dict(enabled=True, want=list(_ranked[0]), applied=False, injected_cs=False, map=_mp, why='none_compatible', tried=tried)
            elif _pw:
                _want = [_pw[0], int(_pw[1]), None, int(_pw[3]), int(_pw[4])]
                hit = next((c for c in cs if list(c.get('win') or []) == _want), None)
                injected = False
                if hit is None and picker_inject_cs_on(rules, env) and _want[0] == 'n':
                    try:
                        import sections as _SECp
                        _sa_p, _sb_p = _SECp.get(a), _SECp.get(b)
                        _na = int(_sa_p.get('music_end') or _sa_p.get('n_bars') or 999)
                        _nb = int(_sb_p.get('music_end') or _sb_p.get('n_bars') or 999)
                        _e, _ib, _X = int(_want[1]), int(_want[3]), int(_want[4])
                        if _X > 0 and 16 <= _e - _X and _e <= _na and 0 <= _ib and _ib + _X <= _nb - 16:
                            hit = dict(fam='picker_style_gated', win=list(_want), env={}, cost=0.0, picker_injected=True)
                            cs.append(hit)
                            injected = True
                    except Exception:
                        hit = None
                picker_info = dict(enabled=True, want=_want, applied=hit is not None, injected_cs=injected, map=_mp)
                if hit is not None:
                    pick = dict(fam='picker_style_gated', win=list(hit['win']), env={}); fade = {}
            elif picker_info is None:
                picker_info = dict(enabled=True, applied=False, map=_mp, why='no_entry')

        # RIDEGATE=1 (off by default, 2026-11-26): live (non-map) ridegate path.
        # Computes ride/leave + exit+cue at render time from track features and
        # the engine's default window. Does not write rules.json. Abstains (keeps
        # the default pick) when the pack is missing or the window is illegal.
        # When this flag is on it takes precedence over the PICKER_STYLE_GATED map.
        ridegate_info = None
        if ridegate_live_on(rules, env):
            _rep = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'replica')
            if _rep not in sys.path:
                sys.path.insert(0, _rep)
            try:
                import ridegate_live as _RG
                import sections as _SECr
                _pack = _RG.load_pack(_RG.pack_path(env))
                _sa_r, _sb_r = _SECr.get(a), _SECr.get(b)
                hit, dec, injected = _RG.maybe_apply(_pack, _sa_r, _sb_r,
                                                     engine_default_win or pick.get('win'), cs,
                                                     a_yt=a, b_yt=b)
                ridegate_info = dict(enabled=True, path='live', want=(dec.get('win') if dec else None),
                                     applied=hit is not None, injected_cs=injected,
                                     abstain=bool(dec.get('is_default')) if dec else None,
                                     p_leave=(dec.get('p_leave') if dec else None))
                os.environ.pop('RIDEGATE_WIN', None)
                if hit is not None:
                    pick = dict(fam='ridegate_live', win=list(hit['win']), env={}); fade = {}
                    os.environ['RIDEGATE_WIN'] = json.dumps(list(hit['win']))
            except Exception as _ex:
                os.environ.pop('RIDEGATE_WIN', None)
                ridegate_info = dict(enabled=True, path='live', applied=False,
                                     error=f'{type(_ex).__name__}: {_ex}')
        pick['env'] = {**env, **dict(pick.get('env') or {}), **fade}
        # FADE=graphcut is a renderer flag: keep it on top of any family FADE so a cohort
        # eval compares the same windows under a different handover, not a different family.
        if str((rules or {}).get('FADE'))=='graphcut' or env.get('GRAPH_CUT')=='1':
            pick['env']['FADE']='graphcut'; pick['env']['GRAPH_CUT']='1'
        dk, M = BB.render(pick, a, b, tag)
        # DRUMCLASH hard check (rendered decks, after BLEND_LOCK + its drum-onset fallback): a confident train wreck is never kept
        # when another scored window renders clean; the next-cheapest unflagged family is rendered instead.
        if clash_info is not None:
            _hc = (M['trans'][0].get('drumclash') or {})
            clash_info['hard'] = dict(fam=pick.get('fam'), win=list(pick.get('win') or []), flagged=_hc.get('flagged'), level=_hc.get('level'),
                                      confidence=_hc.get('confidence'), fallback=_hc.get('applied'))
            if _hc.get('level') == 'gray':
                clash_info['gray'] = True   # listed for an A/B, never re-picked
            if _hc.get('flagged'):
                # veto -> re-rank EVERY natural window in cs (all exits incl. breakdown exits, all cues, 16/32 bars) plus the scored
                # families, keep the ones pick time does not read as a clash, and order them by structural mismatch first: the share
                # of overlap bars where exactly one deck is inside a drop (one straight beat against the other's intro/build/
                # breakdown, the hm09 fault). 0 = both decks in drops (drum swap / double drop, lattice-checked on render) or
                # neither (fading over a breakdown, what the pro did on hm09). Then the engine's own cost. First render that is not
                # a clash wins (at most 4 extra renders). the listener's ear is the judge of the replacement, not this ordering.
                import sections as _SECd
                _sa, _sb = _SECd.get(a), _SECd.get(b)
                def _indrop(sec, k):
                    return any(lo <= k < hi for lo, hi in (sec.get('drops') or []))
                def _mismatch(w):
                    X = int(w[4]); ka = int(w[1]) - X; kb = int(w[3])
                    return sum(1 for j in range(X) if _indrop(_sa, ka + j) != _indrop(_sb, kb + j)) / max(X, 1)
                def _bothdrop(w):
                    X = int(w[4]); ka = int(w[1]) - X; kb = int(w[3])
                    return sum(1 for j in range(X) if _indrop(_sa, ka + j) and _indrop(_sb, kb + j)) / max(X, 1)
                _ecost = {}
                for c in cs + (cs_land if _flag_on(rules.get('DRUMCLASH_LAND') or os.environ.get('DRUMCLASH_LAND')) else []):
                    if (c.get('win') or [''])[0] == 'n' and (not c.get('planner_extra') or c.get('land_extra')):
                        _ecost[tuple(c['win'])] = min(_ecost.get(tuple(c['win']), 1e9), float(c['cost']))
                _pool = {}
                for _cost, _c in sorted(scored, key=lambda x: x[0]):
                    if (_c.get('win') or [''])[0] == 'n' and tuple(_c['win']) not in _pool: _pool[tuple(_c['win'])] = _c
                for w in _ecost:
                    if w not in _pool: _pool[w] = dict(fam='clash_alt', win=list(w), env={})
                _pool.pop(tuple(pick['win']), None)
                _rank = []
                for w, _c in _pool.items():
                    _v = _DC.window_eval_pt(a, b, list(w)) if _DC.KIND == 'lattice' else None
                    if _v is not None and _v['level'] == 'clash': continue
                    _mm = _mismatch(w); _bd = _bothdrop(w)
                    # class 0: neither deck in a drop on any overlap bar (fade over a breakdown / instrumental: the pro's hm09 exit,
                    # the listener 11:29 'even fading over an instrumental / breakdown'); 1: no mismatch but both in drops (double drop /
                    # drum swap); 2+: the rest by mismatch quarter
                    _cls = 0 if (_mm == 0 and _bd == 0) else (1 if _mm == 0 else 2 + float(np.ceil(_mm * 4) / 4))
                    _rank.append((_cls, _ecost.get(w, 1e9), _c, round(_mm, 3), round(_bd, 3)))
                _rank.sort(key=lambda x: (x[0], x[1]))
                clash_info['fallback_rank'] = [dict(win=list(x[2]['win']), fam=x[2]['fam'], cls=x[0], mismatch=x[3], both_drop=x[4], engine_cost=round(x[1], 2)) for x in _rank[:6]]
                _cands = [x[2] for x in _rank]
                if _flag_on(rules.get('DRUMCLASH_RISK') or os.environ.get('DRUMCLASH_RISK')):
                    # dclash5 (the listener 2:55 PM: 'depends how big the risk of a train wreck is with a drop ... I didn't rule it out if
                    # it's safe'): render the 2 cheapest of each class (breakdown fade, double drop, rest), then pick by
                    # engine cost + risk. risk = RISK_W x r for a clean render (r = rendered confidence / its pro-p95 flag, worse
                    # of lattice and pulse, <= 1) and GRAY_PEN + RISK_W x r for a gray render; a clash render is out. A confidently
                    # clean double drop competes on cost; a gray one loses to a clean breakdown fade; if nothing renders clean the
                    # least risky (the breakdown fade, usually) is kept.
                    _RW = float(rules.get('DRUMCLASH_RISK_W') or os.environ.get('DRUMCLASH_RISK_W') or 100.0)
                    _GP = float(rules.get('DRUMCLASH_GRAY_PEN') or os.environ.get('DRUMCLASH_GRAY_PEN') or 500.0)
                    _byc = {}
                    for x in _rank: _byc.setdefault(0 if x[0] == 0 else (1 if x[0] == 1 else 2), []).append(x)
                    _try = sorted([x for k in sorted(_byc) for x in _byc[k][:2]], key=lambda x: (x[0], x[1]))
                    # dclash6 (DRUMCLASH_LAND=1; the listener 3:45 PM rated hm09 144/48/16 4/5 > 144/32/32 3.5 > default clash 2.5; the pro
                    # did the same): 'landing' breakdown fades = the outgoing exits exactly where its breakdown ends (out_end = start
                    # of one of A's drops, every A overlap bar outside a drop) and the incoming's drop lands there (in_begin + X =
                    # start of one of B's drops, every B overlap bar outside a drop). All allowed ones in cs are rendered (cap 6),
                    # shortest overlap first (the pro brought only B's last build bars in), and the first that renders CLEAN wins;
                    # otherwise the dclash5 risk-weighted pick stands.
                    _land_on = _flag_on(rules.get('DRUMCLASH_LAND') or os.environ.get('DRUMCLASH_LAND'))
                    _land = []
                    if _land_on:
                        _da = [lo for lo, hi in (_sa.get('drops') or [])]; _db = [lo for lo, hi in (_sb.get('drops') or [])]
                        for x in _rank:
                            w = x[2]['win']; X = int(w[4])
                            if x[0] == 0 and int(w[1]) in _da and int(w[3]) + X in _db:
                                _land.append(x)
                        _land.sort(key=lambda x: (int(x[2]['win'][4]), x[1])); _land = _land[:6]
                        _seenw = {tuple(x[2]['win']) for x in _land}
                        _try = _land + [x for x in _try if tuple(x[2]['win']) not in _seenw]
                        clash_info['landing'] = [dict(win=list(x[2]['win']), engine_cost=round(x[1], 2), plan_land=tuple(x[2]['win']) in {tuple(c['win']) for c in cs_land}) for x in _land]
                    _landbest = None
                    _best = None
                    for _ti, x in enumerate(_try):
                        _c = x[2]; _p2 = dict(_c); _p2['env'] = {**env, **dict(_c.get('env') or {})}
                        _dk2, _M2 = BB.render(_p2, a, b, f'{tag}r{_ti}')   # own tag: every render must keep its own mp3
                        _h2 = (_M2['trans'][0].get('drumclash') or {}); _fin = _h2.get('after') or _h2.get('before') or {}
                        _lc = float((_fin.get('lattice') or {}).get('confidence') or 0); _pc = float((_fin.get('pulse') or {}).get('confidence') or 0)
                        _r = max(_lc / max(_DC.FLAG3, 1e-3), _pc / max(_DC.PULSE_FLAG, 1e-3))
                        _lv = _h2.get('level')
                        _risk = None if _lv == 'clash' else (_RW * min(_r, 1.0) + (_GP + _RW * (_r - 1.0) if _lv == 'gray' else 0.0))
                        _tot = None if _risk is None else x[1] + _risk
                        clash_info.setdefault('retries', []).append(dict(fam=_c['fam'], win=list(_c['win']), cls=x[0], level=_lv, kind=_h2.get('kind'),
                                                                         lattice=_lc, pulse=_pc, engine_cost=round(x[1], 2),
                                                                         risk=None if _risk is None else round(_risk, 1), total=None if _tot is None else round(_tot, 1)))
                        if _tot is not None and (_best is None or _tot < _best[0]):
                            _best = (_tot, _p2, _dk2, _M2)
                        if _land_on and _landbest is None and _lv == 'clean' and any(x is y for y in _land):
                            _landbest = (_tot, _p2, _dk2, _M2); break   # landing renders come first: stop at the first clean one
                    if _landbest is not None:
                        _best = _landbest; clash_info['landing_pick'] = list(_landbest[1]['win'])
                    if _best is not None:
                        _, pick, dk, M = _best; clash_info['hard']['replaced_by'] = dict(fam=pick['fam'], win=list(pick['win']), total=round(_best[0], 1))
                else:
                    for _c in _cands[:4]:
                        _p2 = dict(_c); _p2['env'] = {**env, **dict(_c.get('env') or {})}
                        _dk2, _M2 = BB.render(_p2, a, b, tag)
                        _h2 = (_M2['trans'][0].get('drumclash') or {})
                        clash_info.setdefault('retries', []).append(dict(fam=_c['fam'], win=list(_c['win']), flagged=_h2.get('flagged'), level=_h2.get('level'),
                                                                         kind=_h2.get('kind'), confidence=_h2.get('confidence')))
                        if not _h2.get('flagged'):
                            pick, dk, M = _p2, _dk2, _M2; clash_info['hard']['replaced_by'] = dict(fam=_c['fam'], win=list(_c['win']))
                            break
        # Official hard-check fallback is off by default (HARD_FALLBACK=0) so the
        # baseline floor stays like-for-like (train 32.40 / held-out 34.07). It is a
        # promotion candidate on its own; do not write rules.json. Test hook
        # HARDCHECK_TEST_FORCE_WIN is also ignored unless the flag is on.
        _hc_on = hard_fallback_on(rules, env)
        _fw = os.environ.get('HARDCHECK_TEST_FORCE_WIN') if _hc_on else None
        if _fw:
            _parts = []
            for _i, _p in enumerate(_fw.split(',')):
                if _p in ('', 'None', 'null'):
                    _parts.append(None)
                elif _i == 0:
                    _parts.append(_p)
                else:
                    _parts.append(int(float(_p)))
            _want = tuple(_parts)
            if tuple(pick.get('win') or []) != _want:
                _hit = next((c for _, c in scored if tuple(c.get('win') or []) == _want), None)
                if _hit is None:
                    _hit = dict(fam='hc_force', win=list(_parts), env={})
                pick = dict(_hit)
                pick['env'] = {**env, **dict(_hit.get('env') or {})}
                dk, M = BB.render(pick, a, b, tag + 'f')
        # Official hard checks (pumping, beat_clash, bass_hole) veto a failing first
        # pick when a later scored candidate renders clean (2026-11-23 JS13 STRUCT_MID
        # 128/16/32 pumped at 5.2 dB over the 4.54 p95). Cap extra renders. Gated on
        # HARD_FALLBACK=1; default is off. Does not write rules.json.
        _hc_fb = dict(enabled=False)
        if _hc_on:
            try:
                _rdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'replica')
                if _rdir not in sys.path: sys.path.insert(0, _rdir)
                import hardcheck as _HC
                def _hc_of(_M, _tg):
                    _mp = os.path.join('/tmp/protrans_bench', f'{_tg}_{a}_{b}_hc.json')
                    json.dump(_M, open(_mp, 'w'), default=str)
                    return _HC.check(_mp)
                _h0 = _hc_of(M, tag)
                _hc_fb = dict(enabled=True, first=dict(fam=pick.get('fam'), win=list(pick.get('win') or []),
                                         hard_fail=bool(_h0.get('hard_fail')), pumping=_h0.get('pumping'),
                                         pump_db=_h0.get('pump_db'), beat_clash=_h0.get('beat_clash'),
                                         bass_hole=_h0.get('bass_hole'), lows_dip_db=_h0.get('lows_dip_db')))
                if _h0.get('hard_fail'):
                    _seen = {tuple(pick.get('win') or [])}
                    _alts = []
                    for _cost, _c in scored:
                        _w = tuple(_c.get('win') or [])
                        if _w in _seen: continue
                        _seen.add(_w); _alts.append(_c)
                    for _c in sorted((c for c in cs if (c.get('win') or [''])[0] == 'n' and not c.get('planner_extra') and not c.get('land_extra')),
                                     key=lambda c: c.get('cost', 1e9)):
                        _w = tuple(_c['win'])
                        if _w in _seen: continue
                        _seen.add(_w); _alts.append(dict(fam=_c.get('fam') or 'hc_alt', win=list(_c['win']), env={}))
                    _tries = []
                    for _ti, _c in enumerate(_alts[:6]):
                        _p2 = dict(_c); _p2['env'] = {**env, **dict(_c.get('env') or {})}
                        _dk2, _M2 = BB.render(_p2, a, b, f'{tag}h{_ti}')
                        _h2 = _hc_of(_M2, f'{tag}h{_ti}')
                        _tries.append(dict(fam=_p2.get('fam'), win=list(_p2.get('win') or []),
                                           hard_fail=bool(_h2.get('hard_fail')), pumping=_h2.get('pumping'),
                                           pump_db=_h2.get('pump_db'), beat_clash=_h2.get('beat_clash'),
                                           bass_hole=_h2.get('bass_hole'), lows_dip_db=_h2.get('lows_dip_db')))
                        if not _h2.get('hard_fail'):
                            pick, dk, M = _p2, _dk2, _M2
                            _hc_fb['replaced_by'] = _tries[-1]
                            break
                    _hc_fb['retries'] = _tries
                    if 'replaced_by' not in _hc_fb:
                        _hc_fb['kept_failing'] = True
            except Exception as ex:
                _hc_fb = dict(enabled=True, error=f'{type(ex).__name__}: {ex}')
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
                    ranker=(ranker_info if ranker_on else None), replica=replica_info, dropcand=drop_info, picker=picker_info, ridegate=ridegate_info,
                    consonance=cons_info, slowpair=sp_info, drumclash=clash_info, hard_fallback=_hc_fb,
                    break_exit=(None if be_info is None else dict(be_info, picked=(pick.get('fam')=='break_exit'), pick_win=list(pick.get('win') or []))))
        return info
    finally:
        os.chdir(oldcwd)
        for k,v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

if __name__ == '__main__':
    print('use run.py')
