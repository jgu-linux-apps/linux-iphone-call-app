"""Motyw „Aurora” dla aplikacji GTK3 serii JGu Linux Apps (ten sam wygląd co aurora.py w aplikacjach GTK4):
jasny = pastelowe szkło z gradientem fiolet → cyjan, ciemny = zorza na granatowym tle z poświatą.
Wariant jasny/ciemny podaje aplikacja (zwykle według systemu). „system” = zwykły motyw GTK, bez zmian.

GTK3 nie ma libadwaity, więc kolory ustawia się przez @define-color theme_* oraz jawne reguły dla
najczęstszych widżetów. extra = reguły konkretnej aplikacji (np. jej własne karty)."""
from gi.repository import Gdk, Gtk

THEMES = ("system", "aurora")

PAL = {
    False: dict(bg="#F4F1FF", fg="#1F1A3A", base="#FFFFFF", header="#FBFAFF", border="#E2DCFA",
                button="#FFFFFF", hover="#ECE7FF", accent="#7C5CFF", accent2="#22B8E6", accent_fg="#FFFFFF",
                popover="#FBFAFF", dim="alpha(#1F1A3A, 0.62)"),
    True: dict(bg="#0C0E1A", fg="#ECEBFF", base="#14172A", header="#10132A", border="#252A45",
               button="#181C33", hover="#1E2340", accent="#A855F7", accent2="#22D3EE", accent_fg="#FFFFFF",
               popover="#161A2E", dim="alpha(#ECEBFF, 0.62)"),
}


def css_for(dark, extra=""):
    p = PAL[dark]
    a, a2 = p["accent"], p["accent2"]
    if dark:
        backdrop = (f"radial-gradient(ellipse at 12% 0%, alpha({a2}, 0.20), transparent 55%), "
                    f"radial-gradient(ellipse at 100% 100%, alpha({a}, 0.24), transparent 55%)")
        sel = f"linear-gradient(to right, alpha({a}, 0.60), alpha({a2}, 0.48))"
        glow = f"0 0 0 1px alpha({a2}, 0.55), 0 0 16px alpha({a2}, 0.28)"
        line = "alpha(#FFFFFF, 0.07)"
    else:
        backdrop = "linear-gradient(135deg, #F6F2FF 0%, #EEF8FF 55%, #FFF4F8 100%)"
        sel = f"linear-gradient(to right, {a}, {a2})"
        glow = f"0 0 0 1px alpha({a}, 0.55), 0 4px 14px alpha({a}, 0.22)"
        line = f"alpha({a}, 0.12)"
    return f"""
@define-color theme_bg_color {p['bg']};
@define-color theme_fg_color {p['fg']};
@define-color theme_base_color {p['base']};
@define-color theme_text_color {p['fg']};
@define-color theme_selected_bg_color {a};
@define-color theme_selected_fg_color {p['accent_fg']};
@define-color borders {p['border']};
@define-color unfocused_borders {p['border']};

window.background, dialog, messagedialog, .dialog-vbox {{ background-color: {p['bg']}; color: {p['fg']}; }}
window.background {{ background-image: {backdrop}; }}
scrolledwindow, viewport, stack, flowbox, flowboxchild {{ background-color: transparent; }}
label {{ color: inherit; }}

headerbar, .titlebar {{ background-image: none; background-color: {p['header']}; color: {p['fg']};
    border-color: {p['border']}; box-shadow: inset 0 -1px {line}; }}
headerbar label, headerbar .title, headerbar .subtitle, headerbar button image {{ color: {p['fg']}; }}
headerbar button {{ background-image: none; background-color: transparent; border-color: transparent; box-shadow: none; }}
headerbar button:hover {{ background-color: {p['hover']}; }}

button {{ background-image: none; background-color: {p['button']}; color: {p['fg']};
    border: 1px solid {p['border']}; border-radius: 10px; box-shadow: none; text-shadow: none;
    transition: all 150ms ease-out; }}
button:hover {{ background-color: {p['hover']}; box-shadow: {glow}; }}
button:checked, button:active {{ background-color: alpha({a}, 0.22); }}
button:disabled, button:disabled label {{ color: {p['dim']}; }}
button.suggested-action, button.suggested-action:hover {{ background-image: {sel}; color: {p['accent_fg']};
    border-color: {a}; box-shadow: 0 0 14px alpha({a}, 0.40); }}
button.suggested-action label {{ color: {p['accent_fg']}; }}
button.destructive-action, button.destructive-action label {{ background-color: #E5484D; color: #FFFFFF; border-color: #E5484D; }}
modelbutton, popover button.flat, button.flat {{ background-color: transparent; border-color: transparent; }}
modelbutton:hover {{ background-color: {p['hover']}; }}
stackswitcher button:checked, stackswitcher button:checked label {{ background-image: {sel}; color: {p['accent_fg']};
    border-color: {a}; }}

entry, spinbutton, textview, textview text {{ background-image: none; background-color: {p['base']}; color: {p['fg']};
    border-color: {p['border']}; border-radius: 10px; }}
entry:focus {{ border-color: {a}; box-shadow: 0 0 0 3px alpha({a}, 0.22); }}
entry selection, textview text selection, label selection {{ background-color: {a}; color: {p['accent_fg']}; }}

popover, popover.background, menu, .menu {{ background-color: {p['popover']}; color: {p['fg']}; border-color: {p['border']}; }}
list, list row {{ background-color: transparent; color: {p['fg']}; }}
list row {{ border-radius: 10px; }}
list row:hover {{ background-color: {p['hover']}; }}
list row:selected, list row:selected label, list row:selected image {{ background-image: {sel}; color: {p['accent_fg']}; }}
separator {{ background-color: {p['border']}; }}

check:checked, radio:checked {{ background-image: none; background-color: {a}; color: {p['accent_fg']}; border-color: {a}; }}
switch:checked {{ background-image: none; background-color: {a}; border-color: {a}; box-shadow: 0 0 8px alpha({a}, 0.45); }}
scale highlight, progressbar progress, levelbar block.filled {{ background-image: {sel}; border-color: {a}; }}
progressbar trough, scale trough, levelbar trough {{ background-color: alpha({p['fg']}, 0.12); border-color: transparent; }}
scrollbar slider {{ background-color: alpha({p['fg']}, 0.35); }}
tooltip, tooltip.background {{ background-color: {p['popover']}; color: {p['fg']}; }}
tooltip label {{ color: {p['fg']}; }}
.card {{ background-color: {p['base']}; border: 1px solid {p['border']}; border-radius: 16px; }}
""" + (extra(p, dark) if callable(extra) else extra)


class AuroraTheme3:
    """apply(name, dark): 'aurora' wczytuje arkusz nad stylem aplikacji, 'system' go zdejmuje.
    Przy zmianie jasny/ciemny w systemie wystarczy ponownie wywołać apply(self.name, dark)."""

    def __init__(self, extra=""):
        self.name = "system"
        self.extra = extra
        self.provider = None

    def apply(self, name, dark):
        self.name = name if name in THEMES else "system"
        screen = Gdk.Screen.get_default()
        if self.provider is not None:
            Gtk.StyleContext.remove_provider_for_screen(screen, self.provider)
            self.provider = None
        if self.name != "aurora" or screen is None:
            return
        self.provider = Gtk.CssProvider()
        self.provider.load_from_data(css_for(bool(dark), self.extra).encode())
        Gtk.StyleContext.add_provider_for_screen(screen, self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
