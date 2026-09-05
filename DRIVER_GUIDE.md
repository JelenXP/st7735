# ST7735 driver guide (optimized) — for AI agents & developers

This explains how the optimized `st7735.py` driver works so any AI can use it correctly.
Target hardware: **Raspberry Pi Pico W (RP2040) or Pico 2 W (RP2350)**, MicroPython, ST7735(S)
128×160 TFT over SPI. The driver detects the chip at runtime (`sys.implementation._machine`) and
picks the correct CLOCKS register base for the SPI-clock boost; everything else is chip-agnostic.
Verified on RP2350; the RP2040 path uses the documented `0x40008000` CLOCKS base.

---

## TL;DR

- Classes in `st7735.py`:
  - **`TFTBuffered`** — full RGB565 framebuffer (~40 KB). **Use this for all real drawing** (lines, circles, text, moving scenes). ~140 FPS for complex scenes. The default and fastest.
  - **`TFTPaletted`** — palette framebuffer for low-RAM boards: `depth=8` (~20 KB, 256 colors) or `depth=4` (~10 KB, 16 colors). Same drawing API, colors are palette indices. See "Framebuffer memory modes".
  - **`TFTBanded`** — renders in horizontal strips (~5 KB), full color, via a `render(draw)` callback. Lowest RAM. See "Framebuffer memory modes".
  - **`TFT`** — legacy direct-to-SPI. Only good for pure full-screen fills (~184 FPS). Its `line()`/`circle()` are extremely slow (per-pixel SPI), do **not** use them for animation.
- `st7735.create()` gives a ready-to-draw display in one line; `initr()` automatically unlocks the SPI clock (see "clk_peri boost"). Pick a memory mode with `create(mode="full"|"gs8"|"gs4"|"banded")`.
- Convenience helpers: `d.text_size(...,height)` (text at any pixel height — dedicated 5×7 and 3×6 micro fonts keep small text sharp), `d.text_centered`, `d.mark_dirty` + `d.flush` (auto partial update for many objects), `d.backlight(level)` / `d.sleep()` / `d.wake()` (power).
- With `TFTBuffered`: draw into `d.fb` (a `framebuf.FrameBuffer`), then call `d.show()` **once** to push the frame. Nothing appears until `show()`.
- Make colors with `d.rgb(r, g, b)` or the `d.C_*` constants — they already fix this panel's BGR + byte-order quirk. Do **not** feed raw `TFTColor()` values to `d.fb`.

---

## Wiring / pins

Pins are **not fixed** — set them for your own board. `st7735.create()` takes every pin as a
keyword argument (`spi_id`, `sck`, `mosi`, `dc`, `rst`, `cs`, `bl`); the manual path passes them
to `SPI(...)` and `TFTBuffered(spi, DC, RST, CS, size)`. `bl` (backlight) may be `None` if you
drive it yourself. Default panel resolution is 128 (W) × 160 (H) but is a constructor argument.

---

## Quick start (the recommended path)

One-line setup with `st7735.create()` (does SPI + pins + backlight + init + clock boost). Pass
your own pin numbers:

```python
import st7735

d = st7735.create(spi_id=1, sck=SCK, mosi=MOSI, dc=DC, rst=RST, cs=CS, bl=BL)
#   -> ready TFTBuffered, ~63 MHz SPI, backlight on

d.fb.fill(0)                                     # black background
d.fb.line(0, 0, 127, 159, d.C_RED)
d.fb.ellipse(64, 80, 30, 30, d.C_GREEN, True)    # filled circle (x, y, xr, yr, color, fill)
d.fb.rect(10, 10, 40, 20, d.rgb(255, 120, 0), True)
d.fb.text("Ahoj", 8, 8, d.C_WHITE)              # built-in 8x8 font
d.show()                                         # <-- push whole frame in ONE SPI transfer
```

`create(buffered=True, baudrate=32_000_000, size=(128,160), spi_id=…, sck=…, mosi=…, dc=…,
rst=…, cs=…, bl=…)`. Pass `buffered=False` for the bare `TFT`. Manual setup (equivalent, if you
need custom control):

```python
from machine import Pin, SPI
import st7735
spi = SPI(SPI_ID, baudrate=32_000_000, polarity=0, phase=0, sck=Pin(SCK), mosi=Pin(MOSI))
d = st7735.TFTBuffered(spi, DC, RST, CS, (128, 160))  # (spi, DC, RST, CS, size)
d.initr()                                             # inits panel + unlocks SPI clock
spi.init(baudrate=32_000_000)                         # request >=24 MHz -> real ~63 MHz
d.attach_backlight(BL); d.backlight(100)
```

Animation loop pattern:

```python
while True:
    d.fb.fill(bg)          # clear
    # ... draw everything for this frame into d.fb ...
    d.show()               # blit
```

---

## Framebuffer memory modes (RAM vs color vs CPU)

A full RGB565 framebuffer is `width × height × 2` bytes = **~40 KB** at 128×160. That is fine on
the Pico 2 W (RP2350) but a big chunk of the Pico W's (RP2040) heap — and `set_background()`
**doubles** it (it keeps a second copy). Pick the mode per project:

| Mode | Class / `create(mode=…)` | RAM @128×160 | Colors | Cost |
|------|--------------------------|--------------|--------|------|
| Full RGB565 | `TFTBuffered` / `"full"` (default) | ~40 KB | full 16-bit | none — fastest, simplest |
| Palette 8-bit | `TFTPaletted(depth=8)` / `"gs8"` | ~20 KB (+~4 KB band) | 256 (palette) | small per-frame convert; ~slightly lower FPS |
| Palette 4-bit | `TFTPaletted(depth=4)` / `"gs4"` | ~10 KB (+~4 KB band) | 16 (palette) | same convert; fewest colors |
| Banded | `TFTBanded` / `"banded"` | ~5 KB (bandh=20) | full 16-bit | redraws the scene once per band (RAM→CPU) |

All four share the same drawing primitives and the `text_size` / Czech-diacritics helpers. Only
**how you feed colors** and **how you push a frame** differ. `set_background()` /
`restore_background()` also work on the palette modes (on a proportionally smaller copy).

> **Rule of thumb:** default to `TFTBuffered`. On a RAM-constrained Pico W, use `"gs8"` if you
> want easy full-featured drawing at half the RAM, `"gs4"` if 16 colors are enough (quarter RAM),
> or `"banded"` if you need the absolute minimum and can structure drawing as a per-band callback.

### Palette modes — `TFTPaletted` (`"gs8"` / `"gs4"`)

Draw with **palette indices** instead of `rgb()` values. The first 16 entries have sensible
defaults with `P_*` constants; redefine any entry with `set_palette(index, r, g, b)`.

```python
import st7735
d = st7735.create(mode="gs8", sck=…, mosi=…, dc=…, rst=…, cs=…, bl=…)   # ~20 KB
d.set_palette(9, 255, 140, 0)                 # index 9 = orange (already the default)

d.fb.fill(d.P_BLACK)
d.fb.ellipse(64, 80, 26, 26, d.P_GREEN, True) # colors are indices, not d.C_*
d.text_size("Ahoj", 8, 8, d.P_WHITE, 12)      # text/Czech work the same
d.show()                                       # converts palette → RGB565 in bands, then blits
```

Defaults: `P_BLACK=0 P_WHITE=1 P_RED=2 P_GREEN=3 P_BLUE=4 P_YELLOW=5 P_CYAN=6 P_PURPLE=7
P_GRAY=8 P_ORANGE=9` (indices 10–15 are grays/darks). `depth=4` (`"gs4"`) is identical but only
indices 0–15 exist. `bandh` (default 16) sets the conversion strip height — smaller = less RAM,
slightly more overhead. `show()`, `show_area()`, `mark_dirty`/`flush` all work.

### Banded mode — `TFTBanded` (`"banded"`)

Keeps only a `bandh`-row strip. You provide a `draw(fb, y0)` callback that redraws the **whole
scene** shifted up by `y0` (draw at `screen_y - y0`); it is called once per band. Off-band pixels
are clipped, so you can draw everything each time. Colors are normal `rgb()` / `C_*`.

```python
import st7735
d = st7735.create(mode="banded", bandh=20, sck=…, mosi=…, dc=…, rst=…, cs=…, bl=…)  # ~5 KB
W, H = d.width, d.height

def draw(fb, y0):
    fb.fill(d.C_BLACK)
    fb.rect(0, 0 - y0, W, H, d.C_WHITE)
    fb.ellipse(64, 80 - y0, 26, 26, d.C_GREEN, True)
    d.text_size("Ahoj", 8, 8 - y0, d.C_WHITE, 12)

d.render(draw)     # renders all bands and pushes them; call once per frame
```

`render()` replaces `show()` here; `show()` / `show_area()` raise `NotImplementedError` on this
class. CPU scales with (scene cost × number of bands), so keep the per-band drawing lean or use a
taller `bandh` to trade RAM back for speed.

---

## Drawing API (`d.fb` = `framebuf.FrameBuffer`, RGB565)

All primitives are C-implemented in MicroPython's `framebuf`, so they are effectively free (µs) compared to SPI:

- `d.fb.fill(color)`
- `d.fb.pixel(x, y, color)`
- `d.fb.hline(x, y, w, color)` / `d.fb.vline(x, y, h, color)`
- `d.fb.line(x1, y1, x2, y2, color)`
- `d.fb.rect(x, y, w, h, color, fill=False)`
- `d.fb.ellipse(x, y, xr, yr, color, fill=False)` — circle = equal radii
- `d.fb.text(string, x, y, color)` — 8×8 font, ASCII
- `d.fb.blit(src_fb, x, y[, key])` — draw another framebuffer (sprites/images)
- `d.fb.scroll(dx, dy)`

Then **always** `d.show()` to make it visible.

### Text at ANY size

The base font is 8×8, but text can be drawn at any pixel height. `text_size()` picks the right
font automatically for the requested height: **≥8 px** nearest-neighbor scales the built-in 8×8
font (crisp at whole multiples); **7 px** uses a dedicated **5×7 font**; **≤6 px** uses a
dedicated **3×6 micro font** (so 5–6 px text stays legible instead of falling apart when a bigger
font is downscaled).

- `d.text_size(str, x, y, color, height, bg=None, spacing=None)` — draw at an exact pixel
  `height` (e.g. 6, 7, 10, 25, 40…). This is the main one. Returns the x past the text.
- `d.text_scaled(str, x, y, color, scale=1, bg=None)` — size as a multiple of 8; `scale` may be
  fractional (e.g. `1.5` → 12 px).
- `d.text_centered(str, y, color, scale=1, bg=None, height=None)` — horizontally centered; pass
  either `scale` or `height`.
- `d.text_width(str, height=None, scale=1, spacing=None)` — pixel width of a string at a size
  (for your own layout/alignment).
- `bg` fills the text background (None = transparent). `spacing` adds extra px between chars.

```python
d.text_size("Teplota 23C", 4, 4, d.C_WHITE, 7)     # small, sharp (5×7 font)
d.text_size("SCORE 42", 4, 20, d.C_WHITE, 16)      # big
d.text_centered("GAME OVER", 70, d.C_RED, height=32)
```

The 3×6 micro font keeps 5–6 px text readable; ~5 px is the practical smallest on this 1.8"
panel. Base charset is ASCII 0x20–0x7E; unknown chars render as `?`.

**Czech diacritics are supported** at every size (á č ď é ě í ň ó ř š ť ú ů ý ž + uppercase).
They are drawn procedurally: each accented char maps (in `_CZ`) to a base ASCII letter plus an
accent type, and the mark (čárka / háček / kroužek / apostrof) is composited just above the
letter's actual ink top, centered on it, scaling and thickening with the font size. So Czech
works at any pixel height with no extra font tables. Just pass normal Czech strings:
`d.text_size("Příliš žluťoučký kůň", 4, 4, d.C_WHITE, 12)`. Leave a couple px of headroom above
accented lines (accents sit above the letter box).

---

## Colors (important gotcha)

This panel runs in **BGR** order (MADCTL `0xC8` set in `initr()`), and `framebuf`'s RGB565
is stored **little-endian** while the panel reads **big-endian**. `TFTBuffered` fixes both:

```python
@staticmethod
def rgb(aR, aG, aB):
    c = TFTColor(aB, aG, aR)                 # swap R<->B for the BGR panel
    return ((c & 0xFF) << 8) | (c >> 8)      # swap bytes for framebuf endianness
```

- **Always** get colors from `d.rgb(r, g, b)` or the pre-swapped constants:
  `d.C_BLACK, d.C_RED, d.C_GREEN, d.C_BLUE, d.C_WHITE, d.C_YELLOW, d.C_CYAN, d.C_PURPLE`.
- **Never** pass a raw `st7735.TFTColor(...)` / `TFT.RED` value into `d.fb.*` — colors will be wrong.
- Verified on real hardware: R/G/B/W bars display correctly with `d.C_*`.

---

## Why it's fast: the two optimizations

### 1. `clk_peri` boost (unlocks the SPI clock) — `boost_peri_clock()`
On RP2350, MicroPython clocks the SPI peripheral from the 48 MHz USB PLL, capping the real
SPI clock at ~20 MHz **regardless of the requested baudrate or `machine.freq()`**. The driver
repoints `clk_peri` to the system PLL by writing `CLK_PERI_CTRL` (CLOCKS base + `0x48`):
disable bit 11, set AUXSRC[7:5]=1 (`clksrc_pll_sys`), re-enable. The CLOCKS base is chosen per
chip — `0x40010000` on RP2350, `0x40008000` on RP2040 (register layout is identical) — via
`_clocks_base()`; on an unrecognized chip the boost is skipped. This drops a full-frame transfer
from 16.2 ms to 5.2 ms (SPI ceiling 62 → 192 FPS). Called automatically from `initr()` and safe
for the USB-CDC REPL (that runs off the USB PLL, not `clk_peri`).

- After the boost, requested baudrate maps to real clock roughly: req 12–20 MHz → ~31 MHz real;
  req ≥24 MHz → ~63 MHz real (verified visually clean on this panel). Request `32_000_000`.

### 2. Framebuffer (makes complex drawing cheap) — `TFTBuffered`
Direct-to-SPI primitives address every pixel individually (each `pixel()` ≈ 6 tiny SPI
transactions ≈ 400 µs). A realistic scene ran **4.1 FPS**. Drawing into a RAM framebuffer and
blitting once gives **142 FPS** for the same scene — the frame is then dominated only by the
single ~5.3 ms SPI blit, so scene complexity is nearly free.

### (also) Fast fill path in `TFT`
`TFT.fill()` caches the fill-pattern buffer per color (avoids a ~2 ms/frame rebuild) and skips
`CASET`/`RASET` on repeated full-screen fills (sends only `RAMWR`). Full-screen fill ≈ 184 FPS.

---

## Performance reference (128×160, real ~63 MHz SPI)

| Operation | Time / FPS |
|-----------|-----------|
| Full-screen fill (`TFT.fill`) | 5.44 ms → **184 FPS** |
| Raw 40 960-byte SPI blit (`show`) | ~5.2–5.3 ms (hard floor) |
| Complex scene, direct `TFT` primitives | 243 ms → **4.1 FPS** ❌ |
| Complex scene, `TFTBuffered` + `show()` | 7.0 ms → **142 FPS** ✅ |
| Same scene drawn into RAM only (no `show`) | 1.67 ms |
| Moving ball over static scene, `show_area()` | 3.1 ms → **324 FPS** (2.2×) |
| Two moving balls, `mark_dirty()` + `flush()` | 3.9 ms → **255 FPS** |

The ~5.2 ms SPI blit is the hardware floor for a full 128×160 RGB565 frame at this clock;
you cannot beat it without a higher panel clock (risky) or a narrower update region.

---

## Partial / dirty-rectangle update (`show_area`) — draw only what changed

`show()` always blits the whole frame (~5.2 ms floor). If most of the screen is static and
only a small region moves, send just that region with **`d.show_area(x, y, w, h)`**. It
transfers only `w*h*2` bytes from the framebuffer, so small regions are much faster.

```python
d.show_area(x, y, w, h)   # blit only this rectangle of the framebuffer to the panel
```

How it works: it sets the panel's address window to the rectangle, then streams the matching
rows out of the RAM framebuffer (a full-width region is one contiguous write; a narrower one is
sent row-by-row via zero-copy `memoryview` slices). Out-of-bounds rectangles are clipped.

**Rules for correct partial updates:**
1. The framebuffer (`d.fb`) must already hold the finished frame — draw into it as usual first,
   then `show_area`. `show_area` never draws; it only transfers pixels already in RAM.
2. For a moving object you must refresh **both** its old and its new position, or a "ghost"
   stays behind. Blit the **union** of the old and new bounding boxes:
   ```python
   ox, oy = x, y                 # remember previous position
   x += dx; y += dy              # move
   draw_scene(x, y)              # redraw into d.fb (or at least the changed area)
   x0 = min(ox, x) - R - 1; y0 = min(oy, y) - R - 1
   w  = abs(x - ox) + 2*R + 3;  h = abs(y - oy) + 2*R + 3
   d.show_area(x0, y0, w, h)     # one blit covers old + new
   ```
3. `show_area` invalidates the fast-fill window; the next full `show()`/`fill()` re-sets it
   automatically — no action needed.
4. To also save the RAM drawing cost, redraw only the dirty rectangle into `d.fb` instead of
   the whole scene (keep a static background copy and restore just that rectangle).

Measured (moving 12 px ball over a static scene, real ~63 MHz SPI): full `show()` = **147 FPS**,
`show_area` on the ball's region = **324 FPS** (2.2×). The bigger the static area, the bigger
the win; a full-screen change gives no benefit (blit the whole frame instead).

### Automatic dirty-rectangle manager (`mark_dirty` + `flush`)

For **several** moving objects, use the built-in dirty tracker instead of calling `show_area`
by hand. Call `d.mark_dirty(x, y, w, h)` for each region that changed (old and new position of
each object), then `d.flush()` once — it **merges overlapping rectangles** and blits the minimal
set of regions, then clears the list. Draw into `d.fb` first; `flush` only transfers.

```python
for obj in objects:
    ox, oy = obj.x, obj.y
    obj.move()
    d.mark_dirty(min(ox,obj.x)-R-1, min(oy,obj.y)-R-1, abs(obj.x-ox)+2*R+3, abs(obj.y-oy)+2*R+3)
draw_scene()          # redraw everything into d.fb (cheap)
d.flush()             # sends only the changed regions
```

Measured with two moving balls: **255 FPS** (vs 147 for full `show()`). If you mark nothing,
`flush()` does nothing.

---

## Static-background caching (big win for complex mostly-static scenes)

If most of the scene is static and only a few things move, don't re-run all the primitives every
frame (that Python work is the bottleneck, especially on RP2040). Draw the static part once,
snapshot it, then each frame restore it with a fast C copy and draw only the moving parts.

- `d.set_background()` — snapshot the current framebuffer as the background (call once, after
  drawing the static scene). Allocates one extra `w*h*2` buffer the first time.
- `d.restore_background()` — copy the whole background back into the framebuffer (one fast C
  `bytearray` copy, ~0.2 ms) instead of redrawing primitives.
- `d.restore_background_area(x, y, w, h)` — restore only a rectangle (e.g. erase a moving
  object's old position); pairs with `show_area()`.

```python
draw_static_scene()          # rects, grid, labels, ... into d.fb
d.set_background()            # snapshot once
while True:
    d.restore_background()   # fast erase (C copy) instead of re-running primitives
    d.fb.ellipse(x, y, 10, 10, col, True)   # only the moving parts
    d.show()
```

Measured (complex scene, one moving ball, RP2350): re-drawing everything + `show()` = **56 FPS**;
`restore_background()` + `show()` = **175 FPS** (3.1×). On RP2040 (slower CPU) the gap is larger,
since it removes exactly the Python-heavy work. Purely additive — existing code is unaffected.

---

## Power saving & backlight

- `d.backlight(level)` — brightness 0–100 % via PWM (0 = off, 100 = full). Needs a backlight pin,
  which `create()` registers automatically (or call `d.attach_backlight(pin)` after manual setup).
- `d.sleep()` — panel sleep (SLPIN) + display off + backlight off. Low power.
- `d.wake()` — resume (SLPOUT) + display on + restore last brightness.

```python
d.backlight(30)     # dim
d.sleep()           # ... idle / battery save ...
d.wake()            # back, brightness restored
```

---

## Decision rules for an AI using this driver

1. Any drawing beyond a solid full-screen fill → use **`TFTBuffered`**, draw into `d.fb`, call `d.show()`.
2. Colors → **only** `d.rgb(...)` or `d.C_*`. Never raw `TFTColor`/`TFT.*` constants with `d.fb`.
3. Forgot `d.show()` → screen stays blank; every frame must end with `d.show()`.
4. Want max fill-only throughput (e.g. clearing) → `TFT`/`TFTBuffered` share the fast fill; a scene should still go through the framebuffer.
5. Request SPI `baudrate >= 24_000_000` after `initr()` for the ~63 MHz real clock.
6. Don't try to raise FPS past ~140–184 by tweaking SPI request values — it's already at the transfer floor; reduce what you redraw or the frame area instead.
7. Mostly-static screen with a small moving part → redraw `d.fb` and call `d.show_area(...)` on the union of the old+new region instead of `d.show()`.
8. Several moving objects → `d.mark_dirty(...)` per changed region + a single `d.flush()`.
9. Setup → `st7735.create()` (one line). Text at any size → `d.text_size(str, x, y, color, height)` (≈7 px smallest legible). Centered → `d.text_centered`. Dim/idle → `d.backlight(level)` / `d.sleep()` / `d.wake()`.
10. Complex mostly-static scene (esp. on RP2040) → `d.set_background()` once, then `d.restore_background()` + draw movers each frame instead of re-running primitives.
