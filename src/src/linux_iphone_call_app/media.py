"""Keep iPhone media audio (games, YouTube, music…) on the iPhone.

Ubuntu advertises itself to phones as a Bluetooth speaker (A2DP sink role), so the
iPhone routes all app audio to the laptop. We drop just that role via a WirePlumber
drop-in; calls (HFP), headphones/speakers used BY the laptop (A2DP source) keep working.
"""
import os
import re
import subprocess

from gi.repository import GLib

_CFG = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
FILE_05 = os.path.join(_CFG, "wireplumber", "wireplumber.conf.d", "51-linux-iphone-call-app-no-phone-media.conf")
FILE_04 = os.path.join(_CFG, "wireplumber", "bluetooth.lua.d", "51-linux-iphone-call-app-no-phone-media.lua")

CONTENT_05 = """# Written by Linux iPhone Calls: the laptop is not offered to phones as a Bluetooth speaker,
# so app audio stays on the iPhone. Calls (hfp_hf) and laptop->headphones (a2dp_source) still work.
monitor.bluez.properties = {
  bluez5.roles = [ a2dp_source bap_sink bap_source hfp_hf hfp_ag ]
}
"""
CONTENT_04 = """-- Written by Linux iPhone Calls: keep iPhone app audio on the iPhone (no a2dp_sink role).
bluez_monitor.properties["bluez5.roles"] = "[ a2dp_source hfp_hf hfp_ag ]"
"""


def wireplumber_version():
    try:
        out = subprocess.run(["wireplumber", "--version"], capture_output=True, text=True, timeout=4).stdout
    except Exception:
        return (0, 5, 0)
    m = re.findall(r"(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(x) for x in m[-1]) if m else (0, 5, 0)


def enabled():
    return os.path.exists(FILE_05) or os.path.exists(FILE_04)


def set_enabled(on):
    """Write/remove the drop-in. Returns True if something changed (restart needed)."""
    changed = False
    if on:
        legacy = wireplumber_version() < (0, 5, 0)
        path, content = (FILE_04, CONTENT_04) if legacy else (FILE_05, CONTENT_05)
        other = FILE_05 if legacy else FILE_04
        try:
            with open(path, "r", encoding="utf-8") as f:
                same = f.read() == content
        except OSError:
            same = False
        if not same:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            changed = True
        if os.path.exists(other):
            os.remove(other)
            changed = True
    else:
        for p in (FILE_05, FILE_04):
            if os.path.exists(p):
                os.remove(p)
                changed = True
    return changed


def restart_wireplumber(done=None):
    """Restart WirePlumber asynchronously so the new roles apply."""
    try:
        proc = subprocess.Popen(["systemctl", "--user", "restart", "wireplumber"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        if done:
            done(False)
        return

    def poll():
        if proc.poll() is None:
            return True
        if done:
            done(proc.returncode == 0)
        return False
    GLib.timeout_add(300, poll)
