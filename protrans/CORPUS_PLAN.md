# Pro-transition corpus plan

Selection first, then version checks, then any later scoring or tuning.
Tuning is paused until this list is admitted.

## What a Goldilocks transition is

A pair is only worth scoring if we can actually reproduce it:

1. A real DJ mix (not a megamix, not a pre-edited yearmix).
2. Liquid drum and bass, mixed by a named DJ.
3. An exact, timestamped tracklist from the official upload or another
   listing that agrees with it (YouTube description / official chapters;
   1001Tracklists or a second independent listing when the description
   has titles only).
4. Both studio sources are the same remix or edit the DJ played
   (Label / VIP named), and those uploads are fetchable.
5. Native tempo close to 174 BPM (about 169–179). No large rubber-band
   stretch.
6. An audible blend long enough to be a 16–64 bar handoff (about 22–88 s
   of overlap), which in practice means the outgoing track is listed for
   roughly 90–280 s. Quick festival smash-cuts are out.
7. A version gate against the pro audio: each studio track must locate
   in the pro clip with the same sub-band-power cross-correlation used
   by `src/eval/control_curves.py` (peak z ≥ 6 and cc ≥ 0.28), outgoing
   in the first part of the clip and incoming after the listed handoff.

Chroma-only matching is not enough: two different liquid tracks in a
similar key can look alike. A known mismatch (Cosmic Flowchart +
Radiance against the Cosmic → Don’t You Leave Me clip) scores z = 4.7
and is rejected. The true incoming on that clip scores z = 10.5.

## Admitted (version-gated)

Corpus fetch and gating is done. No scoring or tuning was run in this phase.

**37 admitted transitions across 5 DJs.** Train 27 / test 10.

| Split | DJ | Mix | Candidates gated | Admitted |
|---|---|---|---|---|
| Train | London Elektricity | [Hospital Podcast 393](https://www.youtube.com/watch?v=2wXDFi2eL1U) | 7 remaining Goldilocks + 2 earlier DYLM pairs | 1 |
| Train | Hybrid Minds | [UKF Liquid Drum & Bass Mix](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 26 (r/DnB + DNBHQ times) | 15 |
| Train | Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 17 (official description times) | 11 |
| Test | Wilkinson | [Live from Boomtown 2026](https://www.youtube.com/watch?v=ifOtJV-xZ-U) | 5 Goldilocks neighbours | 2 |
| Test | Netsky | [Hospital Classics livestream](https://www.youtube.com/watch?v=0yIOFIW4Eow) | 18 (watchthedj times, IDs/bootlegs skipped) | 8 |

Netsky yielded 8 held-out pairs, so a fifth-DJ substitute was not needed.

Full mixes were deleted after clips were cut (Hospital Podcast 393, Boomtown, Joe Syntax, Hybrid Minds UKF, Netsky livestream, plus unused Dimension Allstars and Wilkinson Old Guard files). Only admitted clips and their studio sources remain (`clips/` + `lib/`).

### Admitted table

| DJ | Mix | Timestamp | Track A → Track B | Split |
|---|---|---|---|---|
| London Elektricity | [HP393](https://www.youtube.com/watch?v=2wXDFi2eL1U) | 19:51 → 24:28 | [Inja x Whiney — She Just Wanna Dance (Kyrist Remix)](https://www.youtube.com/watch?v=_Ij78U7OAX4) → [Fred V — Cosmic Flowchart](https://www.youtube.com/watch?v=f2MzUhnpvgk) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 0:00 → 2:11 | [SpectraSoul — Away With Me (Calibre Remix)](https://www.youtube.com/watch?v=pzFgQ7iIfXQ) → [EastColors — Keys](https://www.youtube.com/watch?v=qeXTBEtGUtk) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 11:20 → 13:32 | [Mitekiss — Final Hours](https://www.youtube.com/watch?v=suPgRyRLVC4) → [Hybrid Minds — Listen (ft. Tiffani Juno)](https://www.youtube.com/watch?v=J3oTRY7AdE4) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 13:32 → 15:43 | Listen (ft. Tiffani Juno) → [LSB — The Optimist](https://www.youtube.com/watch?v=ksVDZt9_0J4) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 15:43 → 17:33 | The Optimist → [Hybrid Minds — Secret Place (ft. Tiffani Juno)](https://www.youtube.com/watch?v=Vwb-3pAvOVk) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 17:33 → 19:45 | Secret Place → [Sabre — These Simple Things](https://www.youtube.com/watch?v=M4UU1xn_K4s) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 19:45 → 22:20 | These Simple Things → [Hybrid Minds — Pretend (ft. Rocky Nti)](https://www.youtube.com/watch?v=zEvLsOVhg0I) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 22:20 → 25:14 | Pretend → [Logistics — Wanderlust](https://www.youtube.com/watch?v=W77cCOreg_0) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 32:33 → 34:44 | [Urbandawn — Prime Expansion](https://www.youtube.com/watch?v=HP7Q0vDU9vI) → [Hybrid Minds — Demons (ft. Charlotte Haining)](https://www.youtube.com/watch?v=5YG-HKjtiHM) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 34:44 → 36:45 | Demons → [Changing Faces — Emptiness](https://www.youtube.com/watch?v=tDIlCWhrBPU) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 38:46 → 41:19 | [SpectraSoul & Alix Perez — Undone (ft. DRS)](https://www.youtube.com/watch?v=INaNIcQ4S7k) → [Logistics — City Life](https://www.youtube.com/watch?v=HpfQ0bus688) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 42:47 → 44:37 | [Jome — Cinnamon (Hybrid Minds Remix)](https://www.youtube.com/watch?v=9oBXWTlTPMw) → [Logistics — Together](https://www.youtube.com/watch?v=3f-XOhfDhxk) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 46:48 → 49:00 | [Nu:Tone — Balaclava](https://www.youtube.com/watch?v=bnRTUL2jnk0) → [SpectraSoul & Alix Perez — The Need](https://www.youtube.com/watch?v=Op886B0sd4Q) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 55:57 → 57:47 | [1991 — Nine Clouds](https://www.youtube.com/watch?v=BSckjZOceFg) → [Hybrid Minds — Meant To Be (ft. Grimm) (LSB Remix)](https://www.youtube.com/watch?v=AT8lBlfTT2w) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 67:18 → 69:29 | [LSB — I Need Love](https://www.youtube.com/watch?v=pqqjaLUk-MY) → [Hybrid Minds — Inside (ft. Emily Jones)](https://www.youtube.com/watch?v=oySqE3z99AE) | train |
| Hybrid Minds | [UKF Liquid](https://www.youtube.com/watch?v=Ea4ngKLPNMQ) | 76:04 → 77:54 | [Alix Perez — Contradictions](https://www.youtube.com/watch?v=xv0Qw1QZT8I) → [BCee — Lost & Found (Hybrid Minds Remix)](https://www.youtube.com/watch?v=0oxJBc__U0c) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 0:00 → 3:19 | [Fred V & Grafix — Find My Way](https://www.youtube.com/watch?v=R06kP42RFRo) → [Nu:Tone — The Feeling (ft. Ben Westbeech)](https://www.youtube.com/watch?v=dOJp7bsjuyU) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 3:19 → 5:09 | The Feeling → [High Contrast — Fearful Symmetry](https://www.youtube.com/watch?v=zM6au9qc2XQ) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 20:58 → 22:46 | [Nu:Tone — Shine In (ft. Natalie Williams)](https://www.youtube.com/watch?v=NjwN3B617tg) → [Camo & Krooked — Dusk To Dawn](https://www.youtube.com/watch?v=Dy3qi_gCP9k) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 22:46 → 24:39 | Dusk To Dawn → [Danny Byrd — B.R.I.S.T.O.L (ft. MC Risky)](https://www.youtube.com/watch?v=fApyZbwuAjM) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 24:39 → 27:14 | B.R.I.S.T.O.L → [Logistics — We Are One (Nu:Logic Remix)](https://www.youtube.com/watch?v=wUVt_GsvMzw) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 27:14 → 31:16 | We Are One (Nu:Logic Remix) → [Cyantific — Ghetto Blaster](https://www.youtube.com/watch?v=tCyYwek-o28) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 31:16 → 34:57 | Ghetto Blaster → [S.P.Y — Seconds To Midnight](https://www.youtube.com/watch?v=u6cggHmZEAs) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 34:57 → 36:47 | Seconds To Midnight → [London Elektricity — Meteorites (Danny Byrd Remix)](https://www.youtube.com/watch?v=SqzxwPEa-DI) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 36:47 → 40:05 | Meteorites (Danny Byrd Remix) → [Logistics — Closer](https://www.youtube.com/watch?v=q3WVxTT01dY) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 44:08 → 46:43 | [Camo & Krooked — Lost In The Future (ft. Jenna G & Futurebound)](https://www.youtube.com/watch?v=gZhjz2UQJv0) → [Netsky — Lotus Symphony](https://www.youtube.com/watch?v=RTXo4b0RdyQ) | train |
| Joe Syntax | [Hospital Mix](https://www.youtube.com/watch?v=zgKc7vQNrrE) | 46:43 → 50:00 | Lotus Symphony → [Unquote & Molecular Structures — Lubov Moya](https://www.youtube.com/watch?v=2y8JriTNwyM) | train |
| Wilkinson | [Boomtown 2026](https://www.youtube.com/watch?v=ifOtJV-xZ-U) | 19:24 → 22:00 | [Yosemite (Wilkinson Remix)](https://www.youtube.com/watch?v=PjGZX6K5XnE) → [Wilkinson — Used To This (ft. Issey Cross)](https://www.youtube.com/watch?v=kKWX3C_odcc) | test |
| Wilkinson | [Boomtown 2026](https://www.youtube.com/watch?v=ifOtJV-xZ-U) | 64:24 → 66:10 | [Wilkinson — Ultraviolet (ft. Katy Alex)](https://www.youtube.com/watch?v=uP0KAzefX8Y) → [Wilkinson — Afterglow](https://www.youtube.com/watch?v=I9QGpHScGug) | test |
| Netsky | [Hospital Classics livestream](https://www.youtube.com/watch?v=0yIOFIW4Eow) | 13:22 → 15:50 | [Netsky — I See The Future In Your Eyes](https://www.youtube.com/watch?v=0fjPvcfMJWk) → [Camo & Krooked — In The Future](https://www.youtube.com/watch?v=XUX0ebuFh7Y) | test |
| Netsky | [Hospital Classics livestream](https://www.youtube.com/watch?v=0yIOFIW4Eow) | 21:17 → 23:43 | [High Contrast — Twilight's Last Gleaming](https://www.youtube.com/watch?v=CX4UFb_LlU4) → [Netsky — Escape (ft. Darrison)](https://www.youtube.com/watch?v=na79dfVHpp0) | test |
| Netsky | [Hospital Classics livestream](https://www.youtube.com/watch?v=0yIOFIW4Eow) | 29:10 → 31:23 | [Nu:Tone — Missing Link](https://www.youtube.com/watch?v=RMM3y-WGgdA) → [Netsky — Drawing Straws](https://www.youtube.com/watch?v=cqUMWCyiEFE) | test |
| Netsky | [Hospital Classics livestream](https://www.youtube.com/watch?v=0yIOFIW4Eow) | 37:34 → 39:15 | [Netsky — Memory Lane](https://www.youtube.com/watch?v=cG7cRDcPY3k) → [Netsky — The Whistle Song](https://www.youtube.com/watch?v=k-7z5X0ATEc) | test |
| Netsky | [Hospital Classics livestream](https://www.youtube.com/watch?v=0yIOFIW4Eow) | 39:15 → 43:47 | The Whistle Song → [Logistics — Together](https://www.youtube.com/watch?v=3f-XOhfDhxk) | test |
| Netsky | [Hospital Classics livestream](https://www.youtube.com/watch?v=0yIOFIW4Eow) | 43:47 → 45:38 | Together → [London Elektricity — Just One Second (Apex Remix)](https://www.youtube.com/watch?v=Mzgh0cLopck) | test |
| Netsky | [Hospital Classics livestream](https://www.youtube.com/watch?v=0yIOFIW4Eow) | 56:22 → 58:21 | [Netsky — Porcelain](https://www.youtube.com/watch?v=gCkKc2LuCuM) → [Nu:Logic — Morning Light](https://www.youtube.com/watch?v=KP8jwoWF44Y) | test |
| Netsky | [Hospital Classics livestream](https://www.youtube.com/watch?v=0yIOFIW4Eow) | 58:21 → 60:03 | Morning Light → [Sigma — Nobody To Love (Future Jungle Mix)](https://www.youtube.com/watch?v=esP9UWQOnxk) | test |

Machine-readable copy: `results/admitted.json`. Gate thresholds unchanged (z ≥ 6, cc ≥ 0.28, native BPM 169–179, outgoing early in the clip / incoming after the listed handoff).

London Elektricity is thin (only one pair passed). Hybrid Minds and Joe Syntax carry the train split. Wilkinson is thin (two pairs); Netsky supplies the rest of the held-out set.

## Other rejects (ruled out on paper)

| Item | Reason |
|---|---|
| Liquicity Yearmix 2022 / 2024 / 2025 | Pre-edited yearmixes, not a DJ reading two records. Very short slots. |
| Hospital Podcast 425 (Grafix), 452 (Whiney) | Official uploads list titles but no timestamps. Auto-ID cue sheets invent extra tracks. |
| Hospital Podcast 478 (Degs) | No timestamps, and a wide style spread. Not a liquid-blend test set. |
| Dimension Allstars / Wilkinson Old Guard | No reliable public tracklist. Files deleted after this phase. |
| BBC R1 / 1Xtra Friction, Netsky Boiler Room | No official timestamped full-set page was verified. |
| ID-SCOUTER timestamps in general | They merge Shazam hits with the description and invent IDs. Hint only. |
| Wilkinson Boomtown middle run (CTRL, Jack, Baddadan, …) | Many slots under 90 s and/or jump-up festival edits. |
| Hybrid Minds UKF pairs with a listed gap under 90 s (25 of 51) | Not enough time for a clean 16–64 bar blend plus solos. |
| Joe Syntax 9:12 → 10:40 and 40:05 → 41:33 | 88 s slots, just under the 90 s floor. |

## Notable rejects from this fetch (gate or source)

| Item | Reason |
|---|---|
| HP393 Cosmic Flowchart → Don’t You Leave Me (Dead Man’s Chest Remix), and the next pair out of that remix | Remix locates, but it is not a near-174 studio cut. No stretch. |
| HP393 opening run (Driving Out, Take It Off, Loa, Resistance) and late run (Call The Future, Shimmering, Skirts) | Weak locate on the known studio IDs (several z ≈ 4.4–5.98), so the listed times or the uploads did not match the mix well enough. |
| Wilkinson Lose Control → Half Light | Weak locate and native BPM not in 169–179 (detector ~86). |
| Wilkinson Here For You → Ultraviolet; Afterglow → Balance | Weak locate on the outgoing studio file. |
| Hybrid Minds Never Change → Nine Clouds | Search first hit the GLXY Remix; that upload located after the blend (wrong edit). |
| Hybrid Minds Skin & Bones (Mitekiss Remix hit) | Extra remix when the listing is the original; locate sat before the blend. |
| Hybrid Minds Ember (HM Remix) → Take Me To Another World | Take Me To Another World studio file was not detected as DnB (~86 BPM slice). |
| LSB — Missing You | No confident studio hit that was not the UKF mix itself. |
| Netsky Love Has Gone → Memory Lane | First hit was the Enei Remix; weak locate (z=5.19). |
| Netsky Girl In The Fire → Seba — Snow | Mashup / unofficial uploads; official-ish retry still weak locate (z=3.67). |
| Control (earlier): Cosmic clip + Radiance as incoming | z=4.69, correctly rejected. |
| Search false positives, un-admitted | First-pass ranking once picked the Hybrid Minds UKF mix as “LSB — Missing You” (a tautology against its own clip), “LSB — The Optimist” as Rotary Motion, “LSB — I Need Love” as Wrong To Love You, “Ghetto Blaster” as the Cyantific Remix, and Girl In The Fire as a Star Wars mashup. Those five were removed, search ranking was tightened (penalize extra remixes, long mixes, missing title words), and the real studio IDs were retried. Optimist, I Need Love, and Hospital Ghetto Blaster then passed. |

## Train / test split (by DJ)

| Split | DJs | Role |
|---|---|---|
| Train | London Elektricity, Hybrid Minds, Joe Syntax | Spoken Hospital podcast, long UKF liquid mix, older Hospital catalogue mix |
| Test | Wilkinson, Netsky | Held-out DJs |

## Ready to tune?

Yes. The admitted set meets the 30+ / 5+ DJ target with a DJ-held-out split (27 train / 10 test). The next step is a baseline score and a single general-rule tune pass, keeping a change only if the held-out DJ mean does not drop. Do not pin per-track exceptions. Say whether a score used Demucs stems or band proxies.
