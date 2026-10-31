- 10-30 23:46 start Mix 06 (weekly). fetching 11 new tracks on the Mac
- 23:49 downloads ok; prep running (prepA/B.log)
00:13 prep done 11 new; keys added; base plan_mix06_base.json; building table
00:21 table built 61 tracks; searching
00:24 fresh-only pool infeasible (111 edges); trying FRESHPEN high without hard exclude
00:32 plan_mix06a.json dry all_ok 23 tracks 60.48 min reuse 4; rendering mix06a
- 10-31 09:40 ET: rebuild Mix 06 with new defaults (STRUCT, FADE=tail, 4-bar swap). table+search -> plan_mix06b.json (search5.log)
- 09:50 ET: search5 failed (crate empty: stems cleaned). Re-running restore_audio+search -> search6.log
- QUEUED after Mix06: Mix 05 v2 = same order as prev05.json, keep 55:10 gold blend (Lilies>Just Hold On) fixed, re-plan others w/ STRUCT+FADE tail; same tests+delivery (replace old Mix05 on Drive), iCloud, YT public; cleanup; report both links
- 10:08 ET: scorer now uses render fader (_xpos); COVPEN=300; plan_mix06b.json found 59.26 min. Rendering mix06b (gain 9.3, nudge05n, AUTO_CLEAN=0) -> render_b.log
- 10:27 ET: render_b failed (X1 incoming 4.5dB/beat, C2 -10.6 dB mid-blend, bass swap 4 bars vs X1 1-2, structure drop 1/21). Fixed: blended tail curve FADE_DB 24, swaps placed by crossfader x, X1 bass 1-4 bars, search requires drop_end/outro, predict runs structure+variety tests. Re-searching -> search8.log
- 10:35 ET: plan_mix06c.json all dry tests ok (58.16 min, 21 tracks). Rendering mix06c -> render_c.log
- 10:48 ET: render_c guardrails failed (X1 3.1 dB/beat on 16-bar, O1 5-7 bars, nT25 E1/N1/F1, R1 YNz30>4WY9). Curve D22 q1.4 p1.7; BOTHMIN=11; exclude nT25guf4DRU; ban YNz30crm5g0>4WY9J_yXj8M. search10.log
- 10:54 ET: plan_mix06d (BOTHMIN=10) dry ok. Rendering mix06d (nohup) -> render_d.log
- 11:04 ET: render_d 11 guardrail fails (O1/F1/E4/L1/R1), pairs banned in mix06/ban06.txt; search11.log
- 11:17 ET: excluding nT25guf4DRU,7Itbo72XEz4 (mix06/excl06.txt), BOTHMIN=8; search12.log
- 11:26 ET: plan_mix06e (DROPPEN=100 BOTHMIN=8 COVPEN=300 beam 900, excl06, ban06) dry ok. Rendering mix06e -> render_e.log
