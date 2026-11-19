"""Judge prompts. v1 = first draft; v2 = revised after the dev slice only (see docs/LLM_JUDGE_PILOT_2026-11-18.md)."""
FIG = """You are reviewing diagnostic charts of ONE drum & bass DJ transition (deck A = outgoing track, deck B = incoming track).
Panel titles were removed on purpose. Panels, top to bottom (some charts skip the PRO panel or the last panel):
1. Planned faders: solid blue = A level, solid red = B level, dashed = each deck's lows (<150 Hz) level, orange band = bars where both decks are within 6 dB (the loud overlap).
2. (optional) A reference PRO DJ's fitted deck levels for the same pair. Context only; not our render.
3. Rendered low band per bar: blue = A lows, red = B lows, thick black = summed lows of the mix.
4. Beat offset between the decks per bar in ms (A minus B), only bars where both decks are audible. Green band = +-20 ms (locked). Orange bands = half a beat off.
5. One bar of drum hits per deck, folded over the overlap bars: blue = A kick/snare, red = B kick/snare. Locked decks put kick peaks on the same beat positions.
6. (optional) Spectral penalty lanes, diagnostic only.
"""
DEFECT_V1 = FIG + """
Decide which of these defects are present:
- beat_clash: the two decks' drums are not locked while both are loud (offset several bars away from 0, kicks not lined up).
- bass_hole: the summed low end drops out for a stretch during the blend.
- level_pump: a sudden short dip or jump in level during the blend (the two tracks 'fighting').
- bad_cue: the transition is placed badly (e.g. the incoming track comes in on a weak, bass-less intro while the outgoing is still in full drop, or the outgoing is cut mid-phrase).
Return JSON only: {"beat_clash": {"present": true/false, "confidence": 0-1, "reason": "..."}, "bass_hole": {...}, "level_pump": {...}, "bad_cue": {...}, "none": true/false}"""
DEFECT_V2 = FIG + """
Decide which of these defects are present. Be conservative: most real blends are fine, and a single noisy point is not a defect.
- beat_clash: in panel 4, at least 3 bars (ideally consecutive) sit clearly outside the green band on the SAME side, roughly 40-150 ms, inside the loud overlap, AND/OR panel 5 shows B's kick peaks consistently displaced from A's (about a quarter beat or more). Scattered points that alternate sign are measurement noise, not a clash.
- bass_hole: in panel 3 the thick black summed-lows line falls well below its level just before the blend (roughly 15 dB or more) and stays down for 3 or more bars before the incoming bass arrives. A smooth handoff where black stays near its pre-blend level is fine. Lows falling after the blend ends (outro) do not count.
- level_pump: in panel 3 the black summed line (and usually both colored lines together) shows a sharp 1-2 bar V-shaped notch of ~6 dB or more that recovers immediately, inside the blend.
- bad_cue: in panel 1/3 the incoming deck's lows stay far (20+ dB) below where they settle after the blend for the whole overlap (it came in on a bass-less intro) while the outgoing is still full, or the outgoing's bass is cut long before the incoming has any.
Return JSON only: {"beat_clash": {"present": true/false, "confidence": 0-1, "reason": "cite panel and bars"}, "bass_hole": {...}, "level_pump": {...}, "bad_cue": {...}, "none": true/false}"""
PAIR_V1 = FIG + """
You get TWO renders of transitions, chart A (first image) and chart B (second image). Which blend is LESS defective
(fewer/smaller beat clashes, bass holes, level pumps, bad cue placement)? You must pick one.
Return JSON only: {"winner": "A" or "B", "confidence": 0-1, "reason": "..."}"""
PAIR_V2 = PAIR_V1.replace('You must pick one.', """You must pick one. Check, for each chart: panel 4 (sustained same-side offsets = clash), panel 3 (summed black lows
dropping for several bars = hole, sharp 1-2 bar notch = pump), panel 1 (incoming lows far below body for the whole overlap = bad cue).
Ignore which image comes first; judge only the evidence.""")
DEC_V1 = """The image shows three plans for the same DJ transition between an outgoing and an incoming drum & bass track.
Each plan has two lanes (outgoing on top, incoming below) showing each track's sections by colour (grey intro, light blue build,
red drop, green breakdown, dark grey outro). The black box on each lane is where that track plays during the blend (left edge =
the bar where the blend starts on that track, width = overlap length); the gold tick is the bass swap.
REF is what a professional DJ did. Which candidate, X or Y, is CLOSER to REF in where it leaves the outgoing track, where it
cues the incoming track, how long the overlap is, and when the bass swaps? You must pick one.
Return JSON only: {"closer": "X" or "Y", "confidence": 0-1, "reason": "..."}"""
DEC_V2 = DEC_V1.replace('You must pick one.', """You must pick one. Compare the black boxes' left edges and widths on each lane to REF's, in bars
(read the x axis), and which section each box sits in. Ignore which candidate is listed first.""")
FIG2 = """You are reviewing diagnostic charts of ONE drum & bass DJ transition (deck A = outgoing track, deck B = incoming track).
Panel titles were removed on purpose. Identify panels by what they show, not by their position (some charts have an extra panel):
- FADER panel: solid blue = A level, solid red = B level, dashed = each deck's lows (<150 Hz), orange shading = bars where both decks are within 6 dB (the loud overlap). x = mix bar.
- PRO panel (only on some charts; wiggly fitted curves, legend 'A fitted'/'B fitted'): a reference pro DJ's levels. Context only, never a defect.
- LOW-BAND panel (step lines, legend 'A lows measured', 'B lows measured', thick black 'summed lows'): rendered bass per bar. y in dB.
- OFFSET panel (black dots joined by lines, y in ms, green band +-20 ms, orange bands at +-half a beat): per-bar drum offset A minus B. This measurement is NOISY: isolated points or points that jump between + and - are normal even on perfectly locked blends.
- DRUM-FOLD panel (x = beats in bar 0-4): one bar of kick/snare hits per deck averaged over the overlap. Messy curves are normal.
- SPECTRAL panel (purple/orange 'penalty' lanes): diagnostic only, ignore.
"""
DEFECT_V2 = FIG2 + """
Decide which defects are present. Be conservative: most real blends have NO defect. Only flag what the evidence clearly shows.
- beat_clash: in the OFFSET panel, 3 or more bars in a row sit outside the green band on the SAME side with similar values (within ~30 ms of each other, roughly 40-150 ms) during the orange overlap. Alternating or scattered points are noise -> not a clash.
- bass_hole: in the LOW-BAND panel, the thick black summed-lows line drops 15 dB or more below its level just before the blend and stays down for 3+ bars, then recovers when the incoming bass arrives. Compare the black line's height inside the blend vs the bars just before it; read the y axis.
- level_pump: in the LOW-BAND panel, the black line (with both colored lines together) shows a sharp 1-2 bar notch of ~6 dB or more that recovers immediately, inside the blend.
- bad_cue: in the FADER panel, B's dashed lows stay 20+ dB below their final level for the whole overlap (incoming came in on a bass-less intro) while A is still full.
Before answering, read the black summed-lows values (dB) at: the 2 bars before the blend, the lowest bar inside it, and after.
Return JSON only: {"lows_readout": "pre X dB, min Y dB at bar N, after Z dB", "beat_clash": {"present": true/false, "confidence": 0-1, "reason": "..."}, "bass_hole": {...}, "level_pump": {...}, "bad_cue": {...}, "none": true/false}"""
PAIR_V2 = FIG2 + """
You get TWO renders of transitions, chart A and chart B. Which blend is LESS defective? You must pick one.
For EACH chart first read the LOW-BAND panel's black summed-lows line (pre-blend dB vs lowest dB inside the blend, how many bars down;
a deep multi-bar drop = bass hole, a sharp 1-2 bar notch = pump), then the OFFSET panel (3+ same-side consistent points = clash;
scattered points = noise), then the FADER panel. The chart with the clearer, bigger defect loses. Ignore which chart comes first.
Return JSON only: {"A_readout": "...", "B_readout": "...", "winner": "A" or "B", "confidence": 0-1, "reason": "..."}"""
P = dict(v1=dict(defect=DEFECT_V1, pair=PAIR_V1, dec=DEC_V1), v2=dict(defect=DEFECT_V2, pair=PAIR_V2, dec=DEC_V2))
P['v3'] = P['v2']  # same text; v3 sends each chart panel as its own image (redact.panels)
