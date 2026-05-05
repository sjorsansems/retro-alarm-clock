"""
ESP32 Retro Georgy Alarm Clock (MicroPython)
Doel: stabiel draaien op lage RAM met WiFi + NTP + retro web UI + alarm animaties.
"""

from machine import Pin, SoftI2C
import framebuf
import time
import json
import network
import socket
import gc
import esp32

# Agressieve garbage collection en PSRAM setup
gc.enable()
gc.collect()
try:
    esp32.memory_info()
except:
    pass
try:
    gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())
except:
    pass

LOW_MEMORY_WEB_MODE = False

# WLAN lazy init — niet pre-alloceren
_WLAN = None

try:
    from config_manager import ConfigManager
except ImportError:
    ConfigManager = None

try:
    from ntp_time_sync import NTPTimeSync
except ImportError:
    NTPTimeSync = None

try:
    from ds3231 import DS3231, AT24C32
except ImportError:
    DS3231 = None
    AT24C32 = None

try:
    from dfplayer import DFPlayer
except ImportError:
    DFPlayer = None

try:
    from neopixel_driver import NeopixelDriver
except ImportError:
    NeopixelDriver = None

# ESP32-S3 DevKitC-1 pinnen
SDA_PIN = 8   # gelabeld SDA op het board (OLED)
SCL_PIN = 9   # gelabeld SCL op het board (OLED)
DS3231_SDA_PIN = 5   # aparte I2C bus voor DS3231 RTC
DS3231_SCL_PIN = 6
I2C_FREQ = 100_000
# Buzzer uitgeschakeld — DFPlayer MP3 wordt gebruikt als alarm

# DFPlayer Mini: ESP32-S3 DevKitC-1
# GPIO17 = UART1 TX (gelabeld TXD1) -> 1kΩ -> DFPlayer RX
# GPIO18 = UART1 RX (gelabeld RXD1) <--------- DFPlayer TX
# Optioneel: BUSY-pin (actief-laag als er afgespeeld wordt)
DFPLAYER_UART_ID  = 1
DFPLAYER_TX_PIN   = 17
DFPLAYER_RX_PIN   = 18
DFPLAYER_BUSY_PIN = None   # bijv. 4 als je de BUSY-pin aansluit
DFPLAYER_TRACK    = 1      # track-nummer dat tijdens alarm afgespeeld wordt (1.mp3 op SD)

# WS2812B Addressable LEDs (8-LED strip)
WS2812_PIN = 2  # bevestigd werkend: GPIO2 + bitstream + GRB
WS2812_COUNT = 8  # 8 LEDs
WIDTH = 128
HEIGHT = 64
SH1106_COL_OFFSET = 2
WIFI_PORT = 80
WEBSERVER_START_DELAY_MS = 0
WIFI_MANUAL_ON_MS = 120000
WIFI_DAILY_CHECK_MS = 60000
WIFI_DAILY_RETRY_MS = 3600000
WIFI_MIN_FREE_HEAP = 35000
WIFI_CONNECT_TIMEOUT_S = 8
DEFAULT_WIFI_SSID = "SL2_IOT"
ALARM_INTRO_MS = 2500
ALARM_BOSS_MS = 20000
NIGHT_DIM_START_HOUR = 22
NIGHT_DIM_END_HOUR = 7
UP_BUTTON_PIN = 13    # Touch13 / ADC2_2 — vrij op S3 DevKitC-1
DOWN_BUTTON_PIN = 12  # Touch12 / ADC2_1 — vrij
SET_BUTTON_PIN = 14   # Touch14 / ADC2_3 — vrij
DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# Aantal MP3-nummers op de SD-kaart (lied 1 t/m N)
DFPLAYER_TRACK_COUNT = 9


def get_alarm_tone_options():
    labels = {
        1: "Zelda", 2: "Mario", 3: "Synthwave", 4: "Sonic", 
        5: "Metroid", 6: "Pokemon", 7: "Tetris", 8: "Moonstone", 9: "Arcade"
    }
    schemes = {
        1: "Groen -> goud pulse",
        2: "Rood/geel checker",
        3: "Neon roze -> paars golf",
        4: "Cyaan/blauw strobe",
        5: "Oranje -> rood",
        6: "Geel met rode accenten",
        7: "Regenboog cyclus",
        8: "Maanblauw met fakkel-goud pulse",
        9: "Multicolor strobe",
    }
    return [
        {
            "key": str(i),
            "label": labels.get(i, "Lied {}".format(i)),
            "scheme": schemes.get(i, "Onbekend"),
        }
        for i in range(1, DFPLAYER_TRACK_COUNT + 1)
    ]


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
    def __init__(self, ssid, password, timeout=WIFI_CONNECT_TIMEOUT_S):
        self.ssid = ssid
        self.password = password
        self.timeout = timeout
        global _WLAN
        if _WLAN is None:
            # Agressieve RAM cleanup voordat WiFi wordt geladen
            for _ in range(3):
                gc.collect()
                time.sleep(0.1)
            try:
                _WLAN = network.WLAN(network.STA_IF)
                # WLAN voorbij initi, nog niet actief
            except Exception as e:
                print("! WiFi pre-init fout, retrying...")
                for _ in range(5):
                    gc.collect()
                    time.sleep(0.1)
                try:
                    _WLAN = network.WLAN(network.STA_IF)
                except Exception:
                    raise OSError("WiFi Out of Memory")
        self.sta = _WLAN

    def connect(self):
        try:
            if self.sta.isconnected():
                return True
        except:
            pass

        if not self.ssid:
            print("! WiFi fout: SSID is leeg")
            return False

        try:
            # Minder agressief dan telkens active(False)->active(True),
            # want dat kan op sommige firmware builds instabiel zijn.
            if not self.sta.active():
                self.sta.active(True)
            time.sleep(0.5)

            # Begin met een schone connect-staat.
            try:
                self.sta.disconnect()
            except:
                pass

            print("WiFi: verbinden met '{}'...".format(self.ssid))
            self.sta.connect(self.ssid, self.password)
            start = time.ticks_ms()
            while not self.sta.isconnected():
                st = self.sta.status()
                # ESP32 statuscodes: -3 wrong password, -2 no AP, -1 fail
                if st in (-3, -2, -1):
                    if st == -3:
                        print("! WiFi fout: verkeerd wachtwoord")
                    elif st == -2:
                        print("! WiFi fout: SSID niet gevonden (2.4GHz?)")
                    else:
                        print("! WiFi fout: connect mislukt")
                    return False
                if time.ticks_diff(time.ticks_ms(), start) > self.timeout * 1000:
                    print("! WiFi timeout na {}s, status={}".format(self.timeout, self.sta.status()))
                    return False
                time.sleep(0.3)
                gc.collect()  # Agressieve GC tijdens connect
            ip = self.sta.ifconfig()[0]
            print("✓ WiFi verbonden, IP={}".format(ip))
            return True
        except KeyboardInterrupt:
            # Laat app doorlopen zonder crash als connect wordt onderbroken.
            print("! WiFi connect onderbroken")
            try:
                self.sta.disconnect()
            except:
                pass
            return False
        except Exception as e:
            print("! WiFi connect fout:", e)
            gc.collect()
            return False

    def is_connected(self):
        try:
            return self.sta and self.sta.isconnected()
        except:
            return False

    def get_ip(self):
        try:
            if self.is_connected():
                return self.sta.ifconfig()[0]
        except:
            pass
        return None


class ClockCore:
    def __init__(self, timezone_name="Europe/Amsterdam"):
        self.timezone_name = timezone_name
        self.soft_epoch = None
        self.soft_ticks = 0
        self.last_sync = 0
        self.rtc = None  # wordt gezet door App na I2C init

    @staticmethod
    def _is_leap_year(year):
        return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

    @staticmethod
    def _last_sunday_of_month(year, month):
        if month in (1, 3, 5, 7, 8, 10, 12):
            last_day = 31
        elif month in (4, 6, 9, 11):
            last_day = 30
        else:
            last_day = 29 if ClockCore._is_leap_year(year) else 28
        for day in range(last_day, 0, -1):
            wd = time.localtime(time.mktime((year, month, day, 12, 0, 0, 0, 0)))[6]  # 0=ma
            if wd == 6:  # zondag
                return day
        return last_day

    @staticmethod
    def _is_dst_nl(year, month, day):
        if month < 3 or month > 10:
            return False
        if 3 < month < 10:
            return True
        if month == 3:
            return day >= ClockCore._last_sunday_of_month(year, 3)
        return day < ClockCore._last_sunday_of_month(year, 10)

    @staticmethod
    def _utc_to_amsterdam(utc_tuple):
        y, m, d, hh, mm, ss = utc_tuple[:6]
        offset = 2 if ClockCore._is_dst_nl(y, m, d) else 1
        base = (y, m, d, hh, mm, ss, 0, 0)
        shifted = time.localtime(time.mktime(base) + offset * 3600)
        return (shifted[0], shifted[1], shifted[2], shifted[3], shifted[4], shifted[5], shifted[6] + 1, shifted[7])

    def _tz(self, utc_tuple):
        if self.timezone_name == "Europe/Amsterdam" and NTPTimeSync:
            t = NTPTimeSync.time_tuple_to_dutch(utc_tuple)
            if len(t) >= 7:
                t = t[:6] + (t[6] + 1,) + t[7:]
            return t, ("CEST" if NTPTimeSync.is_dst(utc_tuple[0], utc_tuple[1], utc_tuple[2]) else "CET")
        if self.timezone_name == "Europe/Amsterdam":
            t = self._utc_to_amsterdam(utc_tuple)
            return t, ("CEST" if self._is_dst_nl(utc_tuple[0], utc_tuple[1], utc_tuple[2]) else "CET")
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
        # Lees bij voorkeur rechtstreeks van DS3231
        if self.rtc is not None:
            try:
                t = self.rtc.datetime()   # (yr, mo, day, hr, min, sec, wd)
                # DS3231 bewaart in deze app al lokale tijd; niet opnieuw timezone-shiften.
                return (t[0], t[1], t[2], t[3], t[4], t[5], t[6], 0)
            except Exception:
                pass
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
        # Schrijf ook naar DS3231 als die beschikbaar is
        if self.rtc is not None:
            try:
                import time as _t
                wd = _t.localtime(self.soft_epoch)[6] + 1  # 1=ma
                self.rtc.set_datetime(int(y), int(m), int(d), int(hh), int(mm), int(ss), wd)
            except Exception as _e:
                print("! DS3231 schrijven mislukt:", _e)
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
            print("✓ NTP Sync ({}) → ook naar DS3231 geschreven".format(label) if self.rtc else "✓ NTP Sync ({})".format(label))
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
        self.tone = "1"
        self.volume = 70
        wifi_source = "fallback"
        if self.config:
            self.tone = self.config.get("alarm_sound", "tone", "1")
            self.volume = int(self.config.get("alarm_sound", "volume", 70) or 70)
            timezone = self.config.get("ntp", "timezone", "Europe/Amsterdam")
            raw_ssid = self.config.get("wifi", "ssid", None)
            raw_pwd = self.config.get("wifi", "password", None)
            ssid = str(raw_ssid or "").strip()
            pwd = str(raw_pwd or "")
            if ssid:
                wifi_source = "config.json"
            if getattr(self.config, "last_load_error", None):
                print("! Config waarschuwing:", self.config.last_load_error)
        else:
            timezone, ssid, pwd = "Europe/Amsterdam", "", ""

        if not ssid:
            ssid = DEFAULT_WIFI_SSID
            wifi_source = "defaults"

        print("WiFi cfg: '{}' ({})".format(ssid, wifi_source))
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
        self.alarm_combo = self._default_alarm_combo()
        if self.config:
            self.alarm_combo = self._normalize_alarm_combo(self.config.get("alarm_combo", None, self.alarm_combo))

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
        self._display_dim_state = None
        self._weather_phase = 0
        self._rtc_temp = None
        self._rtc_temp_next_ms = 0
        self._weather_code = None      # WMO weathercode van Open-Meteo
        self._weather_temp = None      # buitentemperatuur °C (int)
        self._weather_next_ms = 0      # tijdstip eerste fetch (meteen bij opstart)
        self._weather_interval_ms = 6 * 3600 * 1000  # 4x per dag
        self._easter_active_until = None
        self._easter_message = ""
        self._easter_key = None
        # Klok-transitie animatie state
        self._transition_pending = True   # eerste keer na intro altijd animeren
        self._last_hour_shown = -1        # voor uur-omslag detectie
        self._transition_step = 0         # huidige frame binnen een lopende transitie
        self._transition_id = 0           # welke transitie (0-4)
        self._transition_active = False   # animatie bezig?
        self._transition_use_leds = True  # LEDs bij deze transitie? (False bij uur-omslag)
        self._transition_buf = None       # snapshot van klokscherm (bytearray 128×64/8)

        self.i2c = SoftI2C(sda=Pin(SDA_PIN, pull=Pin.PULL_UP), scl=Pin(SCL_PIN, pull=Pin.PULL_UP), freq=I2C_FREQ)
        self.display = None
        try:
            dev = self.i2c.scan()
            if 0x3C in dev:
                self.display = SH1106_I2C(WIDTH, HEIGHT, self.i2c, 0x3C)
        except:
            pass

        # DS3231 RTC initialiseren op eigen I2C bus (GPIO5/6)
        self.eeprom = None
        self.i2c_rtc = None
        if DS3231 is not None:
            try:
                self.i2c_rtc = SoftI2C(sda=Pin(DS3231_SDA_PIN, pull=Pin.PULL_UP), scl=Pin(DS3231_SCL_PIN, pull=Pin.PULL_UP), freq=I2C_FREQ)
                self.clock.rtc = DS3231(self.i2c_rtc)
                t = self.clock.rtc.datetime()
                print("✓ DS3231 gereed: {:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(*t[:6]))
            except Exception as _e:
                print("! DS3231 niet gevonden:", _e)
                self.clock.rtc = None

        # AT24C32 EEPROM initialiseren (op dezelfde I2C bus als DS3231)
        if self.i2c_rtc is not None and AT24C32 is not None:
            try:
                self.eeprom = AT24C32(self.i2c_rtc)
                eeprom_schedule = self.eeprom.load_alarm_schedule()
                if eeprom_schedule is not None:
                    self.alarm_schedule = self._normalize_alarm_schedule(eeprom_schedule)
                    print("✓ Alarmschema geladen uit EEPROM")
                else:
                    print("✓ AT24C32 gereed (geen opgeslagen schema)")
            except Exception as _e:
                print("! AT24C32 niet gevonden:", _e)
                self.eeprom = None

        # DFPlayer/WS2812 lazy init: pas initialiseren zodra alarm start.
        self.dfplayer = None
        self._dfplayer_failed = False
        self._dfplayer_playing = False

        self.leds = None
        self._leds_failed = False
        self._led_sunrise_active = False

        # Zorg dat de strip direct bij boot in een bekende UIT-toestand staat.
        self._ensure_leds_ready()
        if self.leds is not None:
            try:
                self.leds.clear()
            except Exception:
                pass

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
        self._apply_display_brightness(force=True)

    def _prepare_for_wifi_attempt(self):
        gc.collect()
        gc.collect()
        gc.collect()

    def _ensure_dfplayer_ready(self):
        if self.dfplayer is not None or self._dfplayer_failed or DFPlayer is None:
            return self.dfplayer is not None
        try:
            dfvol = max(0, min(30, int(self.volume * 30 // 100)))
            self.dfplayer = DFPlayer(
                uart_id=DFPLAYER_UART_ID,
                tx_pin=DFPLAYER_TX_PIN,
                rx_pin=DFPLAYER_RX_PIN,
                busy_pin=DFPLAYER_BUSY_PIN,
                volume=dfvol,
            )
            print("✓ DFPlayer Mini gereed (volume {})".format(dfvol))
            return True
        except Exception as e:
            print("! DFPlayer init mislukt:", e)
            self._dfplayer_failed = True
            self.dfplayer = None
            gc.collect()
            return False

    def _ensure_leds_ready(self):
        if self.leds is not None or self._leds_failed or NeopixelDriver is None:
            return self.leds is not None
        try:
            self.leds = NeopixelDriver(pin=WS2812_PIN, num_leds=WS2812_COUNT)
            self.leds.set_brightness(92)  # 36% brightness om stroom-problemen te voorkomen
            self.leds.clear()
            print("✓ WS2812B LEDs gereed (GPIO{}, {} LEDs)".format(WS2812_PIN, WS2812_COUNT))
            return True
        except Exception as e:
            print("! WS2812B init mislukt:", e)
            self._leds_failed = True
            self.leds = None
            gc.collect()
            return False

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
                self.wifi = WiFiManagerLite(self.wifi_ssid, self.wifi_password, timeout=WIFI_CONNECT_TIMEOUT_S)
            self.wifi_ok = self.wifi.connect()
        except KeyboardInterrupt:
            self.wifi_ok = False
            print("! WiFi poging onderbroken")
            return False
        except Exception as e:
            self.wifi_ok = False
            print("! WiFi fout:", e)
            msg = str(e)
            if "Out of Memory" in msg or "Memory" in msg:
                # Bij WiFi OOM: web UI in low-memory modus, WiFi object vrijgeven,
                # en pas later opnieuw proberen.
                enable_low_memory_web_mode()
                self._disable_wifi()
                self.wifi = None
                self.wifi_reconnect_after_ms = time.ticks_add(time.ticks_ms(), 180000)
                print("! WiFi OOM: volgende poging over 3 minuten")
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

    def _default_alarm_combo(self):
        # Per dag een vaste track/scene-combo.
        return {
            "mon": "1", "tue": "2", "wed": "3", "thu": "1",
            "fri": "2", "sat": "3", "sun": "1",
        }

    def _normalize_alarm_combo(self, raw):
        out = self._default_alarm_combo()
        if not isinstance(raw, dict):
            return out
        for k in DAY_KEYS:
            out[k] = self._normalize_tone_key(raw.get(k, out[k]))
        return out

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
        self.active_tone = self._normalize_tone_key(self.alarm_combo.get(day_key, self._tone_now()))
        self.alarm_started_ms = time.ticks_ms()
        self.alarm_until = time.ticks_add(time.ticks_ms(), 60 * 1000)

    def _stop_alarm(self):
        self.alarm_until = None
        self.alarm_started_ms = None
        if self.dfplayer is not None:
            try:
                self.dfplayer.stop()
                self.dfplayer.set_volume(0)  # dempt idle ticking
            except Exception:
                pass
        self._dfplayer_playing = False
        if self.leds is not None:
            try:
                self.leds.clear()
            except Exception:
                pass
        self._led_sunrise_active = False

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
        if self.eeprom is not None:
            try:
                self.eeprom.save_alarm_schedule(self.alarm_schedule)
            except Exception:
                pass
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
        if self.eeprom is not None:
            try:
                self.eeprom.save_alarm_schedule(self.alarm_schedule)
            except Exception:
                pass
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
        try:
            n = int(tone)
            if 1 <= n <= DFPLAYER_TRACK_COUNT:
                return str(n)
        except (ValueError, TypeError):
            pass
        return "1"

    def _tone_now(self):
        return self._normalize_tone_key(self.tone)

    def _alarm_elapsed_ms(self):
        if self.alarm_started_ms is None:
            return 0
        return max(0, time.ticks_diff(time.ticks_ms(), self.alarm_started_ms))

    def _alarm_boss_level(self):
        ms = self._alarm_elapsed_ms()
        if ms < ALARM_BOSS_MS:
            return 0
        if ms < ALARM_BOSS_MS + 15000:
            return 1
        if ms < ALARM_BOSS_MS + 30000:
            return 2
        return 3

    def _alarm_intensity(self):
        # Intensity is used by LED and animation themes as a 0-100 value.
        ms = self._alarm_elapsed_ms()
        base = 25 + (ms // 1000)  # ramps up about 1% per second
        base += self._alarm_boss_level() * 10
        if base > 100:
            return 100
        if base < 0:
            return 0
        return int(base)

    def _play(self, now_ms):
        if self.alarm_started_ms is None:
            self.alarm_started_ms = now_ms

        # Initialiseer DFPlayer pas wanneer alarm echt start.
        df_ready = self._ensure_dfplayer_ready()
        if not df_ready and DFPlayer is not None and not self._dfplayer_failed:
            print("! DFPlayer niet klaar voor alarmstart")

        # --- DFPlayer: eenmalig starten met geselecteerd lied ---
        if self.dfplayer is not None:
            if not self._dfplayer_playing:
                try:
                    track = int(self.active_tone)
                    dfvol = max(0, min(30, int(self.volume * 30 // 100) + self._alarm_boss_level() * 3))
                    self.dfplayer.set_volume(dfvol)
                    # Speel exact bestand /MP3/000N.mp3 om SD-volgordeproblemen te vermijden.
                    self.dfplayer.play_mp3(track)
                    print("DFPlayer: speel MP3 track {} op volume {}".format(track, dfvol))
                    self._dfplayer_playing = True
                except Exception as e:
                    print("! DFPlayer play fout:", e)
            else:
                # Boss mode: volume traploos opvoeren terwijl alarm blijft lopen.
                try:
                    dfvol = max(0, min(30, int(self.volume * 30 // 100) + self._alarm_boss_level() * 3))
                    self.dfplayer.set_volume(dfvol)
                except Exception as e:
                    print("! DFPlayer volume fout:", e)
            return

        # Geen DFPlayer beschikbaar: stil (buzzer uitgeschakeld)
        return

    def _update_led_animation(self, frame):
        """Update WS2812B LED animations during alarm."""
        self._ensure_leds_ready()
        if not self.leds:
            return

        tone = getattr(self, 'active_tone', '1')
        intensity = self._alarm_intensity()

        # Per-tone theme should start immediately when alarm starts.
        self._led_sunrise_active = False

        # Get theme function and play animation
        try:
            theme_func = self.leds.get_theme_func(tone)
            theme_func(frame, intensity)
        except Exception:
            pass

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

    def _play_boot_intro(self):
        """8-bit retro boot intro: RETRO slaat neer van boven, GEORGY van onder.
        LED strip doet mee; 999.mp3 speelt op achtergrond.
        WiFi is al verbonden (gedaan in __init__).
        """
        if self.display is None:
            return

        # ── Helper: teken tekst 2× geschaald (via tijdelijk framebuf) ────────
        def draw_2x(text, x, y, col=1):
            w = len(text) * 8
            rb = (w + 7) // 8
            buf = bytearray(rb * 8)
            fb = framebuf.FrameBuffer(buf, w, 8, framebuf.MONO_HLSB)
            fb.fill(0)
            fb.text(text, 0, 0, 1)
            for ty in range(8):
                for tx in range(w):
                    if fb.pixel(tx, ty):
                        self.display.fill_rect(x + tx * 2, y + ty * 2, 2, 2, col)

        # ── Helper: spat-pixels (puin) ───────────────────────────────────────
        def debris(seed, y_impact, count=12):
            for i in range(count):
                px = (seed * 17 + i * 37) % 124 + 2
                py = max(0, min(63, y_impact + (i * 7 % 8) - 3))
                self.display.pixel(px, py, 1)

        # ── LED helpers ──────────────────────────────────────────────────────
        def leds_set(r, g, b):
            if self.leds:
                self.leds.set_all(r, g, b)
                self.leds.show()

        def leds_clear():
            if self.leds:
                self.leds.clear()

        def leds_sweep_l2r(fi, r, g, b):
            """Sweep links→rechts: fi = frame (0..n_leds)."""
            if self.leds:
                n = self.leds.num_leds
                for i in range(n):
                    if i <= fi:
                        self.leds.set_pixel(i, r, g, b)
                    else:
                        self.leds.set_pixel(i, 0, 0, 0)
                self.leds.show()

        def leds_sweep_r2l(fi, r, g, b):
            """Sweep rechts→links: fi = frame (0..n_leds)."""
            if self.leds:
                n = self.leds.num_leds
                for i in range(n):
                    if i >= (n - 1 - fi):
                        self.leds.set_pixel(i, r, g, b)
                    else:
                        self.leds.set_pixel(i, 0, 0, 0)
                self.leds.show()

        def leds_rainbow(phase):
            if self.leds:
                n = self.leds.num_leds
                for i in range(n):
                    h = (phase * 12 + i * (256 // n)) % 256
                    s = h // 43
                    f = h % 43
                    p = 0
                    q = int(255 * (42 - f) // 42)
                    t = int(255 * f // 42)
                    if   s == 0: r2, g2, b2 = 255, t, p
                    elif s == 1: r2, g2, b2 = q, 255, p
                    elif s == 2: r2, g2, b2 = p, 255, t
                    elif s == 3: r2, g2, b2 = p, q, 255
                    elif s == 4: r2, g2, b2 = t, p, 255
                    else:        r2, g2, b2 = 255, p, q
                    self.leds.set_pixel(i, r2, g2, b2)
                self.leds.show()

        def leds_flicker(seed):
            cols = [(255,0,0),(255,80,0),(255,255,0),(0,255,0),(0,200,255),(80,0,255),(255,0,200)]
            if self.leds:
                n = self.leds.num_leds
                for i in range(n):
                    c = cols[(seed * 13 + i * 37) % len(cols)]
                    self.leds.set_pixel(i, c[0], c[1], c[2])
                self.leds.show()

        # ── Toon bootscherm terwijl DFPlayer opstart (blokkerende ~1.2s init) ──
        if self.display:
            self.display.fill(0)
            # "LOADING..." met pixel-ruis terwijl DFPlayer init blokt
            for i in range(30):
                px = (time.ticks_ms() * 13 + i * 37) % 128
                py = (time.ticks_ms() * 7  + i * 19) % 64
                self.display.pixel(px, py, 1)
            self.display.text("RETRO GEORGY", 8, 28, 1)
            self.display.text("loading...", 24, 42, 1)
            self.display.show()

        # DFPlayer initialiseren en track 999 afspelen
        try:
            if self._ensure_dfplayer_ready() and self.dfplayer is not None:
                self.dfplayer.set_volume(20)
                self.dfplayer.play_mp3(999)
                print("♫ Intro: 999.mp3 afspelen")
        except Exception as _e:
            print("! Intro DFPlayer:", _e)

        # ── Layout constanten ────────────────────────────────────────────────
        # "RETRO"  = 5 chars × 8 × 2 = 80px breed  →  x=24 (gecentreerd)
        # "GEORGY" = 6 chars × 8 × 2 = 96px breed  →  x=16
        RETRO_X      = (128 - 5 * 8 * 2) // 2   # 24
        GEORGY_X     = (128 - 6 * 8 * 2) // 2   # 16
        RETRO_Y_END  = 2
        GEORGY_Y_END = 24

        # Slide-in keyframes (y-positie per frame)
        RETRO_YS  = [-16, -12, -6, -2, 2, 2, 2, 2]   # 8 frames
        GEORGY_YS = [ 64,  57,  48, 38, 30, 26, 24, 24]  # 8 frames

        # ── FASE 1: pixel-ruis + LED flikkeren (5 frames) ───────────────────
        for f in range(5):
            self.display.fill(0)
            seed = time.ticks_ms()
            for i in range(25):
                self.display.pixel((seed * 13 + i * 41) % 128, (seed * 7 + i * 23) % 64, 1)
            self.display.show()
            leds_flicker(seed + f)
            time.sleep_ms(50)

        # ── FASE 2: "RETRO" schuift neer van boven (8 frames) ───────────────
        for fi, ry in enumerate(RETRO_YS):
            self.display.fill(0)
            if ry > -16:
                draw_2x("RETRO", RETRO_X, ry, 1)
            # Motion trail: stippellijn net boven de tekst
            if fi > 0 and RETRO_YS[fi - 1] < ry:
                trail_y = max(0, ry - 3)
                self.display.hline(RETRO_X, trail_y, 80, 1)
            self.display.show()
            leds_sweep_l2r(fi, 255, 90 + fi * 20, 0)   # oranje sweep
            time.sleep_ms(50)

        # ── FASE 3: RETRO IMPACT (3 frames) ─────────────────────────────────
        for fi in range(3):
            self.display.fill(0)
            draw_2x("RETRO", RETRO_X, RETRO_Y_END, 1)
            impact_y = RETRO_Y_END + 17
            if fi == 0:
                # Dubbele shockwave lijn
                self.display.hline(0, impact_y,     128, 1)
                self.display.hline(0, impact_y + 1, 128, 1)
                debris(time.ticks_ms(), impact_y + 2)
            elif fi == 1:
                self.display.hline(0, impact_y + 2, 128, 1)
                debris(time.ticks_ms() + 11, impact_y + 1, 7)
            # fi==2: kalmeer
            self.display.show()
            leds_set(255, 120, 0)   # oranje flash
            time.sleep_ms(65)

        # ── FASE 4: "GEORGY" schuift op van onder (8 frames) ────────────────
        for fi, gy in enumerate(GEORGY_YS):
            self.display.fill(0)
            draw_2x("RETRO", RETRO_X, RETRO_Y_END, 1)
            if gy < 64:
                draw_2x("GEORGY", GEORGY_X, gy, 1)
            # Motion trail net onder de tekst
            if fi > 0 and GEORGY_YS[fi - 1] > gy:
                trail_y = min(63, gy + 17)
                self.display.hline(GEORGY_X, trail_y, 96, 1)
            self.display.show()
            leds_sweep_r2l(fi, 0, 200, 255)   # cyaan sweep
            time.sleep_ms(50)

        # ── FASE 5: GEORGY IMPACT (3 frames) ────────────────────────────────
        for fi in range(3):
            self.display.fill(0)
            draw_2x("RETRO",  RETRO_X,  RETRO_Y_END,  1)
            draw_2x("GEORGY", GEORGY_X, GEORGY_Y_END, 1)
            impact_y = GEORGY_Y_END - 2
            if fi == 0:
                self.display.hline(0, max(0, impact_y - 1), 128, 1)
                self.display.hline(0, max(0, impact_y - 2), 128, 1)
                debris(time.ticks_ms(), impact_y - 3, 10)
            elif fi == 1:
                self.display.hline(0, max(0, impact_y - 3), 128, 1)
                debris(time.ticks_ms() + 9, impact_y - 2, 6)
            self.display.show()
            leds_set(0, 200, 255)   # cyaan flash
            time.sleep_ms(65)

        # ── FASE 6: pixel-border + "ALARM KLOK" typt in (14 frames) ────────
        ALARMKLOK = "ALARM KLOK"
        ALARMKLOK_X = (128 - len(ALARMKLOK) * 8) // 2  # 4
        for fi in range(14):
            self.display.fill(0)
            draw_2x("RETRO",  RETRO_X,  RETRO_Y_END,  1)
            draw_2x("GEORGY", GEORGY_X, GEORGY_Y_END, 1)
            # Pixel-rand
            self.display.rect(0, 0, 128, 64, 1)
            self.display.rect(2, 2, 124, 60, 1)
            # Typ-effect: 1 extra teken per frame
            shown = min(len(ALARMKLOK), fi + 1)
            self.display.text(ALARMKLOK[:shown], ALARMKLOK_X, 50, 1)
            # Blinkende cursor
            if fi % 2 == 0 and shown < len(ALARMKLOK):
                self.display.text("_", ALARMKLOK_X + shown * 8, 50, 1)
            self.display.show()
            leds_rainbow(fi * 2)
            time.sleep_ms(70)

        # ── FASE 7: eindscherm vasthouden (20 frames = 1 sec) ───────────────
        for fi in range(20):
            self.display.fill(0)
            draw_2x("RETRO",  RETRO_X,  RETRO_Y_END,  1)
            draw_2x("GEORGY", GEORGY_X, GEORGY_Y_END, 1)
            self.display.rect(0, 0, 128, 64, 1)
            self.display.rect(2, 2, 124, 60, 1)
            self.display.text(ALARMKLOK, ALARMKLOK_X, 50, 1)
            self.display.show()
            leds_rainbow(28 + fi * 3)
            time.sleep_ms(50)

        leds_clear()
        gc.collect()
        print("Boot intro klaar")

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

    def _fetch_weather(self):
        """Haal actueel weer op van Open-Meteo (plain HTTP, geen API-key)."""
        try:
            if self.config:
                lat = self.config.get("weather", "latitude", 51.92)
                lon = self.config.get("weather", "longitude", 6.08)
            else:
                lat, lon = 51.92, 6.08
            host = "api.open-meteo.com"
            path = "/v1/forecast?latitude={}&longitude={}&current=temperature_2m,weathercode".format(lat, lon)
            s = socket.socket()
            s.settimeout(8)
            addr = socket.getaddrinfo(host, 80)[0][-1]
            s.connect(addr)
            s.send("GET {} HTTP/1.0\r\nHost: {}\r\n\r\n".format(path, host).encode())
            resp = b""
            while True:
                chunk = s.recv(256)
                if not chunk:
                    break
                resp += chunk
            s.close()
            # Zoek JSON-body na dubbele newline
            idx = resp.find(b"\r\n\r\n")
            if idx < 0:
                return
            body = resp[idx + 4:].decode()
            # Parseer temperature_2m en weathercode zonder json.loads (RAM-zuinig)
            def _extract(key, text):
                i = text.find('"' + key + '"')
                if i < 0:
                    return None
                i = text.find(":", i) + 1
                while i < len(text) and text[i] in " \t":
                    i += 1
                j = i
                while j < len(text) and text[j] not in ",}":
                    j += 1
                try:
                    return float(text[i:j])
                except Exception:
                    return None
            # Zoek alleen in het "current"-blok
            ci = body.find('"current"')
            block = body[ci:ci + 200] if ci >= 0 else body
            temp = _extract("temperature_2m", block)
            code = _extract("weathercode", block)
            if temp is not None:
                self._weather_temp = int(temp + 0.5)
            if code is not None:
                self._weather_code = int(code)
            gc.collect()
        except Exception as e:
            print("! Weer ophalen mislukt:", e)

    def _check_weather_fetch(self):
        """Roep dit aan vanuit de main loop. Zet WiFi tijdelijk aan als nodig."""
        if not self.config or not self.config.get("weather", "enabled", True):
            return
        now_ms = time.ticks_ms()
        if time.ticks_diff(now_ms, self._weather_next_ms) < 0:
            return
        # Nog binnen de 30-min opstart-WiFi-window? Dan gewoon fetchen.
        # Anders: WiFi tijdelijk aanzetten, fetchen, weer uitzetten.
        wifi_was_disabled = self.wifi_disabled
        if wifi_was_disabled:
            print("Weer ophalen: WiFi tijdelijk aan")
            self.wifi_disabled = False
            self._ensure_wifi_connected()
        if self.wifi_ok and self.wifi and self.wifi.is_connected():
            self._fetch_weather()
            self._weather_next_ms = time.ticks_add(now_ms, self._weather_interval_ms)
            print("Weer opgehaald: {}C code {}".format(self._weather_temp, self._weather_code))
        else:
            # Mislukt: 10 min later opnieuw proberen
            self._weather_next_ms = time.ticks_add(now_ms, 10 * 60 * 1000)
        if wifi_was_disabled:
            self._disable_wifi()
            self.wifi_disabled = True
            print("Weer ophalen klaar: WiFi weer uit")

    def _draw_weather_overlay(self, t):
        now_ms = time.ticks_ms()
        # DS3231 temperatuur ophalen (elke 60s, gecached) als fallback
        if self.clock.rtc is not None and time.ticks_diff(now_ms, self._rtc_temp_next_ms) >= 0:
            try:
                self._rtc_temp = self.clock.rtc.temperature()
                self._rtc_temp_next_ms = time.ticks_add(now_ms, 60000)
            except Exception:
                pass

        wifi_up = self.wifi_ok and self.wifi and self.wifi.is_connected()
        # Temperatuur tonen: buitentemperatuur als beschikbaar, anders DS3231
        disp_temp = self._weather_temp if self._weather_temp is not None else (
            int(self._rtc_temp + 0.5) if self._rtc_temp is not None else None)
        if disp_temp is not None:
            temp_str = "{}C".format(disp_temp)
            self.display.text(temp_str, 96 - len(temp_str) * 8 - 2, 50, 1)

        x, y = 96, 50
        h = int(t[3])
        self._weather_phase = (self._weather_phase + 1) % 20

        # Nacht: maan + sterren (ongeacht weercode)
        if h >= 20 or h < 6:
            self.display.fill_rect(x, y, 8, 8, 0)
            self.display.fill_rect(x + 1, y + 1, 4, 4, 1)
            self.display.fill_rect(x + 3, y + 1, 3, 4, 0)
            if self._weather_phase % 4 == 0:
                self.display.pixel(x + 7, y + 1, 1)
                self.display.pixel(x + 6, y + 5, 1)
            return

        # WMO-code → icoon (0-3=helder, 45-48=mist, 51-67/80-82=regen, 71-77=sneeuw, 95-99=onweer)
        code = self._weather_code
        if code is None:
            # Geen data: RSSI-fallback
            try:
                rssi = self.wifi.sta.status('rssi') if wifi_up else -80
            except Exception:
                rssi = -80
            code = 0 if rssi >= -67 else (3 if rssi >= -78 else 61)

        if code <= 3:
            # Zon / weinig bewolkt
            self.display.fill_rect(x + 2, y + 2, 4, 4, 1)
            self.display.pixel(x + 4, y, 1)
            self.display.pixel(x + 4, y + 7, 1)
            self.display.pixel(x, y + 4, 1)
            self.display.pixel(x + 7, y + 4, 1)
        elif code <= 48:
            # Bewolkt / mist
            self.display.hline(x, y + 2, 8, 1)
            self.display.hline(x - 1, y + 4, 10, 1)
            self.display.hline(x, y + 6, 8, 1)
        elif code <= 67 or (80 <= code <= 82):
            # Regen
            self.display.hline(x, y + 2, 8, 1)
            self.display.hline(x - 1, y + 4, 10, 1)
            self.display.hline(x, y + 6, 8, 1)
            if self._weather_phase % 3 == 0:
                self.display.pixel(x + 2, y + 7, 1)
                self.display.pixel(x + 5, y + 7, 1)
        elif code <= 77:
            # Sneeuw: wolkje + stipjes
            self.display.hline(x, y + 2, 8, 1)
            self.display.hline(x - 1, y + 4, 10, 1)
            if self._weather_phase % 2 == 0:
                self.display.pixel(x + 1, y + 6, 1)
                self.display.pixel(x + 4, y + 7, 1)
                self.display.pixel(x + 7, y + 6, 1)
        else:
            # Onweer: wolkje + bliksem
            self.display.hline(x, y + 2, 8, 1)
            self.display.hline(x - 1, y + 4, 10, 1)
            self.display.hline(x, y + 6, 8, 1)
            if self._weather_phase % 4 < 2:
                self.display.pixel(x + 4, y + 7, 1)

    def _update_easter_egg(self, t):
        hh = int(t[3])
        mm = int(t[4])
        ss = int(t[5])
        key = hh * 100 + mm
        secret = {
            707: "LUCKY 707",
            1337: "LEET MODE",
            2121: "RETRO PORTAL",
        }
        if ss == 0 and key in secret and self._easter_key != (key, int(t[2]), int(t[1])):
            self._easter_key = (key, int(t[2]), int(t[1]))
            self._easter_message = secret[key]
            self._easter_active_until = time.ticks_add(time.ticks_ms(), 5000)

    def _draw_easter_overlay(self):
        if self._easter_active_until is None:
            return
        if time.ticks_diff(self._easter_active_until, time.ticks_ms()) <= 0:
            self._easter_active_until = None
            self._easter_message = ""
            return
        self.display.fill_rect(0, 0, 128, 10, 1)
        self.display.text(self._easter_message[:18], 4, 1, 0)

    def _apply_display_brightness(self, force=False):
        if not self.display:
            return
        t = self.clock.read_time()
        h = int(t[3])
        night = (h >= NIGHT_DIM_START_HOUR or h < NIGHT_DIM_END_HOUR)
        boss = self._alarm_boss_level() > 0
        state = "night" if night else "day"
        if boss:
            state = "boss"
        if (not force) and state == self._display_dim_state:
            return
        self._display_dim_state = state
        try:
            self.display.write_cmd(0x81)
            if state == "night":
                self.display.write_cmd(0x30)
            elif state == "boss":
                self.display.write_cmd(0xCF)
            else:
                self.display.write_cmd(0x7F)
        except Exception:
            pass

    def _draw_clock_layout(self):
        t = self.clock.read_time()
        cur_hour = int(t[3])

        # ── Eerste keer (geen IP-scherm gehad): boot-transitie met LEDs ─────
        if self._transition_pending and not self._transition_active:
            self._transition_pending = False
            self._last_hour_shown = cur_hour
            self._start_clock_transition(use_leds=True)

        # ── Uur-omslag detectie: GEEN LEDs (niet 's nachts storen) ───────────
        if self._last_hour_shown != -1 and cur_hour != self._last_hour_shown:
            if not self._transition_active:
                self._start_clock_transition(use_leds=False)
        self._last_hour_shown = cur_hour

        # Als transitie bezig: animatie afhandelen in plaats van directe render
        if self._transition_active:
            done = self._step_clock_transition()
            if done:
                self._transition_active = False
                self._transition_buf = None
                if self.leds:
                    try:
                        self.leds.clear()
                    except Exception:
                        pass
                gc.collect()
            return

        self._update_easter_egg(t)
        self.display.fill(0)
        self._draw_big_time(t[3], t[4])
        # Alarm line (y=38): eerstvolgende alarm met dagafkorting, of --:-- als geen alarm gepland.
        next_alarm = self._next_alarm_info(t)
        if next_alarm:
            day_str, ah, am = next_alarm
            if not day_str:
                day_str = self._weekday_short(t[6])  # vandaag, nog in de toekomst
            alarm_text = "{} {:02d}:{:02d}".format(day_str, ah, am)
            self._draw_alarm_icon(0, 38)
            self.display.text(alarm_text, 10, 38, 1)
        else:
            self.display.text("--:--", 10, 38, 1)
        # Day + date lines
        self.display.text(self._weekday_short(t[6]), 0, 50, 1)
        self.display.text("{:02d}-{:02d}".format(t[2], t[1]), 24, 50, 1)
        self._draw_weather_overlay(t)
        if self.wifi_disabled:
            self._draw_wifi_off_icon(WIDTH - 8, HEIGHT - 8)
        elif self.wifi_ok and self.wifi and self.wifi.is_connected():
            self._draw_wifi_status_icon(WIDTH - 8, HEIGHT - 8)
        self._draw_easter_overlay()
        self.display.show()

    # ═══════════════════════════════════════════════════════════════════════
    # Klok-scherm transitie animaties (5 varianten, random gekozen)
    # ═══════════════════════════════════════════════════════════════════════

    def _snapshot_clock(self):
        """Render het huidige klokscherm naar een losse bytearray buffer."""
        t = self.clock.read_time()
        old_buf = bytearray(self.display.buffer)   # bewaar huidig scherm
        self.display.fill(0)
        self._draw_big_time(t[3], t[4])
        next_alarm = self._next_alarm_info(t)
        if next_alarm:
            day_str, ah, am = next_alarm
            if not day_str:
                day_str = self._weekday_short(t[6])
            self._draw_alarm_icon(0, 38)
            self.display.text("{} {:02d}:{:02d}".format(day_str, ah, am), 10, 38, 1)
        else:
            self.display.text("--:--", 10, 38, 1)
        self.display.text(self._weekday_short(t[6]), 0, 50, 1)
        self.display.text("{:02d}-{:02d}".format(t[2], t[1]), 24, 50, 1)
        self._draw_weather_overlay(t)
        snapshot = bytearray(self.display.buffer)
        self.display.buffer[:] = old_buf   # herstel
        return snapshot

    def _buf_pixel(self, buf, x, y):
        """Lees pixel uit MONO_VLSB buffer (128×64)."""
        if x < 0 or x >= 128 or y < 0 or y >= 64:
            return 0
        page = y >> 3
        bit  = y & 7
        return 1 if (buf[page * 128 + x] >> bit) & 1 else 0

    def _start_clock_transition(self, use_leds=True):
        """Snapshot het doel-scherm, kies random methode, start animatie.
        use_leds=False bij uur-omslag (niet 's nachts storen).
        """
        try:
            self._transition_buf = self._snapshot_clock()
        except Exception:
            return
        self._transition_id   = (time.ticks_ms() // 7) % 5
        self._transition_step = 0
        self._transition_use_leds = use_leds
        self._transition_active = True

    def _pick_and_start_transition(self):
        """Voor opstart: zet pending-transitie om naar animatie."""
        if self._transition_pending:
            self._transition_pending = False
            self._start_clock_transition()

    def _step_clock_transition(self):
        """Voer één frame van de lopende transitie uit. Geeft True als klaar.
        Alle bewerkingen op page-niveau (byte slices) – geen pixel-for-loop.
        Buffer layout MONO_VLSB: buf[page*128 + x] = 8 verticale pixels op kolom x.
        """
        tid  = self._transition_id
        step = self._transition_step
        buf  = self._transition_buf
        d    = self.display

        # ── 0: Tetris – 4 banden (elk 16px = 2 pages) schuiven naar beneden ──
        if tid == 0:
            TOTAL = 28
            # band_start[i] = frame waarop band i begint te vallen
            band_start = (0, 5, 11, 17)
            d.fill(0)
            for band in range(4):
                p_final = band * 2          # doelpagina (0, 2, 4, 6)
                elapsed = step - band_start[band]
                if elapsed < 0:
                    continue
                elif elapsed >= 4:
                    # Geland: kopieer 2 pages direct uit snapshot (byte-slice)
                    for p in range(2):
                        so = (p_final + p) * 128
                        d.buffer[so:so+128] = buf[so:so+128]
                    # Impact-streep op frame van landing
                    if elapsed == 4:
                        d.hline(0, min(63, p_final * 8 + 16), 128, 1)
                else:
                    # Valt: verplaats pages 1 pagina per 1.5 frame omlaag
                    # elapsed 1→3: start 3,2,1 pages boven eindpositie
                    fall_pages_above = 3 - elapsed
                    for p in range(2):
                        src_o = (p_final + p) * 128
                        dst_page = p_final + p - fall_pages_above
                        if 0 <= dst_page < 8:
                            d.buffer[dst_page * 128 : dst_page * 128 + 128] = buf[src_o:src_o+128]
            if self._transition_use_leds and self.leds:
                cols = [(0,200,255),(255,200,0),(255,0,200),(0,255,80)]
                landed = sum(1 for bs in band_start if step >= bs + 4)
                col = cols[min(landed, 3)]
                n = self.leds.num_leds
                lit = max(1, step * n // TOTAL)
                for i in range(n):
                    self.leds.set_pixel(i, col[0] if i < lit else 0, col[1] if i < lit else 0, col[2] if i < lit else 0)
                self.leds.show()
            d.show()
            self._transition_step += 1
            return self._transition_step >= TOTAL

        # ── 1: Space Invaders scan – beam onthult L→R via page-slice ─────
        elif tid == 1:
            TOTAL = 24
            d.fill(0)
            beam_x = min(127, step * 6)
            # Kopieer kolommen 0..beam_x per page (byte-slice per rij)
            for page in range(8):
                base = page * 128
                d.buffer[base : base + beam_x] = buf[base : base + beam_x]
            # Beam: verticale stippellijn
            for y in range(0, 64, 3):
                d.pixel(beam_x, y, 1)
            # 3 invader-sprites (2×2 px pixels, klein gehouden)
            INV = (0b01100110, 0b11111111, 0b01111110, 0b00111100)
            for j in range(3):
                ix = (step * 3 + j * 30) % 138 - 10
                iy = 2 + j * 5
                for row, byte in enumerate(INV):
                    for bit in range(8):
                        if (byte >> (7 - bit)) & 1:
                            px2 = ix + bit
                            if 0 <= px2 < 128:
                                d.pixel(px2, iy + row, 1)
            if self._transition_use_leds and self.leds:
                n = self.leds.num_leds
                lit = step * n // TOTAL
                for i in range(n):
                    g = 220 if i == lit % n else (80 if i < lit else 0)
                    self.leds.set_pixel(i, 0, g, 0)
                self.leds.show()
            d.show()
            self._transition_step += 1
            return self._transition_step >= TOTAL

        # ── 2: Matrix regen – kolommen onthullen van boven naar beneden ───
        elif tid == 2:
            TOTAL = 32
            # 16 kolomgroepen van 8px; snelheid per groep (1, 2 of 3)
            col_speeds = (2,1,3,1,2,3,1,2,1,3,2,1,3,1,2,3)
            d.fill(0)
            for ci in range(16):
                cx = ci * 8
                pages_done = min(8, step * col_speeds[ci] // 5)
                # Kopieer onthulde pages via byte-slice
                for page in range(pages_done):
                    o = page * 128 + cx
                    d.buffer[o : o + 8] = buf[o : o + 8]
                # Regen-druppel net onder onthulde area
                if pages_done < 8:
                    drop_y = pages_done * 8 + (step % 8)
                    if drop_y < 64:
                        d.pixel(cx + (ci * 17) % 8, drop_y, 1)
            if self._transition_use_leds and self.leds:
                n = self.leds.num_leds
                lit = min(n, step * n // TOTAL)
                for i in range(n):
                    self.leds.set_pixel(i, 0, 200 if i < lit else 0, 0)
                self.leds.show()
            d.show()
            self._transition_step += 1
            return self._transition_step >= TOTAL

        # ── 3: Pac-Man – onthult L→R via page-slice, sprite erop getekend ─
        elif tid == 3:
            TOTAL = 26
            pac_x = min(128, step * 5)
            d.fill(0)
            # Kopieer kolommen links van Pac-Man via byte-slice
            reveal = min(pac_x, 128)
            for page in range(8):
                base = page * 128
                d.buffer[base : base + reveal] = buf[base : base + reveal]
            # Pac-Man sprite (12×12)
            px2 = min(pac_x, 116)
            py2 = 26
            mouth_open = (step % 4) < 2
            d.fill_rect(px2, py2, 12, 12, 1)
            for cx2, cy2 in ((px2, py2), (px2+11, py2), (px2, py2+11), (px2+11, py2+11)):
                d.pixel(cx2, cy2, 0)
            if mouth_open:
                d.fill_rect(px2+6, py2+2, 6, 8, 0)
                d.line(px2+6, py2+5, px2+11, py2+2, 0)
                d.line(px2+6, py2+6, px2+11, py2+9, 0)
            d.pixel(px2+4, py2+2, 0)
            if self._transition_use_leds and self.leds:
                n = self.leds.num_leds
                lit = min(n, step * n // TOTAL)
                ycol = (255, 220, 0) if (step % 4 < 2) else (255, 255, 80)
                for i in range(n):
                    self.leds.set_pixel(i, ycol[0] if i < lit else 0, ycol[1] if i < lit else 0, 0)
                self.leds.show()
            d.show()
            self._transition_step += 1
            return self._transition_step >= TOTAL

        # ── 4: CRT power-on – pages groeien open vanuit midden ────────────
        elif tid == 4:
            TOTAL = 28
            d.fill(0)
            if step < 14:
                # Fase 1: breid uit vanuit pagina 3-4 naar buiten (1 page per stap)
                half = step // 2 + 1
                p_start = max(0, 4 - half)
                p_end   = min(8, 4 + half)
                for page in range(p_start, p_end):
                    o = page * 128
                    d.buffer[o : o + 128] = buf[o : o + 128]
                # Gloed-lijn aan rand
                if p_start > 0:
                    d.hline(0, p_start * 8, 128, 1)
                if p_end < 8:
                    d.hline(0, min(63, p_end * 8 - 1), 128, 1)
            elif step < 22:
                # Fase 2: interlaced flicker – wissel even/oneven pages
                phase = (step - 14) % 2
                for page in range(phase, 8, 2):
                    o = page * 128
                    d.buffer[o : o + 128] = buf[o : o + 128]
            else:
                # Fase 3: volledig beeld via één buffer-copy
                d.buffer[:] = buf[:]
            if self._transition_use_leds and self.leds:
                n = self.leds.num_leds
                br = max(0, 220 - step * 8)
                for i in range(n):
                    self.leds.set_pixel(i, br, br, br)
                self.leds.show()
            d.show()
            self._transition_step += 1
            return self._transition_step >= TOTAL

        # Fallback
        return True


    def _draw_zelda_animation(self, frame):
        d = self.display
        d.fill(0)
        f = frame % 16
        H, S = 17, 10

        # Triforce: top apex (64,4), bl (54,21), br (74,21)
        def _tfill(ax, ay, c=1):
            for dy in range(H + 1):
                w = max(1, 2 * S * dy // H)
                d.hline(ax - w // 2, ay + dy, w, c)

        def _tline(ax, ay):
            d.line(ax, ay, ax - S, ay + H, 1)
            d.line(ax, ay, ax + S, ay + H, 1)
            d.hline(ax - S, ay + H, 2 * S + 1, 1)

        if f < 4:
            # BL+BR vast, Top knippert
            _tfill(54, 21); _tfill(74, 21)
            if f % 2 == 0:
                _tfill(64, 4)
            else:
                _tline(64, 4)
        elif f < 12:
            # Alle drie vol (langste fase)
            _tfill(64, 4); _tfill(54, 21); _tfill(74, 21)
        else:
            # Invert: wit vlak, zwarte triforce omtrekken
            d.fill_rect(43, 3, 42, 36, 1)
            d.line(64, 4, 54, 21, 0); d.line(64, 4, 74, 21, 0); d.hline(54, 21, 21, 0)
            d.line(54, 21, 44, 38, 0); d.line(54, 21, 64, 38, 0); d.hline(44, 38, 21, 0)
            d.line(74, 21, 64, 38, 0); d.line(74, 21, 84, 38, 0); d.hline(64, 38, 21, 0)

        # ZELDA tekst (x=44-84, gelijk met triforce)
        d.text("ZELDA", 44, 46, 1)

        # ALARM balk knippert
        if (frame // 10) % 2 == 0:
            d.fill_rect(0, 56, 128, 8, 1)
            d.text("ALARM!", 40, 56, 0)
        else:
            d.text("ALARM!", 40, 56, 1)

        # 3 hartjes rechts (Zelda levens)
        for i in range(3):
            hx = 88 + i * 13; hy = 8
            d.pixel(hx + 1, hy, 1);    d.pixel(hx + 3, hy, 1)
            d.hline(hx,     hy + 1, 5, 1)
            d.hline(hx,     hy + 2, 5, 1)
            d.hline(hx + 1, hy + 3, 3, 1)
            d.pixel(hx + 2, hy + 4, 1)

        # Fonkelende sterretjes links
        for i, (sx, sy) in enumerate(((4, 6), (14, 18), (6, 30), (22, 10), (18, 36))):
            if (frame // 4 + i) % 3 != 0:
                d.pixel(sx, sy, 1)
                d.pixel(sx + 1, sy, 1)
                d.pixel(sx, sy + 1, 1)
                d.pixel(sx + 1, sy + 1, 1)

        d.show()

    def _draw_sonic_animation(self, frame, intensity):
        """Sonic theme: checker ground, running sprite silhouette and floating ring."""
        d = self.display
        d.fill(0)

        # Fast background streaks.
        speed = frame % 32
        for y in (6, 11, 16, 21):
            x = -(speed * 4 + y * 3) % 36
            while x < 128:
                d.hline(x, y, 10 + (y % 3) * 4, 1)
                x += 28

        # Checker-like ground band.
        d.hline(0, 44, 128, 1)
        for i in range(34):
            x = i * 4 - (frame * 2 % 8)
            if i % 2 == 0:
                d.fill_rect(x, 45, 4, 4, 1)
        d.fill_rect(0, 49, 128, 15, 1)

        # Floating ring (right side).
        ring_x = 96
        ring_y = 24 + ((frame // 4) % 4 - 2)
        d.rect(ring_x, ring_y, 14, 14, 1)
        d.rect(ring_x + 2, ring_y + 2, 10, 10, 0)
        if (frame // 3) % 2 == 0:
            d.pixel(ring_x - 2, ring_y + 6, 1)
            d.pixel(ring_x + 16, ring_y + 6, 1)

        # Sonic-like running silhouette.
        x = 18 + ((frame // 2) % 16)
        y = 32
        d.fill_rect(x + 2, y, 6, 4, 1)      # quills/head
        d.fill_rect(x + 1, y + 4, 8, 4, 1)  # torso
        d.fill_rect(x + 3, y + 8, 2, 4, 1)  # left leg
        d.fill_rect(x + 6, y + 8, 2, 4, 1)  # right leg
        if (frame // 3) % 2 == 0:
            d.fill_rect(x, y + 5, 2, 2, 1)
            d.fill_rect(x + 8, y + 3, 2, 2, 1)
        else:
            d.fill_rect(x, y + 3, 2, 2, 1)
            d.fill_rect(x + 8, y + 5, 2, 2, 1)

        # Boss/intensity meter.
        meter = max(0, min(100, int(intensity)))
        d.rect(2, 2, 34, 6, 1)
        d.fill_rect(3, 3, meter * 32 // 100, 4, 1)
        d.text("SONIC", 42, 0, 1)
        d.show()

    def _draw_metroid_animation(self, frame, intensity):
        """Metroid theme: visor HUD, scanline and charging cannon."""
        d = self.display
        d.fill(0)

        # Visor/HUD frame.
        d.rect(0, 0, 128, 64, 1)
        d.hline(0, 10, 128, 1)
        d.hline(0, 52, 128, 1)
        d.vline(14, 10, 42, 1)
        d.vline(113, 10, 42, 1)

        # Scanning line sweeps in the viewport.
        sy = 12 + (frame * 2 % 38)
        d.hline(16, sy, 96, 1)

        # Core orb in the center.
        cx, cy = 64, 31
        pulse = (frame // 3) % 6
        d.rect(cx - 10, cy - 10, 20, 20, 1)
        d.rect(cx - 7, cy - 7, 14, 14, 1)
        d.fill_rect(cx - 2 - (pulse // 3), cy - 2 - (pulse // 3), 4 + (pulse // 2), 4 + (pulse // 2), 1)

        # Cannon charge on right side.
        charge = max(0, min(100, int(intensity)))
        d.rect(100, 22, 20, 8, 1)
        d.fill_rect(101, 23, charge * 18 // 100, 6, 1)
        if charge > 70 and (frame // 2) % 2 == 0:
            d.line(120, 26, 127, 22, 1)
            d.line(120, 26, 127, 30, 1)

        # Energy tanks (bottom strip).
        tanks = max(1, charge // 20)
        for i in range(5):
            x = 20 + i * 18
            d.rect(x, 55, 14, 7, 1)
            if i < tanks:
                d.fill_rect(x + 2, 57, 10, 3, 1)

        d.text("METROID", 34, 1, 1)
        d.show()

    def _draw_pokemon_animation(self, frame, intensity):
        """Pokemon theme: classic battle HUD with trainer/monster silhouettes."""
        d = self.display
        d.fill(0)

        # Battle horizon and grass lines.
        d.hline(0, 30, 128, 1)
        drift = frame % 8
        for y in (33, 37, 41, 45):
            d.hline((y * 3 + drift * 2) % 20 - 20, y, 148, 1)

        # Enemy silhouette (upper-right).
        ex, ey = 88, 11
        d.fill_rect(ex + 3, ey, 10, 3, 1)
        d.fill_rect(ex + 1, ey + 3, 14, 5, 1)
        d.fill_rect(ex + 4, ey + 8, 8, 4, 1)
        if (frame // 6) % 2 == 0:
            d.pixel(ex + 4, ey + 4, 0)
            d.pixel(ex + 10, ey + 4, 0)

        # Player/trainer silhouette (lower-left).
        px, py = 14, 34
        d.fill_rect(px + 2, py, 5, 4, 1)
        d.fill_rect(px + 1, py + 4, 7, 6, 1)
        d.fill_rect(px + 2, py + 10, 2, 4, 1)
        d.fill_rect(px + 5, py + 10, 2, 4, 1)

        # Pokeball throw arc.
        ball_x = 28 + (frame * 3 % 68)
        arc = (ball_x - 62)
        ball_y = 46 - (arc * arc // 140)
        d.rect(ball_x, max(6, ball_y), 4, 4, 1)
        d.hline(ball_x, max(6, ball_y + 2), 4, 1)

        # HP UI boxes.
        hp = max(0, min(100, int(intensity)))
        d.rect(5, 2, 48, 10, 1)
        d.text("YOU", 8, 4, 1)
        d.rect(54, 4, 44, 6, 1)
        d.fill_rect(55, 5, hp * 42 // 100, 4, 1)
        d.rect(75, 52, 48, 10, 1)
        d.text("FOE", 78, 54, 1)
        d.text("PKMN", 52, 0, 1)
        d.show()

    def _draw_tetris_animation(self, frame, intensity):
        """Tetris theme: board, stack silhouette and animated falling tetromino."""
        d = self.display
        d.fill(0)

        bx, by, cell = 18, 8, 3
        bw, bh = 10 * cell, 16 * cell
        d.rect(bx - 1, by - 1, bw + 2, bh + 2, 1)

        # Existing stack silhouette (deterministic skyline).
        for col in range(10):
            h = 2 + ((col * 3 + frame // 7) % 7)
            for row in range(h):
                if row < 14:
                    y = by + (15 - row) * cell
                    x = bx + col * cell
                    d.fill_rect(x, y, cell, cell, 1)

        # Falling piece animation.
        shape = (frame // 18) % 4
        drop = (frame * 2) % (15 * cell)
        px = bx + (2 + (frame // 32) % 5) * cell
        py = by + drop
        if shape == 0:  # I
            d.fill_rect(px, py, cell, cell * 4, 1)
        elif shape == 1:  # O
            d.fill_rect(px, py, cell * 2, cell * 2, 1)
        elif shape == 2:  # T
            d.fill_rect(px, py, cell * 3, cell, 1)
            d.fill_rect(px + cell, py + cell, cell, cell, 1)
        else:  # L
            d.fill_rect(px, py, cell, cell * 3, 1)
            d.fill_rect(px, py + cell * 2, cell * 2, cell, 1)

        # Side panel.
        d.text("TETRIS", 64, 8, 1)
        d.text("NEXT", 70, 20, 1)
        d.rect(72, 30, 18, 12, 1)
        d.fill_rect(74, 34, 4, 4, 1)
        d.fill_rect(78, 34, 4, 4, 1)
        d.fill_rect(82, 34, 4, 4, 1)
        d.text("LV", 74, 48, 1)
        d.text(str(max(1, intensity // 10)), 90, 48, 1)
        d.show()

    def _draw_moonstone_animation(self, frame, intensity):
        """Moonstone sequence: logo intro, then alternating knight and monster close-ups."""
        d = self.display
        d.fill(0)

        elapsed = self._alarm_elapsed_ms()

        # 1) Always start with logo scene.
        if elapsed < 2600:
            # Star field
            for i in range(22):
                sx = (i * 17 + frame * (1 + (i % 2))) % 128
                sy = 2 + (i * 7 % 26)
                d.pixel(sx, sy, 1)

            # Moon + ring
            d.fill_rect(44, 4, 40, 22, 1)
            d.fill_rect(50, 7, 30, 16, 0)
            d.hline(30, 15, 68, 1)
            d.hline(28, 16, 72, 1)

            d.text("MOONSTONE", 26, 30, 1)
            d.text("HARD DAYS KNIGHT", 20, 44, 1)
            if (frame // 4) % 2 == 0:
                d.hline(18, 57, 92, 1)

            d.show()
            return

        # 2) After intro: alternate large face close-ups.
        shot = ((elapsed - 2600) // 1400) % 2
        blink = (frame // 5) % 6

        if shot == 0:
            # Knight face close-up
            d.fill_rect(0, 0, 128, 64, 0)
            d.rect(2, 2, 124, 60, 1)

            # Helmet + shoulders
            d.fill_rect(22, 12, 84, 42, 1)
            d.fill_rect(28, 18, 72, 28, 0)
            d.fill_rect(16, 48, 96, 12, 1)

            # Eyes/visor
            d.fill_rect(40, 28, 14, 4, 1)
            d.fill_rect(74, 28, 14, 4, 1)
            d.fill_rect(56, 24, 16, 14, 1)
            d.fill_rect(59, 27, 10, 8, 0)
            if blink == 0:
                d.hline(42, 30, 10, 0)
                d.hline(76, 30, 10, 0)

            # Plume / sword hint
            d.line(92, 16, 118, 4, 1)
            d.line(92, 19, 120, 9, 1)
            d.line(14, 60, 34, 34, 1)

            d.text("KNIGHT", 46, 4, 1)

        else:
            # Monster face close-up
            d.fill_rect(0, 0, 128, 64, 0)
            d.rect(2, 2, 124, 60, 1)

            # Skull head
            d.fill_rect(24, 12, 80, 40, 1)
            d.fill_rect(30, 18, 68, 26, 0)
            d.fill_rect(44, 42, 40, 12, 1)

            # Horns
            d.line(24, 14, 8, 4, 1)
            d.line(24, 18, 10, 8, 1)
            d.line(103, 14, 119, 4, 1)
            d.line(103, 18, 117, 9, 1)

            # Eyes + maw
            d.fill_rect(40, 28, 12, 6, 1)
            d.fill_rect(76, 28, 12, 6, 1)
            d.fill_rect(52, 36, 24, 10, 1)
            d.fill_rect(56, 39, 16, 5, 0)
            d.vline(59, 39, 5, 1)
            d.vline(64, 39, 5, 1)
            d.vline(69, 39, 5, 1)

            if blink == 0:
                d.hline(42, 30, 8, 0)
                d.hline(78, 30, 8, 0)
            elif blink in (1, 2):
                d.pixel(44, 31, 0)
                d.pixel(82, 31, 0)

            # Drool/blood hint in monochrome style
            d.vline(50, 50, 8, 1)
            d.vline(76, 50, 7, 1)
            d.text("MONSTER", 44, 4, 1)

        # Intensity flare frame
        if int(intensity) > 70 and (frame % 3) == 0:
            d.rect(0, 0, 128, 64, 1)
        d.show()

    def _draw_arcade_animation(self, frame, intensity):
        """Arcade theme: animated cabinet with mini pong game on CRT."""
        d = self.display
        d.fill(0)

        # Cabinet body.
        d.rect(28, 2, 72, 60, 1)
        d.rect(34, 8, 60, 30, 1)
        d.rect(40, 42, 48, 8, 1)
        d.text("ARCADE", 44, 2, 1)

        # CRT scanlines.
        for y in range(10, 36, 3):
            d.hline(36, y, 56, 1)

        # Mini pong animation on screen.
        paddle_y = 13 + ((frame // 3) % 16)
        d.fill_rect(38, paddle_y, 2, 8, 1)
        d.fill_rect(88, 26 - ((frame // 5) % 12), 2, 8, 1)
        bx = 44 + (frame * 3 % 40)
        by = 14 + ((frame * 2) % 16)
        if (frame // 14) % 2 == 1:
            bx = 84 - (frame * 3 % 40)
        d.fill_rect(bx, by, 2, 2, 1)

        # Control panel details.
        d.fill_rect(46, 44, 6, 3, 1)
        d.fill_rect(56, 44, 3, 3, 1)
        d.fill_rect(62, 44, 3, 3, 1)
        d.fill_rect(68, 44, 3, 3, 1)
        if (frame // 8) % 2 == 0:
            d.text("COIN", 46, 53, 1)

        score = (frame * (max(1, int(intensity)))) % 9999
        d.text("HI", 4, 8, 1)
        d.text(str(score), 4, 18, 1)
        d.show()

    def _draw_mario_animation(self, frame):
        d = self.display
        d.fill(0)

        phase = frame % 24
        x = 12 + (phase % 12) * 5
        if phase >= 12:
            x = 12 + (23 - phase) * 5
        jump = 0 if phase % 6 < 3 else -4

        # Ground
        for gy in (50, 53, 56, 59):
            d.hline(0, gy, 128, 1)

        # Question block + coin animation
        bx, by = 92, 20
        d.rect(bx, by, 14, 14, 1)
        d.text("?", bx + 4, by + 3, 1)
        coin_y = by - 8 - ((frame // 3) % 4)
        d.rect(bx + 5, coin_y, 4, 6, 1)

        # Retro clouds
        for cx, cy in ((12, 8), (36, 12), (64, 7)):
            d.hline(cx, cy, 10, 1)
            d.hline(cx - 2, cy + 2, 14, 1)
            d.hline(cx, cy + 4, 10, 1)

        # Pixel plumber sprite (8x12)
        sx, sy = x, 37 + jump
        d.fill_rect(sx + 2, sy, 4, 2, 1)       # cap
        d.fill_rect(sx + 1, sy + 2, 6, 2, 1)   # head
        d.fill_rect(sx + 2, sy + 4, 4, 3, 1)   # torso
        d.fill_rect(sx + 1, sy + 7, 2, 3, 1)   # left leg
        d.fill_rect(sx + 5, sy + 7, 2, 3, 1)   # right leg
        if phase % 4 < 2:
            d.fill_rect(sx, sy + 4, 2, 2, 1)   # arm pose A
        else:
            d.fill_rect(sx + 6, sy + 4, 2, 2, 1)  # arm pose B

        # Pipes for parallax feel
        d.rect(74, 34, 12, 16, 1)
        d.rect(76, 32, 8, 2, 1)
        d.rect(110, 38, 10, 12, 1)
        d.rect(111, 36, 8, 2, 1)

        d.text("MARIO", 2, 0, 1)
        if (frame // 8) % 2 == 0:
            d.fill_rect(40, 0, 36, 8, 1)
            d.text("ALARM", 42, 0, 0)
        else:
            d.text("ALARM", 42, 0, 1)

        d.show()

    def _draw_synthwave_animation(self, frame):
        d = self.display
        d.fill(0)
        horizon = 23

        # Star field.
        for i in range(12):
            sx = (i * 17 + frame * (1 + (i % 3))) % 128
            sy = 2 + (i * 5 % 16)
            d.pixel(sx, sy, 1)

        # Striped sun.
        d.fill_rect(46, 4, 36, 18, 1)
        for y in (6, 9, 12, 15, 18):
            d.hline(48, y, 32, 0)

        # City skyline.
        for i in range(10):
            x = i * 13
            h = 4 + ((i * 7 + frame // 4) % 13)
            d.fill_rect(x, horizon - h, 9, h, 1)
            if i % 2 == 0:
                d.pixel(x + 2, horizon - h + 2, 0)
                d.pixel(x + 5, horizon - h + 4, 0)

        # Perspective road + grid.
        d.hline(0, horizon, 128, 1)
        for y in range(horizon + 2, 64, 4):
            d.hline(0, y, 128, 1)
        center_shift = (frame % 18) - 9
        for x in range(0, 129, 12):
            d.line(x, 63, 64 + center_shift, horizon + 1, 1)

        # Car silhouette in foreground.
        car_x = 52
        d.fill_rect(car_x, 48, 24, 8, 1)
        d.fill_rect(car_x + 5, 45, 14, 4, 1)
        d.fill_rect(car_x + 2, 56, 4, 2, 1)
        d.fill_rect(car_x + 18, 56, 4, 2, 1)
        if (frame // 3) % 2 == 0:
            d.hline(car_x + 9, 50, 6, 0)

        d.text("SYNTH", 2, 0, 1)
        if (frame // 5) % 2 == 0:
            d.text("ALARM", 88, 0, 1)
        d.show()

    def _draw_alarm_intro(self, frame, tone):
        d = self.display
        d.fill(0)
        title_map = {
            "1": "ZELDA MODE",
            "2": "MARIO MODE",
            "3": "SYNTH MODE",
            "4": "SONIC MODE",
            "5": "METROID MODE",
            "6": "POKEMON MODE",
            "7": "TETRIS MODE",
            "8": "MOONSTONE MODE",
            "9": "ARCADE MODE",
        }
        title = title_map.get(str(tone), "RETRO MODE")
        # Wipe animation
        w = min(128, (frame % 26) * 5)
        d.fill_rect(0, 0, w, 64, 1)
        d.text("ALARM START", 18, 18, 0 if w > 90 else 1)
        d.text(title, 24, 34, 0 if w > 90 else 1)
        d.text("GET READY", 30, 50, 0 if w > 90 else 1)
        d.show()

    def _draw_alarm_animation(self, frame):
        elapsed = self._alarm_elapsed_ms()
        tone = getattr(self, 'active_tone', '1')
        intensity = self._alarm_intensity()
        if elapsed < ALARM_INTRO_MS:
            self._draw_alarm_intro(frame, tone)
            return
        if tone == '1':
            self._draw_zelda_animation(frame)
        elif tone == '2':
            self._draw_mario_animation(frame)
        elif tone == '3':
            self._draw_synthwave_animation(frame)
        elif tone == '4':
            self._draw_sonic_animation(frame, intensity)
        elif tone == '5':
            self._draw_metroid_animation(frame, intensity)
        elif tone == '6':
            self._draw_pokemon_animation(frame, intensity)
        elif tone == '7':
            self._draw_tetris_animation(frame, intensity)
        elif tone == '8':
            self._draw_moonstone_animation(frame, intensity)
        elif tone == '9':
            self._draw_arcade_animation(frame, intensity)
        else:
            # Generieke fallback scene per track.
            self.display.fill(0)
            wobble = (frame % 6) - 3
            self.display.rect(20 + wobble, 12, 88, 40, 1)
            self.display.text("TRACK {}".format(tone), 38, 26, 1)
            if (frame // 5) % 2 == 0:
                self.display.text("ALARM", 44, 40, 1)
            self.display.show()

        # Boss FX overlay bovenop elke animatie.
        boss = self._alarm_boss_level()
        if boss > 0:
            if boss >= 2 and (frame % 2 == 0):
                self.display.rect(0, 0, 128, 64, 1)
            if boss >= 3 and (frame % 3 == 0):
                self.display.fill_rect(0, 0, 128, 8, 1)
                self.display.text("BOSS MODE", 32, 0, 0)
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
                "alarm_combo": self.alarm_combo,
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
            self.alarm_combo = self._normalize_alarm_combo(d.get("alarm_combo", self.alarm_combo))
            if self.config:
                self.config.config["alarm_schedule"] = self.alarm_schedule
                self.config.config["alarm_combo"] = self.alarm_combo
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
        if method == "POST" and path == "/api/test-transition":
            d = self._parse(req)
            tid = int(d.get("id", -1))
            if tid < 0 or tid > 4:
                # random
                tid = (time.ticks_ms() // 7) % 5
            if not self._transition_active and self.display:
                try:
                    self._transition_buf = self._snapshot_clock()
                    self._transition_id       = tid
                    self._transition_step     = 0
                    self._transition_use_leds = True   # webtest: LEDs aan
                    self._transition_active   = True
                    c.send(self._json({"ok": True, "id": tid}))
                except Exception as _e:
                    c.send(self._json({"ok": False, "error": str(_e)}))
            else:
                c.send(self._json({"ok": False, "error": "transitie al bezig of geen display"}))
            return
        c.send("HTTP/1.1 404 Not Found\r\n\r\n".encode())

    def run(self):
        print("Hoofdloop gestart")
        self._play_boot_intro()

        frame = 0
        gc_counter = 0
        while True:
            try:
                self._handle_buttons()
                self._handle_wifi_state()
                self._check_weather_fetch()

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

                if frame > 0 and frame % 18000 == 0 and self.wifi_ok:
                    self.clock.sync_ntp()

                if self.display:
                    self._apply_display_brightness()
                    if self.alarm_until is not None:
                        self._draw_alarm_animation(frame)
                        self._update_led_animation(frame)
                    elif self.alarm_edit_mode:
                        self._draw_alarm_edit()
                    elif self.startup_ip_until is not None and time.ticks_diff(self.startup_ip_until, time.ticks_ms()) > 0:
                        self._draw_startup_ip()
                    else:
                        if self.startup_ip_until is not None:
                            # IP-scherm loopt af → transitie starten naar klokscherm (met LEDs)
                            self.startup_ip_until = None
                            self._transition_pending = False
                            self._start_clock_transition(use_leds=True)
                        self._draw_clock_layout()

                # Periodische garbage collection
                gc_counter += 1
                if gc_counter > 100:  # Elke ~5 seconden
                    gc.collect()
                    gc_counter = 0

                frame += 1
                time.sleep(0.05)
            except Exception as e:
                print("Loop fout:", e)
                gc.collect()
                time.sleep(0.5)


if __name__ == "__main__":
    app = App()
    app.run()

