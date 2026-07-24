# Pi Control Panel — JOURNAL

**Raspberry Pi Zero 2 W** (swapped 2026-07-23 from a Zero W v1.1 for stability), hostname
**RasPi0W**, `192.168.12.57` (user `pi`).
Three jobs run as systemd services: an **analog clock** on a Waveshare SPI LCD, a
**LAN monitoring web dashboard** (also on the PiTouch / Pi 5 at `.55`), and an
**animated Nextion demo** on a 4.3" serial HMI. Repo: `pi-control-panel`.

---

## Session log

### 2026-07-23 — Nextion bring-up, animated demo, repo created
- **Nextion NX4827T043_011R** (4.3" 480×272 resistive) brought up on the Pi UART
  (`/dev/serial0`, **9600 baud**). Long debug — root cause was a **floating GND** (wrong pin)
  plus the board not answering serial while blank/in "SD Card Update" mode. Pi UART proven
  via loopback (pin 8↔10). With a project loaded and GND fixed → `comok` handshake:
  `comok 1,67,NX4827T043_011R,0,11,...,16777216`.
- Wrote `nextion/` tools: `nextion_probe.py` (baud sweep + connect handshake),
  `nextion_loopback.py`, `nextion_cls.py`, `nextion_baudsweep.py`, `nextion_demo.py`
  (static shapes), and **`nextion_demo_clock.py`** — animated 7-segment clock (digits drawn
  from rectangles, no font needed) + intended bouncing ball + touch 24H/12H toggle. Running
  as `nextion-demo.service`. **Clock + title bar render great**; see Known issues for the
  ball + touch.
- **pi-monitor**: added auth-gated **Reboot/Shutdown** (`POST /api/power`, PBKDF2 hash in
  `power_auth`, scoped sudoers), dynamic hostname title, and cloned the identical dashboard
  to the **PiTouch (.55)** with the LCD-clock card auto-hidden.
- Fixed the SSH key ACL on Windows (owner-only) and disabled WiFi powersave on both Pis.
- **Created this git repo** (`pi-control-panel`) and pulled all running files into it.

### 2026-07-23 (later) — Nextion demo finished + Pi Zero 2 W swap
- **Nextion touch fixed.** `sendxy=1` *does* stream `0x67` packets (proved with
  `nextion_touchdump.py`) — the demo just wasn't keeping it asserted. Fix: **re-send
  `sendxy=1` every ~2s** in the loop + `flush()` each write. The 24H/12H toggle now works;
  touches log as `touch x=… y=… ev=…`.
- **Button redesigned** as a proper **segmented pill toggle** `[ 24 | 12 ]` (rounded via
  `fill`+`cirs`, active half amber) — tap a side to select. Tap-left→24H, tap-right→12H.
- **Animation fixed** — turns out **`cirs` (filled circle) does NOT render inside the fast
  redraw loop** on this board (works standalone + for the toggle's caps, but not repeated
  rapidly). Switched the "ball" to a **`fill` square** (rock-solid primitive); it bounces
  reliably. Round ball is a TODO if we ever want it (would need to chase the `cirs` quirk).
- **Swapped to the Pi Zero 2 W** (quad-core). Same SD/wiring; **kept IP .57**, hostname
  `RasPi0W`; all three services auto-started; **load ~1.8 vs ~7** — the SSH-drop/reboot
  instability is gone. (Note: the "nothing renders" ball tests on the old board were partly
  its overloaded CPU corrupting serial mid-write.)

---

## Todos

- [ ] **Sleep/dim mode for the Nextion** — a button or auto-timeout to dim the display
  (`dim=<0-100>`), with **wake-on-touch** back to full brightness.
- [ ] **Set the power password** on each Pi (Reboot/Shutdown buttons inert until then):
  `ssh -t pi@192.168.12.57 "cd ~/pi-monitor && python3 set_power_password.py"` and
  `ssh -t jdburgie@192.168.12.55 "cd ~/pi-monitor && python3 set_power_password.py"`
- [ ] Nextion **text/labels** need a font — build a proper `.tft` in Nextion Editor (Windows).
- [ ] (optional) make the bouncing square a round **ball** — needs the `cirs`-in-loop quirk
  solved, or approximate a circle with `fill` blocks.
- [ ] Clock SPI at a conservative 4 MHz; could try higher for snappier redraws.
- [x] **Pushed to GitHub** — *private* repo github.com/jdburgie/pi-control-panel (branch `master`)
- [x] **Pi Zero 2 W swap done** — header soldered, SD moved, stable, IP .57 kept
- [x] Nextion **touch** working; 24H/12H segmented toggle
- [x] Nextion **animation** working (bouncing `fill` square)
- [x] Nextion brought up + animated 7-seg clock driven from the Pi
- [x] Reboot/Shutdown controls behind auth
- [x] Dashboard cloned to the PiTouch
- [x] Git repo created

> **Nextion quirks (this board, driving from the Pi with runtime commands):** needs a project
> loaded to answer serial (blank = silent); `sendxy=1` for raw touch but must be re-asserted;
> `xstr` text needs a font in the loaded project; **`cirs` won't render in a fast loop** —
> use `fill`. GND must be solid or both serial directions die.

---

## Hardware

Pi Zero W drives **two displays at once** (different buses, no pin conflict):

### 1. Waveshare 1.47" SPI LCD module (ST7789-class, 172×320) — the analog clock
Bare panel, **no onboard MCU**. Header pins → Pi 40-pin:

| Panel | Pi pin | Function |
|-------|--------|----------|
| VCC   | 1      | 3.3V |
| GND   | 6      | Ground |
| DIN   | 19     | GPIO10 / MOSI |
| CLK   | 23     | GPIO11 / SCLK |
| CS    | 24     | GPIO8 / CE0 |
| DC    | 22     | GPIO25 |
| RST   | 13     | GPIO27 |
| BL    | 18     | GPIO24 |

### 2. Nextion-style HMI (ITEAD NX4827T043_011, 4.3", UART) — no software yet
4-pin connector → Pi:

| Nextion | Pi pin | Function |
|---------|--------|----------|
| GND     | 9      | Ground |
| RX      | 8      | GPIO14 / TXD (Pi→Nextion) |
| TX      | 10     | GPIO15 / RXD (Nextion→Pi) |
| +5V     | 2      | 5V |

⚠ Before trusting the Nextion TX→Pi RXD line, confirm the board's UART logic is 3.3V
(Pi GPIO is **not** 5V-tolerant). Level-shift if it's 5V.

---

## System configuration changes (in `/boot/firmware/`, backups `*.bak`)

- `config.txt`: `dtparam=spi=on`, `enable_uart=1`, `dtoverlay=disable-bt`
  - disable-bt frees the good PL011 UART onto GPIO14/15 (instead of the flaky mini-UART).
- `cmdline.txt`: removed `console=serial0,115200` so the Nextion owns the UART, not a login console.
- Result: `/dev/spidev0.0`, `/dev/spidev0.1`, and `/dev/serial0 → ttyAMA0`.

### WiFi power-save DISABLED (important)
Pi Zero W was intermittently dropping SSH mid-command (exit 255 on longer commands).
Fix via NetworkManager (Debian 13 / trixie):
- `/etc/NetworkManager/conf.d/wifi-powersave.conf` → `[connection]\nwifi.powersave = 2`
- also `nmcli c modify "<active>" 802-11-wireless.powersave 2`
`iw` is NOT installed here; use nmcli.

### SSH
Key-based auth set up 2026-07-23. Private key `~/.ssh/id_ed25519` on the Windows PC.
Gotcha: `ssh-copy-id` / the Windows `type | ssh >> authorized_keys` fallback produced an
**empty** authorized_keys — had to `echo "<pubkey>" >> ~/.ssh/authorized_keys` on the Pi.
(Separately, Windows OpenSSH refused the key until its ACL was tightened to owner-only via
`icacls ... /inheritance:r /grant:r "<user>:F"` — an orphaned SID had access.)

---

## Clock — `/home/pi/lcd-clock/`

- `venv/` — `st7789`, `pillow`, `spidev` (+ numpy). **Needed `sudo apt install libopenblas0`**
  (numpy import fails with `libopenblas.so.0: cannot open shared object file` otherwise).
- `clock.py` — landscape (320×172) face-left / digital-time-right layout, 1 Hz redraw.
- Driver: Pimoroni `st7789` 1.0.1 (uses libgpiod v2 / `gpiodevice`).

### Display quirks (hard-won)
1. **Screen stayed black** until the **hardware reset pin is pulsed**. The library's `_init()`
   only does a *software* SWRESET and never calls `reset()`. Workaround in code: after
   construction, call `disp.reset()` then `disp._init()`.
2. **Offset / coverage:** panel is 172 wide inside a 240-wide GRAM → `offset_left=34`.
   The driver hardcodes `MADCTL=0x70` (for square 240×240 displays); override to **`0x00`**
   (send cmd `0x36`, data `0x00`) or the image lands shifted with garbage on the sides.
3. **Orientation:** the panel's net transform **mirrors horizontally** (text came out
   backwards). Deterministic fix in `to_panel()`: pre-flip the landscape canvas
   `FLIP_LEFT_RIGHT`, then `rotate(270)` into the portrait frame, then `FLIP_TOP_BOTTOM`.
   Chasing MADCTL bits was unreliable on this panel; software transforms are deterministic.

---

## Monitor dashboard — `/home/pi/pi-monitor/`

- `server.py` — **pure Python stdlib** (`http.server`), no deps. Threaded, port 8080, binds
  0.0.0.0. Quiet logging.
- `logo.svg`, `favicon.ico` — Three Oak Woods badge, copied from the home-hub at .131.

### Routes
- `/` — auto-refreshing (3s) dashboard.
- `/api/stats` — JSON: hostname, model, kernel, ip, uptime, loadavg, cpu% (delta of
  /proc/stat), cpu temp, cpu freq, mem, disk, wifi (signal dBm + SSID), **throttled**
  (under-voltage / throttle flags via `vcgencmd get_throttled`), lcd_clock service state,
  `power_configured`, and `backyard` (see below).
- `POST /api/power` — reboot/shutdown behind Basic auth (see "Power control").
- `/logo.svg`, `/favicon.ico` — served from disk.

### Branding
Matches the e-paper display at .50 / home-hub at .131: palette `#2C654B` green /
`#F9E7DF` cream / `#C8852A` amber / `#2B3A33` bark / `#F5F1E6` parchment, **Nunito** font
(Google Fonts + system fallback), white cards on parchment, badge in header.

### Backyard weather integration
- Source: **`http://192.168.12.50/status.json`** (the e-paper ESP8266 relays the Ambient
  Weather console's push feed; `.station` object has tempf, humidity, wind/gust, rain
  daily/weekly/monthly, uv, solar, barometer, indoor temp/hum, battery, freshness summary).
- Fetched **server-side** in `backyard()` (avoids browser CORS), **cached ~12s** so .50 isn't
  hammered by every client poll. Section auto-hides if `received` is false.
- **.49 (the Ambient console itself) is login-gated** — root is a gzipped `login.html`, all
  data endpoints 404. So .50 is the correct unauthenticated source; do not scrape .49.

### Power control (reboot / shutdown)
- `POST /api/power` with `action=reboot|shutdown`, behind **HTTP Basic auth**.
- Credentials: salted **PBKDF2-SHA256** hash in `~/pi-monitor/power_auth` (chmod 600, JSON:
  user/iter/salt/hash). **No plaintext, nothing hardcoded.** Set via interactive
  `set_power_password.py` (uses getpass). Running service re-reads the file per request — no
  restart needed after setting.
- Auth states: no file → **503** (buttons inert, dashboard shows a hint); bad creds → **401**;
  valid → **200** then `subprocess.Popen(["sudo","-n","/usr/sbin/reboot"|"/usr/sbin/poweroff"])`.
- Sudoers: `/etc/sudoers.d/pi-monitor-power` (chmod 440, `visudo -c` validated) grants the
  service user NOPASSWD for **only** `/usr/sbin/reboot` and `/usr/sbin/poweroff`.
- UI: header title is now dynamic (`<hostname> Monitor`, set by JS from `/api/stats` — no
  hardcoded "Pi Zero"). Power buttons open a confirm modal with a masked password field.

---

## PiTouch sibling — Raspberry Pi 5 @ 192.168.12.55 (user `jdburgie`)

Same SSH key (`~/.ssh/id_ed25519`) and the **identical** `server.py` + assets as this Pi.
- Dashboard: **http://192.168.12.55:8080**. On WiFi (`wlan0`), eth0 down.
- No SPI LCD / clock → the **LCD Clock card auto-hides** (server checks
  `systemctl list-unit-files lcd-clock.service`; card only renders when the unit exists).
- Same backyard feed from .50, same branding, same power endpoint + its own `power_auth` and
  `/etc/sudoers.d/pi-monitor-power` (user `jdburgie`). WiFi powersave disabled the same way.
- **Single codebase, two hosts:** the only per-host differences are the systemd unit's `User=`
  and `ExecStart` path (this Pi: `pi`, `/home/pi`; PiTouch: `jdburgie`, `/home/jdburgie`).

---

## Service files (both `enable`d)
- `/etc/systemd/system/lcd-clock.service` → `venv/bin/python3 clock.py`, `Restart=on-failure`
- `/etc/systemd/system/pi-monitor.service` → `/usr/bin/python3 server.py`,
  `After=network-online.target`, `Restart=on-failure`
- Gotcha seen: a leftover **manual** `python3 server.py` held port 8080 and made the service
  loop on `Address already in use`. Kill stray procs (`pkill -f server.py`) before start; let
  systemd own the port.
