#!/usr/bin/env python3
"""Clock demo on the Nextion (480x272), driven from the Pi over serial, now using
REAL fonts from the flashed .tft (font 0 = small, font 1 = large) via xstr.

- HH:MM:SS clock in the large font, live date in the small font
- bouncing square animation
- segmented pill toggle [ 24H | 12H ] with real text labels; PM/AM shown in 12H
- raw touch via sendxy=1 (re-asserted); touches logged
- sleep after SLEEP_AFTER s of no touch (backlight fades off); any touch wakes it
"""
import time
from datetime import datetime

import serial

PORT, BAUD, TERM = "/dev/serial0", 9600, b"\xff\xff\xff"
s = serial.Serial(PORT, BAUD, timeout=0)

# palette (RGB565)
BG = 2146        # dark slate background
AMBER = 52261    # clock
GREEN = 11049    # title bar
BALLC = 2016     # bright green ball
TRACK = 16904    # inactive toggle track (grey)
LIGHT = 50712    # light grey text
RED = 63488      # PM
WHITE = 65535

FONT_BIG = 1     # large font from the .tft
FONT_SM = 0      # small font

SLEEP_AFTER = 30

mode12 = False


def cmd(c):
    s.write(c.encode() + TERM)
    s.flush()


def text(x, y, w, h, fid, color, bg, string, xc=1, yc=1):
    """xstr with solid background (sta=1) -> also clears the box each draw."""
    cmd(f'xstr {x},{y},{w},{h},{fid},{color},{bg},{xc},{yc},1,"{string}"')


def pill(x, y, w, h, color):
    r = h // 2
    cmd(f"fill {x + r},{y},{w - 2 * r},{h},{color}")
    cmd(f"cirs {x + r},{y + r},{r},{color}")
    cmd(f"cirs {x + w - r},{y + r},{r},{color}")


# ---- layout ----
CLOCK = (30, 44, 420, 78)          # x,y,w,h  (big font, centred)
DATE = (30, 128, 420, 30)
PMBOX = (388, 42, 82, 30)
BALLY, BALLR = 180, 13

TGX, TGY, TGW, TGH = 148, 200, 184, 56
TG_HALF = TGW // 2
TG_MID = TGX + TG_HALF


def draw_toggle():
    pill(TGX, TGY, TGW, TGH, TRACK)
    m = 4
    if mode12:
        pill(TG_MID, TGY + m, TG_HALF - m, TGH - 2 * m, AMBER)
    else:
        pill(TGX + m, TGY + m, TG_HALF - m, TGH - 2 * m, AMBER)
    lh = TGH - 20
    text(TGX + 10, TGY + 10, TG_HALF - 20, lh, FONT_SM,
         BG if not mode12 else LIGHT, AMBER if not mode12 else TRACK, "24H")
    text(TG_MID + 10, TGY + 10, TG_HALF - 20, lh, FONT_SM,
         BG if mode12 else LIGHT, AMBER if mode12 else TRACK, "12H")


def draw_static():
    cmd(f"cls {BG}")
    cmd(f"fill 0,0,480,34,{GREEN}")
    text(0, 3, 480, 28, FONT_SM, WHITE, GREEN, "RasPi0W  \xb7  Nextion")
    draw_toggle()


def time_str(now):
    if mode12:
        h = now.hour % 12 or 12
        return f"{h}:{now.strftime('%M:%S')}"
    return now.strftime("%H:%M:%S")


buf = bytearray()


def poll_touch():
    n = s.in_waiting
    if n:
        buf.extend(s.read(n))
    any_press = False
    hit = None
    while len(buf) >= 9:
        if buf[0] == 0x67 and buf[6] == 0xFF and buf[7] == 0xFF and buf[8] == 0xFF:
            x = (buf[1] << 8) | buf[2]
            y = (buf[3] << 8) | buf[4]
            ev = buf[5]
            del buf[:9]
            print(f"touch x={x} y={y} ev={ev}", flush=True)
            if ev == 1:
                any_press = True
                if TGX <= x <= TGX + TGW and TGY <= y <= TGY + TGH:
                    hit = x
        else:
            del buf[:1]
    return any_press, hit


def main():
    global mode12
    cmd("bkcmd=0")
    cmd("sendxy=1")
    cmd("dim=100")
    time.sleep(0.1)
    s.reset_input_buffer()
    draw_static()

    prev_t = prev_d = prev_pm = None
    last_toggle = 0.0
    last_sendxy = last_activity = time.time()
    asleep = False
    bx, vx = 24, 9
    last_ball = time.time()

    while True:
        any_press, btn_x = poll_touch()
        t = time.time()
        if any_press:
            last_activity = t

        if t - last_sendxy > 2.0:
            last_sendxy = t
            cmd("sendxy=1")

        if asleep:
            if any_press:
                asleep = False
                cmd("dim=100")
                prev_t = None                 # force clock refresh
                print("wake", flush=True)
            time.sleep(0.03)
            continue

        if t - last_activity > SLEEP_AFTER:
            asleep = True
            print("sleep", flush=True)
            for d in (70, 45, 22, 0):
                cmd(f"dim={d}")
                time.sleep(0.06)
            continue

        if btn_x is not None and t - last_toggle > 0.4:
            last_toggle = t
            want12 = btn_x >= TG_MID
            if want12 != mode12:
                mode12 = want12
                draw_toggle()
                prev_t = prev_pm = None
                print(f"mode -> {'12H' if mode12 else '24H'}", flush=True)

        now = datetime.now()
        ts = time_str(now)
        if ts != prev_t:
            prev_t = ts
            text(*CLOCK, FONT_BIG, AMBER, BG, ts)
        ds = now.strftime("%a %b %d")
        if ds != prev_d:
            prev_d = ds
            text(*DATE, FONT_SM, LIGHT, BG, ds)
        pm = ("PM" if now.hour >= 12 else "AM") if mode12 else ""
        if pm != prev_pm:
            prev_pm = pm
            text(*PMBOX, FONT_SM, RED, BG, pm)

        if t - last_ball > 0.11:
            last_ball = t
            cmd(f"fill {bx - BALLR},{BALLY - BALLR},{2 * BALLR},{2 * BALLR},{BG}")
            bx += vx
            if bx <= BALLR + 2 or bx >= 480 - BALLR - 2:
                vx = -vx
                bx += vx
            cmd(f"fill {bx - BALLR},{BALLY - BALLR},{2 * BALLR},{2 * BALLR},{BALLC}")

        time.sleep(0.02)


if __name__ == "__main__":
    main()
