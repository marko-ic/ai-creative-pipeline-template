"""
generate_ads.py — the image generation step.

Reads `prompts.json` from the folder this script lives in, sends each prompt to
Nano Banana 2 via the WaveSpeed API and downloads the results into per-template
subfolders under `outputs/`.

`BRAND_DIR` resolves from the script's own location, so one copy of this folder
per brand targets its own files without further configuration.

Usage:
    # Put your key in a `.env` file next to this script, or in any parent
    # folder — the script walks up until it finds one.
    #     WAVESPEED_API_KEY=...
    python generate_ads.py                       # all prompts
    python generate_ads.py --templates 1,7,13    # subset
    python generate_ads.py --num-images 1        # 1 variant per prompt (cheap smoke test)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

BRAND_DIR = Path(__file__).resolve().parent
PROMPTS_FILE = BRAND_DIR / "prompts.json"
OUTPUTS_DIR = BRAND_DIR / "outputs"

NUM_IMAGES_PER_PROMPT = 4
DEFAULT_RESOLUTION = "2K"

API_BASE = "https://api.wavespeed.ai/api/v3"
UPLOAD_URL = f"{API_BASE}/media/upload/binary"
T2I_URL = f"{API_BASE}/google/nano-banana-2/text-to-image"
EDIT_URL = f"{API_BASE}/google/nano-banana-2/edit"
POLL_URL_TMPL = f"{API_BASE}/predictions/{{task_id}}/result"

POLL_INTERVAL_SEC = 2
POLL_TIMEOUT_SEC = 300


def _resolve_reference_dir():
    """Prefer `reference-images/`, fall back to `product-images/` for legacy brands."""
    for name in ("reference-images", "product-images"):
        candidate = BRAND_DIR / name
        if candidate.exists():
            return candidate
    return BRAND_DIR / "reference-images"


REFERENCE_IMAGES_DIR = _resolve_reference_dir()


def _load_dotenv():
    """Read `.env` from the brand folder or any parent until found."""
    for candidate in [BRAND_DIR, *BRAND_DIR.parents]:
        env_file = candidate / ".env"
        if not env_file.exists():
            continue
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)
        return env_file
    return None


def _auth_headers(json_body=False):
    headers = {"Authorization": f"Bearer {os.environ['WAVESPEED_API_KEY']}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def load_prompts():
    if not PROMPTS_FILE.exists():
        sys.exit(f"prompts.json not found at {PROMPTS_FILE}. "
                 "Copy prompts.example.json to prompts.json and fill it in.")
    with PROMPTS_FILE.open() as f:
        return json.load(f)


def list_product_images():
    """List reference images for this brand (alias kept for legacy compat)."""
    if not REFERENCE_IMAGES_DIR.exists():
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    return sorted(p for p in REFERENCE_IMAGES_DIR.iterdir() if p.suffix.lower() in exts)


def upload_to_wavespeed(image_path):
    """Upload a local image and return its public download_url."""
    with open(image_path, "rb") as fh:
        r = requests.post(
            UPLOAD_URL,
            headers=_auth_headers(),
            files={"file": (image_path.name, fh)},
            timeout=120,
        )
    r.raise_for_status()
    body = r.json()
    if body.get("code") != 200:
        raise RuntimeError(f"Upload failed for {image_path.name}: {body}")
    return body["data"]["download_url"]


def _poll_task(task_id):
    """Poll the prediction endpoint until completed; return list of output URLs."""
    url = POLL_URL_TMPL.format(task_id=task_id)
    deadline = time.monotonic() + POLL_TIMEOUT_SEC
    while time.monotonic() < deadline:
        r = requests.get(url, headers=_auth_headers(), timeout=30)
        r.raise_for_status()
        data = r.json().get("data", {})
        status = data.get("status")
        if status == "completed":
            return data.get("outputs", [])
        if status == "failed":
            raise RuntimeError(f"Task {task_id} failed: {data.get('error')}")
        time.sleep(POLL_INTERVAL_SEC)
    raise TimeoutError(f"Task {task_id} did not complete within {POLL_TIMEOUT_SEC}s.")


def _submit_and_poll(endpoint, payload):
    r = requests.post(endpoint, headers=_auth_headers(json_body=True),
                      json=payload, timeout=60)
    r.raise_for_status()
    body = r.json()
    task_id = body.get("data", {}).get("id")
    if not task_id:
        raise RuntimeError(f"No task id in response: {body}")
    return _poll_task(task_id)


def call_wavespeed_text_to_image(prompt, aspect_ratio, num_images, resolution):
    """Call the Nano Banana 2 text-to-image endpoint num_images times."""
    urls = []
    for i in range(num_images):
        payload = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution.lower(),
            "output_format": "png",
        }
        outputs = _submit_and_poll(T2I_URL, payload)
        urls.extend(outputs)
        print(f"  variant {i + 1}/{num_images} → {len(outputs)} url(s)")
    return urls


def call_wavespeed_edit(prompt, image_urls, aspect_ratio, num_images, resolution):
    """Call the Nano Banana 2 edit endpoint num_images times with reference images."""
    refs = list(image_urls)[:14]
    urls = []
    for i in range(num_images):
        payload = {
            "prompt": prompt,
            "images": refs,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution.lower(),
            "output_format": "png",
        }
        outputs = _submit_and_poll(EDIT_URL, payload)
        urls.extend(outputs)
        print(f"  variant {i + 1}/{num_images} → {len(outputs)} url(s)")
    return urls


def download(url, dest):
    """Stream a URL to a local file in 8 KB chunks."""
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    fh.write(chunk)



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--templates", help="Comma-separated template numbers, e.g. 1,7,13")
    parser.add_argument("--resolution", default=DEFAULT_RESOLUTION,
                        choices=["0.5K", "1K", "2K", "4K"])
    parser.add_argument("--num-images", type=int, default=NUM_IMAGES_PER_PROMPT)
    args = parser.parse_args()

    env_path = _load_dotenv()
    if env_path:
        print(f"Loaded .env from {env_path}")
    if not os.environ.get("WAVESPEED_API_KEY"):
        sys.exit("WAVESPEED_API_KEY not set (export it or put it in `.env`).")

    data = load_prompts()
    prompts = data["prompts"]

    if args.templates:
        wanted = {int(x) for x in args.templates.split(",")}
        prompts = [p for p in prompts if p["template_number"] in wanted]

    OUTPUTS_DIR.mkdir(exist_ok=True)
    product_image_paths = list_product_images()
    print(f"Found {len(product_image_paths)} reference image(s) in {REFERENCE_IMAGES_DIR.name}/.")

    product_image_urls = []
    if product_image_paths:
        print("Uploading reference images to WaveSpeed storage...")
        product_image_urls = [upload_to_wavespeed(p) for p in product_image_paths]
        for path, url in zip(product_image_paths, product_image_urls):
            print(f"  {path.name} → {url}")

    results = []
    for p in prompts:
        n = p["template_number"]
        name = p["template_name"]
        folder = OUTPUTS_DIR / f"{n:02d}-{name}"
        folder.mkdir(exist_ok=True)
        (folder / "prompt.txt").write_text(p["prompt"])

        print(f"\n[{n:02d}] {name} — {p['aspect_ratio']} — "
              f"refs={p['needs_product_images']}")

        try:
            if p["needs_product_images"] and product_image_urls:
                urls = call_wavespeed_edit(
                    prompt=p["prompt"],
                    image_urls=product_image_urls,
                    aspect_ratio=p["aspect_ratio"],
                    num_images=args.num_images,
                    resolution=args.resolution,
                )
            else:
                urls = call_wavespeed_text_to_image(
                    prompt=p["prompt"],
                    aspect_ratio=p["aspect_ratio"],
                    num_images=args.num_images,
                    resolution=args.resolution,
                )
        except Exception as e:
            print(f"  ERROR — {e}")
            continue

        image_paths = []
        for i, url in enumerate(urls, 1):
            dest = folder / f"{name}_v{i}.png"
            download(url, dest)
            image_paths.append(str(dest.relative_to(OUTPUTS_DIR)))
            print(f"  saved {dest.name}")
        results.append({"template_number": n, "template_name": name,
                        "image_paths": image_paths})

    if not results:
        print("\nNo images generated.")


if __name__ == "__main__":
    main()
