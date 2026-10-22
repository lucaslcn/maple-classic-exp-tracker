import time
from typing import Optional, List, Tuple
from dataclasses import dataclass
from core.exp_table import (
    get_max_exp_for_level,
    calculate_raw_exp,
    detect_level_from_exp,
    format_number_k_m,
    format_eta_str
)
from core.map_matcher import get_map_matcher


@dataclass
class TrackerSnapshot:
    is_active: bool = False
    is_paused: bool = False
    is_auto_paused: bool = False

    # Timing
    elapsed_seconds: float = 0.0
    elapsed_time_str: str = "0:00:00"
    date_str: str = ""

    # Context
    map_name: str = "Victoria Road"
    level: int = 57
    party: str = "Solo"

    # EXP Metrics
    current_pct: Optional[float] = None
    start_pct: Optional[float] = None
    gained_pct: float = 0.0

    current_exp: int = 0
    max_exp: int = 1031036
    gained_exp: int = 0
    level_ups: int = 0

    hero_exp_per_hr: int = 0
    hero_eta_str: str = "Lv -- in -- h -- min"
    exp_last_5min: int = 0
    pct_per_hour: float = 0.0

    gained_exp_display: str = "0 (+0 lvl)"
    current_exp_display: str = "0 [0.00%]"

    # Meso Metrics
    current_mesos: Optional[int] = None
    start_mesos: Optional[int] = None
    gained_mesos: int = 0
    mesos_display: str = "-- (+0)"
    mesos_per_hr: int = 0
    mesos_5min: int = 0

    # Status / Banner
    status_text: str = "Waiting for game EXP..."


class ExpTracker:
    """
    Core analytics engine for MapleStory Classic World:
    - Reads Level directly from the bottom-bar LV. badge image (cross-checked with MeowDB curve)
    - Enforces strict mutual consistency between raw EXP, percentage, and level max EXP
    - Accumulates monotonic EXP deltas so EXP/hr never spikes or drops to 0 out of nowhere
    - Automatic idle pause (15s threshold) with rate hold
    """

    def __init__(self, idle_timeout_sec: float = 15.0, rolling_window_sec: float = 300.0):
        self.idle_timeout_sec = idle_timeout_sec
        self.rolling_window_sec = rolling_window_sec

        # Context
        self.map_name: str = "Victoria Road"
        self.level: int = 57
        self.party: str = "Solo"

        # Level consensus state (for image-based level updates without locking)
        self._pending_level: Optional[int] = None
        self._pending_level_count: int = 0

        # Session State
        self.is_paused: bool = False
        self.is_auto_paused: bool = False
        self.start_time: Optional[float] = None
        self.manual_pause_start: Optional[float] = None
        self.auto_pause_start: Optional[float] = None
        self.total_paused_duration: float = 0.0
        self.last_exp_gain_time: Optional[float] = None

        # Live EXP State
        self.start_pct: Optional[float] = None
        self.last_valid_pct: Optional[float] = None
        self.start_raw_exp: Optional[int] = None
        self.last_valid_raw_exp: Optional[int] = None
        self.total_gained_exp: int = 0
        self.total_gained_pct: float = 0.0
        self.level_ups: int = 0

        # Rate hold cache (prevents dropping to 0 between kills)
        self._last_nonzero_exp_hr: int = 0
        self._last_nonzero_pct_hr: float = 0.0

        # History for rolling 5-min rates: (timestamp, active_elapsed_sec, total_gained_exp, total_gained_mesos)
        self.history: List[Tuple[float, float, int, int]] = []

        # Meso Tracking
        self.start_mesos: Optional[int] = None
        self.last_valid_mesos: Optional[int] = None

        # Outlier rejection & Death tracking
        self._pending_suspicious_pct: Optional[float] = None
        self._pending_suspicious_raw: Optional[int] = None
        self._suspicious_count: int = 0
        self.deaths: int = 0
        self.last_death_loss: int = 0

    def reset_session(self):
        """Reset session counters cleanly to current live progress."""
        self.start_time = None
        self.manual_pause_start = None
        self.auto_pause_start = None
        self.total_paused_duration = 0.0
        self.last_exp_gain_time = None
        self.is_auto_paused = False

        self.start_pct = None
        self.last_valid_pct = None
        self.start_raw_exp = None
        self.last_valid_raw_exp = None
        self.total_gained_exp = 0
        self.total_gained_pct = 0.0
        self.level_ups = 0

        self._last_nonzero_exp_hr = 0
        self._last_nonzero_pct_hr = 0.0

        self.start_mesos = None
        self.last_valid_mesos = None
        self.history.clear()

        self._pending_suspicious_pct = None
        self._pending_suspicious_raw = None
        self._suspicious_count = 0
        self.deaths = 0
        self.last_death_loss = 0

    def toggle_pause(self) -> bool:
        now = time.time()
        if not self.is_paused:
            self.is_paused = True
            self.manual_pause_start = now
        else:
            self.is_paused = False
            if self.manual_pause_start:
                self.total_paused_duration += (now - self.manual_pause_start)
                self.manual_pause_start = None
        return self.is_paused

    def set_map(self, map_name: str):
        if map_name and len(map_name.strip()) >= 3:
            self.map_name = map_name.strip()

    def set_level(self, level: int, user_locked: bool = False):
        if 1 <= level <= 100:
            self.level = level
            self._pending_level = None
            self._pending_level_count = 0

    def set_party(self, party: str):
        if party:
            self.party = party.strip()

    def get_elapsed_seconds(self) -> float:
        if not self.start_time:
            return 0.0
        now = time.time()
        paused = self.total_paused_duration
        if self.is_paused and self.manual_pause_start:
            paused += (now - self.manual_pause_start)
        elif self.is_auto_paused and self.auto_pause_start:
            paused += (now - self.auto_pause_start)
        return max(0.0, now - self.start_time - paused)

    def _format_time_hms(self, seconds: float) -> str:
        if seconds <= 0:
            return "0:00:00"
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hrs}:{mins:02d}:{secs:02d}"

    def _update_level_from_sensors(
        self,
        detected_level: Optional[int],
        raw_exp: Optional[int],
        pct: Optional[float]
    ):
        """
        Updates self.level dynamically from the bottom-bar LV. badge image
        and cross-validates with the MeowDB EXP table.
        """
        inferred_lv = detect_level_from_exp(raw_exp, pct) if (raw_exp is not None and pct is not None) else None

        # Determine candidate level from image badge and/or EXP ratio
        candidate = None
        if detected_level is not None and 1 <= detected_level <= 100:
            candidate = detected_level
        elif inferred_lv is not None:
            candidate = inferred_lv

        if candidate is None or candidate == self.level:
            self._pending_level = None
            self._pending_level_count = 0
            return

        # On initial startup before session baseline is set, accept immediately if badge read or inferred
        if self.start_time is None:
            self.level = candidate
            return

        # If badge and EXP ratio both agree on the new level, accept immediately
        if detected_level is not None and inferred_lv is not None and detected_level == inferred_lv:
            self.level = candidate
            self._pending_level = None
            self._pending_level_count = 0
            return

        # Otherwise require 2 consecutive identical reads from the LV. badge image
        if detected_level is not None:
            if self._pending_level == detected_level:
                self._pending_level_count += 1
                if self._pending_level_count >= 2:
                    self.level = detected_level
                    self._pending_level = None
                    self._pending_level_count = 0
            else:
                self._pending_level = detected_level
                self._pending_level_count = 1

    def update(
        self,
        pct: Optional[float],
        raw_exp: Optional[int] = None,
        mesos: Optional[int] = None,
        map_name: Optional[str] = None,
        detected_level: Optional[int] = None,
        party: Optional[str] = None
    ) -> TrackerSnapshot:
        now = time.time()

        if map_name:
            self.set_map(map_name)
        if party:
            self.set_party(party)

        if mesos is not None and mesos > 0:
            if self.start_mesos is None:
                self.start_mesos = mesos
            self.last_valid_mesos = mesos

        # 1. Update level from image sensors
        prev_level = self.level
        self._update_level_from_sensors(detected_level, raw_exp, pct)

        # 2. Validate and reconcile (pct, raw_exp) against current level's max_exp
        max_exp = get_max_exp_for_level(self.level)
        if not self.is_paused and (pct is not None or raw_exp is not None):
            clean_pct, clean_raw = self._reconcile_exp_pair(pct, raw_exp, max_exp)

            if clean_pct is not None and clean_raw is not None:
                if self.start_pct is None:
                    self.start_pct = clean_pct
                    self.last_valid_pct = clean_pct
                    self.start_raw_exp = clean_raw
                    self.last_valid_raw_exp = clean_raw
                    self.start_time = now
                    self.last_exp_gain_time = now
                    self.history.append((now, 0.0, 0, 0))
                else:
                    self._process_exp_update(now, clean_pct, clean_raw, prev_level, detected_level)

        # 3. Check Idle Auto-Pause Condition
        self._check_auto_pause(now)

        return self.get_snapshot()

    def _reconcile_exp_pair(
        self,
        pct: Optional[float],
        raw_exp: Optional[int],
        max_exp: int
    ) -> Tuple[Optional[float], Optional[int]]:
        """
        Cross-validates raw_exp and pct using max_exp.
        Prevents misread percentages (like 0.10%) or dropped digits in raw_exp from corrupting state.
        """
        if raw_exp is not None and (raw_exp < 0 or raw_exp > max_exp):
            raw_exp = None
        if pct is not None and (pct < 0.0 or pct > 100.0):
            pct = None

        if raw_exp is not None and pct is not None:
            expected_pct = round((raw_exp / max_exp) * 100.0, 2)
            if abs(expected_pct - pct) <= 0.15:
                return pct, raw_exp

            # Mismatch between raw_exp and pct: check which one is consistent with last valid state
            if self.last_valid_raw_exp is not None:
                raw_diff = raw_exp - self.last_valid_raw_exp
                if 0 <= raw_diff <= max_exp * 0.15:
                    if raw_diff == 0 and self.last_valid_pct is not None:
                        return self.last_valid_pct, self.last_valid_raw_exp
                    # raw_exp is monotonically valid -> fix pct using expected_pct
                    return expected_pct, raw_exp
            if self.last_valid_pct is not None:
                pct_diff = pct - self.last_valid_pct
                if 0.0 <= pct_diff <= 15.0:
                    if pct_diff == 0.0 and self.last_valid_raw_exp is not None:
                        return self.last_valid_pct, self.last_valid_raw_exp
                    # pct is monotonically valid -> derive raw_exp from pct
                    return pct, calculate_raw_exp(self.level, pct)
            return None, None

        elif raw_exp is not None:
            expected_pct = round((raw_exp / max_exp) * 100.0, 2)
            return expected_pct, raw_exp

        elif pct is not None:
            return pct, calculate_raw_exp(self.level, pct)

        return None, None

    def _process_exp_update(
        self,
        now: float,
        pct: float,
        raw_exp: int,
        prev_level: int,
        detected_level: Optional[int] = None
    ):
        if self.last_valid_pct is None or self.last_valid_raw_exp is None:
            self.last_valid_pct = pct
            self.last_valid_raw_exp = raw_exp
            return

        max_exp = get_max_exp_for_level(self.level)
        exp_changed = False

        # 1. Level-Up detection:
        # Either previous pct >= 90% and new pct < 15%, OR image LV. badge incremented and raw_exp rolled over
        if (self.last_valid_pct >= 90.0 and pct < 15.0 and raw_exp < self.last_valid_raw_exp) or \
           (self.level > prev_level and pct < 25.0):
            prev_max = get_max_exp_for_level(prev_level)
            delta_exp = max(0, prev_max - self.last_valid_raw_exp) + raw_exp
            delta_pct = max(0.0, 100.0 - self.last_valid_pct) + pct

            self.level_ups += 1
            if self.level == prev_level:
                if detected_level is not None and detected_level > prev_level:
                    self.level = detected_level
                else:
                    self.level = prev_level + 1

            self.total_gained_exp += delta_exp
            self.total_gained_pct += delta_pct
            self.last_valid_pct = pct
            self.last_valid_raw_exp = raw_exp
            exp_changed = True

        # 2. Normal forward progression (STRICT 'and' check: both raw_exp AND pct must be non-decreasing!)
        elif (pct >= self.last_valid_pct and (pct - self.last_valid_pct) <= 15.0) and \
             (raw_exp >= self.last_valid_raw_exp and (raw_exp - self.last_valid_raw_exp) <= max_exp * 0.15):
            delta_exp = raw_exp - self.last_valid_raw_exp
            delta_pct = pct - self.last_valid_pct
            if delta_exp > 0 or delta_pct > 0.0:
                self.total_gained_exp += delta_exp
                self.total_gained_pct += delta_pct
                exp_changed = True

            self.last_valid_pct = pct
            self.last_valid_raw_exp = raw_exp
            self._suspicious_count = 0
            self._pending_suspicious_pct = None
            self._pending_suspicious_raw = None

        # 3. Death EXP-Loss Protection & Outlier Filter:
        # If EXP drops by 0.5%..12% on the same level (and raw_exp/pct mutually agree), accept after 2 confirmations
        # without subtracting from total_gained_exp!
        else:
            is_plausible_death = (
                self.level == prev_level
                and 0.5 <= (self.last_valid_pct - pct) <= 12.0
                and raw_exp < self.last_valid_raw_exp
                and abs(round((raw_exp / max_exp) * 100.0, 2) - pct) <= 0.15
            )
            if self._pending_suspicious_pct == pct and self._pending_suspicious_raw == raw_exp:
                self._suspicious_count += 1
                required = 2 if is_plausible_death else 3
                if self._suspicious_count >= required:
                    if is_plausible_death:
                        self.deaths += 1
                        self.last_death_loss = self.last_valid_raw_exp - raw_exp
                    self.last_valid_pct = pct
                    self.last_valid_raw_exp = raw_exp
                    self._suspicious_count = 0
                    self._pending_suspicious_pct = None
                    self._pending_suspicious_raw = None
            else:
                self._pending_suspicious_pct = pct
                self._pending_suspicious_raw = raw_exp
                self._suspicious_count = 1

        if exp_changed:
            # Resume from auto-pause immediately on EXP gain
            if self.is_auto_paused:
                self.is_auto_paused = False
                if self.auto_pause_start:
                    self.total_paused_duration += (now - self.auto_pause_start)
                    self.auto_pause_start = None

            self.last_exp_gain_time = now
            active_elapsed = self.get_elapsed_seconds()
            gained_mesos = max(0, (self.last_valid_mesos or 0) - (self.start_mesos or 0))
            self.history.append((now, active_elapsed, self.total_gained_exp, gained_mesos))

    def _check_auto_pause(self, now: float):
        if self.start_time and not self.is_paused and self.last_exp_gain_time:
            time_since = now - self.last_exp_gain_time
            if time_since >= self.idle_timeout_sec:
                if not self.is_auto_paused:
                    self.is_auto_paused = True
                    self.auto_pause_start = self.last_exp_gain_time + self.idle_timeout_sec

    def get_snapshot(self) -> TrackerSnapshot:
        elapsed = self.get_elapsed_seconds()
        elapsed_str = self._format_time_hms(elapsed)
        date_str = time.strftime("%b %d")

        max_exp = get_max_exp_for_level(self.level)
        current_exp = self.last_valid_raw_exp if self.last_valid_raw_exp is not None else 0
        current_pct = self.last_valid_pct

        if self.start_time is None or current_pct is None:
            return TrackerSnapshot(
                is_active=False,
                is_paused=self.is_paused,
                is_auto_paused=self.is_auto_paused,
                elapsed_seconds=0.0,
                elapsed_time_str="0:00:00",
                date_str=date_str,
                map_name=self.map_name,
                level=self.level,
                party=self.party,
                current_pct=current_pct,
                current_exp=current_exp,
                max_exp=max_exp,
                status_text="Waiting for game EXP..."
            )

        gained_exp = self.total_gained_exp
        gained_pct = self.total_gained_pct

        # Compute overall session rate (active after 2 seconds of grinding)
        effective_elapsed = max(2.0, elapsed) if gained_exp > 0 else elapsed
        overall_exp_hr = 0
        overall_pct_hr = 0.0
        if effective_elapsed > 0.0 and gained_exp > 0:
            overall_exp_hr = int((gained_exp / effective_elapsed) * 3600.0)
            overall_pct_hr = (gained_pct / effective_elapsed) * 3600.0

        # Rolling 5-minute window
        now = time.time()
        cutoff_5m = now - self.rolling_window_sec
        window = [h for h in self.history if h[0] >= cutoff_5m]

        exp_last_5min = gained_exp
        rolling_exp_hr = overall_exp_hr
        rolling_pct_hr = overall_pct_hr

        if len(window) >= 2:
            exp_span = window[-1][2] - window[0][2]
            active_time_span = window[-1][1] - window[0][1]
            exp_last_5min = max(0, exp_span)
            if active_time_span >= 10.0 and exp_span > 0:
                rolling_exp_hr = int((exp_span / active_time_span) * 3600.0)
                rolling_pct_hr = ((exp_span / max_exp) * 100.0 / active_time_span) * 3600.0

        # Rate Hold: never drop to 0 once EXP has been gained in this session
        hero_exp_hr = rolling_exp_hr if rolling_exp_hr > 0 else overall_exp_hr
        hero_pct_hr = rolling_pct_hr if rolling_pct_hr > 0.0 else overall_pct_hr

        if hero_exp_hr > 0:
            self._last_nonzero_exp_hr = hero_exp_hr
            self._last_nonzero_pct_hr = hero_pct_hr
        elif self._last_nonzero_exp_hr > 0:
            hero_exp_hr = self._last_nonzero_exp_hr
            hero_pct_hr = self._last_nonzero_pct_hr

        hero_eta = format_eta_str(self.level, current_exp, max_exp, hero_exp_hr)

        # Formatted Display Strings
        lvl_str = f" (+{self.level_ups} lvl)" if self.level_ups > 0 else ""
        gained_exp_disp = f"{format_number_k_m(gained_exp)}{lvl_str}"
        cur_exp_disp = f"{current_exp:,} [{current_pct:.2f}%]"

        # Meso Metrics
        gained_mesos = 0
        mesos_disp = "-- (+0)"
        mesos_hr = 0
        mesos_5min = 0

        if self.last_valid_mesos is not None:
            if self.start_mesos is not None:
                gained_mesos = max(0, self.last_valid_mesos - self.start_mesos)
            mesos_disp = f"{self.last_valid_mesos:,} (+{format_number_k_m(gained_mesos)})"

            if effective_elapsed > 0.0 and gained_mesos > 0:
                mesos_hr = int((gained_mesos / effective_elapsed) * 3600.0)

            if len(window) >= 2:
                meso_span = window[-1][3] - window[0][3]
                mesos_5min = max(0, meso_span)

        # Status text
        if self.is_paused:
            status = "Paused manually. (Shift+1 to resume)"
        elif self.is_auto_paused:
            if get_map_matcher().is_town(self.map_name):
                status = f"Paused in town ({self.map_name}). Resumes on next EXP gain."
            else:
                status = "Paused: no EXP for 15 seconds, so this time doesn't count. It carries on at your next EXP gain."
        else:
            death_note = f" · Died (-{format_number_k_m(self.last_death_loss)} EXP)" if self.deaths > 0 else ""
            status = f"{date_str} · {self.map_name} · Lv {self.level} · {self.party}{death_note}"

        return TrackerSnapshot(
            is_active=True,
            is_paused=self.is_paused,
            is_auto_paused=self.is_auto_paused,
            elapsed_seconds=elapsed,
            elapsed_time_str=elapsed_str,
            date_str=date_str,
            map_name=self.map_name,
            level=self.level,
            party=self.party,
            current_pct=current_pct,
            start_pct=self.start_pct,
            gained_pct=round(gained_pct, 2),
            current_exp=current_exp,
            max_exp=max_exp,
            gained_exp=gained_exp,
            level_ups=self.level_ups,
            hero_exp_per_hr=hero_exp_hr,
            hero_eta_str=hero_eta,
            exp_last_5min=exp_last_5min,
            pct_per_hour=round(hero_pct_hr, 2),
            gained_exp_display=gained_exp_disp,
            current_exp_display=cur_exp_disp,
            current_mesos=self.last_valid_mesos,
            start_mesos=self.start_mesos,
            gained_mesos=gained_mesos,
            mesos_display=mesos_disp,
            mesos_per_hr=mesos_hr,
            mesos_5min=mesos_5min,
            status_text=status
        )
