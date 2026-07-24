#!/usr/bin/env python3
"""Diagnostic: send whmi-wri and dump the board's RAW reply (to see why no 0x05).
Does NOT send file data -- if 0x05 appears we stop (board would be mid-erase)."""
import time

import serial

PORT, TERM = "/dev/serial0", b"\xff\xff\xff"
SIZE = 696787

s = serial.Serial(PORT, 9600, timeout=0.3)
s.write(TERM + b"connect" + TERM)
s.flush()
time.sleep(0.3)
print("comok:", s.read(128))

s.reset_input_buffer()
cmd = f"whmi-wri {SIZE},9600,0".encode()
s.write(cmd + TERM)
s.flush()
print("sent:", cmd)

end = time.time() + 3
buf = b""
while time.time() < end:
    b = s.read(64)
    if b:
        buf += b
print("reply hex :", buf.hex(" "))
print("reply repr:", buf)
print("0x05 present:", b"\x05" in buf)
s.close()
