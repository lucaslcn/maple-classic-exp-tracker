import os
import json
import mss
import numpy as np
import cv2
from typing import Optional, Tuple, Dict, Any
from core.window_manager import WindowManager
from core.paths import get_data_path


class ScreenGrabber:
    """
    Grabs multiple dynamic regions relative to the MapleStory game window:
    - Level badge (bottom status bar left of job/name)
    - EXP bar (bottom status bar right of center)
    - Minimap banner (top-left white map title text)
    - Meso box (inventory window, user-calibrated)
    """

    def __init__(self, window_manager: Optional[WindowManager] = None, config_path: Optional[str] = None):
        self.wm = window_manager or WindowManager()
        self.sct = mss.mss()
        self.config_path = config_path or get_data_path("config.json")

        # Level badge default relative offsets (from bottom-center cx = width // 2)
        self.lv_offset_x = -358
        self.lv_offset_from_bottom = 32
        self.lv_width = 38
        self.lv_height = 20

        # EXP bar default relative offsets (centered bottom bar for 1980x1200 / 1920x1080)
        self.rel_offset_x = 35
        self.rel_offset_from_bottom = 38
        self.exp_width = 190
        self.exp_height = 26

        # Minimap title banner relative offsets (top-left white text next to map icon)
        self.map_rel_x = 42
        self.map_rel_y = 20
        self.map_width = 225
        self.map_height = 50

        # Meso box relative offset
        self.meso_rel: Optional[Dict[str, int]] = None
        self._load_config()

    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.rel_offset_x = cfg.get("exp_offset_x", self.rel_offset_x)
                    self.rel_offset_from_bottom = cfg.get("exp_offset_from_bottom", self.rel_offset_from_bottom)
                    meso_candidate = cfg.get("meso_rel", None)
                    if self._is_valid_meso_box(meso_candidate):
                        self.meso_rel = meso_candidate
                    else:
                        self.meso_rel = None
                    if "map_rel_x" in cfg:
                        self.map_rel_x = cfg["map_rel_x"]
                        self.map_rel_y = cfg["map_rel_y"]
                        self.map_width = cfg["map_width"]
                        self.map_height = cfg["map_height"]
            except Exception:
                pass

    @staticmethod
    def _is_valid_meso_box(box: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(box, dict):
            return False
        w = box.get("width", 0)
        h = box.get("height", 0)
        return 20 <= w <= 500 and 10 <= h <= 200

    @staticmethod
    def _get_scale_and_viewport_left(width: int, height: int) -> Tuple[int, int]:
        """
        Determines MapleStory Classic World's integer UI scale (1x vs 2x)
        and horizontal pillarbox offset (for ultrawide displays like 3440x1440).
        """
        ui_scale = 2 if height >= 1300 else 1
        aspect = width / max(1, height)
        if aspect > (16.0 / 9.0) + 0.05:
            active_w = int(round(height * 16.0 / 9.0))
            viewport_left = max(0, (width - active_w) // 2)
        else:
            viewport_left = 0
        return ui_scale, viewport_left

    def _save_config(self):
        os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({
                    "exp_offset_x": self.rel_offset_x,
                    "exp_offset_from_bottom": self.rel_offset_from_bottom,
                    "meso_rel": self.meso_rel,
                    "map_rel_x": self.map_rel_x,
                    "map_rel_y": self.map_rel_y,
                    "map_width": self.map_width,
                    "map_height": self.map_height
                }, f, indent=2)
        except Exception:
            pass

    def set_meso_box(self, screen_x: int, screen_y: int, width: int, height: int):
        """Calibrates Meso box relative to the game window."""
        geom = self.wm.get_window_geometry()
        if not geom:
            candidate = {"rel_x": screen_x, "rel_y": screen_y, "width": width, "height": height, "is_abs": True}
        else:
            candidate = {
                "rel_x": screen_x - geom["left"],
                "rel_y": screen_y - geom["top"],
                "width": width,
                "height": height,
                "is_abs": False
            }
        if self._is_valid_meso_box(candidate):
            self.meso_rel = candidate
            self._save_config()

    def get_level_bbox(self) -> Optional[Dict[str, int]]:
        """Compute absolute desktop bounding box for the bottom-bar LV. badge."""
        geom = self.wm.get_window_geometry()
        if not geom:
            return None

        s, _ = self._get_scale_and_viewport_left(geom["width"], geom["height"])
        cx = geom["width"] // 2
        return {
            "top": int(geom["top"] + geom["height"] - self.lv_offset_from_bottom * s),
            "left": int(geom["left"] + cx + self.lv_offset_x * s),
            "width": int(self.lv_width * s),
            "height": int(self.lv_height * s)
        }

    def get_level_frame(self) -> Optional[np.ndarray]:
        """Grabs the current LV. badge frame from the bottom status bar."""
        bbox = self.get_level_bbox()
        if not bbox:
            return None

        try:
            shot = self.sct.grab(bbox)
            img = np.array(shot)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception:
            return None

    def get_exp_bbox(self) -> Optional[Dict[str, int]]:
        """Compute absolute desktop bounding box for the EXP bar."""
        geom = self.wm.get_window_geometry()
        if not geom:
            return None

        s, _ = self._get_scale_and_viewport_left(geom["width"], geom["height"])
        cx = geom["width"] // 2
        return {
            "top": int(geom["top"] + geom["height"] - self.rel_offset_from_bottom * s),
            "left": int(geom["left"] + cx + self.rel_offset_x * s),
            "width": int(self.exp_width * s),
            "height": int(self.exp_height * s)
        }

    def get_exp_frame(self) -> Tuple[Optional[np.ndarray], Optional[Dict[str, Any]]]:
        """Grabs the current EXP bar frame."""
        bbox = self.get_exp_bbox()
        if not bbox:
            return None, None

        geom = self.wm.get_window_geometry()
        try:
            shot = self.sct.grab(bbox)
            img = np.array(shot)
            bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            return bgr, {
                "bbox": bbox,
                "window_title": geom["title"] if geom else "MapleStory",
                "window_size": (geom["width"], geom["height"]) if geom else (),
                "window_pos": (geom["left"], geom["top"]) if geom else ()
            }
        except Exception:
            return None, None

    def get_map_frame(self, exclude_rect: Optional[Tuple[int, int, int, int]] = None) -> Optional[np.ndarray]:
        """
        Grabs the minimap title banner frame.
        If exclude_rect (x, y, w, h) overlaps the minimap box (e.g. HUD dragged over minimap),
        returns None to avoid reading the HUD's own text.
        """
        geom = self.wm.get_window_geometry()
        if not geom:
            return None

        s, viewport_left = self._get_scale_and_viewport_left(geom["width"], geom["height"])
        bbox = {
            "top": int(geom["top"] + self.map_rel_y * s),
            "left": int(geom["left"] + viewport_left + self.map_rel_x * s),
            "width": int(self.map_width * s),
            "height": int(self.map_height * s)
        }

        if exclude_rect:
            ex_x, ex_y, ex_w, ex_h = exclude_rect
            # Check rectangle intersection
            if not (ex_x + ex_w < bbox["left"] or
                    ex_x > bbox["left"] + bbox["width"] or
                    ex_y + ex_h < bbox["top"] or
                    ex_y > bbox["top"] + bbox["height"]):
                return None

        try:
            shot = self.sct.grab(bbox)
            img = np.array(shot)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception:
            return None

    def get_mesos_frame(self) -> Optional[np.ndarray]:
        """Grabs the inventory Meso box if manually calibrated."""
        if not self.meso_rel:
            return None

        geom = self.wm.get_window_geometry()
        if not geom and not self.meso_rel.get("is_abs"):
            return None

        if self.meso_rel.get("is_abs"):
            top = self.meso_rel["rel_y"]
            left = self.meso_rel["rel_x"]
        else:
            top = geom["top"] + self.meso_rel["rel_y"]
            left = geom["left"] + self.meso_rel["rel_x"]

        bbox = {
            "top": int(top),
            "left": int(left),
            "width": int(self.meso_rel["width"]),
            "height": int(self.meso_rel["height"])
        }

        try:
            shot = self.sct.grab(bbox)
            img = np.array(shot)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception:
            return None

    @staticmethod
    def find_money_window_in_frame(bgr: np.ndarray) -> Optional[str]:
        """
        Detects if a 'shop', 'storage', or 'trade' window is open by matching its button column.
        When one of these windows is open, Meso changes are from spending/storing/trading, not farming.
        """
        if bgr is None or bgr.size == 0:
            return None
        scale = min(1.0, 1600.0 / bgr.shape[1])
        small = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1.0 else bgr
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        kernel = np.ones((3, 3), np.uint8)
        colours = {
            "orange": ((6, 150, 170), (16, 255, 255)),
            "green": ((28, 60, 140), (50, 255, 255)),
            "blue": ((92, 100, 140), (110, 255, 255)),
        }
        buttons = {}
        for name, (lo, hi) in colours.items():
            mask = cv2.morphologyEx(cv2.inRange(hsv, np.array(lo), np.array(hi)), cv2.MORPH_CLOSE, kernel)
            n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
            buttons[name] = [
                tuple(map(int, s[:4]))
                for s in stats[1:n]
                if s[3] >= 8 and 2.5 * s[3] <= s[2] <= 7.0 * s[3] and s[4] >= 0.6 * s[2] * s[3]
            ]

        def _below(a, b):
            return (
                abs(a[0] - b[0]) <= 0.08 * a[2]
                and abs(a[2] - b[2]) <= 0.10 * a[2]
                and 0 <= b[1] - a[1] - a[3] <= 0.8 * a[3]
            )

        found = set()
        for orange in buttons["orange"]:
            if any(_below(g, orange) for g in buttons["green"]):
                found.add("storage" if any(_below(orange, b) for b in buttons["blue"]) else "shop")
            elif any(_below(orange, g) for g in buttons["green"]):
                found.add("trade")
        return next((k for k in ("storage", "shop", "trade") if k in found), None)

    @staticmethod
    def find_mesos_field_in_frame(bgr: np.ndarray, gh: int = 7, hsv: Optional[np.ndarray] = None) -> Optional[Tuple[int, int, int, int]]:
        """
        Automatically locates the white Inventory Meso box (with the gold coin on its left)
        anywhere inside the game window frame. Returns (x, y, w, h) or None.
        """
        if bgr is None or bgr.size == 0:
            return None
        if hsv is None:
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        hue, sat, val = cv2.split(hsv)
        n, _, stats, _ = cv2.connectedComponentsWithStats(
            ((val > 225) & (sat < 30)).astype(np.uint8), connectivity=8
        )
        coin = (hue >= 12) & (hue <= 35) & (sat >= 100) & (val >= 140)
        found = []
        for i in range(1, n):
            x, y, w, h, area = map(int, stats[i])
            if h < 8 or not (7.0 * h <= w <= 16.0 * h) or area < 0.6 * w * h:
                continue
            if gh and not (15.0 * gh <= w <= 23.0 * gh and 1.3 * gh <= h <= 2.4 * gh):
                continue
            left_coin = coin[y:y + h, max(0, x - int(1.6 * h)):x]
            if left_coin.size == 0 or left_coin.mean() < 0.15:
                continue
            found.append((area, (x, y, w, h)))
        if not found:
            return None
        found.sort(reverse=True)
        return found[0][1]

    @staticmethod
    def detect_party_in_frame(bgr: np.ndarray, gh: int = 7, hsv: Optional[np.ndarray] = None) -> str:
        """
        Counts party members from the evenly spaced column of party HP bars on screen.
        Returns 'Solo' or '2ppl'..'6ppl'.
        """
        if bgr is None or bgr.size == 0:
            return "Solo"
        val = (cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV) if hsv is None else hsv)[..., 2]
        n, _, stats, _ = cv2.connectedComponentsWithStats((val < 70).astype(np.uint8), connectivity=8)
        bars = sorted(
            (
                tuple(map(int, stats[i][:4]))
                for i in range(1, n)
                if 7.5 * gh <= stats[i][2] <= 10.5 * gh and 1.3 * gh <= stats[i][3] <= 1.85 * gh
            ),
            key=lambda b: b[1],
        )
        best = []
        for i, first in enumerate(bars):
            same = [
                b
                for b in bars[i:]
                if abs(b[0] - first[0]) <= 0.5 * gh
                and abs(b[2] - first[2]) <= 0.5 * gh
                and abs(b[3] - first[3]) <= 0.3 * gh
            ]
            column = [first]
            pitch = None
            for b in same[1:]:
                step = b[1] - column[-1][1]
                if pitch is None and 1.8 * gh <= step <= 3.0 * gh:
                    pitch = step
                if pitch is None or abs(step - pitch) > 0.3 * gh:
                    break
                column.append(b)
            if len(column) > len(best):
                best = column
        count = len(best) if len(best) >= 2 else 1
        return f"{min(6, count)}ppl" if count >= 2 else "Solo"

    def scan_window_extras(self, exclude_rect: Optional[Tuple[int, int, int, int]] = None) -> Tuple[Optional[np.ndarray], Optional[str], Optional[str]]:
        """
        Performs a periodic scan of the active game window to automatically:
        1. Check if Shop/Storage/Trade is open
        2. Auto-detect and crop the Inventory Meso box (even if never calibrated with Select Area)
        3. Auto-detect Party size from the Party HP bar list ('Solo' or '2ppl'..'6ppl')
        Returns (meso_crop, party_str, money_window_kind).
        """
        geom = self.wm.get_window_geometry()
        if not geom:
            return None, None, None

        s, _ = self._get_scale_and_viewport_left(geom["width"], geom["height"])
        gh = 7 * s
        bbox = {
            "top": int(geom["top"]),
            "left": int(geom["left"]),
            "width": int(geom["width"]),
            "height": int(geom["height"]),
        }
        try:
            shot = self.sct.grab(bbox)
            bgr = cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)
        except Exception:
            return None, None, None

        # Blank out our own HUD overlay rectangle so we never detect widgets inside our own HUD
        if exclude_rect:
            ex_x, ex_y, ex_w, ex_h = exclude_rect
            rx0 = max(0, ex_x - bbox["left"])
            ry0 = max(0, ex_y - bbox["top"])
            rx1 = min(bbox["width"], ex_x + ex_w - bbox["left"])
            ry1 = min(bbox["height"], ex_y + ex_h - bbox["top"])
            if rx1 > rx0 and ry1 > ry0:
                bgr[ry0:ry1, rx0:rx1] = 0

        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        money_win = self.find_money_window_in_frame(bgr)
        party_str = self.detect_party_in_frame(bgr, gh=gh, hsv=hsv)

        meso_crop = None
        if money_win is None:
            box = self.find_mesos_field_in_frame(bgr, gh=gh, hsv=hsv)
            if box is not None:
                x, y, w, h = box
                meso_crop = bgr[y:y + h, x:x + w].copy()

        return meso_crop, party_str, money_win
