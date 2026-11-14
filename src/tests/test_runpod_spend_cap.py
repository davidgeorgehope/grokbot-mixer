"""Runpod spend cap is per mix; Mix 08 totals must not cap later mixes."""
import os, subprocess, sys, textwrap
import pytest

TT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'visuals', 'code', 'turntable_viz'))
sys.path.insert(0, TT)
import mix_key as mk  # noqa: E402

SCRIPT = os.path.join(TT, 'runpod_render.sh')


@pytest.mark.parametrize("path,key", [
    ("/workspace/mixes/visuals/dj-mix-09-visuals-1080p30.mp4", "mix09"),
    ("/workspace/mixes/deliver/09/dj-mix-09-128k.mp3", "mix09"),
    ("/workspace/mixes/src2/mix09_r5b_master.wav", "mix09"),
    ("/workspace/mixes/deliver/08/dj-mix-08-128k.mp3", "mix08"),
    ("/workspace/mixes/visuals/dj-mix-08-visuals-1080p30.mp4", "mix08"),
    ("mix10_r1_master.wav", "mix10"),
    ("/tmp/not-a-mix.mp4", "unknown"),
])
def test_mix_key_from_paths(path, key):
    assert mk.mix_key(path) == key
    assert subprocess.check_output([sys.executable, os.path.join(TT, "mix_key.py"), path], text=True).strip() == key


def test_mix_key_prefers_first_hit():
    assert mk.mix_key("not-it.mp4", "dj-mix-09-visuals-1080p30.mp4") == "mix09"


def test_default_spend_log_is_per_mix_not_shared():
    log09 = mk.default_spend_log("mix09")
    log08 = mk.default_spend_log("mix08")
    shared = "/workspace/mixes/jobs/runpod-spend.log"
    assert log09 == "/workspace/mixes/jobs/runpod-spend-mix09.log"
    assert log08 == "/workspace/mixes/jobs/runpod-spend-mix08.log"
    assert log09 != shared and log08 != shared
    assert log09 != log08


def test_mix08_shared_log_is_not_the_default_for_later_mixes():
    """The legacy shared ledger still has Mix 08 spend; defaults must not read it."""
    assert mk.default_spend_log(mk.mix_key("dj-mix-09-visuals-1080p30.mp4")) != "/workspace/mixes/jobs/runpod-spend.log"
    assert mk.default_spend_log(mk.mix_key("dj-mix-10-visuals-1080p30.mp4")) != "/workspace/mixes/jobs/runpod-spend.log"


def test_max_spend_usd_default_and_env_override():
    assert mk.default_max_spend_usd(env={}) == 5.0
    assert mk.default_max_spend_usd(env={"MAX_SPEND_USD": "7"}) == 7.0
    assert mk.default_max_spend_usd(env={"MAX_SPEND_USD": "7.0"}) == 7.0
    assert mk.default_max_spend_usd(env={"MAX_SPEND_USD": ""}) == 5.0


def _script_defaults(env, out, mix, extra=""):
    """Evaluate only the ledger defaults from runpod_render.sh (do not run the render)."""
    body = textwrap.dedent(r"""
        set -euo pipefail
        HERE={here!r}
        OUT={out!r}
        MIX={mix!r}
        MIX_KEY=${{MIX_KEY:-$(python3 "$HERE/mix_key.py" "${{OUT:-}}" "${{MIX:-}}")}}
        SPEND_LOG=${{SPEND_LOG:-/workspace/mixes/jobs/runpod-spend-${{MIX_KEY}}.log}}
        MAX_SPEND_USD=${{MAX_SPEND_USD:-5}}
        printf 'KEY=%s LOG=%s CAP=%s\n' "$MIX_KEY" "$SPEND_LOG" "$MAX_SPEND_USD"
    """).format(here=TT, out=out, mix=mix)
    e = os.environ.copy()
    e.pop("SPEND_LOG", None)
    e.pop("MIX_KEY", None)
    e.pop("MAX_SPEND_USD", None)
    e.update(env)
    outp = subprocess.check_output(["bash", "-c", body], env=e, text=True).strip()
    return dict(part.split("=", 1) for part in outp.split())


def test_script_defaults_key_log_and_cap_for_mix09():
    d = _script_defaults({}, "/workspace/mixes/visuals/dj-mix-09-visuals-1080p30.mp4",
                         "/workspace/mixes/deliver/09/dj-mix-09-128k.mp3")
    assert d["KEY"] == "mix09"
    assert d["LOG"].endswith("runpod-spend-mix09.log")
    assert d["LOG"] != "/workspace/mixes/jobs/runpod-spend.log"
    assert d["CAP"] == "5"


def test_script_env_overrides_cap_7_and_spend_log():
    d = _script_defaults(
        {"MAX_SPEND_USD": "7", "SPEND_LOG": "/tmp/custom-spend.log", "MIX_KEY": "mix09"},
        "/workspace/mixes/visuals/dj-mix-09-visuals-1080p30.mp4",
        "/workspace/mixes/deliver/09/dj-mix-09-128k.mp3",
    )
    assert d["KEY"] == "mix09"
    assert d["LOG"] == "/tmp/custom-spend.log"
    assert d["CAP"] == "7"


def test_script_source_still_has_per_mix_default():
    src = open(SCRIPT).read()
    assert "runpod-spend-${MIX_KEY}.log" in src
    assert 'MAX_SPEND_USD=${MAX_SPEND_USD:-5}' in src
    # The old shared default must no longer be the fallback.
    assert "SPEND_LOG=${SPEND_LOG:-/workspace/mixes/jobs/runpod-spend.log}" not in src
