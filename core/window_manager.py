import ctypes
import os
from typing import Optional, Dict, Any, List
import win32gui
import win32process
import win32con

# Enable per-monitor DPI awareness to prevent pixel coordinate scaling distortion
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def ensure_desktop_access():
    """Ensure process has thread desktop access on Windows."""
    try:
        import win32service
        hwinsta = win32service.OpenWindowStation('WinSta0', False, 0x2000000)
        hwinsta.SetProcessWindowStation()
        hdesk = win32service.OpenDesktop('Default', 0, False, 0x2000000)
        hdesk.SetThreadDesktop()
    except Exception:
        pass


class WindowManager:
    """
    Locates and tracks the position of the MapleStory game window on the desktop.
    Automatically recalculates coordinates when the window is moved or resized.
    """

    DEFAULT_TITLES = ["maplestory", "maple", "classic world"]
    DEFAULT_PROCESSES = ["maplestory.exe"]
    EXCLUDED_CLASSES = {
        "chrome_widgetwin_1",
        "chrome_widgetwin_0",
        "mozillawindowclass",
        "applicationframewindow",
        "cabinetwclass",
        "tktoplevel",
    }
    EXCLUDED_KEYWORDS = (
        "tracker",
        "preview",
        "discord",
        "chrome",
        "microsoft edge",
        "firefox",
        "brave",
        "opera",
        "visual studio",
        "github",
        "youtube",
    )

    def __init__(self, target_titles: Optional[List[str]] = None, target_processes: Optional[List[str]] = None):
        ensure_desktop_access()
        self.target_titles = [t.lower() for t in (target_titles or self.DEFAULT_TITLES)]
        self.target_processes = [p.lower() for p in (target_processes or self.DEFAULT_PROCESSES)]
        self.hwnd: Optional[int] = None
        self.last_title: str = ""

    def find_window(self) -> Optional[int]:
        """Scan active desktop windows for MapleStory client, prioritizing MapleStoryClass and exact title matches."""
        ensure_desktop_access()
        best_candidate = None  # (priority_score, hwnd, title)

        def enum_cb(hwnd, _):
            nonlocal best_candidate
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return

            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return

            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            if w < 300 or h < 300:
                return

            title_lower = title.lower()
            if any(kw in title_lower for kw in self.EXCLUDED_KEYWORDS):
                return

            try:
                cls_name = win32gui.GetClassName(hwnd).strip().lower()
            except Exception:
                cls_name = ""

            if cls_name in self.EXCLUDED_CLASSES:
                return

            score = 0
            # Priority 1: Native MapleStory window class
            if cls_name == "maplestoryclass":
                score = 100
            # Priority 2: Exact window title "MapleStory" or "MapleStory Classic World"
            elif title_lower in ("maplestory", "maplestory classic world"):
                score = 90
            # Priority 3: Substring match on target titles (for custom/test windows)
            elif any(t in title_lower for t in self.target_titles):
                score = 50

            if score > 0:
                if best_candidate is None or score > best_candidate[0]:
                    best_candidate = (score, hwnd, title)

        win32gui.EnumWindows(enum_cb, None)

        if best_candidate is not None:
            _, found_hwnd, found_title = best_candidate
            self.hwnd = found_hwnd
            self.last_title = found_title
            return found_hwnd

        # If previous hwnd is still valid and visible, keep it
        if self.hwnd and win32gui.IsWindow(self.hwnd) and win32gui.IsWindowVisible(self.hwnd):
            return self.hwnd

        self.hwnd = None
        return None

    def get_window_geometry(self) -> Optional[Dict[str, int]]:
        """
        Returns the exact client area rectangle in absolute screen coordinates:
        {'left': int, 'top': int, 'width': int, 'height': int, 'title': str}
        """
        hwnd = self.find_window()
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None

        try:
            # Client area (the playable game screen without window borders/title bar)
            client_rect = win32gui.GetClientRect(hwnd) # (left, top, right, bottom)
            client_w = client_rect[2] - client_rect[0]
            client_h = client_rect[3] - client_rect[1]

            # Convert (0, 0) client coordinate to absolute screen coordinate
            screen_pt = win32gui.ClientToScreen(hwnd, (0, 0))
            client_x = screen_pt[0]
            client_y = screen_pt[1]

            return {
                "hwnd": hwnd,
                "title": self.last_title or win32gui.GetWindowText(hwnd),
                "left": client_x,
                "top": client_y,
                "width": client_w,
                "height": client_h,
            }
        except Exception:
            return None

