#!/usr/bin/env python3
"""Poll the Nextion's tch0/tch1 (last touch x/y) system variables while the user
presses the screen. Tells us whether the touch controller reads real positions
at all -- independent of the sendxy stream (which is reporting 0,0)."""
import time

import serial

TERM = b"\xff\xff\xff"
s = serial.Serial("/dev/serial0", 9600, timeout=0.4)


def get(var):
    s.reset_input_buffer()
    s.write(f"get {var}".encode() + TERM)
    s.flush()
    time.sleep(0.18)
    r = s.read(16)
    # number response: 0x71 <4-byte LE> FF FF FF
    if len(r) >= 8 and r[0] == 0x71:
        return int.from_bytes(r[1:5], "little")
    return f"raw={r!r}"


s.write(b"bkcmd=1" + TERM)
s.flush()
time.sleep(0.2)
s.reset_input_buffer()

print("polling tch0/tch1 for 20s -- PRESS AND HOLD different spots (corners, centre)")
end = time.time() + 20
last = None
while time.time() < end:
    x, y = get("tch0"), get("tch1")
    if (x, y) != last:
        last = (x, y)
        print(f"  tch0(x)={x}  tch1(y)={y}", flush=True)
    time.sleep(0.25)
print("done")
s.close()
