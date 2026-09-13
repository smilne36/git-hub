# Auto-mastering engine

A small, honest command-line tool that takes a **stereo bounce** you export from
Ableton Live (or any DAW) and turns it into a **streaming-ready master** — even
tone, glued dynamics, competitively loud, and safe against clipping.

It is transparent DSP, not a black box: subsonic filter → tone EQ → glue
compression → limiter → loudness normalisation. You can read exactly what happens
to your audio in [`masterlib/chain.py`](masterlib/chain.py).

## Mixing vs. mastering (what this is and isn't)

- **Mixing** balances your *separate* tracks (drums, bass, vocals…). You do that
  in Ableton with all your individual channels. This tool does **not** do that.
- **Mastering** is the final polish on the *single stereo file* you bounce out of
  your mix — overall tone, glue, and loudness so it holds up next to commercial
  releases. **That is what this tool does.**

So the workflow is: mix in Ableton → **export one stereo WAV** → run it through
this → upload the result to SoundCloud/Spotify.

> **About "Dolby Atmos":** true Atmos is object-based *spatial* audio and its
> encoder is licensed by Dolby — you can't make real Atmos files with open tools.
> This engine is a stereo mastering tool, which is what actually makes your
> uploads sound loud and polished. A DIY *binaural/spatial* mixer is a separate,
> bigger project; ask if you want to explore it.

## Install

```bash
cd mastering
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Use

```bash
# Master a bounce to the streaming default (-14 LUFS, -1 dBTP true-peak ceiling):
python master.py mysong.wav
# -> writes mysong.mastered.wav

# Just measure a file and change nothing:
python master.py mysong.wav --analyze

# Brighter, harder, aimed at club loudness, and also export an MP3:
python master.py mysong.wav --tone bright --strength strong --target club --mp3

# Nudge the tonal balance toward a track you love:
python master.py mysong.wav --reference favourite_track.wav
```

Run `python master.py -h` for every option.

### Key options

| Option | What it does | Default |
| --- | --- | --- |
| `--target` | Named loudness target: `streaming`, `apple`, `cd`, `club`… | `streaming` (-14 LUFS) |
| `--target-lufs` | Explicit loudness target in LUFS | `-14.0` |
| `--true-peak` | True-peak ceiling in dBTP | `-1.0` |
| `--tone` | `transparent`, `warm`, `bright`, `open` | `transparent` |
| `--strength` | Compression/limiting intensity: `light`, `medium`, `strong` | `medium` |
| `--reference FILE` | Match tonal balance to a reference track | off |
| `--mp3` | Also write a 320 kbps MP3 | off |

## Why -14 LUFS?

Spotify, YouTube, and SoundCloud normalise playback toward roughly **-14 LUFS**.
A master that's much louder than that just gets turned *down* on playback — so you
lose dynamics for no gain in perceived loudness. `-14 LUFS / -1 dBTP` is the safe,
competitive default. Use `--target club` (-8) only when you specifically need a hot
file for DJ/club playback.

## How it works

For each file the engine:

1. Removes DC offset and filters subsonic rumble below 30 Hz (frees up headroom).
2. Applies your chosen tone EQ (and optional reference-match EQ, capped at ±4 dB).
3. Runs a slow, low-ratio **glue compressor** for cohesion — not squashing.
4. Iterates makeup gain into a **brickwall limiter** until the measured integrated
   loudness (ITU-R BS.1770 / `pyloudnorm`) lands on your target.
5. Verifies the **inter-sample true peak** (4× oversampled) stays under the
   ceiling, scaling down slightly if needed.

It prints a before/after report so you can see exactly what changed:

```
  before   LUFS  -24.7   true-peak  -13.6 dBTP   peak  -13.6 dBFS   crest 15.8 dB
  after    LUFS  -14.0   true-peak   -3.2 dBTP   peak   -3.2 dBFS   crest 15.9 dB
```

## Test

```bash
python tests/smoke_test.py
```

Generates synthetic audio, masters it, and asserts the output hits its loudness
target, respects the true-peak ceiling, and survives a round-trip through disk.

## Built on

[`pedalboard`](https://github.com/spotify/pedalboard) (Spotify's DSP engine),
[`pyloudnorm`](https://github.com/csteinmetz1/pyloudnorm) (loudness measurement),
`soundfile`, `numpy`, and `scipy`.
