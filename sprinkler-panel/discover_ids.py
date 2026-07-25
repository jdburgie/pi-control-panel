#!/usr/bin/env python3
"""Map Nextion component IDs to names by tapping each button once.

The 0x65 touch event reports (page#, componentId) but not the name, so rather than
copying ~30 numeric ids out of the Editor by hand, this walks you through the panel:
it switches to each page, prompts for each button, and records what you tap.

Writes component_map.json next to this script — the driver reads that.

Run it on the Pi with a TTY, after stopping anything else using the serial port:
    sudo systemctl stop nextion-demo.service
    python3 ~/sprinkler-panel/discover_ids.py
"""
import json
import os
import sys
import time

import serial

TERM = b"\xff\xff\xff"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "component_map.json")

# page -> buttons, in the order you'll be asked to tap them
LAYOUT = [
    ("status", ["bStop", "bZones", "bProg", "bRain"]),
    ("zones", [f"bZ{i}" for i in range(1, 10)] + ["bBack"]),
    ("run", ["bM5", "bM1", "bP1", "bP5", "bStart", "bBack"]),
    ("confirm", ["bYes", "bNo"]),
    ("program", ["bRunA", "bRunB", "bClrQ", "bBack"]),
    ("rain", ["bR6", "bR12", "bR24", "bRClr", "bBack"]),
]

s = serial.Serial("/dev/serial0", 9600, timeout=0)
buf = bytearray()


def cmd(c):
    s.write(c.encode() + TERM)
    s.flush()


def next_touch(timeout=30):
    """Wait for one 0x65 release event -> (page, comp_id). None on timeout."""
    end = time.time() + timeout
    while time.time() < end:
        n = s.in_waiting
        if n:
            buf.extend(s.read(n))
        while len(buf) >= 7:
            if buf[0] == 0x65 and buf[4] == 0xFF and buf[5] == 0xFF and buf[6] == 0xFF:
                page, comp, ev = buf[1], buf[2], buf[3]
                del buf[:7]
                if ev == 0:                       # release
                    return page, comp
            else:
                del buf[:1]
        time.sleep(0.02)
    return None


def main():
    cmd("bkcmd=0")
    cmd("sendxy=0")          # we want component events, not raw coords
    time.sleep(0.2)

    mapping = {}
    print("Tap each button as prompted. Ctrl-C to abort, 's' + Enter to skip one.\n")

    for page, buttons in LAYOUT:
        cmd(f"page {page}")
        time.sleep(0.6)
        s.reset_input_buffer()
        buf.clear()
        print(f"--- page '{page}' ---")
        for name in buttons:
            print(f"  tap {name} ... ", end="", flush=True)
            hit = next_touch()
            if hit is None:
                print("timeout, skipped")
                continue
            pg, comp = hit
            mapping[f"{pg}:{comp}"] = {"page": page, "name": name}
            print(f"page={pg} id={comp}")
            time.sleep(0.35)                      # debounce before the next prompt

    with open(OUT, "w") as f:
        json.dump(mapping, f, indent=2, sort_keys=True)
    print(f"\nwrote {OUT}  ({len(mapping)} components)")
    cmd("page status")
    s.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\naborted")
        sys.exit(1)
