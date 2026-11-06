"""Downloads the MediaPipe web library + models used by browser camera mode.

They are served from /static/vendor/mediapipe so the page works without
reaching a CDN (and offline after the first run). If the download fails, the
page falls back to loading them from the public CDN.
"""
import io
import os
import tarfile
import urllib.request

from config import BASE_DIR

TASKS_VISION_VERSION = "0.10.14"
VENDOR_DIR = os.path.join(BASE_DIR, "static", "vendor", "mediapipe")
PACKAGE_URL = (f"https://registry.npmjs.org/@mediapipe/tasks-vision/-/"
               f"tasks-vision-{TASKS_VISION_VERSION}.tgz")
MODELS = {
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                            "hand_landmarker/float16/1/hand_landmarker.task",
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
                            "face_landmarker/float16/1/face_landmarker.task",
}
PACKAGE_FILES = ["vision_bundle.mjs", "wasm/vision_wasm_internal.js", "wasm/vision_wasm_internal.wasm",
                 "wasm/vision_wasm_nosimd_internal.js", "wasm/vision_wasm_nosimd_internal.wasm"]


def assets_present(vendor_dir: str = VENDOR_DIR) -> bool:
    needed = PACKAGE_FILES + list(MODELS)
    return all(os.path.exists(os.path.join(vendor_dir, f)) for f in needed)


def _download(url: str, timeout: float = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def ensure_vision_assets(vendor_dir: str = VENDOR_DIR) -> bool:
    """Download anything missing. Returns True when everything is available locally."""
    if assets_present(vendor_dir):
        return True
    os.makedirs(os.path.join(vendor_dir, "wasm"), exist_ok=True)
    try:
        if not all(os.path.exists(os.path.join(vendor_dir, f)) for f in PACKAGE_FILES):
            print("[assets] Downloading MediaPipe web library (~19 MB, first run only)...")
            with tarfile.open(fileobj=io.BytesIO(_download(PACKAGE_URL)), mode="r:gz") as tar:
                for name in PACKAGE_FILES:
                    member = tar.getmember(f"package/{name}")
                    data = tar.extractfile(member).read()
                    with open(os.path.join(vendor_dir, name), "wb") as f:
                        f.write(data)
        for name, url in MODELS.items():
            path = os.path.join(vendor_dir, name)
            if not os.path.exists(path):
                print(f"[assets] Downloading {name}...")
                data = _download(url)
                with open(path + ".tmp", "wb") as f:
                    f.write(data)
                os.replace(path + ".tmp", path)
    except Exception as exc:  # offline / blocked: the page will use the CDN instead
        print(f"[assets] Could not download MediaPipe assets ({exc}); the browser will use the CDN.")
        return False
    return True
