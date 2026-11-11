#!/usr/bin/env python3
"""Copy stdin to stdout in small chunks. Abort if throughput is below min_bps after probe_sec.

Exit 0 on success, 7 if too slow, 1 on I/O error. Never buffers the whole stream.
"""
from __future__ import annotations

import argparse
import sys
import time

CHUNK = 256 * 1024


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-sec", type=float, default=60.0)
    ap.add_argument("--min-bps", type=float, default=1_000_000.0)
    ap.add_argument("--log-interval", type=float, default=10.0)
    ap.add_argument("--prefix", default="[stream_guard]")
    args = ap.parse_args()

    def log(msg: str) -> None:
        sys.stderr.write(f"{args.prefix} {msg}\n")
        sys.stderr.flush()

    t0 = time.monotonic()
    last_log = t0
    n = 0
    checked = False
    inf = sys.stdin.buffer
    out = sys.stdout.buffer
    try:
        while True:
            buf = inf.read(CHUNK)
            if not buf:
                break
            out.write(buf)
            out.flush()
            n += len(buf)
            now = time.monotonic()
            elapsed = max(now - t0, 1e-6)
            if now - last_log >= args.log_interval:
                log(f"upload {n / 1e6:.1f}MB in {elapsed:.0f}s ({n / elapsed / 1e6:.2f} MB/s)")
                last_log = now
            if not checked and elapsed >= args.probe_sec:
                checked = True
                rate = n / elapsed
                if rate < args.min_bps:
                    log(
                        f"upload too slow: {n / 1e6:.1f}MB in {elapsed:.0f}s "
                        f"({rate / 1e6:.2f} MB/s < {args.min_bps / 1e6:.2f} MB/s); aborting"
                    )
                    return 7
        elapsed = max(time.monotonic() - t0, 1e-6)
        log(f"upload done {n / 1e6:.1f}MB in {elapsed:.0f}s ({n / elapsed / 1e6:.2f} MB/s)")
        return 0
    except BrokenPipeError:
        log("broken pipe")
        return 1
    except KeyboardInterrupt:
        return 143


if __name__ == "__main__":
    sys.exit(main())
