#!/bin/bash
# usage: master.sh in.wav out.mp3 gain_dB [master.wav]
in=$1;out=$2;g=$3;w=${4:-master.wav}
ffmpeg -loglevel error -y -i $in -af "acompressor=threshold=-20dB:ratio=1.8:attack=30:release=250:knee=6:detection=rms,volume=${g}dB,aresample=176400,alimiter=limit=0.78:attack=1:release=60:level=disabled:asc=1,aresample=44100:resampler=soxr:precision=28" -c:a pcm_f32le $w
ffmpeg -loglevel error -y -i $w -c:a libmp3lame -b:a 320k $out
ffmpeg -nostats -i $out -af ebur128=peak=true -f null - 2>&1 | grep -A12 Summary | grep -E "I:|LRA:|Peak:"
