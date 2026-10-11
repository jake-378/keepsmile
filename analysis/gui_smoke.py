"""Launch the GUI, exercise it against the real light, screenshot it, and exit."""

import sys
import time
import tkinter as tk

from PIL import ImageGrab

sys.path.insert(0, r"C:\Development\rx")
from keepsmile.gui import App  # noqa: E402

root = tk.Tk()
app = App(root)
log = []
t0 = time.monotonic()


def snap(name):
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(rf"C:\Development\rx\analysis\{name}.png")
    log.append(f"t={time.monotonic() - t0:4.1f}s {name}: status={app.status_var.get()!r} "
               f"power={app.power_var.get()!r} colour={app.hex_var.get()} connected={app.light is not None} "
               f"slider={app.bright_scale.get():.0f} label={app.bright_label.cget('text')}")


def connected_idle():
    snap("gui_connected")
    if app.light is not None:
        app.set_color((0, 128, 255))
        app.bright_scale.set(70)
    root.after(15000, after_commands)


def after_commands():
    snap("gui_after_commands")
    app.on_close()


root.after(30000, connected_idle)
root.mainloop()
print("\n".join(log))
