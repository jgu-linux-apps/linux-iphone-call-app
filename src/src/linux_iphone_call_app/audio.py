"""Call audio plumbing on PipeWire + ringtone.

When the phone's hands-free audio lands on the laptop, PipeWire exposes a source
(voice from the phone) and a sink (voice to the phone). If WirePlumber hasn't linked
them to the speakers / microphone, we bridge them with two pw-loopback processes.
"""
import glob
import json
import os
import shutil
import subprocess

from gi.repository import GLib

RINGTONES = [
    "/usr/share/sounds/freedesktop/stereo/phone-incoming-call.oga",
    "/usr/share/sounds/Yaru/stereo/phone-incoming-call.oga",
]


def _run(cmd, timeout=4):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def pw_dump():
    out = _run(["pw-dump"], timeout=6)
    try:
        return json.loads(out) if out else []
    except ValueError:
        return []


def pipewire_version():
    out = _run(["pipewire", "--version"])
    for line in out.splitlines():
        if "libpipewire" in line:
            return line.split()[-1]
    for line in out.splitlines():
        if line.strip():
            return line.split()[-1]
    return "?"


def _props(o):
    return (o.get("info") or {}).get("props") or {}


def _node(dump, name):
    for o in dump:
        if o.get("type") == "PipeWire:Interface:Node" and _props(o).get("node.name") == name:
            return o
    return None


def aec_available():
    pats = ["/usr/lib/*/spa-0.2/aec/libspa-aec-webrtc.so", "/usr/lib/spa-0.2/aec/libspa-aec-webrtc.so",
            "/usr/lib64/spa-0.2/aec/libspa-aec-webrtc.so"]
    return any(glob.glob(p) for p in pats) and bool(shutil.which("pipewire"))


# PipeWire client process with the echo-cancel module (WebRTC). Its sink receives the
# phone's voice (and is the echo reference), its source is the cleaned laptop mic.
AEC_CONF = """
context.properties = {{ log.level = 1 }}
context.spa-libs = {{
    audio.convert.* = audioconvert/libspa-audioconvert
    support.*       = support/libspa-support
}}
context.modules = [
    {{ name = libpipewire-module-rt flags = [ ifexists nofail ] }}
    {{ name = libpipewire-module-protocol-native }}
    {{ name = libpipewire-module-client-node }}
    {{ name = libpipewire-module-adapter }}
    {{ name = libpipewire-module-echo-cancel
      args = {{
        library.name = aec/libspa-aec-webrtc
        monitor.mode = false
        audio.channels = 1
        audio.position = [ MONO ]
        aec.args = {{
            webrtc.extended_filter = true
            webrtc.delay_agnostic = true
            webrtc.high_pass_filter = true
            webrtc.noise_suppression = true
            webrtc.gain_control = true
            webrtc.experimental_agc = true
            webrtc.experimental_ns = true
        }}
        capture.props  = {{ node.name = "lica_aec_capture" node.description = "iPhone call: laptop mic"{capture_target} node.dont-reconnect = true }}
        source.props   = {{ node.name = "lica_aec_source" node.description = "iPhone call: clean mic" priority.session = 1 priority.driver = 1 }}
        sink.props     = {{ node.name = "lica_aec_sink" node.description = "iPhone call: voice" priority.session = 1 priority.driver = 1 }}
        playback.props = {{ node.name = "lica_aec_playback" node.description = "iPhone call: speakers"{playback_target} node.dont-reconnect = true }}
      }}
    }}
]
"""


class CallAudio:
    def __init__(self):
        self.procs = []
        self.mic_muted = False
        self._muted_default_source = False
        self._retry = None
        self.mac = ""
        self.aec_proc = None

    # ---- discovery -------------------------------------------------------
    def _phone_nodes(self, dump):
        mac = self.mac.upper()
        src = sink = None
        for o in dump:
            if o.get("type") != "PipeWire:Interface:Node":
                continue
            p = _props(o)
            addr = (p.get("api.bluez5.address") or "").upper()
            name = p.get("node.name") or ""
            if not (addr == mac or mac.replace(":", "_") in name.upper()):
                continue
            prof = (p.get("api.bluez5.profile") or "").lower()
            if "a2dp" in prof or "a2dp" in name.lower():
                continue
            cls = p.get("media.class") or ""
            if "Source" in cls or "Output" in cls:
                src = o
            elif "Sink" in cls or "Input" in cls:
                sink = o
        return src, sink

    @staticmethod
    def _linked(dump, node_id, as_output):
        key = "output-node-id" if as_output else "input-node-id"
        for o in dump:
            if o.get("type") == "PipeWire:Interface:Link":
                if (o.get("info") or {}).get(key) == node_id:
                    return True
        return False

    @staticmethod
    def _default(dump, kind):
        for o in dump:
            if o.get("type") == "PipeWire:Interface:Metadata" and _props(o).get("metadata.name") == "default":
                for m in o.get("metadata") or []:
                    if m.get("key") == f"default.audio.{kind}":
                        v = m.get("value")
                        if isinstance(v, dict):
                            return v.get("name")
                        try:
                            return json.loads(v).get("name")
                        except Exception:
                            return None
        return None

    def _best_local(self, dump, cls, exclude):
        best, prio = None, -1
        for o in dump:
            if o.get("type") != "PipeWire:Interface:Node":
                continue
            p = _props(o)
            name = p.get("node.name") or ""
            if p.get("media.class") != cls or self.mac.replace(":", "_") in name.upper():
                continue
            if p.get("node.name") in exclude:
                continue
            pr = int(p.get("priority.session") or 0)
            if pr > prio:
                best, prio = p.get("node.name"), pr
        return best

    def _ensure_hfp_profile(self, dump):
        mac = self.mac.upper()
        for o in dump:
            if o.get("type") != "PipeWire:Interface:Device":
                continue
            if (_props(o).get("api.bluez5.address") or "").upper() != mac:
                continue
            params = (o.get("info") or {}).get("params") or {}
            cur = (params.get("Profile") or [{}])[0].get("name", "")
            if any(k in cur for k in ("audio-gateway", "headset", "hfp", "hsp")):
                return
            for prof in params.get("EnumProfile") or []:
                n = prof.get("name", "")
                if any(k in n for k in ("audio-gateway", "headset-head-unit", "hfp")):
                    _run(["wpctl", "set-profile", str(o["id"]), str(prof.get("index"))])
                    return

    def set_profile_off(self, mac):
        """Release the hands-free audio link: the iPhone then takes the audio back."""
        self.mac = mac or self.mac
        for o in pw_dump():
            if o.get("type") != "PipeWire:Interface:Device":
                continue
            if (_props(o).get("api.bluez5.address") or "").upper() != self.mac.upper():
                continue
            for prof in ((o.get("info") or {}).get("params") or {}).get("EnumProfile") or []:
                if prof.get("name") == "off":
                    _run(["wpctl", "set-profile", str(o["id"]), str(prof.get("index", 0))])
                    return True
        return False

    def profile_is_off(self, dump=None):
        for o in dump if dump is not None else pw_dump():
            if o.get("type") != "PipeWire:Interface:Device":
                continue
            if (_props(o).get("api.bluez5.address") or "").upper() != self.mac.upper():
                continue
            cur = (((o.get("info") or {}).get("params") or {}).get("Profile") or [{}])[0].get("name", "")
            return cur == "off"
        return False

    def restore_profile_if_off(self, mac=None):
        """After a call that was handed to the iPhone: switch the phone card back on."""
        self.mac = mac or self.mac
        dump = pw_dump()
        if self.profile_is_off(dump):
            self._ensure_hfp_profile(dump)

    # ---- start / stop ----------------------------------------------------
    def start(self, mac, aec=True):
        """Route call audio through the laptop (optionally through WebRTC echo/noise cancel).
        Never touches the card profile: that is decided by the controller only."""
        self.mac = mac
        self.stop_routing()
        attempts = {"n": 0}
        want_aec = aec and aec_available()

        def attempt():
            attempts["n"] += 1
            dump = pw_dump()
            src, sink = self._phone_nodes(dump)
            if not src and not sink:
                if attempts["n"] >= 30:
                    self._retry = None
                    return False
                return True                 # keep trying ~15 s
            if want_aec:
                if self.aec_proc is None:
                    self._start_aec(dump)
                    return True
                if not _node(dump, "lica_aec_sink") and attempts["n"] < 12:
                    return True             # wait for the filter to appear
            self._bridge(dump, src, sink)
            self._retry = None
            return False

        self._retry = GLib.timeout_add(500, attempt)

    def _local_targets(self, dump):
        tag = self.mac.replace(":", "_").upper()
        spk = self._default(dump, "sink")
        if not spk or tag in spk.upper() or spk.startswith("lica_"):
            spk = self._best_local(dump, "Audio/Sink", ("lica_aec_sink",))
        mic = self._default(dump, "source")
        if not mic or tag in mic.upper() or mic.startswith("lica_"):
            mic = self._best_local(dump, "Audio/Source", ("lica_aec_source",))
        return spk, mic

    def _start_aec(self, dump):
        """Free WebRTC audio processing built into PipeWire: echo cancel + noise
        suppression + automatic gain for the laptop microphone."""
        spk, mic = self._local_targets(dump)
        rt = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
        conf = os.path.join(rt, "linux-iphone-call-app-aec.conf")
        cap_t = f' target.object = "{mic}"' if mic else ""
        play_t = f' target.object = "{spk}"' if spk else ""
        with open(conf, "w", encoding="utf-8") as f:
            f.write(AEC_CONF.format(capture_target=cap_t, playback_target=play_t))
        try:
            self.aec_proc = subprocess.Popen(["pipewire", "-c", conf],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            print("AEC start failed:", e)
            self.aec_proc = None

    def _bridge(self, dump, src, sink):
        lb = shutil.which("pw-loopback")
        aec = _node(dump, "lica_aec_sink") is not None and _node(dump, "lica_aec_source") is not None
        spk, mic = self._local_targets(dump)
        out_target = "lica_aec_sink" if aec else spk
        in_target = "lica_aec_source" if aec else mic
        print("call audio:", "WebRTC echo/noise cancel ON" if aec else "direct", "| speaker:", spk, "| mic:", mic)
        if src:
            if (_props(src).get("media.class") or "").startswith("Stream/"):
                if out_target:   # WirePlumber-managed stream: just retarget it
                    _run(["pw-metadata", str(src["id"]), "target.object", out_target])
            elif lb and (aec or not self._linked(dump, src["id"], True)):
                cmd = [lb, "-n", "lica-from-iphone",
                       "--capture-props", f'target.object="{_props(src).get("node.name")}" node.dont-reconnect=true',
                       "--playback-props", "media.role=Communication node.description=\"iPhone call\"" +
                       (f' target.object="{out_target}"' if out_target else "")]
                self.procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        if sink:
            if (_props(sink).get("media.class") or "").startswith("Stream/"):
                if in_target:
                    _run(["pw-metadata", str(sink["id"]), "target.object", in_target])
            elif lb and (aec or not self._linked(dump, sink["id"], False)):
                cmd = [lb, "-n", "lica-to-iphone",
                       "--capture-props", "media.role=Communication node.description=\"iPhone call mic\"" +
                       (f' target.object="{in_target}"' if in_target else ""),
                       "--playback-props", f'target.object="{_props(sink).get("node.name")}" node.dont-reconnect=true']
                self.procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        if self.mic_muted:
            self.set_mute(True)

    def routing(self):
        return bool(self.procs or self._retry or self.aec_proc)

    def stop_routing(self):
        if self._retry:
            GLib.source_remove(self._retry)
            self._retry = None
        for p in self.procs + ([self.aec_proc] if self.aec_proc else []):
            try:
                p.terminate()
            except Exception:
                pass
        self.procs = []
        self.aec_proc = None

    def stop(self):
        self.stop_routing()
        if self.mic_muted:
            self.set_mute(False)
        self.mic_muted = False

    # ---- mute ------------------------------------------------------------
    def set_mute(self, on):
        self.mic_muted = on
        dump = pw_dump()
        _src, sink = self._phone_nodes(dump) if self.mac else (None, None)
        targets = [o["id"] for o in dump
                   if o.get("type") == "PipeWire:Interface:Node"
                   and _props(o).get("node.name", "").startswith("lica-to-iphone")
                   and _props(o).get("media.class", "").startswith("Stream/Input")]
        if sink is not None:
            targets.append(sink["id"])
        for t in targets:
            _run(["wpctl", "set-mute", str(t), "1" if on else "0"])
        if on and not targets:
            _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "1"])
            self._muted_default_source = True
        if not on and self._muted_default_source:
            _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "0"])
            self._muted_default_source = False


RINGTONE_NAMES = ("morning", "wave", "droplet", "system")


def _duration(path):
    try:
        import wave
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 3.0


class Ringer:
    def __init__(self, sounds_dir=None):
        self.proc = None
        self.preview_proc = None
        self.timer = None
        self.sounds_dir = sounds_dir
        self.player = shutil.which("pw-play") or shutil.which("paplay") or shutil.which("canberra-gtk-play")
        self.set_sound("morning")

    def path_for(self, name):
        if name != "system" and self.sounds_dir:
            p = os.path.join(self.sounds_dir, name + ".wav")
            if os.path.exists(p):
                return p
        return next((f for f in RINGTONES if os.path.exists(f)), None)

    def set_sound(self, name):
        self.name = name if name in RINGTONE_NAMES else "morning"
        self.file = self.path_for(self.name)
        self.interval = int((_duration(self.file) + 0.9) * 1000) if self.file and self.file.endswith(".wav") else 3200

    def _spawn(self, path):
        args = [self.player, "-f", path] if self.player.endswith("canberra-gtk-play") else [self.player, path]
        try:
            return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return None

    def preview(self, name):
        if self.preview_proc and self.preview_proc.poll() is None:
            self.preview_proc.terminate()
        path = self.path_for(name)
        if path and self.player and not self.timer:
            self.preview_proc = self._spawn(path)

    def start(self):
        if self.timer or not self.file or not self.player:
            return
        if self.preview_proc and self.preview_proc.poll() is None:
            self.preview_proc.terminate()
        self._play()
        self.timer = GLib.timeout_add(self.interval, self._play)

    def _play(self):
        if self.proc and self.proc.poll() is None:
            return True
        self.proc = self._spawn(self.file)
        return True

    def stop(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None
