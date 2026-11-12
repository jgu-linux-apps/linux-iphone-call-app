"""Client for PipeWire's Bluetooth telephony service (org.pipewire.Telephony, PipeWire >= 1.4).

The laptop acts as a hands-free unit (like a car kit); the iPhone is the audio gateway.
"""
import time

from gi.repository import Gio, GLib, GObject

TEL = "org.pipewire.Telephony"
ROOT = "/org/pipewire/Telephony"
IF_AG = "org.pipewire.Telephony.AudioGateway1"
IF_TR = "org.pipewire.Telephony.AudioGatewayTransport1"
IF_CALL = "org.pipewire.Telephony.Call1"
IF_OFONO_VCM = "org.ofono.VoiceCallManager"
IF_OFONO_CALL = "org.ofono.VoiceCall"
IF_PROPS = "org.freedesktop.DBus.Properties"
IF_OM = "org.freedesktop.DBus.ObjectManager"

RINGING = ("incoming", "waiting")
LIVE = ("active", "held", "dialing", "alerting")


class Telephony(GObject.Object):
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "call-added": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "call-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "call-removed": (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
        "transport-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.available = False
        self.ags = {}     # path -> {"address": str, "transport": dict}
        self.calls = {}   # path -> dict
        self.preferred_mac = ""
        self._sub = None
        Gio.bus_watch_name_on_connection(self.bus, TEL, Gio.BusNameWatcherFlags.NONE,
                                         self._appeared, self._vanished)

    # ---- bus life-cycle --------------------------------------------------
    def _appeared(self, conn, name, owner):
        self.available = True
        if self._sub is None:
            self._sub = self.bus.signal_subscribe(TEL, None, None, None, None,
                                                  Gio.DBusSignalFlags.NONE, self._on_signal)
        self.refresh()

    def _vanished(self, conn, name):
        self.available = False
        for p in list(self.calls):
            self._drop_call(p)
        self.ags.clear()
        self.emit("changed")

    def refresh(self):
        if not self.available:
            return
        try:
            res = self.bus.call_sync(TEL, ROOT, IF_OM, "GetManagedObjects", None, None,
                                     Gio.DBusCallFlags.NONE, 3000, None)
            objs = res.unpack()[0]
        except GLib.Error:
            objs = {}
        seen_ags = set()
        for path, ifaces in objs.items():
            if IF_AG in ifaces:
                seen_ags.add(path)
                self.ags[path] = {"address": (ifaces[IF_AG].get("Address") or "").upper(),
                                  "transport": dict(ifaces.get(IF_TR, {}))}
            if IF_CALL in ifaces:
                self._upsert_call(path, ifaces[IF_CALL])
        for p in list(self.ags):
            if p not in seen_ags:
                self._drop_ag(p)
        # calls may not be exported through the object manager: ask oFono-style too
        for ag in list(self.ags):
            try:
                res = self.bus.call_sync(TEL, ag, IF_OFONO_VCM, "GetCalls", None, None,
                                         Gio.DBusCallFlags.NONE, 3000, None)
                for cpath, props in res.unpack()[0]:
                    self._upsert_call(cpath, props)
            except GLib.Error:
                pass
        self.emit("changed")
        self.emit("transport-changed")

    # ---- signals ---------------------------------------------------------
    def _on_signal(self, conn, sender, path, iface, signal, params):
        try:
            if iface == IF_OM and signal == "InterfacesAdded":
                p, ifaces = params.unpack()
                if IF_AG in ifaces:
                    self.ags[p] = {"address": (ifaces[IF_AG].get("Address") or "").upper(),
                                   "transport": dict(ifaces.get(IF_TR, {}))}
                    self.emit("changed")
                    self.emit("transport-changed")
                if IF_CALL in ifaces:
                    self._upsert_call(p, ifaces[IF_CALL])
            elif iface == IF_OM and signal == "InterfacesRemoved":
                p, names = params.unpack()
                if IF_CALL in names:
                    self._drop_call(p)
                if IF_AG in names:
                    self._drop_ag(p)
            elif iface == IF_PROPS and signal == "PropertiesChanged":
                ifn, changed, _inv = params.unpack()
                if ifn == IF_CALL:
                    self._upsert_call(path, changed)
                elif ifn == IF_TR and path in self.ags:
                    self.ags[path]["transport"].update(changed)
                    self.emit("transport-changed")
            elif iface == IF_OFONO_VCM and signal == "CallAdded":
                p, props = params.unpack()
                self._upsert_call(p, props)
            elif iface == IF_OFONO_VCM and signal == "CallRemoved":
                self._drop_call(params.unpack()[0])
            elif iface == IF_OFONO_CALL and signal == "PropertyChanged":
                name, val = params.unpack()
                self._upsert_call(path, {name: val})
            elif signal in ("ModemAdded", "ModemRemoved", "AudioGatewayAdded", "AudioGatewayRemoved"):
                GLib.timeout_add(300, lambda: (self.refresh(), False)[1])
        except Exception as e:  # never let a malformed signal kill the app
            print("telephony signal error:", e)

    def _upsert_call(self, path, props):
        new = path not in self.calls
        props = dict(props)
        if new and "State" not in props:
            try:
                res = self.bus.call_sync(TEL, path, IF_PROPS, "GetAll",
                                         GLib.Variant("(s)", (IF_CALL,)), None,
                                         Gio.DBusCallFlags.NONE, 2000, None)
                full = dict(res.unpack()[0])
                full.update(props)
                props = full
            except GLib.Error:
                pass
        c = self.calls.setdefault(path, {
            "path": path, "ag": path.rsplit("/", 1)[0], "number": "", "name": "",
            "state": "", "first_seen": time.time(), "active_since": None,
            "was_ringing": False, "answered": False,
        })
        if "LineIdentification" in props:
            c["number"] = props["LineIdentification"] or c["number"]
        if "Name" in props:
            c["name"] = props["Name"] or c["name"]
        if "State" in props:
            c["state"] = props["State"]
            if c["state"] in RINGING:
                c["was_ringing"] = True
            if c["state"] == "active":
                c["answered"] = True
                if not c["active_since"]:
                    c["active_since"] = time.time()
        if c["state"] == "disconnected":
            if new:
                self.calls.pop(path, None)
            else:
                self._drop_call(path)
            return
        self.emit("call-added" if new else "call-changed", path)

    def _drop_call(self, path):
        c = self.calls.pop(path, None)
        if c:
            self.emit("call-removed", path, c)

    def _drop_ag(self, ag):
        self.ags.pop(ag, None)
        for p in [p for p, c in self.calls.items() if c["ag"] == ag]:
            self._drop_call(p)
        self.emit("changed")
        self.emit("transport-changed")

    # ---- queries ---------------------------------------------------------
    def ag(self):
        if not self.ags:
            return None
        if self.preferred_mac:
            for p, a in self.ags.items():
                if a["address"] == self.preferred_mac.upper():
                    return p
        return sorted(self.ags)[0]

    def transport(self):
        ag = self.ag()
        return self.ags[ag]["transport"] if ag else {}

    def audio_on_laptop(self):
        return (self.transport().get("State") or "").lower() == "active"

    def primary_call(self):
        order = {"incoming": 0, "waiting": 1, "active": 2, "alerting": 3, "dialing": 4, "held": 5}
        calls = sorted(self.calls.values(), key=lambda c: (order.get(c["state"], 9), c["first_seen"]))
        return calls[0] if calls else None

    # ---- actions ---------------------------------------------------------
    def _call(self, path, iface, method, params=None, cb=None, reply=None):
        def done(conn, res):
            try:
                out = conn.call_finish(res)
                if cb:
                    cb(True, out.unpack() if out else None)
            except GLib.Error as e:
                print(f"{iface}.{method} failed:", e.message)
                if cb:
                    cb(False, e.message)
        self.bus.call(TEL, path, iface, method, params, reply, Gio.DBusCallFlags.NONE,
                      20000, None, done)

    def answer(self, path, cb=None):
        self._call(path, IF_CALL, "Answer", cb=cb)

    def hangup(self, path, cb=None):
        self._call(path, IF_CALL, "Hangup", cb=cb)

    def dial(self, number, cb=None):
        ag = self.ag()
        if not ag:
            if cb:
                cb(False, "no phone")
            return
        self._call(ag, IF_AG, "Dial", GLib.Variant("(s)", (number,)), cb=cb)

    def hold_and_answer(self, cb=None):
        ag = self.ag()
        if ag:
            self._call(ag, IF_AG, "HoldAndAnswer", cb=cb)

    def send_tones(self, tones):
        ag = self.ag()
        if ag:
            self._call(ag, IF_AG, "SendTones", GLib.Variant("(s)", (tones,)))

    def set_reject_sco(self, value, cb=None):
        ag = self.ag()
        if not ag:
            return
        self._call(ag, IF_PROPS, "Set",
                   GLib.Variant("(ssv)", (IF_TR, "RejectSCO", GLib.Variant("b", bool(value)))), cb=cb)
        self.ags[ag]["transport"]["RejectSCO"] = bool(value)

    def activate_audio(self, cb=None):
        ag = self.ag()
        if ag:
            self._call(ag, IF_TR, "Activate", cb=cb)
