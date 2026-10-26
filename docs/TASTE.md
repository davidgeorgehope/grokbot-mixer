# Taste profile

Before picking tracks, build a profile of the listener:
1. **Seeds**: tracks and artists they name, liked-song screenshots, playlists. Record the ones that give them chills.
2. **Ratings log**: after every mix, append minute-stamped feedback to a JSONL file (`eval/example_ratings.jsonl` is the example). Use the fields `mix`, `date`, `scope` (whole mix, or a transition with mm:ss), `rating`, `verdict`, `quote` (their exact words), and `notes` / `issues` / `rule`.
3. **Turn complaints into rules and checks**: each "bad" spot becomes a regression fixture (`test_guardrails.py` windows) plus a rule in MIXING_RULES.md.
4. **Pick and order**: favour seed artists and close relatives, use official uploads, order by Camelot and an energy arc (`order.py`), and put the favourite track at the peak near the end with a long build.

## Example profile (the original listener)
- **Genre**: emotional, melodic, soulful **liquid drum & bass**, "all about the feels". Vocal-led, 172–175 BPM.
- **Favourite artist**: Hybrid Minds. The tracks named were *Blame You* ("the one that really gives me tingles"), *Bad To Me*, *Supernova*, *Kismet* and *Solitude*.
- **Also liked**: Etherwood & Grace Barton (*Haven*, *Multicolour*), Leah Guest (*Love & War*, Macca remix), Culture Shock (*U & I*), Kanine, Sub Focus & Wilkinson, High Contrast, goddard., Etherwood, Grafix.
- **Ratings so far**:
  - mix 01: 9/10, "You nailed it". Wanted loops, samples and longer crossfades.
  - mix 02: a "weirdly dropped" section and misaligned beats.
  - mix 02b: the drop into *Put Your Arms Around Me* "just dropped" (meh), which led to the build-into-drop rule.
  - mix 03-60:
    - Deeper → Just Hold On was "horrible".
    - The ~37 min stretch was "weird".
    - The echo-out at 32:40 was "stop-start, not mixing".
- Tracklists of mixes that worked: `dj-mix-01/02/03/03-60-tracklist.md`.

The eval scorer (`src/eval/score_mix.py`) is not yet calibrated to these ratings (eval/README.md). Trust the listener over the score.
