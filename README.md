# Pi Control Panel

Home control-panel software running on a **Raspberry Pi Zero W** (hostname `RasPi0W`,
`192.168.12.57`), with the web dashboard also deployed to a **Raspberry Pi 5 "PiTouch"**
(`192.168.12.55`). Everything here is driven from small, dependency-light Python programs
managed as systemd services.

> Full build notes, wiring, gotchas, and the running-state summary live in
> [`JOURNAL.md`](JOURNAL.md) — read the "▶ PICK UP HERE" block first.

## Components

### `lcd-clock/` — analog clock
Landscape analog clock on a **Waveshare 1.47" ST7789 SPI LCD** (172×320). Pure Python
(`st7789` + Pillow). Notable: the panel needs a hardware-reset pulse, `MADCTL=0x00`, and a
software flip pipeline to render upright and un-mirrored (see JOURNAL). Service: `lcd-clock`.

### `pi-monitor/` — LAN web dashboard
Stdlib-only (`http.server`) monitoring dashboard on **:8080**, Three Oak Woods branded.
Shows Pi health (CPU temp/load/freq, memory, disk, WiFi, under-voltage/throttling), a live
**Backyard Station** section pulled server-side from the e-paper display at `.50`
(`/status.json`), and **Reboot/Shutdown** buttons behind HTTP Basic auth.

- `server.py` — the whole app (one file works on both Pis; host-specific cards auto-hide).
- `set_power_password.py` — interactive helper to set the power-control login (writes a
  salted PBKDF2 hash to `power_auth`, which is **gitignored**).
- `logo.svg`, `favicon.ico` — branding assets.

### `nextion/` — Nextion 4.3" display (NX4827T043_011R)
Scripts to drive a Nextion HMI over UART (`/dev/serial0`, 9600 baud):

- `nextion_probe.py` — baud-sweep + `connect` handshake (detects the board / `comok`).
- `nextion_loopback.py` — Pi UART self-test (jumper pin 8 ↔ pin 10).
- `nextion_cls.py`, `nextion_baudsweep.py` — bring-up color tests.
- `nextion_demo.py` — static shapes demo (runtime drawing commands, no `.tft`).
- `nextion_demo_clock.py` — **animated 7-segment clock** with a bouncing ball and a
  touch button that toggles 24H/12H (raw touch via `sendxy=1`). Service: `nextion-demo`.

### `systemd/` — service units
`lcd-clock.service`, `pi-monitor.service`, `nextion-demo.service`. Install with:

```bash
sudo cp systemd/<name>.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now <name>.service
```

(The `pi-monitor` unit on the PiTouch differs only in `User=`/paths.)

## Hardware
Raspberry Pi Zero W · Waveshare 1.47" SPI LCD · Nextion NX4827T043 4.3" (480×272) ·
soon migrating to a **Pi Zero 2 W** (quad-core) to end single-core overload. See
[`JOURNAL.md`](JOURNAL.md) for the full GPIO/UART wiring tables and SPI/UART config.
