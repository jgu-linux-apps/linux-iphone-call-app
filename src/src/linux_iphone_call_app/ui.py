"""GTK3 windows: main window (keypad / contacts / recents / call view) and incoming-call popup."""
import time

from gi.repository import Gdk, GLib, Gtk, Pango

from . import APP_NAME, BUILD_DATE, VERSION
from .i18n import _

CSS = b"""
.lica-root { }
.lica-number { font-size: 28px; font-weight: 300; padding: 10px 6px; border: none; box-shadow: none;
               background: transparent; }
.lica-key { border-radius: 999px; min-width: 70px; min-height: 70px; padding: 0;
            background-image: none; border: none; box-shadow: none;
            background-color: alpha(currentColor, 0.08); }
.lica-key:hover { background-color: alpha(currentColor, 0.14); }
.lica-key:active { background-color: alpha(currentColor, 0.24); }
.lica-key-digit { font-size: 26px; font-weight: 400; }
.lica-key-letters { font-size: 9px; font-weight: 700; letter-spacing: 2px; opacity: .6; }
.lica-round { border-radius: 999px; min-width: 64px; min-height: 64px; padding: 0;
              background-image: none; border: none; box-shadow: none; color: #fff; }
.lica-green { background-color: #30c75a; }
.lica-green:hover { background-color: #3ad466; }
.lica-red { background-color: #ff3b30; }
.lica-red:hover { background-color: #ff5147; }
.lica-pill { border-radius: 999px; padding: 10px 18px; background-image: none; border: none; box-shadow: none;
             font-weight: 600; }
.lica-pill.lica-green, .lica-pill.lica-red { color: #fff; }
.lica-pill.lica-neutral { background-color: alpha(currentColor, 0.10); }
.lica-tool { border-radius: 16px; padding: 10px 6px; min-width: 92px; background-image: none; border: none;
             box-shadow: none; background-color: alpha(currentColor, 0.08); }
.lica-tool:checked { background-color: alpha(currentColor, 0.85); color: @theme_bg_color; }
.lica-avatar { border-radius: 999px; color: #fff; font-weight: 700;
               background-image: linear-gradient(160deg, #8e9db4, #5d6b82); }
.lica-avatar-big { font-size: 40px; }
.lica-avatar-small { font-size: 14px; }
.lica-name-big { font-size: 26px; font-weight: 600; }
.lica-dim { opacity: .62; }
.lica-small { font-size: 11px; }
.lica-missed { color: #ff3b30; }
.lica-row { padding: 8px 12px; }
.lica-bottom { padding: 4px 10px; border-top: 1px solid alpha(currentColor, 0.10); }
.lica-dot-on { color: #30c75a; }
.lica-dot-off { color: #8e8e93; }
.lica-popup { border-radius: 18px; }
.lica-popup-title { font-weight: 700; font-size: 12px; letter-spacing: 1px; opacity: .7; }
"""

KEYS = [("1", ""), ("2", "ABC"), ("3", "DEF"), ("4", "GHI"), ("5", "JKL"), ("6", "MNO"),
        ("7", "PQRS"), ("8", "TUV"), ("9", "WXYZ"), ("*", ""), ("0", "+"), ("#", "")]


def install_css():
    prov = Gtk.CssProvider()
    prov.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def initials(name):
    parts = [p for p in (name or "").replace("+", " ").split() if p and p[0].isalpha()]
    if not parts:
        return "#"
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()


def avatar(name, size, cls):
    lbl = Gtk.Label(label=initials(name))
    lbl.set_size_request(size, size)
    ctx = lbl.get_style_context()
    ctx.add_class("lica-avatar")
    ctx.add_class(cls)
    lbl.set_halign(Gtk.Align.CENTER)
    lbl.set_valign(Gtk.Align.CENTER)
    return lbl


def cls(widget, *names):
    for n in names:
        widget.get_style_context().add_class(n)
    return widget


def icon_button(icon, css, tooltip=None, size=Gtk.IconSize.LARGE_TOOLBAR):
    b = Gtk.Button()
    b.add(Gtk.Image.new_from_icon_name(icon, size))
    cls(b, *css)
    if tooltip:
        b.set_tooltip_text(tooltip)
    b.set_halign(Gtk.Align.CENTER)
    return b


def fmt_time(ts):
    if not ts:
        return ""
    lt = time.localtime(ts)
    now = time.localtime()
    if lt.tm_yday == now.tm_yday and lt.tm_year == now.tm_year:
        return time.strftime("%H:%M", lt)
    y = time.localtime(time.time() - 86400)
    if lt.tm_yday == y.tm_yday and lt.tm_year == y.tm_year:
        return _("yesterday")
    return time.strftime("%d.%m.%Y", lt)


def fmt_dur(sec):
    sec = int(max(0, sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class Keypad(Gtk.Grid):
    def __init__(self, on_key, on_plus=None):
        super().__init__(row_spacing=12, column_spacing=22, halign=Gtk.Align.CENTER)
        self.on_key = on_key
        self.on_plus = on_plus
        for i, (d, letters) in enumerate(KEYS):
            b = Gtk.Button()
            cls(b, "lica-key")
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
            box.pack_start(cls(Gtk.Label(label=d), "lica-key-digit"), False, False, 0)
            box.pack_start(cls(Gtk.Label(label=letters or " "), "lica-key-letters"), False, False, 0)
            b.add(box)
            if d == "0" and on_plus:
                b.connect("button-press-event", self._zero_press)
                b.connect("button-release-event", self._zero_release)
            else:
                b.connect("clicked", lambda _b, d=d: self.on_key(d))
            self.attach(b, i % 3, i // 3, 1, 1)
        self._hold = None
        self._held = False

    def _zero_press(self, *_a):
        self._held = False
        self._hold = GLib.timeout_add(550, self._zero_long)
        return False

    def _zero_long(self):
        self._held = True
        self._hold = None
        self.on_plus()
        return False

    def _zero_release(self, *_a):
        if self._hold:
            GLib.source_remove(self._hold)
            self._hold = None
        if not self._held:
            self.on_key("0")
        return False


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, ctl):
        super().__init__(application=app, title=APP_NAME)
        self.ctl = ctl
        self.set_default_size(400, 700)
        self.connect("delete-event", self._on_delete)
        self._timer = None

        header = Gtk.HeaderBar(show_close_button=True)
        self.set_titlebar(header)
        self.tabs = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.switcher = Gtk.StackSwitcher(stack=self.tabs)
        header.set_custom_title(self.switcher)
        self.menu_btn = Gtk.MenuButton(image=Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        header.pack_end(self.menu_btn)
        header.show_all()   # the titlebar is not covered by root.show_all(); without it the window can't be moved

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        cls(root, "lica-root")
        self.add(root)

        self.banner = Gtk.InfoBar(message_type=Gtk.MessageType.WARNING, show_close_button=False)
        self.banner_label = Gtk.Label(wrap=True, xalign=0)
        self.banner.get_content_area().add(self.banner_label)
        self.banner_btn = self.banner.add_button(_("diagnostics"), 1)
        self.banner.connect("response", lambda *_a: ctl.show_diagnostics())
        self.banner.set_no_show_all(True)
        root.pack_start(self.banner, False, False, 0)

        self.main = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_UP_DOWN, vexpand=True)
        root.pack_start(self.main, True, True, 0)
        self.main.add_named(self.tabs, "tabs")
        self.main.add_named(self._build_call_view(), "call")

        self.tabs.add_titled(self._build_keypad(), "keypad", _("keypad"))
        self.tabs.add_titled(self._build_contacts(), "contacts", _("contacts"))
        self.tabs.add_titled(self._build_recents(), "recents", _("recents"))

        bottom = Gtk.Box(spacing=8)
        cls(bottom, "lica-bottom")
        ver = Gtk.Label(label=f"v{VERSION} · {BUILD_DATE}", xalign=0)
        cls(ver, "lica-dim", "lica-small")
        bottom.pack_start(ver, False, False, 0)
        self.status_dot = Gtk.Label(label="●")
        self.status_label = cls(Gtk.Label(ellipsize=Pango.EllipsizeMode.END), "lica-small")
        self.connect_btn = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
        cls(self.connect_btn, "lica-small")
        self.connect_btn.connect("clicked", lambda *_a: ctl.toggle_connection())
        bottom.pack_end(self.connect_btn, False, False, 0)
        bottom.pack_end(self.status_label, False, False, 0)
        bottom.pack_end(self.status_dot, False, False, 0)
        root.pack_end(bottom, False, False, 0)

        self.key_controller = self.connect("key-press-event", self._on_key)
        root.show_all()

    # ------------------------------------------------------------ keypad --
    def _build_keypad(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=18)
        self.number = Gtk.Entry(placeholder_text=_("number_hint"), xalign=0.5)
        cls(self.number, "lica-number")
        self.number.connect("activate", lambda *_a: self._dial_from_entry())
        self.number.connect("changed", lambda *_a: self._update_match())
        self.completion = Gtk.EntryCompletion()
        self.completion_store = Gtk.ListStore(str, str, str)  # display, number, name
        self.completion.set_model(self.completion_store)
        self.completion.set_text_column(0)
        self.completion.set_minimum_key_length(2)
        self.completion.set_match_func(self._complete_match, None)
        self.completion.connect("match-selected", self._complete_selected)
        self.number.set_completion(self.completion)
        box.pack_start(self.number, False, False, 0)
        self.match_label = cls(Gtk.Label(label=" "), "lica-dim")
        box.pack_start(self.match_label, False, False, 0)
        box.pack_start(Keypad(self._key_pressed, lambda: self._key_pressed("+")), False, False, 4)

        row = Gtk.Box(spacing=22, halign=Gtk.Align.CENTER, margin_top=8)
        spacer = Gtk.Box()
        spacer.set_size_request(70, 1)
        row.pack_start(spacer, False, False, 0)
        call = icon_button("call-start-symbolic", ("lica-round", "lica-green"), _("call"), Gtk.IconSize.DND)
        call.set_size_request(70, 70)
        call.connect("clicked", lambda *_a: self._dial_from_entry())
        row.pack_start(call, False, False, 0)
        back = icon_button("edit-clear-symbolic", ("lica-key",), None)
        back.set_size_request(70, 70)
        back.connect("clicked", lambda *_a: self._backspace())
        row.pack_start(back, False, False, 0)
        box.pack_start(row, False, False, 0)
        return box

    def _key_pressed(self, d):
        pos = self.number.get_position()
        self.number.insert_text(d, pos)
        self.number.set_position(pos + 1)

    def _backspace(self):
        t = self.number.get_text()
        self.number.set_text(t[:-1])

    def _dial_from_entry(self):
        text = self.number.get_text().strip()
        num = self.ctl.resolve_dial_target(text)
        if num:
            self.ctl.dial(num)

    def _update_match(self):
        t = self.number.get_text().strip()
        name = self.ctl.name_for(t) if any(ch.isdigit() for ch in t) else ""
        self.match_label.set_text(name or " ")

    def _complete_match(self, completion, key, it, _data):
        disp, num, name = self.completion_store[it][:]
        key = key.lower().strip()
        if not key:
            return False
        digits = "".join(ch for ch in key if ch.isdigit())
        if digits and len(digits) == len(key.replace(" ", "").replace("+", "")):
            return digits in "".join(ch for ch in num if ch.isdigit())
        return all(w in name.lower() for w in key.split())

    def _complete_selected(self, completion, model, it):
        self.number.set_text(model[it][1])
        self.number.set_position(-1)
        self.match_label.set_text(model[it][2])
        return True

    # ---------------------------------------------------------- contacts --
    def _build_contacts(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.search = Gtk.SearchEntry(placeholder_text=_("search"), margin=10)
        self.search.connect("search-changed", lambda *_a: self.contacts_list.invalidate_filter())
        box.pack_start(self.search, False, False, 0)
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.contacts_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.contacts_list.set_filter_func(self._filter_contact)
        self.contacts_list.connect("row-activated", lambda _l, r: self.ctl.dial(r.number))
        self.contacts_placeholder = cls(Gtk.Label(label=_("no_contacts"), wrap=True, margin=24,
                                                  justify=Gtk.Justification.CENTER), "lica-dim")
        self.contacts_placeholder.show()
        self.contacts_list.set_placeholder(self.contacts_placeholder)
        sw.add(self.contacts_list)
        box.pack_start(sw, True, True, 0)
        return box

    def _filter_contact(self, row):
        q = self.search.get_text().strip().lower()
        if not q:
            return True
        qd = "".join(ch for ch in q if ch.isdigit())
        if qd and qd in row.digits:
            return True
        return all(w in row.name.lower() for w in q.split())

    def set_contacts(self, contacts, note=None):
        for r in self.contacts_list.get_children():
            self.contacts_list.remove(r)
        self.completion_store.clear()
        for c in contacts:
            for t, num in c["numbers"]:
                row = Gtk.ListBoxRow()
                row.number, row.name = num, c["name"]
                row.digits = "".join(ch for ch in num if ch.isdigit())
                h = Gtk.Box(spacing=12)
                cls(h, "lica-row")
                h.pack_start(avatar(c["name"], 38, "lica-avatar-small"), False, False, 0)
                v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
                v.pack_start(Gtk.Label(label=c["name"], xalign=0, ellipsize=Pango.EllipsizeMode.END), False, False, 0)
                v.pack_start(cls(Gtk.Label(label=f"{_(t)} · {num}", xalign=0), "lica-dim", "lica-small"), False, False, 0)
                h.pack_start(v, True, True, 0)
                row.add(h)
                self.contacts_list.add(row)
                self.completion_store.append([f"{c['name']} — {num}", num, c["name"]])
        self.contacts_list.show_all()
        self.contacts_placeholder.set_text(note or _("no_contacts"))

    # ----------------------------------------------------------- recents --
    def _build_recents(self):
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.recents_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.recents_list.connect("row-activated", lambda _l, r: r.number and self.ctl.dial(r.number))
        ph = cls(Gtk.Label(label=_("no_recents"), margin=24), "lica-dim")
        ph.show()
        self.recents_list.set_placeholder(ph)
        sw.add(self.recents_list)
        return sw

    def set_recents(self, items):
        for r in self.recents_list.get_children():
            self.recents_list.remove(r)
        for it in items[:200]:
            row = Gtk.ListBoxRow()
            row.number = it.get("number", "")
            h = Gtk.Box(spacing=12)
            cls(h, "lica-row")
            typ = it.get("type", "received")
            arrow = {"missed": "↙", "received": "↙", "dialed": "↗"}.get(typ, "•")
            a = Gtk.Label(label=arrow, width_chars=2)
            if typ == "missed":
                cls(a, "lica-missed")
            else:
                cls(a, "lica-dim")
            h.pack_start(a, False, False, 0)
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
            title = it.get("name") or self.ctl.name_for(row.number) or row.number or _("private")
            tl = Gtk.Label(label=title, xalign=0, ellipsize=Pango.EllipsizeMode.END)
            if typ == "missed":
                cls(tl, "lica-missed")
            v.pack_start(tl, False, False, 0)
            if title != row.number and row.number:
                v.pack_start(cls(Gtk.Label(label=row.number, xalign=0), "lica-dim", "lica-small"), False, False, 0)
            h.pack_start(v, True, True, 0)
            h.pack_end(cls(Gtk.Label(label=fmt_time(it.get("time"))), "lica-dim", "lica-small"), False, False, 0)
            row.add(h)
            self.recents_list.add(row)
        self.recents_list.show_all()

    # --------------------------------------------------------- call view --
    def _build_call_view(self):
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=22, valign=Gtk.Align.CENTER)
        self.call_avatar_box = Gtk.Box(halign=Gtk.Align.CENTER)
        v.pack_start(self.call_avatar_box, False, False, 6)
        self.call_name = cls(Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER), "lica-name-big")
        self.call_number = cls(Gtk.Label(selectable=True), "lica-dim")
        self.call_state = cls(Gtk.Label(), "lica-dim")
        for w in (self.call_name, self.call_number, self.call_state):
            v.pack_start(w, False, False, 0)

        # ringing controls
        self.ring_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=26)
        b1 = cls(Gtk.Button(label=_("answer_laptop")), "lica-pill", "lica-green")
        b1.connect("clicked", lambda *_a: self.ctl.answer_laptop())
        b2 = cls(Gtk.Button(label=_("on_iphone_long")), "lica-pill", "lica-neutral")
        b2.connect("clicked", lambda *_a: self.ctl.answer_iphone())
        self.ring_iphone_btn = b2
        b3 = cls(Gtk.Button(label=_("reject")), "lica-pill", "lica-red")
        b3.connect("clicked", lambda *_a: self.ctl.reject())
        for b in (b1, b2, b3):
            self.ring_box.pack_start(b, False, False, 0)
        v.pack_start(self.ring_box, False, False, 0)

        # live call controls
        self.live_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=22)
        tools = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER, homogeneous=True)
        self.mute_btn = self._tool("microphone-sensitivity-muted-symbolic", _("mute"))
        self.mute_btn.connect("toggled", lambda b: self.ctl.set_mute(b.get_active()))
        self.dtmf_btn = self._tool("input-dialpad-symbolic", _("dtmf"))
        self.dtmf_btn.connect("toggled", lambda b: self.dtmf_rev.set_reveal_child(b.get_active()))
        self.route_btn = cls(Gtk.Button(), "lica-tool")
        self.route_icon = Gtk.Image()
        self.route_label = cls(Gtk.Label(), "lica-small")
        rb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        rb.pack_start(self.route_icon, False, False, 0)
        rb.pack_start(self.route_label, False, False, 0)
        self.route_btn.add(rb)
        self.route_btn.connect("clicked", lambda *_a: self.ctl.toggle_route())
        for b in (self.mute_btn, self.dtmf_btn, self.route_btn):
            tools.pack_start(b, True, True, 0)
        self.live_box.pack_start(tools, False, False, 0)
        self.dtmf_rev = Gtk.Revealer()
        self.dtmf_rev.add(Keypad(lambda d: self.ctl.send_dtmf(d)))
        self.live_box.pack_start(self.dtmf_rev, False, False, 0)
        hang = icon_button("call-stop-symbolic", ("lica-round", "lica-red"), _("hangup"), Gtk.IconSize.DND)
        hang.set_size_request(70, 70)
        hang.connect("clicked", lambda *_a: self.ctl.hangup())
        self.live_box.pack_start(hang, False, False, 8)
        v.pack_start(self.live_box, False, False, 0)
        return v

    def _tool(self, icon, label):
        b = Gtk.ToggleButton()
        cls(b, "lica-tool")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR), False, False, 0)
        box.pack_start(cls(Gtk.Label(label=label), "lica-small"), False, False, 0)
        b.add(box)
        return b

    def show_call(self, call, name, audio_on_laptop, on_iphone_note=None):
        """call: dict from Telephony (or a phantom dict during hand-off); None hides the view."""
        if call is None:
            if self.main.get_visible_child_name() != "tabs":
                self.main.set_visible_child_name("tabs")
            self.switcher.set_sensitive(True)
            self.mute_btn.set_active(False)
            self.dtmf_btn.set_active(False)
            if self._timer:
                GLib.source_remove(self._timer)
                self._timer = None
            return
        self.switcher.set_sensitive(False)
        for ch in self.call_avatar_box.get_children():
            self.call_avatar_box.remove(ch)
        self.call_avatar_box.pack_start(avatar(name or call.get("number"), 112, "lica-avatar-big"), False, False, 0)
        self.call_avatar_box.show_all()
        num = call.get("number") or ""
        self.call_name.set_text(name or num or _("private"))
        self.call_number.set_text(num if name else "")
        self.call_number.set_visible(bool(name and num))
        ringing = call.get("state") in ("incoming", "waiting")
        self.ring_box.set_visible(ringing)
        self.live_box.set_visible(not ringing)
        self.ring_iphone_btn.set_visible(ringing and not on_iphone_note)
        self._call = call
        self._note = on_iphone_note
        if not ringing:
            self.route_icon.set_from_icon_name(
                "phone-symbolic" if audio_on_laptop else "computer-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
            self.route_label.set_text(_("to_iphone") if audio_on_laptop else _("to_laptop"))
        self._tick()
        if not self._timer:
            self._timer = GLib.timeout_add_seconds(1, self._tick)
        self.main.set_visible_child_name("call")

    def _tick(self):
        c = getattr(self, "_call", None)
        if not c:
            self._timer = None
            return False
        st = c.get("state", "")
        if st == "active" and c.get("active_since"):
            txt = fmt_dur(time.time() - c["active_since"])
        else:
            txt = _("state_" + st) if st else ""
        if self._note:
            txt = self._note if st in ("incoming", "waiting") or not txt else f"{txt} · {self._note}"
        self.call_state.set_text(txt)
        return True

    # ------------------------------------------------------------ status --
    def set_status(self, connected, text, can_connect=True):
        self.status_dot.get_style_context().remove_class("lica-dot-on")
        self.status_dot.get_style_context().remove_class("lica-dot-off")
        cls(self.status_dot, "lica-dot-on" if connected else "lica-dot-off")
        self.status_label.set_text(text)
        self.connect_btn.set_label(_("disconnect") if connected else _("connect"))
        self.connect_btn.set_visible(can_connect)

    def set_banner(self, text):
        if text:
            self.banner_label.set_text(text)
            self.banner.set_no_show_all(False)
            self.banner.show_all()
        else:
            self.banner.hide()

    def _on_key(self, _w, ev):
        if self.main.get_visible_child_name() == "call" and self.dtmf_rev.get_reveal_child():
            ch = ev.string
            if ch and ch in "0123456789*#":
                self.ctl.send_dtmf(ch)
                return True
        if ev.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def _on_delete(self, *_a):
        self.hide()
        return True


class IncomingPopup(Gtk.Window):
    """Small always-on-top window: answer on laptop / on iPhone / decline."""

    def __init__(self, app, ctl):
        super().__init__(title=_("incoming"))
        self.set_application(app)
        self.ctl = ctl
        self.set_keep_above(True)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_default_size(340, -1)
        self.connect("delete-event", self._close)
        self.connect("key-press-event", lambda _w, e: self._close() if e.keyval == Gdk.KEY_Escape else False)

        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=20)
        cls(v, "lica-popup")
        self.title_lbl = cls(Gtk.Label(label=_("incoming").upper()), "lica-popup-title")
        v.pack_start(self.title_lbl, False, False, 0)
        self.av_box = Gtk.Box(halign=Gtk.Align.CENTER, margin_top=6)
        v.pack_start(self.av_box, False, False, 0)
        self.name_lbl = cls(Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER), "lica-name-big")
        self.num_lbl = cls(Gtk.Label(), "lica-dim")
        v.pack_start(self.name_lbl, False, False, 0)
        v.pack_start(self.num_lbl, False, False, 0)
        row = Gtk.Box(spacing=8, homogeneous=True, margin_top=14)
        b1 = cls(Gtk.Button(label=_("answer_short")), "lica-pill", "lica-green")
        b1.set_tooltip_text(_("answer_laptop"))
        b1.connect("clicked", lambda *_a: ctl.answer_laptop())
        b2 = cls(Gtk.Button(label=_("on_iphone")), "lica-pill", "lica-neutral")
        b2.set_tooltip_text(_("on_iphone_long"))
        b2.connect("clicked", lambda *_a: ctl.answer_iphone())
        b3 = cls(Gtk.Button(label=_("reject")), "lica-pill", "lica-red")
        b3.connect("clicked", lambda *_a: ctl.reject())
        for b in (b1, b2, b3):
            row.pack_start(b, True, True, 0)
        v.pack_start(row, False, False, 0)
        self.add(v)
        v.show_all()

    def present_call(self, name, number, waiting=False):
        for ch in self.av_box.get_children():
            self.av_box.remove(ch)
        self.av_box.pack_start(avatar(name or number, 84, "lica-avatar-big"), False, False, 0)
        self.av_box.show_all()
        self.title_lbl.set_text((_("incoming_waiting") if waiting else _("incoming")).upper())
        self.name_lbl.set_text(name or number or _("private"))
        self.num_lbl.set_text(number if name else "")
        self.num_lbl.set_visible(bool(name and number))
        self.set_urgency_hint(True)
        self.show()
        self.present_with_time(Gtk.get_current_event_time() or 0)

    def _close(self, *_a):
        # closing the popup = let it ring on the iPhone only
        self.ctl.answer_iphone()
        return True
