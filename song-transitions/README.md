# Song Transitions

Give it one of your songs and a pile of candidates (local files, SoundCloud links, Spotify
playlists). It ranks which songs mix best **into** your track and **out of** it, then renders
audio previews of each transition so you can hear them.

Built with house, tech house, techno and dancehall in mind: it beatmatches when tempos are close
and switches to selector-style moves (echo out and drop) when they aren't.

## Setup

```bash
cd song-transitions
pip install -r requirements.txt
# ffmpeg is needed for mp3/m4a input and mp3 previews (otherwise previews are .wav)
#   macOS: brew install ffmpeg    Windows: winget install ffmpeg    Linux: apt install ffmpeg
```

## Use it

```bash
# Local folder of tracks
python -m transitions suggest "~/Music/my tune.wav" --library ~/Music/House ~/Music/Dancehall

# Add SoundCloud tracks / sets / profiles, and a Spotify playlist
python -m transitions suggest my_tune.wav \
    --library ~/Music \
    --soundcloud https://soundcloud.com/artist/sets/some-set \
    --spotify https://open.spotify.com/playlist/XXXXXXXX --soundcloud-fallback

# Your song can be a SoundCloud link too
python -m transitions suggest https://soundcloud.com/you/your-track --library ~/Music

# Just inspect BPM / key / intro / outro
python -m transitions analyze ~/Music/House
```

Useful options: `--top 10` (list length), `--render 3` (previews for the top N each way, `0` to
skip), `--bars 32` (force a longer blend), `--lead/--tail 20` (seconds of context in previews),
`--keylock always|never|auto`, `--out folder`.

### What you get

In `transitions_out/<your song>/`:

- **`report.html`**: both ranked lists with scores, reasons and an audio player per preview
- **`previews/`**: rendered transitions (`before_01_X__to__yours.mp3`, `after_01_yours__to__Y.mp3`)
- **`results.csv` / `results.json`**: the full list, including the exact mix-out / mix-in times
  so you can recreate the transition in your DAW or DJ software

The list is also printed in the terminal:

```
Play AFTER my_song
 1.  85.2  Tech House 126 Em  [local]
           BPM 124.0 -> 126.0, next track slowed 1.6% to beatmatch
           Key Am (8A) -> Em (9A): adjacent on Camelot wheel
           Energy close (outro beat, intro beat)
           Transition: blend over 16 bars
```

## How it decides

Each track is analysed once (results cached in `~/.cache/song-transitions`):
BPM and beat grid, downbeats, key (Camelot code), loudness, and the character of the intro and
outro (`beat` = DJ-friendly drums, `ambient` = no kick, `fade` = fades out).

A pair is scored out of 100 from:

| Part        | Weight | What it measures                                                    |
|-------------|-------:|---------------------------------------------------------------------|
| Tempo       | 30%    | BPM distance, counting half/double time (70 BPM riddim on a 140 grid) |
| Key         | 25%    | Camelot wheel: same key, ±1, relative major/minor, etc. Trusted less on drum-only tracks |
| Energy      | 15%    | Outro of the first vs intro of the second: level, density, bass, brightness |
| Timbre      | 15%    | How similar the two sections sound (MFCCs)                          |
| Mixability  | 15%    | Whether a clean beatmatched blend is possible                       |

### Transition styles

- **Blend** (tempos within 6%): the next track is sped up or slowed to match, its first downbeat
  lands on a downbeat of the outgoing track, and the two run together for 8 or 16 bars. The highs
  fade across and the **bass swaps** halfway through so the two kicks and basslines never stack.
  Nudges up to 3% are done vinyl-style (pitch moves slightly); larger ones use key lock.
- **Echo out** (tempos too far apart, e.g. dancehall ↔ house): the outgoing track is cut on the
  bar with a beat-synced delay tail and the next tune drops in.
- **Fade** (outgoing track has a real fade-out and can't be beatmatched): equal-power crossfade
  across the fade.

The incoming track is also level-matched, so there's no volume jump.

## Sources: what works and what doesn't

- **Local files**: full support (mp3, wav, flac, aiff, m4a, ogg, opus). Best results; use
  lossless or high-bitrate files where you can.
- **SoundCloud**: downloads public tracks, sets and profile pages via `yt-dlp`. Go+-only tracks
  only give a 30-second preview. Only use tracks you have the right to use (your own uploads, free
  downloads, or tracks the artist allows).
- **Spotify**: Spotify doesn't provide audio (or audio features) to third-party apps, so the tool
  reads the **track names** from a playlist, album or track link and finds the audio in your local
  library (matched by tags or filename). With `--soundcloud-fallback`, missing tracks are searched
  on SoundCloud instead; check the match, since the search can land on a different version or remix.
  Needs a free app from <https://developer.spotify.com/dashboard>:
  ```bash
  export SPOTIPY_CLIENT_ID=...  SPOTIPY_CLIENT_SECRET=...
  ```
  New Spotify apps can't read Spotify-owned editorial or algorithmic playlists; user playlists work.

## Limitations

- Downbeat detection is a heuristic. On tracks with long breakdowns or swung dancehall riddims
  it can land a beat off; the CSV gives the exact times so you can adjust.
- BPM detection can halve or double the tempo. The matcher treats half and double time as
  equivalent, so ranking isn't affected, but the printed BPM may be off by 2×.
- Assumes a fairly steady tempo (true for nearly all house, techno and dancehall).

## Tests

```bash
pip install pytest
python -m pytest -q
```

The tests generate synthetic house, techno and dancehall tracks with known BPM and key, then
check analysis, ranking, transition planning and rendering.
