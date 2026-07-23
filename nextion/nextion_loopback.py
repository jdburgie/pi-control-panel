#!/usr/bin/env python3
"""Pi UART self-test: with pin 8 (TXD) jumpered to pin 10 (RXD), whatever we
write should come straight back. Proves the Pi's serial TX+RX independent of the
Nextion. Run after jumpering pin 8 <-> pin 10 (Nextion data wires removed)."""
import time

import serial

for baud in (9600, 115200):
    s = serial.Serial("/dev/serial0", baud, timeout=1)
    s.reset_input_buffer()
    msg = f"LOOPBACK-{baud}-abc123".encode()
    s.write(msg)
    s.flush()
    time.sleep(0.3)
    back = s.read(len(msg) + 4)
    s.close()
    ok = msg in back
    print(f"{baud:>6}: sent {msg!r}  read {back!r}  -> {'PASS' if ok else 'FAIL'}")
