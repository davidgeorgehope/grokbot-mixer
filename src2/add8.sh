
for b in N-j7tIeGm1E; do
B=$(python3 pbpm.py wav/$b.wav 2>/dev/null | awk '{print $2}'); echo $b BPM $B
python3 prep.py wav/$b.wav $B 2>&1 | grep -vE "Warn|mel|Using|NOTE"
python3 - $b <<'PY' 2>&1 | grep -v INFO
import sys,essentia.standard as es
exec(open('keys.py').read().split("src=")[0])
a=es.MonoLoader(filename=f'st/{sys.argv[1]}.wav',sampleRate=44100)()
print('KEY',sys.argv[1],[CAM[es.KeyExtractor(profileType=p,sampleRate=44100)(a)[:2]] for p in ['edma','bgate','krumhansl','temperley']])
PY
python3 -m demucs -n htdemucs -j 8 -o sep st/$b.wav >/dev/null 2>&1; echo demucs $b $?
done
python3 fixgrid.py >/dev/null 2>&1; python3 barfeats.py > bf8.log 2>&1; python3 runs.py > runs7.log 2>&1
for b in N-j7tIeGm1E; do python3 phasechk.py $b 2>&1 | tail -3; done; echo ALL7
