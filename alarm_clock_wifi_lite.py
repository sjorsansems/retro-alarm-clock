"""
ESP32 Alarm Clock LITE (MicroPython)
Doel: stabiel draaien op lage RAM met WiFi + NTP + simpele web UI.
"""

from machine import Pin, PWM, SoftI2C
import framebuf
import time
import json
import network
import socket
import gc

try:
    from config_manager import ConfigManager
except ImportError:
    ConfigManager = None

try:
    from ntp_time_sync import NTPTimeSync
except ImportError:
    NTPTimeSync = None

SDA_PIN = 21
SCL_PIN = 22
I2C_FREQ = 100_000
BUZZER_PIN = 27
WIDTH = 128
HEIGHT = 64
SH1106_COL_OFFSET = 2
WIFI_PORT = 80

ALARM_TONES = {
    "classic": {"label": "Classic", "pattern": ((1200, 380, 2), (0, 0, 1), (980, 380, 2), (0, 0, 2))},
    "retro_a": {"label": "Retro A", "pattern": ((523, 320, 1), (659, 320, 1), (784, 360, 2), (659, 320, 1), (523, 320, 2), (0, 0, 2))},
    "retro_b": {"label": "Retro B", "pattern": ((440, 320, 1), (554, 320, 1), (659, 360, 2), (554, 320, 1), (440, 320, 2), (0, 0, 2))},
    "retro_random": {"label": "Retro Random", "pattern": ((880, 300, 2), (0, 0, 2))},
}
RETRO_RANDOM_POOL = ("retro_a", "retro_b")

BIG_TIME_GLYPHS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "001", "001"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    ":": ("0", "1", "0", "1", "0"),
}

HTML_PAGE = """<!DOCTYPE html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Alarm Lite</title>
<style>
body{font-family:Arial,sans-serif;margin:12px;background:#f4f7fb}.card{background:#fff;border-radius:10px;padding:12px;margin-bottom:10px}
.time{font-size:34px;text-align:center;color:#1f6fd6}label{display:block;margin-top:8px;font-weight:bold}
input,select,button{width:100%;padding:10px;margin-top:6px;box-sizing:border-box}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
</style></head><body>
<div class='card'><div class='time' id='t'>--:--:--</div><div id='d'></div></div>
<div class='card'><div class='row'><div><label>Tijd</label><input type='time' id='time' value='12:00'></div><div><label>Seconde</label><input type='number' id='sec' min='0' max='59' value='0'></div></div>
<button onclick='setTime()'>Stel Tijd In</button></div>
<div class='card'><label>Tijdzone</label><select id='tz'><option value='Europe/Amsterdam'>Europe/Amsterdam</option><option value='UTC'>UTC</option><option value='UTC+1'>UTC+1</option><option value='UTC+2'>UTC+2</option><option value='UTC-1'>UTC-1</option></select>
<button onclick='setTimezone()'>Sla Tijdzone Op</button><button onclick='syncNtp()'>Sync Met NTP</button></div>
<div class='card'><div class='row'><div><label>Alarmgeluid</label><select id='tone'></select></div><div><label>Volume %</label><input type='number' id='vol' min='0' max='100' value='70'></div></div>
<div class='row'><div><label>Testduur sec</label><input type='number' id='dur' min='1' max='60' value='10'></div><div></div></div>
<button onclick='saveAlarm()'>Sla Alarminstellingen Op</button><button onclick='testAlarm()'>Test Alarm</button></div>
<script>
function j(x){return JSON.stringify(x)}
function z(n){return String(n).padStart(2,'0')}
let editingUntil = 0
function isEditing(){
    const ids=['time','sec','tz','tone','vol','dur']
    const ae=document.activeElement
    return Date.now()<editingUntil || (ae && ids.indexOf(ae.id)>=0)
}
function markEditing(){editingUntil=Date.now()+3000}
async function apiPost(url,payload){
    const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:payload?j(payload):null})
    return res.json().catch(()=>({ok:false}))
}
function bindEditors(){
    ;['time','sec','tz','tone','vol','dur'].forEach(id=>{
        const el=document.getElementById(id)
        if(!el){return}
        el.addEventListener('focus',markEditing)
        el.addEventListener('input',markEditing)
        el.addEventListener('change',markEditing)
    })
}
function refresh(){
    fetch('/api/time').then(r=>r.json()).then(d=>{
        document.getElementById('t').textContent=z(d.hour)+':'+z(d.minute)+':'+z(d.second)
        document.getElementById('d').textContent=d.weekday_name+' '+z(d.day)+'-'+z(d.month)+'-'+d.year+' ('+d.timezone_label+')'

        if(!isEditing()){
            document.getElementById('time').value=z(d.hour)+':'+z(d.minute)
            document.getElementById('sec').value=d.second
            document.getElementById('tz').value=d.timezone_name||'Europe/Amsterdam'
            const s=document.getElementById('tone')
            const cur=s.value
            s.innerHTML=(d.alarm_tones||[]).map(t=>'<option value="'+t.key+'">'+t.label+'</option>').join('')
            s.value=d.alarm_tone||cur||'classic'
            document.getElementById('vol').value=d.alarm_volume??70
        }
    })
}
async function setTime(){
    markEditing()
    const p=document.getElementById('time').value.split(':').map(Number)
    await apiPost('/api/set-time',{hour:p[0],minute:p[1],second:Number(document.getElementById('sec').value||0)})
    editingUntil=0
    refresh()
}
async function setTimezone(){
    markEditing()
    await apiPost('/api/set-timezone',{timezone:document.getElementById('tz').value})
    editingUntil=0
    refresh()
}
async function saveAlarm(){
    markEditing()
    await apiPost('/api/set-alarm-settings',{tone:document.getElementById('tone').value,volume:Number(document.getElementById('vol').value||70)})
    editingUntil=0
    refresh()
}
function testAlarm(){apiPost('/api/test-alarm',{seconds:Number(document.getElementById('dur').value||10)})}
async function syncNtp(){await apiPost('/api/sync-ntp');refresh()}
bindEditors();refresh();setInterval(refresh,1000)
</script></body></html>"""


class SH1106_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C):
        self.width = width
        self.height = height
        self.i2c = i2c
        self.addr = addr
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        for cmd in (0xAE, 0xD5, 0x80, 0xA8, self.height - 1, 0xD3, 0x00, 0x40,
                    0xAD, 0x8B, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0x7F, 0xD9, 0x22,
                    0xDB, 0x35, 0xA4, 0xA6, 0xAF):
            self.i2c.writeto(self.addr, bytes((0x80, cmd)))
        self.fill(0)
        self.show()

    def show(self):
        for page in range(self.pages):
            self.i2c.writeto(self.addr, bytes((0x80, 0xB0 + page)))
            col = SH1106_COL_OFFSET
            self.i2c.writeto(self.addr, bytes((0x80, col & 0x0F)))
            self.i2c.writeto(self.addr, bytes((0x80, 0x10 | (col >> 4))))
            start = self.width * page
            self.i2c.writeto(self.addr, b"\x40" + self.buffer[start:start + self.width])


class WiFiManagerLite:
    def __init__(self, ssid, password, timeout=10):
        self.ssid = ssid
        self.password = password
        self.timeout = timeout
        self.sta = None
        for _ in range(3):
            try:
                gc.collect()
                self.sta = network.WLAN(network.STA_IF)
                break
            except:
                time.sleep(0.2)
        if self.sta is None:
            raise OSError("WiFi Out of Memory")

    def connect(self):
        if not self.sta.active():
            self.sta.active(True)
            time.sleep(0.4)
        if self.sta.isconnected():
            return True
        self.sta.connect(self.ssid, self.password)
        start = time.time()
        while not self.sta.isconnected():
            if time.time() - start > self.timeout:
                return False
            time.sleep(0.3)
        return True

    def is_connected(self):
        return self.sta and self.sta.isconnected()

    def get_ip(self):
        if self.is_connected():
            return self.sta.ifconfig()[0]
        return None


class ClockCore:
    def __init__(self, timezone_name="Europe/Amsterdam"):
        self.timezone_name = timezone_name
        self.soft_epoch = None
        self.soft_ticks = 0
        self.last_sync = 0

    def _tz(self, utc_tuple):
        if self.timezone_name == "Europe/Amsterdam" and NTPTimeSync:
            t = NTPTimeSync.time_tuple_to_dutch(utc_tuple)
            if len(t) >= 7:
                t = t[:6] + (t[6] + 1,) + t[7:]
            return t, ("CEST" if NTPTimeSync.is_dst(utc_tuple[0], utc_tuple[1], utc_tuple[2]) else "CET")
        off = 0
        if self.timezone_name.startswith("UTC") and len(self.timezone_name) > 3:
            try:
                off = int(self.timezone_name[3:])
            except:
                off = 0
        base = (utc_tuple[0], utc_tuple[1], utc_tuple[2], utc_tuple[3], utc_tuple[4], utc_tuple[5], 0, 0)
        shifted = time.localtime(time.mktime(base) + off * 3600)
        return (shifted[0], shifted[1], shifted[2], shifted[3], shifted[4], shifted[5], shifted[6] + 1, shifted[7]), ("UTC" if off == 0 else "UTC{}{}".format("+" if off > 0 else "", off))

    def read_time(self):
        if self.soft_epoch is None:
            utc = time.gmtime()
            t, _ = self._tz(utc)
            self.set_time(*t[:6])
            return t
        elapsed = time.ticks_diff(time.ticks_ms(), self.soft_ticks) // 1000
        cur = time.localtime(self.soft_epoch + elapsed)
        return (cur[0], cur[1], cur[2], cur[3], cur[4], cur[5], cur[6] + 1, cur[7])

    def set_time(self, y, m, d, hh, mm, ss):
        base = (int(y), int(m), int(d), int(hh), int(mm), int(ss), 0, 0)
        self.soft_epoch = time.mktime(base)
        self.soft_ticks = time.ticks_ms()
        return True

    def set_timezone(self, name):
        self.timezone_name = name or "Europe/Amsterdam"
        utc = time.gmtime()
        t, _ = self._tz(utc)
        self.set_time(*t[:6])

    def sync_ntp(self):
        try:
            import ntptime
            ntptime.host = "pool.ntp.org"
            ntptime.settime()
            utc = time.gmtime()
            t, label = self._tz(utc)
            self.set_time(*t[:6])
            self.last_sync = time.time()
            print("✓ NTP Sync ({})".format(label))
            return True
        except Exception as e:
            print("✗ NTP Sync fout:", e)
            return False

    def timezone_label(self):
        t = self.read_time()
        if self.timezone_name == "Europe/Amsterdam" and NTPTimeSync:
            return "CEST" if NTPTimeSync.is_dst(t[0], t[1], t[2]) else "CET"
        return self.timezone_name


class App:
    def __init__(self):
        print("\n=== ESP32 ALARMKLOK LITE OPSTARTEN ===\n")
        self.config = ConfigManager("config.json") if ConfigManager else None
        self.tone = "classic"
        self.volume = 70
        if self.config:
            self.tone = self.config.get("alarm_sound", "tone", "classic")
            self.volume = int(self.config.get("alarm_sound", "volume", 70) or 70)
            timezone = self.config.get("ntp", "timezone", "Europe/Amsterdam")
            ssid = self.config.get("wifi", "ssid", "SL2")
            pwd = self.config.get("wifi", "password", "")
        else:
            timezone, ssid, pwd = "Europe/Amsterdam", "SL2", ""

        self.clock = ClockCore(timezone)
        self.alarm_until = None
        self.active_tone = self.tone

        self.i2c = SoftI2C(sda=Pin(SDA_PIN, pull=Pin.PULL_UP), scl=Pin(SCL_PIN, pull=Pin.PULL_UP), freq=I2C_FREQ)
        self.display = None
        try:
            dev = self.i2c.scan()
            if 0x3C in dev:
                self.display = SH1106_I2C(WIDTH, HEIGHT, self.i2c, 0x3C)
        except:
            pass

        self.buzzer = PWM(Pin(BUZZER_PIN))
        self.buzzer.freq(1000)
        self.buzzer.duty(0)

        self.wifi = WiFiManagerLite(ssid, pwd)
        self.wifi_ok = self.wifi.connect()
        self.startup_ip_until = None
        print("WiFi:", "OK" if self.wifi_ok else "FOUT")
        if self.wifi_ok:
            self.clock.sync_ntp()
            self.startup_ip_until = time.ticks_add(time.ticks_ms(), 5000)

        self.sock = None

    def _tone_now(self):
        selected = self.tone
        if selected == "retro_random":
            t = self.clock.read_time()
            selected = RETRO_RANDOM_POOL[((t[0] * 372) + (t[1] * 31) + t[2]) % len(RETRO_RANDOM_POOL)]
        return selected if selected in ALARM_TONES else "classic"

    def _play(self, frame):
        tone = self.active_tone
        pat = ALARM_TONES[tone]["pattern"]
        total = 0
        for _f, _d, dur in pat:
            total += dur
        if total <= 0:
            self.buzzer.duty(0)
            return
        pos = frame % total
        cur = 0
        for f, d, dur in pat:
            cur += dur
            if pos < cur:
                if f <= 0 or d <= 0:
                    self.buzzer.duty(0)
                else:
                    self.buzzer.freq(f)
                    duty = int((d * max(0, min(100, self.volume))) / 100)
                    self.buzzer.duty(max(0, min(1023, duty)))
                return

    def _json(self, payload):
        return ("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + json.dumps(payload)).encode()

    def _parse(self, req):
        parts = req.split("\r\n\r\n", 1)
        if len(parts) < 2 or not parts[1]:
            return {}
        try:
            return json.loads(parts[1])
        except:
            return {}

    def _request(self, c):
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 4096:
            ch = c.recv(512)
            if not ch:
                break
            data += ch
        if b"\r\n\r\n" in data:
            h, b = data.split(b"\r\n\r\n", 1)
            cl = 0
            for line in h.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    try:
                        cl = int(line.split(b":", 1)[1].strip())
                    except:
                        cl = 0
            while len(b) < cl and len(data) < 8192:
                ch = c.recv(min(512, cl - len(b)))
                if not ch:
                    break
                data += ch
                b += ch
        return data.decode("utf-8", "ignore")

    def _weekday_name(self, idx):
        names = ("Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag")
        return names[(int(idx) - 1) % 7]

    def _draw_big_char(self, ch, x, y, scale=3):
        glyph = BIG_TIME_GLYPHS.get(ch)
        if not glyph:
            return 0
        w = len(glyph[0]) if glyph else 0
        for row_idx, row in enumerate(glyph):
            for col_idx, bit in enumerate(row):
                if bit == "1":
                    self.display.fill_rect(x + col_idx * scale, y + row_idx * scale, scale, scale, 1)
        return (w * scale) + scale

    def _draw_big_time(self, hh, mm):
        text = "{:02d}:{:02d}".format(hh, mm)
        scale = 3
        width = 0
        for ch in text:
            glyph = BIG_TIME_GLYPHS.get(ch)
            if glyph:
                width += (len(glyph[0]) * scale) + scale
        width = max(0, width - scale)
        x = max(0, (WIDTH - width) // 2)
        y = 0
        for ch in text:
            x += self._draw_big_char(ch, x, y, scale)

    def _draw_startup_ip(self):
        self.display.fill(0)
        self.display.text("WiFi verbonden", 8, 8, 1)
        ip = self.wifi.get_ip() if self.wifi_ok else None
        self.display.text("IP adres:", 8, 26, 1)
        self.display.text(ip if ip else "geen netwerk", 8, 40, 1)
        self.display.show()

    def _draw_clock_layout(self):
        t = self.clock.read_time()
        self.display.fill(0)
        self._draw_big_time(t[3], t[4])
        self.display.text(self._weekday_name(t[6]), 8, 40, 1)
        self.display.text("{:02d}-{:02d}-{:04d}".format(t[2], t[1], t[0]), 8, 54, 1)
        self.display.show()

    def serve_once(self, c):
        req = self._request(c)
        line = req.split("\r\n", 1)[0]
        parts = line.split(" ")
        method = parts[0] if len(parts) > 0 else ""
        path = parts[1] if len(parts) > 1 else ""
        if method == "GET" and path == "/":
            c.send(("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n" + HTML_PAGE).encode())
            return
        if method == "GET" and path == "/api/time":
            t = self.clock.read_time()
            c.send(self._json({
                "year": t[0], "month": t[1], "day": t[2],
                "hour": t[3], "minute": t[4], "second": t[5],
                "weekday": t[6], "weekday_name": self._weekday_name(t[6]),
                "timezone_name": self.clock.timezone_name,
                "timezone_label": self.clock.timezone_label(),
                "alarm_tone": self.tone,
                "alarm_volume": self.volume,
                "alarm_tones": [{"key": k, "label": ALARM_TONES[k]["label"] if k in ALARM_TONES else "Retro Random"} for k in ("retro_random", "classic", "retro_a", "retro_b")]
            }))
            return
        if method == "POST" and path == "/api/set-time":
            d = self._parse(req)
            now = self.clock.read_time()
            self.clock.set_time(now[0], now[1], now[2], int(d.get("hour", now[3])) % 24, int(d.get("minute", now[4])) % 60, int(d.get("second", 0)) % 60)
            c.send(self._json({"ok": True}))
            return
        if method == "POST" and path == "/api/set-timezone":
            d = self._parse(req)
            tz = d.get("timezone", "Europe/Amsterdam")
            self.clock.set_timezone(tz)
            if self.config:
                self.config.set("ntp", "timezone", tz)
            c.send(self._json({"ok": True}))
            return
        if method == "POST" and path == "/api/sync-ntp":
            ok = self.clock.sync_ntp()
            c.send(self._json({"ok": bool(ok)}))
            return
        if method == "POST" and path == "/api/set-alarm-settings":
            d = self._parse(req)
            tone = d.get("tone", "classic")
            vol = int(d.get("volume", 70) or 70)
            if tone not in ("classic", "retro_a", "retro_b", "retro_random"):
                tone = "classic"
            self.tone = tone
            self.volume = max(0, min(100, vol))
            if self.config:
                self.config.set("alarm_sound", "tone", self.tone)
                self.config.set("alarm_sound", "volume", self.volume)
            c.send(self._json({"ok": True}))
            return
        if method == "POST" and path == "/api/test-alarm":
            d = self._parse(req)
            sec = int(d.get("seconds", 10) or 10)
            sec = max(1, min(60, sec))
            self.active_tone = self._tone_now()
            self.alarm_until = time.ticks_add(time.ticks_ms(), sec * 1000)
            c.send(self._json({"ok": True}))
            return
        c.send("HTTP/1.1 404 Not Found\r\n\r\n".encode())

    def run(self):
        if not self.wifi_ok:
            print("Webserver uit: geen WiFi")
        else:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", WIFI_PORT))
            self.sock.listen(2)
            self.sock.settimeout(0.1)
            print("Web:", "http://{}".format(self.wifi.get_ip()))

        frame = 0
        while True:
            try:
                if self.sock:
                    try:
                        c, _a = self.sock.accept()
                        self.serve_once(c)
                        c.close()
                    except OSError:
                        pass

                if self.alarm_until is not None:
                    if time.ticks_diff(time.ticks_ms(), self.alarm_until) >= 0:
                        self.alarm_until = None
                        self.buzzer.duty(0)
                    else:
                        self._play(frame)
                else:
                    self.buzzer.duty(0)

                if frame % 18000 == 0 and self.wifi_ok:
                    self.clock.sync_ntp()

                if self.display:
                    if self.startup_ip_until is not None and time.ticks_diff(self.startup_ip_until, time.ticks_ms()) > 0:
                        self._draw_startup_ip()
                    else:
                        self.startup_ip_until = None
                        self._draw_clock_layout()

                frame += 1
                time.sleep(0.2)
            except Exception as e:
                print("Loop fout:", e)
                time.sleep(0.5)


if __name__ == "__main__":
    app = App()
    app.run()
