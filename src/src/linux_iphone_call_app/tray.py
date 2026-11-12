"""Tray icon (Ayatana AppIndicator, GtkStatusIcon fallback)."""
import os

import gi
from gi.repository import Gtk

from . import APP_ID, APP_NAME

try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AI
except (ValueError, ImportError):
    AI = None


class Tray:
    def __init__(self, icon_dir, on_activate):
        self.icon_dir = icon_dir
        self.on_activate = on_activate
        self.menu = Gtk.Menu()
        self.state = "offline"
        if AI:
            self.ind = AI.Indicator.new(APP_ID, "lica-tray-offline", AI.IndicatorCategory.COMMUNICATIONS)
            self.ind.set_icon_theme_path(icon_dir)
            self.ind.set_status(AI.IndicatorStatus.ACTIVE)
            self.ind.set_title(APP_NAME)
            self.ind.set_menu(self.menu)
            self.status_icon = None
        else:
            self.ind = None
            self.status_icon = Gtk.StatusIcon()
            self.status_icon.set_title(APP_NAME)
            self.status_icon.connect("activate", lambda *_a: on_activate())
            self.status_icon.connect("popup-menu", self._popup)
        self.set_state("offline", APP_NAME)

    def _popup(self, icon, button, t):
        self.menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, t)

    def set_state(self, state, tooltip):
        self.state = state
        name = f"lica-tray-{state}"
        if self.ind:
            self.ind.set_icon_full(name, tooltip)
        else:
            self.status_icon.set_from_file(os.path.join(self.icon_dir, name + ".svg"))
            self.status_icon.set_tooltip_text(tooltip)

    def set_menu(self, items):
        """items: list of (label, callback|None) ; None entry = separator."""
        for ch in self.menu.get_children():
            self.menu.remove(ch)
        for it in items:
            if it is None:
                self.menu.append(Gtk.SeparatorMenuItem())
                continue
            label, cb = it
            mi = Gtk.MenuItem(label=label)
            if cb:
                mi.connect("activate", lambda _m, cb=cb: cb())
            else:
                mi.set_sensitive(False)
            self.menu.append(mi)
        self.menu.show_all()
        if self.ind and items and items[0]:
            # middle-click / secondary activate opens the window
            for ch in self.menu.get_children():
                if isinstance(ch, Gtk.MenuItem) and ch.get_sensitive():
                    self.ind.set_secondary_activate_target(ch)
                    break
