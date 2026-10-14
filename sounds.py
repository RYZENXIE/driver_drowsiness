"""Creates the alarm sounds (beep.wav and siren.wav) without any extra tools.

Run `python sounds.py` to (re)create them, or replace the files with your own.
"""
import math
import os
import struct
import wave

RATE = 22050
HERE = os.path.dirname(os.path.abspath(__file__))
BEEP_FILE = os.path.join(HERE, "beep.wav")
SIREN_FILE = os.path.join(HERE, "siren.wav")


def _write(path, samples):
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767 * 0.9)) for s in samples
    )
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(frames)


def make_beep(path=BEEP_FILE):
    n = int(RATE * 0.25)
    samples = []
    for i in range(n):
        fade = min(1.0, i / 500, (n - i) / 500)  # short fade in/out, no clicks
        samples.append(math.sin(2 * math.pi * 1000 * i / RATE) * fade)
    _write(path, samples)


def make_siren(path=SIREN_FILE):
    """Two seconds: pitch sweeps 600 -> 1400 Hz -> 600 Hz. Loops smoothly."""
    n = RATE * 2
    samples, phase = [], 0.0
    for i in range(n):
        t = i / n                                   # 0..1
        sweep = 1 - abs(2 * t - 1)                  # 0 -> 1 -> 0
        freq = 600 + 800 * sweep
        phase += 2 * math.pi * freq / RATE
        samples.append(0.75 * math.sin(phase) + 0.25 * math.sin(2 * phase))
    _write(path, samples)


def ensure_sounds():
    if not os.path.exists(BEEP_FILE):
        make_beep()
    if not os.path.exists(SIREN_FILE):
        make_siren()


if __name__ == "__main__":
    make_beep()
    make_siren()
    print("Created", BEEP_FILE, "and", SIREN_FILE)
