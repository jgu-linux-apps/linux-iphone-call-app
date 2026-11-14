"""Local config + data storage. Everything stays on this machine (0600 / 0700)."""
import json
import os

from . import PKG

def _xdg(var, default):
    return os.environ.get(var) or os.path.expanduser(default)

CONFIG_DIR = os.path.join(_xdg("XDG_CONFIG_HOME", "~/.config"), PKG)
DATA_DIR = os.path.join(_xdg("XDG_DATA_HOME", "~/.local/share"), PKG)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
CONTACTS_FILE = os.path.join(DATA_DIR, "contacts.json")
RECENTS_FILE = os.path.join(DATA_DIR, "recents.json")
LOCAL_LOG_FILE = os.path.join(DATA_DIR, "local-calls.json")
AUTOSTART_FILE = os.path.join(_xdg("XDG_CONFIG_HOME", "~/.config"), "autostart", PKG + ".desktop")

DEFAULTS = {
    "device": "",          # chosen iPhone MAC
    "ringtone": True,
    "ringtone_sound": "morning",
    "aec": True,           # WebRTC echo cancel + noise suppression + auto gain
    "first_run_done": False,
    "theme": "system",     # system | aurora
}

def _ensure(d):
    os.makedirs(d, mode=0o700, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    _ensure(os.path.dirname(path))
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)

class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        self.data.update(load_json(CONFIG_FILE, {}))

    def get(self, k):
        return self.data.get(k, DEFAULTS.get(k))

    def set(self, k, v):
        self.data[k] = v
        save_json(CONFIG_FILE, self.data)

def autostart_enabled():
    return os.path.exists(AUTOSTART_FILE)

def set_autostart(on):
    if on:
        os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
        with open(AUTOSTART_FILE, "w", encoding="utf-8") as f:
            f.write(
                "[Desktop Entry]\nType=Application\nName=Linux iPhone Calls\n"
                "Exec=linux-iphone-call-app --hidden\nIcon=linux-iphone-call-app\n"
                "X-GNOME-Autostart-enabled=true\nNoDisplay=false\n"
            )
    else:
        try:
            os.remove(AUTOSTART_FILE)
        except FileNotFoundError:
            pass
