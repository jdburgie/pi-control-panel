#!/usr/bin/env python3
"""Paint a demo/test screen on the Nextion (480x272) with runtime drawing
commands. No .tft needed. Colors are RGB565."""
import time

import serial

TERM = b"\xff\xff\xff"
s = serial.Serial("/dev/serial0", 9600, timeout=0.5)


def cmd(c):
    s.write(c.encode())
    s.write(TERM)
    s.flush()
    time.sleep(0.08)


# palette (RGB565)
GREEN = 11049      # ~ #2C654B  Three Oak Woods green
WHITE = 65535
BLACK = 0
RED = 63488
GRN = 2016
BLUE = 31
YELLOW = 65504
MAGENTA = 63519
CYAN = 2047

cmd("bkcmd=1")
cmd(f"cls {BLACK}")

# title bar + text
cmd(f"fill 0,0,480,44,{GREEN}")
cmd(f'xstr 0,0,480,44,0,{WHITE},{GREEN},1,1,1,"Pi Zero  ->  Nextion"')

# four colour swatches
cmd(f"fill 20,70,100,60,{RED}")
cmd(f"fill 140,70,100,60,{GRN}")
cmd(f"fill 260,70,100,60,{BLUE}")
cmd(f"fill 380,70,80,60,{YELLOW}")

# separator + circles
cmd(f"line 20,150,460,150,{WHITE}")
cmd(f"cir 110,210,38,{MAGENTA}")
cmd(f"cirs 250,210,38,{CYAN}")
cmd(f"cir 390,210,38,{YELLOW}")

# status line
cmd(f'xstr 0,250,480,22,0,{WHITE},{GREEN},1,1,1,"Serial OK @ 9600 baud"')

time.sleep(0.3)
resp = s.read(200)
s.close()
print("done. residual bytes:", resp)
