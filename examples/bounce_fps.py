# bounce_fps.py - full-frame animation with a live FPS counter.
#
# Redraws the ENTIRE screen every frame (clear + static scene + moving ball) and calls
# show() once per frame, so the printed FPS reflects worst-case "redraw everything" work.
# On a Pico 2 W this holds ~140+ FPS thanks to the framebuffer + SPI clock boost.
#
# Edit the PINS below, copy st7735.py to the board, and run. Stop with Ctrl-C.

import time
import st7735

# --- your wiring (change these) ---
SPI_ID = 1
SCK, MOSI = 26, 27
DC, RST, CS = 22, 28, 20
BL = 21
# ----------------------------------

d = st7735.create(spi_id=SPI_ID, sck=SCK, mosi=MOSI, dc=DC, rst=RST, cs=CS, bl=BL)
W, H, fb = d.width, d.height, d.fb
BG = d.rgb(10, 10, 25)
R = 11

def scene(bx, by, fps):
    fb.fill(BG)
    fb.rect(0, 0, W, H, d.C_WHITE)
    d.text_size("FPS %d" % fps, 6, 6, d.C_CYAN, 10)
    for i in range(5):
        fb.rect(10 + i * 22, 40, 16, 16, d.C_GREEN if i % 2 else d.C_PURPLE, True)
    fb.ellipse(bx, by, R, R, d.rgb(255, 120, 0), True)

x, y = W / 2.0, H / 2.0
dx, dy = 0.82, 0.57          # direction (roughly unit length)
speed = 240.0                # px/s

t_frame = time.ticks_us()
t_fps = time.ticks_ms()
frames = 0
fps = 0
print("bouncing ball, full redraw per frame (Ctrl-C to stop)")
while True:
    now = time.ticks_us()
    dt = time.ticks_diff(now, t_frame) / 1_000_000
    t_frame = now

    x += dx * speed * dt
    y += dy * speed * dt
    if x < R:            x = R;            dx = -dx
    elif x > W - 1 - R:  x = W - 1 - R;    dx = -dx
    if y < R:            y = R;            dy = -dy
    elif y > H - 1 - R:  y = H - 1 - R;    dy = -dy

    scene(int(x), int(y), fps)
    d.show()
    frames += 1
    if time.ticks_diff(time.ticks_ms(), t_fps) >= 1000:
        fps = frames
        frames = 0
        t_fps += 1000
        print("FPS =", fps)
