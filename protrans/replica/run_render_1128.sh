#!/usr/bin/env bash
# n1128 entry point. Wrapper only — arms come from the card.
# See run_nightly_card.sh for why n1127's run_render_1127.sh was the wrong pattern.
set -euo pipefail
exec "$(dirname "$0")/run_nightly_card.sh" n1128
