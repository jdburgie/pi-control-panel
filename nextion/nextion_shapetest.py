#!/usr/bin/env python3
"""Does cirs (filled circle) render on this board? Red square = known-good fill
control; green circle = the cirs test."""
import time

import serial

TERM = b"\xff\xff\xff"
s = serial.Serial("/dev/serial0", 9600, timeout=0.3)


def c(cmd):
    s.write(cmd.encode() + TERM)
    s.flush()
    time.sleep(0.06)


c("cls 2146")                    # dark background
c("fill 60,96,90,90,63488")      # RED SQUARE  (fill = known good)
c("cirs 320,141,46,2016")        # GREEN CIRCLE (cirs = test)
c("cir 320,141,46,65535")        # white outline around it
time.sleep(0.3)
s.close()
print("done — expect: red square left, green filled circle right")
