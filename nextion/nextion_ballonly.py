#!/usr/bin/env python3
"""Ball test v2 — adds a small per-command delay (the shape test that worked did
this). Draws two stationary circles (should persist) then a bouncing green ball."""
import time

import serial

TERM = b"\xff\xff\xff"
s = serial.Serial("/dev/serial0", 9600, timeout=0)


def cmd(c):
    s.write(c.encode() + TERM)
    s.flush()
    time.sleep(0.05)          # give the Nextion time to process each command


cmd("cls 2146")
cmd("cirs 100,140,30,63488")   # stationary RED (left)
cmd("cirs 380,140,30,2016")    # stationary GREEN (right)
time.sleep(1.0)

bx, vx, by, r = 24, 10, 210, 16
last = time.time()
end = time.time() + 9
while time.time() < end:
    if time.time() - last > 0.12:
        last = time.time()
        cmd(f"fill {bx - r},{by - r},{2 * r},{2 * r},2146")
        bx += vx
        if bx <= r + 2 or bx >= 480 - r - 2:
            vx = -vx
            bx += vx
        cmd(f"cirs {bx},{by},{r},2016")
    time.sleep(0.02)

print("done")
s.close()
