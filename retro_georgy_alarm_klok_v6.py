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

try:
    import ussl as ssl
except ImportError:
    try:
        import ssl
    except ImportError:
        ssl = None

try:
    import uhashlib as hashlib
except ImportError:
    try:
        import hashlib
    except ImportError:
        hashlib = None

try:
    import ubinascii as binascii
except ImportError:
    try:
        import binascii
    except ImportError:
        binascii = None

try:
    from urllib.parse import quote
except ImportError:
    quote = None

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

try:
    import neopixel
except ImportError:
    neopixel = None

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
# Onboard status LED/RGB on many ESP32-S3 dev boards (best effort)
BOARD_LED_PIN = 48
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
DEFAULT_WIFI_SSID = ""
SETUP_AP_SSID = "AlarmKlok-Setup"
SETUP_AP_IP = "192.168.4.1"
WIFI_HOSTNAME = "alarmklok"
ALARM_INTRO_MS = 2500
ALARM_BOSS_MS = 20000
ALARM_AUTO_STOP_MS = 15 * 60 * 1000
NIGHT_DIM_START_HOUR = 22
NIGHT_DIM_END_HOUR = 7
UP_BUTTON_PIN = 12    # Touch12 / ADC2_1 — omgewisseld op verzoek
DOWN_BUTTON_PIN = 13  # Touch13 / ADC2_2 — omgewisseld op verzoek
SET_BUTTON_PIN = 14   # Touch14 / ADC2_3 — vrij
DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
APP_VERSION = "6.1.1"
DEFAULT_UPDATE_MANIFEST_URL = "https://sjorsansems.github.io/retro-alarm-clock/updates/stable/manifest.json"
ANIMATIONS_DIR = "animations"
DEFAULT_RETRO_FACT_DISPLAY_SECONDS = 10
DEFAULT_DOS_IDLE_ENABLED = True
DEFAULT_DOS_IDLE_TRIGGER_MINUTES = 6
DEFAULT_DOS_IDLE_MAX_PER_DAY = 12
RETRO_FACT_LIBRARY = [
    "1977: Atari released the VCS, later known as the Atari 2600",
    "1980: Pac-Man turned arcades into a global phenomenon",
    "1983: Nintendo launched the Famicom in Japan",
    "1985: Super Mario Bros. launched in Japan and reshaped platform games",
    "1986: The Legend of Zelda debuted and defined adventure design",
    "1987: Zelda II pushed the series into a more experimental direction",
    "1988: Sega launched the Mega Drive and started a new console war",
    "1989: Nintendo launched the Game Boy and handheld gaming exploded",
    "1990: The Super Famicom arrived and raised the bar for 16-bit games",
    "1991: Sonic the Hedgehog introduced Sega's fastest mascot",
    "1992: Mortal Kombat made arcades louder, stranger, and bloodier",
    "1993: DOOM changed first-person shooters forever",
    "1994: Sony entered the console market with the original PlayStation",
    "1995: Chrono Trigger became a legendary JRPG favorite",
    "1996: Nintendo 64 brought 3D gaming to the mainstream",
    "1997: Final Fantasy VII made JRPGs a global event",
    "1998: Sega released the Dreamcast in Japan, a cult retro classic",
    "1999: Shenmue showed how ambitious open-world storytelling could be",
    "2000: The PlayStation 2 launched and became a massive success",
    "2001: The Game Boy Advance kept handheld gaming strong",
    "2002: The GameCube gave Nintendo a compact purple powerhouse",
    "2004: The Nintendo DS made touch controls a mainstream idea",
    "2005: The Xbox 360 kicked off the HD console era",
    "2006: The Wii made motion controls a household concept",
    "2007: Super Mario Galaxy proved 3D platforming could still surprise",
    "2008: Braid helped define the indie game boom",
    "2009: Minecraft began its rise from small experiment to phenomenon",
    "2010: Kinect made camera-controlled gaming a headline feature",
    "2011: The Legend of Zelda: Skyward Sword arrived with motion controls",
    "2012: The Wii U introduced a second-screen console idea",
    "2013: The PlayStation 4 launched and set up the modern era",
    "2014: Shovel Knight became an instant retro-inspired classic",
    "2015: Undertale showed how much personality a small game could have",
    "2016: Pokémon Go turned real-world streets into game maps",
    "2017: The Nintendo Switch blended handheld and home gaming",
    "2018: Celeste became a standout example of modern pixel-art design",
    "2019: The Sega Genesis Mini brought 16-bit nostalgia back again",
    "2020: The Xbox Series X|S opened the latest console generation",
    "2021: Metroid Dread brought 2D action back into the spotlight",
    "2022: Atari 50 celebrated the long history of arcade and console gaming",
    "2023: The Legend of Zelda: Tears of the Kingdom became a major launch moment",
    "2024: Retro gaming kept thriving through remakes, minis, and indie tributes",
]

DOS_IDLE_SCENES = [
    {
        "concept": "grappig",
        "lines": [
            "C:\\> loading retro mode...",
            "ERROR: coffee not found",
            "Try again [Y/N]?",
        ],
        "footer": "C:\\>_",
    },
    {
        "concept": "grappig",
        "lines": [
            "Error 274: keyboard not found",
            "press F1 to continue",
            "(F1 is also missing)",
        ],
        "footer": "C:\\> help",
    },
    {
        "concept": "grappig",
        "lines": [
            "Not enough memory to run",
            "Wolvenstein 3-D",
            "Close 47 TSR programs",
        ],
        "footer": "MEM FREE: 12 KB",
    },
    {
        "concept": "boot",
        "lines": [
            "Setup cannot install",
            "MS-DOS 6.22 on your",
            "computer",
        ],
        "footer": "Press F3 to reboot",
    },
    {
        "concept": "boot",
        "lines": [
            "HIMEM.SYS loaded",
            "EMM386 failed",
            "Continuing anyway...",
        ],
        "footer": "C:\\> win /3",
    },
    {
        "concept": "boot",
        "lines": [
            "A:\\ DRIVE ERROR",
            "B:\\ DRIVE ERROR",
            "C:\\ maybe OK",
        ],
        "footer": "Retry, Abort, Fail?",
    },
    {
        "concept": "creepy",
        "lines": [
            "Virus detected in",
            "clock.exe",
            "Quarantine failed",
        ],
        "footer": "SCAN CODE: 0xDEAD",
    },
    {
        "concept": "creepy",
        "lines": [
            "MEMORY MANAGER",
            "NOT INSTALLED",
            "SYSTEM UNSTABLE",
        ],
        "footer": "C:\\> _",
    },
    {
        "concept": "creepy",
        "lines": [
            "SYSTEM HALTED",
            "CLOCK CORE LOCKED",
            "...just kidding",
        ],
        "footer": "Press any key",
    },
]

# Aantal MP3-nummers op de SD-kaart (lied 1 t/m N)
DFPLAYER_TRACK_COUNT = 30
SCHEDULE_NAMED_TONE_MAX = 22
ALARM_REPEAT_MS = 45000  # herstart track pas na ruime speeltijd (voorkomt vroeg afkappen)

# Koppel GIF-namen aan een alarm-tone (muziek + LEDs).
# Voeg hier nieuwe GIFs toe die je aan een specifiek liedje wilt koppelen.
# Waarde None = geen koppeling, gebruiker kiest zelf tone.
GIF_TONE_MAP = {
    "mario": "2",
    "zelda": "1",
    "doom":  "10",
    "knight_rider": "11",
}


def get_alarm_tone_options():
    labels = {
        1: "Zelda", 2: "Mario", 3: "Synthwave", 4: "Sonic", 
        5: "Metroid", 6: "Pokemon", 7: "Tetris", 8: "Moonstone", 9: "Arcade",
        10: "DOOM", 11: "Knight Rider", 12: "Fire", 13: "Heartbeat",
        14: "Matrix", 15: "Pac-Man", 16: "Pong", 17: "Radar",
        18: "Skull", 19: "Snake", 20: "Space", 21: "UFO", 22: "Donkey"
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
        10: "Helrood/oranje doom flicker",
        11: "Rode scanner sweep",
        12: "Vlammen rood -> geel",
        13: "Dubbele hartslag pulse",
        14: "Groene matrix rain",
        15: "Pac-Man chase + ghost",
        16: "Pong bal met paddles",
        17: "Radar sweep + ping",
        18: "Bone-white flashes + paars",
        19: "Snake head/tail chase",
        20: "Space twinkle stars",
        21: "UFO beam + hull pulse",
        22: "Retro amber/brown arcade",
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

_HTML_FILE = "index_v6.html"
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
        self._contrast = 0x7F
        self._display_on = True
        self.fill(0)
        self.show()

    def set_contrast(self, value):
        value = max(0, min(255, int(value)))
        if value == self._contrast:
            return
        self.i2c.writeto(self.addr, bytes((0x80, 0x81)))
        self.i2c.writeto(self.addr, bytes((0x80, value)))
        self._contrast = value

    def display_on(self, enabled=True):
        enabled = bool(enabled)
        if enabled == self._display_on:
            return
        self.i2c.writeto(self.addr, bytes((0x80, 0xAF if enabled else 0xAE)))
        self._display_on = enabled

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

            # Zet een herkenbare netwerknaam voor DHCP/local DNS waar ondersteund.
            try:
                self.sta.config(dhcp_hostname=WIFI_HOSTNAME)
                print("WiFi hostname:", WIFI_HOSTNAME)
            except Exception:
                try:
                    network.hostname(WIFI_HOSTNAME)
                    print("WiFi hostname:", WIFI_HOSTNAME)
                except Exception:
                    pass

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
    def _parse_utc_offset_seconds(tz_name):
        if not isinstance(tz_name, str):
            return 0
        s = tz_name.strip().upper()
        if s == "UTC":
            return 0
        if not s.startswith("UTC") or len(s) <= 3:
            return 0
        raw = s[3:]
        sign = 1
        if raw.startswith("+"):
            raw = raw[1:]
        elif raw.startswith("-"):
            sign = -1
            raw = raw[1:]
        raw = raw.strip()
        if not raw:
            return 0
        hh = 0
        mm = 0
        try:
            if ":" in raw:
                parts = raw.split(":", 1)
                hh = int(parts[0] or "0")
                mm = int(parts[1] or "0")
            elif len(raw) > 2 and raw.isdigit():
                hh = int(raw[:-2])
                mm = int(raw[-2:])
            else:
                hh = int(raw)
                mm = 0
        except Exception:
            return 0
        if hh > 14:
            hh = 14
        if mm < 0:
            mm = 0
        if mm > 59:
            mm = 59
        return sign * (hh * 3600 + mm * 60)

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
        off_sec = self._parse_utc_offset_seconds(self.timezone_name)
        base = (utc_tuple[0], utc_tuple[1], utc_tuple[2], utc_tuple[3], utc_tuple[4], utc_tuple[5], 0, 0)
        shifted = time.localtime(time.mktime(base) + off_sec)
        if off_sec == 0:
            label = "UTC"
        else:
            sign = "+" if off_sec > 0 else "-"
            total_min = abs(off_sec) // 60
            hh = total_min // 60
            mm = total_min % 60
            label = "UTC{}{:02d}:{:02d}".format(sign, hh, mm)
        return (shifted[0], shifted[1], shifted[2], shifted[3], shifted[4], shifted[5], shifted[6] + 1, shifted[7]), label

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
        self.ui_language = "nl"
        self.wifi_keep_alive = False
        self.weather_updates_per_day = 4
        self.auto_update_enabled = False
        self.update_manifest_url = DEFAULT_UPDATE_MANIFEST_URL
        self.update_check_interval_hours = 24
        self.retro_fact_display_seconds = DEFAULT_RETRO_FACT_DISPLAY_SECONDS
        self.dos_idle_enabled = DEFAULT_DOS_IDLE_ENABLED
        self.dos_idle_trigger_minutes = DEFAULT_DOS_IDLE_TRIGGER_MINUTES
        self.dos_idle_max_per_day = DEFAULT_DOS_IDLE_MAX_PER_DAY
        self.setup_mode = False
        self.setup_reason = ""
        self.setup_ap_ssid = SETUP_AP_SSID
        self.ap = None
        self._pending_restart_ms = None
        if self.config:
            self.ui_language = self._normalize_ui_language(self.config.get("ui", "language", "nl"))
            self.wifi_keep_alive = bool(self.config.get("wifi", "keep_alive", False))
            raw_updates = self.config.get("weather", "updates_per_day", None)
            if raw_updates is None:
                interval_s = int(self.config.get("weather", "interval_s", 0) or 0)
                if interval_s > 0:
                    raw_updates = max(1, min(24, int(86400 // interval_s)))
            self.weather_updates_per_day = self._normalize_weather_updates_per_day(raw_updates)
            self.auto_update_enabled = bool(self.config.get("update", "auto_update_enabled", False))
            self.update_manifest_url = self._normalize_manifest_url(self.config.get("update", "manifest_url", DEFAULT_UPDATE_MANIFEST_URL))
            self.update_check_interval_hours = self._normalize_update_check_interval_hours(
                self.config.get("update", "check_interval_hours", 24)
            )
            self.retro_fact_display_seconds = self._normalize_retro_fact_display_seconds(
                self.config.get("retro_fact", "display_seconds", DEFAULT_RETRO_FACT_DISPLAY_SECONDS)
            )
            self.dos_idle_enabled = bool(self.config.get("dos_idle", "enabled", DEFAULT_DOS_IDLE_ENABLED))
            self.dos_idle_trigger_minutes = self._normalize_dos_idle_trigger_minutes(
                self.config.get("dos_idle", "trigger_minutes", DEFAULT_DOS_IDLE_TRIGGER_MINUTES)
            )
            self.dos_idle_max_per_day = self._normalize_dos_idle_max_per_day(
                self.config.get("dos_idle", "max_per_day", DEFAULT_DOS_IDLE_MAX_PER_DAY)
            )

        self.clock = ClockCore(timezone)
        self.alarm_until = None
        self.alarm_started_ms = None
        self.snooze_until = None
        self.snooze_tone = None
        self.snooze_gif = ""
        self.active_tone = self.tone
        self.active_led_tone = self.tone
        self.active_gif = ""
        self._skip_intro = False
        self._in_intro = False
        self.alarm_edit_mode = False
        self.alarm_edit_last_change_ms = 0
        self.alarm_edit_hold_hint_until = 0
        self.alarm_edit_hour = 7
        self.alarm_edit_minute = 0
        self.alarm_edit_day_key = "mon"
        self._skip_once_alarm = None  # (year, month, day, hour, minute) for one-time skip
        self._set_feedback_text = ""
        self._set_feedback_until = 0
        self._set_feedback_lines = []
        self._intro_audio_playing = False
        self.last_schedule_fire = None
        self.alarm_schedule = self._default_alarm_schedule()
        if self.config:
            self.alarm_schedule = self._normalize_alarm_schedule(self.config.get("alarm_schedule", None, self.alarm_schedule))
        self.alarm_combo = self._default_alarm_combo()
        if self.config:
            self.alarm_combo = self._normalize_alarm_combo(self.config.get("alarm_combo", None, self.alarm_combo))
        self.alarm_gif_combo = self._default_alarm_gif_combo()
        if self.config:
            self.alarm_gif_combo = self._normalize_alarm_gif_combo(self.config.get("alarm_gif_combo", None, self.alarm_gif_combo))

        # GIF → toon koppeling (instelbaar via webinterface, opgeslagen in gif_tone_map.json)
        self._gif_tone_overrides = {}
        try:
            with open("gif_tone_map.json", "r") as _f:
                self._gif_tone_overrides = json.loads(_f.read())
        except Exception:
            pass

        # GIF → LED-tone koppeling (apart instelbaar), opgeslagen in gif_led_map.json
        self._gif_led_overrides = {}
        try:
            with open("gif_led_map.json", "r") as _f:
                self._gif_led_overrides = json.loads(_f.read())
        except Exception:
            pass

        # Track labels (instelbaar via webinterface, opgeslagen in track_labels.json)
        self._track_labels = {}
        try:
            with open("track_labels.json", "r") as _f:
                self._track_labels = json.loads(_f.read())
        except Exception:
            pass

        self.wifi = None
        self.wifi_ok = False
        self.wifi_disabled = False
        self.wifi_reconnect_after_ms = 0
        self.wifi_auto_off_ms = self._next_wifi_auto_off_deadline()
        self.webserver_ready_after_ms = None
        self._ntp_synced_once = False
        self.startup_ip_until = None
        self.sock = None
        self.wifi_manual_until = None
        self.last_daily_sync_key = None
        self.next_daily_check_ms = time.ticks_add(time.ticks_ms(), WIFI_DAILY_CHECK_MS)
        self.next_daily_sync_attempt_ms = time.ticks_ms()
        self._display_dim_state = None
        self._display_manual_mode = 0  # 0=normaal, 1=dim, 2=rand, 3=extra dim
        self._alarm_repeat_track = True  # True=blijven herhalen, False=eenmalig (preview)
        self._weather_phase = 0
        self._rtc_temp = None
        self._rtc_temp_next_ms = 0
        self._weather_code = None      # WMO weathercode van Open-Meteo
        self._weather_temp = None      # buitentemperatuur °C (int)
        self._weather_next_ms = 0      # tijdstip eerste fetch (meteen bij opstart)
        self._weather_interval_ms = self._compute_weather_interval_ms(self.weather_updates_per_day)
        self._update_next_check_ms = time.ticks_add(time.ticks_ms(), 90000)
        self._update_last_check_ms = 0
        self._update_last_error = ""
        self._update_last_status = "idle"
        self._update_latest_version = APP_VERSION
        self._update_pending = False
        self._update_manifest_cache = None
        self._retro_fact_pending = False
        self._retro_fact_text = ""
        self._retro_fact_source = ""
        self._set_feedback_start_ms = 0
        self._retro_fact_until = 0
        self._last_activity_ms = time.ticks_ms()
        self._dos_idle_active_until = 0
        self._dos_idle_next_scene_ms = 0
        self._dos_idle_scene = None
        self._dos_idle_scene_cursor = True
        self._dos_idle_day_key = ""
        self._dos_idle_shown_today = 0
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
        self._dfplayer_track_num = None
        self._dfplayer_last_start_ms = 0

        self.leds = None
        self._leds_failed = False
        self._led_sunrise_active = False
        self._nightlight_on = False

        # GIF-animatie state (alarm)
        self._gif_file = None
        self._gif_n_frames = 0
        self._gif_frame_size = 0
        self._gif_delays = []
        self._gif_cur_frame = 0
        self._gif_next_ms = 0
        self._gif_data_offset = 0
        self._gif_runtime_failed = False
        self._gif_frame_buf = bytearray(128 * 64 // 8)
        self._gif_fb = framebuf.FrameBuffer(self._gif_frame_buf, 128, 64, framebuf.MONO_VLSB)

        # Zorg dat de strip direct bij boot in een bekende UIT-toestand staat.
        self._ensure_leds_ready()
        if self.leds is not None:
            try:
                self.leds.clear()
            except Exception:
                pass

        # Onboard board LED may be on during boot; force off afterwards.
        self._setup_board_led_control()
        self._status_led_tick = 0

        self.btn_up = Pin(UP_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.btn_down = Pin(DOWN_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.btn_set = Pin(SET_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        # start=tijdstip indrukken, fired_long=lange druk al uitgevoerd,
        # last_edge=debounce timestamp, pending=actie klaar voor uitvoering
        self._button_state = {
            "set":  {"start": 0, "fired_long": False, "last_edge": 0, "pending": None},
            "up":   {"start": 0, "fired_long": False, "last_edge": 0, "pending": None},
            "down": {"start": 0, "fired_long": False, "last_edge": 0, "pending": None},
        }

        # Hardware IRQ op falling + rising edge:
        # - UP/SET/DOWN wachten tot loslaten om te bepalen of het kort of lang was
        _bs = self._button_state
        def _make_irq(name, has_long_cb, long_ms=0):
            s = _bs[name]
            def handler(p):
                now = time.ticks_ms()
                if time.ticks_diff(now, s["last_edge"]) < 40:
                    return
                s["last_edge"] = now
                if p.value() == 0:  # falling edge = ingedrukt
                    s["start"] = now
                    s["fired_long"] = False
                    if not has_long_cb:
                        s["pending"] = "short"  # direct actie op druk
                    # SET knop tijdens intro -> alleen overslaan (geen short/long actie na intro).
                    if name == "set" and self._in_intro:
                        self._skip_intro = True
                        s["pending"] = None
                        s["fired_long"] = True
                else:  # rising edge = losgelaten
                    if has_long_cb and not s["fired_long"]:
                        held_ms = time.ticks_diff(now, s["start"]) if s["start"] > 0 else 0
                        # Fallback: als de poll-loop de lange druk net miste,
                        # herken hem alsnog netjes bij loslaten.
                        if long_ms > 0 and held_ms >= long_ms:
                            s["pending"] = "long"
                            s["fired_long"] = True
                        else:
                            s["pending"] = "short"
            return handler
        self.btn_up.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=_make_irq("up", False, 0))
        self.btn_down.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=_make_irq("down", True, 3000))
        self.btn_set.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=_make_irq("set", True, 2200))

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
            self._start_setup_ap("Geen WiFi verbinding")
        self._apply_display_brightness(force=True)

    def _normalize_weather_updates_per_day(self, value):
        try:
            n = int(value)
        except Exception:
            return 4
        if n < 1:
            return 1
        if n > 24:
            return 24
        return n

    def _normalize_ui_language(self, value):
        lang = str(value or "nl").strip().lower()
        return "en" if lang == "en" else "nl"

    def _compute_weather_interval_ms(self, updates_per_day):
        updates = self._normalize_weather_updates_per_day(updates_per_day)
        return max(60 * 60 * 1000, (24 * 3600 * 1000) // updates)

    def _normalize_update_check_interval_hours(self, value):
        try:
            n = int(value)
        except Exception:
            return 24
        if n < 1:
            return 1
        if n > 168:
            return 168
        return n

    def _normalize_retro_fact_display_seconds(self, value):
        try:
            n = int(value)
        except Exception:
            return DEFAULT_RETRO_FACT_DISPLAY_SECONDS
        if n < 1:
            return 1
        if n > 60:
            return 60
        return n

    def _normalize_dos_idle_trigger_minutes(self, value):
        try:
            n = int(value)
        except Exception:
            return DEFAULT_DOS_IDLE_TRIGGER_MINUTES
        if n < 1:
            return 1
        if n > 120:
            return 120
        return n

    def _normalize_dos_idle_max_per_day(self, value):
        try:
            n = int(value)
        except Exception:
            return DEFAULT_DOS_IDLE_MAX_PER_DAY
        if n < 0:
            return 0
        if n > 200:
            return 200
        return n

    def _mark_activity(self):
        self._last_activity_ms = time.ticks_ms()
        if self._dos_idle_active_until:
            self._dos_idle_active_until = 0
            self._dos_idle_scene = None

    def _current_day_key(self):
        t = self.clock.read_time()
        return "{:04d}-{:02d}-{:02d}".format(int(t[0]), int(t[1]), int(t[2]))

    def _roll_dos_idle_day(self):
        day_key = self._current_day_key()
        if self._dos_idle_day_key != day_key:
            self._dos_idle_day_key = day_key
            self._dos_idle_shown_today = 0

    def _pick_dos_idle_scene(self):
        if not DOS_IDLE_SCENES:
            return None
        base = int(time.ticks_ms()) + (self._dos_idle_shown_today * 17)
        idx = base % len(DOS_IDLE_SCENES)
        scene = DOS_IDLE_SCENES[idx]
        if scene.get("concept") == "creepy":
            # Creepy mode komt minder vaak voor dan grappig/boot.
            if (base // 7) % 3 != 0:
                idx = (idx + 1) % len(DOS_IDLE_SCENES)
                scene = DOS_IDLE_SCENES[idx]
        return scene

    def _advance_dos_idle_scene(self, now_ms, force=False):
        if (not force) and self._dos_idle_next_scene_ms and time.ticks_diff(now_ms, self._dos_idle_next_scene_ms) < 0:
            return
        self._dos_idle_scene = self._pick_dos_idle_scene()
        self._dos_idle_scene_cursor = ((now_ms // 280) % 2) == 0
        self._dos_idle_next_scene_ms = time.ticks_add(now_ms, 1700 + ((now_ms // 11) % 1800))

    def _start_dos_idle(self, manual=False):
        self._roll_dos_idle_day()
        if not manual:
            if not self.dos_idle_enabled:
                return False
            if self.dos_idle_max_per_day > 0 and self._dos_idle_shown_today >= self.dos_idle_max_per_day:
                return False
            self._dos_idle_shown_today += 1

        now_ms = time.ticks_ms()
        self._dos_idle_active_until = time.ticks_add(now_ms, 12000)
        self._dos_idle_next_scene_ms = 0
        self._dos_idle_scene = None
        self._advance_dos_idle_scene(now_ms, force=True)
        return True

    def _check_dos_idle(self):
        self._roll_dos_idle_day()
        if self._dos_idle_active_until:
            return
        if not self.dos_idle_enabled:
            return
        if self.setup_mode or self.alarm_edit_mode:
            return
        if self.alarm_until is not None or self.snooze_until is not None:
            return
        if self._set_feedback_until and time.ticks_diff(self._set_feedback_until, time.ticks_ms()) > 0:
            return

        idle_ms = self.dos_idle_trigger_minutes * 60 * 1000
        if time.ticks_diff(time.ticks_ms(), self._last_activity_ms) < idle_ms:
            return
        self._start_dos_idle(manual=False)

    def _draw_dos_idle(self):
        now_ms = time.ticks_ms()
        if not self._dos_idle_active_until:
            return False
        if time.ticks_diff(self._dos_idle_active_until, now_ms) <= 0:
            self._dos_idle_active_until = 0
            self._dos_idle_scene = None
            return False

        self._advance_dos_idle_scene(now_ms)
        scene = self._dos_idle_scene or {"lines": ["C:\\>", "idle", "..."], "footer": "C:\\>_"}
        lines = scene.get("lines", [])
        footer = str(scene.get("footer", "C:\\>"))
        blink = ((now_ms // 300) % 2) == 0

        self.display.fill(0)
        self.display.rect(0, 0, 128, 64, 1)
        self.display.text("RETRO DOS", 2, 2, 1)
        self.display.text("C:\\>", 2, 12, 1)
        if blink:
            self.display.fill_rect(34, 19, 4, 1, 1)

        y = 24
        for line in lines[:3]:
            self.display.text(str(line)[:20], 2, y, 1)
            y += 10

        self.display.text(footer[:20], 2, 56, 1)
        self.display.show()
        return True

    def _normalize_manifest_url(self, value):
        raw = str(value or "").strip()
        if raw.startswith("http://") or raw.startswith("https://"):
            return raw
        return DEFAULT_UPDATE_MANIFEST_URL

    def _version_tuple(self, value):
        s = str(value or "0").strip().lower()
        if s.startswith("v"):
            s = s[1:]
        out = []
        for part in s.split("."):
            try:
                out.append(int(part))
            except Exception:
                out.append(0)
        while len(out) < 3:
            out.append(0)
        return tuple(out[:3])

    def _is_newer_version(self, latest, current):
        return self._version_tuple(latest) > self._version_tuple(current)

    def _safe_update_filename(self, value):
        raw = str(value or "").strip()
        if not raw or "/" in raw or "\\" in raw:
            return ""
        safe = "".join(ch for ch in raw if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch in ("_", "-", "."))
        return safe[:64]

    def _parse_url(self, url):
        txt = str(url or "").strip()
        secure = False
        if txt.startswith("https://"):
            secure = True
            rest = txt[8:]
            default_port = 443
        elif txt.startswith("http://"):
            rest = txt[7:]
            default_port = 80
        else:
            raise ValueError("URL moet met http:// of https:// beginnen")

        slash = rest.find("/")
        if slash >= 0:
            hostport = rest[:slash]
            path = rest[slash:]
        else:
            hostport = rest
            path = "/"

        if not hostport:
            raise ValueError("URL host ontbreekt")

        host = hostport
        port = default_port
        if ":" in hostport:
            hp = hostport.rsplit(":", 1)
            host = hp[0].strip()
            try:
                port = int(hp[1])
            except Exception:
                raise ValueError("Ongeldige URL poort")
        if not host:
            raise ValueError("Ongeldige URL host")
        return secure, host, port, path

    def _http_get_bytes(self, url, max_bytes=180000, timeout_s=12):
        secure, host, port, path = self._parse_url(url)
        s = socket.socket()
        try:
            s.settimeout(timeout_s)
            addr = socket.getaddrinfo(host, port)[0][-1]
            s.connect(addr)
            if secure:
                if ssl is None:
                    raise ValueError("HTTPS niet ondersteund door deze firmware")
                s = ssl.wrap_socket(s, server_hostname=host)

            req = "GET {} HTTP/1.0\r\nHost: {}\r\nUser-Agent: AlarmKlok/{}\r\n\r\n".format(path, host, APP_VERSION)
            s.send(req.encode())
            resp = b""
            while True:
                chunk = s.recv(512)
                if not chunk:
                    break
                resp += chunk
                if len(resp) > max_bytes:
                    raise ValueError("Download te groot")
        finally:
            try:
                s.close()
            except Exception:
                pass

        head_end = resp.find(b"\r\n\r\n")
        if head_end < 0:
            raise ValueError("Ongeldig HTTP antwoord")
        header = resp[:head_end].decode("utf-8", "ignore")
        if " 200 " not in header.split("\r\n", 1)[0]:
            status = header.split("\r\n", 1)[0]
            raise ValueError("HTTP fout: {}".format(status))
        return resp[head_end + 4:]

    def _sha256_hex(self, data):
        if hashlib is None:
            return None
        try:
            h = hashlib.sha256()
            h.update(data)
            digest = h.digest()
            if binascii is not None:
                return binascii.hexlify(digest).decode().lower()
            # Fallback zonder binascii
            return "".join("%02x" % b for b in digest)
        except Exception:
            return None

    def _next_wifi_auto_off_deadline(self):
        if self.wifi_keep_alive:
            return None
        return time.ticks_add(time.ticks_ms(), 30 * 60 * 1000)

    def _apply_network_settings(self, reset_wifi_timer=False):
        self.weather_updates_per_day = self._normalize_weather_updates_per_day(self.weather_updates_per_day)
        self._weather_interval_ms = self._compute_weather_interval_ms(self.weather_updates_per_day)
        if reset_wifi_timer:
            if self.wifi_disabled:
                self.wifi_auto_off_ms = None
            else:
                self.wifi_auto_off_ms = self._next_wifi_auto_off_deadline()

    def _schedule_restart(self, delay_ms=1500):
        self._pending_restart_ms = time.ticks_add(time.ticks_ms(), int(delay_ms))

    def _get_setup_ip(self):
        try:
            if self.ap and self.ap.active():
                return self.ap.ifconfig()[0]
        except Exception:
            pass
        return SETUP_AP_IP

    def _start_setup_ap(self, reason=""):
        self._close_webserver()
        self.setup_mode = True
        self.setup_reason = str(reason or "WiFi instellen")
        self.wifi_ok = False
        self.wifi_disabled = True
        self.startup_ip_until = None
        try:
            if self.wifi and self.wifi.sta:
                try:
                    self.wifi.sta.disconnect()
                except Exception:
                    pass
                try:
                    self.wifi.sta.active(False)
                except Exception:
                    pass
        except Exception:
            pass
        self.wifi = None
        try:
            if self.ap is None:
                self.ap = network.WLAN(network.AP_IF)
            try:
                self.ap.active(False)
            except Exception:
                pass
            self.ap.active(True)
            try:
                self.ap.ifconfig((SETUP_AP_IP, "255.255.255.0", SETUP_AP_IP, SETUP_AP_IP))
            except Exception:
                pass
            try:
                self.ap.config(essid=self.setup_ap_ssid)
            except Exception:
                pass
            print("SETUP AP actief:", self.setup_ap_ssid, self._get_setup_ip())
        except Exception as e:
            print("! Setup AP start fout:", e)
            self.ap = None
        self.webserver_ready_after_ms = time.ticks_ms()
        self._start_webserver_if_ready()

    def _toggle_wifi_profile(self):
        if not self.config:
            print("! Geen config beschikbaar voor WiFi-profielwissel")
            return False
        result = self.config.toggle_wifi_profile()
        if not result.get("ok"):
            print("! WiFi-profiel wisselen mislukt:", result.get("error", "onbekend"))
            self._set_feedback_lines = ["WiFi wissel fout", str(result.get("error", "onbekend"))[:16]]
            self._set_feedback("", ms=2500)
            return False
        wifi_cfg = self.config.get("wifi", None, {}) or {}
        self.wifi_ssid = str(wifi_cfg.get("ssid", DEFAULT_WIFI_SSID) or DEFAULT_WIFI_SSID).strip()
        self.wifi_password = str(wifi_cfg.get("password", "") or "")
        self.wifi_keep_alive = bool(wifi_cfg.get("keep_alive", False))
        self._apply_network_settings(reset_wifi_timer=True)
        label = "default WiFi" if result.get("target") == "default" else "custom WiFi"
        self._set_feedback_lines = ["WiFi profiel:", self.wifi_ssid[:16], "Herstart..."]
        self._set_feedback("", ms=2500)
        print("WiFi profiel actief:", label, self.wifi_ssid)
        self._schedule_restart(1200)
        return True

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

    def _setup_board_led_control(self):
        """Best effort onboard LED control; harmless if pin isn't connected."""
        self._board_led_pin = None
        self._board_led_np = None
        try:
            self._board_led_pin = Pin(BOARD_LED_PIN, Pin.OUT)
            self._board_led_pin.value(0)
            if neopixel is not None:
                try:
                    self._board_led_np = neopixel.NeoPixel(self._board_led_pin, 1, bpp=3, timing=1)
                    self._board_led_np[0] = (0, 0, 0)
                    self._board_led_np.write()
                except Exception:
                    self._board_led_np = None
        except Exception:
            self._board_led_pin = None
            self._board_led_np = None

    def _board_led_off(self):
        """Force onboard LED off after boot sequence."""
        try:
            if self._board_led_np is not None:
                self._board_led_np[0] = (0, 0, 0)
                self._board_led_np.write()
            if self._board_led_pin is not None:
                self._board_led_pin.value(0)
        except Exception:
            pass

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
        if self.setup_mode:
            return False
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
        if ((not self.wifi_ok and not self.setup_mode) or self.sock is not None):
            return

        if self.webserver_ready_after_ms is not None and time.ticks_diff(time.ticks_ms(), self.webserver_ready_after_ms) < 0:
            return

        ip = self._get_setup_ip() if self.setup_mode else (self.wifi.get_ip() if self.wifi else "0.0.0.0")
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
        if self.setup_mode:
            self._start_webserver_if_ready()
            return
        now = time.ticks_ms()

        # Auto-off na 30 minuten na opstarten
        if (not self.wifi_keep_alive) and (not self.wifi_disabled) and self.wifi_auto_off_ms is not None and time.ticks_diff(now, self.wifi_auto_off_ms) >= 0:
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
                # Na sync alleen uitzetten als keep-alive uit staat.
                if self.wifi_keep_alive:
                    self.wifi_disabled = False
                    self.wifi_auto_off_ms = None
                else:
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

    def _default_alarm_gif_combo(self):
        # Standaard: per dag willekeurige GIF-animatie.
        return {k: "random" for k in DAY_KEYS}

    def _normalize_alarm_gif_combo(self, raw):
        out = self._default_alarm_gif_combo()
        if not isinstance(raw, dict):
            return out
        for k in DAY_KEYS:
            val = raw.get(k, "random")
            if isinstance(val, str):
                # Lege waarde betekent: geen GIF forceren, gebruik tone-keuze.
                if val == "":
                    out[k] = ""
                    continue
                safe = "".join(c for c in val if ('a' <= c <= 'z') or ('A' <= c <= 'Z') or ('0' <= c <= '9') or c in ('-', '_'))
                safe = safe[:32]
                out[k] = safe if safe else "random"
        return out

    def _get_gif_tone(self, gif_name):
        """Geeft de gekoppelde toon-key voor een GIF, overrides hebben prioriteit."""
        if gif_name in self._gif_tone_overrides:
            return self._gif_tone_overrides[gif_name]
        return GIF_TONE_MAP.get(gif_name)

    def _get_gif_led_tone(self, gif_name):
        """Geeft de gekoppelde LED-tone-key voor een GIF (apart van muziek)."""
        if gif_name in self._gif_led_overrides:
            return self._gif_led_overrides[gif_name]
        # Fallback: als geen aparte LED-koppeling, gebruik de muziek-koppeling
        return self._get_gif_tone(gif_name)

    def _save_track_labels(self):
        try:
            with open("track_labels.json", "w") as _f:
                _f.write(json.dumps(self._track_labels))
        except Exception as _e:
            print("! track_labels.json schrijven mislukt:", _e)

    def _save_gif_tone_overrides(self):
        try:
            with open("gif_tone_map.json", "w") as _f:
                _f.write(json.dumps(self._gif_tone_overrides))
        except Exception as _e:
            print("! gif_tone_map.json schrijven mislukt:", _e)

    def _save_gif_led_overrides(self):
        try:
            with open("gif_led_map.json", "w") as _f:
                _f.write(json.dumps(self._gif_led_overrides))
        except Exception as _e:
            print("! gif_led_map.json schrijven mislukt:", _e)

    def _merged_gif_tone_map(self):
        merged = {k: v for k, v in GIF_TONE_MAP.items() if v is not None}
        merged.update({k: v for k, v in self._gif_tone_overrides.items() if v})
        return merged

    def _merged_gif_led_map(self):
        merged = {k: v for k, v in GIF_TONE_MAP.items() if v is not None}
        merged.update({k: v for k, v in self._gif_led_overrides.items() if v})
        return merged

    def _list_gif_names(self):
        import os as _os
        names = []
        search_paths = ('/' + ANIMATIONS_DIR, ANIMATIONS_DIR, '/', '.')
        for path in search_paths:
            try:
                for f in _os.listdir(path):
                    if isinstance(f, str) and f.endswith('.bin'):
                        names.append(f[:-4])
            except Exception:
                pass
        return sorted(set(names))

    def _list_gif_choices(self):
        # Voor UI animatiebeheer: ALLE .bin bestanden (ook zonder muziekkoppeling).
        # Dit laat je ze allemaal kunnen inschakelen/koppelen.
        return ["random"] + self._list_gif_names()
    
    def _list_random_gif_choices(self):
        # Voor random pool: alleen gifs MET muziekkoppeling.
        all_names = self._list_gif_names()
        merged = self._merged_gif_tone_map()
        filtered = [g for g in all_names if g in merged]
        return ["random"] + filtered

    def _get_gif_mapping_status(self):
        # Geeft alle GIFs met mapping status: {"name": "mario", "mapped": true}
        all_names = self._list_gif_names()
        merged = self._merged_gif_tone_map()
        return [{"name": g, "mapped": g in merged} for g in sorted(all_names)]

    def _get_storage_info(self):
        # Geeft opslagstatus terug zodat web UI upload-limiet kan bewaken.
        try:
            import os as _os
            st = _os.statvfs('/')
            block_size = int(st[0])
            total_bytes = block_size * int(st[2])
            free_bytes = block_size * int(st[3])
            used_bytes = max(0, total_bytes - free_bytes)
            reserve_bytes = 128 * 1024  # buffer om crashes door volle flash te voorkomen
            upload_max_bytes = max(0, free_bytes - reserve_bytes)
            percent_used = int((used_bytes * 100) // total_bytes) if total_bytes > 0 else 0
            return {
                "total_bytes": total_bytes,
                "used_bytes": used_bytes,
                "free_bytes": free_bytes,
                "reserve_bytes": reserve_bytes,
                "upload_max_bytes": upload_max_bytes,
                "percent_used": percent_used,
            }
        except Exception:
            return {
                "total_bytes": 0,
                "used_bytes": 0,
                "free_bytes": 0,
                "reserve_bytes": 0,
                "upload_max_bytes": 0,
                "percent_used": 0,
            }

    def _get_boot_mode(self):
        try:
            with open("boot_mode.txt", "r") as f:
                mode = (f.read() or "primary").strip().lower()
                if mode in ("primary", "backup"):
                    return mode
        except Exception:
            pass
        return "primary"

    def _pick_alarm_gif(self, gif_setting):
        if not isinstance(gif_setting, str):
            return ""
        if gif_setting == "random":
            all_names = self._list_gif_names()
            if not all_names:
                return ""
            # Filter alleen gifs met muziekkoppeling uit de merged map.
            merged = self._merged_gif_tone_map()
            names = [g for g in all_names if g in merged]
            if not names:
                return ""  # fallback: geen gekoppelde gifs beschikbaar
            # Lichtgewicht pseudo-random keuze zonder extra modules.
            t = self.clock.read_time()
            seed = (int(t[0]) * 1000000) + (int(t[1]) * 10000) + (int(t[2]) * 100) + int(t[5])
            seed ^= int(time.ticks_ms())
            idx = seed % len(names)
            return names[idx]
        return gif_setting

    def _is_named_schedule_tone(self, tone):
        try:
            n = int(tone)
        except Exception:
            return False
        return 1 <= n <= SCHEDULE_NAMED_TONE_MAX

    def _pick_named_schedule_tone(self):
        # Kies deterministisch een van de benoemde tones (geen generieke "Lied N").
        max_tone = min(int(DFPLAYER_TRACK_COUNT), int(SCHEDULE_NAMED_TONE_MAX))
        if max_tone < 1:
            return "1"
        t = self.clock.read_time()
        seed = (int(t[0]) * 1000000) + (int(t[1]) * 10000) + (int(t[2]) * 100) + int(t[5])
        seed ^= int(time.ticks_ms())
        return str((seed % max_tone) + 1)

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

        # Eenmalige skip: alleen deze specifieke datum+tijd overslaan.
        if self._skip_once_alarm == fire_key:
            self.last_schedule_fire = fire_key
            self._skip_once_alarm = None
            print("Alarm eenmalig overgeslagen voor {:04d}-{:02d}-{:02d} {:02d}:{:02d}".format(*fire_key))
            return

        self.last_schedule_fire = fire_key
        self.snooze_until = None
        self.snooze_tone = None
        self.snooze_gif = ""
        self.active_tone = self._normalize_tone_key(self.alarm_combo.get(day_key, self._tone_now()))
        self.active_led_tone = self.active_tone
        gif_setting = self.alarm_gif_combo.get(day_key, "random")
        self.active_gif = self._pick_alarm_gif(gif_setting)
        self._gif_runtime_failed = False
        # Overschrijf tone als de gekozen GIF een vaste koppeling heeft
        if self.active_gif and self._get_gif_tone(self.active_gif) is not None:
            self.active_tone = self._normalize_tone_key(self._get_gif_tone(self.active_gif))
            print("GIF-tone koppeling: {} -> tone {}".format(self.active_gif, self.active_tone))
        if self.active_gif and self._get_gif_led_tone(self.active_gif) is not None:
            self.active_led_tone = self._normalize_tone_key(self._get_gif_led_tone(self.active_gif))
            print("GIF-LED koppeling: {} -> led tone {}".format(self.active_gif, self.active_led_tone))
        if gif_setting == "random" and not self._is_named_schedule_tone(self.active_tone):
            self.active_tone = self._pick_named_schedule_tone()
            print("Random schema: LIED-tone geblokkeerd, fallback tone {}".format(self.active_tone))
            if not self._is_named_schedule_tone(self.active_led_tone):
                self.active_led_tone = self.active_tone
        self._alarm_repeat_track = True
        self.alarm_started_ms = time.ticks_ms()
        self.alarm_until = time.ticks_add(time.ticks_ms(), ALARM_AUTO_STOP_MS)

    def _wrap_feedback_lines(self, text, max_chars=16, limit=4):
        words = [w for w in str(text or "").replace("\n", " ").split(" ") if w]
        lines = []
        current = ""
        for word in words:
            candidate = word if not current else current + " " + word
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
                if len(lines) >= limit:
                    break
        if current and len(lines) < limit:
            lines.append(current)
        if not lines:
            lines = [""]
        return lines[:limit]

    def _draw_feedback_text(self, text, y, now_ms):
        value = str(text or "")
        if not value:
            return
        text_width = len(value) * 8
        if text_width <= 128:
            x = max(0, (128 - text_width) // 2)
            self.display.text(value, x, y, 1)
            return

        # Voor losse lange regels: stack de wrapped regels verticaal in plaats van horizontaal te schuiven.
        wrapped = self._wrap_feedback_lines(value, max_chars=12, limit=4)
        yy = y
        for line in wrapped:
            if line:
                x = max(0, (128 - len(line) * 8) // 2)
                self.display.text(line, x, yy, 1)
            yy += 10

    def _build_retro_fact_fallback(self, t):
        year = int(t[0]) if t and len(t) > 0 else 2000
        month = int(t[1]) if t and len(t) > 1 else 1
        day = int(t[2]) if t and len(t) > 2 else 1
        month_lengths = (31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
        day_of_year = day
        for i in range(max(0, month - 1)):
            day_of_year += month_lengths[i]
        idx = (day_of_year - 1) % len(RETRO_FACT_LIBRARY)
        return RETRO_FACT_LIBRARY[idx]

    def _fetch_retro_game_fact(self):
        t = self.clock.read_time()
        return self._build_retro_fact_fallback(t), "offline"

    def _show_retro_fact(self):
        fact, source = self._fetch_retro_game_fact()
        self._retro_fact_text = fact
        self._retro_fact_source = source
        self._retro_fact_pending = False
        self._set_feedback_lines = ["RETRO FACT", "---"] + self._wrap_feedback_lines(fact, max_chars=12, limit=8)
        self._set_feedback_text = fact
        self._set_feedback_start_ms = time.ticks_ms()
        self._set_feedback_until = time.ticks_add(time.ticks_ms(), self.retro_fact_display_seconds * 1000)
        print("Retro fact:", fact)
        return fact, source

    def _get_retro_fact_preview(self):
        fact, source = self._fetch_retro_game_fact()
        return {
            "ok": True,
            "fact": fact,
            "source": source,
            "mode": "manual",
            "status": "ok",
        }

    def _stop_alarm(self, show_retro_fact=False):
        self.alarm_until = None
        self.alarm_started_ms = None
        self._alarm_repeat_track = True
        self._nightlight_on = False  # alarm overschrijft nachtlampje
        if self.dfplayer is not None:
            try:
                self.dfplayer.stop()
                self.dfplayer.set_volume(0)  # dempt idle ticking
            except Exception:
                pass
        self._dfplayer_playing = False
        self._dfplayer_track_num = None
        self._dfplayer_last_start_ms = 0
        self._intro_audio_playing = False
        if self.leds is not None:
            try:
                self.leds.clear()
            except Exception:
                pass
        self._led_sunrise_active = False
        self._gif_runtime_failed = False
        self.active_gif = ""
        if show_retro_fact:
            self._retro_fact_pending = True
            self._set_feedback_lines = ["RETRO FACT", "laden..."]
            self._set_feedback_text = "RETRO FACT laden..."
            self._set_feedback_start_ms = time.ticks_ms()
            self._set_feedback_until = time.ticks_add(time.ticks_ms(), 10000)
        # Sluit eventueel open GIF-bestand
        if self._gif_file is not None:
            try:
                self._gif_file.close()
            except Exception:
                pass
            self._gif_file = None
            self._gif_delays = []

    def _disable_gif_for_alarm(self, reason=None):
        if reason:
            print("GIF alarm gedeactiveerd:", reason)
        if self._gif_file is not None:
            try:
                self._gif_file.close()
            except Exception:
                pass
        self._gif_file = None
        self._gif_delays = []
        self._gif_runtime_failed = True
        self.active_gif = ""

    def _snooze_alarm(self, minutes=10):
        if self.alarm_until is None:
            return
        self.snooze_tone = self.active_tone
        self.snooze_gif = self.active_gif
        self._stop_alarm(show_retro_fact=False)
        self.snooze_until = time.ticks_add(time.ticks_ms(), int(minutes) * 60 * 1000)
        self._set_feedback("SNOOZE 10 MIN", ms=2000)
        print("Alarm snooze {} min".format(int(minutes)))

    def _snooze_remaining_seconds(self):
        if self.snooze_until is None:
            return 0
        rem_ms = time.ticks_diff(self.snooze_until, time.ticks_ms())
        if rem_ms <= 0:
            return 0
        return (rem_ms + 999) // 1000

    def _current_day_alarm(self):
        t = self.clock.read_time()
        day_idx = (int(t[6]) - 1) % 7
        day_key = DAY_KEYS[day_idx]
        row = self.alarm_schedule.get(day_key, {"enabled": False, "hour": 7, "minute": 0})
        return day_key, row

    def _set_feedback(self, text, ms=2200):
        self._set_feedback_text = str(text or "")
        self._set_feedback_start_ms = time.ticks_ms()
        self._set_feedback_until = time.ticks_add(self._set_feedback_start_ms, int(ms))

    def _next_alarm_entry(self, include_disabled=False):
        t = self.clock.read_time()
        day_abbr = ("ma", "di", "wo", "do", "vr", "za", "zo")
        day_keys = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        cfg = self.alarm_schedule
        if not isinstance(cfg, dict):
            return None
        today_idx = (int(t[6]) - 1) % 7
        cur_h = int(t[3])
        cur_m = int(t[4])
        for offset in range(7):
            di = (today_idx + offset) % 7
            key = day_keys[di]
            alarm = cfg.get(key)
            if alarm is None:
                continue
            enabled = bool(alarm.get("enabled", False))
            if (not include_disabled) and (not enabled):
                continue
            try:
                hh = int(alarm.get("hour", 0))
                mm = int(alarm.get("minute", 0))
            except Exception:
                continue
            if offset == 0 and (hh < cur_h or (hh == cur_h and mm <= cur_m)):
                continue
            return {
                "key": key,
                "day": day_abbr[di],
                "hour": hh,
                "minute": mm,
                "enabled": enabled,
            }
        return None

    def _set_toggle_next_alarm(self):
        day_map = {
            "mon": "maandag", "tue": "dinsdag", "wed": "woensdag",
            "thu": "donderdag", "fri": "vrijdag", "sat": "zaterdag", "sun": "zondag"
        }
        # Eén druk in normaal scherm: sla alleen het eerstvolgende alarm één keer over.
        # Tweede druk voor hetzelfde doel: annuleer die skip weer.
        nxt = self._next_alarm_entry(include_disabled=False)
        if not nxt:
            self._set_feedback_lines = ["Geen actief", "alarm gevonden"]
            self._set_feedback("", ms=2500)
            print("Geen actief alarm om over te slaan")
            return

        key = nxt["key"]
        hh = int(nxt["hour"]) % 24
        mm = int(nxt["minute"]) % 60

        # Bepaal de concrete kalenderdatum van 'nxt'.
        now = self.clock.read_time()
        y = int(now[0])
        mo = int(now[1])
        d = int(now[2])
        days_ahead = (DAY_KEYS.index(key) - ((int(now[6]) - 1) % 7)) % 7
        if days_ahead == 0 and (hh < int(now[3]) or (hh == int(now[3]) and mm <= int(now[4]))):
            days_ahead = 7
        target_day = d + days_ahead
        # Datumberekening via mktime/localtime om maandgrenzen correct af te handelen.
        target_ts = time.mktime((y, mo, target_day, hh, mm, 0, 0, 0))
        target = time.localtime(target_ts)
        target_key = (int(target[0]), int(target[1]), int(target[2]), hh, mm)

        if self._skip_once_alarm == target_key:
            self._skip_once_alarm = None
            self._set_feedback_lines = [
                "Skip geannuleerd:",
                "{} {:02d}:{:02d}".format(day_map.get(key, nxt["day"]), hh, mm),
            ]
            self._set_feedback("", ms=2500)
            print("Skip geannuleerd {} {:02d}:{:02d}".format(day_map.get(key, nxt["day"]), hh, mm))
            return

        self._skip_once_alarm = target_key
        day_txt = day_map.get(key, nxt["day"])
        nxt_after = self._next_alarm_entry(include_disabled=False)
        lines = [
            "Alarm skip 1x:",
            "{} {:02d}:{:02d}".format(day_txt, hh, mm),
            "---",
        ]
        if nxt_after:
            nxt_day = day_map.get(nxt_after["key"], nxt_after["day"])
            lines += [
                "Eerst volgend:",
                "{} {:02d}:{:02d}".format(nxt_day, nxt_after["hour"], nxt_after["minute"]),
            ]
        else:
            lines += ["Geen volgend", "alarm actief"]
        self._set_feedback_lines = lines
        self._set_feedback("", ms=3500)
        print("Alarm 1x skip {} {:02d}:{:02d}".format(day_txt, hh, mm))

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
        self.alarm_edit_last_change_ms = 0
        self.alarm_edit_hold_hint_until = 0
        self.alarm_edit_day_key = day_key
        self.alarm_edit_hour = int(row.get("hour", 7)) % 24
        self.alarm_edit_minute = int(row.get("minute", 0)) % 60
        print("Alarm instellen {} {:02d}:{:02d}".format(day_key, self.alarm_edit_hour, self.alarm_edit_minute))
        self._ensure_leds_ready()
        if self.leds:
            for i in range(self.leds.num_leds):
                self.leds.set_pixel(i, 60, 0, 0)  # dim rood
            self.leds.show()

    def _save_alarm_edit_mode(self):
        self.alarm_schedule[self.alarm_edit_day_key] = {
            "enabled": True,
            "hour": int(self.alarm_edit_hour) % 24,
            "minute": int(self.alarm_edit_minute) % 60,
        }
        self.alarm_edit_mode = False
        self.alarm_edit_hold_hint_until = 0
        if self.config:
            self.config.config["alarm_schedule"] = self.alarm_schedule
            self.config.save()
        if self.eeprom is not None:
            try:
                self.eeprom.save_alarm_schedule(self.alarm_schedule)
            except Exception:
                pass
        print("Alarm opgeslagen {} {:02d}:{:02d}".format(self.alarm_edit_day_key, self.alarm_edit_hour, self.alarm_edit_minute))
        self._play_alarm_saved_animation()
        self._start_clock_transition(use_leds=True)

    def _play_alarm_saved_animation(self):
        if not self.display:
            return
        # Korte, goedkope 8-bit save animatie met rode LED knipper.
        seed = (time.ticks_ms() ^ (self.alarm_edit_hour << 8) ^ self.alarm_edit_minute) & 0x7FFFFFFF
        for fi in range(22):
            self.display.fill(0)
            if fi % 4 < 2:
                self.display.rect(0, 0, 128, 64, 1)
            # 8-bit sterretjes (lichte random sparkle)
            for _i in range(10):
                seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
                x = (seed >> 8) % 128
                seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
                y = (seed >> 16) % 64
                self.display.pixel(x, y, 1)
            if fi >= 4:
                self.display.text("TIJD", 40, 20, 1)
            if fi >= 8:
                self.display.text("OPGESLAGEN", 24, 34, 1)
            if fi >= 12 and (fi % 2 == 0):
                self.display.text("OK", 56, 50, 1)
            self.display.show()

            if self.leds:
                if fi % 2 == 0:
                    for j in range(self.leds.num_leds):
                        self.leds.set_pixel(j, 80, 0, 0)
                    self.leds.show()
                else:
                    self.leds.clear()
            time.sleep_ms(70)

        if self.leds:
            if self._nightlight_on:
                for i in range(self.leds.num_leds):
                    self.leds.set_pixel(i, 255, 120, 40)
                self.leds.show()
            else:
                self.leds.clear()

    def _set_short_press(self):
        if self.alarm_until is not None:
            self._stop_alarm(show_retro_fact=True)
            return
        if self.alarm_edit_mode:
            self.alarm_edit_hold_hint_until = time.ticks_add(time.ticks_ms(), 3000)
            return
        self._set_toggle_next_alarm()

    def _set_long_press(self):
        if self.alarm_until is not None:
            self._stop_alarm(show_retro_fact=True)
            return
        if self.alarm_edit_mode:
            self._save_alarm_edit_mode()
            return
        self._enter_alarm_edit_mode()

    def _up_short_press(self):
        if self.alarm_edit_mode:
            self.alarm_edit_hour = (self.alarm_edit_hour + 1) % 24
            self.alarm_edit_last_change_ms = time.ticks_ms()
            return
        # Normaal scherm: nachtlampje aan/uit
        self._nightlight_on = not self._nightlight_on
        self._ensure_leds_ready()
        if self.leds:
            if self._nightlight_on:
                # Warm wit, laag vermogen (~30% brightness)
                for i in range(self.leds.num_leds):
                    self.leds.set_pixel(i, 255, 120, 40)
                self.leds.show()
                print("Nachtlampje AAN")
            else:
                self.leds.clear()
                print("Nachtlampje UIT")

    def _down_short_press(self):
        if self.alarm_until is not None:
            self._snooze_alarm(10)
            return
        if not self.alarm_edit_mode:
            self._display_manual_mode = (self._display_manual_mode + 1) % 4
            labels = ("OLED: NORMAAL", "OLED: DIM", "OLED: RAND", "OLED: EXTRA DIM")
            self._set_feedback(labels[self._display_manual_mode], ms=1200)
            self._apply_display_brightness(force=True)
            return
        self.alarm_edit_minute = (self.alarm_edit_minute + 1) % 60
        self.alarm_edit_last_change_ms = time.ticks_ms()

    def _down_long_press(self):
        if self.alarm_until is not None:
            self._stop_alarm(show_retro_fact=True)
            return
        if self.alarm_edit_mode:
            return

        if self.wifi_disabled:
            # WiFi was uit: zet aan en reset auto-off timer
            self.wifi_disabled = False
            self.wifi_auto_off_ms = self._next_wifi_auto_off_deadline()
            print("WiFi AAN{}".format(" (blijft aan)" if self.wifi_keep_alive else " (auto-uit over 30 min)"))
            if self._ensure_wifi_connected():
                ip = self.wifi.get_ip() if self.wifi else None
                print("WiFi verbonden:", ip if ip else "geen IP")
        else:
            # WiFi was aan: zet uit en annuleer auto-off timer
            self._disable_wifi()
            self.wifi_disabled = True
            self.wifi_auto_off_ms = None
            print("WiFi UIT")

    def _handle_buttons(self):
        now = time.ticks_ms()
        buttons = [
            ("set",  self._set_short_press,  self._set_long_press,  self.btn_set,  2200),
            ("up",   self._up_short_press,    None,                  self.btn_up,   0),
            ("down", self._down_short_press,  self._down_long_press, self.btn_down, 3000),
        ]
        for name, short_cb, long_cb, pin_obj, long_ms in buttons:
            s = self._button_state[name]

            # Alarm actief: SET stopt, DOWN snooze 10 min, UP doet niets.
            if s["pending"] is not None and self.alarm_until is not None:
                s["pending"] = None
                s["fired_long"] = True
                if name == "set":
                    self._stop_alarm(show_retro_fact=True)
                elif name == "down":
                    self._snooze_alarm(10)
                continue

            # Voer pending actie direct uit (gezet door IRQ)
            if s["pending"] == "short":
                s["pending"] = None
                if short_cb:
                    self._mark_activity()
                    short_cb()
            elif s["pending"] == "long":
                s["pending"] = None
                if long_cb:
                    self._mark_activity()
                    long_cb()

            # Lange druk detectie terwijl knop ingehouden (alleen voor knoppen met long_cb)
            if long_cb and not s["fired_long"] and pin_obj.value() == 0:
                if s["start"] > 0 and time.ticks_diff(now, s["start"]) >= long_ms:
                    s["fired_long"] = True
                    s["pending"] = None  # annuleer eventuele short
                    self._mark_activity()
                    long_cb()

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

        # --- DFPlayer: herhaal bij echte alarmen, speel eenmalig bij preview ---
        if self.dfplayer is not None:
            try:
                # Track 0001.mp3 is reserved for intro, so alarm tones map to +1.
                tone_num = int(self.active_tone)
                track = tone_num + 1
                if track < 1:
                    track = 1
                if track > DFPLAYER_TRACK_COUNT:
                    track = DFPLAYER_TRACK_COUNT
                dfvol = max(0, min(30, int(self.volume * 30 // 100) + self._alarm_boss_level() * 3))
                self.dfplayer.set_volume(dfvol)

                restart_needed = (not self._dfplayer_playing) or (self._dfplayer_track_num != track)

                # Met BUSY-pin kunnen we exact wachten tot een nummer klaar is.
                if not restart_needed and DFPLAYER_BUSY_PIN is not None:
                    try:
                        if not self.dfplayer.is_busy():
                            restart_needed = True
                    except Exception:
                        pass

                # Zonder BUSY-pin: herstart pas na een ruime interval.
                if not restart_needed and DFPLAYER_BUSY_PIN is None:
                    if self._dfplayer_last_start_ms <= 0:
                        restart_needed = True
                    elif time.ticks_diff(now_ms, self._dfplayer_last_start_ms) >= ALARM_REPEAT_MS:
                        restart_needed = True

                if restart_needed:
                    # Preview-modus: stop zodra het nummer klaar is of de fallback-interval bereikt is.
                    if (not self._alarm_repeat_track) and self._dfplayer_playing:
                        self._stop_alarm()
                        return
                    self.dfplayer.play_mp3(track)
                    print("DFPlayer: speel track {} (tone {}), volume {}".format(track, tone_num, dfvol))
                    self._dfplayer_playing = True
                    self._dfplayer_track_num = track
                    self._dfplayer_last_start_ms = now_ms
            except Exception as e:
                print("! DFPlayer play fout:", e)
            return

        # Geen DFPlayer beschikbaar: stil (buzzer uitgeschakeld)
        return

    def _update_led_animation(self, frame):
        """Update WS2812B LED animations during alarm."""
        self._ensure_leds_ready()
        if not self.leds:
            return

        tone = getattr(self, 'active_led_tone', getattr(self, 'active_tone', '1'))
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
        # Zorg dat de client-socket blokkerende mode heeft met timeout
        # zodat recv() niet direct EAGAIN gooit op non-blocking sockets.
        try:
            c.settimeout(3)
        except Exception:
            pass
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 4096:
            try:
                ch = c.recv(512)
            except OSError:
                break
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
                try:
                    ch = c.recv(min(512, cl - len(b)))
                except OSError:
                    break
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
        names = (
            ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
            if self.ui_language == "en"
            else
            ("Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag")
        )
        return names[(int(idx) - 1) % 7]

    def _weekday_short(self, idx):
        names = ("mo", "tu", "we", "th", "fr", "sa", "su") if self.ui_language == "en" else ("ma", "di", "wo", "do", "vr", "za", "zo")
        return names[(int(idx) - 1) % 7]

    def _lang(self, nl_text, en_text):
        return en_text if self.ui_language == "en" else nl_text

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

    def _draw_big_char(self, ch, x, y, scale=3, dim_mode=False, rand_mode=False, extra_dim_mode=False):
        glyph = BIG_TIME_GLYPHS.get(ch)
        if not glyph:
            return 0
        w = len(glyph[0]) if glyph else 0

        def _is_on(r, c):
            return 0 <= r < len(glyph) and 0 <= c < len(glyph[r]) and glyph[r][c] == "1"
        
        if rand_mode:
            # RAND mode: alleen contourlijnen (binnenkant volledig zwart)
            for row_idx, row in enumerate(glyph):
                for col_idx, bit in enumerate(row):
                    if bit != "1":
                        continue
                    px = x + col_idx * scale
                    py = y + row_idx * scale
                    # Teken alleen zijden die aan "uit" grenzen.
                    if not _is_on(row_idx - 1, col_idx):
                        self.display.hline(px, py, scale, 1)
                    if not _is_on(row_idx + 1, col_idx):
                        self.display.hline(px, py + scale - 1, scale, 1)
                    if not _is_on(row_idx, col_idx - 1):
                        self.display.vline(px, py, scale, 1)
                    if not _is_on(row_idx, col_idx + 1):
                        self.display.vline(px + scale - 1, py, scale, 1)
        elif extra_dim_mode:
            # EXTRA DIM: alleen contour, maar met lage display-contrastinstelling.
            for row_idx, row in enumerate(glyph):
                for col_idx, bit in enumerate(row):
                    if bit != "1":
                        continue
                    px = x + col_idx * scale
                    py = y + row_idx * scale
                    if not _is_on(row_idx - 1, col_idx):
                        self.display.hline(px, py, scale, 1)
                    if not _is_on(row_idx + 1, col_idx):
                        self.display.hline(px, py + scale - 1, scale, 1)
                    if not _is_on(row_idx, col_idx - 1):
                        self.display.vline(px, py, scale, 1)
                    if not _is_on(row_idx, col_idx + 1):
                        self.display.vline(px + scale - 1, py, scale, 1)
        else:
            # Normaal: volledig gevuld.
            for row_idx, row in enumerate(glyph):
                for col_idx, bit in enumerate(row):
                    if bit == "1":
                        self.display.fill_rect(x + col_idx * scale, y + row_idx * scale, scale, scale, 1)
        return (w * scale) + scale

    def _draw_big_time(self, hh, mm, y_offset=0, outline_only=False):
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
        
        dim_mode = (self._display_manual_mode == 1)
        rand_mode = (self._display_manual_mode == 2)
        extra_dim_mode = (self._display_manual_mode == 3)
        for ch in text:
            x += self._draw_big_char(ch, x, y, scale, dim_mode=dim_mode, rand_mode=rand_mode, extra_dim_mode=extra_dim_mode)

    def _play_boot_intro(self):
        """8-bit retro boot intro: RETRO slaat neer van boven, GEORGY van onder.
        LED strip doet mee; 999.mp3 speelt op achtergrond.
        WiFi is al verbonden (gedaan in __init__).
        """
        if self.display is None:
            return
        self._in_intro = True
        self._skip_intro = False  # reset voor elke boot

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
            self.display.text(self._lang("laden...", "loading..."), 24, 42, 1)
            self.display.show()

        # DFPlayer initialiseren en track 999 afspelen
        try:
            if self._ensure_dfplayer_ready() and self.dfplayer is not None:
                self.dfplayer.set_volume(20)
                self.dfplayer.play_mp3(1)
                self._intro_audio_playing = True
                print("♫ Intro: 0001.mp3 afspelen")
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
            if self._skip_intro: break
            self.display.fill(0)
            seed = time.ticks_ms()
            for i in range(25):
                self.display.pixel((seed * 13 + i * 41) % 128, (seed * 7 + i * 23) % 64, 1)
            self.display.show()
            leds_flicker(seed + f)
            time.sleep_ms(50)

        # ── FASE 2: "RETRO" schuift neer van boven (8 frames) ───────────────
        for fi, ry in enumerate(RETRO_YS):
            if self._skip_intro: break
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
            if self._skip_intro: break
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
            if self._skip_intro: break
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
            if self._skip_intro: break
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
            if self._skip_intro: break
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

        # ── FASE 7: WiFi zoekt verbinding (animatie, 8-bit stijl) ───────────
        # 8-bit WiFi-icoon: 3 concentrische bogen + stip (16×10 px)
        def draw_wifi_icon(x, y, rings=3, invert=False):
            """Teken WiFi-icoon met 'rings' actieve bogen (0-3)."""
            d = self.display
            col = 0 if invert else 1
            # Stip (antenne-punt)
            d.fill_rect(x + 7, y + 9, 2, 2, col)
            # Boog 1 (klein)
            if rings >= 1:
                d.pixel(x + 5, y + 7, col); d.pixel(x + 6, y + 6, col)
                d.pixel(x + 9, y + 6, col); d.pixel(x + 10, y + 7, col)
            # Boog 2 (middel)
            if rings >= 2:
                d.pixel(x + 3, y + 6, col); d.pixel(x + 4, y + 5, col)
                d.pixel(x + 5, y + 4, col); d.pixel(x + 6, y + 3, col)
                d.pixel(x + 9, y + 3, col); d.pixel(x + 10, y + 4, col)
                d.pixel(x + 11, y + 5, col); d.pixel(x + 12, y + 6, col)
            # Boog 3 (groot)
            if rings >= 3:
                d.pixel(x + 1, y + 6, col); d.pixel(x + 2, y + 4, col)
                d.pixel(x + 3, y + 2, col); d.pixel(x + 4, y + 1, col)
                d.pixel(x + 6, y,     col); d.pixel(x + 9, y,     col)
                d.pixel(x + 11, y + 1, col); d.pixel(x + 12, y + 2, col)
                d.pixel(x + 13, y + 4, col); d.pixel(x + 14, y + 6, col)

        WIFI_X = (128 - 16) // 2   # gecentreerd
        WIFI_Y = 28
        SCAN_TEXT = "SCANNING..."
        SCAN_X = (128 - len(SCAN_TEXT) * 8) // 2

        for fi in range(24):
            if self._skip_intro: break
            self.display.fill(0)
            # Titel bovenaan (klein)
            self.display.text("RETRO GEORGY", 8, 2, 1)
            self.display.hline(0, 11, 128, 1)
            # Pulserende bogen: cyclus 0→1→2→3→2→1→0...
            pulse = fi % 8
            rings = pulse if pulse <= 3 else (6 - pulse)
            draw_wifi_icon(WIFI_X, WIFI_Y, rings)
            # Knipperende scan-tekst
            if fi % 4 < 3:
                self.display.text(SCAN_TEXT, SCAN_X, 52, 1)
            # Voortgangspuntjes onder het icoon
            dots = fi % 4
            for d2 in range(dots + 1):
                self.display.fill_rect(52 + d2 * 8, 42, 4, 4, 1)
            self.display.show()
            leds_sweep_l2r(fi % 8, 0, 180, 255)
            time.sleep_ms(80)

        # ── FASE 8: BAM! IP-adres gevonden ──────────────────────────────────
        ip = self.wifi.get_ip() if (self.wifi_ok and self.wifi) else None

        if self._skip_intro:
            self.startup_ip_until = None
            leds_clear()
            try:
                if self.dfplayer:
                    self.dfplayer.stop()
            except Exception:
                pass
            self._intro_audio_playing = False
            self._in_intro = False
            return

        def _safe_ascii_text(value, max_chars=16):
            try:
                s = str(value if value is not None else "")
            except Exception:
                s = ""
            out = []
            for ch in s:
                code = ord(ch)
                if 32 <= code <= 126:
                    out.append(ch)
                else:
                    out.append("?")
            if not out:
                out = ["-"]
            txt = "".join(out)
            if len(txt) > max_chars:
                return txt[:max_chars]
            return txt

        try:
            # BAM flash: 3 frames wit knippert
            for fi in range(3):
                if self._skip_intro:
                    break
                self.display.fill(fi % 2)
                if fi % 2 == 0:
                    self.display.text("  ** BAM! **  ", 0, 26, 1)
                self.display.show()
                leds_set(255, 255, 0)
                time.sleep_ms(80)

            # Lange WiFi reveal (zelfde gevoel/duur), maar geheugen-zuinig getekend.
            GEVONDEN = self._lang("GEVONDEN!", "FOUND!")
            SSID_LABEL = self._lang("VERBONDEN MET", "CONNECTED TO")
            IP_LABEL = self._lang("IP ADRES", "IP ADDRESS")
            ssid_str = _safe_ascii_text(self.wifi_ssid or "onbekend", max_chars=16)
            ip_str = _safe_ascii_text(ip if ip else "geen WiFi", max_chars=16)

            def _draw_typed(text, shown, x, y):
                count = shown if shown < len(text) else len(text)
                i = 0
                while i < count:
                    self.display.text(text[i], x + i * 8, y, 1)
                    i += 1

            total_frames = len(GEVONDEN) + len(SSID_LABEL) + len(ssid_str) + len(IP_LABEL) + len(ip_str) + 20
            for fi in range(total_frames):
                if self._skip_intro:
                    break

                self.display.fill(0)
                self.display.text("RETRO GEORGY", 8, 2, 1)
                self.display.hline(0, 11, 128, 1)
                draw_wifi_icon(2, 18, 3)

                g_shown = fi + 1
                _draw_typed(GEVONDEN, g_shown, 24, 18)
                if fi < len(GEVONDEN) and (fi % 2 == 0):
                    cursor_x = 24 + (g_shown if g_shown < len(GEVONDEN) else len(GEVONDEN)) * 8
                    self.display.text("_", cursor_x, 18, 1)

                ssid_label_fi = fi - len(GEVONDEN) - 1
                if ssid_label_fi >= 0:
                    _draw_typed(SSID_LABEL, ssid_label_fi + 1, 0, 30)

                ssid_text_fi = fi - len(GEVONDEN) - len(SSID_LABEL) - 2
                if ssid_text_fi >= 0:
                    _draw_typed(ssid_str, ssid_text_fi + 1, 0, 38)
                    if ssid_text_fi < len(ssid_str) and (ssid_text_fi % 2 == 0):
                        cursor_x = (ssid_text_fi + 1 if (ssid_text_fi + 1) < len(ssid_str) else len(ssid_str)) * 8
                        self.display.text("_", cursor_x, 38, 1)

                ip_label_fi = fi - len(GEVONDEN) - len(SSID_LABEL) - len(ssid_str) - 3
                if ip_label_fi >= 0:
                    _draw_typed(IP_LABEL, ip_label_fi + 1, 0, 48)

                ip_text_fi = fi - len(GEVONDEN) - len(SSID_LABEL) - len(ssid_str) - len(IP_LABEL) - 4
                if ip_text_fi >= 0:
                    _draw_typed(ip_str, ip_text_fi + 1, 0, 56)
                    if ip_text_fi < len(ip_str) and (ip_text_fi % 2 == 0):
                        cursor_x = (ip_text_fi + 1 if (ip_text_fi + 1) < len(ip_str) else len(ip_str)) * 8
                        self.display.text("_", cursor_x, 56, 1)

                if fi >= (total_frames - 16):
                    if (fi % 4) < 2:
                        self.display.rect(0, 12, 128, 52, 1)

                self.display.show()
                leds_rainbow(40 + fi * 4)
                if (fi % 10) == 0:
                    gc.collect()
                time.sleep_ms(70)

            # Vasthouden (zelfde duur als eerder, ca. 1.5s)
            for fi in range(18):
                if self._skip_intro:
                    break
                self.display.fill(0)
                self.display.text("RETRO GEORGY", 8, 2, 1)
                self.display.hline(0, 11, 128, 1)
                draw_wifi_icon(2, 18, 3)
                self.display.text(GEVONDEN, 24, 18, 1)
                self.display.text(SSID_LABEL, 0, 30, 1)
                self.display.text(ssid_str, 0, 38, 1)
                self.display.text(IP_LABEL, 0, 48, 1)
                self.display.text(ip_str, 0, 56, 1)
                self.display.rect(0, 12, 128, 52, 1)
                self.display.show()
                leds_rainbow(110 + fi * 3)
                if (fi % 6) == 0:
                    gc.collect()
                time.sleep_ms(80)
        except Exception as _e:
            # Intro mag de hoofdloop nooit blokkeren.
            print("! Intro WiFi reveal fout:", _e)

        # Zet startup_ip_until op None: IP al getoond in intro
        self.startup_ip_until = None

        leds_clear()
        self._intro_audio_playing = False
        self._in_intro = False
        gc.collect()
        print("Boot intro klaar")

    def _draw_startup_ip(self):
        self.display.fill(0)
        self.display.text(self._lang("WiFi verbonden", "WiFi connected"), 8, 8, 1)
        ip = self.wifi.get_ip() if self.wifi_ok else None
        self.display.text(self._lang("IP adres:", "IP address:"), 8, 26, 1)
        self.display.text(ip if ip else self._lang("geen netwerk", "no network"), 8, 40, 1)
        self.display.show()

    def _draw_setup_mode(self):
        self.display.fill(0)
        self.display.text(self._lang("INSTEL MODUS", "SETUP MODE"), 20, 2, 1)
        self.display.hline(0, 11, 128, 1)
        self.display.text(self.setup_ap_ssid[:16], 0, 20, 1)
        self.display.text(self._get_setup_ip()[:16], 0, 30, 1)
        self.display.text(self._lang("OPEN IN BROWSER", "OPEN IN BROWSER"), 0, 42, 1)
        self.display.text(self._lang("SLA WIFI OP", "SAVE WIFI VIA WEB"), 0, 52, 1)
        self.display.show()

    def _draw_wifi_intro_style_icon(self, x, y, rings=3):
        # Zelfde 8-bit stijl als in de boot-intro (16x10).
        d = self.display
        # Stip (antenne-punt)
        d.fill_rect(x + 7, y + 9, 2, 2, 1)
        # Boog 1 (klein)
        if rings >= 1:
            d.pixel(x + 5, y + 7, 1); d.pixel(x + 6, y + 6, 1)
            d.pixel(x + 9, y + 6, 1); d.pixel(x + 10, y + 7, 1)
        # Boog 2 (middel)
        if rings >= 2:
            d.pixel(x + 3, y + 6, 1); d.pixel(x + 4, y + 5, 1)
            d.pixel(x + 5, y + 4, 1); d.pixel(x + 6, y + 3, 1)
            d.pixel(x + 9, y + 3, 1); d.pixel(x + 10, y + 4, 1)
            d.pixel(x + 11, y + 5, 1); d.pixel(x + 12, y + 6, 1)
        # Boog 3 (groot)
        if rings >= 3:
            d.pixel(x + 1, y + 6, 1); d.pixel(x + 2, y + 4, 1)
            d.pixel(x + 3, y + 2, 1); d.pixel(x + 4, y + 1, 1)
            d.pixel(x + 6, y, 1); d.pixel(x + 9, y, 1)
            d.pixel(x + 11, y + 1, 1); d.pixel(x + 12, y + 2, 1)
            d.pixel(x + 13, y + 4, 1); d.pixel(x + 14, y + 6, 1)

    def _draw_wifi_status_icon(self, x, y):
        self._draw_wifi_intro_style_icon(x, y, 3)

    def _draw_wifi_off_icon(self, x, y):
        self._draw_wifi_intro_style_icon(x, y, 3)
        # Streep er doorheen
        self.display.line(x + 1, y + 1, x + 14, y + 10, 1)

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

    def _url_quote(self, value):
        text = str(value or "")
        if quote is not None:
            try:
                return quote(text)
            except Exception:
                pass
        safe = []
        for ch in text:
            code = ord(ch)
            if (48 <= code <= 57) or (65 <= code <= 90) or (97 <= code <= 122) or ch in "-_.~":
                safe.append(ch)
            elif ch == " ":
                safe.append("%20")
            else:
                safe.append("%%%02X" % code)
        return "".join(safe)

    def _resolve_weather_location(self, place_name):
        """Zoek plaatsnaam op via Open-Meteo geocoding API en geef beste match terug."""
        host = "geocoding-api.open-meteo.com"
        encoded = self._url_quote(place_name)
        path = "/v1/search?name={}&count=1&language=nl&format=json".format(encoded)
        s = socket.socket()
        try:
            s.settimeout(8)
            addr = socket.getaddrinfo(host, 80)[0][-1]
            s.connect(addr)
            s.send((
                "GET {} HTTP/1.0\r\n"
                "Host: {}\r\n\r\n"
            ).format(path, host).encode())
            resp = b""
            while True:
                chunk = s.recv(256)
                if not chunk:
                    break
                resp += chunk
        finally:
            try:
                s.close()
            except Exception:
                pass

        idx = resp.find(b"\r\n\r\n")
        if idx < 0:
            raise ValueError("Geen geldig antwoord van geocoding")
        payload = json.loads(resp[idx + 4:].decode())
        results = payload.get("results") or []
        if not results:
            raise ValueError("Plaats niet gevonden")

        best = results[0]
        resolved_name = best.get("name") or str(place_name)
        admin1 = best.get("admin1")
        country = best.get("country")
        parts = [resolved_name]
        if admin1 and admin1 != resolved_name:
            parts.append(admin1)
        if country:
            parts.append(country)

        return {
            "place": ", ".join(parts),
            "latitude": float(best.get("latitude")),
            "longitude": float(best.get("longitude")),
        }

    def _check_weather_fetch(self):
        """Roep dit aan vanuit de main loop. Zet WiFi tijdelijk aan als nodig."""
        if self.setup_mode:
            return
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

    def _set_update_status(self, status, err=""):
        self._update_last_status = str(status or "idle")
        self._update_last_error = str(err or "")
        self._update_last_check_ms = time.ticks_ms()

    def _read_update_manifest(self):
        url = self._normalize_manifest_url(self.update_manifest_url)
        body = self._http_get_bytes(url, max_bytes=64000, timeout_s=12)
        try:
            manifest = json.loads(body.decode("utf-8"))
        except Exception as e:
            raise ValueError("Manifest is geen geldige JSON: {}".format(e))
        if not isinstance(manifest, dict):
            raise ValueError("Manifest moet een object zijn")
        version = str(manifest.get("version", "")).strip()
        if not version:
            raise ValueError("Manifest mist version")
        files = manifest.get("files", [])
        if not isinstance(files, list):
            raise ValueError("Manifest files moet een lijst zijn")
        return manifest

    def _check_updates_once(self):
        manifest = self._read_update_manifest()
        latest = str(manifest.get("version", APP_VERSION)).strip()
        self._update_manifest_cache = manifest
        self._update_latest_version = latest
        self._update_pending = self._is_newer_version(latest, APP_VERSION)
        self._set_update_status("checked", "")
        return {
            "ok": True,
            "current_version": APP_VERSION,
            "latest_version": latest,
            "update_pending": self._update_pending,
            "manifest_url": self.update_manifest_url,
        }

    def _apply_manifest_update(self, manifest):
        latest = str(manifest.get("version", "")).strip()
        if not self._is_newer_version(latest, APP_VERSION):
            self._update_latest_version = latest or APP_VERSION
            self._update_pending = False
            return {"ok": True, "updated": False, "message": "Geen nieuwere versie"}

        files = manifest.get("files", [])
        if not files:
            raise ValueError("Manifest bevat geen bestanden")

        staged = []
        try:
            for item in files:
                if not isinstance(item, dict):
                    raise ValueError("Ongeldige file entry in manifest")
                target = self._safe_update_filename(item.get("path", ""))
                if not target:
                    raise ValueError("Ongeldig doelbestand in manifest")
                url = str(item.get("url", "")).strip()
                if not url:
                    raise ValueError("Bestand URL ontbreekt voor {}".format(target))
                blob = self._http_get_bytes(url, max_bytes=280000, timeout_s=18)
                expected_hash = str(item.get("sha256", "") or "").strip().lower()
                if expected_hash:
                    got_hash = self._sha256_hex(blob)
                    if not got_hash:
                        raise ValueError("sha256 niet beschikbaar voor hash-check")
                    if got_hash != expected_hash:
                        raise ValueError("Hash mismatch voor {}".format(target))

                tmp_name = target + ".new"
                with open(tmp_name, "wb") as f:
                    f.write(blob)
                staged.append((target, tmp_name))

            for target, tmp_name in staged:
                bak_name = target + ".bak"
                try:
                    import uos
                    try:
                        uos.remove(bak_name)
                    except Exception:
                        pass
                    try:
                        uos.rename(target, bak_name)
                    except Exception:
                        pass
                    uos.rename(tmp_name, target)
                except Exception as e:
                    raise ValueError("Wisselen bestand mislukt ({}): {}".format(target, e))

            self._update_latest_version = latest
            self._update_pending = False
            self._set_update_status("updated", "")
            self._schedule_restart(1500)
            return {
                "ok": True,
                "updated": True,
                "latest_version": latest,
                "restart": True,
                "files": [name for name, _tmp in staged],
            }
        except Exception:
            # Probeer losse .new bestanden op te ruimen
            try:
                import uos
                for _target, tmp_name in staged:
                    try:
                        uos.remove(tmp_name)
                    except Exception:
                        pass
            except Exception:
                pass
            raise

    def _run_update_cycle(self, apply_update=False):
        wifi_was_disabled = self.wifi_disabled
        if wifi_was_disabled:
            self.wifi_disabled = False
            self._ensure_wifi_connected()
        if not self.wifi_ok or not self.wifi or not self.wifi.is_connected():
            self._set_update_status("error", "Geen WiFi verbinding")
            if wifi_was_disabled:
                self._disable_wifi()
                self.wifi_disabled = True
            return {"ok": False, "error": "Geen WiFi verbinding"}

        try:
            check = self._check_updates_once()
            if not apply_update:
                return check
            if not check.get("update_pending"):
                return {"ok": True, "updated": False, "message": "Geen update beschikbaar"}
            manifest = self._update_manifest_cache or self._read_update_manifest()
            return self._apply_manifest_update(manifest)
        except Exception as e:
            self._set_update_status("error", str(e))
            return {"ok": False, "error": str(e)}
        finally:
            if wifi_was_disabled:
                self._disable_wifi()
                self.wifi_disabled = True

    def _check_auto_update(self):
        if not self.auto_update_enabled:
            return
        if self.setup_mode or self.alarm_until is not None or self.alarm_edit_mode:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self._update_next_check_ms) < 0:
            return

        self._update_next_check_ms = time.ticks_add(now, self.update_check_interval_hours * 3600 * 1000)
        result = self._run_update_cycle(apply_update=True)
        if result.get("ok") and result.get("updated"):
            print("Auto-update toegepast:", result.get("latest_version", "?"))
        elif result.get("ok"):
            print("Auto-update check: geen update")
        else:
            print("Auto-update fout:", result.get("error", "onbekend"))

    def _get_update_status_payload(self):
        remaining_ms = max(0, time.ticks_diff(self._update_next_check_ms, time.ticks_ms()))
        return {
            "current_version": APP_VERSION,
            "latest_version": self._update_latest_version,
            "update_pending": self._update_pending,
            "auto_update_enabled": self.auto_update_enabled,
            "manifest_url": self.update_manifest_url,
            "check_interval_hours": self.update_check_interval_hours,
            "last_status": self._update_last_status,
            "last_error": self._update_last_error,
            "next_check_in_s": int(remaining_ms // 1000),
        }

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
            self.display.text(temp_str, 96 - len(temp_str) * 8 - 2, 56, 1)

        x, y = 96, 56
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
        if self._display_manual_mode == 3:
            target = 0x08
        elif self._display_manual_mode == 2:
            target = 0x04
        elif self._display_manual_mode == 1:
            target = 0x01
        else:
            target = 0x7F
        if force or self._display_dim_state != target:
            try:
                if hasattr(self.display, "display_on"):
                    self.display.display_on(True)
                if hasattr(self.display, "set_contrast"):
                    self.display.set_contrast(target)
                elif hasattr(self.display, "ssd1306_command"):
                    self.display.ssd1306_command(0xAF)
                    self.display.ssd1306_command(0x81)
                    self.display.ssd1306_command(target)
            except Exception as e:
                print("! Contrast instellen mislukt:", e)
            self._display_dim_state = target

    def _apply_clock_dither(self, t):
        # Dither uitgeschakeld: voorkomt zichtbaar flikkeren/ademen op sommige OLED panelen.
        return

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
                        if self._nightlight_on:
                            for i in range(self.leds.num_leds):
                                self.leds.set_pixel(i, 255, 120, 40)
                            self.leds.show()
                        else:
                            self.leds.clear()
                    except Exception:
                        pass
                gc.collect()
            return

        self._update_easter_egg(t)
        # Nachtlampje bijhouden buiten transitie/alarm
        if self.leds and self._nightlight_on and self.alarm_until is None:
            try:
                for i in range(self.leds.num_leds):
                    self.leds.set_pixel(i, 255, 120, 40)
                self.leds.show()
            except Exception:
                pass
        self.display.fill(0)
        self._draw_big_time(t[3], t[4])
        extra_dim = (self._display_manual_mode == 3)
        if not extra_dim:
            # Alarmregel: normaal het eerstvolgende alarm, maar tijdens snooze een countdown.
            snooze_sec = self._snooze_remaining_seconds()
            if snooze_sec > 0:
                sh = snooze_sec // 3600
                sm = (snooze_sec % 3600) // 60
                ss = snooze_sec % 60
                self.display.text("SNOOZE {:02d}:{:02d}:{:02d}".format(sh, sm, ss), 0, 44, 1)
            else:
                next_alarm = self._next_alarm_info(t)
                if next_alarm:
                    day_str, ah, am = next_alarm
                    if not day_str:
                        day_str = self._weekday_short(t[6])  # vandaag, nog in de toekomst
                    alarm_text = "{} {:02d}:{:02d}".format(day_str, ah, am)
                    self._draw_alarm_icon(0, 44)
                    self.display.text(alarm_text, 10, 44, 1)
                else:
                    self.display.text("--:--", 10, 44, 1)
            # Day + date lines
            self.display.text(self._weekday_short(t[6]), 0, 56, 1)
            self.display.text("{:02d}-{:02d}".format(t[2], t[1]), 24, 56, 1)
            self._draw_weather_overlay(t)
            if self.wifi_disabled:
                self._draw_wifi_off_icon(WIDTH - 16, HEIGHT - 11)
            elif self.wifi_ok and self.wifi and self.wifi.is_connected():
                self._draw_wifi_status_icon(WIDTH - 16, HEIGHT - 11)

        # Korte statusmelding na SET-kort in standaard scherm.
        now_ms = time.ticks_ms()
        if self._set_feedback_until and time.ticks_diff(self._set_feedback_until, now_ms) > 0:
            # Volledig scherm wissen en feedback tonen
            self.display.fill(0)
            lines = self._set_feedback_lines if self._set_feedback_lines else [self._set_feedback_text]
            y_positions = [2, 14, 26, 36, 48, 56]
            delay_ms = 1200
            step_ms = 900
            max_start = max(0, len(lines) - len(y_positions))
            elapsed = time.ticks_diff(now_ms, self._set_feedback_start_ms)
            start_idx = 0
            if elapsed >= delay_ms and max_start > 0:
                start_idx = min(max_start, (elapsed - delay_ms) // step_ms)

            line_idx = start_idx
            y_idx = 0
            while line_idx < len(lines) and y_idx < len(y_positions):
                ln = lines[line_idx]
                if ln == "---":
                    self.display.hline(4, y_positions[y_idx] + 3, 120, 1)
                elif ln:
                    self._draw_feedback_text(ln, y_positions[y_idx], now_ms)
                y_idx += 1
                line_idx += 1
        elif self._set_feedback_until:
            self._set_feedback_until = 0
            self._set_feedback_text = ""
            self._set_feedback_lines = []

        self._draw_easter_overlay()
        self._apply_clock_dither(t)
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
        if self._display_manual_mode != 3:
            next_alarm = self._next_alarm_info(t)
            if next_alarm:
                day_str, ah, am = next_alarm
                if not day_str:
                    day_str = self._weekday_short(t[6])
                self._draw_alarm_icon(0, 44)
                self.display.text("{} {:02d}:{:02d}".format(day_str, ah, am), 10, 44, 1)
            else:
                self.display.text("--:--", 10, 44, 1)
            self.display.text(self._weekday_short(t[6]), 0, 56, 1)
            self.display.text("{:02d}-{:02d}".format(t[2], t[1]), 24, 56, 1)
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
        """Green Hill Zone: rolling hills, detailed Sonic sprite, rings, speed lines."""
        d = self.display
        d.fill(0)

        # Sky: distant checkered pattern (GHZ style)
        for sy in range(0, 20, 4):
            for sx in range(0, 128, 8):
                if (sx // 8 + sy // 4) % 2 == 0:
                    d.fill_rect(sx, sy, 4, 2, 1)

        # Far rolling hill (slow)
        ho1 = (frame // 4) % 64
        for hx in range(0, 128):
            hpeak = 20 - 8 * abs(((hx + ho1) % 64) - 32) // 32
            d.vline(hx, hpeak, 22 - hpeak, 1)

        # Near hill (faster, higher)
        ho2 = (frame // 2) % 48
        for hx in range(0, 128):
            hpeak = 26 - 6 * abs(((hx + ho2) % 48) - 24) // 24
            d.vline(hx, hpeak, 30 - hpeak, 1)

        # Ground
        d.fill_rect(0, 30, 128, 6, 0)
        d.hline(0, 30, 128, 1)
        d.hline(0, 36, 128, 1)
        # Checkerboard tiles scrolling
        tile_off = (frame * 3) % 16
        for tx in range(0, 128, 16):
            x = tx - tile_off
            d.fill_rect(x, 31, 8, 5, 1)
        d.fill_rect(0, 37, 128, 27, 1)

        # Speed lines behind Sonic
        sx0 = 28
        for i, (ly, llen) in enumerate(((33, 14), (35, 18), (37, 12))):
            d.hline(sx0 - llen - i * 3, ly, llen, 0)

        # Sonic sprite (12x14) at fixed position
        sx, sy = 30, 17
        leg = (frame // 2) % 4
        # Spines (3 spikes going back-left)
        d.line(sx + 4, sy, sx, sy - 3, 1)
        d.line(sx + 6, sy + 1, sx + 2, sy - 2, 1)
        d.line(sx + 8, sy + 2, sx + 5, sy - 1, 1)
        # Head
        d.fill_rect(sx + 4, sy, 8, 7, 1)
        d.pixel(sx + 10, sy + 2, 0)  # eye
        # Torso
        d.fill_rect(sx + 3, sy + 7, 7, 5, 1)
        # Arm
        if frame % 4 < 2:
            d.fill_rect(sx + 10, sy + 8, 4, 2, 1)
        else:
            d.fill_rect(sx + 10, sy + 9, 4, 2, 1)
        # Legs
        if leg < 2:
            d.fill_rect(sx + 3, sy + 12, 3, 4, 1)
            d.fill_rect(sx + 7, sy + 10, 3, 4, 1)
        else:
            d.fill_rect(sx + 3, sy + 10, 3, 4, 1)
            d.fill_rect(sx + 7, sy + 12, 3, 4, 1)
        # Red shoe hint
        d.hline(sx + 2, sy + 14, 5, 1)
        d.hline(sx + 6, sy + 13, 5, 1)

        # Ring (right side, bobbing)
        ry = 20 + ((frame // 5) % 3)
        d.rect(90, ry, 10, 10, 1)
        d.rect(92, ry + 2, 6, 6, 0)
        # Shine on ring
        if (frame // 4) % 2 == 0:
            d.pixel(91, ry + 1, 1)
            d.pixel(92, ry, 1)

        # HUD
        d.text("SONIC", 68, 0, 1)
        score = (frame * 77) % 9999
        d.text(str(score), 68, 10, 1)
        if (frame // 8) % 2 == 0:
            d.fill_rect(0, 56, 128, 8, 1)
            d.text("ALARM!", 40, 56, 0)
        else:
            d.text("ALARM!", 40, 56, 1)
        d.show()

    def _draw_metroid_animation(self, frame, intensity):
        """Samus in Chozo ruins: detailed armor silhouette, charging beam, lava glow."""
        d = self.display
        d.fill(0)

        # Lava at bottom (pulsing)
        lava_y = 52 + (frame // 6) % 3
        d.fill_rect(0, lava_y, 128, 64 - lava_y, 1)
        for bx in range(0, 128, 12):
            boff = (bx + frame * 2) % 24
            by = lava_y - 2 - (boff % 5)
            d.fill_rect(bx, by, 6, lava_y - by, 0)

        # Pillars (Chozo ruins)
        for px in (2, 108):
            d.fill_rect(px, 20, 14, lava_y - 20, 1)
            d.fill_rect(px - 2, 18, 18, 4, 1)  # capital
            d.fill_rect(px - 2, lava_y - 4, 18, 4, 1)  # base
            for gy in range(24, lava_y - 4, 8):
                d.hline(px + 1, gy, 12, 0)

        # Samus armor silhouette (centered)
        sx, sy = 52, 4
        # Helmet (round top)
        d.fill_rect(sx + 4, sy, 16, 4, 1)
        d.fill_rect(sx + 2, sy + 2, 20, 10, 1)
        d.fill_rect(sx + 6, sy + 5, 12, 5, 0)  # visor cutout
        d.fill_rect(sx + 8, sy + 6, 8, 3, 1)   # visor glow
        # Shoulders
        d.fill_rect(sx, sy + 10, 8, 8, 1)
        d.fill_rect(sx + 16, sy + 10, 8, 8, 1)
        d.fill_rect(sx, sy + 10, 8, 3, 1)  # shoulder cap
        d.fill_rect(sx + 16, sy + 10, 8, 3, 1)
        # Torso
        d.fill_rect(sx + 6, sy + 12, 12, 10, 1)
        d.hline(sx + 8, sy + 16, 8, 0)  # chest detail
        # Arm cannon (right)
        cannon_len = 12 + ((frame // 3) % 4)
        d.fill_rect(sx + 24, sy + 13, cannon_len, 5, 1)
        d.fill_rect(sx + 22, sy + 12, 4, 7, 1)  # cannon joint
        # Charge ball at cannon tip
        pulse = (frame // 2) % 6
        tip_x = sx + 24 + cannon_len
        if pulse < 3:
            d.fill_rect(tip_x, sy + 13, 4, 5, 1)
        else:
            d.fill_rect(tip_x - 1, sy + 12, 6, 7, 1)
            if pulse == 5:
                d.pixel(tip_x + 2, sy + 15, 0)  # core
        # Left arm
        d.fill_rect(sx - 4, sy + 13, 12, 4, 1)
        # Legs
        d.fill_rect(sx + 5, sy + 22, 5, 10, 1)
        d.fill_rect(sx + 14, sy + 22, 5, 10, 1)
        d.fill_rect(sx + 3, sy + 30, 7, 4, 1)  # boot left
        d.fill_rect(sx + 14, sy + 30, 7, 4, 1)  # boot right

        # Energy bar (top)
        charge = max(0, min(100, int(intensity)))
        d.text("E", 0, 0, 1)
        d.rect(10, 1, 52, 6, 1)
        d.fill_rect(11, 2, charge * 50 // 100, 4, 1)

        if (frame // 8) % 2 == 0:
            d.fill_rect(0, 56, 128, 8, 1)
            d.text("ALARM!", 40, 56, 0)
        else:
            d.text("ALARM!", 40, 56, 1)
        d.show()

    def _draw_pokemon_animation(self, frame, intensity):
        """Gen-1 battle scene: proper HUD boxes, Pikachu silhouette, trainer, pokeball."""
        d = self.display
        d.fill(0)

        # Battle field divider
        d.hline(0, 28, 128, 1)
        d.hline(0, 29, 128, 1)

        # Pikachu-like silhouette (enemy, top-right)
        px, py = 76, 2
        # Ears (pointy)
        d.line(px + 4, py, px + 2, py - 4, 1)
        d.line(px + 2, py - 4, px + 1, py - 4, 1)
        d.line(px + 9, py, px + 11, py - 4, 1)
        d.line(px + 11, py - 4, px + 12, py - 4, 1)
        # Head
        d.fill_rect(px + 1, py, 12, 10, 1)
        d.pixel(px + 3, py + 3, 0)  # left eye
        d.pixel(px + 9, py + 3, 0)  # right eye
        d.pixel(px + 5, py + 6, 0)  # nose
        d.pixel(px + 7, py + 6, 0)
        # Cheeks (round)
        d.fill_rect(px - 1, py + 4, 3, 3, 1)
        d.fill_rect(px + 12, py + 4, 3, 3, 1)
        # Body
        d.fill_rect(px + 2, py + 10, 10, 7, 1)
        # Tail (lightning bolt hint)
        d.line(px + 12, py + 12, px + 16, py + 8, 1)
        d.line(px + 16, py + 8, px + 20, py + 14, 1)
        # Legs
        d.fill_rect(px + 3, py + 17, 3, 4, 1)
        d.fill_rect(px + 8, py + 17, 3, 4, 1)

        # Trainer silhouette (player, bottom-left)
        tx, ty = 8, 16
        d.fill_rect(tx + 3, ty, 6, 5, 1)   # head
        d.fill_rect(tx + 2, ty + 5, 8, 8, 1)  # body
        d.fill_rect(tx, ty + 6, 3, 5, 1)   # arm (throwing)
        d.fill_rect(tx + 9, ty + 7, 3, 4, 1)
        d.fill_rect(tx + 3, ty + 13, 3, 5, 1)  # legs
        d.fill_rect(tx + 6, ty + 13, 3, 5, 1)

        # Pokeball arc
        progress = (frame * 2) % 80
        bx = 22 + progress
        arc_h = 22 - ((progress - 40) * (progress - 40)) // 73
        by2 = max(6, arc_h)
        d.rect(bx, by2, 6, 6, 1)
        d.hline(bx, by2 + 3, 6, 1)  # equator line
        d.pixel(bx + 2, by2 + 2, 0)
        d.pixel(bx + 3, by2 + 2, 0)  # button

        # Enemy HP box (top-left)
        d.rect(0, 0, 62, 12, 1)
        d.text("PIKACHU", 2, 1, 1)
        d.rect(0, 9, 62, 4, 1)
        hp = max(0, min(100, int(intensity)))
        d.fill_rect(1, 10, hp * 60 // 100, 2, 1)

        # Player status box bottom
        d.rect(66, 30, 62, 12, 1)
        d.text("TRAINER", 68, 31, 1)
        d.rect(66, 39, 62, 4, 1)
        d.fill_rect(67, 40, 60, 2, 1)

        # Battle text box
        d.rect(0, 45, 128, 19, 1)
        blink = (frame // 6) % 2
        if blink == 0:
            d.text("WAKE  UP!", 4, 48, 1)
        else:
            d.text("WAKE  UP!", 4, 56, 1)
        d.pixel(120, 56, 1)
        d.pixel(122, 54, 1)
        d.pixel(124, 56, 1)
        d.show()

    def _draw_tetris_animation(self, frame, intensity):
        """Tetris: detailed board with grid, filled stack, active piece, next+score panel."""
        d = self.display
        d.fill(0)

        bx, by, cell = 4, 2, 5
        cols, rows = 9, 12

        # Board outline + grid
        d.rect(bx - 1, by - 1, cols * cell + 2, rows * cell + 2, 1)
        for gx in range(1, cols):
            d.vline(bx + gx * cell, by, rows * cell, 1)
        for gy in range(1, rows):
            d.hline(bx, by + gy * cell, cols * cell, 1)

        # Static stack (deterministic per frame-epoch)
        epoch = frame // 60
        stack_heights = [(4 + ((i * 5 + epoch * 3) % 5)) for i in range(cols)]
        for col in range(cols):
            sh = stack_heights[col]
            for row in range(sh):
                ry = rows - 1 - row
                cx2 = bx + col * cell + 1
                cy2 = by + ry * cell + 1
                d.fill_rect(cx2, cy2, cell - 2, cell - 2, 1)
                # Checker pattern on filled cells
                if (col + row) % 2 == 0:
                    d.pixel(cx2 + 1, cy2 + 1, 0)

        # Line clear flash
        full_row = rows - 1
        all_full = all(stack_heights[c] >= 1 for c in range(cols))
        if all_full and (frame // 3) % 2 == 0:
            d.fill_rect(bx, by + full_row * cell, cols * cell, cell, 0)

        # Falling piece
        shape = (frame // 24) % 5
        max_drop = (rows - max(stack_heights)) * cell
        drop = (frame * 2) % max(cell, max_drop)
        px2 = bx + (1 + (frame // 40) % (cols - 3)) * cell
        py2 = by + drop
        if shape == 0:   # I (horizontal)
            for i in range(4):
                d.rect(px2 + i * cell, py2, cell - 1, cell - 1, 1)
        elif shape == 1: # O
            d.rect(px2, py2, cell - 1, cell - 1, 1)
            d.rect(px2 + cell, py2, cell - 1, cell - 1, 1)
            d.rect(px2, py2 + cell, cell - 1, cell - 1, 1)
            d.rect(px2 + cell, py2 + cell, cell - 1, cell - 1, 1)
        elif shape == 2: # T
            for i in range(3):
                d.rect(px2 + i * cell, py2, cell - 1, cell - 1, 1)
            d.rect(px2 + cell, py2 + cell, cell - 1, cell - 1, 1)
        elif shape == 3: # S
            d.rect(px2 + cell, py2, cell - 1, cell - 1, 1)
            d.rect(px2 + 2 * cell, py2, cell - 1, cell - 1, 1)
            d.rect(px2, py2 + cell, cell - 1, cell - 1, 1)
            d.rect(px2 + cell, py2 + cell, cell - 1, cell - 1, 1)
        else:            # L
            for i in range(3):
                d.rect(px2, py2 + i * cell, cell - 1, cell - 1, 1)
            d.rect(px2 + cell, py2 + 2 * cell, cell - 1, cell - 1, 1)

        # Side panel
        px3 = bx + cols * cell + 6
        d.text("TETRIS", px3, 0, 1)
        d.hline(px3, 9, 40, 1)
        d.text("NEXT", px3, 12, 1)
        # Next piece preview
        d.rect(px3, 21, 20, 14, 1)
        next_s = (shape + 1) % 5
        if next_s < 2:
            d.fill_rect(px3 + 2, px3 - 48, 16, 5, 1)
        else:
            d.fill_rect(px3 + 2, 24, 6, 5, 1)
            d.fill_rect(px3 + 8, 24, 6, 5, 1)
        d.text("SCORE", px3, 38, 1)
        score = (frame * 13 + intensity * 7) % 9999
        d.text(str(score), px3, 48, 1)

        if (frame // 8) % 2 == 0:
            d.fill_rect(0, 56, 128, 8, 1)
            d.text("ALARM!", 40, 56, 0)
        else:
            d.text("ALARM!", 40, 56, 1)
        d.show()

    def _draw_moonstone_animation(self, frame, intensity):
        """Moonstone: detailed knight/dragon battle with sword swings and fire breath."""
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
        """Space Invaders: alien formation, shields, player cannon, bomb/laser battle."""
        d = self.display
        d.fill(0)

        # Alien sprites (3 rows × 8 cols), each 10px wide 7px tall
        def draw_alien(ax, ay, t):
            # Row-dependent shape
            if t == 0:  # top row: crab
                d.pixel(ax + 1, ay, 1); d.pixel(ax + 8, ay, 1)
                d.fill_rect(ax + 2, ay + 1, 6, 3, 1)
                d.pixel(ax, ay + 2, 1); d.pixel(ax + 9, ay + 2, 1)
                d.fill_rect(ax + 1, ay + 4, 8, 2, 1)
                d.pixel(ax + 2, ay + 6, 1); d.pixel(ax + 7, ay + 6, 1)
            elif t == 1:  # middle row: squid
                d.fill_rect(ax + 3, ay, 4, 2, 1)
                d.fill_rect(ax + 1, ay + 2, 8, 3, 1)
                d.pixel(ax, ay + 2, 1); d.pixel(ax + 9, ay + 2, 1)
                d.pixel(ax + 1, ay + 5, 1); d.pixel(ax + 4, ay + 5, 1)
                d.pixel(ax + 5, ay + 5, 1); d.pixel(ax + 8, ay + 5, 1)
            else:  # bottom row: jellyfish
                d.fill_rect(ax + 1, ay, 8, 5, 1)
                d.pixel(ax, ay + 1, 1); d.pixel(ax + 9, ay + 1, 1)
                d.fill_rect(ax, ay + 5, 3, 2, 1)
                d.fill_rect(ax + 7, ay + 5, 3, 2, 1)

        march = (frame // 8) % 2  # aliens march left/right
        formation_x = 6 + march * 4
        formation_y = 2 + ((frame // 16) % 3)  # slowly descend
        for row in range(3):
            for col in range(8):
                ax = formation_x + col * 14
                ay = formation_y + row * 9
                if ax < 120:  # clip
                    draw_alien(ax, ay, row)

        # Bombs falling from random aliens
        for i in range(3):
            bomb_col = (frame // 5 + i * 3) % 8
            bomb_x = formation_x + bomb_col * 14 + 4
            bomb_y = formation_y + 28 + ((frame * 2 + i * 13) % 20)
            if bomb_y < 44:
                d.vline(bomb_x, bomb_y, 4, 1)

        # Shields (3 bunkers)
        for si in range(3):
            sx = 10 + si * 38
            damage = (frame // 20 + si) % 4
            d.fill_rect(sx, 44, 20, 6, 1)
            # Notch bottom center (cannon port)
            d.fill_rect(sx + 7, 48, 6, 2, 0)
            # Damage holes
            for di in range(damage):
                d.fill_rect(sx + 2 + di * 4, 44 + (di % 3), 3, 3, 0)

        # Player cannon
        cx = 60 + ((frame // 3) % 4 - 2) * 2
        d.fill_rect(cx - 6, 52, 12, 4, 1)    # base
        d.fill_rect(cx - 1, 50, 3, 3, 1)     # barrel
        d.fill_rect(cx - 3, 51, 7, 1, 1)     # turret top

        # Player laser
        if (frame // 4) % 6 == 0:
            d.vline(cx, 36, 14, 1)
            d.pixel(cx - 1, 36, 1)
            d.pixel(cx + 1, 36, 1)

        # Score + lives
        score = (frame * 10) % 9999
        d.text(str(score), 0, 57, 1)
        for li in range(3):
            d.fill_rect(100 + li * 9, 57, 7, 6, 1)
            d.fill_rect(101 + li * 9, 57, 2, 2, 0)
            d.fill_rect(104 + li * 9, 57, 2, 2, 0)

        if (frame // 8) % 2 == 0:
            d.fill_rect(0, 56, 60, 8, 0)  # clear score area for alarm
            d.fill_rect(0, 56, 128, 8, 1)
            d.text("ALARM!", 40, 56, 0)
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

    def _open_gif_by_name(self, name):
        if not name:
            return False
        if self._gif_runtime_failed:
            return False
        path_candidates = (
            "/{}/{}.bin".format(ANIMATIONS_DIR, name),
            "{}/{}.bin".format(ANIMATIONS_DIR, name),
            "/{}.bin".format(name),
        )
        f = None
        path = ""
        for candidate in path_candidates:
            try:
                f = open(candidate, "rb")
                path = candidate
                break
            except OSError:
                pass
        if f is None:
            return False
        try:
            magic = f.read(2)
            if magic != bytes([0x47, 0xAF]):
                f.close()
                self._gif_runtime_failed = True
                return False
            b = f.read(4)
            if len(b) != 4:
                f.close()
                self._gif_runtime_failed = True
                return False
            n = (b[0] << 8) | b[1]
            w = b[2]
            h = b[3]
            if w != 128 or h != 64:
                print("GIF alarm: verwacht 128x64, got {}x{}".format(w, h))
                f.close()
                self._gif_runtime_failed = True
                return False
            delays = []
            for _ in range(n):
                d = f.read(2)
                if len(d) != 2:
                    f.close()
                    self._gif_runtime_failed = True
                    return False
                hi = d[0]
                lo = d[1]
                delays.append((hi << 8) | lo)
            self._gif_file = f
            self._gif_n_frames = n
            self._gif_frame_size = w * h // 8
            self._gif_delays = delays
            self._gif_cur_frame = 0
            self._gif_data_offset = f.tell()
            self._gif_next_ms = 0
            self._gif_runtime_failed = False
            print("GIF alarm: {} frames geladen uit {}".format(n, path))
            return True
        except Exception as e:
            print("GIF alarm open fout:", e)
            try:
                f.close()
            except Exception:
                pass
            self._disable_gif_for_alarm("open fout")
            return False

    def _draw_gif_alarm_frame(self):
        now = time.ticks_ms()
        if time.ticks_diff(now, self._gif_next_ms) < 0:
            return True
        try:
            self._gif_file.seek(self._gif_data_offset + self._gif_cur_frame * self._gif_frame_size)
            n = self._gif_file.readinto(self._gif_frame_buf)
            if n != self._gif_frame_size:
                raise OSError("onvolledige GIF frame data")
            self.display.fill(0)
            self.display.blit(self._gif_fb, 0, 0)
            self.display.show()
            delay = self._gif_delays[self._gif_cur_frame]
            if delay < 20:
                delay = 100
            elif delay > 500:
                delay = 500
            self._gif_next_ms = time.ticks_add(now, delay)
            self._gif_cur_frame = (self._gif_cur_frame + 1) % self._gif_n_frames
            return True
        except Exception as e:
            print("GIF alarm frame fout:", e)
            self._disable_gif_for_alarm("frame decode fout")
            return False

    def _draw_alarm_controls_overlay(self, frame):
        # Toon STOP/SNOOZE hint: 2s aan, 5s uit (7s periode).
        t_sec = time.ticks_ms() // 1000
        if t_sec % 7 < 2:
            self.display.fill_rect(0, 0, 128, 10, 0)
            self.display.text("^STOP", 0, 1, 1)
            self.display.text("^SNOOZE", 72, 1, 1)

    def _draw_alarm_animation(self, frame):
        elapsed = self._alarm_elapsed_ms()
        tone = getattr(self, 'active_tone', '1')
        intensity = self._alarm_intensity()
        # GIF-animatie als actieve gif ingesteld is
        gif_name = getattr(self, 'active_gif', '')
        if self._gif_file is None and gif_name and not self._gif_runtime_failed:
            self._open_gif_by_name(gif_name)
        if self._gif_file is not None:
            if not self._draw_gif_alarm_frame():
                # GIF-pad viel uit; val direct terug op standaard animatie in deze frame.
                pass
            else:
                boss = self._alarm_boss_level()
                if boss > 0:
                    if boss >= 2 and (frame % 2 == 0):
                        self.display.rect(0, 0, 128, 64, 1)
                self._draw_alarm_controls_overlay(frame)
                self.display.show()
                return
        # Skip intro als _skip_intro is ingesteld (bijv. test-alarm)
        if not self._skip_intro and elapsed < ALARM_INTRO_MS:
            self._draw_alarm_intro(frame, tone)
            self._draw_alarm_controls_overlay(frame)
            self.display.show()
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
        self._draw_alarm_controls_overlay(frame)
        self.display.show()

    def _draw_alarm_edit(self):
        self.display.fill(0)
        # Header met acties bovenaan
        self.display.text("^OPSL", 0, 0, 1)
        self.display.text("^UUR", (128 - 4 * 8) // 2, 0, 1)
        self.display.text("^MIN", 128 - 4 * 8, 0, 1)
        self.display.hline(0, 9, 128, 1)
        # Knipperen stopt 5s na laatste wijziging van uur/min, daarna weer aan.
        now = time.ticks_ms()
        recent_change = self.alarm_edit_last_change_ms and time.ticks_diff(now, self.alarm_edit_last_change_ms) < 5000
        if recent_change or ((now // 500) % 2 == 0):
            self._draw_big_time(self.alarm_edit_hour, self.alarm_edit_minute, y_offset=12)
        # Na korte SET druk 3 seconden hint tonen.
        if self.alarm_edit_hold_hint_until and time.ticks_diff(self.alarm_edit_hold_hint_until, now) > 0:
            self.display.text("3 sec indrukken", 2, 56, 1)
        elif self.alarm_edit_hold_hint_until:
            self.alarm_edit_hold_hint_until = 0
        self.display.show()

    def serve_once(self, c):
        try:
            self._serve_request(c)
        except Exception as e:
            print("! serve_once fout:", e)
            try:
                c.send(("HTTP/1.1 500 Internal Server Error\r\nContent-Type: application/json\r\n\r\n{\"ok\":false,\"error\":\"" + str(e) + "\"}").encode())
            except Exception:
                pass

    def _read_request_headers(self, c):
        """Lees alleen de HTTP-headers (tot \\r\\n\\r\\n). Geef (headers_str, body_start_bytes)."""
        try:
            c.settimeout(3)
        except Exception:
            pass
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 4096:
            try:
                ch = c.recv(256)
            except OSError:
                break
            if not ch:
                break
            data += ch
        if b"\r\n\r\n" in data:
            h, b = data.split(b"\r\n\r\n", 1)
            return h.decode("utf-8", "ignore"), b
        return data.decode("utf-8", "ignore"), b""

    def _validate_uploaded_bin_file(self, path):
        """Valideer geuploade 1-bit animatie .bin op header, frames, delays en payload-grootte."""
        try:
            with open(path, "rb") as f:
                magic = f.read(2)
                if magic != bytes([0x47, 0xAF]):
                    return False, "Ongeldige BIN header"

                b = f.read(4)
                if len(b) != 4:
                    return False, "BIN header onvolledig"

                n = (b[0] << 8) | b[1]
                w = b[2]
                h = b[3]

                if w != 128 or h != 64:
                    return False, "Animatie moet 128x64 zijn"
                if n < 1 or n > 1200:
                    return False, "Ongeldig aantal frames"

                for _ in range(n):
                    d = f.read(2)
                    if len(d) != 2:
                        return False, "Delay-tabel onvolledig"
                    delay = (d[0] << 8) | d[1]
                    if delay < 20 or delay > 5000:
                        return False, "Frame delay buiten bereik (20..5000 ms)"

                frame_size = (w * h) // 8
                expected = n * frame_size
                data = f.read(expected)
                if len(data) != expected:
                    return False, "Frame data onvolledig"

                if f.read(1):
                    return False, "Onverwachte extra bytes in bestand"

        except Exception as e:
            return False, "Validatie fout: {}".format(e)

        return True, "ok"

    def _handle_upload_bin(self, c, headers_raw, body_buf, path):
        """Stream binaire .bin upload naar animations/<naam>.bin"""
        import uos as _uos
        # Bestandsnaam uit query string ?name=
        name = ""
        if "?" in path:
            for kv in path.split("?", 1)[1].split("&"):
                if kv.startswith("name="):
                    name = kv[5:]
                    break
        # Sanitize: alleen alfanumeriek + - _
        safe = "".join(ch for ch in name if ('a' <= ch <= 'z') or ('A' <= ch <= 'Z') or ('0' <= ch <= '9') or ch in ('-', '_'))[:32]
        # Strip .bin suffix als al aanwezig
        if safe.lower().endswith("bin"):
            safe = safe[:-3].rstrip(".")
        if not safe:
            c.send(self._json({"ok": False, "error": "Ongeldige bestandsnaam"}))
            return
        # Content-Length ophalen
        cl = 0
        for line in headers_raw.split("\r\n"):
            if line.lower().startswith("content-length:"):
                try:
                    cl = int(line.split(":", 1)[1].strip())
                except Exception:
                    pass
        if cl == 0:
            c.send(self._json({"ok": False, "error": "Geen Content-Length header"}))
            return
        if cl > 512 * 1024:
            c.send(self._json({"ok": False, "error": "Bestand te groot (max 512KB)"}))
            return
        # Vrije ruimte controleren
        try:
            st = self._get_storage_info()
            avail = st.get("free_bytes", 0) - 8192
            if cl > avail:
                c.send(self._json({"ok": False, "error": "Onvoldoende opslagruimte"}))
                return
        except Exception:
            pass
        anim_dir = "/{}".format(ANIMATIONS_DIR)
        try:
            _uos.mkdir(anim_dir)
        except Exception:
            pass
        dest = "{}/{}.bin".format(anim_dir, safe)
        written = 0
        try:
            with open(dest, "wb") as f:
                if body_buf:
                    f.write(body_buf)
                    written += len(body_buf)
                while written < cl:
                    try:
                        chunk = c.recv(min(512, cl - written))
                    except OSError:
                        break
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
        except Exception as _e:
            try:
                _uos.remove(dest)
            except Exception:
                pass
            c.send(self._json({"ok": False, "error": str(_e)}))
            return
        if written < cl:
            try:
                _uos.remove(dest)
            except Exception:
                pass
            c.send(self._json({"ok": False, "error": "Upload onvolledig ({}/{} bytes)".format(written, cl)}))
            return

        ok, msg = self._validate_uploaded_bin_file(dest)
        if not ok:
            try:
                _uos.remove(dest)
            except Exception:
                pass
            c.send(self._json({"ok": False, "error": "BIN preflight afgekeurd: {}".format(msg)}))
            return

        print("GIF upload opgeslagen:", dest, written, "bytes")
        c.send(self._json({"ok": True, "name": safe + ".bin", "bytes": written}))

    def _handle_upload_file(self, c, headers_raw, body_buf, path):
        """Generieke bestandsupload: schrijft elk bestand naar de root van het filesystem."""
        import uos as _uos
        # Bestandsnaam uit query string ?filename=
        filename = ""
        if "?" in path:
            for kv in path.split("?", 1)[1].split("&"):
                if kv.startswith("filename="):
                    filename = kv[9:]
                    break
        # URL-decode %20 etc. (eenvoudig)
        filename = filename.replace("%20", " ").replace("%2F", "/").replace("%5F", "_")
        # Toegestane extensies
        ALLOWED = (".py", ".html", ".json", ".bin", ".mpy", ".txt", ".css", ".js")
        ok_ext = any(filename.lower().endswith(e) for e in ALLOWED)
        if not filename or not ok_ext or "/" in filename or ".." in filename:
            c.send(self._json({"ok": False, "error": "Ongeldige bestandsnaam of extensie"}))
            return
        # Content-Length
        cl = 0
        for line in headers_raw.split("\r\n"):
            if line.lower().startswith("content-length:"):
                try:
                    cl = int(line.split(":", 1)[1].strip())
                except Exception:
                    pass
        if cl == 0:
            c.send(self._json({"ok": False, "error": "Geen Content-Length header"}))
            return
        if cl > 600 * 1024:
            c.send(self._json({"ok": False, "error": "Bestand te groot (max 600KB)"}))
            return
        dest = "/" + filename
        written = 0
        try:
            with open(dest, "wb") as f:
                if body_buf:
                    f.write(body_buf)
                    written += len(body_buf)
                while written < cl:
                    try:
                        chunk = c.recv(min(512, cl - written))
                    except OSError:
                        break
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
        except Exception as _e:
            try:
                _uos.remove(dest)
            except Exception:
                pass
            c.send(self._json({"ok": False, "error": str(_e)}))
            return
        if written < cl:
            try:
                _uos.remove(dest)
            except Exception:
                pass
            c.send(self._json({"ok": False, "error": "Upload onvolledig ({}/{} bytes)".format(written, cl)}))
            return
        print("Bestand upload opgeslagen:", dest, written, "bytes")
        c.send(self._json({"ok": True, "filename": filename, "bytes": written}))

    def _serve_request(self, c):
        # Lees eerst alleen de headers, zodat binaire uploads direct gestreamed kunnen worden
        headers_raw, body_start = self._read_request_headers(c)
        first_line = headers_raw.split("\r\n", 1)[0] if headers_raw else ""
        parts_l = first_line.split(" ")
        method = parts_l[0] if len(parts_l) > 0 else ""
        path = parts_l[1] if len(parts_l) > 1 else ""
        path_no_query = path.split("?", 1)[0]
        if method:
            # Elke webactie telt als user activity, zodat idle-screensaver niet blijft overtekenen.
            self._mark_activity()
        # Upload endpoints: stream data naar bestand (omzeilt body-buffer limiet)
        if method == "POST" and path_no_query == "/api/upload-bin":
            self._handle_upload_bin(c, headers_raw, body_start, path)
            return
        if method == "POST" and path_no_query == "/api/upload-file":
            self._handle_upload_file(c, headers_raw, body_start, path)
            return
        # Alle andere endpoints: lees body volledig af (max 8KB)
        cl = 0
        for _hline in headers_raw.split("\r\n"):
            if _hline.lower().startswith("content-length:"):
                try:
                    cl = int(_hline.split(":", 1)[1].strip())
                except Exception:
                    cl = 0
        body = body_start
        while len(body) < cl and (len(headers_raw) + len(body)) < 8192:
            try:
                _ch = c.recv(min(512, cl - len(body)))
            except OSError:
                break
            if not _ch:
                break
            body += _ch
        req = headers_raw + "\r\n\r\n" + body.decode("utf-8", "ignore")
        if method == "GET" and path_no_query == "/":
            filename = _HTML_FILE_LITE if LOW_MEMORY_WEB_MODE else _HTML_FILE
            _send_html_response(c, filename)
            gc.collect()
            return
        if method == "GET" and path == "/api/time":
            self._roll_dos_idle_day()
            t = self.clock.read_time()
            c.send(self._json({
                "year": t[0], "month": t[1], "day": t[2],
                "hour": t[3], "minute": t[4], "second": t[5],
                "weekday": t[6], "weekday_name": self._weekday_name(t[6]),
                "weekday_short": self._weekday_short(t[6]),
                "timezone_name": self.clock.timezone_name,
                "timezone_label": self.clock.timezone_label(),
                "ui_language": self.ui_language,
                "boot_mode": self._get_boot_mode(),
                "setup_mode": self.setup_mode,
                "setup_ap_ssid": self.setup_ap_ssid,
                "setup_ip": self._get_setup_ip(),
                "wifi_ssid": self.wifi_ssid,
                "alarm_tone": self.tone,
                "alarm_volume": self.volume,
                "alarm_schedule": self.alarm_schedule,
                "alarm_combo": self.alarm_combo,
                "alarm_tones": get_alarm_tone_options(),
                "track_labels": self._track_labels,
                "alarm_gif_combo": self.alarm_gif_combo,
                "alarm_gifs": self._list_gif_choices(),
                "storage": self._get_storage_info(),
                "gif_tone_map": self._merged_gif_tone_map(),
                "gif_led_map": self._merged_gif_led_map(),
                "wifi_keep_alive": self.wifi_keep_alive,
                "weather_updates_per_day": self.weather_updates_per_day,
                "weather_place": self.config.get("weather", "place", "Zevenaar") if self.config else "Zevenaar",
                "weather_latitude": self.config.get("weather", "latitude", 51.92) if self.config else 51.92,
                "weather_longitude": self.config.get("weather", "longitude", 6.08) if self.config else 6.08,
                "app_version": APP_VERSION,
                "update_latest_version": self._update_latest_version,
                "update_pending": self._update_pending,
                "update_auto_enabled": self.auto_update_enabled,
                "update_manifest_url": self.update_manifest_url,
                "update_check_interval_hours": self.update_check_interval_hours,
                "retro_fact_display_seconds": self.retro_fact_display_seconds,
                "dos_idle_enabled": self.dos_idle_enabled,
                "dos_idle_trigger_minutes": self.dos_idle_trigger_minutes,
                "dos_idle_max_per_day": self.dos_idle_max_per_day,
                "dos_idle_shown_today": self._dos_idle_shown_today,
                "update_last_status": self._update_last_status,
                "update_last_error": self._update_last_error
            }))
            return
        if method == "GET" and path == "/api/storage-info":
            c.send(self._json({"ok": True, "storage": self._get_storage_info()}))
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
        if method == "POST" and path == "/api/set-language":
            d = self._parse(req)
            lang = self._normalize_ui_language(d.get("language", self.ui_language))
            self.ui_language = lang
            if self.config:
                self.config.set("ui", "language", lang)
            c.send(self._json({"ok": True, "ui_language": self.ui_language}))
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
        if method == "POST" and path == "/api/set-weather-location":
            d = self._parse(req)
            place = str(d.get("place", "") or "").strip()
            if not place:
                c.send(self._json({"ok": False, "error": "Geen plaatsnaam opgegeven"}))
                return
            if not self.config:
                c.send(self._json({"ok": False, "error": "Configuratie niet beschikbaar"}))
                return
            try:
                resolved = self._resolve_weather_location(place)
                self.config.config.setdefault("weather", {})
                self.config.config["weather"]["place"] = resolved["place"]
                self.config.config["weather"]["latitude"] = resolved["latitude"]
                self.config.config["weather"]["longitude"] = resolved["longitude"]
                self.config.save()
                self._weather_temp = None
                self._weather_code = None
                self._fetch_weather()
                self._weather_next_ms = time.ticks_add(time.ticks_ms(), self._weather_interval_ms)
                c.send(self._json({
                    "ok": True,
                    "place": resolved["place"],
                    "latitude": resolved["latitude"],
                    "longitude": resolved["longitude"],
                    "temp": self._weather_temp,
                    "code": self._weather_code,
                }))
            except Exception as _e:
                c.send(self._json({"ok": False, "error": str(_e)}))
            return
        if method == "POST" and path == "/api/set-network-settings":
            d = self._parse(req)
            self.wifi_keep_alive = bool(d.get("wifi_keep_alive", self.wifi_keep_alive))
            self.weather_updates_per_day = self._normalize_weather_updates_per_day(d.get("weather_updates_per_day", self.weather_updates_per_day))
            self._apply_network_settings(reset_wifi_timer=True)
            if self.config:
                self.config.set("wifi", "keep_alive", self.wifi_keep_alive)
                self.config.set("weather", "updates_per_day", self.weather_updates_per_day)
                self.config.set("weather", "interval_s", int(self._weather_interval_ms // 1000))
            c.send(self._json({
                "ok": True,
                "wifi_keep_alive": self.wifi_keep_alive,
                "weather_updates_per_day": self.weather_updates_per_day,
            }))
            return
        if method == "GET" and path == "/api/update-status":
            c.send(self._json({"ok": True, "update": self._get_update_status_payload()}))
            return
        if method == "POST" and path == "/api/check-updates":
            out = self._run_update_cycle(apply_update=False)
            if out.get("ok"):
                out["update"] = self._get_update_status_payload()
            c.send(self._json(out))
            return
        if method == "POST" and path == "/api/apply-update":
            out = self._run_update_cycle(apply_update=True)
            if out.get("ok"):
                out["update"] = self._get_update_status_payload()
            c.send(self._json(out))
            return
        if method == "POST" and path == "/api/set-update-settings":
            d = self._parse(req)
            self.auto_update_enabled = bool(d.get("auto_update_enabled", self.auto_update_enabled))
            self.update_manifest_url = self._normalize_manifest_url(d.get("manifest_url", self.update_manifest_url))
            self.update_check_interval_hours = self._normalize_update_check_interval_hours(
                d.get("check_interval_hours", self.update_check_interval_hours)
            )
            self._update_next_check_ms = time.ticks_add(time.ticks_ms(), 30000)
            if self.config:
                self.config.set("update", "auto_update_enabled", self.auto_update_enabled)
                self.config.set("update", "manifest_url", self.update_manifest_url)
                self.config.set("update", "check_interval_hours", self.update_check_interval_hours)
            c.send(self._json({"ok": True, "update": self._get_update_status_payload()}))
            return
        if method == "POST" and path == "/api/set-retro-fact-settings":
            d = self._parse(req)
            self.retro_fact_display_seconds = self._normalize_retro_fact_display_seconds(
                d.get("display_seconds", self.retro_fact_display_seconds)
            )
            if self.config:
                self.config.set("retro_fact", "display_seconds", self.retro_fact_display_seconds)
            c.send(self._json({
                "ok": True,
                "retro_fact_display_seconds": self.retro_fact_display_seconds,
            }))
            return
        if method == "POST" and path == "/api/set-dos-idle-settings":
            d = self._parse(req)
            self.dos_idle_enabled = bool(d.get("enabled", self.dos_idle_enabled))
            self.dos_idle_trigger_minutes = self._normalize_dos_idle_trigger_minutes(
                d.get("trigger_minutes", self.dos_idle_trigger_minutes)
            )
            self.dos_idle_max_per_day = self._normalize_dos_idle_max_per_day(
                d.get("max_per_day", self.dos_idle_max_per_day)
            )
            if self.config:
                self.config.set("dos_idle", "enabled", self.dos_idle_enabled)
                self.config.set("dos_idle", "trigger_minutes", self.dos_idle_trigger_minutes)
                self.config.set("dos_idle", "max_per_day", self.dos_idle_max_per_day)
            c.send(self._json({
                "ok": True,
                "dos_idle_enabled": self.dos_idle_enabled,
                "dos_idle_trigger_minutes": self.dos_idle_trigger_minutes,
                "dos_idle_max_per_day": self.dos_idle_max_per_day,
                "dos_idle_shown_today": self._dos_idle_shown_today,
            }))
            return
        if method == "POST" and path == "/api/set-wifi-credentials":
            d = self._parse(req)
            ssid = str(d.get("ssid", "") or "").strip()
            password = str(d.get("password", "") or "")
            if not ssid:
                c.send(self._json({"ok": False, "error": "SSID ontbreekt"}))
                return
            if not self.config:
                c.send(self._json({"ok": False, "error": "Configuratie niet beschikbaar"}))
                return
            if not self.config.set_wifi_credentials(ssid, password, keep_alive=self.wifi_keep_alive):
                c.send(self._json({"ok": False, "error": "Opslaan WiFi mislukt"}))
                return
            self.wifi_ssid = ssid
            self.wifi_password = password
            self._set_feedback_lines = ["WiFi opgeslagen:", ssid[:16], "Herstart..."]
            self._set_feedback("", ms=2500)
            print("WiFi credentials opgeslagen voor:", ssid)
            self._schedule_restart(1200)
            c.send(self._json({"ok": True, "restart": True, "ssid": ssid}))
            return
        if method == "POST" and path == "/api/set-alarm-schedule":
            d = self._parse(req)
            self.alarm_schedule = self._normalize_alarm_schedule(d.get("alarm_schedule", {}))
            self.alarm_combo = self._normalize_alarm_combo(d.get("alarm_combo", self.alarm_combo))
            self.alarm_gif_combo = self._normalize_alarm_gif_combo(d.get("alarm_gif_combo", self.alarm_gif_combo))
            if self.config:
                self.config.config["alarm_schedule"] = self.alarm_schedule
                self.config.config["alarm_combo"] = self.alarm_combo
                self.config.config["alarm_gif_combo"] = self.alarm_gif_combo
                self.config.save()
            if self.eeprom is not None:
                try:
                    self.eeprom.save_alarm_schedule(self.alarm_schedule)
                    print("Alarmschema opgeslagen in EEPROM")
                except Exception as _e:
                    print("! EEPROM schrijven mislukt:", _e)
            c.send(self._json({"ok": True}))
            return
        if method == "GET" and path == "/api/list-alarm-gifs":
            c.send(self._json({"ok": True, "gifs": self._list_gif_choices()}))
            return
        if method == "GET" and path == "/api/list-random-gifs":
            c.send(self._json({"ok": True, "gifs": self._list_random_gif_choices()}))
            return
        if method == "GET" and path == "/api/gif-mapping-status":
            c.send(self._json({"ok": True, "gifs": self._get_gif_mapping_status()}))
            return
        if method == "POST" and path == "/api/test-alarm":
            d = self._parse(req)
            try:
                sec = int(d.get("seconds", 0) or 0)
            except Exception:
                sec = 0
            if sec > 0:
                sec = max(1, min(60, sec))
            tone = self._normalize_tone_key(d.get("tone", self._tone_now()))
            led_tone = self._normalize_tone_key(d.get("led_tone", tone))
            animation = d.get("animation", "")
            self.active_gif = ""
            
            # Belangrijke fix: respecteer tone van client, override alleen als empty
            client_tone = d.get("tone", "")
            
            if isinstance(animation, str) and animation.startswith("gif:"):
                safe = "".join(ch for ch in animation[4:] if ('a' <= ch <= 'z') or ('A' <= ch <= 'Z') or ('0' <= ch <= '9') or ch in ('-', '_'))[:32]
                self.active_gif = self._pick_alarm_gif(safe if safe else "random")
                # Alleen lookup GIF-tone als client geen tone heeft gestuurd
                if not client_tone:
                    linked = self._get_gif_tone(self.active_gif)
                    if linked is not None:
                        tone = self._normalize_tone_key(linked)
                linked_led = self._get_gif_led_tone(self.active_gif)
                if linked_led is not None:
                    led_tone = self._normalize_tone_key(linked_led)
            elif isinstance(animation, str) and animation == "random":
                self.active_gif = self._pick_alarm_gif("random")
                if not client_tone:
                    linked = self._get_gif_tone(self.active_gif)
                    if linked is not None:
                        tone = self._normalize_tone_key(linked)
                linked_led = self._get_gif_led_tone(self.active_gif)
                if linked_led is not None:
                    led_tone = self._normalize_tone_key(linked_led)
            elif isinstance(animation, str) and animation.startswith("tone:"):
                tone = self._normalize_tone_key(animation[5:])
                led_tone = tone
            
            if self._gif_file is not None:
                try:
                    self._gif_file.close()
                except Exception:
                    pass
                self._gif_file = None
                self._gif_delays = []
            
            self.active_tone = tone
            self.active_led_tone = led_tone
            # Skip intro voor test-alarm (geen boot-intro gewenst)
            self._skip_intro = True
            self._in_intro = False
            self._alarm_repeat_track = (sec > 0)
            self.alarm_started_ms = time.ticks_ms()
            if sec > 0:
                self.alarm_until = time.ticks_add(time.ticks_ms(), sec * 1000)
            else:
                # Geen vaste timeout: stop handmatig, bij volgende start, of na einde track in preview-modus.
                self.alarm_until = time.ticks_add(time.ticks_ms(), 24 * 3600 * 1000)
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
        if method == "GET" and path == "/api/dfplayer-info":
            count = None
            if self._ensure_dfplayer_ready():
                try:
                    count = self.dfplayer.query_track_count()
                except Exception:
                    pass
            c.send(self._json({"ok": True, "track_count": count}))
            return
        if method == "POST" and path == "/api/play-track":
            d = self._parse(req)
            track = str(d.get("track", "") or "").strip()
            if track.isdigit() and 1 <= int(track) <= DFPLAYER_TRACK_COUNT:
                if self._ensure_dfplayer_ready():
                    try:
                        dfvol = max(0, min(30, int(self.volume * 30 // 100)))
                        self.dfplayer.set_volume(dfvol)
                        self.dfplayer.play_mp3(int(track))
                    except Exception as _e:
                        print("! play-track fout:", _e)
                c.send(self._json({"ok": True}))
            else:
                c.send(self._json({"ok": False, "error": "Ongeldig tracknummer"}))
            return
        if method == "POST" and path == "/api/stop-audio":
            # Stop handmatig gestart afspelen en actieve alarm/test-preview.
            if self.alarm_until is not None:
                self._stop_alarm(show_retro_fact=True)
            else:
                if self.dfplayer is not None:
                    try:
                        self.dfplayer.stop()
                        self.dfplayer.set_volume(0)
                    except Exception:
                        pass
                self._dfplayer_playing = False
                if self.leds is not None:
                    try:
                        self.leds.clear()
                    except Exception:
                        pass

            self.active_gif = ""
            self.alarm_started_ms = None
            self.alarm_until = None
            c.send(self._json({"ok": True}))
            return
        if method == "POST" and path == "/api/test-retro-fact":
            try:
                if self.alarm_until is not None:
                    c.send(self._json({"ok": False, "error": "Alarm is actief"}))
                else:
                    fact, source = self._show_retro_fact()
                    c.send(self._json({
                        "ok": True,
                        "fact": fact,
                        "source": source,
                        "mode": "manual",
                        "status": "ok",
                        "display_ms": self.retro_fact_display_seconds * 1000,
                        "display_seconds": self.retro_fact_display_seconds,
                    }))
            except Exception as e:
                c.send(self._json({"ok": False, "error": str(e)}))
            return
        if method == "POST" and path == "/api/test-dos-idle":
            try:
                if self.alarm_until is not None:
                    c.send(self._json({"ok": False, "error": "Alarm is actief"}))
                elif self.setup_mode:
                    c.send(self._json({"ok": False, "error": "Setup modus actief"}))
                else:
                    ok = self._start_dos_idle(manual=True)
                    c.send(self._json({
                        "ok": bool(ok),
                        "status": "ok" if ok else "busy",
                        "shown_today": self._dos_idle_shown_today,
                    }))
            except Exception as e:
                c.send(self._json({"ok": False, "error": str(e)}))
            return
        if method == "POST" and path == "/api/set-track-label":
            d = self._parse(req)
            track = str(d.get("track", "") or "").strip()
            label = str(d.get("label", "") or "").strip()[:40]
            if not track.isdigit() or not (1 <= int(track) <= DFPLAYER_TRACK_COUNT):
                c.send(self._json({"ok": False, "error": "Ongeldig tracknummer"}))
                return
            if label:
                self._track_labels[track] = label
            else:
                self._track_labels.pop(track, None)
            self._save_track_labels()
            c.send(self._json({"ok": True, "track_labels": self._track_labels}))
            return
        if method == "POST" and path == "/api/set-gif-tone":
            d = self._parse(req)
            gif_name = str(d.get("name", "") or "").strip()
            legacy_tone = str(d.get("tone", "") or "").strip()
            music_tone_key = str(d.get("music_tone", "") or "").strip()
            led_tone_key = str(d.get("led_tone", "") or "").strip()
            if legacy_tone and not music_tone_key:
                music_tone_key = legacy_tone
            if legacy_tone and not led_tone_key:
                led_tone_key = legacy_tone
            safe = "".join(ch for ch in gif_name if ('a' <= ch <= 'z') or ('A' <= ch <= 'Z') or ('0' <= ch <= '9') or ch in ('-', '_'))[:32]
            if not safe:
                c.send(self._json({"ok": False, "error": "Ongeldige animatienaam"}))
                return
            if music_tone_key:
                self._gif_tone_overrides[safe] = self._normalize_tone_key(music_tone_key)
            else:
                self._gif_tone_overrides.pop(safe, None)
            if led_tone_key:
                self._gif_led_overrides[safe] = self._normalize_tone_key(led_tone_key)
            else:
                self._gif_led_overrides.pop(safe, None)
            self._save_gif_tone_overrides()
            self._save_gif_led_overrides()
            c.send(self._json({"ok": True, "gif_tone_map": self._merged_gif_tone_map(), "gif_led_map": self._merged_gif_led_map()}))
            return
        if method == "POST" and path == "/api/delete-gif":
            import uos as _uos
            d = self._parse(req)
            name = str(d.get("name", "") or "")
            safe = "".join(ch for ch in name if ('a' <= ch <= 'z') or ('A' <= ch <= 'Z') or ('0' <= ch <= '9') or ch in ('-', '_'))[:32]
            if safe.lower().endswith("bin"):
                safe = safe[:-3].rstrip(".")
            if not safe:
                c.send(self._json({"ok": False, "error": "Ongeldige naam"}))
                return
            try:
                try:
                    _uos.remove("/{}/{}.bin".format(ANIMATIONS_DIR, safe))
                except OSError:
                    _uos.remove("/{}.bin".format(safe))
                if safe in self._gif_tone_overrides:
                    self._gif_tone_overrides.pop(safe, None)
                    self._save_gif_tone_overrides()
                if safe in self._gif_led_overrides:
                    self._gif_led_overrides.pop(safe, None)
                    self._save_gif_led_overrides()
                c.send(self._json({"ok": True}))
            except OSError:
                c.send(self._json({"ok": False, "error": "Bestand niet gevonden"}))
            return
        if method == "POST" and path == "/api/restart":
            import machine as _machine
            c.send(self._json({"ok": True, "message": "Herstarten..."}))
            try:
                c.close()
            except Exception:
                pass
            import time as _time
            _time.sleep_ms(300)
            _machine.reset()
            return
        c.send("HTTP/1.1 404 Not Found\r\n\r\n".encode())

    def run(self):
        print("Hoofdloop gestart")
        try:
            self._play_boot_intro()
        except Exception as _e:
            print("! Boot intro fout, ga door:", _e)
            try:
                if self.dfplayer:
                    self.dfplayer.stop()
            except Exception:
                pass

        self._board_led_off()

        frame = 0
        gc_counter = 0
        while True:
            try:
                if self._pending_restart_ms is not None and time.ticks_diff(time.ticks_ms(), self._pending_restart_ms) >= 0:
                    import machine as _machine
                    print("Herstart na config-wijziging...")
                    _machine.reset()
                self._status_led_tick += 1
                if self._status_led_tick >= 50:
                    self._board_led_off()
                    self._status_led_tick = 0
                self._handle_buttons()
                self._handle_wifi_state()
                self._check_weather_fetch()
                self._check_auto_update()
                self._check_dos_idle()

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
                    if self.snooze_until is not None:
                        if time.ticks_diff(time.ticks_ms(), self.snooze_until) >= 0:
                            self.active_tone = self._normalize_tone_key(self.snooze_tone if self.snooze_tone else self._tone_now())
                            self.active_gif = self.snooze_gif if self.snooze_gif else ""
                            self._alarm_repeat_track = True
                            self.alarm_started_ms = time.ticks_ms()
                            self.alarm_until = time.ticks_add(time.ticks_ms(), ALARM_AUTO_STOP_MS)
                            self.snooze_until = None
                            self.snooze_tone = None
                            self.snooze_gif = ""
                    else:
                        self._check_scheduled_alarm()

                if self._retro_fact_pending and self.alarm_until is None and self.snooze_until is None:
                    if self.wifi_ok and self.wifi and self.wifi.is_connected():
                        self._show_retro_fact()
                    else:
                        self._retro_fact_pending = False
                        self._set_feedback_lines = ["RETRO FACT", "geen internet"]
                        self._set_feedback_text = "RETRO FACT geen internet"
                        self._set_feedback_until = time.ticks_add(time.ticks_ms(), 4500)

                if frame > 0 and frame % 18000 == 0 and self.wifi_ok:
                    self.clock.sync_ntp()

                if self.display:
                    self._apply_display_brightness()
                    if self.setup_mode:
                        self._draw_setup_mode()
                    elif self.alarm_until is not None:
                        self._draw_alarm_animation(frame)
                        self._update_led_animation(frame)
                    elif self.alarm_edit_mode:
                        self._draw_alarm_edit()
                    elif self.startup_ip_until is not None and time.ticks_diff(self.startup_ip_until, time.ticks_ms()) > 0:
                        self._draw_startup_ip()
                    elif self._draw_dos_idle():
                        pass
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
                time.sleep(0.01)
            except Exception as e:
                print("Loop fout:", e)
                gc.collect()
                time.sleep(0.5)


if __name__ == "__main__":
    app = App()
    app.run()


