#!/usr/bin/env bash
# restore stretched stems for the Mix 09 crate (4 in parallel), excluding the tracks still being prepped
cd /workspace/mixes/src2
for b in $(cat ../mix09/crate.txt); do [ -f "st/$b.json" ] && [ -f "st/$b.sections.json" ] && echo $b; done | grep -v -E 'rjoK9MXhMYc|uWDLe0zNgZY|zEvLsOVhg0I|J3oTRY7AdE4|jIqXQ8EbKNY' | xargs -P4 -n1 python3 restore_audio.py
ls st/*.wav | wc -l
