"""Synthesize the app's original ringtones (no samples, no third-party audio).
python3 tools/make_ringtones.py  ->  data/sounds/*.wav"""
import math
import os
import struct
import wave

SR = 32000
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "sounds")


def note(n):            # "A4" style -> Hz
    names = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
    acc = 1 if "#" in n else (-1 if n[1] == "b" else 0)
    octv = int(n[-1])
    semis = names[n[0]] + acc + (octv - 4) * 12
    return 440.0 * 2 ** (semis / 12)


def buf(seconds):
    return [0.0] * int(SR * seconds)


def add_tone(b, t0, freq, dur, partials, attack=0.006, decay=0.5, amp=0.3, trem=0.0):
    start = int(t0 * SR)
    for i in range(int(dur * SR)):
        if start + i >= len(b):
            break
        t = i / SR
        env = min(1.0, t / attack) * math.exp(-t / decay)
        if trem:
            env *= 1 - 0.18 * (0.5 + 0.5 * math.sin(2 * math.pi * trem * t))
        v = 0.0
        for mult, a, pdecay in partials:
            v += a * math.exp(-t / pdecay) * math.sin(2 * math.pi * freq * mult * t)
        b[start + i] += amp * env * v


def echo(b, delay, fb, mix):
    d = int(delay * SR)
    out = b[:]
    for i in range(d, len(out)):
        out[i] += out[i - d] * fb
    return [x * (1 - mix) + y * mix for x, y in zip(b, out)]


def fade_out(b, sec):
    n = int(sec * SR)
    for i in range(n):
        b[-n + i] *= 1 - i / n
    return b


def write(name, b, peak=0.55):
    m = max(abs(x) for x in b) or 1
    b = [x / m * peak for x in b]
    os.makedirs(OUT, exist_ok=True)
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(x * 32767)) for x in b))


# 1) Poranek / Morning – soft marimba arpeggio (pentatonic)
b = buf(3.0)
marimba = [(1, 1.0, 0.9), (3.93, 0.25, 0.08), (9.2, 0.06, 0.03)]
seq = ["E5", "G5", "A5", "C6", "A5", "G5", "E5", "D5"]
for i, n in enumerate(seq):
    add_tone(b, 0.05 + i * 0.17, note(n), 1.2, marimba, decay=0.45, amp=0.32)
add_tone(b, 1.55, note("C5"), 1.4, marimba, decay=0.7, amp=0.30)
add_tone(b, 1.55, note("G5"), 1.4, marimba, decay=0.7, amp=0.22)
write("morning", fade_out(echo(b, 0.19, 0.3, 0.25), 0.3))

# 2) Fala / Wave – warm electric-piano chords with gentle tremolo (lo-fi)
b = buf(3.4)
epiano = [(1, 1.0, 2.0), (2, 0.18, 0.6), (3, 0.05, 0.3)]
for n in ["F3", "A4", "C5", "E5", "G5"]:          # Fmaj9
    add_tone(b, 0.0, note(n), 1.7, epiano, attack=0.02, decay=1.2, amp=0.16, trem=4.2)
for n in ["E3", "G4", "B4", "D5", "F#5"]:         # Em9
    add_tone(b, 1.55, note(n), 1.85, epiano, attack=0.02, decay=1.3, amp=0.16, trem=4.2)
add_tone(b, 2.35, note("B5"), 1.0, epiano, attack=0.01, decay=0.5, amp=0.10)
write("wave", fade_out(echo(b, 0.27, 0.25, 0.2), 0.4))

# 3) Kropla / Droplet – kalimba plucks with echo
b = buf(3.0)
kalimba = [(1, 1.0, 0.7), (2.76, 0.22, 0.12), (5.4, 0.05, 0.05)]
for t, n in [(0.0, "D5"), (0.22, "F#5"), (0.44, "A5"), (0.66, "D6"), (1.1, "C#6"), (1.32, "A5")]:
    add_tone(b, t, note(n), 1.4, kalimba, attack=0.003, decay=0.55, amp=0.3)
write("droplet", fade_out(echo(b, 0.23, 0.38, 0.35), 0.4))
print("ok")
