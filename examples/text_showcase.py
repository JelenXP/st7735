# -*- coding: utf-8 -*-
# text_showcase.py - text at many pixel sizes, plus full Czech diacritics.
#
# Shows the same string from large to tiny. text_size() automatically switches font:
#   >=8 px  scaled 8x8 font
#    7 px   dedicated 5x7 font
#   <=6 px  dedicated 3x6 micro font
# All sizes render Czech accents (acute / caron / ring / apostrophe) procedurally.
#
# Edit the PINS below, copy st7735.py to the board, and run.

import st7735

# --- your wiring (change these) ---
SPI_ID = 1
SCK, MOSI = 26, 27
DC, RST, CS = 22, 28, 20
BL = 21
# ----------------------------------

d = st7735.create(spi_id=SPI_ID, sck=SCK, mosi=MOSI, dc=DC, rst=RST, cs=CS, bl=BL)
d.fb.fill(0)

s = "aáAÁěĚ"                       # lower/upper + acute + caron
y = 6
for h in (20, 16, 13, 11, 9, 8, 7, 6, 5):
    d.text_size(s, 2, y, d.C_WHITE, h)
    w = d.text_width(s, height=h)
    if 2 + w + 7 < d.width:        # size label on the right where there is room
        d.text_size(str(h), d.width - 6, y, d.C_CYAN, 5)
    y += h + (h // 4 if h // 4 > 3 else 3)

d.show()
print("text sizes 20..5 px shown")
