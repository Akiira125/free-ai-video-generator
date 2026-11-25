import asyncio
import subprocess
from pathlib import Path
import edge_tts
import soundfile as sf
import numpy as np
from kokoro import KPipeline

TEXT = """Winter was merciless. Food was running out, and for Feyre Archeron, survival meant venturing deeper into the forest.

But on that particular day, something was different. Among the silent trees stood a creature that should never have been there. An enormous gray wolf.

Feyre raised her bow. She hesitated for a moment, then released the arrow.

What she didn't know was that this single decision would change her life forever."""

out = Path("voice_preview")
out.mkdir(exist_ok=True)
def normalize(source, name):
    subprocess.run(["ffmpeg","-y","-i",str(source),"-af","loudnorm=I=-19:TP=-1.5:LRA=11","-c:a","libmp3lame","-b:a","192k",str(out / (name+".mp3"))],check=True)

asyncio.run(edge_tts.Communicate(TEXT,"en-US-AriaNeural").save("edge_raw.mp3"))
normalize("edge_raw.mp3","01_edge_aria")
pipelines = {}
for name, voice, lang in [("02_kokoro_heart","af_heart","a"),("03_kokoro_nicole","af_nicole","a"),("04_kokoro_michael","am_michael","a"),("05_kokoro_george","bm_george","b")]:
    if lang not in pipelines:
        pipelines[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    chunks = [np.asarray(audio) for _,_,audio in pipelines[lang](TEXT,voice=voice,speed=1.0,split_pattern=r"\n+")]
    if not chunks:
        raise RuntimeError("No audio for "+voice)
    sf.write("kokoro_raw.wav",np.concatenate(chunks),24000)
    normalize("kokoro_raw.wav",name)
(out/"narration.txt").write_text(TEXT,encoding="utf-8")
