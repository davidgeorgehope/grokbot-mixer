"""Calibration control using retained blind A (pro) and original source anchors.
The full rejected pro.wav was cleaned; this does NOT claim to measure its full 64 s.
"""
import json, os
import paths, score, diagnose_gap as D, real_blend as R

if __name__ == '__main__':
    row = next(r for r in json.load(open(os.path.join(paths.RESULTS, 'talkover_rejected.json')))
               if r['id'] == 'hospital_podcast393__04')
    pro = '/workspace/mixes/deliver/protrans/daily_2026-11-08_A.mp3'
    mix = score._load(pro)
    aligned = []
    for deck in ('a', 'b'):
        path = os.path.join(paths.LIB, row[deck]['yt'] + '.m4a')
        loc = row['gate'][deck]['locate']
        y = D.place_source(path, loc['track_t'], loc['mix_t'], len(mix))
        y, _ = D.refine_lag(mix, y)
        aligned.append(y)
    g, _, _, hop = D.band_gains(mix, *aligned)
    sweep = {str(db): R.assess(g['all']['a'], g['all']['b'], hop / D.SR, D.BAR_SEC, level_db=db)
             for db in (-9, -12, -15)}
    result = dict(id=row['id'], pro_excerpt=pro, duration_s=len(mix)/D.SR,
                  full_clip_available=False, alignment='Original version-gate anchors; excerpt begins at original clip time zero.',
                  sweep=sweep,
                  caveat='Only the retained 46.7 s excerpt was measured; the missing full clip remains excluded by talkover and fail-closed missing-input gate.')
    positive = next(r for r in json.load(open(os.path.join(paths.RESULTS, 'admitted.json')))
                    if r['id'] == 'hybrid_minds_ukf__08')
    positive_mix = score._load(positive['pro_clip'])
    positive_sources = []
    for deck in ('a', 'b'):
        path = os.path.join(paths.LIB, positive[deck]['yt'] + '.m4a')
        loc = D.version_match.locate_in(positive_mix, score._load(path))
        y = D.place_source(path, loc['track_t'], loc['mix_t'], len(positive_mix))
        y, _ = D.refine_lag(positive_mix, y)
        positive_sources.append(y)
    pg, _, _, phop = D.band_gains(positive_mix, *positive_sources)
    result['genuine_blend_control'] = dict(id=positive['id'], sweep={
        str(db): R.assess(pg['all']['a'], pg['all']['b'], phop / D.SR, D.BAR_SEC, level_db=db)
        for db in (-9, -12, -15)})
    json.dump(result, open(os.path.join(paths.RESULTS, 'real_blend_calibration.json'), 'w'), indent=2)
    print(json.dumps(result), flush=True)
    assert sweep['-12']['flagged'], 'Known fade-gap-drop excerpt must fail'
    assert not result['genuine_blend_control']['sweep']['-12']['flagged']
