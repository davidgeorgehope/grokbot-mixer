b=hY2IB2gGC14
B=$(python3 pbpm.py wav/$b.wav 2>/dev/null | awk '{print $2}'); echo BPM $B
python3 prep.py wav/$b.wav $B 2>&1 | grep -vE "Warn|mel|Using|NOTE"
python3 fixgrid.py >/dev/null 2>&1
python3 - <<'PY' 2>&1 | grep -v INFO
import essentia.standard as es
exec(open('keys.py').read().split("src=")[0])
a=es.MonoLoader(filename='st/hY2IB2gGC14.wav',sampleRate=44100)()
print('KEY',[CAM[es.KeyExtractor(profileType=p,sampleRate=44100)(a)[:2]] for p in ['edma','bgate','krumhansl','temperley']])
PY
while ! grep -q ALL4 d4.log; do sleep 10; done
python3 -m demucs -n htdemucs -j 4 -o sep st/$b.wav >/dev/null 2>&1
python3 barfeats.py > bf.log 2>&1; python3 runs.py > runs5.log 2>&1; echo ALL5
