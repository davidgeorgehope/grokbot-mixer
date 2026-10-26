set -e
b=5196v8VY1LI
ssh -o ControlMaster=no "$HOST" "cd /tmp && ~/.ytdlp-nightly/bin/yt-dlp --cookies-from-browser chrome -f 140 -o $b.m4a https://www.youtube.com/watch?v=$b" >/dev/null 2>&1
scp -o ControlMaster=no "$HOST":/tmp/$b.m4a . ; ffmpeg -y -loglevel error -i $b.m4a -ar 44100 wav/$b.wav
B=$(python3 pbpm.py wav/$b.wav 2>/dev/null | awk '{print $2}'); echo BPM $B
python3 prep.py wav/$b.wav $B 2>&1 | grep -vE "Warn|mel|Using|NOTE"
python3 fixgrid.py >/dev/null 2>&1
python3 - <<'PY' 2>&1 | grep -v INFO
import essentia.standard as es
exec(open('keys.py').read().split("src=")[0])
a=es.MonoLoader(filename='st/5196v8VY1LI.wav',sampleRate=44100)()
python3 -m demucs -n htdemucs -j 8 -o sep st/$b.wav >/dev/null 2>&1; python3 barfeats.py > bf8.log 2>&1; python3 runs.py > runs6.log 2>&1; echo ALL6
