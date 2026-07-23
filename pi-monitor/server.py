#!/usr/bin/env python3
"""Lightweight stdlib-only monitoring web server for a Raspberry Pi Zero W.

Serves an auto-refreshing dashboard at / and JSON at /api/stats.
No external dependencies; reads from /proc, /sys and vcgencmd.
"""
import base64
import hashlib
import hmac
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8080
_prev_cpu = {}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Backyard weather relayed by the e-paper display at .50 (Ambient Weather feed).
BACKYARD_URL = "http://192.168.12.50/status.json"
_backyard = {"ts": 0, "data": {"ok": False}}

# Power control: reboot/shutdown behind HTTP Basic auth (see set_power_password.py).
AUTH_FILE = os.path.join(BASE_DIR, "power_auth")
REBOOT_CMD = ["sudo", "-n", "/usr/sbin/reboot"]
POWEROFF_CMD = ["sudo", "-n", "/usr/sbin/poweroff"]


def load_power_auth():
    try:
        with open(AUTH_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def check_power_auth(header):
    """None = not configured, False = bad creds, True = authorized."""
    a = load_power_auth()
    if not a:
        return None
    if not header or not header.startswith("Basic "):
        return False
    try:
        user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
    except Exception:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(a["salt"]), a["iter"])
    return hmac.compare_digest(user, a["user"]) and hmac.compare_digest(
        calc, bytes.fromhex(a["hash"])
    )


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def cpu_percent():
    """Non-blocking CPU%: delta of /proc/stat between calls."""
    parts = read("/proc/stat").splitlines()[0].split()[1:]
    vals = [int(x) for x in parts]
    idle = vals[3] + vals[4]  # idle + iowait
    total = sum(vals)
    p = _prev_cpu.get("t")
    _prev_cpu["t"] = (total, idle)
    if not p:
        return None
    dt, di = total - p[0], idle - p[1]
    if dt <= 0:
        return None
    return round(100.0 * (dt - di) / dt, 1)


def mem_info():
    info = {}
    for line in read("/proc/meminfo").splitlines():
        k, _, rest = line.partition(":")
        info[k] = int(rest.strip().split()[0])  # kB
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", 0)
    used = total - avail
    return {
        "total_mb": round(total / 1024, 1),
        "used_mb": round(used / 1024, 1),
        "pct": round(100.0 * used / total, 1) if total else 0,
    }


def disk_info():
    u = shutil.disk_usage("/")
    return {
        "total_gb": round(u.total / 1e9, 2),
        "used_gb": round(u.used / 1e9, 2),
        "pct": round(100.0 * u.used / u.total, 1),
    }


def cpu_temp():
    t = read("/sys/class/thermal/thermal_zone0/temp")
    return round(int(t) / 1000.0, 1) if t.isdigit() else None


def cpu_freq_mhz():
    f = read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    return round(int(f) / 1000) if f.isdigit() else None


def uptime():
    up = read("/proc/uptime").split()
    secs = int(float(up[0])) if up else 0
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    out = []
    if d:
        out.append(f"{d}d")
    out.append(f"{h}h")
    out.append(f"{m}m")
    return " ".join(out)


def wifi():
    """Signal from /proc/net/wireless; SSID via iw/nmcli fallback."""
    sig = None
    for line in read("/proc/net/wireless").splitlines():
        if line.strip().startswith("wlan0"):
            cols = line.split()
            try:
                sig = int(float(cols[3]))  # dBm
            except (ValueError, IndexError):
                pass
    ssid = ""
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
            capture_output=True, text=True, timeout=3,
        ).stdout
        for line in out.splitlines():
            if line.startswith("yes:"):
                ssid = line.split(":", 1)[1]
                break
    except Exception:
        pass
    return {"signal_dbm": sig, "ssid": ssid}


def throttled():
    """Decode vcgencmd get_throttled (under-voltage / throttling)."""
    try:
        out = subprocess.run(
            ["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=3
        ).stdout.strip()
        val = int(out.split("=")[1], 16)
    except Exception:
        return None
    return {
        "raw": hex(val),
        "under_voltage_now": bool(val & 0x1),
        "throttled_now": bool(val & 0x4),
        "under_voltage_past": bool(val & 0x10000),
        "throttled_past": bool(val & 0x40000),
    }


def ip_addr():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def service_active(name):
    try:
        r = subprocess.run(
            ["systemctl", "is-active", name], capture_output=True, text=True, timeout=3
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def service_exists(name):
    try:
        r = subprocess.run(
            ["systemctl", "list-unit-files", name, "--no-legend"],
            capture_output=True, text=True, timeout=3,
        )
        return bool(r.stdout.strip())
    except Exception:
        return False


def backyard():
    """Pull the Ambient Weather station data relayed by .50 (cached ~12s)."""
    now = time.time()
    if now - _backyard["ts"] < 12:
        return _backyard["data"]
    data = {"ok": False}
    try:
        with urllib.request.urlopen(BACKYARD_URL, timeout=4) as r:
            st = json.loads(r.read().decode()).get("station", {})
        if st.get("received"):
            data = {
                "ok": True,
                "tempf": st.get("tempf"),
                "humidity": st.get("humidity"),
                "windmph": st.get("windmph"),
                "gustmph": st.get("gustmph"),
                "winddir": st.get("winddir"),
                "dailyrain": st.get("dailyrain"),
                "weeklyrain": st.get("weeklyrain"),
                "monthlyrain": st.get("monthlyrain"),
                "uv": st.get("uv"),
                "solar": st.get("solarradiation"),
                "baromin": st.get("baromin"),
                "tempinf": st.get("tempinf"),
                "humidityin": st.get("humidityin"),
                "battout": st.get("battout"),
                "summary": st.get("summary"),
            }
    except Exception:
        data = {"ok": False}
    _backyard.update(ts=now, data=data)
    return data


def collect():
    return {
        "backyard": backyard(),
        "hostname": socket.gethostname(),
        "model": read("/proc/device-tree/model").replace("\x00", "") or "unknown",
        "kernel": os.uname().release,
        "ip": ip_addr(),
        "uptime": uptime(),
        "loadavg": [round(x, 2) for x in os.getloadavg()],
        "cpu_pct": cpu_percent(),
        "cpu_temp_c": cpu_temp(),
        "cpu_freq_mhz": cpu_freq_mhz(),
        "mem": mem_info(),
        "disk": disk_info(),
        "wifi": wifi(),
        "throttled": throttled(),
        "lcd_clock": (
            service_active("lcd-clock.service")
            if service_exists("lcd-clock.service")
            else None
        ),
        "power_configured": load_power_auth() is not None,
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pi Monitor · Three Oak Woods</title>
<link rel="icon" type="image/svg+xml" href="/logo.svg">
<link rel="icon" type="image/png" href="/favicon.ico">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --green:#2C654B; --cream:#F9E7DF; --amber:#C8852A; --bark:#2B3A33;
  --parchment:#F5F1E6; --card:#ffffff; --line:#e4dcc9;
  --muted:#7c8578; --crit:#b23b3b;
}
*{box-sizing:border-box}
body{margin:0;color:var(--bark);background:var(--parchment);
  font-family:'Nunito',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
header{padding:18px 22px;border-bottom:2px solid var(--green);
  display:flex;justify-content:space-between;align-items:center;
  flex-wrap:wrap;gap:12px;background:var(--parchment)}
.brand{display:flex;align-items:center;gap:14px}
.badge{width:46px;height:46px;flex:none}
h1{margin:0;font-size:20px;font-weight:800;color:var(--green);letter-spacing:.01em}
.sub{color:var(--muted);font-size:13px;font-weight:600}
.stamp{color:var(--green);font-size:13px;font-weight:700;text-align:right}
.grid{display:grid;gap:14px;padding:20px 22px;
  grid-template-columns:repeat(auto-fill,minmax(210px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:15px 17px;box-shadow:0 1px 2px rgba(43,58,51,.05)}
.label{color:var(--green);font-size:12px;font-weight:700;text-transform:uppercase;
  letter-spacing:.06em}
.val{font-size:27px;font-weight:800;margin-top:6px;color:var(--bark)}
.val small{font-size:14px;color:var(--muted);font-weight:600}
.bar{height:7px;background:#ece4d3;border-radius:5px;margin-top:11px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--green);border-radius:5px}
.bar.warn>i{background:var(--amber)}.bar.crit>i{background:var(--crit)}
.ok{color:var(--green);font-weight:800}.bad{color:var(--crit);font-weight:800}
.pill{display:inline-block;padding:3px 11px;border-radius:20px;font-size:13px;
  font-weight:700;background:#eee7d6;color:var(--bark)}
.pill.ok{background:#e2efe6;color:var(--green)}
.pill.bad{background:#f4e2e2;color:var(--crit)}
.section{display:flex;align-items:baseline;gap:10px;padding:8px 24px 0;
  color:var(--green);font-size:16px;font-weight:800}
.section .sub{font-weight:600}
footer{padding:4px 22px 26px;color:var(--muted);font-size:12px;font-weight:600}
footer a{color:var(--green)}
.powerbar{display:flex;gap:12px;align-items:center;padding:14px 24px 0;flex-wrap:wrap}
.pw{font-family:inherit;font-weight:800;font-size:14px;border:0;border-radius:10px;
  padding:10px 18px;cursor:pointer;color:#fff}
.pw.reboot{background:var(--amber)}.pw.shutdown{background:var(--crit)}
.pw:hover{filter:brightness(1.07)}
.pwhint{color:var(--muted);font-size:12px;font-weight:600}
.modal{position:fixed;inset:0;background:rgba(43,58,51,.45);display:flex;
  align-items:center;justify-content:center;z-index:10;padding:16px}
.modal[hidden]{display:none}
.modal-box{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:20px;width:100%;max-width:340px;box-shadow:0 8px 30px rgba(43,58,51,.25)}
.modal-box h3{margin:0 0 12px;color:var(--bark);font-size:17px;font-weight:800}
.modal-box input{font-family:inherit;font-size:15px;padding:10px 12px;width:100%;
  border:1px solid #cfc6b3;border-radius:8px;margin:0 0 10px;background:#fff;color:var(--bark)}
.pwmsg{min-height:18px;font-size:13px;font-weight:700;margin:2px 0 10px;color:var(--muted)}
.modal-actions{display:flex;gap:10px;justify-content:flex-end}
.modal-actions button{font-family:inherit;font-weight:800;font-size:14px;border-radius:9px;
  padding:9px 16px;cursor:pointer;border:0;color:#fff}
.modal-actions .clear{background:#fff;color:var(--bark);border:1px solid #cfc6b3}
</style></head>
<body>
<header>
  <div class="brand">
    <img class="badge" src="/logo.svg" alt="Three Oak Woods">
    <div>
      <h1 id="title">Pi Monitor</h1>
      <div class="sub" id="model">&nbsp;</div>
    </div>
  </div>
  <div class="stamp"><span id="host"></span><br><span id="ts"></span></div>
</header>
<div class="section">Pi Health</div>
<div class="grid" id="grid"></div>
<div class="section" id="ysection" style="display:none">Backyard Station
  <span class="sub" id="ystamp"></span></div>
<div class="grid" id="ygrid"></div>
<div class="section">Power</div>
<div class="powerbar">
  <button class="pw reboot" onclick="askPower('reboot')">⟳ Reboot</button>
  <button class="pw shutdown" onclick="askPower('shutdown')">⏻ Shutdown</button>
  <span class="pwhint" id="pwhint"></span>
</div>
<footer>Auto-refresh every 3s · <span id="ip"></span> · backyard via <a href="http://192.168.12.50/status.json">.50</a> · <a href="/api/stats">/api/stats</a></footer>
<div class="modal" id="pwmodal" hidden>
  <div class="modal-box">
    <h3 id="pwtitle">Confirm</h3>
    <input id="pwuser" placeholder="username" autocomplete="username">
    <input id="pwpass" type="password" placeholder="password" autocomplete="current-password">
    <div class="pwmsg" id="pwmsg"></div>
    <div class="modal-actions">
      <button class="clear" onclick="closePower()">Cancel</button>
      <button id="pwgo" class="pw shutdown">Confirm</button>
    </div>
  </div>
</div>
<script>
function bar(pct,warn,crit){
  let c=pct>=crit?'crit':pct>=warn?'warn':'';
  return `<div class="bar ${c}"><i style="width:${Math.min(100,pct)}%"></i></div>`;
}
function card(label,val,extra=''){
  return `<div class="card"><div class="label">${label}</div>
    <div class="val">${val}</div>${extra}</div>`;
}
async function tick(){
  let d;
  try{ d=await (await fetch('/api/stats',{cache:'no-store'})).json(); }
  catch(e){ document.getElementById('ts').textContent='disconnected'; return; }
  document.getElementById('host').textContent=d.hostname;
  document.getElementById('title').textContent=d.hostname+' Monitor';
  document.title=d.hostname+' Monitor · Three Oak Woods';
  document.getElementById('model').textContent=d.model;
  document.getElementById('ts').textContent=d.ts;
  document.getElementById('ip').textContent=d.ip;
  let t=d.throttled, uv=t&&(t.under_voltage_now||t.under_voltage_past);
  let g=[];
  g.push(card('CPU Temp', d.cpu_temp_c!=null?`${d.cpu_temp_c}<small>°C</small>`:'—',
    d.cpu_temp_c!=null?bar(d.cpu_temp_c,60,75):''));
  g.push(card('CPU Load', d.cpu_pct!=null?`${d.cpu_pct}<small>%</small>`:'—',
    (d.cpu_pct!=null?bar(d.cpu_pct,70,90):'')+
    `<div class="sub" style="margin-top:8px">load ${d.loadavg.join(' · ')}</div>`));
  g.push(card('Memory', `${d.mem.pct}<small>%</small>`,
    bar(d.mem.pct,75,90)+`<div class="sub" style="margin-top:8px">${d.mem.used_mb} / ${d.mem.total_mb} MB</div>`));
  g.push(card('Disk /', `${d.disk.pct}<small>%</small>`,
    bar(d.disk.pct,80,92)+`<div class="sub" style="margin-top:8px">${d.disk.used_gb} / ${d.disk.total_gb} GB</div>`));
  g.push(card('CPU Freq', d.cpu_freq_mhz?`${d.cpu_freq_mhz}<small>MHz</small>`:'—'));
  g.push(card('Uptime', d.uptime));
  g.push(card('WiFi', d.wifi.signal_dbm!=null?`${d.wifi.signal_dbm}<small>dBm</small>`:'—',
    `<div class="sub" style="margin-top:8px">${d.wifi.ssid||''}</div>`));
  g.push(card('Power', uv?'<span class="bad">Under-volt</span>':'<span class="ok">OK</span>',
    t?`<div class="sub" style="margin-top:8px">now: ${t.under_voltage_now?'⚠':'ok'} · past: ${t.under_voltage_past?'⚠':'ok'}</div>`:''));
  if(d.lcd_clock!=null){
    let clk=d.lcd_clock==='active';
    g.push(card('LCD Clock', `<span class="pill ${clk?'ok':'bad'}">${d.lcd_clock}</span>`));
  }
  document.getElementById('grid').innerHTML=g.join('');
  renderBackyard(d.backyard);
  powerHint(d.power_configured);
}
function compass(deg){
  const dirs=['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
  return dirs[Math.round(deg/22.5)%16];
}
function renderBackyard(b){
  let sec=document.getElementById('ysection'), grid=document.getElementById('ygrid');
  if(!b||!b.ok){ sec.style.display='none'; grid.innerHTML=''; return; }
  sec.style.display='';
  let m=(b.summary||'').match(/\\(([^)]*ago)\\)/);
  document.getElementById('ystamp').textContent=m?m[1]:'';
  let y=[];
  y.push(card('Outdoor Temp', `${b.tempf}<small>°F</small>`,
    `<div class="sub" style="margin-top:8px">indoor ${b.tempinf}°F</div>`));
  y.push(card('Humidity', `${b.humidity}<small>%</small>`,
    bar(b.humidity,200,201)+`<div class="sub" style="margin-top:8px">indoor ${b.humidityin}%</div>`));
  y.push(card('Wind', `${b.windmph}<small>mph</small>`,
    `<div class="sub" style="margin-top:8px">gust ${b.gustmph} · ${compass(b.winddir)} (${b.winddir}°)</div>`));
  y.push(card('Rain Today', `${b.dailyrain}<small>in</small>`,
    `<div class="sub" style="margin-top:8px">wk ${b.weeklyrain} · mo ${b.monthlyrain}</div>`));
  y.push(card('UV Index', `${b.uv}`, bar((b.uv/11)*100,73,100)));
  y.push(card('Solar', `${b.solar}<small>W/m²</small>`));
  y.push(card('Barometer', `${b.baromin}<small>inHg</small>`));
  y.push(card('Sensor Batt', b.battout?'<span class="ok">OK</span>':'<span class="bad">Low</span>'));
  grid.innerHTML=y.join('');
}
let pwAction=null;
function hostName(){return document.getElementById('host').textContent||'this Pi';}
function askPower(a){
  pwAction=a;
  document.getElementById('pwtitle').textContent=
    (a==='reboot'?'Reboot ':'Shut down ')+hostName()+'?';
  let msg=document.getElementById('pwmsg'); msg.style.color=''; msg.textContent='';
  document.getElementById('pwpass').value='';
  document.getElementById('pwmodal').hidden=false;
  document.getElementById('pwuser').focus();
}
function closePower(){document.getElementById('pwmodal').hidden=true;pwAction=null;}
document.getElementById('pwgo').onclick=async ()=>{
  let u=document.getElementById('pwuser').value,
      p=document.getElementById('pwpass').value,
      msg=document.getElementById('pwmsg');
  msg.style.color=''; msg.textContent='Sending…';
  try{
    let r=await fetch('/api/power',{method:'POST',
      headers:{'Authorization':'Basic '+btoa(u+':'+p),
        'Content-Type':'application/x-www-form-urlencoded'},
      body:'action='+pwAction});
    if(r.status===200){ msg.style.color='var(--green)';
      msg.textContent=(pwAction==='reboot'?'Rebooting '+hostName()+'…':'Shutting down '+hostName()+'…'); }
    else if(r.status===401){ msg.style.color='var(--crit)'; msg.textContent='Invalid login.'; }
    else if(r.status===503){ msg.style.color='var(--crit)';
      msg.textContent='Not configured — run set_power_password.py on this Pi.'; }
    else { msg.style.color='var(--crit)'; msg.textContent='Error: '+r.status; }
  }catch(e){ msg.style.color='var(--crit)'; msg.textContent='Request failed.'; }
};
function powerHint(cfg){
  document.getElementById('pwhint').textContent=
    cfg?'':'⚠ no password set — run set_power_password.py';
}
tick(); setInterval(tick,3000);
</script>
</body></html>"""


ASSETS = {
    "/logo.svg": ("logo.svg", "image/svg+xml"),
    "/favicon.ico": ("favicon.ico", "image/png"),
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/stats"):
            body = json.dumps(collect()).encode()
            self._send(200, body, "application/json")
        elif self.path == "/" or self.path.startswith("/index"):
            self._send(200, HTML.encode(), "text/html; charset=utf-8")
        elif self.path in ASSETS:
            fname, ctype = ASSETS[self.path]
            try:
                with open(os.path.join(BASE_DIR, fname), "rb") as f:
                    self._send(200, f.read(), ctype)
            except OSError:
                self._send(404, b"not found", "text/plain")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path.split("?")[0] != "/api/power":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length).decode() if length else ""
        action = urllib.parse.parse_qs(body).get("action", [""])[0]

        auth = check_power_auth(self.headers.get("Authorization"))
        if auth is None:
            self._send(503, b"power auth not configured", "text/plain")
            return
        if not auth:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="pi-power"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if action not in ("reboot", "shutdown"):
            self._send(400, b"bad action", "text/plain")
            return

        self._send(200, json.dumps({"ok": True, "action": action}).encode(),
                   "application/json")
        try:
            self.wfile.flush()
        except Exception:
            pass
        subprocess.Popen(REBOOT_CMD if action == "reboot" else POWEROFF_CMD)

    def log_message(self, *a):
        pass  # quiet


if __name__ == "__main__":
    cpu_percent()  # prime the delta
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
