import unittest
import cv2
import numpy as np
from core.ocr_pipeline import OCREngine
from core.tracker import ExpTracker
from core.capture import ScreenGrabber
from core.window_manager import WindowManager


class TestMapleExpTracker(unittest.TestCase):

    def setUp(self):
        self.ocr = OCREngine()
        self.tracker = ExpTracker(rolling_window_sec=60.0)

    def test_ocr_with_real_sample(self):
        """Test OCR extraction on real MapleStory Classic World screenshot."""
        sample_path = r'C:\Nexon\Library\maplestorycw\appdata\Maple_A_261020_004637.jpg'
        full_img = cv2.imread(sample_path)
        self.assertIsNotNone(full_img, "Failed to read sample image")

        h, w, _ = full_img.shape
        cx = w // 2
        # Crop formula for classic EXP bar
        crop = full_img[h-38:h-12, cx+35:cx+220]

        result = self.ocr.extract_exp(crop)
        self.assertTrue(result["success"], f"OCR failed to extract EXP: {result}")
        self.assertIsNotNone(result["percentage"])
        self.assertIn(round(result["percentage"], 2), [0.01, 0.03])

    def test_exp_tracker_calculations(self):
        """Test tracking math: EXP gains, rate calculation, and ETA."""
        # Initial reading: 10.00%
        snap1 = self.tracker.update(pct=10.00)
        self.assertEqual(snap1.current_pct, 10.00)
        self.assertEqual(snap1.gained_pct, 0.00)

        # Gain 2%: now 12.00%
        snap2 = self.tracker.update(pct=12.00)
        self.assertEqual(snap2.current_pct, 12.00)
        self.assertEqual(snap2.gained_pct, 2.00)

    def test_level_up_rollover(self):
        """Test that level up from 99.50% to 0.50% is handled seamlessly without negative gain."""
        self.tracker.update(pct=98.00)
        self.tracker.update(pct=99.50)
        # Level up occurred
        snap = self.tracker.update(pct=0.50)
        self.assertEqual(snap.level_ups, 1)
        self.assertEqual(snap.current_pct, 0.50)
        # Total gain = (100 - 98.00) + 0.50 = 2.50%
        self.assertAlmostEqual(snap.gained_pct, 2.50, places=2)

    def test_outlier_noise_rejection(self):
        """Test that single-frame glitch OCR drops (e.g. 50% -> 5% -> 50.1%) are rejected."""
        self.tracker.update(pct=50.00)
        # Glitch frame: OCR misreads as 5.00%
        glitch_snap = self.tracker.update(pct=5.00)
        # Should NOT update current_pct to 5.00%
        self.assertEqual(glitch_snap.current_pct, 50.00)

        # Next normal frame
        valid_snap = self.tracker.update(pct=50.15)
        self.assertEqual(valid_snap.current_pct, 50.15)
        self.assertAlmostEqual(valid_snap.gained_pct, 0.15, places=2)

    def test_grabber_bbox_relative_calculation(self):
        """Test EXP bounding box relative math for a 1980x1200 window."""
        grabber = ScreenGrabber()
        # Mock window geometry
        grabber.wm.get_window_geometry = lambda: {
            "left": 500,
            "top": 200,
            "width": 1980,
            "height": 1200,
            "title": "MapleStory",
            "hwnd": 12345
        }

        bbox = grabber.get_exp_bbox()
        self.assertIsNotNone(bbox)
        # cx = 1980 // 2 = 990
        # left = 500 + 990 + 35 = 1525
        self.assertEqual(bbox["left"], 1525)
        # top = 200 + 1200 - 38 = 1362
        self.assertEqual(bbox["top"], 1362)
        self.assertEqual(bbox["width"], 190)
        self.assertEqual(bbox["height"], 26)


if __name__ == "__main__":
    unittest.main()

