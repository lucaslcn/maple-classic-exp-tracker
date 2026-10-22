import tkinter as tk
from tkinter import ttk
import ctypes
import win32gui
import customtkinter as ctk
import cv2
from PIL import Image
from typing import Optional, Callable, Tuple
from core.tracker import TrackerSnapshot
from core.session_storage import SessionStorage
from ui.area_selector import AreaSelector


class CapturePreviewWindow(ctk.CTkToplevel):
    """Auxiliary window to preview live camera feeds for Level, EXP, Map, and Meso regions."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("MapleStory Tracker - Live Capture Preview")
        self.geometry("500x440")
        self.attributes("-topmost", True)
        self.resizable(False, False)

        self.label_info = ctk.CTkLabel(
            self,
            text="Live Image Sensors (Level Badge, EXP Bar, Map, Mesos):",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.label_info.pack(pady=6)

        # Level + Map row
        top_feeds = ctk.CTkFrame(self, fg_color="transparent")
        top_feeds.pack(fill="x", padx=12, pady=2)

        self.lv_frame_lbl = ctk.CTkLabel(top_feeds, text="Waiting for LV...", width=100, height=44)
        self.lv_frame_lbl.pack(side="left", padx=8)
        self.lbl_lv_txt = ctk.CTkLabel(top_feeds, text="Level Read: --", text_color="#4ade80", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_lv_txt.pack(side="left", padx=8)

        # EXP feed
        self.exp_frame_lbl = ctk.CTkLabel(self, text="Waiting for EXP bar...", width=400, height=50)
        self.exp_frame_lbl.pack(pady=4)

        self.lbl_exp_txt = ctk.CTkLabel(self, text="EXP Read: --", text_color="#38bdf8", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_exp_txt.pack(pady=2)

        # Map feed
        self.lbl_map_txt = ctk.CTkLabel(self, text="Map Read: --", text_color="#cbd5e1", font=ctk.CTkFont(size=11))
        self.lbl_map_txt.pack(pady=2)

        # Meso feed
        self.meso_frame_lbl = ctk.CTkLabel(self, text="Waiting for Meso box (use Select Area)...", width=250, height=40)
        self.meso_frame_lbl.pack(pady=4)

        self.lbl_meso_txt = ctk.CTkLabel(self, text="Mesos Read: --", text_color="#fbbf24")
        self.lbl_meso_txt.pack(pady=2)

        self.btn_close = ctk.CTkButton(self, text="Close", width=100, command=self.destroy)
        self.btn_close.pack(pady=8)

    def update_feeds(
        self,
        lv_frame,
        exp_frame,
        meso_frame,
        lv_val: Optional[int],
        exp_text: str,
        map_text: str,
        meso_val: Optional[int]
    ):
        if lv_frame is not None:
            try:
                res = cv2.resize(lv_frame, (76, 40), interpolation=cv2.INTER_NEAREST)
                pil_img = Image.fromarray(cv2.cvtColor(res, cv2.COLOR_BGR2RGB))
                ctk_img = ctk.CTkImage(pil_img, size=(76, 40))
                self.lv_frame_lbl.configure(image=ctk_img, text="")
                self.lv_frame_lbl.image = ctk_img
                self.lbl_lv_txt.configure(text=f"Level Image Read: Lv {lv_val}" if lv_val else "Level Read: --")
            except Exception:
                pass

        if exp_frame is not None:
            try:
                res = cv2.resize(exp_frame, (380, 52), interpolation=cv2.INTER_NEAREST)
                pil_img = Image.fromarray(cv2.cvtColor(res, cv2.COLOR_BGR2RGB))
                ctk_img = ctk.CTkImage(pil_img, size=(380, 52))
                self.exp_frame_lbl.configure(image=ctk_img, text="")
                self.exp_frame_lbl.image = ctk_img
                self.lbl_exp_txt.configure(text=f"EXP OCR: {exp_text}")
            except Exception:
                pass

        self.lbl_map_txt.configure(text=f"Map: {map_text}")

        if meso_frame is not None:
            try:
                h, w = meso_frame.shape[:2]
                disp_w = min(280, max(40, w))
                disp_h = min(56, max(20, h))
                res = cv2.resize(meso_frame, (disp_w, disp_h), interpolation=cv2.INTER_NEAREST)
                pil_img = Image.fromarray(cv2.cvtColor(res, cv2.COLOR_BGR2RGB))
                ctk_img = ctk.CTkImage(pil_img, size=(disp_w, disp_h))
                self.meso_frame_lbl.configure(image=ctk_img, text="")
                self.meso_frame_lbl.image = ctk_img
                self.lbl_meso_txt.configure(text=f"Mesos Read: {meso_val:,}" if meso_val is not None else "Mesos: Not detected")
            except Exception:
                pass


class EditSessionDialog(ctk.CTkToplevel):
    """Simple modal to edit Map or Party name for a historical log entry."""

    def __init__(self, parent, current_map: str, current_party: str, on_save: Callable[[str, str], None]):
        super().__init__(parent)
        self.title("Edit Session Record")
        self.geometry("320x220")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.on_save = on_save

        ctk.CTkLabel(self, text="Map Name:", font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(12, 2), padx=16, anchor="w")
        self.entry_map = ctk.CTkEntry(self, width=280)
        self.entry_map.insert(0, current_map)
        self.entry_map.pack(pady=2, padx=16)

        ctk.CTkLabel(self, text="Party (e.g. Solo, 5ppl):", font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(8, 2), padx=16, anchor="w")
        self.entry_party = ctk.CTkEntry(self, width=280)
        self.entry_party.insert(0, current_party)
        self.entry_party.pack(pady=2, padx=16)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=16, fill="x", padx=16)

        ctk.CTkButton(btn_row, text="Cancel", width=80, fg_color="#334155", command=self.destroy).pack(side="left")
        ctk.CTkButton(btn_row, text="Save", width=80, fg_color="#0284c7", command=self._save).pack(side="right")

    def _save(self):
        new_map = self.entry_map.get().strip()
        new_party = self.entry_party.get().strip()
        self.on_save(new_map, new_party)
        self.destroy()


class OverlayHUD(ctk.CTk):
    """
    Two-pane MapleStory grinding tracker HUD matching the classic gold-standard layout.
    """

    def __init__(
        self,
        storage: Optional[SessionStorage] = None,
        on_reset: Optional[Callable] = None,
        on_pause: Optional[Callable] = None,
        on_calibrate_mesos: Optional[Callable[[int, int, int, int], None]] = None,
        on_update_meta: Optional[Callable[[str, int, str], None]] = None
    ):
        super().__init__()

        self.storage = storage or SessionStorage()
        self.on_reset_callback = on_reset
        self.on_pause_callback = on_pause
        self.on_calibrate_mesos_callback = on_calibrate_mesos
        self.on_update_meta_callback = on_update_meta

        self.preview_win: Optional[CapturePreviewWindow] = None
        self.is_right_pane_open: bool = True
        self.is_dont_log: bool = False

        # Appearance & Properties
        ctk.set_appearance_mode("Dark")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color="#121316")

        # Initial Dimensions: Placed at +420+60 by default so it doesn't cover the top-left minimap
        self.left_pane_width = 360
        self.right_pane_width = 520
        self.total_width = 880
        self.total_height = 430
        self.geometry(f"{self.total_width}x{self.total_height}+420+60")

        # Mouse Dragging state
        self._drag_x = 0
        self._drag_y = 0
        self._hotkey_prev = {1: False, 2: False, 3: False, 4: False}

        self._build_ui()
        self._load_table_sessions()
        self.after(150, self._poll_hotkeys)

    def _poll_hotkeys(self):
        """
        Polls Shift+1..4 when MapleStory or this Overlay is the active foreground window:
        - Shift+1: Pause / Resume
        - Shift+2: Save & Reset
        - Shift+3: Toggle Don't Log
        - Shift+4: Collapse / Expand Right Log Pane
        """
        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            fg_title = (win32gui.GetWindowText(fg_hwnd) or "").lower()
            if "maple" in fg_title or "tracker" in fg_title:
                user32 = ctypes.windll.user32
                shift_down = bool(user32.GetAsyncKeyState(0x10) & 0x8000)
                vk_map = {1: 0x31, 2: 0x32, 3: 0x33, 4: 0x34}
                for k, vk in vk_map.items():
                    is_down = shift_down and bool(user32.GetAsyncKeyState(vk) & 0x8000)
                    if is_down and not self._hotkey_prev[k]:
                        if k == 1:
                            self._handle_pause()
                        elif k == 2:
                            self._handle_reset()
                        elif k == 3:
                            self._toggle_dont_log()
                        elif k == 4:
                            self._toggle_right_pane()
                    self._hotkey_prev[k] = is_down
            else:
                for k in self._hotkey_prev:
                    self._hotkey_prev[k] = False
        except Exception:
            pass
        if self.winfo_exists():
            self.after(150, self._poll_hotkeys)

    def refresh_table(self):
        self.after(0, self._load_table_sessions)

    def get_hud_rect(self) -> Tuple[int, int, int, int]:
        """Returns current (x, y, width, height) of the HUD window on screen."""
        try:
            return (self.winfo_x(), self.winfo_y(), self.winfo_width(), self.winfo_height())
        except Exception:
            return (0, 0, 0, 0)

    def _build_ui(self):
        # 1. Custom Drag Header Bar across entire top
        self.header_bar = ctk.CTkFrame(self, fg_color="#18191d", corner_radius=0, height=28)
        self.header_bar.pack(fill="x", side="top")

        self.header_title = ctk.CTkLabel(
            self.header_bar,
            text="🍁 MapleStory Classic EXP Tracker",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#94a3b8"
        )
        self.header_title.pack(side="left", padx=10)

        self.btn_close = ctk.CTkButton(
            self.header_bar,
            text="✕",
            width=26,
            height=20,
            fg_color="transparent",
            hover_color="#ef4444",
            command=self.destroy
        )
        self.btn_close.pack(side="right", padx=4)

        for w in (self.header_bar, self.header_title):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        # 2. Main Two-Pane Container
        self.body_container = ctk.CTkFrame(self, fg_color="transparent")
        self.body_container.pack(fill="both", expand=True)

        self._build_left_pane()
        self._build_right_pane()

    def _build_left_pane(self):
        self.left_pane = ctk.CTkFrame(self.body_container, fg_color="#151619", width=self.left_pane_width, corner_radius=0)
        self.left_pane.pack(side="left", fill="both", expand=False)
        self.left_pane.pack_propagate(False)

        # Top row: "EXP / hr" title, Settings gear, Collapse "<" button
        top_row = ctk.CTkFrame(self.left_pane, fg_color="transparent", height=30)
        top_row.pack(fill="x", padx=14, pady=(8, 2))

        self.lbl_title_metric = ctk.CTkLabel(
            top_row,
            text="EXP / hr",
            font=ctk.CTkFont(size=13, weight="normal"),
            text_color="#94a3b8"
        )
        self.lbl_title_metric.pack(side="left")

        self.btn_collapse = ctk.CTkButton(
            top_row,
            text="<",
            width=22,
            height=20,
            fg_color="transparent",
            hover_color="#262930",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94a3b8",
            command=self._toggle_right_pane
        )
        self.btn_collapse.pack(side="right", padx=(4, 0))

        self.btn_settings = ctk.CTkButton(
            top_row,
            text="⚙",
            width=22,
            height=20,
            fg_color="transparent",
            hover_color="#262930",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8",
            command=self._open_meta_dialog
        )
        self.btn_settings.pack(side="right")

        # Hero Metric Banner: Big bold yellow EXP / hr
        self.lbl_hero_exp = ctk.CTkLabel(
            self.left_pane,
            text="0",
            font=ctk.CTkFont(size=36, weight="bold"),
            text_color="#facc15"
        )
        self.lbl_hero_exp.pack(anchor="w", padx=14, pady=(0, 0))

        # Hero Subtitle: "Lv 58 in 2 h 25 min"
        self.lbl_hero_sub = ctk.CTkLabel(
            self.left_pane,
            text="Lv -- in -- h -- min",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#fde047"
        )
        self.lbl_hero_sub.pack(anchor="w", padx=14, pady=(0, 6))

        # Metrics Table
        self.metrics_frame = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        self.metrics_frame.pack(fill="x", padx=14, pady=2)
        self.metrics_frame.columnconfigure(0, weight=1)
        self.metrics_frame.columnconfigure(1, weight=1)

        self.metrics_rows = {}
        row_defs = [
            ("Last 5 min", "val_5min", "0"),
            ("% / hr", "val_pct_hr", "0.00%"),
            ("Gained", "val_gained_exp", "0 (+0 lvl)"),
            ("Current", "val_current_exp", "0 [0.00%]"),
            ("Mesos", "val_mesos", "-- (+0)"),
            ("Mesos / hr", "val_mesos_hr", "0"),
            ("Mesos / 5 min", "val_mesos_5min", "0"),
            ("Elapsed", "val_elapsed", "0:00:00")
        ]

        for i, (label_text, key, def_val) in enumerate(row_defs):
            lbl_name = ctk.CTkLabel(
                self.metrics_frame,
                text=label_text,
                font=ctk.CTkFont(size=12),
                text_color="#94a3b8",
                anchor="w"
            )
            lbl_name.grid(row=i, column=0, sticky="w", pady=1)

            lbl_val = ctk.CTkLabel(
                self.metrics_frame,
                text=def_val,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#e2e8f0",
                anchor="e"
            )
            lbl_val.grid(row=i, column=1, sticky="e", pady=1)
            self.metrics_rows[key] = lbl_val

        # Action Buttons Row
        self.actions_frame = ctk.CTkFrame(self.left_pane, fg_color="transparent")
        self.actions_frame.pack(fill="x", padx=10, pady=(10, 4))

        btn_style = {"height": 24, "font": ctk.CTkFont(size=11), "fg_color": "#21242c", "hover_color": "#333742"}

        self.btn_pause = ctk.CTkButton(self.actions_frame, text="Pause", width=52, command=self._handle_pause, **btn_style)
        self.btn_pause.pack(side="left", padx=2)

        self.btn_reset = ctk.CTkButton(self.actions_frame, text="Reset", width=52, command=self._handle_reset, **btn_style)
        self.btn_reset.pack(side="left", padx=2)

        self.btn_dont_log = ctk.CTkButton(self.actions_frame, text="Don't log", width=62, command=self._toggle_dont_log, **btn_style)
        self.btn_dont_log.pack(side="left", padx=2)

        self.btn_select_area = ctk.CTkButton(self.actions_frame, text="Select area", width=72, command=self._handle_select_area, **btn_style)
        self.btn_select_area.pack(side="left", padx=2)

        self.btn_view_capture = ctk.CTkButton(self.actions_frame, text="View capture", width=76, command=self._open_capture_preview, **btn_style)
        self.btn_view_capture.pack(side="left", padx=2)

        # Status / Auto-Pause Banner Footer
        self.banner_frame = ctk.CTkFrame(self.left_pane, fg_color="#181a1f", corner_radius=4)
        self.banner_frame.pack(fill="x", padx=10, pady=(6, 8))

        self.lbl_banner = ctk.CTkLabel(
            self.banner_frame,
            text="Tracking active. Logging carries on at your next EXP gain.",
            font=ctk.CTkFont(size=10),
            text_color="#94a3b8",
            wraplength=330,
            justify="left"
        )
        self.lbl_banner.pack(padx=8, pady=4, anchor="w")

    def _build_right_pane(self):
        self.right_pane = ctk.CTkFrame(self.body_container, fg_color="#18191d", corner_radius=0)
        self.right_pane.pack(side="right", fill="both", expand=True)

        # Header: < EXP log
        rp_header = ctk.CTkFrame(self.right_pane, fg_color="transparent")
        rp_header.pack(fill="x", padx=14, pady=(8, 2))

        self.lbl_log_title = ctk.CTkLabel(
            rp_header,
            text="< EXP log",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#cbd5e1"
        )
        self.lbl_log_title.pack(side="left")

        # Date · Map · Level · Party summary
        self.lbl_log_meta = ctk.CTkLabel(
            self.right_pane,
            text="Victoria Road · Lv 57 · Solo",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#f1f5f9"
        )
        self.lbl_log_meta.pack(anchor="w", padx=14, pady=(2, 0))

        # Status subheader
        self.lbl_log_status = ctk.CTkLabel(
            self.right_pane,
            text="Waiting for game EXP...",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        self.lbl_log_status.pack(anchor="w", padx=14, pady=(0, 6))

        # Table container with dark Treeview
        table_container = ctk.CTkFrame(self.right_pane, fg_color="#151619", corner_radius=4)
        table_container.pack(fill="both", expand=True, padx=12, pady=4)

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "ExpLog.Treeview",
            background="#151619",
            foreground="#e2e8f0",
            rowheight=22,
            fieldbackground="#151619",
            borderwidth=0,
            font=("Arial", 9)
        )
        style.configure(
            "ExpLog.Treeview.Heading",
            background="#1e2025",
            foreground="#94a3b8",
            relief="flat",
            font=("Arial", 9, "bold")
        )
        style.map("ExpLog.Treeview", background=[("selected", "#0284c7")])

        cols = ("date", "map", "lv", "party", "time", "exp_hr", "mesos_hr")
        self.tree = ttk.Treeview(table_container, columns=cols, show="headings", style="ExpLog.Treeview", selectmode="browse")
        self.tree.tag_configure("live_row", foreground="#facc15", background="#1c1f26")

        self.tree.heading("date", text="Date")
        self.tree.heading("map", text="Map")
        self.tree.heading("lv", text="Lv")
        self.tree.heading("party", text="Party")
        self.tree.heading("time", text="Time")
        self.tree.heading("exp_hr", text="EXP/hr")
        self.tree.heading("mesos_hr", text="Mesos/hr")

        self.tree.column("date", width=58, anchor="w")
        self.tree.column("map", width=155, anchor="w")
        self.tree.column("lv", width=35, anchor="center")
        self.tree.column("party", width=48, anchor="center")
        self.tree.column("time", width=48, anchor="center")
        self.tree.column("exp_hr", width=70, anchor="e")
        self.tree.column("mesos_hr", width=70, anchor="e")

        scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Context Menu on Right Click
        self.context_menu = tk.Menu(self, tearoff=0, bg="#1e2025", fg="#e2e8f0", activebackground="#0284c7")
        self.context_menu.add_command(label="Rename / Edit Record", command=self._edit_selected_log)
        self.context_menu.add_command(label="Copy Row Data", command=self._copy_selected_log)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete Entry", command=self._delete_selected_log)

        self.tree.bind("<Button-3>", self._show_context_menu)

        # Footer hint
        lbl_hint = ctk.CTkLabel(
            self.right_pane,
            text="Top row is your active session. Right-click a saved row to copy, rename or delete.",
            font=ctk.CTkFont(size=10),
            text_color="#64748b"
        )
        lbl_hint.pack(pady=4)

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        x = self.winfo_x() + (event.x - self._drag_x)
        y = self.winfo_y() + (event.y - self._drag_y)
        self.geometry(f"+{x}+{y}")

    def _toggle_right_pane(self):
        if self.is_right_pane_open:
            self.right_pane.pack_forget()
            self.btn_collapse.configure(text=">")
            self.geometry(f"{self.left_pane_width}x{self.total_height}")
            self.is_right_pane_open = False
        else:
            self.right_pane.pack(side="right", fill="both", expand=True)
            self.btn_collapse.configure(text="<")
            self.geometry(f"{self.total_width}x{self.total_height}")
            self.is_right_pane_open = True

    def _toggle_dont_log(self):
        self.is_dont_log = not self.is_dont_log
        if self.is_dont_log:
            self.btn_dont_log.configure(fg_color="#7f1d1d", text="Logging OFF")
        else:
            self.btn_dont_log.configure(fg_color="#21242c", text="Don't log")

    def _handle_pause(self):
        if self.on_pause_callback:
            paused = self.on_pause_callback()
            self.btn_pause.configure(text="Resume" if paused else "Pause")

    def _handle_reset(self):
        if self.on_reset_callback:
            self.on_reset_callback(save_to_log=not self.is_dont_log)
        self._load_table_sessions()

    def _handle_select_area(self):
        def _on_box_selected(x, y, w, h):
            if self.on_calibrate_mesos_callback:
                self.on_calibrate_mesos_callback(x, y, w, h)

        AreaSelector(on_selected=_on_box_selected)

    def _open_capture_preview(self):
        if self.preview_win is None or not self.preview_win.winfo_exists():
            self.preview_win = CapturePreviewWindow(self)
        else:
            self.preview_win.focus()

    def _open_meta_dialog(self):
        """Allows user to edit Map name or Party size."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Grind Settings")
        dlg.geometry("300x240")
        dlg.attributes("-topmost", True)

        curr_meta_parts = [p.strip() for p in self.lbl_log_meta.cget("text").split("·")]
        default_map = curr_meta_parts[1] if len(curr_meta_parts) >= 3 else (curr_meta_parts[0] if curr_meta_parts else "Victoria Road")
        default_lv = "57"
        for p in curr_meta_parts:
            if p.startswith("Lv "):
                default_lv = p.replace("Lv", "").strip()

        ctk.CTkLabel(dlg, text="Map Name:", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(10, 2), padx=14, anchor="w")
        e_map = ctk.CTkEntry(dlg, width=270)
        e_map.insert(0, default_map)
        e_map.pack(padx=14)

        ctk.CTkLabel(dlg, text="Current Level (Auto-detected from LV. badge):", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(8, 2), padx=14, anchor="w")
        e_lv = ctk.CTkEntry(dlg, width=270)
        e_lv.insert(0, default_lv)
        e_lv.pack(padx=14)

        ctk.CTkLabel(dlg, text="Party Size (e.g. Solo, 5ppl):", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(8, 2), padx=14, anchor="w")
        e_party = ctk.CTkEntry(dlg, width=270)
        e_party.insert(0, "Solo")
        e_party.pack(padx=14)

        def _apply():
            m = e_map.get().strip()
            p = e_party.get().strip()
            try:
                l = int(e_lv.get().strip())
            except ValueError:
                l = 57
            if self.on_update_meta_callback:
                self.on_update_meta_callback(m, l, p)
            dlg.destroy()

        ctk.CTkButton(dlg, text="Apply", width=100, fg_color="#0284c7", command=_apply).pack(pady=14)

    def _load_table_sessions(self):
        """Populates Treeview from storage while preserving any live row."""
        for item in self.tree.get_children():
            if item != "__live__":
                self.tree.delete(item)

        sessions = self.storage.load_sessions()
        for s in sessions:
            self.tree.insert(
                "",
                "end",
                iid=s.get("id"),
                values=(
                    s.get("date", ""),
                    s.get("map", "Victoria Road"),
                    s.get("lv", 1),
                    s.get("party", "Solo"),
                    s.get("time", "0m"),
                    f"{s.get('exp_hr', 0):,}",
                    f"{s.get('mesos_hr', 0):,}" if s.get('mesos_hr') else ""
                )
            )

    def _update_live_table_row(self, snapshot: TrackerSnapshot):
        """Updates or inserts the top live session row in the EXP Log table."""
        if not snapshot.is_active:
            if self.tree.exists("__live__"):
                self.tree.delete("__live__")
            return

        if snapshot.elapsed_seconds >= 60:
            time_col = f"{int(snapshot.elapsed_seconds // 60)}m"
        else:
            time_col = f"{int(snapshot.elapsed_seconds)}s"

        row_values = (
            snapshot.date_str,
            snapshot.map_name,
            snapshot.level,
            snapshot.party,
            time_col,
            f"{snapshot.hero_exp_per_hr:,}",
            f"{snapshot.mesos_per_hr:,}" if snapshot.mesos_per_hr > 0 else ""
        )

        if self.tree.exists("__live__"):
            self.tree.item("__live__", values=row_values, tags=("live_row",))
        else:
            self.tree.insert("", 0, iid="__live__", values=row_values, tags=("live_row",))

    def _show_context_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id and row_id != "__live__":
            self.tree.selection_set(row_id)
            self.context_menu.post(event.x_root, event.y_root)

    def _copy_selected_log(self):
        selected = self.tree.selection()
        if selected:
            vals = self.tree.item(selected[0], "values")
            text = " | ".join(str(v) for v in vals)
            self.clipboard_clear()
            self.clipboard_append(text)

    def _delete_selected_log(self):
        selected = self.tree.selection()
        if selected and selected[0] != "__live__":
            session_id = selected[0]
            self.storage.delete_session(session_id)
            self.tree.delete(session_id)

    def _edit_selected_log(self):
        selected = self.tree.selection()
        if not selected or selected[0] == "__live__":
            return
        session_id = selected[0]
        vals = self.tree.item(selected[0], "values")
        curr_map = vals[1]
        curr_party = vals[3]

        def _on_save(new_map, new_party):
            self.storage.update_session(session_id, new_map=new_map, new_party=new_party)
            self._load_table_sessions()

        EditSessionDialog(self, curr_map, curr_party, _on_save)

    def update_stats(
        self,
        snapshot: TrackerSnapshot,
        lv_frame=None,
        exp_frame=None,
        meso_frame=None,
        raw_exp_text: str = ""
    ):
        """Thread-safe update called from the tracking worker."""
        def _update():
            # Hero Metrics
            self.lbl_hero_exp.configure(text=f"{snapshot.hero_exp_per_hr:,}")
            self.lbl_hero_sub.configure(text=snapshot.hero_eta_str)

            # Metrics Table
            self.metrics_rows["val_5min"].configure(text=f"{snapshot.exp_last_5min:,}")
            self.metrics_rows["val_pct_hr"].configure(text=f"{snapshot.pct_per_hour:.2f}%")
            self.metrics_rows["val_gained_exp"].configure(text=snapshot.gained_exp_display)
            self.metrics_rows["val_current_exp"].configure(text=snapshot.current_exp_display)
            self.metrics_rows["val_mesos"].configure(text=snapshot.mesos_display)
            self.metrics_rows["val_mesos_hr"].configure(text=f"{snapshot.mesos_per_hr:,}")
            self.metrics_rows["val_mesos_5min"].configure(text=f"{snapshot.mesos_5min:,}")
            self.metrics_rows["val_elapsed"].configure(text=snapshot.elapsed_time_str)

            # Banner / Status
            self.lbl_banner.configure(text=snapshot.status_text)
            self.lbl_log_status.configure(text=snapshot.status_text)
            self.lbl_log_meta.configure(text=f"{snapshot.date_str} · {snapshot.map_name} · Lv {snapshot.level} · {snapshot.party}")

            # Live row in right-pane table
            self._update_live_table_row(snapshot)

            # Preview window
            if self.preview_win and self.preview_win.winfo_exists():
                self.preview_win.update_feeds(
                    lv_frame,
                    exp_frame,
                    meso_frame,
                    snapshot.level,
                    raw_exp_text,
                    snapshot.map_name,
                    snapshot.current_mesos
                )

        self.after(0, _update)
