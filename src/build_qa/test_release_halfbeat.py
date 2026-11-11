"""Half-beat gate on the selected build (2026-11-11 RCA: Shine In sat 0.46 beat off Dusk To Dawn and passed every check).
Gate: no blend's decks may line up half a beat apart (halfbeat.blend_check: drum phase AND per-bar onset xcorr agree).
Also writes the standard per-blend diagnostic figures to deliver/<MIX_NAME>/diagnostics (generate-only, never fails;
MIX_DIAG=0 skips, MIX_DIAG_DIR overrides the folder)."""
import os, json
import pytest
import checks as C


def _meta():
    for p in (f'{C.SRC}/{C.NAME}_meta.json', f'{C.SRC}/{C.NAME}_dry_meta.json'):
        if os.path.exists(p):
            return p, json.load(open(p))
    pytest.skip('mix meta missing')


def test_no_half_beat_blends():
    import halfbeat as H
    p, M = _meta(); cwd = os.getcwd(); os.chdir(C.SRC)
    try:
        bad = []
        for i, (a, b, wa, wb) in enumerate(H.meta_blends(M)):
            q = M['trans'][i].get('halfbeat') or H.blend_check(a, b, wa, wb)
            if q.get('fail'):
                bad.append((i, a, b, q))
    finally:
        os.chdir(cwd)
    assert not bad, f'decks half a beat apart: {bad}'


def test_diagnostic_figures_generated():
    if os.environ.get('MIX_DIAG', '1') == '0':
        pytest.skip('MIX_DIAG=0')
    import blend_diag
    p, M = _meta(); out = os.environ.get('MIX_DIAG_DIR') or os.path.join('/workspace/mixes/deliver', C.NAME, 'diagnostics')
    os.makedirs(out, exist_ok=True); cwd = os.getcwd(); os.chdir(C.SRC)
    try:
        res = blend_diag.mix_diagnostics(p, out)
    except Exception as e:   # generate-only
        print('diagnostics skipped:', type(e).__name__, e); return
    finally:
        os.chdir(cwd)
    print(f"diagnostics: {sum('png' in r for r in res)}/{len(res)} blends -> {out}")
