# Sprinkler panel — Nextion `.HMI` layout spec

You lay the pages out in Nextion Editor; the Pi drives them. This is the contract between
the two. Deviate freely on *looks* (sizes, colours, placement) — just keep the **page names**,
**component names**, and **types** below, and the driver will work unchanged.

Board: **NX4827T043_011**, 480×272, display direction **0°**. Fonts already generated
(0 = small, 1 = large).

---

## Editor settings that actually matter

1. **Every button → Touch *Release* Event → tick “Send Component ID.”**
   That's what makes the Pi hear the tap. (No code needed in the event box.)
2. **Every text component the Pi writes → set “Max. Text Size” big enough.**
   Default is tiny (often 10) and silently truncates. Use **32** for zone-name fields,
   **40** for `tMsg`. This is the #1 gotcha.
3. **Do NOT put page-change commands in the Editor's event boxes.** Leave the events empty
   apart from the “Send Component ID” tick — **the Pi drives all navigation** (`page zones`).
   If the display changes pages on its own, the Pi's idea of the current view desyncs, and
   ID discovery can't step through the pages cleanly.
4. Leave **baud at 9600** (the driver assumes it).
5. **After flashing, run `touch_j`** (crosshair calibration) or touch reports `0,0`.
   Required after *any* reflash or direction change.

---

## Pages & components

Names are ≤10 chars (Nextion limit). `t*` = text, `n*` = number, `b*` = button.

### Page `status` (page 0 — the home screen)
| Name | Type | Driver writes |
|---|---|---|
| `tName` | text | controller name (“Garden Sprinkler”) |
| `tClock` | text | `HH:MM` |
| `tState` | text | `IDLE` / `WATERING` / `OFFLINE` |
| `tZone` | text | active zone name (blank when idle) |
| `tLeft` | text | remaining `M:SS` (blank when idle) |
| `tInfo` | text | `12/480 min today   queue 3` |
| `tRain` | text | `RAIN LOCKOUT` or blank |
| `bStop` | button | — (tap = stop watering, no confirm) |
| `bZones` | button | → page `zones` |
| `bProg` | button | → page `program` |
| `bRain` | button | → page `rain` |

### Page `zones` (pick a zone)
| Name | Type | Driver writes |
|---|---|---|
| `bZ1` … `bZ9` | button ×9 | `.txt` set to each zone's real name |
| `bBack` | button | → `status` |

### Page `run` (set duration & start)
| Name | Type | Driver writes |
|---|---|---|
| `tZone` | text | selected zone name |
| `nMin` | number | minutes (1–59) |
| `bM5` `bM1` `bP1` `bP5` | button ×4 | −5 / −1 / +1 / +5 |
| `bStart` | button | → confirm |
| `bBack` | button | → `zones` |

### Page `confirm`
| Name | Type | Driver writes |
|---|---|---|
| `tMsg` | text | e.g. `Water Dog Run 10 min?` (max size 40) |
| `bYes` | button | performs the action |
| `bNo` | button | → `status` |

### Page `program`
| Name | Type | Driver writes |
|---|---|---|
| `bRunA` | button | run program A (confirmed) |
| `bRunB` | button | run program B (confirmed) |
| `bClrQ` | button | clear queue |
| `bBack` | button | → `status` |

### Page `rain`
| Name | Type | Driver writes |
|---|---|---|
| `tRainSt` | text | `RAIN LOCKOUT ACTIVE` / `No delay` |
| `bR6` `bR12` `bR24` | button ×3 | 6h / 12h / 24h delay |
| `bRClr` | button | clear delay |
| `bBack` | button | → `status` |

---

## How the Pi talks to it

**Pi → display**
```
page zones                 switch page
tZone.txt="Dog Run"        set text   (cross-page: status.tZone.txt="...")
nMin.val=15                set number
vis bStop,0                hide/show a component
tsw bStart,0               disable a button's touch
```

**Display → Pi** (from “Send Component ID”)
```
65 <page> <compId> <event> FF FF FF     event: 01=press 00=release
```
`compId` is the numeric `.id` the Editor assigns — **you don't need to write these down.**
After you flash, run the discovery helper and tap each button once when prompted; it records
the `(page, id) → name` map automatically:

```bash
sudo systemctl stop nextion-demo.service
python3 ~/sprinkler-panel/discover_ids.py
```

---

## Sprinkler API the driver uses (read-only unless noted)

| Call | Body |
|---|---|
| `GET /api/status` | live state: `running`, `activeZoneName`, `remainingSec`, `queueDepth`, `rainLockedOut`, `dailyWateredMin`/`dailyBudgetMin` |
| `GET /api/config` | zone names/ids/durations, program names |
| `POST /api/manual/start` | `{"zone":1-9,"durationMinutes":1-59,"ignoreRain":false}` |
| `POST /api/manual/stop` | — |
| `POST /api/queue/clear` | — |
| `POST /api/program/start` | `{"program":"A"}` |
| `POST /api/rain-delay` | `{"hours":0-240}` (0 clears) |

Controller: `http://192.168.12.52`. Note it currently has **no PIN** (`pinEnabled:false`), so the
API is open on the LAN; if a PIN is set later the driver needs a `/api/login` session cookie.
