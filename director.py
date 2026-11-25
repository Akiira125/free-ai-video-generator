"""Offline storyboard direction, technical image checks and bounded generation."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageStat

STYLE = "Photorealistic cinematic medieval fantasy film still, natural anatomy, coherent perspective, detailed textures, landscape 16:9, no lettering."
CHARACTERS = {
    "feyre": "Feyre: young adult woman, long chestnut brown hair, gray-blue eyes, oval face, worn brown leather winter coat, wooden bow.",
    "beast": "Tamlin in beast form: massive supernatural quadruped, golden fur, wolf-like muzzle, curved horns, powerful feline body."
}
ENVIRONMENTS = {"winter_forest": "Dense snow-covered pine forest, deep white snow on ground, cold overcast winter daylight, no grassy hills or mountains."}
CREATURES = {"giant_wolf": "Supernatural gray wolf, shoulder height comparable to an adult human, thick gray fur, intimidating wild animal."}

PAINTED_STYLE = "Epic cinematic digital oil painting, visible refined brushwork, atmospheric perspective, richly painted textures, natural human anatomy, expressive faces, sophisticated lighting, illustrated novel aesthetic, not photography, not cartoon, widescreen 16:9, no text."
SPECIES = {"human": "Mortal human, natural rounded human ears, no elven features.", "high_fae": "High Fae, humanoid anatomy, subtly pointed ears, elegant otherworldly features."}

def direct(scenes):
    for scene in scenes:
        p = scene["image_prompt"]
        for tag, description in {**ENVIRONMENTS, **CREATURES}.items():
            marker = "[" + tag + "]"
            if marker in p:
                p = p.replace(marker, description + " ")
        style = PAINTED_STYLE if "[painted]" in p else STYLE
        p = p.replace("[painted]", "")
        for tag, description in SPECIES.items():
            p = p.replace("[" + tag + "]", description)
        names = scene.get("characters", [])
        unknown = set(names) - CHARACTERS.keys()
        if unknown:
            raise ValueError(f"Unknown character: {unknown}")
        scene["image_prompt"] = " ".join([p, *(CHARACTERS[n] + (" " + SPECIES["human"] if n == "feyre" and style == PAINTED_STYLE else "") for n in names), style])
        if len(scene["image_prompt"]) > 2048:
            raise ValueError("Prompt exceeds provider limit")
    return scenes

def check_image(path):
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        if im.width < 640 or im.height < 360:
            raise ValueError("Image resolution too low")
        if ImageStat.Stat(im.convert("L").resize((64,64))).stddev[0] < 5:
            raise ValueError("Image appears blank")
        return {"width": im.width, "height": im.height, "semantic_review": "not performed"}

def cache_key(mode, prompt):
    return hashlib.sha256(json.dumps([mode,prompt], ensure_ascii=False).encode()).hexdigest()

def budget_check(mode, count, limit):
    rates = {"pollinations-klein":5,"pollinations-zimage":4,"pollinations-schnell":2}
    if mode in rates and count * rates[mode] > limit:
        raise ValueError(f"Estimated cost {count*rates[mode]} milli-USD exceeds limit {limit}")
