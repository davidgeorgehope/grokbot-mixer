set -x
for b in n1dOiesZS1g yogt46dJJ4g _K2sC9nrf_A T3deOQPJ2H8 2s3M6oX2lfo cb2sbJ-ii-I 6YDKymmWe9o pUUrJH7jzAQ sObzaBqaBRQ q_cZZY0BehE q_IuTV23x7Q KDRPfuZfNYw  kKu3fIOTiHk; do ffmpeg -loglevel error -y -i $b.m4a -ar 44100 -ac 2 wav/$b.wav; B=$(python3 pbpm.py wav/$b.wav 2>/dev/null | awk '{print $2}'); python3 prep.py wav/$b.wav $B 2>&1 | grep -vE "Warn|mel|Using|NOTE"; done
python3 fixgrid.py >/dev/null 2>&1
python3 - <<'PY' 2>&1 | grep -v INFO
import essentia.standard as es,json
exec(open('keys.py').read().split("src=")[0])
K=json.load(open('keys_full.json'))
for b in "n1dOiesZS1g yogt46dJJ4g _K2sC9nrf_A T3deOQPJ2H8 2s3M6oX2lfo cb2sbJ-ii-I 6YDKymmWe9o pUUrJH7jzAQ sObzaBqaBRQ q_cZZY0BehE q_IuTV23x7Q KDRPfuZfNYw  kKu3fIOTiHk".split():
  a=es.MonoLoader(filename=f'st/{b}.wav',sampleRate=44100)()
  K[b]={p:list(map(lambda x:x if not isinstance(x,float) else round(x,2),[CAM[es.KeyExtractor(profileType=p,sampleRate=44100)(a)[:2]]]+[None])) for p in ['edma','bgate','krumhansl','temperley']}
  print('KEY',b,[K[b][p][0] for p in K[b]])
PY
for b in n1dOiesZS1g yogt46dJJ4g _K2sC9nrf_A T3deOQPJ2H8 2s3M6oX2lfo cb2sbJ-ii-I 6YDKymmWe9o pUUrJH7jzAQ sObzaBqaBRQ q_cZZY0BehE q_IuTV23x7Q KDRPfuZfNYw  kKu3fIOTiHk; do python3 -m demucs -n htdemucs -j 8 -o sep st/$b.wav >/dev/null 2>&1; done
python3 barfeats.py > bf3.log 2>&1; echo ALL3DONE
