"""Town tune audio synthesis for Animal Crossing Tunes.

Attempts to recreate the bright, bell-like celesta sound of the
Animal Crossing town tune editor. Uses additive synthesis with
harmonic partials tuned to approximate a struck-bell/celesta timbre.
"""
from __future__ import annotations

import logging
import math
import os
import struct
import wave

_LOGGER = logging.getLogger(__name__)

# ── Note definitions ──────────────────────────────────────────────
# Animal Crossing town tunes span roughly two octaves.
# Lower-case = lower octave, upper-case = upper octave,
# matching the ACNH note grid layout.
#
# The config UI uses single-character codes:
#   g a b c d e f  (lower octave: G3–F4)
#   G A B C D E F  (upper octave: G4–F5)  — note: AC only goes to E5
#   z = rest, - = sustain previous note
#
# For backwards compatibility the old uppercase-only mapping still works.

TOWN_TUNE_NOTES: dict[str, float] = {
    # Lower octave
    "g": 196.00,   # G3
    "a": 220.00,   # A3
    "b": 246.94,   # B3
    "c": 261.63,   # C4  (middle C)
    "d": 293.66,   # D4
    "e": 329.63,   # E4
    "f": 349.23,   # F4
    # Upper octave
    "G": 392.00,   # G4
    "A": 440.00,   # A4
    "B": 493.88,   # B4
    "C": 523.25,   # C5
    "D": 587.33,   # D5
    "E": 659.25,   # E5
    "F": 698.46,   # F5
    # Special
    "z": 0.0,      # rest
    "x": 0.0,      # rest (ACNH_tunes compat)
    "-": -1.0,     # sustain (hold previous note)
}

TOWN_TUNE_LENGTH = 16
SAMPLE_RATE = 44100  # CD quality for better high-frequency reproduction
NOTE_DURATION = 0.30  # seconds per note slot — matches the in-game town tune speed

# ── Synthesis parameters ──────────────────────────────────────────
# The AC town tune has a bright, metallic, bell/celesta quality.
# We approximate this with additive synthesis: a fundamental plus
# several inharmonic partials at ratios typical of struck metal bars
# (similar to a glockenspiel or celesta).

# (frequency_ratio, amplitude, decay_rate)
# Higher partials decay faster, giving the bright "ting" attack.
PARTIALS = [
    (1.0,   0.45,  4.0),   # fundamental
    (2.0,   0.25,  5.5),   # octave
    (3.0,   0.12,  7.0),   # 12th
    (4.0,   0.08,  9.0),   # 2nd octave
    (5.92,  0.05, 12.0),   # inharmonic — gives bell character
    (8.0,   0.03, 15.0),   # high shimmer
]

# Master envelope
ATTACK_TIME = 0.003   # 3ms — very fast percussive attack
DECAY_RATE = 3.5       # base exponential decay

# Default town tune (the classic AC default melody)
DEFAULT_TOWN_TUNE = [
    "C", "C", "C", "E",
    "D", "D", "D", "F",
    "E", "E", "D", "D",
    "C", "-", "z", "z",
]


def validate_town_tune(notes: list[str]) -> bool:
    """Validate a town tune note sequence."""
    if len(notes) != TOWN_TUNE_LENGTH:
        return False
    return all(note in TOWN_TUNE_NOTES for note in notes)


def _generate_samples(notes: list[str]) -> list[int]:
    """Generate PCM samples for a town tune using additive bell synthesis."""
    samples_per_note = int(SAMPLE_RATE * NOTE_DURATION)
    # Extra ring-out time after last note so it doesn't cut off abruptly
    ring_out_samples = int(SAMPLE_RATE * 0.4)
    total_samples = TOWN_TUNE_LENGTH * samples_per_note + ring_out_samples

    # Work in float, convert to int16 at the end
    buf = [0.0] * total_samples

    current_freq = 0.0
    attack_samples = max(1, int(SAMPLE_RATE * ATTACK_TIME))

    for note_idx, note in enumerate(notes):
        freq = TOWN_TUNE_NOTES.get(note, 0.0)

        if freq == -1.0:
            # Sustain — don't start a new note, previous one keeps ringing
            continue
        if freq <= 0.0:
            # Rest
            current_freq = 0.0
            continue

        current_freq = freq
        start = note_idx * samples_per_note
        # Let each note ring for the remaining duration of the tune
        ring_length = total_samples - start

        for i in range(ring_length):
            t_sec = i / SAMPLE_RATE
            t_note = i / ring_length  # 0..1 over the ring duration

            # Master envelope: fast attack, exponential decay
            if i < attack_samples:
                env = i / attack_samples
            else:
                env = math.exp(-DECAY_RATE * t_sec)

            # Exit early once envelope is negligible (only after attack)
            if i >= attack_samples and env < 0.001:
                break

            # Additive synthesis of bell partials
            sample = 0.0
            for ratio, amp, partial_decay in PARTIALS:
                partial_freq = freq * ratio
                # Each partial has its own decay (higher partials fade faster)
                partial_env = amp * math.exp(-partial_decay * t_sec)
                sample += partial_env * math.sin(
                    2.0 * math.pi * partial_freq * t_sec
                )

            buf[start + i] += sample * env

    # Normalize to avoid clipping, then scale to int16 range
    peak = max(abs(s) for s in buf) or 1.0
    scale = 28000.0 / peak  # leave a little headroom

    result: list[int] = []
    for s in buf:
        value = int(s * scale)
        value = max(-32768, min(32767, value))
        result.append(value)

    return result


def generate_town_tune_wav(
    notes: list[str] | None = None,
    output_path: str = "",
) -> str:
    """Generate a WAV file for a town tune and return the file path.

    Args:
        notes: List of 16 note characters. Uses DEFAULT_TOWN_TUNE if None.
        output_path: Full path for the output WAV file.

    Returns:
        The path to the generated WAV file.
    """
    if notes is None:
        notes = DEFAULT_TOWN_TUNE

    if not validate_town_tune(notes):
        _LOGGER.error("Invalid town tune: %s, using default", notes)
        notes = DEFAULT_TOWN_TUNE

    samples = _generate_samples(notes)

    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with wave.open(output_path, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    _LOGGER.debug(
        "Generated town tune WAV at %s (%d samples, %.1fs)",
        output_path,
        len(samples),
        len(samples) / SAMPLE_RATE,
    )
    return output_path
