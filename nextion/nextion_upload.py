#!/usr/bin/env python3
"""Upload a Nextion .tft to the display over the Pi's serial link -- no SD card.

Auto-detects the TFT format and uses the matching upload protocol:
  - newer `DNxE` files -> v1.2 (`whmi-wris`, handles the 0x08 skip-offset acks)
  - classic files      -> v1.0 (`whmi-wri`, plain 0x05 acks)
Flow: connect -> comok, send the upload command, switch to <baud>, wait for 0x05,
stream the file in 4096-byte chunks, device reboots into the new project.

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

    data = open(path, "rb").read()
    v12 = b"DNxE" in data[:16]        # newer TFT format -> v1.2 upload protocol
    cmd = "whmi-wris" if v12 else "whmi-wri"
    flag = 1 if v12 else 0
    print(f"protocol: {'v1.2 (whmi-wris)' if v12 else 'v1.0 (whmi-wri)'}")

    # send the upload command at the current baud, THEN switch baud
    s.reset_input_buffer()
    s.write(TERM + f"{cmd} {size},{up_baud},{flag}".encode() + TERM)
    s.flush()
    time.sleep(0.1)
    s.baudrate = up_baud
    time.sleep(0.2)

    if read_byte(s, 3) != b"\x05":
        sys.exit("device did not become ready (no 0x05). The bootloader may not "
                 "support this .tft format, or the model/baud is wrong.")

    pos = 0
    while pos < size:
        chunk = data[pos:pos + CHUNK]
        s.write(chunk)
        s.flush()
        pos += len(chunk)
        resp = read_byte(s, 10)
        if resp == b"\x05":
            pass                                  # send next block
        elif resp == b"\x08":                     # v1.2 skip: seek to given offset
            off = s.read(4)
            if len(off) == 4:
                skip = int.from_bytes(off, "little")
                if skip:
                    pos = skip
        else:
            sys.exit(f"\nno ack after {pos}/{size} bytes (got {resp!r})")
        print(f"\r  {pos}/{size}  ({100 * pos // size}%)", end="", flush=True)

    print("\ndone -- the Nextion reboots into the new project.")
    s.close()


if __name__ == "__main__":
    main()
