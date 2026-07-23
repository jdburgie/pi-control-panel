#!/usr/bin/env python3
"""Send a distinct solid color (cls) at each candidate baud. The color left on the
screen identifies the Nextion's real baud. Screen staying unchanged = wiring issue."""
import time

import serial

TERM = b"\xff\xff\xff"
# (baud, color name, RGB565)
STEPS = [
    (9600, "RED", 63488),
    (115200, "GREEN", 2016),
    (57600, "BLUE", 31),
    (38400, "YELLOW", 65504),
    (19200, "MAGENTA", 63519),
    (4800, "CYAN", 2047),
]

for baud, name, color in STEPS:
    try:
        s = serial.Serial("/dev/serial0", baud, timeout=0.4)
    except Exception as e:
        print(f"  {baud}: open-fail {e}")
        continue
    # settle, wake, clear to this baud's color
    time.sleep(0.1)
    s.write(TERM)
    s.write(f"cls {color}".encode())
    s.write(TERM)
    s.flush()
    print(f"  {baud:>6} -> {name}")
    time.sleep(4)
    s.close()

print("done — tell me the final color on screen (or 'nothing')")
