for b in rJuyd8koFAU KdtDm5cBsFo TdPvpzw2KKw l4XZ-wqc4vQ AC3eEHeLd8A N4mzOUMNsuI MoYkYkoeb84 F1NCnCxyhqc uMDP4VTzlBI VdyXzg3nxfU; do ffmpeg -loglevel error -y -i $b.m4a -ar 44100 -ac 2 wav/$b.wav; B=$(python3 pbpm.py wav/$b.wav 2>/dev/null | awk '{print $2}'); python3 prep.py wav/$b.wav $B 2>&1 | grep -vE "Warn|mel|Using|NOTE"; done
python3 - <<'PY' 2>&1 | grep -v INFO
import essentia.standard as es
exec(open('keys.py').read().split("src=")[0])
for b in "rJuyd8koFAU KdtDm5cBsFo TdPvpzw2KKw l4XZ-wqc4vQ AC3eEHeLd8A N4mzOUMNsuI MoYkYkoeb84 F1NCnCxyhqc uMDP4VTzlBI VdyXzg3nxfU".split():
  a=es.MonoLoader(filename=f'st/{b}.wav',sampleRate=44100)()
  print('KEY',b,[CAM[es.KeyExtractor(profileType=p,sampleRate=44100)(a)[:2]] for p in ['edma','bgate','krumhansl','temperley']],flush=True)
PY
for b in rJuyd8koFAU KdtDm5cBsFo TdPvpzw2KKw l4XZ-wqc4vQ AC3eEHeLd8A N4mzOUMNsuI MoYkYkoeb84 F1NCnCxyhqc uMDP4VTzlBI VdyXzg3nxfU; do python3 -m demucs -n htdemucs -j 8 -o sep st/$b.wav >/dev/null 2>&1; echo DM $b; done
python3 fixgrid.py >/dev/null 2>&1; python3 barfeats.py > bf7.log 2>&1; python3 phasechk.py rJuyd8koFAU KdtDm5cBsFo TdPvpzw2KKw l4XZ-wqc4vQ AC3eEHeLd8A N4mzOUMNsuI MoYkYkoeb84 F1NCnCxyhqc uMDP4VTzlBI VdyXzg3nxfU K6dMmz0jLcI; echo ALL4DONE
