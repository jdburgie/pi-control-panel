#!/usr/bin/env python3
"""After flashing a .tft with a font: confirm comms + that xstr text renders.
bkcmd=1 so we can read per-command acks (0x01 ok, 0x00 invalid, 0x23 invalid font)."""
import time

import serial

TERM = b"\xff\xff\xff"
s = serial.Serial("/dev/serial0", 9600, timeout=0.4)


def cmd(c, wait=0.08):
    s.write(c.encode() + TERM)
    s.flush()
    time.sleep(wait)


# handshake
s.write(TERM + b"connect" + TERM)
s.flush()
time.sleep(0.3)
print("comok:", s.read(128))

s.reset_input_buffer()
cmd("bkcmd=1")
cmd("cls 2146")                       # dark background

# try xstr with font id 0 and id 1 (whichever the .tft has)
for fid in (0, 1):
    s.reset_input_buffer()
    cmd(f'xstr 20,{60 + fid*70},440,56,{fid},65535,2146,1,1,1,"Font {fid}: Hello 12:34"')
    time.sleep(0.2)
    print(f"xstr font{fid} ack:", s.read(16))

s.close()
print("done")
