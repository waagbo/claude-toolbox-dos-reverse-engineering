# Rendering artifacts

Decoded output goes under `artifacts/<topic>/` (git-ignored, regenerable
from the probe that made it) with an `INDEX.md`: one line per file saying
what it is and what the reviewer should see in it.

| Format | Artifact |
|---|---|
| video | `.mp4` with its audio, at the engine's real frame rate |
| images / sprites / fonts | `.png`, small sprites upscaled ×3 nearest-neighbour |
| audio | `.wav` + a waveform `.png` |
| tables | annotated decoded dump; a graph render where the data is a graph |

Every upscale is nearest-neighbour (`flags=neighbor`, `Image.NEAREST`):
exact pixel replication, nothing invented. Static exports keep the native
palette — no auto-brightening or gamma; dark frames stay dark.

## Palettes

VGA DAC palettes are 256 × 3 bytes of **6-bit** values (0..63). Expand to
8-bit with `(v << 2) | (v >> 4)` — that maps 63 to 255; a bare `<< 2`
tops out at 252. A trailing 768-byte (or 768 + small trailer) block on an
image file is usually its palette.

```python
from PIL import Image
pal6 = open('pal.pal', 'rb').read()[:768]
pal8 = bytes((v << 2) | (v >> 4) for v in pal6)
img = Image.frombytes('P', (320, 200), pixels)       # one byte per pixel
img.putpalette(pal8)
img.resize((960, 600), Image.NEAREST).save('frame.png')
```

## Video

```bash
# a container ffmpeg already decodes (e.g. Interplay .c93)
ffmpeg -hide_banner -loglevel warning -y -i intro.c93 \
  -c:v libx264 -crf 18 -preset veryfast -pix_fmt yuv420p \
  -vf scale=iw*2:ih*2:flags=neighbor -c:a aac -b:a 128k intro.mp4

# frames your own decoder produces: pipe raw RGB, mux the wav
python3 mydecoder.py --raw-rgb file.vid | ffmpeg -y -loglevel error \
  -f rawvideo -pix_fmt rgb24 -s 320x200 -r 15 -i - -i file.wav \
  -vf scale=iw*2:ih*2:flags=neighbor -c:v libx264 -crf 18 -pix_fmt yuv420p \
  -c:a aac -shortest file.mp4

# a PNG / PPM sequence (e.g. a headless port's --snap frames)
ffmpeg -y -framerate 15 -i frame_%04d.ppm -c:v libx264 -pix_fmt yuv420p seq.mp4
```

`-r` is the engine's real rate, taken from the binary (its timer divisor
or tick handler), never a guess; log the audio-vs-video duration drift so
a wrong rate shows up as a number.

## Audio

```bash
# raw 8-bit unsigned mono PCM at the rate the header / driver programs
ffmpeg -y -f u8 -ar 11025 -ac 1 -i clip.raw clip.wav
# signed 16-bit little-endian
ffmpeg -y -f s16le -ar 22050 -ac 1 -i clip.raw clip.wav
# waveform picture for the INDEX
ffmpeg -y -i clip.wav -filter_complex showwavespic=s=1200x200 -frames:v 1 clip.png
```

Creative Voice files (`.VOC`) play and convert directly: `ffmpeg -i X.VOC X.wav`.

## Sheets and graphs

```bash
montage out/*.png -tile 8x -geometry +2+2 -background '#202020' sheet.png
dot -Tsvg states.dot -o states.svg     # or -Tpng
```
