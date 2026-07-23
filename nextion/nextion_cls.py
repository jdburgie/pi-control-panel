#!/usr/bin/env python3
"""One-way test: flood the Nextion screen with solid colors so we can confirm the
Pi->Nextion direction works even if the return line doesn't. Usage: nextion_cls.py [baud]"""
import sys
import time

import serial

baud = int(sys.argv[1]) if len(sys.argv) > 1 else 9600
TERM = b"\xff\xff\xff"
s = serial.Serial("/dev/serial0", baud, timeout=0.5)


def cmd(text):
    s.write(text.encode())
    s.write(TERM)
    s.flush()


print(f"Sending cls color sweep at {baud} baud...")
for color, name in [(63488, "RED"), (2016, "GREEN"), (31, "BLUE"), (65535, "WHITE")]:
    cmd(f"cls {color}")
    print(f"  sent: cls {name}")
    time.sleep(2.5)
s.close()
print("done")
