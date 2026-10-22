"""
Official MeowDB MapleStory Classic World EXP Table (Levels 1 to 100).
Supports exact level detection from raw EXP and percentage.
"""

from typing import Dict, Tuple, Optional

# Official MapleStory Classic World curve sourced from MeowDB
MEOWDB_CLASSIC_EXP_TABLE: Dict[int, int] = {
    1: 15,
    2: 34,
    3: 57,
    4: 92,
    5: 135,
    6: 372,
    7: 560,
    8: 840,
    9: 1242,
    10: 1716,
    11: 2360,
    12: 3216,
    13: 4200,
    14: 5460,
    15: 7050,
    16: 8840,
    17: 11040,
    18: 13716,
    19: 16680,
    20: 20216,
    21: 24402,
    22: 28980,
    23: 34320,
    24: 40512,
    25: 47216,
    26: 54900,
    27: 63666,
    28: 73080,
    29: 83720,
    30: 95700,
    31: 108480,
    32: 122760,
    33: 138666,
    34: 155540,
    35: 174216,
    36: 194832,
    37: 216600,
    38: 240500,
    39: 266682,
    40: 294216,
    41: 324240,
    42: 356916,
    43: 391160,
    44: 428280,
    45: 468450,
    46: 510420,
    47: 555680,
    48: 604416,
    49: 655200,
    50: 709716,
    51: 748608,
    52: 789631,
    53: 832902,
    54: 878545,
    55: 926689,
    56: 977471,
    57: 1031036,
    58: 1087536,
    59: 1147132,
    60: 1209994,
    61: 1276301,
    62: 1346242,
    63: 1420016,
    64: 1497832,
    65: 1579913,
    66: 1666492,
    67: 1757815,
    68: 1854143,
    69: 1955750,
    70: 2062925,
    71: 2175973,
    72: 2295216,
    73: 2420993,
    74: 2553663,
    75: 2693603,
    76: 2841212,
    77: 2996910,
    78: 3161140,
    79: 3334370,
    80: 3517093,
    81: 3709829,
    82: 3913071,
    83: 4127419,
    84: 4353468,
    85: 4591857,
    86: 4843233,
    87: 5108230,
    88: 5387527,
    89: 5681858,
    90: 11931902,
    91: 25056994,
    92: 52619687,
    93: 110501343,
    94: 232052820,
    95: 487310922,
    96: 1023352936,
    97: 2149041166,
    98: 4512986449,
    99: 9477271543
}


def get_max_exp_for_level(level: int) -> int:
    """Returns the total EXP needed to complete the given level in MapleStory Classic."""
    return MEOWDB_CLASSIC_EXP_TABLE.get(level, 1031036)


def calculate_raw_exp(level: int, percentage: float) -> int:
    """Calculates approximate numeric EXP given level and current percentage."""
    max_exp = get_max_exp_for_level(level)
    return int(round(max_exp * (max(0.0, min(100.0, percentage)) / 100.0)))


def detect_level_from_exp(raw_exp: int, pct: float) -> Optional[int]:
    """
    Mathematically infers the exact player Level from raw EXP and percentage:
    implied_max = raw_exp / (pct / 100.0).
    Finds the exact matching level in the MeowDB table.
    """
    if raw_exp <= 0 or pct <= 0.05 or pct > 100.0:
        return None

    implied_max = raw_exp / (pct / 100.0)

    best_level = None
    best_diff = float("inf")

    for lv, max_val in MEOWDB_CLASSIC_EXP_TABLE.items():
        diff = abs(implied_max - max_val)
        rel_diff = diff / max_val
        if rel_diff < 0.03: # within 3% tolerance due to float rounding on the 2-decimal %
            if diff < best_diff:
                best_diff = diff
                best_level = lv

    return best_level


def format_number_k_m(num: float) -> str:
    """Formats 20260 -> '20.26K', 1500000 -> '1.50M'."""
    abs_num = abs(num)
    sign = "-" if num < 0 else ""
    if abs_num >= 1_000_000:
        return f"{sign}{abs_num / 1_000_000:.2f}M"
    elif abs_num >= 1_000:
        return f"{sign}{abs_num / 1_000:.2f}K"
    return f"{sign}{int(abs_num):,}"


def format_eta_str(level: int, current_exp: int, max_exp: int, exp_per_hr: float) -> str:
    """Returns 'Lv [next] in [X] h [Y] min' based on true remaining EXP points."""
    next_level = level + 1
    if exp_per_hr <= 10.0:
        return f"Lv {next_level} in -- h -- min"

    remaining_exp = max(0, max_exp - current_exp)
    total_hours = remaining_exp / exp_per_hr
    hours = int(total_hours)
    minutes = int((total_hours - hours) * 60)

    if hours >= 100:
        return f"Lv {next_level} in >99h"
    elif hours > 0:
        return f"Lv {next_level} in {hours} h {minutes} min"
    else:
        return f"Lv {next_level} in {minutes} min"
