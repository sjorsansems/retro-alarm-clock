"""
ESP32 Retro Georgy Alarm Clock (MicroPython)
Doel: stabiel draaien op lage RAM met WiFi + NTP + retro web UI + alarm animaties.
"""

from machine import Pin, PWM, SoftI2C
import framebuf
import time
import json
import network
import socket
import gc

LOW_MEMORY_WEB_MODE = False

# WLAN vroeg alloceren terwijl heap nog maximaal vrij is
_WLAN = None
try:
    gc.collect()
    _WLAN = network.WLAN(network.STA_IF)
except Exception as _e:
    print("! WLAN pre-alloc mislukt:", _e)

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
WEBSERVER_START_DELAY_MS = 0
WIFI_MANUAL_ON_MS = 120000
WIFI_DAILY_CHECK_MS = 60000
WIFI_DAILY_RETRY_MS = 3600000
UP_BUTTON_PIN = 13
DOWN_BUTTON_PIN = 12
SET_BUTTON_PIN = 14
DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

ALARM_TONES = {
    "classic": {
        "label": "Classic Beep",
        "pattern": ((1200, 420, 3), (0, 0, 2), (1000, 420, 3), (0, 0, 4)),
    },
}
RETRO_TONE_KEYS = ("classic",)

ALARM_RANDOM_KEY = "retro_random"
RETRO_RANDOM_POOL = RETRO_TONE_KEYS
_RTTL_FRAME_MS = 50


def get_alarm_tone_options():
    options = []
    for tone_key in ALARM_TONES:
        options.append({"key": tone_key, "label": ALARM_TONES[tone_key]["label"]})
    return options


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

_HTML_FILE = "index.html"
_HTML_FILE_LITE = "index_lite.html"


def _send_all(sock, data):
    view = memoryview(data)
    while len(view):
        sent = sock.send(view)
        if sent is None or sent <= 0:
            break
        view = view[sent:]


def _send_html_response(sock, filename):
    _send_all(sock, b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
    try:
        with open(filename, "rb") as f:
            while True:
                chunk = f.read(512)
                if not chunk:
                    break
                _send_all(sock, chunk)
    except Exception as e:
        body = "<html><body>Fout: kan {} niet laden: {}</body></html>".format(filename, e)
        _send_all(sock, body.encode())


# HTML wordt van disk naar socket gestreamd via _send_html_response() - niet in RAM opgeslagen.
def enable_low_memory_web_mode():
    global LOW_MEMORY_WEB_MODE
    if LOW_MEMORY_WEB_MODE:
        return
    LOW_MEMORY_WEB_MODE = True
    gc.collect()


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
    def __init__(self, ssid, password, timeout=15):
        self.ssid = ssid
        self.password = password
        self.timeout = timeout
        global _WLAN
        if _WLAN is None:
            gc.collect()
            gc.collect()
            try:
                _WLAN = network.WLAN(network.STA_IF)
            except Exception as e:
                raise OSError("WiFi Out of Memory") from e
        self.sta = _WLAN

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
        print("\n=== ESP32 RETRO GEORGY ALARM OPSTARTEN ===\n")
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
        self.wifi_ssid = ssid
        self.wifi_password = pwd
        self.tone = self._normalize_tone_key(self.tone)

        self.clock = ClockCore(timezone)
        self.alarm_until = None
        self.alarm_started_ms = None
        self.active_tone = self.tone
        self.alarm_edit_mode = False
        self.alarm_edit_hour = 7
        self.alarm_edit_minute = 0
        self.alarm_edit_day_key = "mon"
        self.last_schedule_fire = None
        self.alarm_schedule = self._default_alarm_schedule()
        if self.config:
            self.alarm_schedule = self._normalize_alarm_schedule(self.config.get("alarm_schedule", None, self.alarm_schedule))

        self.wifi = None
        self.wifi_ok = False
        self.wifi_disabled = False
        self.wifi_reconnect_after_ms = 0
        self.wifi_auto_off_ms = time.ticks_add(time.ticks_ms(), 30 * 60 * 1000)
        self.webserver_ready_after_ms = None
        self._ntp_synced_once = False
        self.startup_ip_until = None
        self.sock = None
        self.wifi_manual_until = None
        self.last_daily_sync_key = None
        self.next_daily_check_ms = time.ticks_add(time.ticks_ms(), WIFI_DAILY_CHECK_MS)
        self.next_daily_sync_attempt_ms = time.ticks_ms()

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

        self.btn_up = Pin(UP_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.btn_down = Pin(DOWN_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.btn_set = Pin(SET_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self._button_state = {
            "set": {"pressed": False, "start": 0, "long": False, "last_edge": 0},
            "up": {"pressed": False, "start": 0, "long": False, "last_edge": 0},
            "down": {"pressed": False, "start": 0, "long": False, "last_edge": 0},
        }

        print("WiFi: verbinden...")
        gc.collect()
        gc.collect()
        if self._ensure_wifi_connected():
            self.clock.sync_ntp()
            self._ntp_synced_once = True
            t2 = self.clock.read_time()
            self.last_daily_sync_key = (int(t2[0]), int(t2[1]), int(t2[2]))
        else:
            print("WiFi: niet verbonden bij opstarten")

    def _prepare_for_wifi_attempt(self):
        gc.collect()
        gc.collect()
        gc.collect()

    def _close_webserver(self):
        try:
            if self.sock:
                self.sock.close()
        except:
            pass
        self.sock = None

    def _disable_wifi(self):
        self._close_webserver()
        try:
            if self.wifi and self.wifi.sta:
                try:
                    self.wifi.sta.disconnect()
                except:
                    pass
                try:
                    self.wifi.sta.active(False)
                except:
                    pass
        except:
            pass
        self.wifi_ok = False

    def _ensure_wifi_connected(self):
        gc.collect()
        self.wifi_ok = False
        try:
            if self.wifi is None:
                self.wifi = WiFiManagerLite(self.wifi_ssid, self.wifi_password, timeout=15)
            self.wifi_ok = self.wifi.connect()
        except Exception as e:
            self.wifi_ok = False
            print("! WiFi fout:", e)
            gc.collect()
            return False

        if self.wifi_ok:
            self.startup_ip_until = time.ticks_add(time.ticks_ms(), 5000)
            self.webserver_ready_after_ms = time.ticks_add(time.ticks_ms(), WEBSERVER_START_DELAY_MS)
            self._start_webserver_if_ready()
            return True
        return False

    def _start_webserver_if_ready(self):
        if not self.wifi_ok or self.sock is not None:
            return

        if self.webserver_ready_after_ms is not None and time.ticks_diff(time.ticks_ms(), self.webserver_ready_after_ms) < 0:
            return

        ip = self.wifi.get_ip() if self.wifi else "0.0.0.0"
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", WIFI_PORT))
            self.sock.listen(2)
            self.sock.settimeout(0)
            print("Web:", "http://{}".format(ip))
        except Exception as e:
            print("! Webserver start fout:", e)
            try:
                if self.sock:
                    self.sock.close()
            except:
                pass
            self.sock = None
            self.webserver_ready_after_ms = time.ticks_add(time.ticks_ms(), 5000)

    def _handle_wifi_state(self):
        now = time.ticks_ms()

        # Auto-off na 30 minuten na opstarten
        if not self.wifi_disabled and self.wifi_auto_off_ms is not None and time.ticks_diff(now, self.wifi_auto_off_ms) >= 0:
            self.wifi_auto_off_ms = None
            self._disable_wifi()
            self.wifi_disabled = True
            print("WiFi auto-uit na 30 min")

        # WiFi altijd aan (tenzij handmatig uitgeschakeld): herverbinden als nodig
        if not self.wifi_disabled:
            if not self.wifi_ok or not self.wifi or not self.wifi.is_connected():
                # Maximaal 1x per 30 sec proberen (voorkomt blokkering elke loop-cycle)
                if time.ticks_diff(now, self.wifi_reconnect_after_ms) >= 0:
                    self._ensure_wifi_connected()
                    self.wifi_reconnect_after_ms = time.ticks_add(now, 30000)
            self._start_webserver_if_ready()

        if time.ticks_diff(now, self.next_daily_check_ms) >= 0:
            self.next_daily_check_ms = time.ticks_add(now, WIFI_DAILY_CHECK_MS)
            t = self.clock.read_time()
            day_key = (int(t[0]), int(t[1]), int(t[2]))
            # Dagelijkse NTP sync om 12:00: WiFi aan, sync, WiFi uit
            if int(t[3]) >= 12 and self.last_daily_sync_key != day_key and time.ticks_diff(now, self.next_daily_sync_attempt_ms) >= 0:
                print("Dagelijkse NTP sync (12:00)...")
                if self._ensure_wifi_connected() and self.clock.sync_ntp():
                    t2 = self.clock.read_time()
                    self.last_daily_sync_key = (int(t2[0]), int(t2[1]), int(t2[2]))
                    self.next_daily_sync_attempt_ms = now
                    print("Dagelijkse sync OK, WiFi weer uit")
                else:
                    self.next_daily_sync_attempt_ms = time.ticks_add(now, WIFI_DAILY_RETRY_MS)
                    print("Dagelijkse sync mislukt, volgende poging over 1 uur")
                # Altijd WiFi uitzetten na de sync poging
                self._disable_wifi()
                self.wifi_disabled = True
                self.wifi_auto_off_ms = None

    def _default_alarm_schedule(self):
        return {k: {"enabled": False, "hour": 7, "minute": 0} for k in DAY_KEYS}

    def _normalize_alarm_schedule(self, raw):
        out = self._default_alarm_schedule()
        if not isinstance(raw, dict):
            return out
        for k in DAY_KEYS:
            row = raw.get(k, {}) if isinstance(raw.get(k, {}), dict) else {}
            out[k]["enabled"] = bool(row.get("enabled", False))
            out[k]["hour"] = int(row.get("hour", 7)) % 24
            out[k]["minute"] = int(row.get("minute", 0)) % 60
        return out

    def _check_scheduled_alarm(self):
        if self.alarm_until is not None:
            return
        t = self.clock.read_time()
        day_key = DAY_KEYS[(int(t[6]) - 1) % 7]
        sch = self.alarm_schedule.get(day_key, {})
        if not sch.get("enabled", False):
            return
        if int(sch.get("hour", -1)) != int(t[3]) or int(sch.get("minute", -1)) != int(t[4]):
            return
        fire_key = (t[0], t[1], t[2], t[3], t[4])
        if self.last_schedule_fire == fire_key:
            return
        self.last_schedule_fire = fire_key
        self.active_tone = self._tone_now()
        self.alarm_started_ms = time.ticks_ms()
        self.alarm_until = time.ticks_add(time.ticks_ms(), 60 * 1000)

    def _stop_alarm(self):
        self.alarm_until = None
        self.alarm_started_ms = None
        self.buzzer.duty(0)

    def _current_day_alarm(self):
        t = self.clock.read_time()
        day_idx = (int(t[6]) - 1) % 7
        day_key = DAY_KEYS[day_idx]
        row = self.alarm_schedule.get(day_key, {"enabled": False, "hour": 7, "minute": 0})
        return day_key, row

    def _toggle_today_alarm(self):
        day_key, row = self._current_day_alarm()
        enabled = not bool(row.get("enabled", False))
        self.alarm_schedule[day_key] = {
            "enabled": enabled,
            "hour": int(row.get("hour", 7)) % 24,
            "minute": int(row.get("minute", 0)) % 60,
        }
        if self.config:
            self.config.config["alarm_schedule"] = self.alarm_schedule
            self.config.save()
        print("Alarm {} {} {:02d}:{:02d}".format("AAN" if enabled else "UIT", day_key, self.alarm_schedule[day_key]["hour"], self.alarm_schedule[day_key]["minute"]))

    def _enter_alarm_edit_mode(self):
        day_key, row = self._current_day_alarm()
        self.alarm_edit_mode = True
        self.alarm_edit_day_key = day_key
        self.alarm_edit_hour = int(row.get("hour", 7)) % 24
        self.alarm_edit_minute = int(row.get("minute", 0)) % 60
        print("Alarm instellen {} {:02d}:{:02d}".format(day_key, self.alarm_edit_hour, self.alarm_edit_minute))

    def _save_alarm_edit_mode(self):
        self.alarm_schedule[self.alarm_edit_day_key] = {
            "enabled": True,
            "hour": int(self.alarm_edit_hour) % 24,
            "minute": int(self.alarm_edit_minute) % 60,
        }
        self.alarm_edit_mode = False
        if self.config:
            self.config.config["alarm_schedule"] = self.alarm_schedule
            self.config.save()
        print("Alarm opgeslagen {} {:02d}:{:02d}".format(self.alarm_edit_day_key, self.alarm_edit_hour, self.alarm_edit_minute))

    def _set_short_press(self):
        if self.alarm_until is not None:
            self._stop_alarm()
            return
        if self.alarm_edit_mode:
            return
        self._toggle_today_alarm()

    def _set_long_press(self):
        if self.alarm_until is not None:
            self._stop_alarm()
            return
        if self.alarm_edit_mode:
            self._save_alarm_edit_mode()
            return
        self._enter_alarm_edit_mode()

    def _up_short_press(self):
        if not self.alarm_edit_mode:
            return
        self.alarm_edit_hour = (self.alarm_edit_hour + 1) % 24

    def _down_short_press(self):
        if not self.alarm_edit_mode:
            return
        self.alarm_edit_minute = (self.alarm_edit_minute + 1) % 60

    def _down_long_press(self):
        if self.alarm_until is not None:
            self._stop_alarm()
            return
        if self.alarm_edit_mode:
            return

        if self.wifi_disabled:
            # WiFi was uit: zet aan en reset auto-off timer
            self.wifi_disabled = False
            self.wifi_auto_off_ms = time.ticks_add(time.ticks_ms(), 30 * 60 * 1000)
            print("WiFi AAN (auto-uit over 30 min)")
            if self._ensure_wifi_connected():
                ip = self.wifi.get_ip() if self.wifi else None
                print("WiFi verbonden:", ip if ip else "geen IP")
        else:
            # WiFi was aan: zet uit en annuleer auto-off timer
            self._disable_wifi()
            self.wifi_disabled = True
            self.wifi_auto_off_ms = None
            print("WiFi UIT")

    def _process_button(self, name, pin, short_cb=None, long_cb=None, long_press_ms=2000):
        state = self._button_state[name]
        now = time.ticks_ms()
        pressed = (pin.value() == 0)

        if pressed and not state["pressed"]:
            if time.ticks_diff(now, state["last_edge"]) < 120:
                return
            # One press should always silence the active alarm immediately.
            if self.alarm_until is not None:
                self._stop_alarm()
                state["pressed"] = True
                state["start"] = now
                state["long"] = True  # suppress short callback on release
                state["last_edge"] = now
                return
            state["pressed"] = True
            state["start"] = now
            state["long"] = False
            state["last_edge"] = now
            return

        if pressed and state["pressed"]:
            if long_cb and (not state["long"]) and time.ticks_diff(now, state["start"]) >= long_press_ms:
                long_cb()
                state["long"] = True
            return

        if (not pressed) and state["pressed"]:
            if time.ticks_diff(now, state["last_edge"]) < 50:
                state["pressed"] = False
                state["long"] = False
                state["last_edge"] = now
                return
            if (not state["long"]) and short_cb:
                short_cb()
            state["pressed"] = False
            state["long"] = False
            state["last_edge"] = now

    def _handle_buttons(self):
        self._process_button("set", self.btn_set, short_cb=self._set_short_press, long_cb=self._set_long_press)
        self._process_button("up", self.btn_up, short_cb=self._up_short_press)
        self._process_button("down", self.btn_down, short_cb=self._down_short_press, long_cb=self._down_long_press, long_press_ms=3000)

    def _normalize_tone_key(self, tone):
        legacy_map = {
            "retro_a": "retro_runner",
            "retro_b": "retro_orbit",
        }
        mapped = legacy_map.get(tone, tone)
        if mapped == ALARM_RANDOM_KEY or mapped in ALARM_TONES:
            return mapped
        return "classic"

    def _tone_now(self):
        selected = self._normalize_tone_key(self.tone)
        if selected == ALARM_RANDOM_KEY and len(RETRO_RANDOM_POOL) > 0:
            t = self.clock.read_time()
            selected = RETRO_RANDOM_POOL[((t[0] * 372) + (t[1] * 31) + t[2]) % len(RETRO_RANDOM_POOL)]
        return self._normalize_tone_key(selected)

    def _play(self, now_ms):
        if self.alarm_started_ms is None:
            self.alarm_started_ms = now_ms

        tone = self.active_tone
        tone_def = ALARM_TONES.get(tone, ALARM_TONES["classic"])
        pat = tone_def.get("pattern")
        if pat is None:
            pat = ALARM_TONES["classic"]["pattern"]
        total = 0
        for _f, _d, dur in pat:
            total += dur
        if total <= 0:
            self.buzzer.duty(0)
            return

        elapsed_ms = time.ticks_diff(now_ms, self.alarm_started_ms)
        if elapsed_ms < 0:
            elapsed_ms = 0
        pos = (elapsed_ms // _RTTL_FRAME_MS) % total

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

    def _serve_simple(self, c):
        try:
            c.settimeout(0.2)
        except:
            pass
        try:
            c.recv(256)
        except:
            pass
        ip = self.wifi.get_ip() if (self.wifi and self.wifi.is_connected()) else "offline"
        body = "ESP32 Alarm web alive\nip={}\n".format(ip)
        resp = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n" + body
        c.send(resp.encode())

    def _weekday_name(self, idx):
        names = ("Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag")
        return names[(int(idx) - 1) % 7]

    def _weekday_short(self, idx):
        names = ("ma", "di", "wo", "do", "vr", "za", "zo")
        return names[(int(idx) - 1) % 7]

    def _next_alarm_info(self, t):
        # Returns (day_str, hh, mm) for next alarm, or None if none
        # t[6] is weekday: 1=Mon ... 7=Sun, DAY_KEYS = ("mon","tue","wed","thu","fri","sat","sun")
        day_abbr = ("ma", "di", "wo", "do", "vr", "za", "zo")
        day_keys = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        cfg = self.alarm_schedule
        if not isinstance(cfg, dict):
            return None
        today_idx = (int(t[6]) - 1) % 7  # 0=Mon
        cur_h = int(t[3])
        cur_m = int(t[4])
        for offset in range(7):
            di = (today_idx + offset) % 7
            key = day_keys[di]
            alarm = cfg.get(key)
            if alarm is None:
                continue
            enabled = alarm.get("enabled", False)
            if not enabled:
                continue
            try:
                hh = int(alarm.get("hour", 0))
                mm = int(alarm.get("minute", 0))
            except Exception:
                continue
            if offset == 0:
                # today: only if alarm time is still in future
                if hh > cur_h or (hh == cur_h and mm > cur_m):
                    return ("", hh, mm)
            else:
                return (day_abbr[di], hh, mm)
        return None

    def _draw_alarm_icon(self, x, y):
        # 8x8 pixel alarm bell icon
        pixels = (
            0b00010000,
            0b00111000,
            0b00111000,
            0b01111100,
            0b01111100,
            0b11111110,
            0b00010000,
            0b00111000,
        )
        for row, bits in enumerate(pixels):
            for col in range(8):
                if bits & (0x80 >> col):
                    self.display.pixel(x + col, y + row, 1)

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

    def _draw_big_time(self, hh, mm, y_offset=0):
        text = "{:02d}:{:02d}".format(hh, mm)
        max_height = 36  # Keep room for alarm + date lines below.
        scale = 1
        width = 0

        for cand in range(8, 0, -1):
            cand_width = 0
            for ch in text:
                glyph = BIG_TIME_GLYPHS.get(ch)
                if glyph:
                    cand_width += (len(glyph[0]) * cand) + cand
            cand_width = max(0, cand_width - cand)
            if cand_width <= WIDTH and (5 * cand) <= max_height:
                scale = cand
                width = cand_width
                break

        x = max(0, (WIDTH - width) // 2)
        y = y_offset + max(0, (max_height - (5 * scale)) // 2)
        for ch in text:
            x += self._draw_big_char(ch, x, y, scale)

    def _draw_startup_ip(self):
        self.display.fill(0)
        self.display.text("WiFi verbonden", 8, 8, 1)
        ip = self.wifi.get_ip() if self.wifi_ok else None
        self.display.text("IP adres:", 8, 26, 1)
        self.display.text(ip if ip else "geen netwerk", 8, 40, 1)
        self.display.show()

    def _draw_wifi_status_icon(self, x, y):
        # Tiny 8x8 WiFi icon (bottom-right status indicator)
        self.display.pixel(x + 3, y + 7, 1)
        self.display.pixel(x + 3, y + 6, 1)
        self.display.line(x + 2, y + 5, x + 4, y + 5, 1)
        self.display.line(x + 1, y + 4, x + 5, y + 4, 1)
        self.display.line(x, y + 3, x + 6, y + 3, 1)

    def _draw_wifi_off_icon(self, x, y):
        # Tiny 8x8 WiFi-off icon: arcs + diagonale streep
        self.display.pixel(x + 3, y + 7, 1)
        self.display.pixel(x + 3, y + 6, 1)
        self.display.line(x + 2, y + 5, x + 4, y + 5, 1)
        self.display.line(x + 1, y + 4, x + 5, y + 4, 1)
        self.display.line(x, y + 3, x + 6, y + 3, 1)
        # Streep er doorheen
        self.display.line(x, y + 1, x + 6, y + 7, 1)

    def _draw_clock_layout(self):
        t = self.clock.read_time()
        self.display.fill(0)
        self._draw_big_time(t[3], t[4])
        # Alarm line (y=38): bij uitgeschakeld alarm geen icoon, maar wel --:-- placeholder.
        day_key = DAY_KEYS[(int(t[6]) - 1) % 7]
        day_alarm = self.alarm_schedule.get(day_key, {})
        if day_alarm.get("enabled", False):
            alarm_text = "{:02d}:{:02d}".format(int(day_alarm.get("hour", 7)) % 24,
                                                 int(day_alarm.get("minute", 0)) % 60)
            self._draw_alarm_icon(0, 38)
            self.display.text(alarm_text, 10, 38, 1)
        else:
            self.display.text("--:--", 10, 38, 1)
        # Day + date lines
        self.display.text(self._weekday_short(t[6]), 0, 50, 1)
        self.display.text("{:02d}-{:02d}".format(t[2], t[1]), 24, 50, 1)
        if self.wifi_disabled:
            self._draw_wifi_off_icon(WIDTH - 8, HEIGHT - 8)
        elif self.wifi_ok and self.wifi and self.wifi.is_connected():
            self._draw_wifi_status_icon(WIDTH - 8, HEIGHT - 8)
        self.display.show()

    def _draw_alarm_animation(self, frame):
        # Ultra-lite 6-keyframe animation (32x32 look) without bitmap arrays.
        keyframes = (
            (-2, -1, 1, 0, 0),
            (-1,  0, 0, 1, 1),
            ( 0,  1, 1, 0, 2),
            ( 1,  0, 0, 1, 3),
            ( 2, -1, 1, 0, 4),
            ( 0,  0, 0, 0, 5),
        )
        shake_x, bell_tilt, pulse, blink, hand_pose = keyframes[frame % 6]

        self.display.fill(0)
        self.display.text("ALARM!", 36, 0, 1)

        # Center a 32x32 style clock body.
        x = 48 + shake_x
        y = 16
        w = 32
        h = 32

        # Clock body
        self.display.rect(x, y, w, h, 1)
        self.display.rect(x + 2, y + 2, w - 4, h - 4, 1)

        # Feet
        self.display.line(x + 5, y + h, x + 2, y + h + 5, 1)
        self.display.line(x + w - 6, y + h, x + w - 3, y + h + 5, 1)

        # Bells with simple tilt keyframe
        by = y - 6
        self.display.line(x + 5 + bell_tilt, by + 5, x + 12 + bell_tilt, by, 1)
        self.display.line(x + w - 6 - bell_tilt, by + 5, x + w - 13 - bell_tilt, by, 1)

        # Ring waves
        if pulse:
            self.display.pixel(x - 3, by + 1, 1)
            self.display.pixel(x - 5, by + 3, 1)
            self.display.pixel(x + w + 3, by + 1, 1)
            self.display.pixel(x + w + 5, by + 3, 1)

        # Dial center
        cx = x + (w // 2)
        cy = y + (h // 2)
        self.display.pixel(cx, cy, 1)

        # Hour hand (fixed) + minute hand (6 key poses)
        self.display.line(cx, cy, cx - 4, cy - 2, 1)
        if hand_pose == 0:
            self.display.line(cx, cy, cx, cy - 9, 1)
        elif hand_pose == 1:
            self.display.line(cx, cy, cx + 5, cy - 7, 1)
        elif hand_pose == 2:
            self.display.line(cx, cy, cx + 8, cy - 2, 1)
        elif hand_pose == 3:
            self.display.line(cx, cy, cx + 8, cy + 2, 1)
        elif hand_pose == 4:
            self.display.line(cx, cy, cx + 5, cy + 7, 1)
        else:
            self.display.line(cx, cy, cx, cy + 9, 1)

        # Bottom alert strip
        if blink:
            self.display.fill_rect(20, 54, 88, 8, 1)
        else:
            self.display.rect(20, 54, 88, 8, 1)

        self.display.show()

    def _draw_alarm_edit(self):
        self.display.fill(0)
        self.display.text("ALARM INSTELLEN", 0, 0, 1)
        self._draw_big_time(self.alarm_edit_hour, self.alarm_edit_minute, y_offset=14)
        self.display.show()

    def serve_once(self, c):
        req = self._request(c)
        line = req.split("\r\n", 1)[0]
        parts = line.split(" ")
        method = parts[0] if len(parts) > 0 else ""
        path = parts[1] if len(parts) > 1 else ""
        path_no_query = path.split("?", 1)[0]
        if method == "GET" and path_no_query == "/":
            filename = _HTML_FILE_LITE if LOW_MEMORY_WEB_MODE else _HTML_FILE
            _send_html_response(c, filename)
            gc.collect()
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
                "alarm_schedule": self.alarm_schedule,
                "alarm_tones": get_alarm_tone_options()
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
            tone = self._normalize_tone_key(tone)
            self.tone = tone
            self.volume = max(0, min(100, vol))
            if self.config:
                self.config.set("alarm_sound", "tone", self.tone)
                self.config.set("alarm_sound", "volume", self.volume)
            c.send(self._json({"ok": True}))
            return
        if method == "POST" and path == "/api/set-alarm-schedule":
            d = self._parse(req)
            self.alarm_schedule = self._normalize_alarm_schedule(d.get("alarm_schedule", {}))
            if self.config:
                self.config.config["alarm_schedule"] = self.alarm_schedule
                self.config.save()
            c.send(self._json({"ok": True}))
            return
        if method == "POST" and path == "/api/test-alarm":
            d = self._parse(req)
            sec = int(d.get("seconds", 10) or 10)
            sec = max(1, min(60, sec))
            self.active_tone = self._tone_now()
            self.alarm_started_ms = time.ticks_ms()
            self.alarm_until = time.ticks_add(time.ticks_ms(), sec * 1000)
            c.send(self._json({"ok": True}))
            return
        c.send("HTTP/1.1 404 Not Found\r\n\r\n".encode())

    def run(self):
        print("Hoofdloop gestart")

        frame = 0
        while True:
            try:
                self._handle_buttons()
                self._handle_wifi_state()

                if self.sock:
                    try:
                        c, _a = self.sock.accept()
                        self.serve_once(c)
                        c.close()
                    except OSError:
                        pass

                if self.alarm_until is not None:
                    if time.ticks_diff(time.ticks_ms(), self.alarm_until) >= 0:
                        self._stop_alarm()
                    else:
                        self._play(time.ticks_ms())
                else:
                    self._check_scheduled_alarm()
                    self.buzzer.duty(0)

                if frame > 0 and frame % 18000 == 0 and self.wifi_ok:
                    self.clock.sync_ntp()

                if self.display:
                    if self.alarm_until is not None:
                        self._draw_alarm_animation(frame)
                    elif self.alarm_edit_mode:
                        self._draw_alarm_edit()
                    elif self.startup_ip_until is not None and time.ticks_diff(self.startup_ip_until, time.ticks_ms()) > 0:
                        self._draw_startup_ip()
                    else:
                        self.startup_ip_until = None
                        self._draw_clock_layout()

                frame += 1
                time.sleep(0.05)
            except Exception as e:
                print("Loop fout:", e)
                time.sleep(0.5)


if __name__ == "__main__":
    app = App()
    app.run()

