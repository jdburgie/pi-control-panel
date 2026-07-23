# Pi Zero W Display Hub — JOURNAL

Raspberry Pi Zero W v1.1, hostname **RasPi0W**, `192.168.12.57` (user `pi`).
Two jobs running as systemd services: an **analog clock** on a small SPI LCD, and a
**LAN monitoring web dashboard** that also relays backyard weather.

---

## ▶ PICK UP HERE (2026-07-23)

Everything below is deployed and running as enabled systemd services (survive reboot).

- **Clock:** `lcd-clock.service` → `/home/pi/lcd-clock/clock.py` (venv). Landscape analog
  clock on the Waveshare 1.47" SPI LCD. Working, un-mirrored, upright.
- **Monitor:** `pi-monitor.service` → `/home/pi/pi-monitor/server.py` (stdlib only).
  Dashboard at **http://192.168.12.57:8080**. Three Oak Woods branded. Shows Pi health,
  a Backyard Station section (from the e-paper display at .50), and **Reboot/Shutdown**
  buttons behind a login.
- **Sibling:** the **PiTouch** (Raspberry Pi 5) at **192.168.12.55** runs the *same*
  `server.py` (dashboard at http://192.168.12.55:8080). One codebase, two hosts — see the
  "PiTouch sibling" section.

### ⚠ To finish: set the power password on each Pi (one-time, interactive)
Reboot/Shutdown buttons stay inert until a login is set. Run in your own terminal:
```
ssh -t pi@192.168.12.57 "cd ~/pi-monitor && python3 set_power_password.py"
ssh -t jdburgie@192.168.12.55 "cd ~/pi-monitor && python3 set_power_password.py"
```

### Open / next ideas
- Nextion board (`NX4827T043_011`) is wired to the UART (see below) but has **no software
  yet** — purpose undecided.
- Clock SPI runs at a conservative **4 MHz**; could try higher for snappier redraws.
- Dashboard *view* has no auth (fine for LAN); only the power actions are login-gated.
- **Stability:** .57 dropped off WiFi and rebooted once on 2026-07-23 under load (single-core
  Zero running clock@1Hz + web server). Services auto-recovered (both enabled). If it
  recurs, consider a watchdog / lowering clock redraw rate.
- Not a git repo yet — consider `git init` + push to match the other hardware projects.

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
