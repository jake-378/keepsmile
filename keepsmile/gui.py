"""Desktop GUI for Keepsmile lights. Run with ``python -m keepsmile.gui``."""

from __future__ import annotations

import asyncio
import queue
import threading
import tkinter as tk
from concurrent.futures import Future
from tkinter import colorchooser, ttk
from typing import Any, Callable, Coroutine

from . import state
from .client import FoundLight, KeepsmileLight, scan
from .protocol import MAX_BRIGHTNESS, LightState

PRESETS = [
    ("Red", (255, 0, 0)),
    ("Orange", (255, 96, 0)),
    ("Yellow", (255, 208, 0)),
    ("Green", (0, 255, 0)),
    ("Cyan", (0, 255, 255)),
    ("Blue", (0, 0, 255)),
    ("Purple", (128, 0, 255)),
    ("Pink", (255, 0, 128)),
    ("White", (255, 255, 255)),
    ("Warm", (255, 150, 60)),
]

BG = "#1e1f24"
PANEL = "#2a2c33"
FG = "#e8e8ec"
MUTED = "#9a9ca5"
ACCENT = "#4f8cff"
OK = "#3ecf6e"
ERR = "#ff5c5c"


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


class AsyncRunner:
    """Runs coroutines on a background event loop and hands results back to the Tk thread."""

    def __init__(self, root: tk.Tk):
        self._root = root
        self._results: queue.Queue[Callable[[], None]] = queue.Queue()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self._poll()

    def _poll(self) -> None:
        while True:
            try:
                callback = self._results.get_nowait()
            except queue.Empty:
                break
            callback()
        self._root.after(30, self._poll)

    def call_soon_in_ui(self, callback: Callable[[], None]) -> None:
        self._results.put(callback)

    def submit(
        self,
        coro: Coroutine[Any, Any, Any],
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> Future:
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)

        def finished(f: Future) -> None:
            error = f.exception()
            if error is not None:
                if on_error:
                    self.call_soon_in_ui(lambda: on_error(error))
            elif on_done:
                self.call_soon_in_ui(lambda: on_done(f.result()))

        future.add_done_callback(finished)
        return future

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.runner = AsyncRunner(root)
        self.found: list[FoundLight] = []
        self.light: KeepsmileLight | None = None
        self.rgb = state.DEFAULT_RGB
        self._lock: asyncio.Lock | None = None
        self._brightness_pending: int | None = None
        self._brightness_busy = False

        root.title("Keepsmile Lights")
        root.configure(bg=BG)
        root.minsize(420, 0)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._style()
        self._build()
        self._set_controls_enabled(False)
        self.scan(auto_connect=True)

    # ---------- layout ----------

    def _style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Panel.TLabel", background=PANEL, foreground=FG)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Header.TLabel", background=PANEL, foreground=FG, font=("Segoe UI Semibold", 11))
        style.configure("TButton", background="#3a3d46", foreground=FG, borderwidth=0, padding=(12, 6))
        style.map("TButton", background=[("disabled", "#2f3138"), ("active", "#474b56")],
                  foreground=[("disabled", "#666870")])
        style.configure("Accent.TButton", background=ACCENT, foreground="white")
        style.map("Accent.TButton", background=[("disabled", "#2f3138"), ("active", "#6a9eff")])
        style.configure("TCombobox", fieldbackground="#3a3d46", background="#3a3d46", foreground=FG,
                        arrowcolor=FG, bordercolor="#3a3d46", lightcolor="#3a3d46", darkcolor="#3a3d46",
                        padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", "#3a3d46")], foreground=[("readonly", FG)],
                  selectbackground=[("readonly", "#3a3d46")], selectforeground=[("readonly", FG)],
                  background=[("readonly", "#3a3d46")])
        self.root.option_add("*TCombobox*Listbox.background", "#3a3d46")
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        style.configure("Horizontal.TScale", background=PANEL, troughcolor="#3a3d46")

    def _panel(self, title: str) -> ttk.Frame:
        outer = ttk.Frame(self.root, style="Panel.TFrame", padding=14)
        outer.pack(fill="x", padx=14, pady=(14, 0))
        ttk.Label(outer, text=title, style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        return outer

    def _build(self) -> None:
        # Device
        device = self._panel("Device")
        row = ttk.Frame(device, style="Panel.TFrame")
        row.pack(fill="x")
        self.device_var = tk.StringVar()
        self.device_box = ttk.Combobox(row, textvariable=self.device_var, state="readonly", width=30)
        self.device_box.pack(side="left", fill="x", expand=True)
        self.scan_btn = ttk.Button(row, text="Scan", command=self.scan)
        self.scan_btn.pack(side="left", padx=(8, 0))
        self.connect_btn = ttk.Button(row, text="Connect", style="Accent.TButton", command=self.toggle_connection)
        self.connect_btn.pack(side="left", padx=(8, 0))

        status = ttk.Frame(device, style="Panel.TFrame")
        status.pack(fill="x", pady=(10, 0))
        self.status_dot = tk.Canvas(status, width=10, height=10, bg=PANEL, highlightthickness=0)
        self.status_dot.pack(side="left")
        self._dot = self.status_dot.create_oval(1, 1, 9, 9, fill=MUTED, outline="")
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").pack(side="left", padx=(8, 0))

        # Power
        power = self._panel("Power")
        row = ttk.Frame(power, style="Panel.TFrame")
        row.pack(fill="x")
        self.on_btn = ttk.Button(row, text="On", style="Accent.TButton", command=lambda: self.set_power(True))
        self.on_btn.pack(side="left", expand=True, fill="x")
        self.off_btn = ttk.Button(row, text="Off", command=lambda: self.set_power(False))
        self.off_btn.pack(side="left", expand=True, fill="x", padx=(8, 0))
        self.power_var = tk.StringVar(value="Power state unknown")
        self.power_label = ttk.Label(power, textvariable=self.power_var, style="Muted.TLabel")
        self.power_label.pack(anchor="w", pady=(8, 0))

        # Color
        color = self._panel("Color")
        top = ttk.Frame(color, style="Panel.TFrame")
        top.pack(fill="x")
        self.preview = tk.Canvas(top, width=64, height=64, bg=PANEL, highlightthickness=0)
        self.preview.pack(side="left")
        self._swatch = self.preview.create_rectangle(2, 2, 62, 62, fill=to_hex(self.rgb), outline="#555")
        right = ttk.Frame(top, style="Panel.TFrame")
        right.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.hex_var = tk.StringVar(value=to_hex(self.rgb))
        ttk.Label(right, textvariable=self.hex_var, style="Panel.TLabel", font=("Consolas", 12)).pack(anchor="w")
        self.pick_btn = ttk.Button(right, text="Pick color…", command=self.pick_color)
        self.pick_btn.pack(anchor="w", pady=(8, 0))

        grid = ttk.Frame(color, style="Panel.TFrame")
        grid.pack(fill="x", pady=(12, 0))
        self.preset_buttons: list[tk.Button] = []
        for i, (name, rgb) in enumerate(PRESETS):
            btn = tk.Button(grid, bg=to_hex(rgb), activebackground=to_hex(rgb), relief="flat", bd=0,
                            width=4, height=1, cursor="hand2", command=lambda c=rgb: self.set_color(c))
            btn.grid(row=i // 5, column=i % 5, padx=3, pady=3, sticky="ew")
            grid.columnconfigure(i % 5, weight=1)
            self.preset_buttons.append(btn)

        # Brightness
        bright = self._panel("Brightness")
        row = ttk.Frame(bright, style="Panel.TFrame")
        row.pack(fill="x")
        # Bound to a variable because ttk.Scale.set() is a no-op while the widget is disabled.
        self.bright_var = tk.DoubleVar(value=MAX_BRIGHTNESS)
        self.bright_scale = ttk.Scale(row, from_=0, to=MAX_BRIGHTNESS, variable=self.bright_var,
                                      orient="horizontal", command=self.on_brightness_drag)
        self.bright_scale.pack(side="left", fill="x", expand=True)
        self.bright_label = ttk.Label(row, text=f"{MAX_BRIGHTNESS}%", style="Panel.TLabel", width=5, anchor="e")
        self.bright_label.pack(side="left", padx=(8, 0))

        ttk.Frame(self.root, height=14).pack()

    # ---------- status helpers ----------

    def set_status(self, text: str, color: str = MUTED) -> None:
        self.status_var.set(text)
        self.status_dot.itemconfigure(self._dot, fill=color)

    def report_error(self, prefix: str) -> Callable[[BaseException], None]:
        def handler(error: BaseException) -> None:
            self.set_status(f"{prefix}: {error or type(error).__name__}", ERR)
        return handler

    def _set_controls_enabled(self, enabled: bool) -> None:
        state_flag = "!disabled" if enabled else "disabled"
        for widget in (self.on_btn, self.off_btn, self.pick_btn, self.bright_scale):
            widget.state([state_flag])
        for btn in self.preset_buttons:
            btn.configure(state="normal" if enabled else "disabled")

    def _show_color(self, rgb: tuple[int, int, int]) -> None:
        self.rgb = rgb
        self.preview.itemconfigure(self._swatch, fill=to_hex(rgb))
        self.hex_var.set(to_hex(rgb))

    def _show_brightness(self, level: int) -> None:
        self.bright_var.set(level)
        self.bright_label.configure(text=f"{level}%")

    def _show_power(self, on: bool | None) -> None:
        text, color = {True: ("Light is on", OK), False: ("Light is off", MUTED)}.get(on, ("Power state unknown", MUTED))
        self.power_var.set(text)
        self.power_label.configure(foreground=color)

    def _show_state(self, s: LightState) -> None:
        self._show_color(s.rgb)
        self._show_brightness(s.brightness)
        self._show_power(s.on)

    # ---------- device ----------

    def scan(self, auto_connect: bool = False) -> None:
        self.scan_btn.state(["disabled"])
        self.set_status("Scanning…", ACCENT)

        def done(lights: list[FoundLight]) -> None:
            self.scan_btn.state(["!disabled"])
            self.found = lights
            self.device_box["values"] = [f"{l.name}  ({l.address})" for l in lights]
            if not lights:
                self.set_status("No lights found. Close the phone app and scan again.", ERR)
                return
            strips = [i for i, l in enumerate(lights) if l.name.startswith("KS03")]
            self.device_box.current(strips[0] if strips else 0)
            self.set_status(f"Found {len(lights)} light(s)")
            if auto_connect and self.light is None:
                self.connect()

        def failed(error: BaseException) -> None:
            self.scan_btn.state(["!disabled"])
            self.report_error("Scan failed")(error)

        self.runner.submit(scan(5.0), done, failed)

    def toggle_connection(self) -> None:
        if self.light is not None:
            self.disconnect()
        else:
            self.connect()

    def connect(self) -> None:
        index = self.device_box.current()
        if index < 0:
            self.set_status("Scan and pick a light first", ERR)
            return
        found = self.found[index]
        rgb, brightness = state.load(found.address)
        light = KeepsmileLight(found.device, found.name, rgb=rgb, brightness=brightness,
                               on_disconnect=lambda: self.runner.call_soon_in_ui(self._on_lost),
                               on_state=lambda s: self.runner.call_soon_in_ui(lambda: self._show_state(s)))
        self.connect_btn.state(["disabled"])
        self.set_status(f"Connecting to {found.name}…", ACCENT)

        async def go() -> None:
            self._lock = asyncio.Lock()
            await light.connect()

        def done(_: Any) -> None:
            self.light = light
            self.connect_btn.state(["!disabled"])
            self.connect_btn.configure(text="Disconnect", style="TButton")
            self._show_color(light.rgb)
            self._show_brightness(light.brightness)
            self._show_power(light.is_on)
            self._set_controls_enabled(True)
            self.set_status(f"Connected to {found.name} ({light.protocol.value} protocol)", OK)

        def failed(error: BaseException) -> None:
            self.connect_btn.state(["!disabled"])
            self.report_error("Connect failed")(error)

        self.runner.submit(go(), done, failed)

    def disconnect(self) -> None:
        light, self.light = self.light, None
        self._reset_connection_ui("Disconnected")
        if light is not None:
            state.save(light.address, light.rgb, light.brightness)
            self.runner.submit(light.disconnect())

    def _on_lost(self) -> None:
        if self.light is not None and not self.light.is_connected:
            self.light = None
            self._reset_connection_ui("Connection lost", ERR)

    def _reset_connection_ui(self, text: str, color: str = MUTED) -> None:
        self.connect_btn.configure(text="Connect", style="Accent.TButton")
        self._set_controls_enabled(False)
        self.set_status(text, color)

    # ---------- commands ----------

    def _send(self, action: Callable[[KeepsmileLight], Coroutine[Any, Any, None]],
              on_done: Callable[[Any], None] | None = None, label: str = "Command") -> None:
        light = self.light
        if light is None:
            return

        async def go() -> None:
            async with self._lock:
                await action(light)

        def done(result: Any) -> None:
            state.save(light.address, light.rgb, light.brightness)
            if on_done:
                on_done(result)

        self.runner.submit(go(), done, self.report_error(f"{label} failed"))

    def set_power(self, on: bool) -> None:
        self._send(lambda l: l.turn_on() if on else l.turn_off(), lambda _: self._show_power(on), label="Power")

    def set_color(self, rgb: tuple[int, int, int]) -> None:
        self._show_color(rgb)
        self._send(lambda l: l.set_color(*rgb), label="Color")

    def pick_color(self) -> None:
        picked, _ = colorchooser.askcolor(color=to_hex(self.rgb), title="Pick a color", parent=self.root)
        if picked:
            self.set_color(tuple(int(c) for c in picked))

    def on_brightness_drag(self, value: str) -> None:
        level = round(float(value))
        self.bright_label.configure(text=f"{level}%")
        if self.light is None:
            return
        self._brightness_pending = level
        if not self._brightness_busy:
            self._flush_brightness()

    def _flush_brightness(self) -> None:
        level, self._brightness_pending = self._brightness_pending, None
        if level is None or self.light is None or level == self.light.brightness:
            self._brightness_busy = False
            return
        self._brightness_busy = True
        light = self.light

        async def go() -> None:
            async with self._lock:
                await light.set_brightness(level)

        def done(_: Any) -> None:
            state.save(light.address, light.rgb, light.brightness)
            self._flush_brightness()

        def failed(error: BaseException) -> None:
            self._brightness_busy = False
            self.report_error("Brightness failed")(error)

        self.runner.submit(go(), done, failed)

    # ---------- shutdown ----------

    def on_close(self) -> None:
        if self.light is not None:
            light = self.light
            state.save(light.address, light.rgb, light.brightness)
            try:
                asyncio.run_coroutine_threadsafe(light.disconnect(), self.runner.loop).result(timeout=5)
            except Exception:
                pass
        self.runner.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
