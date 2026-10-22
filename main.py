import sys
import time
import threading
import argparse

# Ensure immediate unbuffered console output
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from core.window_manager import WindowManager
from core.capture import ScreenGrabber
from core.ocr_pipeline import OCREngine
from core.tracker import ExpTracker
from core.session_storage import SessionStorage
from core.map_matcher import get_map_matcher
from ui.overlay import OverlayHUD


class TrackingApp:
    def __init__(self, cli_mode: bool = False):
        self.cli_mode = cli_mode
        self.running = True

        self.storage = SessionStorage()
        self.wm = WindowManager()
        self.grabber = ScreenGrabber(window_manager=self.wm)
        self.ocr = OCREngine()
        self.tracker = ExpTracker(idle_timeout_sec=15.0)

        self._tick_counter = 0
        self._active_hunting_map = None
        self._money_window_until = 0.0
        self._last_meso_frame = None

        self.hud = None if cli_mode else OverlayHUD(
            storage=self.storage,
            on_reset=self._handle_reset,
            on_pause=self.tracker.toggle_pause,
            on_calibrate_mesos=self.grabber.set_meso_box,
            on_update_meta=self._handle_update_meta
        )

    def _handle_update_meta(self, map_name: str, level: int, party: str):
        self.tracker.set_map(map_name)
        self.tracker.set_level(level)
        self.tracker.set_party(party)

    def _handle_reset(self, save_to_log: bool = True):
        snap = self.tracker.get_snapshot()
        # Save previous completed session to storage if it had meaningful activity
        if save_to_log and snap.elapsed_seconds >= 15.0 and (snap.gained_exp > 0 or snap.gained_mesos > 0):
            time_str = f"{int(snap.elapsed_seconds // 60)}m" if snap.elapsed_seconds >= 60 else f"{int(snap.elapsed_seconds)}s"
            record = {
                "date": snap.date_str or time.strftime("%b %d"),
                "map": snap.map_name,
                "lv": snap.level,
                "party": snap.party,
                "time": time_str,
                "exp_hr": snap.hero_exp_per_hr,
                "mesos_hr": snap.mesos_per_hr,
                "gained_exp": snap.gained_exp,
                "gained_mesos": snap.gained_mesos,
                "timestamp": time.time()
            }
            self.storage.add_session(record)
            print(f"[TrackingApp] Saved session log: {record['map']} (Lv {record['lv']}) - {record['exp_hr']:,} EXP/hr")

        self.tracker.reset_session()

    def tracking_worker(self):
        """Worker loop running capture -> OCR -> tracking."""
        print("[TrackingApp] Advanced tracking loop active.")

        while self.running:
            try:
                self._tick_counter += 1

                # 1. Grab Level Badge frame directly from bottom status bar
                lv_frame = self.grabber.get_level_frame()
                detected_level = None
                if lv_frame is not None:
                    detected_level = self.ocr.extract_level(lv_frame)

                # 2. Grab EXP frame
                exp_frame, exp_info = self.grabber.get_exp_frame()
                pct = None
                raw_exp = None
                raw_exp_str = ""

                if exp_frame is not None:
                    ocr_res = self.ocr.extract_exp(exp_frame)
                    raw_exp_str = ocr_res.get("raw_text", "")
                    pct = ocr_res.get("percentage")
                    raw_exp = ocr_res.get("current_exp")

                # 3. Grab Meso frame (manual calibration or auto-detected from inventory)
                meso_frame = self.grabber.get_mesos_frame()
                meso_val = None
                detected_party = None

                # 4. Periodic 5-second scan: Map Name + Auto Inventory Meso Box + Party HP Bars
                detected_map = None
                if self._tick_counter == 1 or self._tick_counter % 5 == 0:
                    hud_rect = self.hud.get_hud_rect() if self.hud else None
                    map_frame = self.grabber.get_map_frame(exclude_rect=hud_rect)
                    if map_frame is not None:
                        detected_map = self.ocr.extract_map_name(map_frame)

                    auto_meso_crop, detected_party, money_win = self.grabber.scan_window_extras(exclude_rect=hud_rect)
                    if money_win is not None:
                        # Shop, Storage, or Trade is open: ignore Meso changes for 8 seconds
                        self._money_window_until = time.time() + 8.0
                    elif meso_frame is None and auto_meso_crop is not None:
                        meso_frame = auto_meso_crop

                if meso_frame is not None and time.time() >= self._money_window_until:
                    meso_val = self.ocr.extract_mesos(meso_frame)
                    self._last_meso_frame = meso_frame

                # Automatic Map-Change Session Split:
                # If the player moves to a different hunting map after >= 60s of farming, save the old map's run and start fresh
                if detected_map and not get_map_matcher().is_town(detected_map):
                    if (
                        self._active_hunting_map
                        and detected_map != self._active_hunting_map
                        and self.tracker.get_elapsed_seconds() >= 60.0
                        and self.tracker.total_gained_exp > 0
                    ):
                        save_flag = (not self.hud.is_dont_log) if self.hud else True
                        self._handle_reset(save_to_log=save_flag)
                        if self.hud:
                            self.hud.refresh_table()
                    self._active_hunting_map = detected_map

                # 5. Update Tracker Engine (passing image-detected level, raw_exp, pct, mesos, map, party)
                snapshot = self.tracker.update(
                    pct=pct,
                    raw_exp=raw_exp,
                    mesos=meso_val,
                    map_name=detected_map,
                    detected_level=detected_level,
                    party=detected_party
                )

                if self.cli_mode:
                    if snapshot.current_pct is not None:
                        print(f"[{snapshot.date_str} | {snapshot.map_name}] Lv {snapshot.level} | "
                              f"EXP/hr: {snapshot.hero_exp_per_hr:,} | "
                              f"{snapshot.hero_eta_str} | "
                              f"Cur: {snapshot.current_exp_display} | "
                              f"Gained: {snapshot.gained_exp_display} | "
                              f"Time: {snapshot.elapsed_time_str}")
                    else:
                        print(f"[TrackingApp] Searching for MapleStory client ({snapshot.status_text})")
                else:
                    if self.hud:
                        self.hud.update_stats(
                            snapshot=snapshot,
                            lv_frame=lv_frame,
                            exp_frame=exp_frame,
                            meso_frame=meso_frame if meso_frame is not None else self._last_meso_frame,
                            raw_exp_text=raw_exp_str
                        )

                # 1 second loop interval
                time.sleep(1.0)

            except Exception as e:
                print(f"[TrackingApp] Error: {e}")
                time.sleep(1.0)

    def run(self):
        worker = threading.Thread(target=self.tracking_worker, daemon=True)
        worker.start()

        if self.cli_mode:
            print("Running in CLI mode. Press Ctrl+C to stop.")
            try:
                while True:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.running = False
        else:
            try:
                self.hud.mainloop()
            finally:
                self.running = False


def main():
    parser = argparse.ArgumentParser(description="MapleStory Classic EXP & Meso Tracker")
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode without GUI overlay")
    args = parser.parse_args()

    app = TrackingApp(cli_mode=args.cli)
    app.run()


if __name__ == "__main__":
    main()
