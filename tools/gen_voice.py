#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Synthesize the placeholder voice clips shipped with the pet.

The plugin is designed around a voice pack the *user* supplies: the real
"なつめ" line is a commercial recording and cannot be redistributed here. What
this script produces is a small, clearly-labelled stand-in so the click-to-speak
path is audible and testable before any of your own audio is dropped in.

The synth is a cartoon-cat meow: a glottal pulse train with a pitch contour,
shaped by two resonant formants, with an amplitude envelope and a little breath
noise. It is deliberately stylised rather than realistic — it must never be
mistaken for the real character's voice.

Usage:
    python gen_voice.py            # write assets/voice/*.mp3 (ffmpeg required)
    python gen_voice.py --wav      # keep uncompressed WAV instead
    python gen_voice.py --list     # show the clip table
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "voice"
SR = 44100


def glottal(n: int, f0: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Pulse train with a per-sample fundamental, phase-continuous."""
    phase = np.cumsum(f0) / SR
    # A raised-cosine pulse is a cheap, stable stand-in for a glottal waveform.
    pulse = 0.5 - 0.5 * np.cos(2 * np.pi * phase)
    return np.sign(np.sin(2 * np.pi * phase)) * pulse + 0.02 * rng.standard_normal(n)


def formant(signal: np.ndarray, freq: float, bandwidth: float = 90.0) -> np.ndarray:
    """Two-pole resonator, applied as a simple biquad in the time domain."""
    r = np.exp(-np.pi * bandwidth / SR)
    theta = 2 * np.pi * freq / SR
    a1, a2 = -2 * r * np.cos(theta), r * r
    out = np.zeros_like(signal)
    y1 = y2 = 0.0
    for i, x in enumerate(signal):
        y = x - a1 * y1 - a2 * y2
        out[i] = y
        y2, y1 = y1, y
    return out


def meow(f0_start: float, f0_peak: float, f0_end: float, dur: float,
         seed: int = 0, bright: float = 1.0) -> np.ndarray:
    """Render one meow: pitch rises then falls, two formants sweep with it."""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.linspace(0, 1, n, endpoint=False)
    # Pitch contour: a quick rise to the peak, then a long fall — the shape that
    # reads as a meow rather than a beep. The falloff exponent is applied to a
    # non-negative ramp so the power cannot produce a NaN.
    fall = np.clip((t - 0.22) / 0.78, 0.0, 1.0) ** 0.7
    f0 = np.where(
        t < 0.22,
        f0_start + (f0_peak - f0_start) * (t / 0.22),
        f0_peak + (f0_end - f0_peak) * fall,
    )
    voice = glottal(n, f0, rng)

    # Formants track the pitch so the vowel colours move: "ny" then "aa" then "u".
    f1 = 380 + 620 * np.sin(np.pi * np.clip(t / 0.75, 0, 1)) ** 1.4
    f2 = (1100 + 1500 * np.sin(np.pi * np.clip(t / 0.6, 0, 1)) ** 1.2) * bright
    out = np.zeros(n)
    for i, (a, b) in enumerate(zip(f1, f2)):
        chunk = voice[max(0, i - 40):i + 1]
        if chunk.size == 0:
            continue
        out[i] = formant(chunk, b, 140)[-1] * 0.7 + formant(chunk, a, 110)[-1] * 1.0

    # Amplitude envelope: fast attack, gentle decay, silent tail.
    env = np.clip(t / 0.06, 0, 1) * np.clip((1 - t) / 0.25, 0, 1) ** 0.9
    out *= env

    # A whisper of breath keeps it from sounding synthetic.
    out += 0.015 * rng.standard_normal(n) * env
    out /= max(1e-9, np.max(np.abs(out)))
    return out * 0.86


def trill(base: float, dur: float, seed: int) -> np.ndarray:
    """A short purring trill for the content/idle clip."""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    carrier = np.sin(2 * np.pi * base * t + 3.0 * np.sin(2 * np.pi * 26 * t))
    envelope = np.clip(np.sin(np.pi * t / dur) ** 0.8, 0, 1)
    return (carrier * envelope * 0.6 + 0.02 * rng.standard_normal(n) * envelope) * 0.8


def short_yip(seed: int) -> np.ndarray:
    """A clipped, indignant yip for the angry clip."""
    rng = np.random.default_rng(seed)
    n = int(SR * 0.34)
    t = np.linspace(0, 1, n, endpoint=False)
    f0 = 520 + 260 * np.exp(-((t - 0.12) ** 2) / 0.004) - 260 * t
    voice = glottal(n, f0, rng)
    out = np.zeros(n)
    for i in range(n):
        chunk = voice[max(0, i - 30):i + 1]
        if chunk.size == 0:
            continue
        out[i] = formant(chunk, 850, 200)[-1]
    env = np.clip(t / 0.03, 0, 1) * np.clip((1 - t) / 0.18, 0, 1)
    out *= env
    out /= max(1e-9, np.max(np.abs(out)))
    return out * 0.9


def write_wav(path: Path, samples: np.ndarray) -> None:
    audio = np.clip(samples, -1.0, 1.0)
    pcm = (audio * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(pcm.tobytes())


# Clip id → renderer. The ids are what the client asks for by name.
CLIPS = {
    "natsume": lambda: meow(430, 700, 330, 0.72, seed=11),
    "happy": lambda: meow(500, 820, 420, 0.52, seed=23, bright=1.15),
    "angry": lambda: short_yip(31),
    "surprised": lambda: meow(620, 980, 520, 0.34, seed=47, bright=1.3),
    "eat": lambda: trill(240, 0.85, 59),
    "purr": lambda: trill(180, 1.4, 67),
    "sleep": lambda: trill(150, 1.8, 71),
}


def to_mp3(wav: Path) -> Path:
    """Transcode a rendered clip to MP3, which is ~7x smaller than raw PCM.

    The published package ships MP3 (76 KiB for all seven clips instead of
    535 KiB of WAV). WAV stays the intermediate so the synth itself needs no
    encoder; if ffmpeg is missing the WAV is kept, because the host serves both.
    """
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print(f"  ! ffmpeg not found; keeping {wav.name} uncompressed")
        return wav
    mp3 = wav.with_suffix(".mp3")
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav),
         "-ac", "1", "-ar", str(SR), "-b:a", "96k", str(mp3)],
        check=True,
    )
    wav.unlink()
    return mp3


def main() -> None:
    if "--list" in sys.argv:
        for clip in CLIPS:
            print(clip)
        return
    keep_wav = "--wav" in sys.argv
    for clip, render in CLIPS.items():
        samples = render()
        path = OUT / f"{clip}.wav"
        write_wav(path, samples)
        if not keep_wav:
            path = to_mp3(path)
        print(f"  {path.relative_to(ROOT)}  {len(samples) / SR:.2f}s  "
              f"{path.stat().st_size / 1024:.0f} KiB")
    print("\nThese are SYNTHETIC PLACEHOLDERS. Replace them with your own audio of "
          "the same clip names to hear the real voice.")


if __name__ == "__main__":
    main()
