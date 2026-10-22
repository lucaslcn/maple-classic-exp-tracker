import unittest
import os
import shutil
import glob
import time
import numpy as np
import cv2
from core.exp_table import (
    get_max_exp_for_level,
    calculate_raw_exp,
    detect_level_from_exp,
    format_number_k_m,
    format_eta_str
)
from core.session_storage import SessionStorage
from core.tracker import ExpTracker
from core.ocr_pipeline import OCREngine
from core.capture import ScreenGrabber
from core.map_matcher import get_map_matcher


class TestAdvancedTracker(unittest.TestCase):

    def setUp(self):
        self.test_data_dir = "data_test_tmp"
        os.makedirs(self.test_data_dir, exist_ok=True)
        self.storage = SessionStorage(data_dir=self.test_data_dir)
        self.tracker = ExpTracker(idle_timeout_sec=2.0)
        self.ocr = OCREngine()

    def tearDown(self):
        if os.path.exists(self.test_data_dir):
            shutil.rmtree(self.test_data_dir)

    def test_real_screenshots_level_exp_and_map(self):
        """Verify direct image-based Level, EXP, and Map extraction across both 3440x1440 (2x) and 1920x1080 (1x) screenshots."""
        files = sorted(glob.glob(r'C:\Nexon\Library\maplestorycw\appdata\Maple_A_*.jpg'))[-5:]
        expected = [
            (52, 42, 0.01, "Hidden Street : Monkey Forest I"),
            (53, 83, 0.01, "Victoria Road : The Entrance of Golem's Temple"),
            (54, 118, 0.01, "Dungeon : Sleepy Dungeon III"),
            (55, 79, 0.01, "Dungeon : Sleepy Dungeon III"),
            (56, 63, 0.01, "Dungeon : Sleepy Dungeon III"),
        ]
        for f, (exp_lv, exp_raw, exp_pct, exp_map) in zip(files, expected):
            img = cv2.imread(f)
            h, w, _ = img.shape
            s, vp_left = ScreenGrabber._get_scale_and_viewport_left(w, h)
            cx = w // 2
            lv_crop = img[h - 32 * s:h - 12 * s, cx - 358 * s:cx - 320 * s]
            exp_crop = img[h - 38 * s:h - 12 * s, cx + 35 * s:cx + 225 * s]
            map_crop = img[20 * s:70 * s, vp_left + 42 * s:vp_left + 267 * s]

            lv = self.ocr.extract_level(lv_crop)
            exp_res = self.ocr.extract_exp(exp_crop)
            map_name = self.ocr.extract_map_name(map_crop)

            self.assertEqual(lv, exp_lv, f"Level mismatch on {f}")
            self.assertEqual(exp_res["current_exp"], exp_raw, f"Raw EXP mismatch on {f}")
            self.assertAlmostEqual(exp_res["percentage"], exp_pct, places=2)
            self.assertEqual(map_name, exp_map, f"Map mismatch on {f}")

    def test_anti_spike_and_anti_zero_drop(self):
        """
        Verify that:
        1. A misread percentage (0.10% with raw_exp=440,101) is reconciled to 42.69% and does NOT jump level to 84.
        2. A single-frame dropped digit in raw_exp (40,101 instead of 440,101) does NOT reset EXP/hr to 0.
        """
        # Start at Level 57, 434,600 EXP (42.15%)
        snap1 = self.tracker.update(pct=42.15, raw_exp=434600, detected_level=57)
        self.assertEqual(snap1.level, 57)

        # Advance time slightly and gain 5,501 EXP -> 440,101 (42.69%)
        self.tracker.start_time -= 60.0
        snap2 = self.tracker.update(pct=42.69, raw_exp=440101, detected_level=57)
        self.assertEqual(snap2.level, 57)
        self.assertEqual(snap2.gained_exp, 5501)
        self.assertGreater(snap2.hero_exp_per_hr, 300000)
        rate_before = snap2.hero_exp_per_hr

        # Frame 3: Corrupted pct=0.10% while raw_exp=440,101 -> should reconcile pct to 42.69% and keep Lv 57!
        snap3 = self.tracker.update(pct=0.10, raw_exp=440101, detected_level=None)
        self.assertEqual(snap3.level, 57)
        self.assertAlmostEqual(snap3.current_pct, 42.69, places=2)
        self.assertEqual(snap3.current_exp, 440101)

        # Frame 4: Dropped digit in raw_exp=40,101 while pct=42.69% -> should keep 440,101 and NOT drop rate to 0!
        snap4 = self.tracker.update(pct=42.69, raw_exp=40101, detected_level=57)
        self.assertEqual(snap4.current_exp, 440101)
        self.assertEqual(snap4.gained_exp, 5501)
        self.assertGreater(snap4.hero_exp_per_hr, 0)

    def test_dynamic_image_level_up_without_lock(self):
        """Verify that when the player levels up from 57 to 58 on the LV. badge, level updates automatically."""
        self.tracker.update(pct=99.50, raw_exp=1025880, detected_level=57)
        self.tracker.start_time -= 30.0
        snap = self.tracker.update(pct=0.50, raw_exp=5438, detected_level=58)
        self.assertEqual(snap.level, 58)
        self.assertEqual(snap.level_ups, 1)
        # Gained = (1,031,036 - 1,025,880) + 5,438 = 10,594 EXP
        self.assertEqual(snap.gained_exp, 10594)
        self.assertIn("(+1 lvl)", snap.gained_exp_display)

    def test_ocr_synthetic_fallback(self):
        img = np.zeros((30, 220, 3), dtype=np.uint8)
        cv2.putText(img, "EXP 440.101 [42.68%]", (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        res = self.ocr.extract_exp(img)
        self.assertTrue(res["success"])
        self.assertEqual(res["percentage"], 42.68)
        self.assertEqual(res["current_exp"], 440101)

    def test_map_matcher_fuzzy_and_town_detection(self):
        matcher = get_map_matcher()
        self.assertEqual(matcher.snap_map_name("Cungeon : Sleapy Dungeon lV"), "Dungeon : Sleepy Dungeon IV")
        self.assertEqual(
            matcher.snap_map_name("Victoria Road : The Entrance of Golem's Temnle"),
            "Victoria Road : The Entrance of Golem's Temple"
        )
        self.assertTrue(matcher.is_town("Dungeon : Sleepywood"))
        self.assertFalse(matcher.is_town("Dungeon : Sleepy Dungeon IV"))

    def test_death_exp_loss_protection(self):
        # Start at Level 57, 48.00% (494,897) -> gain to 50.00% (515,518)
        self.tracker.update(pct=48.00, raw_exp=494897, detected_level=57)
        self.tracker.start_time -= 60.0
        snap1 = self.tracker.update(pct=50.00, raw_exp=515518, detected_level=57)
        self.assertEqual(snap1.gained_exp, 20621)
        rate_before = snap1.hero_exp_per_hr

        # Player dies and loses 5% EXP -> drops to 45.00% (463,966) for 2 consecutive frames
        self.tracker.update(pct=45.00, raw_exp=463966, detected_level=57)
        snap_death = self.tracker.update(pct=45.00, raw_exp=463966, detected_level=57)
        self.assertEqual(self.tracker.deaths, 1)
        self.assertEqual(snap_death.gained_exp, 20621)
        self.assertEqual(snap_death.current_exp, 463966)
        self.assertGreaterEqual(snap_death.hero_exp_per_hr, rate_before * 0.9)

        # Next kill adds +1,031 EXP from 463,966 -> 464,997 (45.10%)
        snap_after = self.tracker.update(pct=45.10, raw_exp=464997, detected_level=57)
        self.assertEqual(snap_after.gained_exp, 20621 + 1031)

    def test_auto_meso_box_and_party_detection(self):
        files = sorted(glob.glob(r'C:\Nexon\Library\maplestorycw\appdata\Maple_A_*.jpg'))
        meso_file = [x for x in files if "261006_212829" in x]
        if meso_file:
            bgr = cv2.imread(meso_file[0])
            box = ScreenGrabber.find_mesos_field_in_frame(bgr, gh=14)
            self.assertIsNotNone(box)
            x, y, w, h = box
            val = self.ocr.extract_mesos(bgr[y:y + h, x:x + w])
            self.assertEqual(val, 1274)

        party_file = [x for x in files if "261020_004637" in x]
        if party_file:
            bgr_p = cv2.imread(party_file[0])
            party_str = ScreenGrabber.detect_party_in_frame(bgr_p, gh=7)
            self.assertEqual(party_str, "4ppl")


if __name__ == "__main__":
    unittest.main()
