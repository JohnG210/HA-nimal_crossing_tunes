"""Town tune support for Animal Crossing Tunes (Phase 2 placeholder)."""
from __future__ import annotations

# Town tune note definitions matching Animal Crossing's town tune editor.
# Each note maps to a MIDI-like pitch value for future audio synthesis.
TOWN_TUNE_NOTES = {
    "G": 67,
    "A": 69,
    "B": 71,
    "C": 72,
    "D": 74,
    "E": 76,
    "F": 77,
    "z": -1,  # rest
    "-": 0,  # sustain (hold previous note)
}

# Town tunes are 16 notes long
TOWN_TUNE_LENGTH = 16

# Default town tune (the classic AC default)
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
