#!/usr/bin/env python3
"""Sprinkler control panel on the Nextion NX4827T043 (480x272), driven from the Pi.

Talks to the ESP32 sprinkler controller over HTTP and renders multi-view UI with
runtime drawing commands (no .tft rebuild needed to change layout).

Views: STATUS -> ZONES -> RUN -> CONFIRM, plus PROGRAM and RAIN.

Safety:
  * every action that can open a valve (zone start, program start) goes through
    an explicit confirm view
  * STOP is always one tap, never confirmed
  * --no-actuate logs POSTs instead of sending them (for development)

Usage: sprinkler_panel.py [--no-actuate]
"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

import serial

# ---------------------------------------------------------------- config -----
SPRINKLER = "http://192.168.12.52"
PORT, BAUD = "/dev/serial0", 9600
POLL_SEC = 2.0                 # status refresh
SLEEP_AFTER = 90               # backlight off after this many idle seconds
HTTP_TIMEOUT = 3
MIN_MIN, MAX_MIN = 1, 59       # firmware limits
NO_ACTUATE = "--no-actuate" in sys.argv

W, H = 480, 272
FONT_SM, FONT_BIG = 0, 1

# palette (RGB565)
BG = 2146
CARD = 8584
GREEN = 11049
AMBER = 52261
RED = 63488
WHITE = 65535
LIGHT = 50712
GREY = 16904
CYAN = 2047

TERM = b"\xff\xff\xff"
ser = serial.Serial(PORT, BAUD, timeout=0)


def cmd(c):
    ser.write(c.encode() + TERM)
    ser.flush()


def esc(s):
    """Nextion strings are double-quoted; strip chars that would break them."""
    return str(s).replace('"', "").replace("\\", "")


def text(x, y, w, h, fid, fg, bg, s, xc=1, yc=1):
    cmd(f'xstr {x},{y},{w},{h},{fid},{fg},{bg},{xc},{yc},1,"{esc(s)}"')


def fill(x, y, w, h, c):
    cmd(f"fill {x},{y},{w},{h},{c}")


def trunc(s, n):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "."


# ------------------------------------------------------------------ api ------
class Api:
    """Sprinkler HTTP client. Status is polled on a thread so the UI never blocks."""

    def __init__(self):
        self.status = {}
        self.zones = []
        self.programs = []
        self.online = False
        self.last_error = ""
        self._lock = threading.Lock()

    def _get(self, path):
        with urllib.request.urlopen(SPRINKLER + path, timeout=HTTP_TIMEOUT) as r:
            return json.loads(r.read().decode())

    def post(self, path, obj=None):
        """Returns (ok, message). Honours --no-actuate."""
        if NO_ACTUATE:
            print(f"[no-actuate] POST {path} {obj}", flush=True)
            return True, "dry run"
        data = json.dumps(obj or {}).encode()
        req = urllib.request.Request(
            SPRINKLER + path, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
                print(f"POST {path} {obj} -> {r.status}", flush=True)
                return True, "ok"
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:80]
            print(f"POST {path} failed {e.code}: {body}", flush=True)
            return False, f"HTTP {e.code}"
        except Exception as e:
            print(f"POST {path} failed: {e}", flush=True)
            return False, "no reply"

    def load_config(self):
        try:
            c = self._get("/api/config")
            with self._lock:
                self.zones = [
                    {"id": z.get("id", i + 1),
                     "name": z.get("name", f"Zone {i+1}"),
                     "duration": z.get("duration", 10)}
                    for i, z in enumerate(c.get("zones", []))
                ]
                self.programs = sorted((c.get("programs") or {}).keys())
            return True
        except Exception as e:
            self.last_error = str(e)[:40]
            return False

    def poll_forever(self):
        while True:
            try:
                s = self._get("/api/status")
                with self._lock:
                    self.status = s
                    self.online = True
            except Exception as e:
                with self._lock:
                    self.online = False
                    self.last_error = str(e)[:40]
            if not self.zones:
                self.load_config()
            time.sleep(POLL_SEC)

    def snap(self):
        with self._lock:
            return dict(self.status), self.online, list(self.zones), list(self.programs)


api = Api()

# ------------------------------------------------------------------ ui -------
NAV_Y, NAV_H = 234, 34
CONTENT_Y = 32

view = "status"
sel_zone = None          # dict from api.zones
sel_min = 10
pending = None           # (label, fn) awaiting confirmation
toast = ""
toast_until = 0.0
buttons = []             # [{rect,label,fn,bg,fg,font}]
dirty = True


def note(msg, secs=2.5):
    global toast, toast_until, dirty
    toast, toast_until = msg, time.time() + secs
    dirty = True


def go(v):
    global view, dirty
    view, dirty = v, True


def button(x, y, w, h, label, fn, bg=CARD, fg=WHITE, font=FONT_SM):
    buttons.append({"rect": (x, y, w, h), "label": label, "fn": fn,
                    "bg": bg, "fg": fg, "font": font})


def draw_buttons():
    for b in buttons:
        x, y, w, h = b["rect"]
        fill(x, y, w, h, b["bg"])
        text(x + 4, y + 3, w - 8, h - 6, b["font"], b["fg"], b["bg"], b["label"])


def header(title, st, online):
    fill(0, 0, W, 28, GREEN)
    text(6, 1, 300, 26, FONT_SM, WHITE, GREEN, title, xc=0)
    right = st.get("time", "")[11:16] if online else "OFFLINE"
    text(W - 130, 1, 124, 26, FONT_SM, WHITE if online else AMBER, GREEN, right)


def mmss(sec):
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def confirm(label, fn):
    global pending
    pending = (label, fn)
    go("confirm")


# ---- actions (each returns nothing; they post and bounce back to status) ----
def act_start_zone():
    ok, msg = api.post("/api/manual/start",
                       {"zone": sel_zone["id"], "durationMinutes": sel_min,
                        "ignoreRain": False})
    note(f"Started {trunc(sel_zone['name'], 14)}" if ok else f"Failed: {msg}")
    go("status")


def act_stop():
    ok, msg = api.post("/api/manual/stop")
    note("Stopped" if ok else f"Failed: {msg}")
    go("status")


def act_program(p):
    def run():
        ok, msg = api.post("/api/program/start", {"program": p})
        note(f"Program {p} started" if ok else f"Failed: {msg}")
        go("status")
    return lambda: confirm(f"Run program {p} now?", run)


def act_clear_queue():
    ok, msg = api.post("/api/queue/clear")
    note("Queue cleared" if ok else f"Failed: {msg}")
    go("status")


def act_rain(hours):
    def fn():
        ok, msg = api.post("/api/rain-delay", {"hours": hours})
        note((f"Rain delay {hours}h" if hours else "Rain delay cleared")
             if ok else f"Failed: {msg}")
        go("status")
    return fn


# ------------------------------------------------------------- views ---------
def build_status(st, online, zones):
    running = bool(st.get("running"))
    fill(0, CONTENT_Y, W, NAV_Y - CONTENT_Y, BG)

    if not online:
        text(0, 90, W, 40, FONT_BIG, AMBER, BG, "controller offline")
        text(0, 140, W, 24, FONT_SM, LIGHT, BG, trunc(api.last_error, 40))
    elif running:
        text(0, 40, W, 30, FONT_SM, LIGHT, BG, "WATERING")
        text(0, 68, W, 46, FONT_BIG, WHITE, BG,
             trunc(st.get("activeZoneName") or "?", 24))
        text(0, 118, W, 44, FONT_BIG, AMBER, BG, mmss(st.get("remainingSec", 0)))
        button(300, 168, 174, 52, "STOP", act_stop, bg=RED, fg=WHITE)
    else:
        text(0, 52, W, 46, FONT_BIG, GREEN, BG, "IDLE")

    if online:
        q = st.get("queueDepth", 0)
        rain = st.get("rainLockedOut") or st.get("rainSensorWet")
        info = f"{st.get('dailyWateredMin', 0)}/{st.get('dailyBudgetMin', 0)} min today"
        if q:
            info += f"   queue {q}"
        text(6, 196, 288 if running else W - 12, 24, FONT_SM, LIGHT, BG, info, xc=0)
        if rain:
            text(6, 168, 288, 24, FONT_SM, CYAN, BG, "RAIN LOCKOUT", xc=0)

    bw = (W - 24) // 3
    button(6, NAV_Y, bw, NAV_H, "ZONES", lambda: go("zones"), bg=GREEN)
    button(12 + bw, NAV_Y, bw, NAV_H, "PROGRAM", lambda: go("program"), bg=CARD)
    button(18 + 2 * bw, NAV_Y, bw, NAV_H, "RAIN", lambda: go("rain"), bg=CARD)


def build_zones(zones):
    fill(0, CONTENT_Y, W, NAV_Y - CONTENT_Y, BG)
    if not zones:
        text(0, 110, W, 30, FONT_SM, AMBER, BG, "no zone list yet")
    for i, z in enumerate(zones[:10]):
        col, row = i // 5, i % 5
        x = 6 + col * 237
        y = CONTENT_Y + 2 + row * 39
        button(x, y, 231, 36, trunc(z["name"], 17), _pick(z), bg=CARD)
    button(6, NAV_Y, 140, NAV_H, "BACK", lambda: go("status"), bg=GREY)


def _pick(z):
    def fn():
        global sel_zone, sel_min
        sel_zone = z
        sel_min = max(MIN_MIN, min(MAX_MIN, int(z.get("duration") or 10)))
        go("run")
    return fn


def build_run():
    fill(0, CONTENT_Y, W, NAV_Y - CONTENT_Y, BG)
    text(0, 36, W, 26, FONT_SM, LIGHT, BG, trunc(sel_zone["name"], 30))
    text(0, 66, W, 52, FONT_BIG, AMBER, BG, f"{sel_min} min")

    for i, (lbl, d) in enumerate((("-5", -5), ("-1", -1), ("+1", 1), ("+5", 5))):
        button(30 + i * 108, 124, 96, 44, lbl, _adj(d), bg=CARD)

    button(120, 178, 240, 48, "START",
           lambda: confirm(f"Water {trunc(sel_zone['name'], 16)} {sel_min} min?",
                           act_start_zone), bg=GREEN)
    button(6, NAV_Y, 140, NAV_H, "BACK", lambda: go("zones"), bg=GREY)


def _adj(d):
    def fn():
        global sel_min, dirty
        sel_min = max(MIN_MIN, min(MAX_MIN, sel_min + d))
        dirty = True
    return fn


def build_confirm():
    fill(0, CONTENT_Y, W, NAV_Y - CONTENT_Y, BG)
    text(10, 60, W - 20, 60, FONT_SM, WHITE, BG, pending[0])
    button(40, 140, 180, 60, "YES", pending[1], bg=GREEN)
    button(260, 140, 180, 60, "CANCEL", lambda: go("status"), bg=GREY)


def build_program(programs):
    fill(0, CONTENT_Y, W, NAV_Y - CONTENT_Y, BG)
    text(0, 36, W, 24, FONT_SM, LIGHT, BG, "Run a program now")
    for i, p in enumerate(programs[:3]):
        button(30 + i * 150, 70, 130, 60, f"RUN {p}", act_program(p), bg=GREEN)
    button(120, 150, 240, 48, "CLEAR QUEUE", act_clear_queue, bg=CARD)
    button(6, NAV_Y, 140, NAV_H, "BACK", lambda: go("status"), bg=GREY)


def build_rain(st):
    fill(0, CONTENT_Y, W, NAV_Y - CONTENT_Y, BG)
    wet = st.get("rainLockedOut") or st.get("rainSensorWet")
    text(0, 36, W, 24, FONT_SM, CYAN if wet else LIGHT, BG,
         "RAIN LOCKOUT ACTIVE" if wet else "Set a rain delay")
    for i, h in enumerate((6, 12, 24)):
        button(30 + i * 150, 70, 130, 60, f"{h}h", act_rain(h), bg=CARD)
    button(120, 150, 240, 48, "CLEAR DELAY", act_rain(0), bg=GREEN)
    button(6, NAV_Y, 140, NAV_H, "BACK", lambda: go("status"), bg=GREY)


def redraw():
    global buttons
    buttons = []
    st, online, zones, programs = api.snap()

    titles = {"status": st.get("controllerName") or "Sprinkler", "zones": "Select zone",
              "run": "Manual run", "confirm": "Confirm", "program": "Programs",
              "rain": "Rain delay"}
    header(titles.get(view, "Sprinkler"), st, online)

    if view == "status":
        build_status(st, online, zones)
    elif view == "zones":
        build_zones(zones)
    elif view == "run":
        build_run()
    elif view == "confirm":
        build_confirm()
    elif view == "program":
        build_program(programs)
    elif view == "rain":
        build_rain(st)

    fill(0, NAV_Y - 4, W, 3, GREY)
    draw_buttons()

    if toast and time.time() < toast_until:
        text(150, NAV_Y, W - 156, NAV_H, FONT_SM, AMBER, BG, toast)
    if NO_ACTUATE:
        text(W - 90, 30, 88, 20, FONT_SM, RED, BG, "DRY RUN")


# ---------------------------------------------------------------- touch ------
buf = bytearray()


def poll_touch():
    n = ser.in_waiting
    if n:
        buf.extend(ser.read(n))
    press = None
    any_press = False
    while len(buf) >= 9:
        if buf[0] == 0x67 and buf[6] == 0xFF and buf[7] == 0xFF and buf[8] == 0xFF:
            x = (buf[1] << 8) | buf[2]
            y = (buf[3] << 8) | buf[4]
            ev = buf[5]
            del buf[:9]
            if ev == 1:
                any_press = True
                press = (x, y)
        else:
            del buf[:1]
    return any_press, press


def hit(pt):
    x, y = pt
    for b in buttons:
        bx, by, bw, bh = b["rect"]
        if bx <= x <= bx + bw and by <= y <= by + bh:
            return b
    return None


# ----------------------------------------------------------------- main ------
def main():
    global dirty

    threading.Thread(target=api.poll_forever, daemon=True).start()

    cmd("bkcmd=0")
    cmd("sendxy=1")
    cmd("dim=100")
    time.sleep(0.2)
    ser.reset_input_buffer()
    cmd(f"cls {BG}")

    last_sendxy = last_activity = time.time()
    last_paint = 0.0
    last_sig = None
    asleep = False
    print(f"sprinkler panel up ({'DRY RUN' if NO_ACTUATE else 'live'})", flush=True)

    while True:
        any_press, pt = poll_touch()
        now = time.time()
        if any_press:
            last_activity = now

        if now - last_sendxy > 2.0:
            last_sendxy = now
            cmd("sendxy=1")

        if asleep:
            if any_press:
                asleep = False
                cmd("dim=100")
                go("status")
                print("wake", flush=True)
            time.sleep(0.03)
            continue

        if now - last_activity > SLEEP_AFTER:
            asleep = True
            print("sleep", flush=True)
            for d in (70, 45, 22, 0):
                cmd(f"dim={d}")
                time.sleep(0.05)
            continue

        if pt:
            b = hit(pt)
            print(f"touch {pt} -> {b['label'] if b else '-'}", flush=True)
            if b:
                b["fn"]()
                dirty = True

        # repaint when state changes, or at most ~2x/sec while watering
        st, online, _, _ = api.snap()
        sig = (view, online, st.get("running"), st.get("activeZone"),
               st.get("remainingSec"), st.get("queueDepth"),
               st.get("rainLockedOut"), sel_min,
               sel_zone["id"] if sel_zone else None,
               bool(toast and now < toast_until))
        if dirty or (sig != last_sig and now - last_paint > 0.45):
            last_sig, last_paint, dirty = sig, now, False
            redraw()

        time.sleep(0.03)


if __name__ == "__main__":
    main()
