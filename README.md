# 🍁 MapleStory Classic World — EXP & Meso Tracker

A lightweight, non-intrusive floating HUD overlay for **MapleStory Classic World** that reads your **Level**, **EXP**, **Map**, **Party Size**, and **Inventory Mesos** directly from the game window using computer vision and pixel-bitmap matching—while saving all your grinding sessions to a clean `exp_log.csv` file.

> **100% Safe & Non-Intrusive**: Only captures screen pixels (like OBS or Windows Snipping Tool). It never reads or modifies game memory, files, or network traffic.

![HUD Preview](docs/hud_preview.png)

---

## 🚀 Quick Start (Zero-Setup Portable Executable)

You do **not** need Python or Tesseract installed to run the portable version:

1. Go to the **[Releases](../../releases/latest)** page and download **`MapleEXPTracker_Portable.zip`**.
2. Right-click **`MapleEXPTracker_Portable.zip`** and click **Extract All...**.
3. Open the extracted `MapleEXPTracker` folder and double-click **`MapleEXPTracker.exe`** while MapleStory Classic World is open.
4. All completed grinding sessions are automatically saved in **`data/exp_log.csv`** (openable in Microsoft Excel or Google Sheets).

---

## ✨ Key Features

![Live Image Sensors (Level Badge, EXP Bar, Minimap)](docs/sensors_preview.png)

- **Direct Image-Based Level & EXP Recognition**:
  - Reads your character level directly from the bottom-left `LV.` badge and your EXP from the bottom `EXP` bar using deterministic 7-row pixel-bitmap templates (`LV_BITMAP_TEMPLATES` & `EXP_BITMAP_TEMPLATES`).
  - Automatically adapts to both **Windowed (`1x` HUD scale, e.g. `1920x1080` / `1980x1200`)** and **Fullscreen / Ultrawide (`2x` integer HUD scale, e.g. `2560x1440` / `3440x1440`)** displays.
- **Official MeowDB EXP Curve & 423-Map Dictionary**:
  - Uses the official MapleStory Classic World EXP table (Levels 1–100) for accurate `EXP/hr`, `%/hr`, and next-level ETA (`Lv 58 in 14 min`).
  - Includes all 423 official MeowDB map names (`core/maps.txt`) with fuzzy Levenshtein snapping, Roman numeral fixing (`"lV" -> "IV"`), and automatic **Town detection** (`Sleepywood`, `Henesys`, `Ellinia`, etc.).
- **Automatic Map-Change Session Splitting**:
  - Moving to a new hunting map after $\ge 60\text{s}$ of farming automatically logs your previous map's session to `data/exp_log.csv` and resets the counter for the new map.
- **Automatic Inventory Meso Box & Party Size Detection**:
  - Automatically locates your Inventory Meso box (with the gold coin on its left) whenever you open your inventory (`I` key), while ignoring Meso changes when a **Shop**, **Storage**, or **Trade** window is open.
  - Counts on-screen Party HP bars every 5 seconds to set `Solo` or `2ppl`–`6ppl` automatically.
- **Idle Auto-Pause & Death EXP-Loss Protection**:
  - Automatically pauses the timer after **15 seconds** of no EXP gain (or while in town) and holds your active `EXP/hr` steady until your next kill.
  - Preserves your accumulated `gained_exp` and `EXP/hr` if you die and lose EXP on the same level.

---

## ⌨️ In-Game Hotkeys

Works while either **MapleStory** or the **Tracker Overlay** is the active window:

| Hotkey | Action |
| :--- | :--- |
| **`Shift + 1`** | Pause / Resume tracking |
| **`Shift + 2`** | Save session to CSV & Reset counters |
| **`Shift + 3`** | Toggle `Don't log` for the current run |
| **`Shift + 4`** | Collapse / Expand the right-hand `EXP log` table |

---

## 🛠️ Running from Source & Building the Executable

### Requirements (Source Mode Only)
- Python 3.10+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed at `C:\Program Files\Tesseract-OCR`

```powershell
pip install -r requirements.txt
python main.py
```

### Run Unit Tests
```powershell
python -m unittest test_tracker.py test_advanced_tracker.py -v
```

### Build Standalone `MapleEXPTracker.exe` & Portable Zip
```powershell
pip install pyinstaller
python build_exe.py
```
This compiles `dist/MapleEXPTracker/MapleEXPTracker.exe`, bundles the pruned 34-binary Tesseract runtime, and creates `dist/MapleEXPTracker_Portable.zip`.

---

## 🙏 Credits & Acknowledgments
- Inspired by [beanguri/Maple-Classic-Exp-Overlay](https://github.com/beanguri/Maple-Classic-Exp-Overlay).
- MapleStory Classic World EXP table and map list sourced from [MeowDB](https://meowdb.com).
