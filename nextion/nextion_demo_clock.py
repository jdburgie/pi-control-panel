#!/usr/bin/env python3
"""Animated 7-segment clock demo on the Nextion (480x272), driven entirely from
the Pi over serial -- no .tft/font needed (digits are drawn from rectangles).

- HH:MM:SS clock, redraws only changed digits (easy on the 9600 baud link)
- bouncing ball animation
- a segmented pill toggle [ 24 | 12 ]: tap a side to pick 24H/12H; PM dot in 12H
- raw touch via sendxy=1 (re-asserted periodically); touches logged to stdout
- sleep after SLEEP_AFTER seconds of no touch (backlight fades to off); any touch
  wakes it back to full brightness (the wake tap only wakes, it won't toggle)
"""
import time
from datetime import datetime

import serial

PORT, BAUD, TERM = "/dev/serial0", 9600, b"\xff\xff\xff"
s = serial.Serial(PORT, BAUD, timeout=0)

# palette (RGB565)
BG = 2146        # dark slate background
AMBER = 52261    # clock digits + active toggle segment
GREEN = 11049    # title bar (Three Oak Woods green)
BALLC = 2016     # bright green ball
TRACK = 16904    # dark grey toggle track (inactive)
LIGHT = 50712    # light grey (inactive segment digits)
RED = 63488      # PM dot

# 7-segment maps
SEGS = {0: "abcdef", 1: "bc", 2: "abged", 3: "abgcd", 4: "fgbc",
        5: "afgcd", 6: "afgecd", 7: "abc", 8: "abcdefg", 9: "abcdfg"}


def cmd(c):
    s.write(c.encode() + TERM)
    s.flush()  # pace writes to the 9600 link so the Nextion RX doesn't overrun


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


def draw_digit(x, y, dw, dh, t, val, color, bg=BG):
    cmd(f"fill {x},{y},{dw},{dh},{bg}")           # clear cell to its background
    if val < 0:
        return                                     # blank (leading 12H zero)
    r = seg_rects(x, y, dw, dh, t)
    for name in SEGS[val]:
        rx, ry, rw, rh = r[name]
        cmd(f"fill {rx},{ry},{rw},{rh},{color}")


def pill(x, y, w, h, color):
    """Rounded (pill) horizontal bar."""
    r = h // 2
    cmd(f"fill {x + r},{y},{w - 2 * r},{h},{color}")
    cmd(f"cirs {x + r},{y + r},{r},{color}")
    cmd(f"cirs {x + w - r},{y + r},{r},{color}")


# ---- layout ----
DX = [69, 119, 193, 243, 317, 367]          # clock digit x positions
DY, DW, DH, T = 40, 44, 84, 8
C1X, C2X = 169, 293
PMX, PMY, PMR = 432, 40, 10

# segmented toggle [ 24 | 12 ]
TGX, TGY, TGW, TGH = 148, 202, 184, 54
TG_HALF = TGW // 2
TG_MID = TGX + TG_HALF                        # x boundary between the two halves
LDW, LDH, LT = 22, 32, 5                      # toggle label digit size

SLEEP_AFTER = 30          # seconds of no touch before the backlight sleeps

mode12 = False


def draw_two(text, cx, y, color, bg):
    gap = 5
    x0 = cx - (2 * LDW + gap) // 2
    draw_digit(x0, y, LDW, LDH, LT, int(text[0]), color, bg)
    draw_digit(x0 + LDW + gap, y, LDW, LDH, LT, int(text[1]), color, bg)


def draw_button():
    pill(TGX, TGY, TGW, TGH, TRACK)                       # full track
    m = 4
    if mode12:                                            # highlight right half
        pill(TG_MID, TGY + m, TG_HALF - m, TGH - 2 * m, AMBER)
    else:                                                 # highlight left half
        pill(TGX + m, TGY + m, TG_HALF - m, TGH - 2 * m, AMBER)
    ly = TGY + (TGH - LDH) // 2
    draw_two("24", TGX + TG_HALF // 2, ly, BG if not mode12 else LIGHT,
             AMBER if not mode12 else TRACK)
    draw_two("12", TG_MID + TG_HALF // 2, ly, BG if mode12 else LIGHT,
             AMBER if mode12 else TRACK)


def draw_static():
    cmd(f"cls {BG}")
    cmd(f"fill 0,0,480,30,{GREEN}")
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


def poll_touch():
    """Poll raw touch. Returns (any_press, toggle_hit_x_or_None)."""
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
    cmd("dim=100")               # full brightness on start
    time.sleep(0.1)
    s.reset_input_buffer()
    draw_static()

    prev = [None] * 6
    last_sec = -1
    last_toggle = 0.0
    last_sendxy = time.time()
    last_activity = time.time()
    asleep = False
    bx, vx, BALLY, BALLR = 24, 9, 166, 14
    last_ball = time.time()

    while True:
        any_press, btn_x = poll_touch()
        t = time.time()
        if any_press:
            last_activity = t

        if t - last_sendxy > 2.0:            # keep raw touch alive (even while asleep)
            last_sendxy = t
            cmd("sendxy=1")

        # ---- asleep: dark screen, wait for a touch to wake ----
        if asleep:
            if any_press:                    # wake (this tap only wakes; no toggle)
                asleep = False
                cmd("dim=100")
                last_sec = -1                # refresh the clock immediately
                print("wake", flush=True)
            time.sleep(0.03)
            continue

        # ---- go to sleep after inactivity ----
        if t - last_activity > SLEEP_AFTER:
            asleep = True
            print("sleep", flush=True)
            for d in (70, 45, 22, 0):        # gentle fade to off
                cmd(f"dim={d}")
                time.sleep(0.06)
            continue

        # ---- awake: normal demo ----
        if btn_x is not None and t - last_toggle > 0.4:
            last_toggle = t
            want12 = btn_x >= TG_MID
            if want12 != mode12:
                mode12 = want12
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

        if t - last_ball > 0.11:
            last_ball = t
            cmd(f"fill {bx - BALLR},{BALLY - BALLR},{2 * BALLR},{2 * BALLR},{BG}")
            bx += vx
            if bx <= BALLR + 2 or bx >= 480 - BALLR - 2:
                vx = -vx
                bx += vx
            # fill square (proven primitive) instead of cirs, which won't render here
            cmd(f"fill {bx - BALLR},{BALLY - BALLR},{2 * BALLR},{2 * BALLR},{BALLC}")

        time.sleep(0.02)


if __name__ == "__main__":
    main()
