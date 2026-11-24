"""Media providers: local files and openly licensed Wikimedia Commons images."""
import re
import os
import base64
from PIL import ImageDraw
from collections import Counter
from pathlib import Path
from io import BytesIO
import requests
from PIL import Image

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "FreeAIVideoGenerator/2.0 (https://github.com/Akiira125/free-ai-video-generator)"}

def _search_image(query, destination):
    rejected = Counter()
    response = requests.get(API, params={
        "action": "query", "generator": "search", "gsrsearch": query + " filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": 50, "prop": "imageinfo",
        "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 1280,
        "format": "json"
    }, headers=HEADERS, timeout=30)
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {}).values()
    for page in sorted(pages, key=lambda p: p.get("index", 999)):
        if not page.get("imageinfo"):
            rejected["missing imageinfo"] += 1
            continue
        info = page["imageinfo"][0]
        meta = info.get("extmetadata", {})
        license_name = meta.get("LicenseShortName", {}).get("value", "").strip()
        if not (license_name.lower() in ("cc0", "cc0 1.0", "public domain") or re.fullmatch(r"CC BY(?:-SA)? (?:1\.0|2\.0|2\.5|3\.0|4\.0)(?: [A-Za-z]{2})?", license_name)):
            rejected["license: " + license_name] += 1
            continue
        if info.get("width", 0) < 480 or info.get("height", 0) < 270:
            rejected["dimensions"] += 1
            continue
        url = info.get("thumburl") or info.get("url", "")
        if not url.startswith("https://upload.wikimedia.org/"):
            continue
        try:
            with requests.get(url, headers=HEADERS, timeout=40, stream=True) as download:
                download.raise_for_status()
                data = bytearray()
                for chunk in download.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > 20_000_000:
                        raise ValueError("Image too large")
            with Image.open(BytesIO(data)) as img:
                img.convert("RGB").save(destination, "JPEG", quality=90)
            return {"provider": "Wikimedia Commons", "query": query, "title": page.get("title"),
                    "source": info.get("descriptionurl"), "license": license_name,
                    "license_url": meta.get("LicenseUrl", {}).get("value"),
                    "artist": meta.get("Artist", {}).get("value"), "changes": "Resized/cropped for video"}
        except (requests.RequestException, OSError, ValueError) as exc:
            print(f"  [media] Skipping image: {exc}")
    print(f"  [media] Search {query!r}: {len(pages)} results, rejected {dict(rejected)}")
    return None


def internet_image(query, destination):
    alternatives = {"gray wolf": ["Canis lupus", "grey wolf", "wolf"], "snowy forest": ["winter forest", "snow forest"], "Neuschwanstein Castle": ["Schloss Neuschwanstein", "Neuschwanstein", "Bavarian castle", "fairy tale castle"]}
    for term in dict.fromkeys([query, *alternatives.get(query, [])]):
        credit = _search_image(term, destination)
        if credit is not None:
            print(f"  [media] Selected {credit['title']} ({credit['license']})")
            return credit
    raise RuntimeError(f"No suitable openly licensed image found for: {query}")

MODEL = "@cf/black-forest-labs/flux-1-schnell"

def ai_image(prompt, destination):
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account) or not token:
        raise RuntimeError("Cloudflare credentials missing or invalid")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}"
    response = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                             json={"prompt": prompt[:2048], "steps": 4}, timeout=120)
    if not response.ok:
        raise RuntimeError(f"Cloudflare HTTP {response.status_code}")
    if response.headers.get("Content-Type", "").startswith("image/"):
        data = response.content
    else:
        payload = response.json()
        if payload.get("success") is False:
            raise RuntimeError("Cloudflare inference failed")
        data = base64.b64decode(payload["result"]["image"], validate=True)
    with Image.open(BytesIO(data)) as img:
        img.convert("RGB").save(destination, "JPEG", quality=95)
    print("  [media] Cloudflare AI image generated")
    return {"provider": "Cloudflare Workers AI", "model": MODEL, "prompt": prompt}


def pixabay_media(query, destination):
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Pixabay API key missing")
    for kind in ("video", "image"):
        endpoint = "https://pixabay.com/api/videos/" if kind == "video" else "https://pixabay.com/api/"
        params = {"key": key, "q": query[:100], "safesearch": "true", "per_page": 10}
        if kind == "image":
            params.update({"image_type": "photo", "orientation": "horizontal"})
        try:
            response = requests.get(endpoint, params=params, timeout=30)
            if not response.ok:
                print(f"  [media] Pixabay HTTP {response.status_code}")
                continue
            for hit in response.json().get("hits", []):
                if kind == "video":
                    variants = hit.get("videos", {})
                    item = variants.get("medium") or variants.get("small") or {}
                    url = item.get("url", "")
                    if item.get("width", 0) < item.get("height", 0):
                        continue
                else:
                    url = hit.get("largeImageURL", "")
                if not url.startswith("https://"):
                    continue
                try:
                    target = destination.with_name(destination.stem + "_source.mp4") if kind == "video" else destination
                    with requests.get(url, stream=True, timeout=60) as download:
                        if not download.ok:
                            continue
                        with open(target, "wb") as out:
                            size = 0
                            for chunk in download.iter_content(65536):
                                size += len(chunk)
                                if size > 100_000_000:
                                    raise ValueError("Media too large")
                                out.write(chunk)
                    if kind == "image":
                        with Image.open(target) as img:
                            rgb = img.convert("RGB")
                        rgb.save(target, "JPEG", quality=95)
                    print(f"  [media] Pixabay {kind} selected")
                    return {"provider": "Pixabay", "kind": kind, "source": hit.get("pageURL"),
                            "artist": hit.get("user"), "license": "Pixabay Content License",
                            "license_url": "https://pixabay.com/service/license-summary/", "query": query}
                except (requests.RequestException, OSError, ValueError):
                    print("  [media] Pixabay download skipped")
        except (requests.RequestException, ValueError):
            print("  [media] Pixabay request failed")
    raise RuntimeError("No suitable Pixabay media found")


POLLINATIONS_MODELS = {
    "pollinations-schnell": "black-forest-labs/flux.1-schnell",
    "pollinations-zimage": "tongyi-mai/z-image-turbo",
    "pollinations-klein": "black-forest-labs/flux.2-klein-4b",
}

def pollinations_image(mode, prompt, destination):
    from urllib.parse import quote
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Pollinations API key missing")
    model = POLLINATIONS_MODELS[mode]
    url = "https://gen.pollinations.ai/image/" + quote(prompt[:2048], safe="")
    try:
        response = requests.get(url, headers={"Authorization": "Bearer " + key},
                                params={"model": model, "width": 1280, "height": 720},
                                timeout=180, allow_redirects=False)
    except requests.RequestException:
        raise RuntimeError("Pollinations connection failed") from None
    if not response.ok or response.is_redirect:
        raise RuntimeError(f"Pollinations HTTP {response.status_code}")
    with Image.open(BytesIO(response.content)) as img:
        img.convert("RGB").save(destination, "JPEG", quality=95)
    print(f"  [media] Pollinations image generated: {model}")
    return {"provider": "Pollinations", "model": model, "prompt": prompt}


def select_image(mode, index, query, destination, local_dir, prompt=None):
    images = sorted(p for p in Path(local_dir).iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")) if Path(local_dir).exists() else []
    if mode == "manual":
        if index >= len(images):
            raise RuntimeError(f"Missing local image for scene {index + 1}")
        with Image.open(images[index]) as img:
            img.convert("RGB").save(destination, "JPEG", quality=95)
        return {"provider": "local", "file": images[index].name}
    if mode in POLLINATIONS_MODELS:
        return pollinations_image(mode, prompt or query, destination)
    if mode == "pixabay":
        return pixabay_media(query, destination)
    if mode == "ai":
        return ai_image(prompt or query, destination)
    if mode in ("internet", "hybrid"):
        try:
            return internet_image(query, destination)
        except (RuntimeError, requests.RequestException, ValueError) as exc:
            if mode == "internet":
                raise
            print("  [media] Internet failed; trying Cloudflare")
        try:
            return ai_image(prompt or query, destination)
        except (RuntimeError, requests.RequestException, ValueError, KeyError, OSError):
            print("  [media] Cloudflare failed; using labeled placeholder")
            img = Image.new("RGB", (1280, 720), (24, 32, 48))
            ImageDraw.Draw(img).text((40, 340), f"Visual unavailable - scene {index + 1}", fill="white")
            img.save(destination, "JPEG")
            return {"provider": "placeholder", "query": query}
    raise ValueError(f"Unsupported media mode: {mode}")
