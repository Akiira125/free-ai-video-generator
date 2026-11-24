"""Review existing cached images without generating new ones."""
import argparse
import base64
import json
import os
from pathlib import Path
import requests
from director import direct, cache_key
from generate_video import parse_script

MODEL = "@cf/meta/llama-3.2-11b-vision-instruct"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accept-license", action="store_true")
    args = ap.parse_args()
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    headers = {"Authorization": "Bearer " + os.environ["CLOUDFLARE_API_TOKEN"]}
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}"
    def call(payload):
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        if not r.ok:
            raise RuntimeError(f"Cloudflare review HTTP {r.status_code}")
        data = r.json()
        if not data.get("success"):
            raise RuntimeError("Cloudflare review failed")
        return data["result"]
    _, scenes = parse_script("scripts/acotar_test_v3.txt")
    scenes = direct(scenes)
    targets = [(i, scenes[i-1], Path(".image_cache") / (cache_key("pollinations-klein", scenes[i-1]["image_prompt"]) + ".jpg")) for i in (5,6,7)]
    if not all(p.exists() for _,_,p in targets):
        raise RuntimeError("Original cached images unavailable; no API calls made")
    if args.accept_license:
        call({"prompt":"agree"})
    checks = {5:"Is the wolf enormous? Is the woman hiding at a distance or standing beside it?",6:"Is this a snowy pine forest? Has the arrow actually left the bow? Is the wolf consistent with giant size?",7:"Is the beast outdoors and the woman indoors, facing each other?"}
    report = []
    for i, scene, path in targets:
        prompt = "Inspect actual visible evidence only. " + checks[i] + " Check visible anatomy and objects. For each question explain briefly, including uncertainty. Return PASS, FAIL or UNCERTAIN overall. Expected scene: " + scene["narration"]
        result = call({"prompt":prompt,"image":"data:image/jpeg;base64,"+base64.b64encode(path.read_bytes()).decode(),"max_tokens":350})
        report.append({"scene":i,"model":MODEL,"review":result})
    Path("vision_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
if __name__ == "__main__":
    main()
