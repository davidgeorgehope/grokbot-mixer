#!/usr/bin/env python3
"""Per-mix identity for the Runpod spend ledger.

Spend for one mix must not count against a later mix. The default ledger path is
jobs/runpod-spend-<mixXX>.log (e.g. mix09), never the legacy shared
jobs/runpod-spend.log that still holds Mix 08 totals.
"""
from __future__ import annotations

import os
import re
import sys

JOBS_DIR = "/workspace/mixes/jobs"
KEY_RE = re.compile(r"mix[-_]?0*(\d+)", re.I)


def mix_key(*paths: str) -> str:
    for s in paths:
        m = KEY_RE.search(os.path.basename(s or ""))
        if m:
            return "mix%02d" % int(m.group(1))
    return "unknown"


def default_spend_log(key: str, jobs_dir: str = JOBS_DIR) -> str:
    return os.path.join(jobs_dir, f"runpod-spend-{key}.log")


def default_max_spend_usd(env=os.environ, default: float = 5.0) -> float:
    raw = env.get("MAX_SPEND_USD")
    if raw is None or raw == "":
        return default
    return float(raw)


if __name__ == "__main__":
    print(mix_key(*sys.argv[1:]))
