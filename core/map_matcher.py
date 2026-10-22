import os
import re
from typing import Optional, Tuple, List, Dict
from core.paths import get_bundle_dir


_ROMAN_RE = re.compile(r"^(?:X{0,2})(?:IX|IV|V?I{0,3})$")

KNOWN_REGIONS = [
    "Victoria Road",
    "Dungeon",
    "Hidden Street",
    "Maple Road",
    "Rainbow Street",
    "Warning Street",
    "Sleepywood",
    "Victoria Island",
    "Ossyria",
    "El Nath",
    "Ludus Lake",
    "Aqua Road",
    "Minar Forest",
    "Mu Lung",
    "Nihal Desert",
]


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            row.append(min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = row
    return prev[-1]


def _map_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _extract_numbers_and_romans(name: str) -> Tuple[str, ...]:
    tokens = name.split()
    out = []
    for i, tok in enumerate(tokens):
        clean_tok = re.sub(r"[^A-Za-z0-9]", "", tok)
        if any(c.isdigit() for c in clean_tok):
            out.append(clean_tok.lower())
        elif i == len(tokens) - 1 and _ROMAN_RE.match(clean_tok.upper()) and clean_tok:
            out.append(clean_tok.upper())
    return tuple(out)


def fix_roman(name: str) -> str:
    """Fixes Roman numeral misreads at the end of a map name (e.g. 'lV' -> 'IV', 'Vil' -> 'VII', 'il' -> 'II')."""
    def _fix(m):
        token = m.group(2)
        if not re.search(r"[IVXivxl|!]", token):
            return m.group(0)
        numeral = re.sub(r"[li1|!]", "I", token, flags=re.I).upper()
        return m.group(1) + numeral if numeral and _ROMAN_RE.match(numeral) else m.group(0)

    return re.sub(r"(\s)([IVXivxl1|!]{1,6})$", _fix, name)


def clean_map_part(text: str) -> str:
    t = text.replace("’", "'").replace("‘", "'").replace("|", "I")
    t = re.sub(r"(?<=\s)[!\[\]](?=\s*$)", "I", t)
    t = re.sub(r"[^A-Za-z0-9 '<>:.&()\-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" .:-")
    t = fix_roman(t)
    t = re.sub(r"(^|\s)[IiLl]st(?=\s|$)", r"\g<1>1st", t)
    t = re.sub(r"(^|\s)[Zz]nd(?=\s|$)", r"\g<1>2nd", t)
    t = re.sub(r"(^|\s)[SsBb5]rd(?=\s|$)", r"\g<1>3rd", t)
    return t if len(t) >= 3 else ""


class MapMatcher:
    """
    Matches OCR-extracted map names against the official MeowDB MapleStory Classic World map list
    (core/maps.txt) to fix typos and identify towns.
    """

    def __init__(self, maps_path: Optional[str] = None):
        if not maps_path:
            candidates = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps.txt"),
                os.path.join(get_bundle_dir(), "core", "maps.txt"),
                os.path.join(get_bundle_dir(), "maps.txt"),
            ]
            maps_path = next((p for p in candidates if os.path.exists(p)), candidates[0])

        self.entries: List[Tuple[str, str, bool, Tuple[str, ...]]] = []
        self.by_key: Dict[str, Tuple[str, str, bool, Tuple[str, ...]]] = {}

        if os.path.exists(maps_path):
            try:
                with open(maps_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        name, _, town_flag = line.partition("\t")
                        style = clean_map_part(name)
                        if style:
                            key = _map_key(style)
                            is_t = town_flag.strip() == "1"
                            nums = _extract_numbers_and_romans(style)
                            entry = (style, key, is_t, nums)
                            self.entries.append(entry)
                            self.by_key[key] = entry
            except Exception:
                pass

    def match_single_map(self, raw_map: str) -> Tuple[str, bool]:
        """Returns (canonical_map_name, is_town) for a single map name (without region prefix)."""
        cleaned = clean_map_part(raw_map)
        if not cleaned:
            return raw_map.strip(), False

        key = _map_key(cleaned)
        if key in self.by_key:
            e = self.by_key[key]
            return e[0], e[2]

        nums = _extract_numbers_and_romans(cleaned)
        best = None
        second_dist = 999
        for e in self.entries:
            if e[3] != nums or abs(len(e[1]) - len(key)) > 2:
                continue
            d = _edit_distance(key, e[1])
            if best is None or d < best[0]:
                second_dist = best[0] if best else second_dist
                best = (d, e)
            elif d < second_dist:
                second_dist = d

        allowed = 2 if len(key) >= 14 else 1
        if best and best[0] <= allowed and (second_dist - best[0] >= 1):
            return best[1][0], best[1][2]

        return cleaned, False

    def match_region(self, raw_region: str) -> str:
        cleaned = clean_map_part(raw_region)
        if not cleaned:
            return raw_region.strip()
        key = _map_key(cleaned)
        for reg in KNOWN_REGIONS:
            if _map_key(reg) == key:
                return reg
        best_reg = None
        best_d = 999
        for reg in KNOWN_REGIONS:
            rk = _map_key(reg)
            if abs(len(rk) - len(key)) <= 2:
                d = _edit_distance(key, rk)
                if d < best_d:
                    best_d = d
                    best_reg = reg
        if best_reg and best_d <= 2:
            return best_reg
        return cleaned

    def snap_map_name(self, full_name: str) -> str:
        """
        Snaps either 'Region : Map Name' or 'Map Name' to its official MeowDB spelling.
        """
        if not full_name:
            return full_name

        if ":" in full_name:
            reg_part, map_part = full_name.split(":", 1)
            snapped_reg = self.match_region(reg_part.strip())
            snapped_map, _ = self.match_single_map(map_part.strip())
            # Also check if map_part alone is actually the region or identical
            if snapped_reg and snapped_map:
                return f"{snapped_reg} : {snapped_map}"

        snapped_map, _ = self.match_single_map(full_name)
        return snapped_map

    def is_town(self, full_name: str) -> bool:
        """Returns True if the map is an official Town (e.g. Sleepywood, Henesys, Ellinia)."""
        if not full_name:
            return False
        target = full_name.split(":", 1)[1].strip() if ":" in full_name else full_name.strip()
        _, town = self.match_single_map(target)
        return town


_MATCHER_INSTANCE: Optional[MapMatcher] = None


def get_map_matcher() -> MapMatcher:
    global _MATCHER_INSTANCE
    if _MATCHER_INSTANCE is None:
        _MATCHER_INSTANCE = MapMatcher()
    return _MATCHER_INSTANCE

