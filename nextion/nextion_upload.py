#!/usr/bin/env python3
"""Upload a Nextion .tft to the display over the Pi's serial link -- no SD card.

Implements the classic Nextion `whmi-wri` upload protocol:
  connect -> comok, then `whmi-wri <size>,<baud>,0`, switch to <baud>, wait for
  0x05, stream the file in 4096-byte chunks (0x05 ack after each), device reboots.

Requirements:
  - a project must already be loaded on the display (a blank board won't answer serial)
  - nothing else may hold /dev/serial0 -> stop the demo first:
        sudo systemctl stop nextion-demo.service
  - the .tft must be compiled for THIS model (NX4827T043, 480x272) in Nextion Editor

Usage:  python3 nextion_upload.py <file.tft> [upload_baud]      # default baud 115200
"""
import os
import sys
import time

import serial

PORT = "/dev/serial0"
CUR_BAUD = 9600          # the display's normal running baud
TERM = b"\xff\xff\xff"
CHUNK = 4096


def read_byte(s, timeout):
    end = time.time() + timeout
    while time.time() < end:
        b = s.read(1)
        if b:
            return b
    return b""


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python3 nextion_upload.py <file.tft> [upload_baud]")
    path = sys.argv[1]
    up_baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200
    if not os.path.isfile(path):
        sys.exit(f"no such file: {path}")
    if not path.lower().endswith(".tft"):
        print("! warning: file does not end in .tft")
    size = os.path.getsize(path)
    print(f"uploading {path}  ({size} bytes)  at {up_baud} baud")

    try:
        s = serial.Serial(PORT, CUR_BAUD, timeout=1)
    except serial.SerialException as e:
        sys.exit(f"cannot open {PORT}: {e}\n"
                 f"-> stop the demo first:  sudo systemctl stop nextion-demo.service")

    # handshake -- confirms a project is loaded and the board is listening
    s.reset_input_buffer()
    s.write(TERM + b"connect" + TERM)
    s.flush()
    time.sleep(0.3)
    resp = s.read(128)
    if b"comok" in resp:
        print("handshake OK:", resp.split(b"\xff")[0].decode("ascii", "replace").strip())
    else:
        print("! no comok reply -- is a project loaded? trying the upload anyway...")

    # begin transfer (send command at current baud, THEN switch baud)
    s.reset_input_buffer()
    s.write(TERM + f"whmi-wri {size},{up_baud},0".encode() + TERM)
    s.flush()
    time.sleep(0.1)
    s.baudrate = up_baud
    time.sleep(0.2)

    if read_byte(s, 2) != b"\x05":
        sys.exit("device did not become ready (no 0x05 after whmi-wri). "
                 "Check the model/baud and that a project is loaded.")

    sent = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            s.write(chunk)
            s.flush()
            sent += len(chunk)
            ack = read_byte(s, 8)
            if ack != b"\x05":
                sys.exit(f"\nno ack (0x05) after {sent}/{size} bytes (got {ack!r})")
            print(f"\r  {sent}/{size}  ({100 * sent // size}%)", end="", flush=True)

    print("\ndone -- the Nextion reboots into the new project.")
    s.close()


if __name__ == "__main__":
    main()
