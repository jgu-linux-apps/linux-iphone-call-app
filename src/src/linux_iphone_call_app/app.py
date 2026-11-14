"""Linux iPhone Calls — answer and make iPhone calls on Ubuntu over Bluetooth hands-free."""
import os
import sys
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, APP_NAME, BUILD_DATE, CREATED_BY, SUPPORTED_BY, VERSION, media, pbap  # noqa: E402
from .audio import CallAudio, Ringer, aec_available, pipewire_version, pw_dump  # noqa: E402
from .bluez import Bluez  # noqa: E402
from .config import (CONTACTS_FILE, LOCAL_LOG_FILE, RECENTS_FILE, Config,  # noqa: E402
                     autostart_enabled, load_json, save_json, set_autostart)
from .i18n import _  # noqa: E402
from .notify import Notifier  # noqa: E402
from .telephony import LIVE, RINGING, Telephony  # noqa: E402
from .theme import Theme  # noqa: E402
from .aurora3 import AuroraTheme3  # noqa: E402
from .tray import Tray  # noqa: E402
from .ui import IncomingPopup, MainWindow, install_css  # noqa: E402

CONTACTS_MAX_AGE = 6 * 3600
CODECS = {1: "CVSD 8 kHz (narrowband)", 2: "mSBC 16 kHz (wideband)", 3: "LC3-SWB 32 kHz"}


def data_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.environ.get("LICA_DATA_DIR"),
              os.path.join(here, "..", "..", "data"),
              "/usr/share/linux-iphone-call-app"):
        if d and os.path.isdir(os.path.join(d, "icons")):
            return os.path.abspath(d)
    return "/usr/share/linux-iphone-call-app"


def clean_number(text):
    return "".join(ch for ch in (text or "") if ch in "+0123456789*#")



def AURORA_EXTRA(p, dark):
    """Klawiatura, kafle narzędzi i awatary w kolorach Aurory (zielony/czerwony przycisk rozmowy bez zmian)."""
    a, a2 = p["accent"], p["accent2"]
    glow = a2 if dark else a
    return f"""
.lica-key {{ background-color: {'alpha(#FFFFFF, 0.06)' if dark else 'alpha(#FFFFFF, 0.85)'};
    border: 1px solid {p['border']}; transition: all 150ms ease-out; }}
.lica-key:hover {{ background-color: {p['hover']}; box-shadow: 0 0 0 1px alpha({glow}, 0.55), 0 0 14px alpha({glow}, 0.28); }}
.lica-key:active {{ background-image: linear-gradient(to right, alpha({a}, 0.55), alpha({a2}, 0.45)); }}
.lica-tool {{ background-color: {'alpha(#FFFFFF, 0.06)' if dark else 'alpha(#FFFFFF, 0.85)'}; border: 1px solid {p['border']}; }}
.lica-tool:checked {{ background-image: linear-gradient(to right, {a}, {a2}); color: #FFFFFF; }}
.lica-pill.lica-neutral {{ background-color: {p['hover']}; }}
.lica-avatar {{ background-image: linear-gradient(160deg, {a}, {a2}); }}
.lica-bottom {{ border-top-color: {p['border']}; }}
.lica-number {{ background-color: transparent; border: none; box-shadow: none; }}
.lica-round, .lica-pill.lica-green, .lica-pill.lica-red {{ border: none; }}
.lica-green {{ background-image: none; background-color: #30c75a; }}
.lica-red {{ background-image: none; background-color: #ff3b30; }}
"""

class Controller:
    def __init__(self, app, hidden):
        self.app = app
        self.cfg = Config()
        if not self.cfg.get("first_run_done"):
            set_autostart(True)          # a phone app is only useful when it's running
            self.cfg.set("first_run_done", True)

        self.pending_wp_restart = False
        if not self.cfg.get("media_rule_initialized"):
            self.cfg.set("media_rule_initialized", True)
            try:
                if media.set_enabled(True):
                    self.pending_wp_restart = True
            except OSError as e:
                print("media rule:", e)

        self.icon_dir = os.path.join(data_dir(), "icons")
        Gtk.IconTheme.get_default().append_search_path(self.icon_dir)

        self.theme = Theme()
        self.look = AuroraTheme3(extra=AURORA_EXTRA)
        self.look.apply(self.cfg.get("theme"), self.theme.dark)
        self.bluez = Bluez()
        self.bluez.preferred = self.cfg.get("device")
        self.tel = Telephony()
        self.tel.preferred_mac = self.bluez.phone_mac()
        self.audio = CallAudio()
        self.ringer = Ringer(os.path.join(data_dir(), "sounds"))
        self.ringer.set_sound(self.cfg.get("ringtone_sound"))
        self.notifier = Notifier(APP_NAME, self._on_notification_action)

        c = load_json(CONTACTS_FILE, {})
        self.contacts = c.get("contacts", [])
        self.contacts_ts = c.get("ts", 0)
        self.history = load_json(RECENTS_FILE, {}).get("items", [])
        self.local_log = load_json(LOCAL_LOG_FILE, [])
        self._index()

        self.choice = {}               # call path -> laptop | iphone | reject
        self.notified = set()
        self.next_dial_choice = None
        self.want_reject_sco = False   # user wants call audio on the iPhone
        self.handoff_call = None       # phantom call shown while HFP is re-connecting
        self.handoff_until = 0
        self.profile_off = False
        self.user_disconnected = False
        self.loading = False
        self.contacts_note = None
        self.unseen_missed = 0
        self._had_ag = False
        self._pw_version = None
        self._last_missed = None

        self.win = MainWindow(app, self)
        self.popup = IncomingPopup(app, self)
        self.tray = Tray(self.icon_dir, self.show)
        self._build_menu()
        self._apply_icons()
        self.theme.connect("changed", lambda *_a: (self._apply_icons(), self.look.apply(self.cfg.get("theme"), self.theme.dark)))

        self.bluez.connect("changed", lambda *_a: self._on_bluez())
        self.tel.connect("changed", lambda *_a: self._on_tel_changed())
        self.tel.connect("call-added", lambda _t, p: self._on_call_added(p))
        self.tel.connect("call-changed", lambda _t, p: self._on_call_changed(p))
        self.tel.connect("call-removed", lambda _t, p, c: self._on_call_removed(p, c))
        self.tel.connect("transport-changed", lambda *_a: self._on_transport())

        self.win.set_contacts(self.contacts)
        self.win.set_recents(self._merged_recents())
        # a previous run may have left the phone's sound card off (call moved to iPhone)
        GLib.timeout_add_seconds(2, lambda: (self.audio.restore_profile_if_off(self.bluez.phone_mac())
                                             if self.bluez.phone_mac() and not self.tel.calls else None, False)[1])
        if self.pending_wp_restart:
            GLib.timeout_add_seconds(2, lambda: (self._apply_wp_restart(), False)[1])
        GLib.timeout_add_seconds(25, self._watchdog)
        GLib.timeout_add(1500, lambda: (self._watchdog(), False)[1])
        self.refresh_ui()
        if not hidden:
            self.show()

    # ============================================================ helpers ==
    def _index(self):
        self.idx = {}
        for c in self.contacts:
            for _t, n in c["numbers"]:
                k = pbap.number_key(n)
                if k and k not in self.idx:
                    self.idx[k] = c["name"]

    def name_for(self, number):
        return self.idx.get(pbap.number_key(number), "") if number else ""

    def resolve_dial_target(self, text):
        num = clean_number(text)
        if sum(ch.isdigit() for ch in num) >= 2 and len(num) >= len(text.replace(" ", "").replace("-", "")) - 1:
            return num
        q = text.lower().split()
        for c in self.contacts:
            if q and all(w in c["name"].lower() for w in q):
                return c["numbers"][0][1]
        return num

    def _apply_icons(self):
        Gtk.Window.set_default_icon_name(self.theme.app_icon)
        for w in (self.win, self.popup):
            w.set_icon_name(self.theme.app_icon)

    def show(self):
        self.unseen_missed = 0
        self.win.present()
        self.refresh_ui()

    def _ringing(self):
        for c in self.tel.calls.values():
            if c["state"] in RINGING:
                return c
        return None

    def _live(self):
        for st in ("active", "alerting", "dialing", "held"):
            for c in self.tel.calls.values():
                if c["state"] == st:
                    return c
        return None

    def _display_name(self, c):
        return self.name_for(c.get("number")) or c.get("name") or ""

    # ============================================================= events ==
    def _on_bluez(self):
        mac = self.bluez.phone_mac()
        if mac and mac != self.tel.preferred_mac:
            self.tel.preferred_mac = mac
        self._build_menu()
        self.refresh_ui()

    def _on_tel_changed(self):
        has_ag = bool(self.tel.ag())
        if has_ag and not self._had_ag:
            # (re)connected
            if self.want_reject_sco and (self.tel.calls or self.handoff_call):
                self.tel.set_reject_sco(True)
            elif self.handoff_call and not self.want_reject_sco:
                self.tel.set_reject_sco(False)
                GLib.timeout_add(800, self._ensure_laptop_audio)
            if not self.contacts or time.time() - self.contacts_ts > CONTACTS_MAX_AGE:
                GLib.timeout_add_seconds(3, lambda: (self.refresh_contacts(), False)[1])
        self._had_ag = has_ag
        if has_ag and self.handoff_call:
            GLib.timeout_add(1500, self._finish_handoff)
        self.refresh_ui()

    def _finish_handoff(self):
        if self.handoff_call and not self._live() and not self._ringing():
            # reconnected and the call is gone: it ended on the iPhone meanwhile
            self._log_call(self.handoff_call, "iphone")
            self.handoff_call = None
            self._calls_finished()
        self.refresh_ui()
        return False

    def _on_call_added(self, path):
        c = self.tel.calls.get(path)
        if not c:
            return
        if self.handoff_call and c["state"] in LIVE:
            c["active_since"] = self.handoff_call.get("active_since") or c["active_since"]
            c["was_ringing"] = self.handoff_call.get("was_ringing", False)
            c["answered"] = True
            self.choice[path] = "iphone" if self.want_reject_sco else "laptop"
            self.handoff_call = None
        if c["state"] in RINGING:
            self._incoming(c)
        elif path not in self.choice:
            self.choice[path] = self.next_dial_choice or "iphone"
            self.next_dial_choice = None
            if self.choice[path] == "laptop":
                GLib.timeout_add(1200, self._ensure_laptop_audio)
        self.refresh_ui()

    def _on_call_changed(self, path):
        c = self.tel.calls.get(path)
        if not c:
            return
        if c["state"] in RINGING:
            self._incoming(c)
        elif c["state"] == "active" and c["was_ringing"]:
            if path in self.notified:
                self.notified.discard(path)
                self._stop_ringing_ui()
            ch = self.choice.setdefault(path, "iphone")   # answered on the phone itself
            if ch == "iphone":
                self.want_reject_sco = True
                GLib.timeout_add(400, self._enforce_iphone)
        self._on_transport()
        self.refresh_ui()

    def _on_call_removed(self, path, c):
        ch = self.choice.pop(path, None)
        self.notified.discard(path)
        if (time.time() < self.handoff_until or self.profile_off) and c.get("answered") and not self.tel.calls:
            # maybe the hands-free link dropped on purpose (move to iPhone): keep showing the call,
            # unless the phone link is still there a moment later (then the call really ended)
            self.handoff_call = dict(c)
            self.choice[path] = ch
            GLib.timeout_add(1200, self._check_handoff, path, ch)
            self.refresh_ui()
            return
        self._log_call(c, ch)
        if not self._ringing():
            self._stop_ringing_ui()
        if not self.tel.calls:
            self._calls_finished()
        self.refresh_ui()

    def _check_handoff(self, path, ch):
        self.choice.pop(path, None)
        if self.handoff_call and self.tel.ag() and not self.tel.calls:
            c, self.handoff_call = self.handoff_call, None
            self.handoff_until = 0
            self._log_call(c, ch)
            self._calls_finished()
            self.refresh_ui()
        return False

    def _calls_finished(self):
        if self.profile_off:
            self.profile_off = False
            self.audio.restore_profile_if_off(self.bluez.phone_mac())
        if self.pending_wp_restart:
            GLib.timeout_add_seconds(2, lambda: (self._apply_wp_restart(), False)[1])
        self.audio.stop()
        self.win.mute_btn.set_active(False)
        self.want_reject_sco = False
        self.tel.set_reject_sco(False)
        self.audio.mac = self.bluez.phone_mac()
        GLib.timeout_add_seconds(4, lambda: (self.refresh_history(), False)[1])

    def audio_here(self):
        """Is the call audio really on the laptop right now?"""
        return self.tel.audio_on_laptop() and not self.profile_off

    def _on_transport(self):
        live = any(c["state"] in LIVE for c in self.tel.calls.values())
        if live and self.want_reject_sco:
            # the user wants the iPhone: never route here, push it back if the phone grabbed it
            self.audio.stop_routing()
            if self.audio_here():
                GLib.timeout_add(300, self._enforce_iphone)
        elif live and self.audio_here():
            if not self.audio.routing():
                self.audio.start(self.bluez.phone_mac(), aec=bool(self.cfg.get("aec")))
        elif not self.audio_here():
            self.audio.stop_routing()
        self.refresh_ui()

    def _log_call(self, c, choice):
        if c.get("was_ringing") and not c.get("answered"):
            typ = "missed"
        else:
            typ = "received" if c.get("was_ringing") else "dialed"
        entry = {"number": c.get("number", ""), "name": self._display_name(c), "type": typ,
                 "time": c.get("first_seen") or time.time()}
        self.local_log.insert(0, entry)
        del self.local_log[300:]
        save_json(LOCAL_LOG_FILE, self.local_log)
        if typ == "missed" and choice != "reject":
            self.unseen_missed += 1
            who = entry["name"] or entry["number"] or _("private")
            self._last_missed = entry["number"]
            self.notifier.show("missed", _("missed"), who, self.theme.app_icon,
                               actions=[("default", _("show")), ("callback", _("call_back"))]
                               if entry["number"] else [("default", _("show"))],
                               category="call.unanswered")
        self.win.set_recents(self._merged_recents())

    def _merged_recents(self):
        newest = max((h.get("time", 0) for h in self.history), default=0)
        extra = [e for e in self.local_log if e.get("time", 0) > newest + 5]
        items = extra + (self.history if self.history else self.local_log[len(extra):])
        return sorted(items, key=lambda e: -e.get("time", 0))

    # ============================================================ ringing ==
    def _incoming(self, c):
        if c["path"] in self.notified or self.choice.get(c["path"]) in ("iphone", "reject"):
            return
        self.notified.add(c["path"])
        name = self._display_name(c)
        num = c.get("number") or ""
        waiting = c["state"] == "waiting"
        self.popup.present_call(name, num, waiting)
        body = "\n".join(x for x in (name, num) if x) or _("private")
        self.notifier.show("call", _("incoming_waiting") if waiting else _("incoming"), body,
                           self.theme.app_icon,
                           actions=[("answer", _("answer_short")), ("iphone", _("on_iphone")),
                                    ("reject", _("reject"))],
                           urgent=True, resident=True, category="x-gnome.call", timeout=0)
        if self.cfg.get("ringtone") and not self._live():
            self.ringer.start()
        self.refresh_ui()

    def _stop_ringing_ui(self):
        self.ringer.stop()
        self.popup.hide()
        self.notifier.close("call")

    def _on_notification_action(self, tag, key):
        if tag == "call":
            {"answer": self.answer_laptop, "iphone": self.answer_iphone,
             "reject": self.reject}.get(key, self.show)()
        elif tag == "missed":
            if key == "callback" and self._last_missed:
                self.dial(self._last_missed)
            self.show()

    # ============================================================ actions ==
    def answer_laptop(self):
        c = self._ringing()
        self._stop_ringing_ui()
        if not c:
            return
        self.choice[c["path"]] = "laptop"
        self.want_reject_sco = False
        self.tel.set_reject_sco(False)
        self.audio.mac = self.bluez.phone_mac()
        self.profile_off = False
        GLib.idle_add(lambda: (self.audio._ensure_hfp_profile(pw_dump()), False)[1])

        def done(ok, _r):
            if ok:
                GLib.timeout_add(700, self._ensure_laptop_audio)
        if c["state"] == "waiting":
            self.tel.hold_and_answer(done)
        else:
            self.tel.answer(c["path"], done)
        self.show()

    def _ensure_laptop_audio(self):
        if self.tel.calls and not self.tel.audio_on_laptop() and not self.want_reject_sco:
            self.tel.activate_audio()
        return False

    def answer_iphone(self):
        c = self._ringing()
        self._stop_ringing_ui()
        if not c:
            return
        self.choice[c["path"]] = "iphone"
        self.want_reject_sco = True
        self.tel.set_reject_sco(True)
        name = self._display_name(c) or c.get("number") or _("private")
        self.notifier.show("call", _("incoming"), f"{name}\n{_('ringing_on_iphone')}", self.theme.app_icon,
                           actions=[("answer", _("answer_laptop")), ("reject", _("reject"))],
                           category="x-gnome.call")
        self.refresh_ui()

    def reject(self):
        c = self._ringing()
        self._stop_ringing_ui()
        if c:
            self.choice[c["path"]] = "reject"
            self.tel.hangup(c["path"])

    def hangup(self):
        self.handoff_until = 0
        c = self._live() or self._ringing()
        if c:
            self.tel.hangup(c["path"])
        elif self.handoff_call:
            self.handoff_call = None
            self._calls_finished()
            self.refresh_ui()

    def toggle_route(self):
        if self.audio_here():
            self.move_to_iphone()
        else:
            self.move_to_laptop()

    def move_to_iphone(self):
        """Hand the call audio back to the handset: the hands-free unit releases the audio
        link (sound card off); the hands-free control link stays up, so the iPhone does not
        pull the call back like it does when a car (re)connects."""
        for p in self.tel.calls:
            self.choice[p] = "iphone"
        self.want_reject_sco = True
        self.audio.stop_routing()
        self._enforce_iphone()
        self.refresh_ui()

    def _enforce_iphone(self):
        if not self.want_reject_sco or not self.tel.calls:
            return False
        self.tel.set_reject_sco(True)
        if self.audio_here() or self.tel.audio_on_laptop():
            mac = self.bluez.phone_mac()
            if self.audio.set_profile_off(mac):
                self.profile_off = True
            else:
                self.notifier.show("route", APP_NAME, _("route_hint"), self.theme.app_icon)
        self.refresh_ui()
        return False

    def move_to_laptop(self):
        for p in self.tel.calls:
            self.choice[p] = "laptop"
        self.want_reject_sco = False
        self.notifier.close("route")
        if self.profile_off:
            self.profile_off = False
            self.audio.restore_profile_if_off(self.bluez.phone_mac())
        if self.tel.ag():
            self.audio.mac = self.bluez.phone_mac()
            self.profile_off = False
            self.audio._ensure_hfp_profile(pw_dump())
            self.tel.set_reject_sco(False)
            GLib.timeout_add(600, lambda: (self.tel.activate_audio(), False)[1])
        else:
            self.user_disconnected = False
            self.bluez.connect_hfp()
        self.refresh_ui()

    def set_mute(self, on):
        self.audio.set_mute(on)

    def send_dtmf(self, d):
        self.tel.send_tones(d)

    def dial(self, number):
        number = clean_number(number)
        if not number:
            return
        if not self.tel.available or not self.tel.ag():
            self._error(_("dial_failed", _("not_connected")))
            return
        self.next_dial_choice = "laptop"
        self.want_reject_sco = False
        self.profile_off = False
        self.audio.mac = self.bluez.phone_mac()
        self.audio.restore_profile_if_off()
        self.tel.set_reject_sco(False)
        self.audio.mac = self.bluez.phone_mac()

        def done(ok, res):
            if ok:
                GLib.timeout_add(1200, self._ensure_laptop_audio)
            else:
                self.next_dial_choice = None
                self._error(_("dial_failed", res))
        self.tel.dial(number, done)
        self.win.number.set_text("")
        self.show()

    def toggle_connection(self):
        if self.tel.ag():
            self.user_disconnected = True
            self.bluez.disconnect_hfp(lambda *_a: self.refresh_ui())
        else:
            self.user_disconnected = False
            self._connecting = True
            self.refresh_ui()

            def done(ok, err):
                self._connecting = False
                if not ok:
                    print("connect failed:", err)
                self.refresh_ui()
            self.bluez.connect_hfp(done)

    def set_ringtone_sound(self, name):
        self.cfg.set("ringtone_sound", name)
        self.ringer.set_sound(name)
        self.ringer.preview(name)          # let the user hear it right away

    def set_aec(self, on):
        self.cfg.set("aec", on)
        if self.tel.calls and self.audio_here():
            self.audio.start(self.bluez.phone_mac(), aec=on)   # re-route live

    # ====================================================== media on iPhone ==
    def set_media_on_iphone(self, on):
        try:
            changed = media.set_enabled(on)
        except OSError as e:
            self._error(str(e))
            return
        if changed:
            self.pending_wp_restart = True
            self._apply_wp_restart()

    def _apply_wp_restart(self):
        """Restart WirePlumber only when no call is going on, then re-connect the iPhone."""
        if not self.pending_wp_restart:
            return
        if self.tel.calls or self.handoff_call:
            return          # retried from _calls_finished
        self.pending_wp_restart = False

        def done(ok):
            print("wireplumber restart:", "ok" if ok else "failed")
            # the hands-free link drops with WirePlumber: bring it back (without media audio)
            GLib.timeout_add_seconds(3, lambda: (self.bluez.connect_hfp(), False)[1])
        media.restart_wireplumber(done)

    def _watchdog(self):
        if (self.tel.available and not self.tel.ag() and self.bluez.phone()
                and not self.user_disconnected and time.time() > self.handoff_until and not self.profile_off):
            self.bluez.connect_hfp()
        if self.tel.ag() and not self.loading and time.time() - self.contacts_ts > CONTACTS_MAX_AGE:
            self.refresh_contacts()
        return True

    # =========================================================== contacts ==
    def refresh_contacts(self):
        mac = self.bluez.phone_mac()
        if not mac or self.loading:
            return
        self.loading = True
        if not self.contacts:
            self.win.set_contacts([], _("contacts_loading"))
        pbap.fetch_async(mac, self._contacts_done, want_contacts=True)

    def refresh_history(self):
        mac = self.bluez.phone_mac()
        if mac and self.tel.ag():
            pbap.fetch_async(mac, self._contacts_done, want_contacts=False)

    def _contacts_done(self, contacts, history, err):
        if contacts is not None:
            self.loading = False
            self.contacts = contacts
            self.contacts_ts = time.time()
            save_json(CONTACTS_FILE, {"ts": self.contacts_ts, "contacts": contacts})
            self._index()
            self.win.set_contacts(self.contacts)
        elif err:
            self.loading = False
            print("PBAP contacts failed:", err)
            self.contacts_ts = time.time() - CONTACTS_MAX_AGE + 600   # retry in 10 min
            self.win.set_contacts(self.contacts, None if self.contacts else _("contacts_failed"))
        if history is not None:
            self.history = history
            save_json(RECENTS_FILE, {"items": history})
        self.win.set_recents(self._merged_recents())

    # ================================================================ ui ===
    def refresh_ui(self):
        if self._pw_version is None and not self.tel.available:
            self._pw_version = pipewire_version()
        phone = self.bluez.phone()
        if not self.tel.available:
            self.win.set_banner(_("telephony_missing", self._pw_version or "?"))
        else:
            self.win.set_banner(None)
        connected = bool(self.tel.ag())
        if not phone:
            status = _("no_iphone")
        elif connected:
            status = _("connected_to", self.bluez.phone_name())
        elif getattr(self, "_connecting", False):
            status = _("connecting")
        else:
            status = _("not_connected")
        self.win.set_status(connected, status, can_connect=bool(phone) and self.tel.available)

        ringing = self._ringing()
        live = self._live()
        call = ringing or live or self.handoff_call
        if call:
            note = None
            if live and not self.audio_here():
                note = _("call_on_iphone")
            elif self.handoff_call and not live:
                note = _("call_on_iphone")
            elif ringing and self.choice.get(ringing["path"]) == "iphone":
                note = _("ringing_on_iphone")
            self.win.show_call(call, self._display_name(call), self.audio_here(), note)
        else:
            self.win.show_call(None, "", False)

        if ringing:
            state = "ringing"
        elif live or self.handoff_call:
            state = "incall"
        elif self.unseen_missed:
            state = "missed"
        elif connected:
            state = "idle"
        else:
            state = "offline"
        self.tray.set_state(state, f"{APP_NAME} — {status}")

        items = [(status, None), None, (_("show"), self.show)]
        if ringing:
            items += [None, (_("answer_laptop"), self.answer_laptop), (_("on_iphone_long"), self.answer_iphone),
                      (_("reject"), self.reject)]
        elif live:
            items += [None, (_("to_iphone") if self.audio_here() else _("to_laptop"), self.toggle_route),
                      (_("hangup"), self.hangup)]
        items += [None]
        if phone and self.tel.available:
            items += [(_("disconnect") if connected else _("connect"), self.toggle_connection)]
        items += [(_("quit"), self.quit)]
        self.tray.set_menu(items)

    def _error(self, text):
        d = Gtk.MessageDialog(transient_for=self.win, modal=True, message_type=Gtk.MessageType.ERROR,
                              buttons=Gtk.ButtonsType.CLOSE, text=text)
        d.connect("response", lambda d, *_a: d.destroy())
        d.show()

    def show_diagnostics(self):
        ph = self.bluez.phone()
        tr = self.tel.transport()
        lines = [
            f"{APP_NAME} {VERSION} ({BUILD_DATE})",
            CREATED_BY,
            SUPPORTED_BY,
            f"PipeWire: {pipewire_version()}",
            f"org.pipewire.Telephony: {'OK' if self.tel.available else '—'}",
            f"iPhone: {(ph[1].get('Alias') or ph[1].get('Name')) + ' ' + (ph[1].get('Address') or '') if ph else '—'}",
            f"Bluetooth connected: {bool(ph and ph[1].get('Connected'))}",
            f"Hands-free (HFP) gateway: {self.tel.ag() or '—'}",
            f"Audio transport: {tr.get('State', '—')}  codec={CODECS.get(tr.get('Codec'), tr.get('Codec', '—'))}  RejectSCO={tr.get('RejectSCO', '—')}",
            f"Echo/noise cancel (WebRTC): {'on' if self.cfg.get('aec') else 'off'}, available={aec_available()}",
            f"Calls: {len(self.tel.calls)}",
            f"Contacts cached: {len(self.contacts)}",
            f"App audio stays on iPhone (no a2dp_sink): {media.enabled()}  WirePlumber {'.'.join(map(str, media.wireplumber_version()))}",
        ]
        if not self.tel.available:
            lines += ["", _("telephony_missing", pipewire_version())]
        d = Gtk.MessageDialog(transient_for=self.win, modal=True, message_type=Gtk.MessageType.INFO,
                              buttons=Gtk.ButtonsType.CLOSE, text=_("diagnostics"))
        d.format_secondary_text("\n".join(lines))
        for ch in d.get_message_area().get_children():
            if isinstance(ch, Gtk.Label):
                ch.set_selectable(True)
        d.connect("response", lambda d, *_a: d.destroy())
        d.show()

    def show_about(self):
        d = Gtk.AboutDialog(transient_for=self.win, modal=True)
        d.set_program_name(APP_NAME)
        d.set_version(f"{VERSION} · {BUILD_DATE}")
        d.set_logo_icon_name(self.theme.app_icon)
        d.set_comments(f"{_('about_desc')}\n\n{CREATED_BY}\n{SUPPORTED_BY}")
        d.set_license_type(Gtk.License.CUSTOM)
        d.set_license("Freeware License (No Modifications).\nFree to use and to share unmodified; modification is not permitted.\nSee /usr/share/doc/linux-iphone-call-app/copyright.")
        d.connect("response", lambda d, *_a: d.destroy())
        d.show()

    def _build_menu(self):
        app = self.app
        def add(name, cb, state=None, ptype=None):
            if app.lookup_action(name):
                app.remove_action(name)
            if state is not None:
                a = Gio.SimpleAction.new_stateful(name, None, GLib.Variant("b", state))
                a.connect("change-state", lambda a, v: (a.set_state(v), cb(v.get_boolean())))
            else:
                a = Gio.SimpleAction.new(name, ptype)
                a.connect("activate", lambda _a, p: cb(p))
            app.add_action(a)
        add("ringtone", lambda v: self.cfg.set("ringtone", v), state=bool(self.cfg.get("ringtone")))
        add("autostart", set_autostart, state=autostart_enabled())
        add("media-on-iphone", self.set_media_on_iphone, state=media.enabled())
        add("aec", self.set_aec, state=bool(self.cfg.get("aec")))
        if app.lookup_action("ringtone-sound"):
            app.remove_action("ringtone-sound")
        snd = Gio.SimpleAction.new_stateful("ringtone-sound", GLib.VariantType.new("s"),
                                            GLib.Variant("s", self.ringer.name))
        snd.connect("change-state", lambda a, v: (a.set_state(v), self.set_ringtone_sound(v.get_string())))
        app.add_action(snd)
        if app.lookup_action("theme"):
            app.remove_action("theme")
        th = Gio.SimpleAction.new_stateful("theme", GLib.VariantType.new("s"), GLib.Variant("s", self.look.name))
        th.connect("change-state", lambda a, v: (a.set_state(v), self.set_theme(v.get_string())))
        app.add_action(th)
        add("refresh", lambda _p: self.refresh_contacts())
        add("diagnostics", lambda _p: self.show_diagnostics())
        add("about", lambda _p: self.show_about())
        add("quit", lambda _p: self.quit())
        add("device", self._choose_device, ptype=GLib.VariantType.new("s"))
        # call actions (also reachable from notifications / scripts)
        add("show", lambda _p: self.show())
        add("answer", lambda _p: self.answer_laptop())
        add("answer-iphone", lambda _p: self.answer_iphone())
        add("reject", lambda _p: self.reject())
        add("hangup", lambda _p: self.hangup())
        add("route", lambda _p: self.toggle_route())
        add("dial", lambda p: self.dial(p.get_string()), ptype=GLib.VariantType.new("s"))
        add("tab", lambda p: (self.show(), self.win.tabs.set_visible_child_name(p.get_string())),
            ptype=GLib.VariantType.new("s"))
        add("preview-tone", lambda p: self.ringer.preview(p.get_string()), ptype=GLib.VariantType.new("s"))
        add("search", lambda p: (self.win.tabs.set_visible_child_name("contacts"),
                                 self.win.search.set_text(p.get_string())),
            ptype=GLib.VariantType.new("s"))

        menu = Gio.Menu()
        sec = Gio.Menu()
        sec.append(_("ringtone"), "app.ringtone")
        sec.append(_("autostart"), "app.autostart")
        sec.append(_("media_on_iphone"), "app.media-on-iphone")
        sec.append(_("aec"), "app.aec")
        menu.append_section(None, sec)
        tones = Gio.Menu()
        for key in ("morning", "wave", "droplet", "system"):
            it = Gio.MenuItem.new(_("tone_" + key), None)
            it.set_action_and_target_value("app.ringtone-sound", GLib.Variant("s", key))
            tones.append_item(it)
        menu.append_submenu(_("ringtone_sound"), tones)
        looks = Gio.Menu()
        for key in ("system", "aurora"):
            it = Gio.MenuItem.new(_("theme_" + key), None)
            it.set_action_and_target_value("app.theme", GLib.Variant("s", key))
            looks.append_item(it)
        menu.append_submenu(_("theme"), looks)
        phones = self.bluez.phones()
        if len(phones) > 1:
            sub = Gio.Menu()
            for _p, d in phones:
                item = Gio.MenuItem.new(d.get("Alias") or d.get("Name") or d.get("Address"), None)
                item.set_action_and_target_value("app.device", GLib.Variant("s", d.get("Address", "")))
                sub.append_item(item)
            menu.append_submenu(_("choose_iphone"), sub)
        sec2 = Gio.Menu()
        sec2.append(_("refresh_contacts"), "app.refresh")
        sec2.append(_("diagnostics"), "app.diagnostics")
        sec2.append(_("about"), "app.about")
        menu.append_section(None, sec2)
        sec3 = Gio.Menu()
        sec3.append(_("quit"), "app.quit")
        menu.append_section(None, sec3)
        self.win.menu_btn.set_menu_model(menu)

    def set_theme(self, name):
        self.cfg.set("theme", name)
        self.look.apply(name, self.theme.dark)

    def _choose_device(self, param):
        mac = param.get_string()
        self.cfg.set("device", mac)
        self.bluez.preferred = mac
        self.tel.preferred_mac = mac
        self.contacts_ts = 0
        self.refresh_ui()
        self.refresh_contacts()

    def quit(self):
        self.ringer.stop()
        self.audio.stop()
        self.notifier.close("call")
        self.app.quit()


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.ctl = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        GLib.set_application_name(APP_NAME)
        install_css()

    def do_command_line(self, cmdline):
        args = cmdline.get_arguments()
        hidden = "--hidden" in args
        if "--version" in args:
            cmdline.print_literal(f"{APP_NAME} {VERSION} ({BUILD_DATE})\n")
            return 0
        if self.ctl is None:
            self.hold()
            self.ctl = Controller(self, hidden)
        elif not hidden:
            self.ctl.show()
        return 0


def main():
    GLib.set_prgname("linux-iphone-call-app")
    return App().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
