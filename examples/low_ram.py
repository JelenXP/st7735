# -*- coding: utf-8 -*-
# low_ram.py - the low-memory framebuffer modes (for Pico W / RP2040).
#
# The full RGB565 framebuffer is ~40 KB at 128x160. This shows the two smaller modes:
#   "gs8"    palette, ~20 KB, 256 colors  (drop-in: draw with palette indices)
#   "banded" strip renderer, ~5 KB, full color (draw via a per-band callback)
# See DRIVER_GUIDE.md -> "Framebuffer memory modes" for the full comparison.
#
# Set MODE below, edit the PINS, copy st7735.py to the board, and run.

import st7735

MODE = "gs8"                 # "gs8", "gs4", or "banded"

# --- your wiring (change these) ---
SPI_ID = 1
SCK, MOSI = 26, 27
DC, RST, CS = 22, 28, 20
BL = 21
# ----------------------------------

d = st7735.create(mode=MODE, spi_id=SPI_ID, sck=SCK, mosi=MOSI,
                  dc=DC, rst=RST, cs=CS, bl=BL)
W, H = d.width, d.height

if MODE == "banded":
    # Full color, ~5 KB. Redraw the whole scene per band, offset by y0.
    def draw(fb, y0):
        fb.fill(d.C_BLACK)
        fb.rect(0, 0 - y0, W, H, d.C_WHITE)
        fb.ellipse(W // 2, 80 - y0, 26, 26, d.C_GREEN, True)
        fb.rect(10, 10 - y0, 44, 18, d.rgb(255, 120, 0), True)
        d.text_size("Ahoj (banded)", 8, 40 - y0, d.C_WHITE, 8)
    d.render(draw)
else:
    # Palette modes: colors are indices (P_*). Redefine any with d.set_palette().
    d.fb.fill(d.P_BLACK)
    d.fb.rect(0, 0, W, H, d.P_WHITE)
    d.fb.ellipse(W // 2, 80, 26, 26, d.P_GREEN, True)
    d.fb.rect(10, 10, 44, 18, d.P_ORANGE, True)
    d.text_size("Ahoj (%s)" % MODE, 8, 40, d.P_WHITE, 8)
    d.show()

print("rendered in mode:", MODE)
