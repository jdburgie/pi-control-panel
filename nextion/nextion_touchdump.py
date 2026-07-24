#!/usr/bin/env python3
"""Dump every byte the Nextion sends while touched. Sets sendxy=1 and prints all
RX as hex (also to /tmp/touchdump.log so a dropped SSH doesn't lose it)."""
import sys
import time

import serial

PORT, TERM = "/dev/serial0", b"\xff\xff\xff"
dur = int(sys.argv[1]) if len(sys.argv) > 1 else 30

s = serial.Serial(PORT, 9600, timeout=0.2)
s.write(b"bkcmd=0" + TERM)
s.write(b"sendxy=1" + TERM)
s.flush()
time.sleep(0.2)
s.reset_input_buffer()

log = open("/tmp/touchdump.log", "w")


def out(m):
    print(m, flush=True)
    log.write(m + "\n")
    log.flush()


out(f"listening {dur}s @ 9600, sendxy=1 -- PRESS FIRMLY + DRAG ALL OVER")
end = time.time() + dur
total = 0
while time.time() < end:
    n = s.in_waiting
    if n:
        d = s.read(n)
        total += len(d)
        out("RX " + d.hex(" "))
    time.sleep(0.04)
out(f"done, {total} bytes received")
s.close()
log.close()
