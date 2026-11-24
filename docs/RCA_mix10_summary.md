# Mix 10: why it keeps failing (one-page summary)

2026-11-24 ET. Full write-up: `docs/RCA_mix10_failure_loop.md`. Chart: `deliver/protrans/diagnostics/rca_2026-11-24_mix10_failure_loop.png`.

## What is going wrong

The mixer checks a mix four times, and each check sees more than the one before it:

1. **Planning** picks the track order and blend spots using rough estimates.
2. **Dry check** tests the plan on paper, with no audio.
3. **Render checks** measure the finished audio.
4. **Final tests** measure the finished audio in more detail.

Each fix so far taught one early check about one problem. The next build then failed on a problem that only the audio checks can hear. That is why it feels like hammering nails: each round finds the next blind spot.

## The numbers

- 22 audio problems turned up across the Mix 10 builds.
- 10 of them could only be found after rendering the whole mix. No early check looks for them.
- 3 plans passed the dry check. All 3 failed later.
- 8 of the 13 kinds of problem have no early check at all: bass gaps, level dips at the bass swap, entries off the beat grid, beats drifting in a blend, abrupt fade-outs, quiet holes, loudness jumps, and peaks running hot.
- Each full render plus tests took 50 minutes to almost 5 hours, so each lesson cost hours.
- The repair tool ran out of time 3 times. Each repair try re-checks the whole hour-long mix, which took about 10 minutes on a busy box. Its "fixed" verdict also comes from the dry check, which cannot hear the problems it was fixing.

## The four root causes in plain words

1. **The early check can't hear.** It reads the plan, not the audio, so it passes mixes that are sure to fail.
2. **The planner and the dry check disagree.** The planner has its own cheaper copy of each rule, and the copies drift. Seven of the 12 early catches were the planner and the dry check disagreeing about the same problem.
3. **Repair is slow, local, and checks with the wrong tool.** It patches one blend at a time, takes 10 minutes per try, and can't confirm the fix without another full render.
4. **Some problems aren't about a blend at all.** A track's own quiet breakdown left playing alone (Hayling, Memory Lane), or peaks running hot from the mastering gain, can't be fixed by moving a blend. They need a rule at the track or master level.

## The fix

1. **Test each blend on its own audio before choosing it.** Render just that blend (about 40 seconds of audio) and run the real audio checks on it. Remember the result. The planner then picks only blends that have already passed. This takes about 5 to 10 minutes per plan, instead of hours per full render. It would have caught 7 of the 10 late problems. About 2 days of work.
2. **Track and master rules.** Never leave a track's deep breakdown playing alone, and pick the master gain from a quick peak test. These cover the other 3 late problems. About 1 day.
3. **One rulebook.** Every stage uses the same check code and the same limits, so they can't drift. About 1 day.
4. **Faster, smarter repair.** Check each try with the single-blend test (seconds, not 10 minutes). If a pair can't be fixed, hand it back to the planner. Half a day to 1 day.

Total: about 4 to 5 days. After that, the full render confirms a good mix instead of being the place where the system finds new problems. No limits get loosened.
