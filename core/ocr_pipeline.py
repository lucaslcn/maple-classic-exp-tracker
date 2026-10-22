import os
import re
import cv2
import numpy as np
import pytesseract
from typing import Dict, Any, Optional, Tuple
from core.paths import get_bundle_dir, get_app_dir
from core.map_matcher import get_map_matcher


LV_BITMAP_TEMPLATES: Dict[str, str] = {
    '0': '.#####.\n##...##\n##...##\n##...##\n##...##\n##...##\n.#####.',
    '1': '.##\n###\n.##\n.##\n.##\n.##\n.##',
    '2': '.#####.\n##...##\n.....##\n..####.\n.##....\n##.....\n#######',
    '3': '.#####.\n##...##\n.....##\n..####.\n.....##\n##...##\n.#####.',
    '4': '...###.\n..####.\n.##.##.\n##..##.\n#######\n....##.\n....##.',
    '5': '#######\n##.....\n##.....\n.#####.\n.....##\n##...##\n.#####.',
    '6': '.#####.\n##...##\n##.....\n######.\n##...##\n##...##\n.#####.',
    '7': '#######\n.....##\n....##.\n...##..\n...##..\n..##...\n..##...',
    '8': '.#####.\n##...##\n##...##\n.#####.\n##...##\n##...##\n.#####.',
    '9': '.#####.\n##...##\n##...##\n.######\n.....##\n##...##\n.#####.',
}

EXP_BITMAP_TEMPLATES: Dict[str, str] = {
    '0': '.###.\n#...#\n#...#\n#...#\n#...#\n#...#\n.###.',
    '1': '.#\n##\n.#\n.#\n.#\n.#\n.#',
    '2': '.###.\n#...#\n....#\n...#.\n..#..\n.#...\n#####',
    '3': '.###.\n#...#\n....#\n..##.\n....#\n#...#\n.###.',
    '4': '...#.\n..##.\n.#.#.\n#..#.\n#####\n...#.\n...#.',
    '5': '#####\n#....\n#....\n.###.\n....#\n#...#\n.###.',
    '6': '.###.\n#...#\n#....\n####.\n#...#\n#...#\n.###.',
    '7': '#####\n....#\n....#\n....#\n...#.\n..#..\n..#..',
    '8': '.###.\n#...#\n#...#\n.###.\n#...#\n#...#\n.###.',
    '9': '.###.\n#...#\n#...#\n.####\n....#\n#...#\n.###.',
    '[': '##\n#.\n#.\n#.\n#.\n#.\n##',
    ']': '##\n.#\n.#\n.#\n.#\n.#\n##',
    '%': '.#....#\n#.#..#.\n.#..#..\n...#...\n..#..#.\n.#..#.#\n#....#.',
}


class OCREngine:
    """
    Enhanced OCR engine for MapleStory Classic World:
    1. Level badge: Deterministic 7-row bitmap template matching + Tesseract fallback
    2. EXP bar: Deterministic 7-row bitmap template matching (preserving gray brackets) + Tesseract fallback
    3. Minimap banner: White-text thresholding for Map location name
    4. Inventory: Meso counter
    """

    TESSERACT_CANDIDATES = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Users\lucas\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
    ]

    def __init__(self, tesseract_path: Optional[str] = None):
        self._init_tesseract(tesseract_path)
        self.tess_config_exp = r'--oem 3 --psm 7'
        self.tess_config_text = r'--oem 3 --psm 6'
        self.tess_config_digits = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789,'
        self.tess_config_level = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'

        self._lv_arrays = {
            k: np.array([[1 if c == '#' else 0 for c in r] for r in v.split('\n')], dtype=np.uint8)
            for k, v in LV_BITMAP_TEMPLATES.items()
        }
        self._exp_arrays = {
            k: np.array([[1 if c == '#' else 0 for c in r] for r in v.split('\n')], dtype=np.uint8)
            for k, v in EXP_BITMAP_TEMPLATES.items()
        }

    def _init_tesseract(self, explicit_path: Optional[str] = None):
        candidates = []
        if explicit_path:
            candidates.append(explicit_path)

        # Prioritize bundled Tesseract-OCR inside portable executable package
        candidates.extend([
            os.path.join(get_bundle_dir(), "Tesseract-OCR", "tesseract.exe"),
            os.path.join(get_app_dir(), "Tesseract-OCR", "tesseract.exe"),
            os.path.join(get_app_dir(), "_internal", "Tesseract-OCR", "tesseract.exe"),
        ])
        candidates.extend(self.TESSERACT_CANDIDATES)

        for path in candidates:
            if path and os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                tessdata_dir = os.path.join(os.path.dirname(path), "tessdata")
                if os.path.isdir(tessdata_dir):
                    os.environ["TESSDATA_PREFIX"] = tessdata_dir
                return

    def extract_level(self, image: np.ndarray) -> Optional[int]:
        """
        Extracts the player's Level directly from the bottom-bar LV. badge image.
        Automatically normalizes 2x integer-scaled crops (e.g. 1440p/4K fullscreen) to 1x,
        then uses exact 7-row bitmap matching first, falling back to Tesseract digit OCR.
        """
        if image is None or image.size == 0:
            return None

        gray_full = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        if gray_full.shape[0] >= 36:
            candidates = [gray_full[::2, ::2], gray_full[1::2, 1::2]]
        else:
            candidates = [gray_full]

        # 1. Bitmap template matching on high-luminance white digits (> 185)
        for gray in candidates:
            thresh = (gray > 185).astype(np.uint8)
            rows = [r for r in range(thresh.shape[0]) if thresh[r].sum() > 0]
            if rows:
                sub = thresh[min(rows):max(rows) + 1, :]
                if 5 <= sub.shape[0] <= 9:
                    cols = sub.sum(axis=0)
                    in_c = False
                    st = 0
                    digits = []
                    for x, c in enumerate(cols):
                        if c > 0 and not in_c:
                            in_c = True
                            st = x
                        elif c == 0 and in_c:
                            in_c = False
                            g = sub[:, st:x]
                            ch = self._match_template(g, self._lv_arrays, min_score=0.80)
                            digits.append(ch or '?')
                    if in_c:
                        g = sub[:, st:]
                        ch = self._match_template(g, self._lv_arrays, min_score=0.80)
                        digits.append(ch or '?')

                    lv_str = "".join(digits)
                    if lv_str and '?' not in lv_str and lv_str.isdigit():
                        val = int(lv_str)
                        if 1 <= val <= 100:
                            return val

        # 2. Fallback: Tesseract on 4x nearest-neighbor scaled binary image
        try:
            gray = candidates[0]
            _, binary = cv2.threshold(gray, 185, 255, cv2.THRESH_BINARY_INV)
            scaled = cv2.resize(binary, (0, 0), fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
            padded = cv2.copyMakeBorder(scaled, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
            txt = pytesseract.image_to_string(padded, config=self.tess_config_level).strip()
            if txt.isdigit():
                val = int(txt)
                if 1 <= val <= 100:
                    return val
        except Exception:
            pass

        return None

    def _match_template(self, glyph: np.ndarray, templates: Dict[str, np.ndarray], min_score: float = 0.85) -> Optional[str]:
        best_char = None
        best_score = -1.0
        gh, gw = glyph.shape
        for ch, t in templates.items():
            th, tw = t.shape
            if abs(gw - tw) > 1 or abs(gh - th) > 1:
                continue
            if (gh, gw) != (th, tw):
                gr = cv2.resize(glyph, (tw, th), interpolation=cv2.INTER_NEAREST)
            else:
                gr = glyph
            score = float((gr == t).mean())
            if score > best_score:
                best_score = score
                best_char = ch
        return best_char if best_score >= min_score else None

    def _extract_exp_bitmap(self, gray: np.ndarray) -> Tuple[Optional[int], Optional[float], str]:
        """
        Scans the EXP crop for the 7-row status bar pixel font (threshold > 125 preserves gray '[' and ']').
        Returns (current_exp, percentage, decoded_string).
        """
        h, w = gray.shape
        if h < 7 or w < 30:
            return None, None, ""

        # Find the 7-row text band (above the progress bar)
        thresh = (gray > 125).astype(np.uint8)
        best_parsed = (None, None, "")

        # Candidate starting rows for the 7-pixel-tall bitmap line (numbers start after 'EXP' at x=26)
        x_start = 26 if w > 60 else 0
        x_end = min(w, 160)
        for y0 in range(0, min(h - 6, 16)):
            band = thresh[y0:y0 + 7, x_start:x_end]
            # Must have empty row above and below in the number region (after 'EXP' label)
            if y0 > 0 and thresh[y0 - 1, x_start:min(w, 130)].sum() > 3:
                continue
            if y0 + 7 < h and thresh[y0 + 7, x_start:min(w, 130)].sum() > 5:
                continue
            if band.sum() < 15:
                continue

            cols = band.sum(axis=0)
            in_c = False
            st = 0
            tokens = []
            for x, c in enumerate(cols):
                if c > 0 and not in_c:
                    in_c = True
                    st = x
                elif c == 0 and in_c:
                    in_c = False
                    g = band[:, st:x]
                    # Check if dot or comma (1-2px wide, only bottom 2 rows lit)
                    if g.shape[1] <= 2 and g[:5, :].sum() == 0 and g[5:, :].sum() > 0:
                        tokens.append('.')
                    else:
                        ch = self._match_template(g, self._exp_arrays, min_score=0.85)
                        if ch is not None:
                            tokens.append(ch)

            decoded = "".join(tokens)
            if '[' in decoded and '%' in decoded:
                # Split around '['
                before_bracket, after_bracket = decoded.split('[', 1)
                raw_digits = "".join(c for c in before_bracket if c.isdigit())
                pct_part = after_bracket.split('%', 1)[0]
                pct_clean = "".join(c for c in pct_part if c.isdigit() or c == '.')

                raw_val = int(raw_digits) if raw_digits else None
                pct_val = None
                try:
                    if pct_clean and '.' in pct_clean:
                        pv = float(pct_clean)
                        if 0.0 <= pv <= 100.0:
                            pct_val = pv
                except ValueError:
                    pass

                if pct_val is not None:
                    fmt = f"EXP {raw_val:,} [{pct_val:.2f}%]" if raw_val is not None else f"EXP [{pct_val:.2f}%]"
                    return raw_val, pct_val, fmt

        return best_parsed

    def preprocess_exp(self, image: np.ndarray) -> np.ndarray:
        """Preprocess EXP bar at threshold 125 so gray brackets '[' and ']' are preserved."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        if gray.shape == (52, 380):
            gray = gray[::2, ::2]
        # Crop out bottom progress bar only on standard 26px tall EXP bar crops
        text_strip = gray[:19, :] if gray.shape == (26, 190) else gray
        _, binary = cv2.threshold(text_strip, 125, 255, cv2.THRESH_BINARY_INV)
        scaled = cv2.resize(binary, (0, 0), fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
        return cv2.copyMakeBorder(scaled, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)

    def extract_exp(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Extracts both raw numeric EXP and percentage from the EXP bar crop.
        Automatically normalizes 2x integer-scaled crops (52x380) to 1x (26x190),
        1. Runs deterministic 7-row pixel bitmap matcher first.
        2. Falls back to bracket-isolated Tesseract OCR if bitmap match is not found (e.g. custom font/synthetic test).
        """
        if image is None or image.size == 0:
            return {
                "success": False,
                "raw_text": "",
                "percentage": None,
                "current_exp": None,
                "max_exp": None,
                "processed_image": image
            }

        gray_full = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        processed = self.preprocess_exp(image)

        if gray_full.shape[0] >= 44:
            candidates = [gray_full[::2, ::2], gray_full[1::2, 1::2]]
        else:
            candidates = [gray_full]

        # 1. Try deterministic 7-row bitmap template matcher first
        for gray in candidates:
            bm_raw, bm_pct, bm_text = self._extract_exp_bitmap(gray)
            if bm_pct is not None:
                return {
                    "success": True,
                    "percentage": bm_pct,
                    "current_exp": bm_raw,
                    "max_exp": None,
                    "raw_text": bm_text,
                    "processed_image": processed
                }

        # 2. Fallback to Tesseract OCR (for synthetic images or non-standard UI scaling)
        try:
            raw_text = pytesseract.image_to_string(processed, config=self.tess_config_exp).strip()
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "raw_text": "",
                "percentage": None,
                "current_exp": None,
                "max_exp": None,
                "processed_image": processed
            }

        percentage = None
        current_exp = None
        max_exp = None

        # Strictly isolate percentage from inside brackets/parentheses or immediately before '%'
        m_pct = re.search(r'[\(\[]\s*(\d{1,3}(?:\.\d{1,2})?)\s*%\s*[\)\]]?', raw_text)
        if not m_pct:
            m_pct = re.search(r'(\d{1,3}\.\d{2})\s*%', raw_text)

        if m_pct:
            try:
                val = float(m_pct.group(1))
                if 0.0 <= val <= 100.0:
                    percentage = val
            except ValueError:
                pass

        # Extract raw EXP strictly BEFORE the bracket/parenthesis (or before the matched percentage)
        m_raw = re.search(r'EXP\s*([0-9][0-9,\.]*)\s*[\(\[]', raw_text, re.IGNORECASE)
        if m_raw:
            clean = re.sub(r'[^0-9]', '', m_raw.group(1))
            if clean.isdigit() and len(clean) >= 1:
                current_exp = int(clean)

        # Match fraction formats if present: e.g. 12,345 / 500,000
        if current_exp is None:
            fraction_match = re.search(r'(\d[\d,]+)\s*(?:/|\|)\s*(\d[\d,]+)', raw_text)
            if fraction_match:
                try:
                    c_val = int(fraction_match.group(1).replace(',', ''))
                    m_val = int(fraction_match.group(2).replace(',', ''))
                    if m_val > 0 and c_val <= m_val:
                        current_exp = c_val
                        max_exp = m_val
                        if percentage is None:
                            percentage = round((c_val / m_val) * 100.0, 2)
                except ValueError:
                    pass

        return {
            "success": (percentage is not None or current_exp is not None),
            "percentage": percentage,
            "current_exp": current_exp,
            "max_exp": max_exp,
            "raw_text": raw_text,
            "processed_image": processed
        }

    def extract_map_name(self, image: np.ndarray) -> Optional[str]:
        """Extract white map title text (>195 luminance) from minimap banner crop."""
        if image is None or image.size == 0:
            return None

        is_2x = image.shape[0] >= 80
        img_1x = image[::2, ::2] if is_2x else image

        if is_2x:
            # Crop out top/bottom horizontal minimap border lines on standard 50px tall crops
            if img_1x.shape[0] >= 45:
                img_1x = img_1x[6:38, :]

            # Trim right side where the slate-blue minimap header ends
            if len(img_1x.shape) == 3 and img_1x.shape[1] > 60:
                b_minus_r = np.median(img_1x[:, :, 0].astype(int) - img_1x[:, :, 2].astype(int), axis=0)
                g_med = np.median(img_1x[:, :, 1], axis=0)
                valid_cols = np.where((b_minus_r > 20) & (g_med > 130))[0]
                if len(valid_cols) > 20 and valid_cols[-1] >= 60:
                    img_1x = img_1x[:, :min(img_1x.shape[1], valid_cols[-1] + 4)]

            gray = cv2.cvtColor(img_1x, cv2.COLOR_BGR2GRAY) if len(img_1x.shape) == 3 else img_1x
            upscaled = cv2.resize(gray, (0, 0), fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            _, thresh = cv2.threshold(upscaled, 195, 255, cv2.THRESH_BINARY_INV)
            padded = cv2.copyMakeBorder(thresh, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)
        else:
            gray = cv2.cvtColor(img_1x, cv2.COLOR_BGR2GRAY) if len(img_1x.shape) == 3 else img_1x
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
            scaled = cv2.resize(thresh, (0, 0), fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
            padded = cv2.copyMakeBorder(scaled, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)

        try:
            txt = pytesseract.image_to_string(padded, config=self.tess_config_text).strip()
            lines = [l.strip() for l in txt.splitlines() if l.strip()]
            valid_parts = []
            for line in lines:
                # Strip leading pipe or icon noise
                line = line.replace("’", "'").replace("‘", "'")
                cleaned = re.sub(r'^[^a-zA-Z0-9]+', '', line)
                cleaned = re.sub(r'[^a-zA-Z0-9\s:\'\-]', '', cleaned).strip()
                words = [w for w in cleaned.split() if len(w) > 1 or w in ["I", "V", "X", "1", "2", "3", "4", "5"]]
                if words:
                    part = " ".join(words)
                    if len(part) >= 3:
                        valid_parts.append(part)

            if valid_parts:
                result = f"{valid_parts[0]} : {valid_parts[1]}" if len(valid_parts) >= 2 else valid_parts[0]
                # Fix common pixel-font OCR substitutions on map names
                corrections = {
                    "Gungeon": "Dungeon",
                    "Oungeon": "Dungeon",
                    "Cungeon": "Dungeon",
                    "Dimgeon": "Dungeon",
                    "Gingedn": "Dungeon",
                    "Dunigecn": "Dungeon",
                    "Temnle": "Temple",
                    " ill": " III",
                    " Il": " II",
                }
                for wrong, right in corrections.items():
                    result = result.replace(wrong, right)
                return get_map_matcher().snap_map_name(result)
        except Exception:
            pass
        return None

    def extract_mesos(self, image: np.ndarray) -> Optional[int]:
        """Extract numerical Meso value from inventory meso box crop."""
        if image is None or image.size == 0:
            return None

        # Trim 2px inner border if box is large enough
        inner = image[2:-2, 2:-2] if (image.shape[0] > 10 and image.shape[1] > 20) else image
        gray = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY) if len(inner.shape) == 3 else inner

        # Inventory Meso box has dark digits on a bright white background (median > 180)
        is_white_bg = float(np.median(gray)) > 170.0
        thresh_mode = cv2.THRESH_BINARY if is_white_bg else cv2.THRESH_BINARY_INV
        _, thresh = cv2.threshold(gray, 165, 255, thresh_mode)
        scaled = cv2.resize(thresh, (0, 0), fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        padded = cv2.copyMakeBorder(scaled, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)

        try:
            txt = pytesseract.image_to_string(padded, config=self.tess_config_digits).strip()
            match = re.search(r'(\d{1,3}(?:,\d{3})+|\d+)', txt)
            if match:
                clean_num = int(match.group(1).replace(',', ''))
                if 0 <= clean_num <= 2147483647:
                    return clean_num
        except Exception:
            pass
        return None
