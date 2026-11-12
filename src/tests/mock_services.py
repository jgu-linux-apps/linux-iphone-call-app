"""Mock BlueZ + PipeWire telephony + notifications on one session bus, for UI tests."""
import sys

from gi.repository import Gio, GLib

XML = """
<node>
 <interface name="org.freedesktop.DBus.ObjectManager">
  <method name="GetManagedObjects"><arg type="a{oa{sa{sv}}}" direction="out"/></method>
  <signal name="InterfacesAdded"><arg type="o"/><arg type="a{sa{sv}}"/></signal>
  <signal name="InterfacesRemoved"><arg type="o"/><arg type="as"/></signal>
 </interface>
 <interface name="org.freedesktop.DBus.Properties">
  <method name="Get"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
  <method name="GetAll"><arg type="s" direction="in"/><arg type="a{sv}" direction="out"/></method>
  <method name="Set"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/></method>
  <signal name="PropertiesChanged"><arg type="s"/><arg type="a{sv}"/><arg type="as"/></signal>
 </interface>
 <interface name="org.bluez.Device1">
  <method name="ConnectProfile"><arg type="s" direction="in"/></method>
  <method name="DisconnectProfile"><arg type="s" direction="in"/></method>
 </interface>
 <interface name="org.pipewire.Telephony.AudioGateway1">
  <method name="Dial"><arg type="s" direction="in"/><arg type="o" direction="out"/></method>
  <method name="SendTones"><arg type="s" direction="in"/></method>
  <method name="HoldAndAnswer"/>
 </interface>
 <interface name="org.pipewire.Telephony.AudioGatewayTransport1"><method name="Activate"/></interface>
 <interface name="org.pipewire.Telephony.Call1"><method name="Answer"/><method name="Hangup"/></interface>
 <interface name="org.freedesktop.Notifications">
  <method name="Notify"><arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="s" direction="in"/>
   <arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="as" direction="in"/>
   <arg type="a{sv}" direction="in"/><arg type="i" direction="in"/><arg type="u" direction="out"/></method>
  <method name="CloseNotification"><arg type="u" direction="in"/></method>
  <signal name="ActionInvoked"><arg type="u"/><arg type="s"/></signal>
  <signal name="NotificationClosed"><arg type="u"/><arg type="u"/></signal>
 </interface>
 <interface name="org.lica.Mock">
  <method name="Ring"><arg type="s" direction="in"/></method>
  <method name="RemoteAnswer"/>
  <method name="RemoteHangup"/>
 </interface>
</node>"""

NODE = Gio.DBusNodeInfo.new_for_xml(XML)
IFS = {i.name: i for i in NODE.interfaces}
MAC = "AA:BB:CC:DD:EE:FF"
DEV = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF"
AG = "/org/pipewire/Telephony/ag1"
V = GLib.Variant

state = {"hfp": True, "transport": {"State": "idle", "Codec": 2, "RejectSCO": False},
         "calls": {}, "n": 0, "nid": 0}
conn = None


def log(*a):
    print("MOCK:", *a, flush=True)


def emit(path, iface, name, params):
    conn.emit_signal(None, path, iface, name, params)


def call_props(c):
    return {"LineIdentification": V("s", c["num"]), "Name": V("s", ""), "State": V("s", c["state"]),
            "IncomingLine": V("s", ""), "Multiparty": V("b", False)}


def ag_ifaces():
    return {"org.pipewire.Telephony.AudioGateway1": {"Address": V("s", MAC)},
            "org.pipewire.Telephony.AudioGatewayTransport1": {
                "State": V("s", state["transport"]["State"]), "Codec": V("y", 2),
                "RejectSCO": V("b", state["transport"]["RejectSCO"])}}


def set_call_state(path, st):
    state["calls"][path]["state"] = st
    emit(path, "org.freedesktop.DBus.Properties", "PropertiesChanged",
         V("(sa{sv}as)", ("org.pipewire.Telephony.Call1", {"State": V("s", st)}, [])))
    log("call", path, st)


def set_transport(st):
    state["transport"]["State"] = st
    emit(AG, "org.freedesktop.DBus.Properties", "PropertiesChanged",
         V("(sa{sv}as)", ("org.pipewire.Telephony.AudioGatewayTransport1", {"State": V("s", st)}, [])))
    log("transport", st)


def add_call(num, st):
    state["n"] += 1
    p = f"{AG}/call{state['n']}"
    state["calls"][p] = {"num": num, "state": st}
    emit("/org/pipewire/Telephony", "org.freedesktop.DBus.ObjectManager", "InterfacesAdded",
         V("(oa{sa{sv}})", (p, {"org.pipewire.Telephony.Call1": call_props(state["calls"][p])})))
    log("call added", p, num, st)
    return p


def remove_call(p):
    if state["calls"].pop(p, None) is not None:
        emit("/org/pipewire/Telephony", "org.freedesktop.DBus.ObjectManager", "InterfacesRemoved",
             V("(oas)", (p, ["org.pipewire.Telephony.Call1"])))
        log("call removed", p)
    if not state["calls"]:
        set_transport("idle")


def handle(c, sender, path, iface, method, params, inv):
    args = params.unpack()
    ret = None
    if iface == "org.freedesktop.DBus.ObjectManager":
        if path == "/":
            ret = V("(a{oa{sa{sv}}})", ({DEV: {"org.bluez.Device1": {
                "Address": V("s", MAC), "Name": V("s", "iPhone Jaro"), "Alias": V("s", "iPhone Jaro"),
                "Paired": V("b", True), "Connected": V("b", True),
                "UUIDs": V("as", ["0000111f-0000-1000-8000-00805f9b34fb"])}}},))
        else:
            objs = {}
            if state["hfp"]:
                objs[AG] = ag_ifaces()
                for p, cl in state["calls"].items():
                    objs[p] = {"org.pipewire.Telephony.Call1": call_props(cl)}
            ret = V("(a{oa{sa{sv}}})", (objs,))
    elif iface == "org.freedesktop.DBus.Properties":
        if method == "Set":
            log("SET", args)
            if args[1] == "RejectSCO":
                state["transport"]["RejectSCO"] = args[2]
        elif method == "GetAll":
            ret = V("(a{sv})", (call_props(state["calls"].get(path, {"num": "", "state": "active"})),))
        else:
            ret = V("(v)", (V("s", ""),))
    elif iface == "org.pipewire.Telephony.AudioGateway1":
        log(method, args)
        if method == "Dial":
            p = add_call(args[0], "dialing")
            GLib.timeout_add(600, lambda: (set_call_state(p, "alerting"), False)[1])
            GLib.timeout_add(1500, lambda: (set_call_state(p, "active"), False)[1])
            ret = V("(o)", (p,))
    elif iface == "org.pipewire.Telephony.AudioGatewayTransport1":
        log("Activate"); set_transport("active")
    elif iface == "org.pipewire.Telephony.Call1":
        log(method, path)
        if method == "Answer":
            set_call_state(path, "active")
            if not state["transport"]["RejectSCO"]:
                GLib.timeout_add(300, lambda: (set_transport("active"), False)[1])
        else:
            GLib.timeout_add(200, lambda: (remove_call(path), False)[1])
    elif iface == "org.bluez.Device1":
        log(method, args)
        if method == "DisconnectProfile" and state["hfp"]:
            state["hfp"] = False
            state["transport"]["State"] = "idle"
            for p in list(state["calls"]):
                emit("/org/pipewire/Telephony", "org.freedesktop.DBus.ObjectManager", "InterfacesRemoved",
                     V("(oas)", (p, ["org.pipewire.Telephony.Call1"])))
            emit("/org/pipewire/Telephony", "org.freedesktop.DBus.ObjectManager", "InterfacesRemoved",
                 V("(oas)", (AG, list(ag_ifaces()))))
        elif method == "ConnectProfile" and not state["hfp"]:
            def up():
                state["hfp"] = True
                state["transport"]["RejectSCO"] = False
                emit("/org/pipewire/Telephony", "org.freedesktop.DBus.ObjectManager", "InterfacesAdded",
                     V("(oa{sa{sv}})", (AG, ag_ifaces())))
                for p, cl in state["calls"].items():
                    emit("/org/pipewire/Telephony", "org.freedesktop.DBus.ObjectManager", "InterfacesAdded",
                         V("(oa{sa{sv}})", (p, {"org.pipewire.Telephony.Call1": call_props(cl)})))
                log("HFP up again")
                return False
            GLib.timeout_add(800, up)
    elif iface == "org.freedesktop.Notifications":
        if method == "Notify":
            state["nid"] = args[1] or state["nid"] + 1
            log("NOTIFY", args[3], "|", args[4].replace("\n", " / "), "|", args[5])
            ret = V("(u)", (state["nid"],))
        else:
            log("NOTIFY-CLOSE", args)
    elif iface == "org.lica.Mock":
        if method == "Ring":
            add_call(args[0], "incoming")
        elif method == "RemoteAnswer":
            for p in list(state["calls"]):
                set_call_state(p, "active")
        elif method == "RemoteHangup":
            for p in list(state["calls"]):
                remove_call(p)
    inv.return_value(ret)


def on_bus(c, name):
    global conn
    conn = c
    paths = ["/", DEV, "/org/pipewire/Telephony", AG, "/org/freedesktop/Notifications", "/mock"] + \
            [f"{AG}/call{i}" for i in range(1, 20)]
    for p in paths:
        for iname in IFS:
            c.register_object(p, IFS[iname], handle, None, None)
    for n in ("org.bluez", "org.pipewire.Telephony", "org.freedesktop.Notifications", "org.lica.Mock"):
        Gio.bus_own_name_on_connection(c, n, Gio.BusNameOwnerFlags.NONE, None, None)
    log("ready")


Gio.bus_get(Gio.BusType.SESSION, None, lambda _s, r: on_bus(Gio.bus_get_finish(r), None))
GLib.MainLoop().run()
