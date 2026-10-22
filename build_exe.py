import os
import sys
import glob
import json
import csv
import shutil
import zipfile
import pefile
import PyInstaller.__main__


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
APP_NAME = "MapleEXPTracker"
APP_DIST_DIR = os.path.join(DIST_DIR, APP_NAME)
ZIP_PATH = os.path.join(DIST_DIR, f"{APP_NAME}_Portable.zip")

TESSERACT_SRC_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
    r"C:\Users\lucas\AppData\Local\Programs\Tesseract-OCR",
]

# Unused large library parts (OpenCV's FFmpeg video player and Pillow AVIF codec)
UNUSED_PATTERNS = [
    "_internal/cv2/opencv_videoio_ffmpeg*.dll",
    "_internal/PIL/_avif*.pyd",
]


def find_tesseract_dir() -> str:
    for path in TESSERACT_SRC_CANDIDATES:
        if os.path.exists(os.path.join(path, "tesseract.exe")):
            return path
    raise FileNotFoundError("Could not find local Tesseract-OCR installation to bundle.")


def get_required_tesseract_files(tess_dir: str) -> set:
    """
    Uses PE import table analysis to find the exact set of DLLs actually loaded by tesseract.exe,
    excluding the ~47 MB of unused training-only DLLs (libicudt78.dll, libcairo, libpango, etc.).
    """
    needed = set()
    queue = ["tesseract.exe"]
    while queue:
        fn = queue.pop(0)
        p = os.path.join(tess_dir, fn)
        if not os.path.exists(p) or fn.lower() in needed:
            continue
        needed.add(fn.lower())
        try:
            pe = pefile.PE(p, fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
            if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
                for entry in pe.DIRECTORY_ENTRY_IMPORT:
                    dll = entry.dll.decode("utf-8", "ignore")
                    if os.path.exists(os.path.join(tess_dir, dll)):
                        queue.append(dll)
            pe.close()
        except Exception:
            pass
    return needed


def bundle_tesseract(target_internal_dir: str):
    src_dir = find_tesseract_dir()
    dest_dir = os.path.join(target_internal_dir, "Tesseract-OCR")
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    dest_tessdata = os.path.join(dest_dir, "tessdata")
    os.makedirs(dest_tessdata, exist_ok=True)

    required_files = get_required_tesseract_files(src_dir)
    copied_count = 0
    for f in os.listdir(src_dir):
        if f.lower() in required_files:
            shutil.copy2(os.path.join(src_dir, f), os.path.join(dest_dir, f))
            copied_count += 1

    # Copy only eng.traineddata (osd.traineddata is 10 MB and unused for line OCR)
    src_eng = os.path.join(src_dir, "tessdata", "eng.traineddata")
    if os.path.exists(src_eng):
        shutil.copy2(src_eng, os.path.join(dest_tessdata, "eng.traineddata"))

    print(f"[Build] Bundled minimal Tesseract-OCR ({copied_count} runtime binaries + eng.traineddata) into: {dest_dir}")


def prune_unused_binaries(app_dist_dir: str):
    removed_mb = 0.0
    for pat in UNUSED_PATTERNS:
        for fpath in glob.glob(os.path.join(app_dist_dir, pat)):
            try:
                sz = os.path.getsize(fpath) / (1024 * 1024)
                os.remove(fpath)
                removed_mb += sz
                print(f"[Build] Pruned unused binary: {os.path.relpath(fpath, app_dist_dir)} ({sz:.1f} MB)")
            except Exception:
                pass
    if removed_mb > 0:
        print(f"[Build] Total pruned unused OpenCV/Pillow binaries: {removed_mb:.1f} MB")


def create_clean_data_folder(app_dist_dir: str):
    data_dir = os.path.join(app_dist_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    # 1. Clean exp_log.csv with headers
    csv_path = os.path.join(data_dir, "exp_log.csv")
    fieldnames = [
        "id", "date", "map", "lv", "party", "time",
        "exp_hr", "mesos_hr", "gained_exp", "gained_mesos", "timestamp"
    ]
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

    # 2. Clean exp_log.json
    json_path = os.path.join(data_dir, "exp_log.json")
    with open(json_path, mode="w", encoding="utf-8") as f:
        json.dump([], f, indent=2)

    # 3. Clean config.json
    cfg_path = os.path.join(data_dir, "config.json")
    with open(cfg_path, mode="w", encoding="utf-8") as f:
        json.dump({
            "exp_offset_x": 35,
            "exp_offset_from_bottom": 38,
            "meso_rel": None,
            "map_rel_x": 42,
            "map_rel_y": 20,
            "map_width": 225,
            "map_height": 50
        }, f, indent=2)

    # 4. Quick-start README for friend
    readme_path = os.path.join(app_dist_dir, "README_HOW_TO_USE.txt")
    with open(readme_path, mode="w", encoding="utf-8") as f:
        f.write(
            "MapleStory Classic World - Portable EXP & Meso Tracker\n"
            "======================================================\n\n"
            "How to Run:\n"
            "1. Unzip this entire folder anywhere on your PC.\n"
            "2. Double-click 'MapleEXPTracker.exe' while MapleStory Classic World is open.\n"
            "3. All your saved grinding sessions are stored in 'data/exp_log.csv' (you can open it in Excel or Google Sheets anytime!).\n\n"
            "Features:\n"
            "- Automatically reads your Level, EXP, Map, Party Size (Solo / 2-6ppl), and Inventory Mesos directly from the game window.\n"
            "- Supports both 1080p/1200p Windowed (1x scale) and 1440p/Ultrawide Fullscreen (2x scale).\n"
            "- Auto-pauses after 15 seconds of no EXP gain (or in Towns) so town/restock trips don't lower your EXP/hr.\n"
            "- Automatically logs your session and starts fresh when you move to a new hunting map.\n"
            "- Protects your EXP/hr rate if you die and lose EXP.\n\n"
            "In-Game Hotkeys (while MapleStory or the Tracker is focused):\n"
            "- Shift+1 : Pause / Resume\n"
            "- Shift+2 : Save & Reset Session\n"
            "- Shift+3 : Toggle 'Don't log'\n"
            "- Shift+4 : Toggle Compact / Full Log View\n"
        )

    print(f"[Build] Initialized clean data folder: {data_dir}")


def create_portable_zip(src_folder: str, zip_path: str):
    if os.path.exists(zip_path):
        os.remove(zip_path)

    parent_dir = os.path.dirname(src_folder)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, _, files in os.walk(src_folder):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, parent_dir)
                zf.write(abs_path, rel_path)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[Build] Created shareable archive: {zip_path} ({size_mb:.1f} MB)")


def build():
    print("[Build] Running PyInstaller...")
    maps_src = os.path.join(PROJECT_ROOT, "core", "maps.txt")
    PyInstaller.__main__.run([
        os.path.join(PROJECT_ROOT, "main.py"),
        f"--name={APP_NAME}",
        "--onedir",
        "--noconsole",
        "--noconfirm",
        "--clean",
        "--collect-all=customtkinter",
        f"--add-data={maps_src};core",
    ])

    internal_dir = os.path.join(APP_DIST_DIR, "_internal")
    if not os.path.isdir(internal_dir):
        internal_dir = APP_DIST_DIR

    prune_unused_binaries(APP_DIST_DIR)
    bundle_tesseract(internal_dir)
    create_clean_data_folder(APP_DIST_DIR)
    create_portable_zip(APP_DIST_DIR, ZIP_PATH)
    print("\n[Build] SUCCESS!")
    print(f"  Executable : {os.path.join(APP_DIST_DIR, APP_NAME + '.exe')}")
    print(f"  CSV Log    : {os.path.join(APP_DIST_DIR, 'data', 'exp_log.csv')}")
    print(f"  Share Zip  : {ZIP_PATH}")


if __name__ == "__main__":
    build()
