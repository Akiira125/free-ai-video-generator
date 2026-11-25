from pathlib import Path
import subprocess
import numpy as np
import soundfile as sf
from kokoro import KPipeline
from PIL import Image
from director import direct, cache_key
from camera_motion import camera_filter
from generate_video import parse_script, prepare_background

OUT = Path("narration_comparison")
OUT.mkdir(exist_ok=True)
WORK = Path("ab_work")
WORK.mkdir(exist_ok=True)
SR = 24000
FPS = 30
TEXT = [
    "Winter was merciless. Deep in the forest, Feyre Archeron searched for anything that might keep her family alive. Then, among the silent trees, she spotted an enormous gray wolf.",
    "Feyre raised her bow. The creature was unlike anything she had encountered before. She released the arrow, unaware that her decision would carry a terrible price.",
    "When a mysterious beast arrived at her family's cottage, the truth began to emerge. Beyond the ancient wall lay a kingdom of immortal Fae, and Feyre's life would never be the same."
]
def run(*args):
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",*map(str,args)],check=True)

_, scenes = parse_script("scripts/acotar_test_v3.txt")
scenes = direct(scenes)
images = []
for i in (4,5,6):
    p = Path(".image_cache") / (cache_key("pollinations-klein",scenes[i]["image_prompt"])+".jpg")
    if not p.exists():
        raise RuntimeError("Missing cached Klein V3 scene "+str(i+1)+"; no image generation attempted")
    dest = WORK / f"image{i}.jpg"
    prepare_background(p,1920,1080).save(dest,quality=95)
    images.append(dest)

pipe = KPipeline(lang_code="a",repo_id="hexgrad/Kokoro-82M")
audio = {}
for voice in ("af_heart","am_michael"):
    for i, paragraph in enumerate(TEXT):
        chunks = [np.asarray(a) for _,_,a in pipe(paragraph,voice=voice,speed=0.95)]
        if not chunks:
            raise RuntimeError("Empty voice output")
        audio[voice,i] = np.concatenate(chunks)
# Common scene lengths keep every visual cut identical across variants.
frames = [max(600, int(np.ceil((max(len(audio[v,i]) for v in ("af_heart","am_michael"))/SR+0.5)*FPS))) for i in range(3)]
for i,p in enumerate(images):
    n=frames[i]
    run("-i",p,"-vf",camera_filter(i,n)+",fade=t=in:st=0:d=0.25,fade=t=out:st="+str(n/FPS-0.25)+":d=0.25","-frames:v",n,"-an","-c:v","libx264","-pix_fmt","yuv420p",WORK/f"shot{i}.mp4")
(WORK/"list.txt").write_text("\n".join(f"file 'shot{i}.mp4'" for i in range(3)))
run("-f","concat","-safe",0,"-i",WORK/"list.txt","-c","copy",WORK/"visual.mp4")
# Original quiet synthesized ambient bed, identical in all versions.
total = sum(frames)*SR//FPS
t = np.arange(total)/SR
bed = sum(np.sin(2*np.pi*f*t + 0.12*np.sin(2*np.pi*0.13*t)) for f in (110,164.81,220,261.63))/4
bed *= 0.035*(0.7+0.3*np.sin(2*np.pi*0.08*t))
bed *= np.minimum(1,np.minimum(t,(total/SR-t))/2)
sf.write(WORK/"bed.wav",bed,SR)
for label, voices in {"A":["af_heart"]*3,"B":["am_michael"]*3,"C":["af_heart","af_heart","am_michael"]}.items():
    parts=[]
    for i,v in enumerate(voices):
        a=audio[v,i]
        length=frames[i]*SR//FPS
        parts.append(np.pad(a,(0,length-len(a))))
    sf.write(WORK/"speech.wav",np.concatenate(parts),SR)
    run("-i",WORK/"speech.wav","-af","highpass=f=70,acompressor=threshold=0.125:ratio=2:attack=20:release=150,loudnorm=I=-19:TP=-2:LRA=11","-ar",SR,WORK/"normalized.wav")
    run("-i",WORK/"visual.mp4","-i",WORK/"normalized.wav","-i",WORK/"bed.wav","-filter_complex","[1:a][2:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]","-map","0:v","-map","[a]","-c:v","copy","-c:a","aac","-b:a","192k","-shortest",OUT/f"Version_{label}.mp4")
(OUT/"narration.txt").write_text("\n\n".join(TEXT),encoding="utf-8")
