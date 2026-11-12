"""Contacts and call history from the iPhone over Bluetooth PBAP (bluez obexd).

Runs in a worker thread; the result is handed back on the GTK main loop.
Nothing leaves this machine: the vCards are parsed and the temp file deleted at once.
"""
import os
import quopri
import re
import tempfile
import threading
import time

from gi.repository import Gio, GLib

OBEX = "org.bluez.obex"
OBEX_ROOT = "/org/bluez/obex"
IF_CLIENT = "org.bluez.obex.Client1"
IF_PBAP = "org.bluez.obex.PhonebookAccess1"
IF_TRANSFER = "org.bluez.obex.Transfer1"


# ---------------------------------------------------------------- vCard ----
def _unfold(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for line in text.split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif out and out[-1].endswith("=") and "QUOTED-PRINTABLE" in out[-1].upper():
            out[-1] = out[-1][:-1] + line   # QP soft line break (vCard 2.1)
        else:
            out.append(line)
    return out

def _unescape(v):
    return v.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")

def _decode(params, value):
    up = [p.upper() for p in params]
    if any("QUOTED-PRINTABLE" in p for p in up):
        try:
            charset = "utf-8"
            for p in params:
                if p.upper().startswith("CHARSET="):
                    charset = p.split("=", 1)[1]
            value = quopri.decodestring(value.encode("latin-1", "ignore")).decode(charset, "replace")
        except Exception:
            pass
    return value

def parse_vcards(text):
    cards, cur = [], None
    for line in _unfold(text):
        if not line:
            continue
        if line.upper() == "BEGIN:VCARD":
            cur = {"name": "", "numbers": [], "call_type": "", "call_time": ""}
            continue
        if line.upper() == "END:VCARD":
            if cur is not None:
                cards.append(cur)
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parts = key.split(";")
        prop = parts[0].upper()
        if "." in prop:            # item1.TEL
            prop = prop.split(".", 1)[1]
        params = parts[1:]
        value = _decode(params, value)
        if prop == "FN":
            cur["name"] = _unescape(value).strip()
        elif prop == "N" and not cur["name"]:
            f = [x.strip() for x in value.split(";")]
            given = f[1] if len(f) > 1 else ""
            cur["name"] = _unescape(" ".join(x for x in (given, f[0]) if x)).strip()
        elif prop == "TEL":
            num = value.strip()
            if num:
                types = ",".join(params).upper()
                if "CELL" in types or "IPHONE" in types:
                    t = "mobile"
                elif "HOME" in types:
                    t = "home"
                elif "WORK" in types:
                    t = "work"
                elif "MAIN" in types or "PREF" in types:
                    t = "main"
                else:
                    t = "other"
                cur["numbers"].append([t, num])
        elif prop == "X-IRMC-CALL-DATETIME":
            ptxt = ",".join(params).upper()
            for t in ("MISSED", "RECEIVED", "DIALED"):
                if t in ptxt:
                    cur["call_type"] = t.lower()
            cur["call_time"] = value.strip()
    return cards


def digits(num):
    return re.sub(r"\D", "", num or "")

def number_key(num):
    """Key for caller-ID matching: last 9 digits (works for +48 / 0048 / plain)."""
    d = digits(num)
    return d[-9:] if len(d) >= 9 else d


def parse_irmc_time(s):
    """20261104T180501 or 20261104T180501Z -> epoch seconds (local)"""
    s = (s or "").strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S"):
        try:
            tm = time.strptime(s, fmt)
            if fmt.endswith("Z"):
                import calendar
                return calendar.timegm(tm)
            return time.mktime(tm)
        except ValueError:
            continue
    return 0


# ---------------------------------------------------------------- obexd ----
class PbapError(Exception):
    pass

def _pull(bus, mac, phonebook, max_count=None):
    sess = None
    tmpdir = tempfile.mkdtemp(prefix="lica-", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
    os.chmod(tmpdir, 0o700)
    target = os.path.join(tmpdir, phonebook + ".vcf")
    try:
        res = bus.call_sync(OBEX, OBEX_ROOT, IF_CLIENT, "CreateSession",
                            GLib.Variant("(sa{sv})", (mac, {"Target": GLib.Variant("s", "PBAP")})),
                            None, Gio.DBusCallFlags.NONE, 30000, None)
        sess = res.unpack()[0]
        bus.call_sync(OBEX, sess, IF_PBAP, "Select", GLib.Variant("(ss)", ("int", phonebook)),
                      None, Gio.DBusCallFlags.NONE, 15000, None)
        filters = {"Format": GLib.Variant("s", "vcard30")}
        if max_count:
            filters["MaxCount"] = GLib.Variant("q", max_count)
        res = bus.call_sync(OBEX, sess, IF_PBAP, "PullAll",
                            GLib.Variant("(sa{sv})", (target, filters)),
                            None, Gio.DBusCallFlags.NONE, 30000, None)
        transfer = res.unpack()[0]
        deadline = time.time() + 180
        status = "queued"
        while time.time() < deadline:
            try:
                r = bus.call_sync(OBEX, transfer, "org.freedesktop.DBus.Properties", "Get",
                                  GLib.Variant("(ss)", (IF_TRANSFER, "Status")), None,
                                  Gio.DBusCallFlags.NONE, 3000, None)
                status = r.unpack()[0]
            except GLib.Error:
                # object vanished: transfer finished (complete or error)
                status = "complete" if os.path.exists(target) and os.path.getsize(target) > 0 else "error"
            if status in ("complete", "error"):
                break
            time.sleep(0.25)
        if status != "complete":
            raise PbapError("transfer " + status)
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            return parse_vcards(f.read())
    except GLib.Error as e:
        raise PbapError(e.message)
    finally:
        if sess:
            try:
                bus.call_sync(OBEX, OBEX_ROOT, IF_CLIENT, "RemoveSession",
                              GLib.Variant("(o)", (sess,)), None, Gio.DBusCallFlags.NONE, 5000, None)
            except GLib.Error:
                pass
        try:
            if os.path.exists(target):
                os.remove(target)
            os.rmdir(tmpdir)
        except OSError:
            pass


_lock = threading.Lock()

def fetch_async(mac, callback, want_contacts=True):
    """callback(contacts|None, history|None, error|None) on the main loop."""
    def worker():
        with _lock:
            _work()

    def _work():
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        contacts = history = None
        err = None
        try:
            if want_contacts:
                cards = _pull(bus, mac, "pb")
                contacts = []
                for c in cards:
                    if c["numbers"] and c["name"]:
                        contacts.append({"name": c["name"], "numbers": c["numbers"]})
                contacts.sort(key=lambda c: c["name"].lower())
        except Exception as e:
            err = str(e)
        try:
            cards = _pull(bus, mac, "cch", max_count=200)
            history = []
            for c in cards:
                num = c["numbers"][0][1] if c["numbers"] else ""
                history.append({"name": c["name"], "number": num, "type": c["call_type"] or "received",
                                "time": parse_irmc_time(c["call_time"])})
            history.sort(key=lambda h: -h["time"])
        except Exception as e:
            print("PBAP history failed:", e)
        GLib.idle_add(lambda: (callback(contacts, history, err), False)[1])
    threading.Thread(target=worker, daemon=True).start()
