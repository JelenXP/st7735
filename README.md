# ST7735 driver for Raspberry Pi Pico — optimized fork

A performance-optimized MicroPython driver for **ST7735(S) 128×160 SPI TFT** displays,
running on the **Raspberry Pi Pico W (RP2040)** and **Pico 2 W (RP2350)**.

This is a fork of [micropython-st7735](https://github.com/alastairhm/micropython-st7735)
by Alastair Montgomery (itself based on work by Guy Carver and boochow), rewritten into a
single-file driver with a framebuffer class, much higher frame rates, and extra developer
conveniences.

## What's different from the original

- **SPI clock boost** — `initr()` repoints `clk_peri` from the 48 MHz USB PLL to the
  system PLL, lifting the SPI ceiling from ~20 MHz to ~63 MHz. Full-screen fills went from
  ~52 FPS to ~184 FPS. The chip (RP2040 vs RP2350) is detected at runtime; the boost is a
  safe no-op on unknown chips.
- **`TFTBuffered` framebuffer class** — all drawing happens in RAM via the C `framebuf`
  module, then `show()` pushes the whole frame in one SPI transfer. Complex animated scenes
  hold ~140+ FPS instead of single digits.
- **Partial updates** — `show_area()`, a `mark_dirty()` / `flush()` dirty-rectangle manager,
  and a static-background cache (`set_background()` / `restore_background()`) for even higher
  effective frame rates.
- **Text at any pixel size** — `text_size(str, x, y, color, height)` with dedicated 5×7 and
  3×6 micro fonts for crisp small text, plus `text_centered`, `text_scaled`, `text_width`.
- **Full Czech diacritics** at every size (á č ď é ě í ň ó ř š ť ú ů ý ž + uppercase),
  drawn procedurally — no extra font tables.
- **Framebuffer memory modes** — pick per project via `create(mode=…)`: full RGB565 (~40 KB,
  default), 8-bit palette (~20 KB), 4-bit palette (~10 KB), or banded/strip rendering (~5 KB) for
  RAM-tight boards like the Pico W. Same drawing API across all of them.
- **Power helpers** — `backlight(0–100)`, `sleep()`, `wake()`.
- **One-line setup** — `st7735.create(...)`.

## Quick start

Copy `st7735.py` to your board, then:

```python
import st7735

# set these to match your wiring
d = st7735.create(spi_id=1, sck=26, mosi=27, dc=22, rst=28, cs=20, bl=21)

d.fb.fill(0)                                   # black background
d.fb.ellipse(64, 80, 26, 26, d.C_GREEN, True)  # filled circle
d.text_size("Hello!", 8, 8, d.C_WHITE, 12)
d.show()                                        # push the frame in ONE SPI transfer
```

Build colors with `d.rgb(r, g, b)` or the `d.C_*` constants — they handle this panel's
BGR + byte-order quirk. With `TFTBuffered`, nothing appears until you call `d.show()`.

## Repository contents

| File | Description |
|------|-------------|
| [`st7735.py`](st7735.py) | The driver (single file — this is all you need on the board). |
| [`DRIVER_GUIDE.md`](DRIVER_GUIDE.md) | In-depth reference: API, performance notes, decision rules. |
| [`examples/hello.py`](examples/hello.py) | Minimal quick start. |
| [`examples/bounce_fps.py`](examples/bounce_fps.py) | Full-frame animation with a live FPS counter. |
| [`examples/text_showcase.py`](examples/text_showcase.py) | Text at many sizes + Czech diacritics. |
| [`examples/low_ram.py`](examples/low_ram.py) | Low-memory framebuffer modes (palette / banded). |

Every example has an editable pin block at the top — set it for your own board.

## License

MIT — see [LICENSE](LICENSE). Original © 2023 Alastair Montgomery; optimizations © 2026 JelenXP.
