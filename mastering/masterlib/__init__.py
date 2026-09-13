"""A small, honest auto-mastering engine for a stereo bounce.

Feed it the stereo WAV you export from Ableton (or any DAW) and it applies a
classic mastering chain -- subsonic filter, gentle tone shaping, glue
compression and a brickwall limiter -- then normalises to a streaming loudness
target while keeping the true peak under a safe ceiling.

Nothing here is magic or AI: it is transparent DSP built on Spotify's
`pedalboard`, `pyloudnorm` for ITU-R BS.1770 loudness measurement, and
`soundfile` for I/O. Read `chain.py` to see exactly what happens to your audio.
"""

from .chain import master, MasterResult
from .analysis import analyze, LoudnessStats

__all__ = ["master", "MasterResult", "analyze", "LoudnessStats"]
