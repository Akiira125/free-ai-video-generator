"""Media providers: local files and openly licensed Wikimedia Commons images."""
import re
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
        info = (page.get("imageinfo") or [{}])[0]
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
    alternatives = {"gray wolf": ["Canis lupus", "grey wolf", "wolf"], "snowy forest": ["winter forest", "snow forest"], "Neuschwanstein Castle": ["Schloss Neuschwanstein"]}
    for term in dict.fromkeys([query, *alternatives.get(query, [])]):
        credit = _search_image(term, destination)
        if credit is not None:
            print(f"  [media] Selected {credit['title']} ({credit['license']})")
            return credit
    raise RuntimeError(f"No suitable openly licensed image found for: {query}")

def select_image(mode, index, query, destination, local_dir):
    images = sorted(p for p in Path(local_dir).iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")) if Path(local_dir).exists() else []
    if mode == "manual" or (mode == "hybrid" and index < len(images)):
        if index >= len(images):
            raise RuntimeError(f"Missing local image for scene {index + 1}")
        with Image.open(images[index]) as img:
            img.convert("RGB").save(destination, "JPEG", quality=95)
        return {"provider": "local", "file": images[index].name}
    if mode in ("internet", "hybrid"):
        return internet_image(query, destination)
    raise ValueError(f"Unsupported media mode: {mode}")
