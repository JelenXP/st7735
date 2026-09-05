# hello.py - minimal quick start for the optimized ST7735 driver.
# Draws a few shapes and some text, then pushes one frame.
#
# Edit the PINS below to match your wiring, copy st7735.py to the board, and run this.

import st7735

# --- your wiring (change these) ---
SPI_ID = 1
SCK, MOSI = 26, 27
DC, RST, CS = 22, 28, 20
BL = 21                      # backlight pin, or None if you drive it yourself
# ----------------------------------

d = st7735.create(spi_id=SPI_ID, sck=SCK, mosi=MOSI, dc=DC, rst=RST, cs=CS, bl=BL)
#   -> ready TFTBuffered, ~63 MHz SPI, backlight on

d.fb.fill(0)                                      # black background
d.fb.rect(0, 0, d.width, d.height, d.C_WHITE)     # frame
d.fb.line(4, 40, d.width - 5, 120, d.C_RED)
d.fb.ellipse(d.width // 2, 80, 26, 26, d.C_GREEN, True)   # (x, y, xr, yr, color, fill)
d.fb.rect(10, 10, 44, 18, d.rgb(255, 120, 0), True)

d.text_size("Hello, ST7735!", 8, 12, d.C_WHITE, 8)       # any pixel height
d.text_centered("Ahoj, svete!", 132, d.C_CYAN, height=11)  # Czech works too

d.show()                                          # push the whole frame in ONE SPI transfer
print("done")
