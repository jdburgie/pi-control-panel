#!/usr/bin/env python3
"""Detect a Nextion display on /dev/serial0: sweep bauds, send the `connect`
handshake, and print whatever comes back (a healthy board replies `comok ...`)."""
import time

import serial

PORT = "/dev/serial0"
TERM = b"\xff\xff\xff"
BAUDS = [9600, 115200, 57600, 38400, 19200, 4800, 2400, 921600, 250000]


def probe(baud):
    try:
        s = serial.Serial(PORT, baud, timeout=0.6)
    except Exception as e:
        return f"open-fail: {e}"
    try:
        time.sleep(0.1)
        s.reset_input_buffer()
        # nudge, then the documented connect handshake
        s.write(TERM)
        s.write(b"connect")
        s.write(TERM)
        s.flush()
        time.sleep(0.4)
        data = s.read(256)
        return data
    finally:
        s.close()


print(f"Probing {PORT} ...")
hit = None
for b in BAUDS:
    resp = probe(b)
    if isinstance(resp, bytes):
        ascii_ = resp.decode("ascii", "replace")
        print(f"  {b:>7}: {resp!r}")
        if b"comok" in resp and hit is None:
            hit = (b, ascii_)
    else:
        print(f"  {b:>7}: {resp}")

print()
if hit:
    print(f"==> Nextion responding at {hit[0]} baud")
    print(f"    comok: {hit[1].strip()}")
else:
    print("==> No `comok` reply at any baud.")
    print("    Check wiring (Pi TXD pin8 -> Nextion RX, Nextion TX -> Pi RXD pin10),")
    print("    the board's configured baud, and Nextion TX logic level (must be 3.3V).")
