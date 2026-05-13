"""Daftar segment untuk format BO3 (3 Match x 3 Game x 3 phase + 4 intro = 31)."""

SOURCES = ["BOG-YT", "BOG-TT", "MPL-YT", "MPL-TT"]


def _build_segments():
    intro = ["Waiting Screen", "TVC", "Opening Caster", "Trivia"]
    matches = []
    for m in range(1, 4):
        for g in range(1, 4):
            for phase in ["Pre Game", "In Game", "Post Game"]:
                matches.append(f"Match {m} - Game #{g} {phase}")
    return intro + matches


SEGMENTS = _build_segments()
