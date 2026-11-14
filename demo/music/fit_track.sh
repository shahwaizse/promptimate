#!/bin/sh
# fit_track.sh <in.wav> <seconds> <out.mp3>: crossfade-loop to length, 1.5 s fade-out, normalise to -14 LUFS.
FF=/d/tools/ffmpeg/bin/ffmpeg
IN="$1"; DUR="$2"; OUT="$3"
mkdir -p "$(dirname "$OUT")"
$FF -y -loglevel error -i "$IN" -i "$IN" -i "$IN" -filter_complex "[0][1]acrossfade=d=2:c1=tri:c2=tri[a];[a][2]acrossfade=d=2:c1=tri:c2=tri,atrim=0:$DUR,afade=t=in:d=0.05,afade=t=out:st=$(awk "BEGIN{print $DUR-1.5}"):d=1.5,loudnorm=I=-14:TP=-1.5:LRA=11" -ar 48000 -b:a 192k "$OUT"
