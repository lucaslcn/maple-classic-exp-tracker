import tkinter as tk
from typing import Callable, Optional


class AreaSelector(tk.Toplevel):
    """
    Transparent fullscreen overlay allowing the user to click & drag
    a bounding box on their screen (e.g. over their inventory Meso pouch).
    """

    def __init__(self, on_selected: Callable[[int, int, int, int], None]):
        super().__init__()
        self.on_selected = on_selected

        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.35)
        self.attributes("-topmost", True)
        self.configure(cursor="cross")

        self.canvas = tk.Canvas(self, cursor="cross", bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Instructions banner at top center
        self.canvas.create_text(
            self.winfo_screenwidth() // 2,
            40,
            text="Click and drag a box over your Inventory Meso counter (or EXP area). Press ESC to cancel.",
            fill="#ffffff",
            font=("Arial", 16, "bold")
        )

        self.start_x = 0
        self.start_y = 0
        self.rect_id = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self.destroy())

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#38bdf8", width=3, fill="#0284c7"
        )

    def _on_drag(self, event):
        if self.rect_id:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def _on_release(self, event):
        end_x = event.x
        end_y = event.y

        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        width = x2 - x1
        height = y2 - y1

        self.destroy()

        if width > 10 and height > 8:
            self.on_selected(x1, y1, width, height)

