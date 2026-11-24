"""ESTAB (2026-11-24 midnight research, OFF by default): predicted total-energy stability of a candidate blend window.
Idea from MixWeaver (Zhou, Jiang, Zhi, Wu & McAuley, ISMIR 2026), whose transition objective includes "total energy
stability" across the exchange, and from DJustify (arXiv 2610.33434, 2026), whose acoustic checker treats an energy hole
as a placement failure with a re-cue repair. Here it is a pre-render cost on each window: simulate the summed level per
bar from the two decks' stored per-bar levels under an equal-power crossfade, and charge every dB that the deepest
2-bar dip in the middle 80% of the blend falls below the outgoing track's body beyond ESTAB_DB (default 6 dB, the same
6 dB line as THIN_DB / guardrail E1). Bands: full ('all') and lows ('low'); the cost uses the worse of the two.
Nothing here changes a test, a threshold, rules.json or a default; with ESTAB unset/0 the engine is untouched."""
import os, numpy as np

def on():
    return os.environ.get('ESTAB', '0') not in ('', '0')

def weight():
    return float(os.environ.get('ESTAB_W', 20) or 20)

def line_db():
    return float(os.environ.get('ESTAB_DB', 6) or 6)

def _p(db):
    return 10 ** (np.asarray(db, float) / 10)

def predicted_dip(ga, gb, wa, wb):
    """ga/gb: per-bar level dicts (track(x)['g']['bar']); wa/wb: bar lists of the blend. Returns (dip_all_db, dip_low_db)."""
    wa, wb = list(wa), list(wb); n = min(len(wa), len(wb))
    if n < 4: return 0.0, 0.0
    out = []
    for band in ('all', 'low'):
        la = np.asarray(ga.get(band, ga['all']), float); lb = np.asarray(gb.get(band, gb['all']), float)
        body = float(np.percentile(la, 75))
        ka = [min(max(k, 0), len(la) - 1) for k in wa[:n]]; kb = [min(max(k, 0), len(lb) - 1) for k in wb[:n]]
        u = (np.arange(n) + 0.5) / n
        ga_, gb_ = np.cos(np.pi * u / 2) ** 2, np.sin(np.pi * u / 2) ** 2  # equal-power gains (power domain)
        tot = 10 * np.log10(ga_ * _p(la[ka]) + gb_ * _p(lb[kb]) + 1e-12)
        sm = np.convolve(tot, np.ones(2) / 2, 'valid')  # 2-bar smoothing (E1 uses a 3 s window, ~2 bars at 174)
        lo, hi = int(0.1 * len(sm)), max(int(0.9 * len(sm)), int(0.1 * len(sm)) + 1)
        out.append(float(body - sm[lo:hi].min()))
    return out[0], out[1]

def cost(ga, gb, wa, wb):
    da, dl = predicted_dip(ga, gb, wa, wb)
    d = max(da, dl)
    return weight() * max(0.0, d - line_db()), d
