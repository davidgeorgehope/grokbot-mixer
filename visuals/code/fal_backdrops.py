import os,json,sys,urllib.request
KEY=os.environ['FAL_KEY']
P=["abstract liquid light, soft rose gold and peach silk fluid swirling in dark space, bokeh, dreamy, no text",
"abstract sunrise glow through ocean water, warm amber and coral light rays, underwater caustics, no text",
"abstract ink in water, deep teal and soft gold flowing smoke, elegant, cinematic, no text",
"abstract luminous nebula, electric violet and magenta volumetric light beams, dark background, no text",
"abstract aurora ribbons, emerald and cyan flowing light over dark water reflections, no text",
"abstract rain on glass at night, deep blue and silver lilies of light, soft focus bokeh, melancholic, no text",
"abstract molten crimson and deep purple liquid chrome waves, dramatic rim light, no text"]
os.makedirs('../tex',exist_ok=True)
for i,p in enumerate(P):
    fn=f'../tex/track{i+1}.jpg'
    if os.path.exists(fn): continue
    req=urllib.request.Request('https://fal.run/fal-ai/flux/schnell',data=json.dumps({"prompt":p,"image_size":"landscape_16_9","num_inference_steps":4,"num_images":1}).encode(),headers={'Authorization':'Key '+KEY,'Content-Type':'application/json'})
    r=json.load(urllib.request.urlopen(req,timeout=120)); img=r['images'][0]
    urllib.request.urlretrieve(img['url'],fn); print(i+1,img.get('width'),img.get('height'))
