# ST7735(S) MicroPython driver - performance-optimized fork for RP2040 / RP2350
#
# Copyright (c) 2023 Alastair Montgomery  (original micropython-st7735)
# Copyright (c) 2026 JelenXP             (optimizations, framebuffer class, fonts)
# Released under the MIT License. See the LICENSE file for the full text.
#
# Lineage: driver for the Sainsmart 1.8" ST7735 TFT, originally translated by
# Guy Carver from the ST7735 sample code, adapted for micropython-esp32 by boochow,
# packaged by Alastair Montgomery, then extended here (see DRIVER_GUIDE.md).

import machine
import time
import framebuf
from math import sqrt


def _clocks_base():
  '''Return the CLOCKS block base address for the current chip (RP2040 vs RP2350),
     or None on an unknown chip. The register map (CLK_PERI_CTRL at offset 0x48,
     AUXSRC[7:5], ENABLE bit 11) is identical on both chips; only the base differs.'''
  import sys
  m = sys.implementation._machine    # e.g. "...Pico 2 W with RP2350" / "...Pico W with RP2040"
  if "RP2350" in m:
    return 0x40010000
  if "RP2040" in m:
    return 0x40008000
  return None


def boost_peri_clock():
  '''RP2040 and RP2350: repoint clk_peri from the 48 MHz USB PLL to the system PLL so
     SPI is not capped at ~20-24 MHz. Safe for the USB-CDC REPL (that runs off the USB
     PLL, not clk_peri). No-op if already switched, or on an unknown chip (keeps the
     default clock source).'''
  from machine import mem32
  base = _clocks_base()
  if base is None:
    return
  CLK_PERI_CTRL = base + 0x48
  ctrl = mem32[CLK_PERI_CTRL]
  if ((ctrl >> 5) & 0x7) == 1:         # AUXSRC already = clksrc_pll_sys
    return
  mem32[CLK_PERI_CTRL] = ctrl & ~(1 << 11)                # disable
  time.sleep_us(20)
  ctrl = (mem32[CLK_PERI_CTRL] & ~(0x7 << 5)) | (1 << 5)  # AUXSRC = clksrc_pll_sys
  mem32[CLK_PERI_CTRL] = ctrl
  mem32[CLK_PERI_CTRL] = ctrl | (1 << 11)                 # enable
  time.sleep_us(20)

# Compact 5x7 font (ASCII 0x20-0x7E) for sharp small text below 8 px.
# 5 bytes per glyph = 5 columns; in each byte bit0 = top row (7 rows).
_FONT5X7 = bytes((
  0x00,0x00,0x00,0x00,0x00, 0x00,0x00,0x5F,0x00,0x00, 0x00,0x07,0x00,0x07,0x00,
  0x14,0x7F,0x14,0x7F,0x14, 0x24,0x2A,0x7F,0x2A,0x12, 0x23,0x13,0x08,0x64,0x62,
  0x36,0x49,0x55,0x22,0x50, 0x00,0x05,0x03,0x00,0x00, 0x00,0x1C,0x22,0x41,0x00,
  0x00,0x41,0x22,0x1C,0x00, 0x14,0x08,0x3E,0x08,0x14, 0x08,0x08,0x3E,0x08,0x08,
  0x00,0x50,0x30,0x00,0x00, 0x08,0x08,0x08,0x08,0x08, 0x00,0x60,0x60,0x00,0x00,
  0x20,0x10,0x08,0x04,0x02, 0x3E,0x51,0x49,0x45,0x3E, 0x00,0x42,0x7F,0x40,0x00,
  0x42,0x61,0x51,0x49,0x46, 0x21,0x41,0x45,0x4B,0x31, 0x18,0x14,0x12,0x7F,0x10,
  0x27,0x45,0x45,0x45,0x39, 0x3C,0x4A,0x49,0x49,0x30, 0x01,0x71,0x09,0x05,0x03,
  0x36,0x49,0x49,0x49,0x36, 0x06,0x49,0x49,0x29,0x1E, 0x00,0x36,0x36,0x00,0x00,
  0x00,0x56,0x36,0x00,0x00, 0x08,0x14,0x22,0x41,0x00, 0x14,0x14,0x14,0x14,0x14,
  0x00,0x41,0x22,0x14,0x08, 0x02,0x01,0x51,0x09,0x06, 0x32,0x49,0x79,0x41,0x3E,
  0x7E,0x11,0x11,0x11,0x7E, 0x7F,0x49,0x49,0x49,0x36, 0x3E,0x41,0x41,0x41,0x22,
  0x7F,0x41,0x41,0x22,0x1C, 0x7F,0x49,0x49,0x49,0x41, 0x7F,0x09,0x09,0x09,0x01,
  0x3E,0x41,0x49,0x49,0x7A, 0x7F,0x08,0x08,0x08,0x7F, 0x00,0x41,0x7F,0x41,0x00,
  0x20,0x40,0x41,0x3F,0x01, 0x7F,0x08,0x14,0x22,0x41, 0x7F,0x40,0x40,0x40,0x40,
  0x7F,0x02,0x0C,0x02,0x7F, 0x7F,0x04,0x08,0x10,0x7F, 0x3E,0x41,0x41,0x41,0x3E,
  0x7F,0x09,0x09,0x09,0x06, 0x3E,0x41,0x51,0x21,0x5E, 0x7F,0x09,0x19,0x29,0x46,
  0x46,0x49,0x49,0x49,0x31, 0x01,0x01,0x7F,0x01,0x01, 0x3F,0x40,0x40,0x40,0x3F,
  0x1F,0x20,0x40,0x20,0x1F, 0x3F,0x40,0x38,0x40,0x3F, 0x63,0x14,0x08,0x14,0x63,
  0x07,0x08,0x70,0x08,0x07, 0x61,0x51,0x49,0x45,0x43, 0x00,0x7F,0x41,0x41,0x00,
  0x02,0x04,0x08,0x10,0x20, 0x00,0x41,0x41,0x7F,0x00, 0x04,0x02,0x01,0x02,0x04,
  0x40,0x40,0x40,0x40,0x40, 0x00,0x01,0x02,0x04,0x00, 0x20,0x54,0x54,0x54,0x78,
  0x7F,0x48,0x44,0x44,0x38, 0x38,0x44,0x44,0x44,0x20, 0x38,0x44,0x44,0x48,0x7F,
  0x38,0x54,0x54,0x54,0x18, 0x08,0x7E,0x09,0x01,0x02, 0x0C,0x52,0x52,0x52,0x3E,
  0x7F,0x08,0x04,0x04,0x78, 0x00,0x44,0x7D,0x40,0x00, 0x20,0x40,0x44,0x3D,0x00,
  0x7F,0x10,0x28,0x44,0x00, 0x00,0x41,0x7F,0x40,0x00, 0x7C,0x04,0x18,0x04,0x78,
  0x7C,0x08,0x04,0x04,0x78, 0x38,0x44,0x44,0x44,0x38, 0x7C,0x14,0x14,0x14,0x08,
  0x08,0x14,0x14,0x18,0x7C, 0x7C,0x08,0x04,0x04,0x08, 0x48,0x54,0x54,0x54,0x20,
  0x04,0x3F,0x44,0x40,0x20, 0x3C,0x40,0x40,0x20,0x7C, 0x1C,0x20,0x40,0x20,0x1C,
  0x3C,0x40,0x30,0x40,0x3C, 0x44,0x28,0x10,0x28,0x44, 0x0C,0x50,0x50,0x50,0x3C,
  0x44,0x64,0x54,0x4C,0x44, 0x00,0x08,0x36,0x41,0x00, 0x00,0x00,0x7F,0x00,0x00,
  0x00,0x41,0x36,0x08,0x00, 0x08,0x04,0x08,0x10,0x08,
))

# Micro 3x6 font (Tom-Thumb style) for sizes <=6 px, where downscaling the 5x7 font
# falls apart. 3 bytes/glyph = 3 columns, bit0 = top row (6 rows). ASCII 0x20-0x7E.
# The main body is in rows 0-4, descenders (g j p q y) in row 5 -> 5px = clean top 3x5.
_FONT3X6 = bytes((
  0x00,0x00,0x00,0x00,0x17,0x00,0x03,0x00,0x03,0x1F,0x0A,0x1F,0x0A,0x1F,0x05,
  0x19,0x04,0x13,0x0A,0x15,0x1A,0x00,0x03,0x00,0x00,0x0E,0x11,0x11,0x0E,0x00,
  0x15,0x0E,0x15,0x04,0x0E,0x04,0x20,0x10,0x00,0x04,0x04,0x04,0x00,0x10,0x00,
  0x18,0x04,0x03,0x0E,0x11,0x0E,0x12,0x1F,0x10,0x19,0x15,0x12,0x11,0x15,0x0E,
  0x07,0x04,0x1F,0x17,0x15,0x09,0x0E,0x15,0x08,0x01,0x1D,0x03,0x0A,0x15,0x0A,
  0x02,0x15,0x0E,0x00,0x0A,0x00,0x20,0x12,0x00,0x04,0x0A,0x11,0x0A,0x0A,0x0A,
  0x11,0x0A,0x04,0x01,0x15,0x02,0x0E,0x15,0x16,0x1E,0x05,0x1E,0x1F,0x15,0x0A,
  0x0E,0x11,0x11,0x1F,0x11,0x0E,0x1F,0x15,0x11,0x1F,0x05,0x01,0x0E,0x11,0x1D,
  0x1F,0x04,0x1F,0x11,0x1F,0x11,0x08,0x10,0x0F,0x1F,0x04,0x1B,0x1F,0x10,0x10,
  0x1F,0x06,0x1F,0x17,0x0E,0x1D,0x0E,0x11,0x0E,0x1F,0x05,0x02,0x06,0x09,0x16,
  0x1F,0x05,0x1A,0x12,0x15,0x09,0x01,0x1F,0x01,0x0F,0x10,0x0F,0x07,0x18,0x07,
  0x1F,0x0C,0x1F,0x1B,0x04,0x1B,0x03,0x1C,0x03,0x19,0x15,0x13,0x1F,0x11,0x11,
  0x03,0x04,0x18,0x11,0x11,0x1F,0x02,0x01,0x02,0x10,0x10,0x10,0x01,0x02,0x00,
  0x0C,0x12,0x1E,0x1F,0x14,0x08,0x0C,0x12,0x12,0x08,0x14,0x1F,0x0C,0x16,0x14,
  0x04,0x1F,0x05,0x24,0x2A,0x1E,0x1F,0x04,0x18,0x00,0x1D,0x00,0x10,0x20,0x1D,
  0x1F,0x04,0x1A,0x11,0x1F,0x10,0x1E,0x0C,0x1E,0x1E,0x02,0x1C,0x0C,0x12,0x0C,
  0x3E,0x0A,0x04,0x04,0x0A,0x3E,0x1C,0x02,0x02,0x14,0x16,0x0A,0x02,0x0F,0x12,
  0x0E,0x10,0x1E,0x06,0x18,0x06,0x1E,0x0C,0x1E,0x12,0x0C,0x12,0x26,0x28,0x1E,
  0x1A,0x16,0x12,0x04,0x0E,0x11,0x00,0x1F,0x00,0x11,0x0E,0x04,0x04,0x02,0x04,
))


# Czech diacritics: char -> (base ASCII letter, accent type).
# 1 = acute (carka /), 2 = caron (hacek v), 3 = ring (krouzek o),
# 4 = apostrophe to the right of the letter (lowercase d - the tall stem is on the right),
# 5 = apostrophe into the top-right corner of the letter (lowercase t - empty there).
# The accent is drawn above the base glyph and works at every size.
_CZ = {
  "á": ("a", 1), "é": ("e", 1), "í": ("i", 1), "ó": ("o", 1),
  "ú": ("u", 1), "ý": ("y", 1),
  "Á": ("A", 1), "É": ("E", 1), "Í": ("I", 1), "Ó": ("O", 1),
  "Ú": ("U", 1), "Ý": ("Y", 1),
  "č": ("c", 2), "ě": ("e", 2), "ň": ("n", 2),
  "ř": ("r", 2), "š": ("s", 2), "ž": ("z", 2),
  "Č": ("C", 2), "Ě": ("E", 2), "Ň": ("N", 2),
  "Ř": ("R", 2), "Š": ("S", 2), "Ž": ("Z", 2),
  "ď": ("d", 4), "ť": ("t", 5), "Ď": ("D", 2), "Ť": ("T", 2),
  "ů": ("u", 3), "Ů": ("U", 3),
}


#TFTRotations and TFTRGB are bits to set
# on MADCTL to control display rotation/color layout
#Looking at display with pins on top.
#00 = upper left printing right
#10 = does nothing (MADCTL_ML)
#20 = upper left printing down (backwards) (Vertical flip)
#40 = upper right printing left (backwards) (X Flip)
#80 = lower left printing right (backwards) (Y Flip)
#04 = (MADCTL_MH)

#60 = 90 right rotation
#C0 = 180 right rotation
#A0 = 270 right rotation
TFTRotations = [0x00, 0x60, 0xC0, 0xA0]
TFTBGR = 0x08 #When set color is bgr else rgb.
TFTRGB = 0x00

#@micropython.native
def clamp( aValue, aMin, aMax ) :
  return max(aMin, min(aMax, aValue))

#@micropython.native
def TFTColor( aR, aG, aB ) :
  '''Create a 16 bit rgb value from the given R,G,B from 0-255.
     This assumes rgb 565 layout and will be incorrect for bgr.'''
  return ((aR & 0xF8) << 8) | ((aG & 0xFC) << 3) | (aB >> 3)



class TFT(object) :
  """Sainsmart TFT 7735 display driver."""

  NOP = 0x0
  SWRESET = 0x01
  RDDID = 0x04
  RDDST = 0x09

  SLPIN  = 0x10
  SLPOUT  = 0x11
  PTLON  = 0x12
  NORON  = 0x13

  INVOFF = 0x20
  INVON = 0x21
  DISPOFF = 0x28
  DISPON = 0x29
  CASET = 0x2A
  RASET = 0x2B
  RAMWR = 0x2C
  RAMRD = 0x2E

  VSCRDEF = 0x33
  VSCSAD = 0x37

  COLMOD = 0x3A
  MADCTL = 0x36

  FRMCTR1 = 0xB1
  FRMCTR2 = 0xB2
  FRMCTR3 = 0xB3
  INVCTR = 0xB4
  DISSET5 = 0xB6

  PWCTR1 = 0xC0
  PWCTR2 = 0xC1
  PWCTR3 = 0xC2
  PWCTR4 = 0xC3
  PWCTR5 = 0xC4
  VMCTR1 = 0xC5

  RDID1 = 0xDA
  RDID2 = 0xDB
  RDID3 = 0xDC
  RDID4 = 0xDD

  PWCTR6 = 0xFC

  GMCTRP1 = 0xE0
  GMCTRN1 = 0xE1

  BLACK = 0
  RED = TFTColor(0xFF, 0x00, 0x00)
  MAROON = TFTColor(0x80, 0x00, 0x00)
  GREEN = TFTColor(0x00, 0xFF, 0x00)
  FOREST = TFTColor(0x00, 0x80, 0x80)
  BLUE = TFTColor(0x00, 0x00, 0xFF)
  NAVY = TFTColor(0x00, 0x00, 0x80)
  CYAN = TFTColor(0x00, 0xFF, 0xFF)
  YELLOW = TFTColor(0xFF, 0xFF, 0x00)
  PURPLE = TFTColor(0xFF, 0x00, 0xFF)
  WHITE = TFTColor(0xFF, 0xFF, 0xFF)
  GRAY = TFTColor(0x80, 0x80, 0x80)

  @staticmethod
  def color( aR, aG, aB ) :
    '''Create a 565 rgb TFTColor value'''
    return TFTColor(aR, aG, aB)

  def __init__( self, spi, aDC, aReset, aCS, ScreenSize = (128, 160)) :
    """aLoc SPI pin location is either 1 for 'X' or 2 for 'Y'.
       aDC is the DC pin and aReset is the reset pin."""
    self._size = ScreenSize
    self._offset = bytearray([0,0])
    self.rotate = 0                    #Vertical with top toward pins.
    self._rgb = True                   #color order of rgb.
    self.tfa = 0                       #top fixed area
    self.bfa = 0                       #bottom fixed area
    self.dc  = machine.Pin(aDC, machine.Pin.OUT, machine.Pin.PULL_DOWN)
    self.reset = machine.Pin(aReset, machine.Pin.OUT, machine.Pin.PULL_DOWN)
    self.cs = machine.Pin(aCS, machine.Pin.OUT, machine.Pin.PULL_DOWN)
    self.cs(1)
    self.spi = spi
    self.colorData = bytearray(2)
    self.windowLocData = bytearray(4)
    self.buf = b''
    self._fillcache = {}     #color -> 8KB pattern buffer (avoids rebuilding each fill)
    self._fillwin = None     #last full-screen window set (skip CASET/RASET on repeated fills)
    self._bl_pin = None      #backlight pin number (for backlight()/sleep())
    self._bl_pwm = None      #lazy PWM object for brightness control
    self._bl_level = 100     #last brightness set, 0-100

  def size( self ) :
    return self._size

#   @micropython.native
  def on( self, aTF = True ) :
    '''Turn display on or off.'''
    self._writecommand(TFT.DISPON if aTF else TFT.DISPOFF)

#   @micropython.native
  def invertcolor( self, aBool ) :
    '''Invert the color data IE: Black = White.'''
    self._writecommand(TFT.INVON if aBool else TFT.INVOFF)

#   @micropython.native
  def rgb( self, aTF = True ) :
    '''True = rgb else bgr'''
    self._rgb = aTF
    self._setMADCTL()

#   @micropython.native
  def rotation( self, aRot ) :
    '''0 - 3. Starts vertical with top toward pins and rotates 90 deg
       clockwise each step.'''
    if (0 <= aRot < 4):
      rotchange = self.rotate ^ aRot
      self.rotate = aRot
      #If switching from vertical to horizontal swap x,y
      # (indicated by bit 0 changing).
      if (rotchange & 1):
        self._size =(self._size[1], self._size[0])
      self._setMADCTL()

#  @micropython.native
  def pixel( self, aPos, aColor ) :
    '''Draw a pixel at the given position'''
    if 0 <= aPos[0] < self._size[0] and 0 <= aPos[1] < self._size[1]:
      self._setwindowpoint(aPos)
      self._pushcolor(aColor)

#   @micropython.native
  def text( self, aPos, aString, aColor, aFont, aSize = 1, nowrap = False ) :
    '''Draw a text at the given position.  If the string reaches the end of the
       display it is wrapped to aPos[0] on the next line.  aSize may be an integer
       which will size the font uniformly on w,h or a or any type that may be
       indexed with [0] or [1].'''

    if aFont == None:
      return

    #Make a size either from single value or 2 elements.
    if (type(aSize) == int) or (type(aSize) == float):
      wh = (aSize, aSize)
    else:
      wh = aSize

    px, py = aPos
    width = wh[0] * aFont["Width"] + 1
    for c in aString:
      self.char((px, py), c, aColor, aFont, wh)
      px += width
      #We check > rather than >= to let the right (blank) edge of the
      # character print off the right of the screen.
      if px + width > self._size[0]:
        if nowrap:
          break
        else:
          py += aFont["Height"] * wh[1] + 1
          px = aPos[0]

#   @micropython.native
  def char( self, aPos, aChar, aColor, aFont, aSizes ) :
    '''Draw a character at the given position using the given font and color.
       aSizes is a tuple with x, y as integer scales indicating the
       # of pixels to draw for each pixel in the character.'''

    if aFont == None:
      return

    startchar = aFont['Start']
    endchar = aFont['End']

    ci = ord(aChar)
    if (startchar <= ci <= endchar):
      fontw = aFont['Width']
      fonth = aFont['Height']
      ci = (ci - startchar) * fontw

      charA = aFont["Data"][ci:ci + fontw]
      px = aPos[0]
      for c in charA :
        py = aPos[1]
        for r in range(fonth) :
          if c & 0x01 :
            self.fillrect((px, py), aSizes, aColor)
          py += aSizes[1]
          c >>= 1
        px += aSizes[0]

#   @micropython.native
  def line( self, aStart, aEnd, aColor ) :
    '''Draws a line from aStart to aEnd in the given color.  Vertical or horizontal
       lines are forwarded to vline and hline.'''
    if aStart[0] == aEnd[0]:
      #Make sure we use the smallest y.
      pnt = aEnd if (aEnd[1] < aStart[1]) else aStart
      self.vline(pnt, abs(aEnd[1] - aStart[1]) + 1, aColor)
    elif aStart[1] == aEnd[1]:
      #Make sure we use the smallest x.
      pnt = aEnd if aEnd[0] < aStart[0] else aStart
      self.hline(pnt, abs(aEnd[0] - aStart[0]) + 1, aColor)
    else:
      px, py = aStart
      ex, ey = aEnd
      dx = ex - px
      dy = ey - py
      inx = 1 if dx > 0 else -1
      iny = 1 if dy > 0 else -1

      dx = abs(dx)
      dy = abs(dy)
      if (dx >= dy):
        dy <<= 1
        e = dy - dx
        dx <<= 1
        while (px != ex):
          self.pixel((px, py), aColor)
          if (e >= 0):
            py += iny
            e -= dx
          e += dy
          px += inx
      else:
        dx <<= 1
        e = dx - dy
        dy <<= 1
        while (py != ey):
          self.pixel((px, py), aColor)
          if (e >= 0):
            px += inx
            e -= dy
          e += dx
          py += iny

#   @micropython.native
  def vline( self, aStart, aLen, aColor ) :
    '''Draw a vertical line from aStart for aLen. aLen may be negative.'''
    start = (clamp(aStart[0], 0, self._size[0]), clamp(aStart[1], 0, self._size[1]))
    stop = (start[0], clamp(start[1] + aLen, 0, self._size[1]))
    #Make sure smallest y 1st.
    if (stop[1] < start[1]):
      start, stop = stop, start
    self._setwindowloc(start, stop)
    self._setColor(aColor)
    self._draw(aLen)

#   @micropython.native
  def hline( self, aStart, aLen, aColor ) :
    '''Draw a horizontal line from aStart for aLen. aLen may be negative.'''
    start = (clamp(aStart[0], 0, self._size[0]), clamp(aStart[1], 0, self._size[1]))
    stop = (clamp(start[0] + aLen, 0, self._size[0]), start[1])
    #Make sure smallest x 1st.
    if (stop[0] < start[0]):
      start, stop = stop, start
    self._setwindowloc(start, stop)
    self._setColor(aColor)
    self._draw(aLen)

#   @micropython.native
  def rect( self, aStart, aSize, aColor ) :
    '''Draw a hollow rectangle.  aStart is the smallest coordinate corner
       and aSize is a tuple indicating width, height.'''
    self.hline(aStart, aSize[0], aColor)
    self.hline((aStart[0], aStart[1] + aSize[1] - 1), aSize[0], aColor)
    self.vline(aStart, aSize[1], aColor)
    self.vline((aStart[0] + aSize[0] - 1, aStart[1]), aSize[1], aColor)

#   @micropython.native
  def fillrect( self, aStart, aSize, aColor ) :
    '''Draw a filled rectangle.  aStart is the smallest coordinate corner
       and aSize is a tuple indicating width, height.'''
    start = (clamp(aStart[0], 0, self._size[0]), clamp(aStart[1], 0, self._size[1]))
    end = (clamp(start[0] + aSize[0] - 1, 0, self._size[0]), clamp(start[1] + aSize[1] - 1, 0, self._size[1]))

    if (end[0] < start[0]):
      tmp = end[0]
      end = (start[0], end[1])
      start = (tmp, start[1])
    if (end[1] < start[1]):
      tmp = end[1]
      end = (end[0], start[1])
      start = (start[0], tmp)

    self._setwindowloc(start, end)
    numPixels = (end[0] - start[0] + 1) * (end[1] - start[1] + 1)
    self._setColor(aColor)
    self._draw(numPixels)

#   @micropython.native
  def circle( self, aPos, aRadius, aColor ) :
    '''Draw a hollow circle with the given radius and color with aPos as center.'''
    self.colorData[0] = aColor >> 8
    self.colorData[1] = aColor
    xend = int(0.7071 * aRadius) + 1
    rsq = aRadius * aRadius
    for x in range(xend) :
      y = int(sqrt(rsq - x * x))
      xp = aPos[0] + x
      yp = aPos[1] + y
      xn = aPos[0] - x
      yn = aPos[1] - y
      xyp = aPos[0] + y
      yxp = aPos[1] + x
      xyn = aPos[0] - y
      yxn = aPos[1] - x

      self._setwindowpoint((xp, yp))
      self._writedata(self.colorData)
      self._setwindowpoint((xp, yn))
      self._writedata(self.colorData)
      self._setwindowpoint((xn, yp))
      self._writedata(self.colorData)
      self._setwindowpoint((xn, yn))
      self._writedata(self.colorData)
      self._setwindowpoint((xyp, yxp))
      self._writedata(self.colorData)
      self._setwindowpoint((xyp, yxn))
      self._writedata(self.colorData)
      self._setwindowpoint((xyn, yxp))
      self._writedata(self.colorData)
      self._setwindowpoint((xyn, yxn))
      self._writedata(self.colorData)

#   @micropython.native
  def fillcircle( self, aPos, aRadius, aColor ) :
    '''Draw a filled circle with given radius and color with aPos as center'''
    rsq = aRadius * aRadius
    for x in range(aRadius) :
      y = int(sqrt(rsq - x * x))
      y0 = aPos[1] - y
      ey = y0 + y * 2
      y0 = clamp(y0, 0, self._size[1])
      ln = abs(ey - y0) + 1;

      self.vline((aPos[0] + x, y0), ln, aColor)
      self.vline((aPos[0] - x, y0), ln, aColor)

  def fill( self, aColor = BLACK ) :
    '''Fill screen with the given color. Fast path: the window is set only once
       (repeated fills send RAMWR only), and the pattern buffer comes from the cache.'''
    w = self._size[0]
    h = self._size[1]
    if self._fillwin != self._size:
      self._setwindowloc((0, 0), (w - 1, h - 1))   #set window + RAMWR
      self._fillwin = self._size
    else:
      self._writecommand(TFT.RAMWR)                #just restart the RAM pointer

    self._setColor(aColor)
    buf = self.buf
    spi = self.spi
    n = w * h

    self.dc(1)
    self.cs(0)
    for _ in range(n >> 12):        # n // 4096 full blocks
      spi.write(buf)
    rest = n & 0xFFF               # n % 4096
    if rest:
      spi.write(bytes(self.colorData) * rest)
    self.cs(1)

  def image( self, x0, y0, x1, y1, data ) :
    self._setwindowloc((x0, y0), (x1, y1))
    self._writedata(data)

  # ---- Power / backlight (convenience helpers) ----

  def attach_backlight( self, aPin ) :
    '''Register the backlight pin so backlight()/sleep()/wake() work.
       (create() does this automatically.)'''
    self._bl_pin = aPin

  def backlight( self, aLevel = 100 ) :
    '''Set backlight brightness 0-100 %% via PWM. 0 = off, 100 = full brightness.'''
    if self._bl_pin is None:
      return
    aLevel = 0 if aLevel < 0 else (100 if aLevel > 100 else aLevel)
    self._bl_level = aLevel
    if aLevel == 100 and self._bl_pwm is None:
      machine.Pin(self._bl_pin, machine.Pin.OUT).value(1)   #just drive it high
    if self._bl_pwm is None:
      self._bl_pwm = machine.PWM(machine.Pin(self._bl_pin))
      self._bl_pwm.freq(1000)
    self._bl_pwm.duty_u16(aLevel * 65535 // 100)

  def sleep( self ) :
    '''Put the panel to sleep (SLPIN) + turn the backlight off. Low power.'''
    if self._bl_pin is not None:
      if self._bl_pwm is not None:
        self._bl_pwm.duty_u16(0)
      else:
        machine.Pin(self._bl_pin, machine.Pin.OUT).value(0)
    self._writecommand(TFT.DISPOFF)
    self._writecommand(TFT.SLPIN)
    time.sleep_ms(120)

  def wake( self ) :
    '''Wake the panel (SLPOUT) + restore the backlight to the last brightness.'''
    self._writecommand(TFT.SLPOUT)
    time.sleep_ms(120)
    self._writecommand(TFT.DISPON)
    if self._bl_pin is not None:
      self.backlight(self._bl_level)

  def setvscroll(self, tfa, bfa) :
    ''' set vertical scroll area '''
    self._writecommand(TFT.VSCRDEF)
    data2 = bytearray([0, tfa])
    self._writedata(data2)
    data2[1] = 162 - tfa - bfa
    self._writedata(data2)
    data2[1] = bfa
    self._writedata(data2)
    self.tfa = tfa
    self.bfa = bfa

  def vscroll(self, value) :
    a = value + self.tfa
    if (a + self.bfa > 162) :
      a = 162 - self.bfa
    self._vscrolladdr(a)

  def _vscrolladdr(self, addr) :
    self._writecommand(TFT.VSCSAD)
    data2 = bytearray([addr >> 8, addr & 0xff])
    self._writedata(data2)
    
#   @micropython.native
  def _setColor(self, aColor):
    self.colorData[0] = aColor >> 8
    self.colorData[1] = aColor & 0xFF

    # 4096 pixels x 2 bytes = 8192 bytes.
    # The buffer is rebuilt only when the color changes (build costs ~2 ms),
    # otherwise it comes from the cache -> no per-frame overhead.
    buf = self._fillcache.get(aColor)
    if buf is None:
      if len(self._fillcache) > 32:
        self._fillcache.clear()
      buf = bytes(self.colorData) * 4096
      self._fillcache[aColor] = buf
    self.buf = buf

  def _draw(self, aPixels):
    '''Send given color to the device aPixels times.'''

    self.dc(1)
    self.cs(0)

    # Send pixels in large blocks instead of 32 at a time.
    full_chunks = aPixels // 4096

    for i in range(full_chunks):
      self.spi.write(self.buf)

    rest = aPixels % 4096

    if rest > 0:
      self.spi.write(
        bytes(self.colorData) * rest
      )

    self.cs(1)

#   @micropython.native
  def _setwindowpoint( self, aPos ) :
    '''Set a single point for drawing a color to.'''
    self._fillwin = None
    x = self._offset[0] + int(aPos[0])
    y = self._offset[1] + int(aPos[1])
    self._writecommand(TFT.CASET)            #Column address set.
    self.windowLocData[0] = self._offset[0]
    self.windowLocData[1] = x
    self.windowLocData[2] = self._offset[0]
    self.windowLocData[3] = x
    self._writedata(self.windowLocData)

    self._writecommand(TFT.RASET)            #Row address set.
    self.windowLocData[0] = self._offset[1]
    self.windowLocData[1] = y
    self.windowLocData[2] = self._offset[1]
    self.windowLocData[3] = y
    self._writedata(self.windowLocData)
    self._writecommand(TFT.RAMWR)            #Write to RAM.

#   @micropython.native
  def _setwindowloc( self, aPos0, aPos1 ) :
    '''Set a rectangular area for drawing a color to.'''
    self._fillwin = None
    self._writecommand(TFT.CASET)            #Column address set.
    self.windowLocData[0] = self._offset[0]
    self.windowLocData[1] = self._offset[0] + int(aPos0[0])
    self.windowLocData[2] = self._offset[0]
    self.windowLocData[3] = self._offset[0] + int(aPos1[0])
    self._writedata(self.windowLocData)

    self._writecommand(TFT.RASET)            #Row address set.
    self.windowLocData[0] = self._offset[1]
    self.windowLocData[1] = self._offset[1] + int(aPos0[1])
    self.windowLocData[2] = self._offset[1]
    self.windowLocData[3] = self._offset[1] + int(aPos1[1])
    self._writedata(self.windowLocData)

    self._writecommand(TFT.RAMWR)            #Write to RAM.

  #@micropython.native
  def _writecommand( self, aCommand ) :
    '''Write given command to the device.'''
    self.dc(0)
    self.cs(0)
    self.spi.write(bytearray([aCommand]))
    self.cs(1)

  #@micropython.native
  def _writedata( self, aData ) :
    '''Write given data to the device.  This may be
       either a single int or a bytearray of values.'''
    self.dc(1)
    self.cs(0)
    self.spi.write(aData)
    self.cs(1)

  #@micropython.native
  def _pushcolor( self, aColor ) :
    '''Push given color to the device.'''
    self.colorData[0] = aColor >> 8
    self.colorData[1] = aColor
    self._writedata(self.colorData)

  #@micropython.native
  def _setMADCTL( self ) :
    '''Set screen rotation and RGB/BGR format.'''
    self._writecommand(TFT.MADCTL)
    rgb = TFTRGB if self._rgb else TFTBGR
    self._writedata(bytearray([TFTRotations[self.rotate] | rgb]))

  #@micropython.native
  def _reset( self ) :
    '''Reset the device.'''
    self.dc(0)
    self.reset(1)
    time.sleep_us(500)
    self.reset(0)
    time.sleep_us(500)
    self.reset(1)
    time.sleep_us(500)

  def initb( self, ScreenSize = (128, 160) ) :
    '''Initialize blue tab version.'''
    self._size = (ScreenSize[0] + 2, ScreenSize[1] + 1)
    self._reset()
    self._writecommand(TFT.SWRESET)              #Software reset.
    time.sleep_us(50)
    self._writecommand(TFT.SLPOUT)               #out of sleep mode.
    time.sleep_us(500)

    data1 = bytearray(1)
    self._writecommand(TFT.COLMOD)               #Set color mode.
    data1[0] = 0x05                             #16 bit color.
    self._writedata(data1)
    time.sleep_us(10)

    data3 = bytearray([0x00, 0x06, 0x03])       #fastest refresh, 6 lines front, 3 lines back.
    self._writecommand(TFT.FRMCTR1)              #Frame rate control.
    self._writedata(data3)
    time.sleep_us(10)

    self._writecommand(TFT.MADCTL)
    data1[0] = 0x08                             #row address/col address, bottom to top refresh
    self._writedata(data1)

    data2 = bytearray(2)
    self._writecommand(TFT.DISSET5)              #Display settings
    data2[0] = 0x15                             #1 clock cycle nonoverlap, 2 cycle gate rise, 3 cycle oscil, equalize
    data2[1] = 0x02                             #fix on VTL
    self._writedata(data2)

    self._writecommand(TFT.INVCTR)               #Display inversion control
    data1[0] = 0x00                             #Line inversion.
    self._writedata(data1)

    self._writecommand(TFT.PWCTR1)               #Power control
    data2[0] = 0x02   #GVDD = 4.7V
    data2[1] = 0x70   #1.0uA
    self._writedata(data2)
    time.sleep_us(10)

    self._writecommand(TFT.PWCTR2)               #Power control
    data1[0] = 0x05                             #VGH = 14.7V, VGL = -7.35V
    self._writedata(data1)

    self._writecommand(TFT.PWCTR3)           #Power control
    data2[0] = 0x01   #Opamp current small
    data2[1] = 0x02   #Boost frequency
    self._writedata(data2)

    self._writecommand(TFT.VMCTR1)               #Power control
    data2[0] = 0x3C   #VCOMH = 4V
    data2[1] = 0x38   #VCOML = -1.1V
    self._writedata(data2)
    time.sleep_us(10)

    self._writecommand(TFT.PWCTR6)               #Power control
    data2[0] = 0x11
    data2[1] = 0x15
    self._writedata(data2)

    #These different values don't seem to make a difference.
#     dataGMCTRP = bytearray([0x0f, 0x1a, 0x0f, 0x18, 0x2f, 0x28, 0x20, 0x22, 0x1f,
#                             0x1b, 0x23, 0x37, 0x00, 0x07, 0x02, 0x10])
    dataGMCTRP = bytearray([0x02, 0x1c, 0x07, 0x12, 0x37, 0x32, 0x29, 0x2d, 0x29,
                            0x25, 0x2b, 0x39, 0x00, 0x01, 0x03, 0x10])
    self._writecommand(TFT.GMCTRP1)
    self._writedata(dataGMCTRP)

#     dataGMCTRN = bytearray([0x0f, 0x1b, 0x0f, 0x17, 0x33, 0x2c, 0x29, 0x2e, 0x30,
#                             0x30, 0x39, 0x3f, 0x00, 0x07, 0x03, 0x10])
    dataGMCTRN = bytearray([0x03, 0x1d, 0x07, 0x06, 0x2e, 0x2c, 0x29, 0x2d, 0x2e,
                            0x2e, 0x37, 0x3f, 0x00, 0x00, 0x02, 0x10])
    self._writecommand(TFT.GMCTRN1)
    self._writedata(dataGMCTRN)
    time.sleep_us(10)

    self._writecommand(TFT.CASET)                #Column address set.
    self.windowLocData[0] = 0x00
    self.windowLocData[1] = 2                   #Start at column 2
    self.windowLocData[2] = 0x00
    self.windowLocData[3] = self._size[0] - 1
    self._writedata(self.windowLocData)

    self._writecommand(TFT.RASET)                #Row address set.
    self.windowLocData[1] = 1                   #Start at row 2.
    self.windowLocData[3] = self._size[1] - 1
    self._writedata(self.windowLocData)

    self._writecommand(TFT.NORON)                #Normal display on.
    time.sleep_us(10)

    self._writecommand(TFT.RAMWR)
    time.sleep_us(500)

    self._writecommand(TFT.DISPON)
    self.cs(1)
    time.sleep_us(500)

  def initr( self ) :
    '''Initialize a red tab version.'''
    boost_peri_clock()   #unlock the SPI clock from the 48 MHz USB PLL to the system PLL
    self._reset()

    self._writecommand(TFT.SWRESET)              #Software reset.
    time.sleep_us(150)
    self._writecommand(TFT.SLPOUT)               #out of sleep mode.
    time.sleep_us(500)

    data3 = bytearray([0x01, 0x2C, 0x2D])       #fastest refresh, 6 lines front, 3 lines back.
    self._writecommand(TFT.FRMCTR1)              #Frame rate control.
    self._writedata(data3)

    self._writecommand(TFT.FRMCTR2)              #Frame rate control.
    self._writedata(data3)

    data6 = bytearray([0x01, 0x2c, 0x2d, 0x01, 0x2c, 0x2d])
    self._writecommand(TFT.FRMCTR3)              #Frame rate control.
    self._writedata(data6)
    time.sleep_us(10)

    data1 = bytearray(1)
    self._writecommand(TFT.INVCTR)               #Display inversion control
    data1[0] = 0x07                             #Line inversion.
    self._writedata(data1)

    self._writecommand(TFT.PWCTR1)               #Power control
    data3[0] = 0xA2
    data3[1] = 0x02
    data3[2] = 0x84
    self._writedata(data3)

    self._writecommand(TFT.PWCTR2)               #Power control
    data1[0] = 0xC5   #VGH = 14.7V, VGL = -7.35V
    self._writedata(data1)

    data2 = bytearray(2)
    self._writecommand(TFT.PWCTR3)               #Power control
    data2[0] = 0x0A   #Opamp current small
    data2[1] = 0x00   #Boost frequency
    self._writedata(data2)

    self._writecommand(TFT.PWCTR4)               #Power control
    data2[0] = 0x8A   #Opamp current small
    data2[1] = 0x2A   #Boost frequency
    self._writedata(data2)

    self._writecommand(TFT.PWCTR5)               #Power control
    data2[0] = 0x8A   #Opamp current small
    data2[1] = 0xEE   #Boost frequency
    self._writedata(data2)

    self._writecommand(TFT.VMCTR1)               #Power control
    data1[0] = 0x0E
    self._writedata(data1)

    self._writecommand(TFT.INVOFF)

    self._writecommand(TFT.MADCTL)               #Power control
    data1[0] = 0xC8
    self._writedata(data1)

    self._writecommand(TFT.COLMOD)
    data1[0] = 0x05
    self._writedata(data1)

    self._writecommand(TFT.CASET)                #Column address set.
    self.windowLocData[0] = 0x00
    self.windowLocData[1] = 0x00
    self.windowLocData[2] = 0x00
    self.windowLocData[3] = self._size[0] - 1
    self._writedata(self.windowLocData)

    self._writecommand(TFT.RASET)                #Row address set.
    self.windowLocData[3] = self._size[1] - 1
    self._writedata(self.windowLocData)

    dataGMCTRP = bytearray([0x0f, 0x1a, 0x0f, 0x18, 0x2f, 0x28, 0x20, 0x22, 0x1f,
                            0x1b, 0x23, 0x37, 0x00, 0x07, 0x02, 0x10])
    self._writecommand(TFT.GMCTRP1)
    self._writedata(dataGMCTRP)

    dataGMCTRN = bytearray([0x0f, 0x1b, 0x0f, 0x17, 0x33, 0x2c, 0x29, 0x2e, 0x30,
                            0x30, 0x39, 0x3f, 0x00, 0x07, 0x03, 0x10])
    self._writecommand(TFT.GMCTRN1)
    self._writedata(dataGMCTRN)
    time.sleep_us(10)

    self._writecommand(TFT.DISPON)
    time.sleep_us(100)

    self._writecommand(TFT.NORON)                #Normal display on.
    time.sleep_us(10)

    self.cs(1)
    
  def initb2( self, ScreenSize = (128, 160) ) :
    '''Initialize another blue tab version.'''
    self._size = (ScreenSize[0] + 2, ScreenSize[1] + 1)
    self._offset[0] = 2
    self._offset[1] = 1
    self._reset()
    self._writecommand(TFT.SWRESET)              #Software reset.
    time.sleep_us(50)
    self._writecommand(TFT.SLPOUT)               #out of sleep mode.
    time.sleep_us(500)

    data3 = bytearray([0x01, 0x2C, 0x2D])        #
    self._writecommand(TFT.FRMCTR1)              #Frame rate control.
    self._writedata(data3)
    time.sleep_us(10)

    self._writecommand(TFT.FRMCTR2)              #Frame rate control.
    self._writedata(data3)
    time.sleep_us(10)

    self._writecommand(TFT.FRMCTR3)              #Frame rate control.
    self._writedata(data3)
    time.sleep_us(10)

    self._writecommand(TFT.INVCTR)               #Display inversion control
    data1 = bytearray(1)                         #
    data1[0] = 0x07
    self._writedata(data1)

    self._writecommand(TFT.PWCTR1)               #Power control
    data3[0] = 0xA2   #
    data3[1] = 0x02   #
    data3[2] = 0x84   #
    self._writedata(data3)
    time.sleep_us(10)

    self._writecommand(TFT.PWCTR2)               #Power control
    data1[0] = 0xC5                              #
    self._writedata(data1)

    self._writecommand(TFT.PWCTR3)           #Power control
    data2 = bytearray(2)
    data2[0] = 0x0A   #
    data2[1] = 0x00   #
    self._writedata(data2)

    self._writecommand(TFT.PWCTR4)           #Power control
    data2[0] = 0x8A   #
    data2[1] = 0x2A   #
    self._writedata(data2)

    self._writecommand(TFT.PWCTR5)           #Power control
    data2[0] = 0x8A   #
    data2[1] = 0xEE   #
    self._writedata(data2)

    self._writecommand(TFT.VMCTR1)               #Power control
    data1[0] = 0x0E   #
    self._writedata(data1)
    time.sleep_us(10)

    self._writecommand(TFT.MADCTL)
    data1[0] = 0xC8                             #row address/col address, bottom to top refresh
    self._writedata(data1)

#These different values don't seem to make a difference.
#     dataGMCTRP = bytearray([0x0f, 0x1a, 0x0f, 0x18, 0x2f, 0x28, 0x20, 0x22, 0x1f,
#                             0x1b, 0x23, 0x37, 0x00, 0x07, 0x02, 0x10])
    dataGMCTRP = bytearray([0x02, 0x1c, 0x07, 0x12, 0x37, 0x32, 0x29, 0x2d, 0x29,
                            0x25, 0x2b, 0x39, 0x00, 0x01, 0x03, 0x10])
    self._writecommand(TFT.GMCTRP1)
    self._writedata(dataGMCTRP)

#     dataGMCTRN = bytearray([0x0f, 0x1b, 0x0f, 0x17, 0x33, 0x2c, 0x29, 0x2e, 0x30,
#                             0x30, 0x39, 0x3f, 0x00, 0x07, 0x03, 0x10])
    dataGMCTRN = bytearray([0x03, 0x1d, 0x07, 0x06, 0x2e, 0x2c, 0x29, 0x2d, 0x2e,
                            0x2e, 0x37, 0x3f, 0x00, 0x00, 0x02, 0x10])
    self._writecommand(TFT.GMCTRN1)
    self._writedata(dataGMCTRN)
    time.sleep_us(10)

    self._writecommand(TFT.CASET)                #Column address set.
    self.windowLocData[0] = 0x00
    self.windowLocData[1] = 0x02                   #Start at column 2
    self.windowLocData[2] = 0x00
    self.windowLocData[3] = self._size[0] - 1
    self._writedata(self.windowLocData)

    self._writecommand(TFT.RASET)                #Row address set.
    self.windowLocData[1] = 0x01                   #Start at row 2.
    self.windowLocData[3] = self._size[1] - 1
    self._writedata(self.windowLocData)

    data1 = bytearray(1)
    self._writecommand(TFT.COLMOD)               #Set color mode.
    data1[0] = 0x05                             #16 bit color.
    self._writedata(data1)
    time.sleep_us(10)

    self._writecommand(TFT.NORON)                #Normal display on.
    time.sleep_us(10)

    self._writecommand(TFT.RAMWR)
    time.sleep_us(500)

    self._writecommand(TFT.DISPON)
    self.cs(1)
    time.sleep_us(500)

  #@micropython.native
  def initg( self ) :
    '''Initialize a green tab version.'''
    self._reset()

    self._writecommand(TFT.SWRESET)              #Software reset.
    time.sleep_us(150)
    self._writecommand(TFT.SLPOUT)               #out of sleep mode.
    time.sleep_us(255)

    data3 = bytearray([0x01, 0x2C, 0x2D])       #fastest refresh, 6 lines front, 3 lines back.
    self._writecommand(TFT.FRMCTR1)              #Frame rate control.
    self._writedata(data3)

    self._writecommand(TFT.FRMCTR2)              #Frame rate control.
    self._writedata(data3)

    data6 = bytearray([0x01, 0x2c, 0x2d, 0x01, 0x2c, 0x2d])
    self._writecommand(TFT.FRMCTR3)              #Frame rate control.
    self._writedata(data6)
    time.sleep_us(10)

    self._writecommand(TFT.INVCTR)               #Display inversion control
    self._writedata(bytearray([0x07]))
    self._writecommand(TFT.PWCTR1)               #Power control
    data3[0] = 0xA2
    data3[1] = 0x02
    data3[2] = 0x84
    self._writedata(data3)

    self._writecommand(TFT.PWCTR2)               #Power control
    self._writedata(bytearray([0xC5]))

    data2 = bytearray(2)
    self._writecommand(TFT.PWCTR3)               #Power control
    data2[0] = 0x0A   #Opamp current small
    data2[1] = 0x00   #Boost frequency
    self._writedata(data2)

    self._writecommand(TFT.PWCTR4)               #Power control
    data2[0] = 0x8A   #Opamp current small
    data2[1] = 0x2A   #Boost frequency
    self._writedata(data2)

    self._writecommand(TFT.PWCTR5)               #Power control
    data2[0] = 0x8A   #Opamp current small
    data2[1] = 0xEE   #Boost frequency
    self._writedata(data2)

    self._writecommand(TFT.VMCTR1)               #Power control
    self._writedata(bytearray([0x0E]))

    self._writecommand(TFT.INVOFF)

    self._setMADCTL()

    self._writecommand(TFT.COLMOD)
    self._writedata(bytearray([0x05]))

    self._writecommand(TFT.CASET)                #Column address set.
    self.windowLocData[0] = 0x00
    self.windowLocData[1] = 0x01                #Start at row/column 1.
    self.windowLocData[2] = 0x00
    self.windowLocData[3] = self._size[0] - 1
    self._writedata(self.windowLocData)

    self._writecommand(TFT.RASET)                #Row address set.
    self.windowLocData[3] = self._size[1] - 1
    self._writedata(self.windowLocData)

    dataGMCTRP = bytearray([0x02, 0x1c, 0x07, 0x12, 0x37, 0x32, 0x29, 0x2d, 0x29,
                            0x25, 0x2b, 0x39, 0x00, 0x01, 0x03, 0x10])
    self._writecommand(TFT.GMCTRP1)
    self._writedata(dataGMCTRP)

    dataGMCTRN = bytearray([0x03, 0x1d, 0x07, 0x06, 0x2e, 0x2c, 0x29, 0x2d, 0x2e,
                            0x2e, 0x37, 0x3f, 0x00, 0x00, 0x02, 0x10])
    self._writecommand(TFT.GMCTRN1)
    self._writedata(dataGMCTRN)

    self._writecommand(TFT.NORON)                #Normal display on.
    time.sleep_us(10)

    self._writecommand(TFT.DISPON)
    time.sleep_us(100)

    self.cs(1)

class TFTBuffered(TFT):
  '''Framebuffer-backed ST7735: every primitive (line, circle, rectangle, text) is
     drawn in RAM through the built-in `framebuf` module (in C, microseconds), and
     `show()` sends the whole buffer to the panel in a single SPI transfer (~5 ms).
     Scene complexity is therefore almost free -> steady high FPS for any drawing.

     Usage:
        d = st7735.TFTBuffered(spi, DC, RES, CS, (128, 160))
        d.initr()
        d.fb.fill(0)
        d.fb.line(0, 0, 127, 159, d.rgb(255, 0, 0))
        d.fb.ellipse(64, 80, 30, 30, d.rgb(0, 255, 0), True)
        d.fb.text("Hi", 10, 10, d.rgb(255, 255, 255))
        d.show()

     Build colors with `d.rgb(r, g, b)` (or the pre-swapped d.C_* constants), because
     framebuf RGB565 stores bytes little-endian while the panel reads big-endian.'''

  def __init__(self, spi, aDC, aReset, aCS, ScreenSize=(128, 160)):
    super().__init__(spi, aDC, aReset, aCS, ScreenSize)
    self.width = ScreenSize[0]
    self.height = ScreenSize[1]
    self.buffer = bytearray(self.width * self.height * 2)
    self.fb = framebuf.FrameBuffer(
      self.buffer, self.width, self.height, framebuf.RGB565)
    self._dirty = []         #list of changed rectangles for flush()
    self._bg = None          #saved background copy (set_background / restore_background)
    self._glyphbuf = bytearray(8)   #temporary 8x8 glyph for scaled text
    self._glyphfb = framebuf.FrameBuffer(self._glyphbuf, 8, 8, framebuf.MONO_HLSB)

  @staticmethod
  def rgb(aR, aG, aB):
    '''Color for framebuf. Handles two things at once:
       - the panel is in BGR mode (MADCTL) -> swap R and B,
       - framebuf RGB565 stores bytes little-endian, the panel reads big-endian -> swap bytes.'''
    c = TFTColor(aB, aG, aR)                    # BGR panel: swap R<->B
    return ((c & 0xFF) << 8) | (c >> 8)         # byte swap for framebuf

  # Pre-computed color constants for use with framebuf.
  C_BLACK  = 0x0000
  C_RED    = (((TFTColor(0, 0, 0xFF) & 0xFF) << 8) | (TFTColor(0, 0, 0xFF) >> 8))
  C_GREEN  = (((TFTColor(0, 0xFF, 0) & 0xFF) << 8) | (TFTColor(0, 0xFF, 0) >> 8))
  C_BLUE   = (((TFTColor(0xFF, 0, 0) & 0xFF) << 8) | (TFTColor(0xFF, 0, 0) >> 8))
  C_WHITE  = 0xFFFF
  C_YELLOW = (((TFTColor(0, 0xFF, 0xFF) & 0xFF) << 8) | (TFTColor(0, 0xFF, 0xFF) >> 8))
  C_CYAN   = (((TFTColor(0xFF, 0xFF, 0) & 0xFF) << 8) | (TFTColor(0xFF, 0xFF, 0) >> 8))
  C_PURPLE = (((TFTColor(0xFF, 0, 0xFF) & 0xFF) << 8) | (TFTColor(0xFF, 0, 0xFF) >> 8))

  def show(self):
    '''Send the whole framebuffer to the panel in a single SPI transfer.'''
    if self._fillwin != self._size:
      self._setwindowloc((0, 0), (self.width - 1, self.height - 1))
      self._fillwin = self._size
    else:
      self._writecommand(TFT.RAMWR)
    self.dc(1)
    self.cs(0)
    self.spi.write(self.buffer)
    self.cs(1)

  def show_area(self, x, y, w, h):
    '''Partial refresh: send only the rectangle (x, y, w, h) from the framebuffer to
       the panel. The framebuffer data must already be up to date (draw into self.fb
       as usual). Transfers only w*h*2 bytes instead of the whole screen -> for small
       areas many times faster. For a moving object refresh the union of the old and
       new position (otherwise a "ghost" stays at the old position).'''
    # clip to the display
    if x < 0:
      w += x; x = 0
    if y < 0:
      h += y; y = 0
    if x + w > self.width:
      w = self.width - x
    if y + h > self.height:
      h = self.height - y
    if w <= 0 or h <= 0:
      return

    self._setwindowloc((x, y), (x + w - 1, y + h - 1))   # window to the rect (+RAMWR)
    self.dc(1)
    self.cs(0)
    mv = memoryview(self.buffer)
    stride = self.width * 2          # bytes per row of the full framebuffer
    if w == self.width:
      # full width -> contiguous block in memory, single write
      self.spi.write(mv[y * stride : (y + h) * stride])
    else:
      rowbytes = w * 2
      start = (y * self.width + x) * 2
      for _ in range(h):
        self.spi.write(mv[start : start + rowbytes])   # zero-copy row
        start += stride
    self.cs(1)

  # ---- Dirty-rectangle manager: send only what changed ----

  def mark_dirty(self, x, y, w, h):
    '''Mark a rectangle as changed. Call it for BOTH the old and new position of an
       object, then flush() sends only those areas (for many objects at once too).'''
    self._dirty.append((int(x), int(y), int(w), int(h)))

  def flush(self):
    '''Send only the marked (dirty) areas to the panel and clear the list.
       Overlapping rectangles are merged so pixels are not sent twice.
       Does nothing if nothing is marked.'''
    rects = self._dirty
    if not rects:
      return
    merged = []
    for r in rects:
      rx, ry, rw, rh = r
      rx2 = rx + rw; ry2 = ry + rh
      joined = True
      while joined:                       #repeat while anything keeps merging
        joined = False
        for i in range(len(merged)):
          mx, my, mx2, my2 = merged[i]
          if rx < mx2 and rx2 > mx and ry < my2 and ry2 > my:   #overlap
            rx = mx if mx < rx else rx
            ry = my if my < ry else ry
            rx2 = mx2 if mx2 > rx2 else rx2
            ry2 = my2 if my2 > ry2 else ry2
            merged.pop(i)
            joined = True
            break
      merged.append((rx, ry, rx2, ry2))
    self._dirty = []
    for mx, my, mx2, my2 in merged:
      self.show_area(mx, my, mx2 - mx, my2 - my)

  # ---- Static-background cache (fast restore instead of re-drawing primitives) ----

  def set_background(self):
    '''Save the CURRENT framebuffer content as the "background". Draw the static part
       of the scene (frames, grid, labels) into d.fb and call this once. Then, instead
       of re-drawing those primitives every frame, restore_background() (a C-fast copy)
       + drawing the moving things is enough. A big speed-up especially on RP2040.'''
    if self._bg is None:
      self._bg = bytearray(self.buffer)   # copy
    else:
      self._bg[:] = self.buffer

  def restore_background(self):
    '''Restore the whole saved background into the framebuffer (one fast C copy).
       Does nothing if the background has not been saved yet.'''
    if self._bg is not None:
      self.buffer[:] = self._bg

  def restore_background_area(self, x, y, w, h):
    '''Restore only a rectangle of the background (e.g. erase the old position of a
       moving object). Pairs with show_area(): restore the old area -> draw the object
       -> show_area. Touches only a small part. Does nothing if no background is saved.'''
    if self._bg is None:
      return
    if x < 0:
      w += x; x = 0
    if y < 0:
      h += y; y = 0
    if x + w > self.width:
      w = self.width - x
    if y + h > self.height:
      h = self.height - y
    if w <= 0 or h <= 0:
      return
    buf = self.buffer
    bg = self._bg
    stride = self.width * 2
    rowbytes = w * 2
    start = (y * self.width + x) * 2
    for _ in range(h):
      buf[start:start + rowbytes] = bg[start:start + rowbytes]
      start += stride

  # ---- Text helpers: ANY size (built-in 8x8 font, nearest-neighbor scaled) ----

  def _blit_glyph(self, ch, x, y, color, tw, th, bg, dotless=False):
    '''Blit a glyph from the 8x8 font scaled to tw x th. Returns (inkL, inkR, inkTop) in px.'''
    glyph = self._glyphbuf
    for i in range(8):
      glyph[i] = 0
    self._glyphfb.text(ch, 0, 0, 1)
    if dotless:
      glyph[0] = 0; glyph[1] = 0     # remove the dot over 'i' (for accented i)
    fb = self.fb
    if bg is not None:
      fb.fill_rect(x, y, tw, th, bg)
    if tw % 8 == 0 and th % 8 == 0:
      sx = tw // 8; sy = th // 8
      fr = fb.fill_rect
      for gy in range(8):
        row = glyph[gy]
        if row:
          py = y + gy * sy
          for gx in range(8):
            if row & (0x80 >> gx):
              fr(x + gx * sx, py, sx, sy, color)
    else:
      px = fb.pixel
      for oy in range(th):
        row = glyph[(oy * 8) // th]
        if row:
          yy = y + oy
          for ox in range(tw):
            if row & (0x80 >> ((ox * 8) // tw)):
              px(x + ox, yy, color)
    # glyph outline (for placing the accent): occupied columns + top row
    orb = 0
    firstrow = 8
    for r in range(8):
      row = glyph[r]
      if row:
        orb |= row
        if firstrow == 8:
          firstrow = r
    if orb == 0:
      return (0, tw, 0)
    lmin = 0
    while lmin < 8 and not (orb & (0x80 >> lmin)):
      lmin += 1
    rmax = 7
    while rmax >= 0 and not (orb & (0x80 >> rmax)):
      rmax -= 1
    return (lmin * tw // 8, (rmax + 1) * tw // 8, firstrow * th // 8)

  def _blit_glyph_small(self, ch, x, y, color, gw, gh, dotless=False):
    '''Blit a glyph from the 5x7 font scaled to gw x gh. Returns (inkL, inkR, inkTop) in px.
       When SHRINKING (gw<5 or gh<7) pixels are OR-merged instead of dropped, so letters
       stay whole (just bolder) even below the native 7 px. At 7 px and above this is
       identical to nearest-neighbor (each cell spans 1).'''
    o = ord(ch)
    if o < 0x20 or o > 0x7E:
      o = 0x3F                       # '?' for an unknown char
    base = (o - 0x20) * 5
    font = _FONT5X7
    px = self.fb.pixel
    for ox in range(gw):
      col = font[base + (ox * 5) // gw]   # native width (gw=5) -> exact column
      if dotless:
        col &= 0xFE                       # remove the top row (the dot over 'i')
      if col:
        xx = x + ox
        for oy in range(gh):
          r0 = (oy * 7) // gh
          r1 = ((oy + 1) * 7) // gh
          if r1 <= r0:
            r1 = r0 + 1
          mask = 0
          for r in range(r0, r1):         # OR vertically -> letters stay whole (bolder)
            mask |= (1 << r)
          if col & mask:
            px(xx, y + oy, color)
    lmin = 5; rmax = -1; orc = 0
    for c in range(5):
      cb = font[base + c]
      if dotless:
        cb &= 0xFE
      if cb:
        orc |= cb
        if c < lmin:
          lmin = c
        if c > rmax:
          rmax = c
    if rmax < 0:
      return (0, gw, 0)
    minrow = 0
    while not (orc & (1 << minrow)):
      minrow += 1
    return (lmin * gw // 5, (rmax + 1) * gw // 5, minrow * gh // 7)

  def _blit_glyph_micro(self, ch, x, y, color, gw, gh, dotless=False):
    '''Blit a glyph from the micro 3x6 font (native width 3). Returns (inkL, inkR, inkTop).
       gh=6 is native; gh=5 -> drops row 5 (descenders only), the top 3x5 stays fully clean.'''
    o = ord(ch)
    if o < 0x20 or o > 0x7E:
      o = 0x3F
    base = (o - 0x20) * 3
    font = _FONT3X6
    px = self.fb.pixel
    for ox in range(gw):
      col = font[base + (ox * 3) // gw]
      if dotless:
        col &= 0x3E                  # remove the top row (the dot over 'i')
      if col:
        xx = x + ox
        for oy in range(gh):
          if col & (1 << ((oy * 6) // gh)):
            px(xx, y + oy, color)
    lmin = 3; rmax = -1; orc = 0
    for c in range(3):
      cb = font[base + c]
      if dotless:
        cb &= 0x3E
      if cb:
        orc |= cb
        if c < lmin:
          lmin = c
        if c > rmax:
          rmax = c
    if rmax < 0:
      return (0, gw, 0)
    minrow = 0
    while not (orc & (1 << minrow)):
      minrow += 1
    return (lmin * gw // 3, (rmax + 1) * gw // 3, minrow * gh // 6)

  def _cell(self, height):
    '''Return (tier, glyph_width, gap). tier: 0=large 8x8 (>=8px), 1=5x7 (7px),
       2=micro 3x6 (<=6px). The width is native to the chosen font (not compressed).'''
    if height >= 8:
      return 0, height, 0
    if height == 7:
      return 1, 5, 1
    return 2, 3, 1        # micro 3x6, native width 3 + 1 gap

  def _tline(self, x1, y1, x2, y2, color, thick):
    '''A line 'thick' px wide (offset in x) - for bolder accents on larger fonts.'''
    fb = self.fb
    fb.line(x1, y1, x2, y2, color)
    for i in range(1, thick):
      fb.line(x1 + i, y1, x2 + i, y2, color)

  def _accent(self, gx, y, inkl, inkr, inktop, height, acc, color):
    '''Draw a Czech accent just above the letter's REAL top (inktop). The size grows
       with the font height; on small fonts (<12 px) it stays tiny and un-shifted (so
       small fonts look as before). 1=acute /, 2=caron v, 3=ring o, 4/5=apostrophe (d/t).'''
    fb = self.fb
    w = height // 5               # mark size
    if w < 2:
      w = 2
    thick = 1 if height < 14 else 2
    top = y + inktop              # the letter's real top
    if acc == 4 or acc == 5:      # apostrophe (d: right of the stem / t: top-right corner)
      if acc == 4:                # d: to the right, past the stem
        tx = gx + inkr + (2 if height >= 12 else 1)
      else:                       # t: into the top-right corner (empty there)
        tx = gx + inkr - (4 if height >= 12 else 2)
      atop = top - w
      if atop < 0:
        atop = 0
      abot = top + w // 2
      if height < 12:                # small font: shorter apostrophe (was too long)
        abot -= 1
      if abot <= atop:
        abot = atop + 1
      self._tline(tx, atop, tx, abot, color, thick)
      return
    big = height >= 12
    gap = 1 if big else 0         # +1 up on large fonts
    b = top - 1 - gap             # bottom of the mark just above the letter
    if b < 0:
      b = 0
    mid = gx + (inkl + inkr) // 2
    if acc == 1:                  # acute  /  (+2 right on large fonts)
      cxa = mid + (2 if big else 0)
      hw = w * 2 // 3
      if hw < 1:
        hw = 1
      self._tline(cxa - hw, b, cxa + hw, b - w, color, thick)
    elif acc == 2:                # caron  v  (+1 right on large fonts)
      cxc = mid + (1 if big else 0)
      self._tline(cxc - w, b - w, cxc, b, color, thick)
      self._tline(cxc + w, b - w, cxc, b, color, thick)
    else:                         # ring  o
      ry = w // 2
      if ry < 1:
        ry = 1
      cyr = b - ry
      fb.ellipse(mid, cyr, w, ry, color)
      if thick > 1:
        fb.ellipse(mid, cyr, w - 1 if w > 1 else 1, ry, color)

  def text_size(self, aStr, x, y, color, height, bg=None, spacing=None):
    '''Draw text at ANY height 'height' px, including Czech diacritics.
       7 px uses the sharp 5x7 font, <=6 px the micro 3x6 font, >=8 px scales the
       built-in 8x8 font. Letters have a uniform full height; accents are drawn ABOVE
       the line, so leave ~height//7 + 1 px of space above the text.
       bg = background color, spacing = gap between glyphs.'''
    if height < 1:
      height = 1
    tier, gw, gap = self._cell(height)
    if spacing is not None:
      gap = spacing
    cz = _CZ
    step = gw + gap
    cx = x
    for ch in aStr:
      acc = 0
      dotless = False
      m = cz.get(ch)
      if m:
        ch, acc = m
        if ch == "i":
          dotless = True                      # dotless i (the accent replaces the dot)
      if bg is not None and tier != 0:
        self.fb.fill_rect(cx, y, step, height, bg)
      if tier == 0:
        inkl, inkr, inktop = self._blit_glyph(ch, cx, y, color, height, height, bg, dotless)
      elif tier == 1:
        inkl, inkr, inktop = self._blit_glyph_small(ch, cx, y, color, gw, height, dotless)
      else:
        inkl, inkr, inktop = self._blit_glyph_micro(ch, cx, y, color, gw, height, dotless)
      if acc:
        self._accent(cx, y, inkl, inkr, inktop, height, acc, color)
      cx += step
      if acc == 4:               # d with apostrophe needs a little room on the right
        cx += 2 if height >= 12 else 1
    return cx

  def text_scaled(self, aStr, x, y, color, scale=1, bg=None):
    '''Text enlarged 'scale' times (may be fractional, e.g. 1.5). scale=1 -> 8 px.'''
    h = int(round(8 * scale))
    if h < 1:
      h = 1
    return self.text_size(aStr, x, y, color, h, bg)

  def text_width(self, aStr, height=None, scale=1, spacing=None):
    '''Return the text width in px for a given size (for alignment/layout).'''
    h = height if height is not None else int(round(8 * scale))
    if h < 1:
      h = 1
    n = len(aStr)
    if not n:
      return 0
    tier, gw, gap = self._cell(h)
    if spacing is not None:
      gap = spacing
    return n * (gw + gap)

  def text_centered(self, aStr, y, color, scale=1, bg=None, height=None):
    '''Text horizontally centered across the display width. Pass either scale or height (px).
       Returns the x used.'''
    h = height if height is not None else int(round(8 * scale))
    if h < 1:
      h = 1
    x = (self.width - self.text_width(aStr, height=h)) // 2
    if x < 0:
      x = 0
    self.text_size(aStr, x, y, color, h, bg)
    return x


class TFTPaletted(TFTBuffered):
  '''Palette-backed framebuffer for low-RAM boards (e.g. Pico W). Stores 1 byte/pixel
     (depth=8, up to 256 colors) or 4 bits/pixel (depth=4, 16 colors) instead of RGB565,
     and converts to RGB565 in small horizontal bands inside show(). Roughly HALF
     (depth=8) or a QUARTER (depth=4) of the RAM of TFTBuffered, at the cost of a limited
     palette and a small per-frame conversion pass.

     Draw with palette INDICES (0..255 / 0..15), NOT rgb() values. Define the colors with
     set_palette(index, r, g, b); the first 16 entries have sensible defaults and the
     P_* index constants (P_RED, P_GREEN, ...). All the drawing/text helpers are inherited.

     RAM (128x160): depth 8 ~20 KB + ~4 KB band + 512 B palette; depth 4 ~10 KB + ~4 KB.

     Usage:
        d = st7735.TFTPaletted(spi, DC, RST, CS, (128, 160), depth=8)
        d.initr(); spi.init(baudrate=32_000_000)
        d.set_palette(9, 255, 140, 0)          # (re)define index 9 = orange
        d.fb.fill(d.P_BLACK)
        d.fb.ellipse(64, 80, 26, 26, d.P_GREEN, True)
        d.text_size("Ahoj", 8, 8, d.P_WHITE, 12)
        d.show()'''

  P_BLACK = 0; P_WHITE = 1; P_RED = 2; P_GREEN = 3; P_BLUE = 4
  P_YELLOW = 5; P_CYAN = 6; P_PURPLE = 7; P_GRAY = 8; P_ORANGE = 9

  _DEFAULT = (                      # (index, r, g, b) for the first 16 palette entries
    (0, 0, 0, 0),      (1, 255, 255, 255), (2, 255, 0, 0),   (3, 0, 255, 0),
    (4, 0, 0, 255),    (5, 255, 255, 0),   (6, 0, 255, 255), (7, 255, 0, 255),
    (8, 128, 128, 128),(9, 255, 140, 0),   (10, 60, 60, 60), (11, 190, 190, 190),
    (12, 0, 0, 128),   (13, 0, 128, 0),    (14, 128, 0, 0),  (15, 0, 128, 128),
  )

  def __init__(self, spi, aDC, aReset, aCS, ScreenSize=(128, 160), depth=8, bandh=16):
    TFT.__init__(self, spi, aDC, aReset, aCS, ScreenSize)   # skip the 40 KB RGB565 alloc
    if depth not in (4, 8):
      raise ValueError("depth must be 4 or 8")
    self.width = ScreenSize[0]
    self.height = ScreenSize[1]
    self.depth = depth
    if bandh > self.height:
      bandh = self.height
    self.bandh = bandh
    if depth == 8:
      self.buffer = bytearray(self.width * self.height)
      fmt = framebuf.GS8
      ncol = 256
    else:
      self.buffer = bytearray((self.width * self.height) // 2)
      fmt = framebuf.GS4_HMSB
      ncol = 16
    self.fb = framebuf.FrameBuffer(self.buffer, self.width, self.height, fmt)
    self._bandbuf = bytearray(self.width * bandh * 2)     # RGB565 conversion strip
    self._bandfb = framebuf.FrameBuffer(self._bandbuf, self.width, bandh, framebuf.RGB565)
    self._palbuf = bytearray(ncol * 2)                    # index -> RGB565 lookup for blit
    self._palette = framebuf.FrameBuffer(self._palbuf, ncol, 1, framebuf.RGB565)
    self._ncol = ncol
    self._glyphbuf = bytearray(8)                         # text infra (inherited methods)
    self._glyphfb = framebuf.FrameBuffer(self._glyphbuf, 8, 8, framebuf.MONO_HLSB)
    self._dirty = []
    self._bg = None
    for i, r, g, b in self._DEFAULT:
      if i < ncol:
        self.set_palette(i, r, g, b)

  def set_palette(self, index, r, g, b):
    '''Define palette entry 'index' as color (r, g, b). Draw with this index afterwards.'''
    self._palette.pixel(index, 0, TFTBuffered.rgb(r, g, b))

  def show(self):
    '''Convert the palette framebuffer to RGB565 band by band and push it to the panel.'''
    W = self.width; H = self.height; bh = self.bandh
    self._setwindowloc((0, 0), (W - 1, H - 1))
    self.dc(1)
    self.cs(0)
    mv = memoryview(self._bandbuf)
    pal = self._palette; src = self.fb; band = self._bandfb; spi = self.spi
    y0 = 0
    while y0 < H:
      h = H - y0
      if h > bh:
        h = bh
      band.blit(src, 0, -y0, -1, pal)        # convert source rows [y0, y0+h) -> RGB565
      spi.write(mv[:W * h * 2])
      y0 += bh
    self.cs(1)

  def show_area(self, x, y, w, h):
    '''Partial refresh of a rectangle, converted through the palette. Full-width areas
       are cheapest; a narrower area still converts full rows but sends only its columns.'''
    if y < 0:
      h += y; y = 0
    if y + h > self.height:
      h = self.height - y
    if x < 0:
      w += x; x = 0
    if x + w > self.width:
      w = self.width - x
    if w <= 0 or h <= 0:
      return
    W = self.width; bh = self.bandh
    self._setwindowloc((x, y), (x + w - 1, y + h - 1))
    self.dc(1)
    self.cs(0)
    mv = memoryview(self._bandbuf)
    pal = self._palette; src = self.fb; band = self._bandfb; spi = self.spi
    rowbytes = w * 2
    yy = y
    end = y + h
    while yy < end:
      hh = end - yy
      if hh > bh:
        hh = bh
      band.blit(src, 0, -yy, -1, pal)
      if w == W:
        spi.write(mv[:W * hh * 2])
      else:
        for r in range(hh):
          start = (r * W + x) * 2
          spi.write(mv[start:start + rowbytes])
      yy += bh
    self.cs(1)

  def restore_background_area(self, x, y, w, h):
    '''Restore a background rectangle. Works per whole rows (safe for GS8/GS4 packing),
       so x and w are ignored; only the row range [y, y+h) is restored.'''
    if self._bg is None:
      return
    if y < 0:
      h += y; y = 0
    if y + h > self.height:
      h = self.height - y
    if h <= 0:
      return
    bpr = len(self.buffer) // self.height    # bytes per row (1*W, or W//2 for GS4)
    start = y * bpr
    n = h * bpr
    self.buffer[start:start + n] = self._bg[start:start + n]


class TFTBanded(TFTBuffered):
  '''Band renderer for the lowest RAM. Keeps only a small RGB565 strip (bandh rows) and
     renders the frame one horizontal band at a time, in FULL RGB565 color. In exchange
     you supply a draw callback that redraws the whole scene once per band. All drawing
     and text helpers are inherited (colors are rgb()/C_* as usual).

     RAM (128x160, bandh=20): ~5 KB (vs 40 KB for TFTBuffered).

     Draw in SCREEN coordinates minus the band's y0 (anything off-band is clipped):
        W, H = d.width, d.height
        def draw(fb, y0):
            fb.fill(d.C_BLACK)
            fb.rect(0, 0 - y0, W, H, d.C_WHITE)
            fb.ellipse(bx, by - y0, r, r, d.C_RED, True)
            d.text_size("Ahoj", 8, 8 - y0, d.C_WHITE, 12)
        d.render(draw)'''

  def __init__(self, spi, aDC, aReset, aCS, ScreenSize=(128, 160), bandh=20):
    TFT.__init__(self, spi, aDC, aReset, aCS, ScreenSize)
    self.width = ScreenSize[0]
    self.height = ScreenSize[1]
    if bandh > self.height:
      bandh = self.height
    self.bandh = bandh
    self.buffer = bytearray(self.width * bandh * 2)
    self.fb = framebuf.FrameBuffer(self.buffer, self.width, bandh, framebuf.RGB565)
    self._glyphbuf = bytearray(8)
    self._glyphfb = framebuf.FrameBuffer(self._glyphbuf, 8, 8, framebuf.MONO_HLSB)
    self._dirty = []
    self._bg = None

  def render(self, draw):
    '''Render one full frame. 'draw(fb, y0)' is called once per band and must draw the
       whole scene shifted up by y0 (use screen_y - y0). fb is a bandh-tall framebuffer.'''
    W = self.width; H = self.height; bh = self.bandh
    mv = memoryview(self.buffer)
    spi = self.spi
    y0 = 0
    while y0 < H:
      h = H - y0
      if h > bh:
        h = bh
      draw(self.fb, y0)
      self._setwindowloc((0, y0), (W - 1, y0 + h - 1))
      self.dc(1)
      self.cs(0)
      spi.write(mv[:W * h * 2])
      self.cs(1)
      y0 += bh

  def show(self):
    raise NotImplementedError("TFTBanded renders via render(draw); there is no full-screen buffer to show()")

  def show_area(self, x, y, w, h):
    raise NotImplementedError("TFTBanded renders via render(draw); show_area() is not available")


def create(buffered=True, mode="full", baudrate=32_000_000, size=(128, 160),
           spi_id=1, sck=26, mosi=27, dc=22, rst=28, cs=20, bl=21,
           depth=8, bandh=None):
  '''One-line setup: creates the SPI bus + pins, turns the backlight on, initializes
     the panel (including the SPI clock boost) and returns a display ready to draw on.

     Pass your own pin numbers to match your wiring. Usage:
        import st7735
        d = st7735.create(sck=..., mosi=..., dc=..., rst=..., cs=..., bl=...)
        d.fb.fill(0); d.fb.text("Hi", 4, 4, d.C_WHITE); d.show()

     mode selects the framebuffer memory strategy (see DRIVER_GUIDE.md):
        "full"   -> TFTBuffered  (full RGB565, ~40 KB, fastest, default)
        "gs8"    -> TFTPaletted(depth=8)  (~20 KB, 256 palette colors)
        "gs4"    -> TFTPaletted(depth=4)  (~10 KB, 16 palette colors)
        "banded" -> TFTBanded    (~5 KB, full color, render(draw) callback)
     'depth'/'bandh' tune the palette/band modes (bandh defaults: 16 palette, 20 banded).
     buffered=False returns the plain TFT (for full-screen fills only; ignores mode).'''
  spi = machine.SPI(spi_id, baudrate=baudrate, polarity=0, phase=0,
                    sck=machine.Pin(sck), mosi=machine.Pin(mosi))
  if not buffered:
    d = TFT(spi, dc, rst, cs, size)
  elif mode == "gs8":
    d = TFTPaletted(spi, dc, rst, cs, size, depth=8, bandh=bandh or 16)
  elif mode == "gs4":
    d = TFTPaletted(spi, dc, rst, cs, size, depth=4, bandh=bandh or 16)
  elif mode == "banded":
    d = TFTBanded(spi, dc, rst, cs, size, bandh=bandh or 20)
  else:                           # "full" (default)
    d = TFTBuffered(spi, dc, rst, cs, size)
  d.initr()                       #panel init + clk_peri boost
  spi.init(baudrate=baudrate)     #re-init after the boost -> real high clock
  if bl is not None:
    d.attach_backlight(bl)
    d.backlight(100)
  return d
