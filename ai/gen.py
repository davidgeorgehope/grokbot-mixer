import os,json,time,urllib.request
K=os.environ["FAL_KEY"];H={"Authorization":"Key "+K,"Content-Type":"application/json"}
body={"prompt":"Genre: liquid drum and bass, UKF / Hospital Records style. BPM: 174. Key: F minor. Emotional, euphoric and tearful, like goddard. or Hybrid Minds. Long 32-bar DJ-friendly intro of pads, rolling breakbeats and soft sub bass; lush live strings and piano chords; deep warm reese/sub bassline; crisp two-step DnB drums at 174 BPM throughout. Vocals: soulful female lead, airy and emotive, reverb-drenched, stacked harmonies in the chorus. Big emotional drop after the chorus. Long 32-bar instrumental outro with drums for mixing. No rap, no dubstep, no EDM pop drop.",
"lyrics":"[intro]\n[instrumental]\n[verse]\nI kept the light on in the hall\nIn case you found your way back home\nThe city hums a song we wrote\nI hear it every time I'm alone\n[pre-chorus]\nAnd if the night won't let me go\n[chorus]\nHold me where the rivers run\nUnderneath the morning sun\nEvery tear becomes a glow\nI won't let you go\n[instrumental]\n[verse]\nThe photographs are turning gold\nThe streets remember what we said\nI wear your laughter like a coat\nA warmth that never leaves my head\n[chorus]\nHold me where the rivers run\nUnderneath the morning sun\nEvery tear becomes a glow\nI won't let you go\n[bridge]\nOh, I won't let you go\n[instrumental]\n[outro]\n[instrumental]",
"duration":240,"num_inference_steps":50}
r=json.load(urllib.request.urlopen(urllib.request.Request("https://queue.fal.run/minimax/music-3",json.dumps(body).encode(),H)))
print(r.get("request_id"),flush=True)
while True:
  time.sleep(10)
  s=json.load(urllib.request.urlopen(urllib.request.Request(r["status_url"],headers=H)))
  if s["status"]=="COMPLETED":break
  if s["status"] not in("IN_QUEUE","IN_PROGRESS"):print(s);raise SystemExit
o=json.load(urllib.request.urlopen(urllib.request.Request(r["response_url"],headers=H)))
json.dump(o,open("out.json","w"));print(json.dumps(o)[:500])
urllib.request.urlretrieve(o["audio"]["url"],"ai.wav");print("ok")
