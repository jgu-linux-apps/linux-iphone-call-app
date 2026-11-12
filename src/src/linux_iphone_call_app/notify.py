"""Desktop notifications with action buttons (org.freedesktop.Notifications)."""
from gi.repository import Gio, GLib

NAME = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"


class Notifier:
    def __init__(self, app_name, on_action):
        self.app_name = app_name
        self.on_action = on_action      # on_action(tag, action_key)
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.ids = {}                   # tag -> notification id
        self.bus.signal_subscribe(NAME, NAME, "ActionInvoked", PATH, None,
                                  Gio.DBusSignalFlags.NONE, self._on_action)
        self.bus.signal_subscribe(NAME, NAME, "NotificationClosed", PATH, None,
                                  Gio.DBusSignalFlags.NONE, self._on_closed)

    def show(self, tag, summary, body, icon, actions=(), urgent=False, resident=False,
             category="", timeout=-1):
        hints = {"desktop-entry": GLib.Variant("s", "linux-iphone-call-app"),
                 "urgency": GLib.Variant("y", 2 if urgent else 1)}
        if resident:
            hints["resident"] = GLib.Variant("b", True)
        if category:
            hints["category"] = GLib.Variant("s", category)
        flat = []
        for key, label in actions:
            flat += [key, label]
        replaces = self.ids.get(tag, 0)
        try:
            res = self.bus.call_sync(NAME, PATH, NAME, "Notify",
                                     GLib.Variant("(susssasa{sv}i)",
                                                  (self.app_name, replaces, icon, summary, body,
                                                   flat, hints, timeout)),
                                     None, Gio.DBusCallFlags.NONE, 3000, None)
            self.ids[tag] = res.unpack()[0]
        except GLib.Error as e:
            print("notify failed:", e.message)

    def close(self, tag):
        nid = self.ids.pop(tag, None)
        if nid:
            try:
                self.bus.call_sync(NAME, PATH, NAME, "CloseNotification",
                                   GLib.Variant("(u)", (nid,)), None,
                                   Gio.DBusCallFlags.NONE, 2000, None)
            except GLib.Error:
                pass

    def _tag_for(self, nid):
        for t, i in self.ids.items():
            if i == nid:
                return t
        return None

    def _on_action(self, conn, sender, path, iface, signal, params):
        nid, key = params.unpack()
        tag = self._tag_for(nid)
        if tag:
            self.on_action(tag, key)

    def _on_closed(self, conn, sender, path, iface, signal, params):
        nid = params.unpack()[0]
        tag = self._tag_for(nid)
        if tag:
            self.ids.pop(tag, None)
