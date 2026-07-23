#!/usr/bin/env python3
"""Animated 7-segment clock demo on the Nextion (480x272), driven entirely from
the Pi over serial -- no .tft/font needed (digits are drawn from rectangles).

- HH:MM:SS clock, redraws only changed digits (easy on the 9600 baud link)
- bouncing ball animation
- touch button toggles 24H <-> 12H (raw touch via sendxy=1); PM dot in 12H mode
- touch coordinates are logged to stdout (journal) for touch testing
"""
import time
from datetime import datetime

import serial

PORT, BAUD, TERM = "/dev/serial0", 9600, b"\xff\xff\xff"
s = serial.Serial(PORT, BAUD, timeout=0)

# palette (RGB565)
BG = 2146        # dark slate
AMBER = 52261    # clock digits
GREEN = 11049    # title bar (Three Oak Woods green)
BALLC = 2016     # bright green ball
BTNC = 52261     # amber button
RED = 63488      # PM dot

# 7-segment maps
SEGS = {0: "abcdef", 1: "bc", 2: "abged", 3: "abgcd", 4: "fgbc",
        5: "afgcd", 6: "afgecd", 7: "abc", 8: "abcdefg", 9: "abcdfg"}


def cmd(c):
    s.write(c.encode() + TERM)


def seg_rects(x, y, dw, dh, t):
    h2 = dh // 2
    return {
        "a": (x + t, y, dw - 2 * t, t),
        "b": (x + dw - t, y + t, t, h2 - t),
        "c": (x + dw - t, y + h2, t, h2 - t),
        "d": (x + t, y + dh - t, dw - 2 * t, t),
        "e": (x, y + h2, t, h2 - t),
        "f": (x, y + t, t, h2 - t),
        "g": (x + t, y + h2 - t // 2, dw - 2 * t, t),
    }


def draw_digit(x, y, dw, dh, t, val, color):
    cmd(f"fill {x},{y},{dw},{dh},{BG}")           # clear cell
    if val < 0:
        return                                     # blank (leading 12H zero)
    r = seg_rects(x, y, dw, dh, t)
    for name in SEGS[val]:
        rx, ry, rw, rh = r[name]
        cmd(f"fill {rx},{ry},{rw},{rh},{color}")


# layout
DX = [69, 119, 193, 243, 317, 367]
DY, DW, DH, T = 58, 44, 84, 8
C1X, C2X = 169, 293
BTN = (170, 200, 140, 56)          # x, y, w, h
MDX, MDY, MDW, MDH, MT = [196, 236], 210, 28, 40, 6
PMX, PMY, PMR = 432, 58, 10

mode12 = False


def draw_button():
    x, y, w, h = BTN
    cmd(f"fill {x},{y},{w},{h},{BTNC}")
    for i, ch in enumerate("12" if mode12 else "24"):
        draw_digit(MDX[i], MDY, MDW, MDH, MT, int(ch), BG)


def draw_static():
    cmd(f"cls {BG}")
    cmd(f"fill 0,0,480,34,{GREEN}")
    for cx in (C1X, C2X):
        cmd(f"fill {cx + 4},{DY + 22},10,10,{AMBER}")
        cmd(f"fill {cx + 4},{DY + 50},10,10,{AMBER}")
    draw_button()


def compute_digits(now):
    h = (now.hour % 12 or 12) if mode12 else now.hour
    text = f"{h:02d}{now.minute:02d}{now.second:02d}"
    d = [int(c) for c in text]
    if mode12 and h < 10:
        d[0] = -1
    return d


def draw_pm(now):
    on = mode12 and now.hour >= 12
    cmd(f"cirs {PMX},{PMY},{PMR},{RED if on else BG}")


buf = bytearray()


def poll_touch_in_button():
    n = s.in_waiting
    if n:
        buf.extend(s.read(n))
    pressed = False
    while len(buf) >= 9:
        if buf[0] == 0x67 and buf[6] == 0xFF and buf[7] == 0xFF and buf[8] == 0xFF:
            x = (buf[1] << 8) | buf[2]
            y = (buf[3] << 8) | buf[4]
            ev = buf[5]
            del buf[:9]
            print(f"touch x={x} y={y} ev={ev}", flush=True)
            if ev == 1:
                bx, by, bw, bh = BTN
                if bx <= x <= bx + bw and by <= y <= by + bh:
                    pressed = True
        else:
            del buf[:1]
    return pressed


def main():
    global mode12
    cmd("bkcmd=0")
    cmd("sendxy=1")
    time.sleep(0.1)
    s.reset_input_buffer()
    draw_static()

    prev = [None] * 6
    last_sec = -1
    last_toggle = 0.0
    bx, vx, BALLY, BALLR = 14, 7, 172, 9
    last_ball = time.time()

    while True:
        if poll_touch_in_button() and time.time() - last_toggle > 0.6:
            last_toggle = time.time()
            mode12 = not mode12
            draw_button()
            prev = [None] * 6
            print(f"mode -> {'12H' if mode12 else '24H'}", flush=True)

        now = datetime.now()
        if now.second != last_sec:
            last_sec = now.second
            for i, val in enumerate(compute_digits(now)):
                if val != prev[i]:
                    draw_digit(DX[i], DY, DW, DH, T, val, AMBER)
                    prev[i] = val
            draw_pm(now)

        t = time.time()
        if t - last_ball > 0.08:
            last_ball = t
            cmd(f"fill {bx - BALLR},{BALLY - BALLR},{2 * BALLR},{2 * BALLR},{BG}")
            bx += vx
            if bx <= BALLR + 2 or bx >= 480 - BALLR - 2:
                vx = -vx
                bx += vx
            cmd(f"cirs {bx},{BALLY},{BALLR},{BALLC}")

        time.sleep(0.02)


if __name__ == "__main__":
    main()
