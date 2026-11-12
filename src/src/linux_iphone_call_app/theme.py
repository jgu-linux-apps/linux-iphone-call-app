"""Follow the system light/dark preference (xdg-desktop-portal, GNOME fallback)."""
from gi.repository import Gio, GLib, GObject, Gtk


class Theme(GObject.Object):
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self):
        super().__init__()
        self.dark = False
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._read()
        self.bus.signal_subscribe("org.freedesktop.portal.Desktop", "org.freedesktop.portal.Settings",
                                  "SettingChanged", "/org/freedesktop/portal/desktop", None,
                                  Gio.DBusSignalFlags.NONE, self._on_changed)
        self._gsettings = None
        try:
            src = Gio.SettingsSchemaSource.get_default()
            if src and src.lookup("org.gnome.desktop.interface", True):
                self._gsettings = Gio.Settings.new("org.gnome.desktop.interface")
                self._gsettings.connect("changed::color-scheme", lambda *a: self._read(True))
                self._gsettings.connect("changed::gtk-theme", lambda *a: self._read(True))
        except Exception:
            pass
        self._apply()

    def _read(self, emit=False):
        dark = None
        try:
            res = self.bus.call_sync("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                                     "org.freedesktop.portal.Settings", "Read",
                                     GLib.Variant("(ss)", ("org.freedesktop.appearance", "color-scheme")),
                                     None, Gio.DBusCallFlags.NONE, 1500, None)
            v = res.unpack()[0]
            while isinstance(v, GLib.Variant):
                v = v.unpack()
            dark = (int(v) == 1)
        except Exception:
            pass
        if dark is None:
            try:
                s = Gio.Settings.new("org.gnome.desktop.interface")
                dark = "dark" in s.get_string("color-scheme") or "dark" in s.get_string("gtk-theme").lower()
            except Exception:
                dark = False
        changed = dark != self.dark
        self.dark = dark
        if emit and changed:
            self._apply()
            self.emit("changed")

    def _on_changed(self, conn, sender, path, iface, signal, params):
        ns, key, _val = params.unpack()
        if ns == "org.freedesktop.appearance" and key == "color-scheme":
            self._read(True)

    def _apply(self):
        s = Gtk.Settings.get_default()
        if s:
            s.set_property("gtk-application-prefer-dark-theme", self.dark)

    @property
    def app_icon(self):
        return "linux-iphone-call-app-dark" if self.dark else "linux-iphone-call-app"
