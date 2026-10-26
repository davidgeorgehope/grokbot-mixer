for b in rpIpJQ7ujzc; do ffmpeg -loglevel error -y -i $b.m4a -ar 44100 -ac 2 wav/$b.wav; B=$(python3 pbpm.py wav/$b.wav 2>/dev/null | awk '{print $2}'); python3 prep.py wav/$b.wav $B 2>&1 | grep -vE "Warn|mel|Using|NOTE"; done
python3 fixgrid.py >/dev/null 2>&1; python3 barfeats.py 2>&1 | grep -E "rpIp"
python3 - <<'PY' 2>&1 | grep -v INFO
import essentia.standard as es
exec(open('keys.py').read().split("src=")[0])
for b in ['rpIpJQ7ujzc']:
  a=es.MonoLoader(filename=f'st/{b}.wav',sampleRate=44100)()
  print(b,[CAM[es.KeyExtractor(profileType=p,sampleRate=44100)(a)[:2]] for p in ['edma','bgate','krumhansl','temperley']])
PY
echo NEW4DONE
while ! grep -q ALL3 demucs2.log; do sleep 10; done
for b in rpIpJQ7ujzc; do python3 -m demucs -n htdemucs -j 4 -o sep st/$b.wav >/dev/null 2>&1; done; echo ALL4
