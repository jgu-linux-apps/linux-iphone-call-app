"""BlueZ (system bus): find the paired iPhone, connect / disconnect the hands-free link."""
from gi.repository import Gio, GLib, GObject

BLUEZ = "org.bluez"
IF_DEV = "org.bluez.Device1"
HFP_AG_UUID = "0000111f-0000-1000-8000-00805f9b34fb"   # phone side of hands-free
PBAP_PSE_UUID = "0000112f-0000-1000-8000-00805f9b34fb"


def mac_from_path(path):
    # /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF
    tail = path.rsplit("/", 1)[-1]
    return tail[4:].replace("_", ":") if tail.startswith("dev_") else ""


class Bluez(GObject.Object):
    __gsignals__ = {"changed": (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self):
        super().__init__()
        self.devices = {}   # path -> props
        self.preferred = ""
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            print("no system bus:", e.message)
            self.bus = None
            return
        self.bus.signal_subscribe(BLUEZ, None, None, None, None,
                                  Gio.DBusSignalFlags.NONE, self._on_signal)
        self.refresh()

    # ---- discovery -------------------------------------------------------
    def refresh(self):
        if self.bus is None:
            return
        try:
            res = self.bus.call_sync(BLUEZ, "/", "org.freedesktop.DBus.ObjectManager",
                                     "GetManagedObjects", None, None,
                                     Gio.DBusCallFlags.NONE, 5000, None)
            objs = res.unpack()[0]
        except GLib.Error:
            objs = {}
        self.devices = {p: dict(i[IF_DEV]) for p, i in objs.items() if IF_DEV in i}
        self.emit("changed")

    def _on_signal(self, conn, sender, path, iface, signal, params):
        if iface == "org.freedesktop.DBus.ObjectManager":
            GLib.idle_add(self._refresh_once)
        elif iface == "org.freedesktop.DBus.Properties" and signal == "PropertiesChanged":
            ifn, changed, _inv = params.unpack()
            if ifn == IF_DEV and path in self.devices:
                self.devices[path].update(changed)
                self.emit("changed")

    def _refresh_once(self):
        self.refresh()
        return False

    def phones(self):
        """Paired devices that can act as a phone (HFP Audio Gateway)."""
        out = []
        for p, d in self.devices.items():
            uuids = [u.lower() for u in d.get("UUIDs", [])]
            if not d.get("Paired"):
                continue
            if HFP_AG_UUID in uuids or "iphone" in (d.get("Name") or "").lower():
                out.append((p, d))
        out.sort(key=lambda x: (0 if "iphone" in (x[1].get("Name") or "").lower() else 1,
                                0 if x[1].get("Connected") else 1))
        return out

    def phone(self):
        """(path, props) of the chosen iPhone or None."""
        phones = self.phones()
        if self.preferred:
            for p, d in phones:
                if (d.get("Address") or "").upper() == self.preferred.upper():
                    return p, d
        return phones[0] if phones else None

    def phone_mac(self):
        ph = self.phone()
        return (ph[1].get("Address") or mac_from_path(ph[0])).upper() if ph else ""

    def phone_name(self):
        ph = self.phone()
        return (ph[1].get("Alias") or ph[1].get("Name") or "iPhone") if ph else ""

    def phone_connected(self):
        ph = self.phone()
        return bool(ph and ph[1].get("Connected"))

    # ---- actions ---------------------------------------------------------
    def _dev_call(self, method, params, cb=None):
        ph = self.phone()
        if not ph or self.bus is None:
            if cb:
                cb(False, "no device")
            return

        def done(conn, res):
            try:
                conn.call_finish(res)
                ok, err = True, ""
            except GLib.Error as e:
                ok, err = False, e.message
            if cb:
                cb(ok, err)

        self.bus.call(BLUEZ, ph[0], IF_DEV, method, params, None,
                      Gio.DBusCallFlags.NONE, 30000, None, done)

    def connect_hfp(self, cb=None):
        self._dev_call("ConnectProfile", GLib.Variant("(s)", (HFP_AG_UUID,)), cb)

    def disconnect_hfp(self, cb=None):
        self._dev_call("DisconnectProfile", GLib.Variant("(s)", (HFP_AG_UUID,)), cb)
