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

    def __init__(self, target_titles: Optional[List[str]] = None, target_processes: Optional[List[str]] = None):
        ensure_desktop_access()
        self.target_titles = [t.lower() for t in (target_titles or self.DEFAULT_TITLES)]
        self.target_processes = [p.lower() for p in (target_processes or self.DEFAULT_PROCESSES)]
        self.hwnd: Optional[int] = None
        self.last_title: str = ""

    def find_window(self) -> Optional[int]:
        """Scan active desktop windows for MapleStory client."""
        ensure_desktop_access()
        found_hwnd = None
        found_title = ""

        def enum_cb(hwnd, _):
            nonlocal found_hwnd, found_title
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
            # Never match our own tracker or preview windows
            if "tracker" in title_lower or "preview" in title_lower:
                return

            # Match title
            if any(t in title_lower for t in self.target_titles):
                found_hwnd = hwnd
                found_title = title
                return

            # Check process name if title doesn't directly mention it
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                # Check with toolhelp or kernel if needed
            except Exception:
                pass

        win32gui.EnumWindows(enum_cb, None)

        if found_hwnd:
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

