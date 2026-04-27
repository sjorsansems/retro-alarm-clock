"""
ESP32 Alarmklok met WiFi Web Interface + NTP Synchronisatie
VERBETERDE VERSIE: Gebruikt Station mode (STA) met DHCP
"""

from machine import Pin, I2C, PWM, SoftI2C
import framebuf
import time
import json
import network
import socket
import gc

LOW_MEMORY_WEB_MODE = False

# Import modules
try:
    from ntp_time_sync import NTPTimeSync
except ImportError:
    NTPTimeSync = None

try:
    from config_manager import ConfigManager
except ImportError:
    ConfigManager = None

WIFI_MANAGER_IMPORT_ERROR = None
try:
    from wifi_manager import WiFiManager
except ImportError as exc:
    WiFiManager = None
    WIFI_MANAGER_IMPORT_ERROR = exc


if WiFiManager is None:
    class WiFiManager:
        def __init__(self, ssid, password, timeout=10):
            self.ssid = ssid
            self.password = password
            self.timeout = timeout
            self.sta = None

            last_error = None
            for _try_idx in range(3):
                try:
                    gc.collect()
                    self.sta = network.WLAN(network.STA_IF)
                    break
                except OSError as e:
                    last_error = e
                    # Geef de heap kort de kans om te herstellen.
                    gc.collect()
                    time.sleep(0.2)

            if self.sta is None:
                raise OSError("WiFi Out of Memory: {}".format(last_error))

        def connect(self):
            print("\n=== WiFi Verbinding ===")
            print("Netwerk:", self.ssid)

            if not self.sta.active():
                print("-> STA mode activeren...")
                self.sta.active(True)
                time.sleep(1)

            if self.sta.isconnected():
                ip_info = self.sta.ifconfig()
                print("âœ“ Reeds verbonden!")
                print("  IP-adres:", ip_info[0])
                return True

            print("-> Verbinden...")
            self.sta.connect(self.ssid, self.password)

            start_time = time.time()
            while not self.sta.isconnected():
                elapsed = int(time.time() - start_time)
                print("  Wachten... ({}s)".format(elapsed))

                if elapsed > self.timeout:
                    print("âœ— Verbinding mislukt na {}s".format(self.timeout))
                    self.sta.disconnect()
                    return False

                time.sleep(0.5)

            ip_info = self.sta.ifconfig()
            print("âœ“ Verbonden!")
            print("  IP-adres:", ip_info[0])
            print("  Netmask: ", ip_info[1])
            print("  Gateway: ", ip_info[2])
            print("  DNS:     ", ip_info[3])
            return True

        def disconnect(self):
            if self.sta.isconnected():
                self.sta.disconnect()

        def is_connected(self):
            return self.sta.isconnected()

        def get_ip(self):
            if self.is_connected():
                return self.sta.ifconfig()[0]
            return None


DAY_ORDER = (
    ("mon", "Maandag"),
    ("tue", "Dinsdag"),
    ("wed", "Woensdag"),
    ("thu", "Donderdag"),
    ("fri", "Vrijdag"),
    ("sat", "Zaterdag"),
    ("sun", "Zondag"),
)


def build_default_alarm_schedule(enabled=False, hour=7, minute=0):
    schedule = {}
    for day_key, _day_name in DAY_ORDER:
        schedule[day_key] = {
            "enabled": bool(enabled),
            "hour": int(hour),
            "minute": int(minute),
        }
    return schedule


def normalize_alarm_schedule(schedule, legacy_alarm=None):
    legacy_alarm = legacy_alarm or {}
    default_enabled = legacy_alarm.get("enabled", False)
    default_hour = legacy_alarm.get("hour", 7)
    default_minute = legacy_alarm.get("minute", 0)
    normalized = build_default_alarm_schedule(default_enabled, default_hour, default_minute)

    if isinstance(schedule, dict):
        for day_key, _day_name in DAY_ORDER:
            day_config = schedule.get(day_key, {})
            if isinstance(day_config, dict):
                normalized[day_key]["enabled"] = bool(day_config.get("enabled", normalized[day_key]["enabled"]))
                normalized[day_key]["hour"] = int(day_config.get("hour", normalized[day_key]["hour"])) % 24
                normalized[day_key]["minute"] = int(day_config.get("minute", normalized[day_key]["minute"])) % 60

    return normalized


def weekday_to_day_key(weekday):
    if not weekday:
        return DAY_ORDER[0][0]
    index = (int(weekday) - 1) % 7
    return DAY_ORDER[index][0]


def day_key_to_name(day_key):
    for current_key, day_name in DAY_ORDER:
        if current_key == day_key:
            return day_name
    return day_key


TIMEZONE_OPTIONS = (
    ("Europe/Amsterdam", "Europa/Amsterdam (automatische zomer-/wintertijd)"),
    ("UTC", "UTC"),
    ("UTC+1", "UTC+1"),
    ("UTC+2", "UTC+2"),
    ("UTC+3", "UTC+3"),
    ("UTC-1", "UTC-1"),
    ("UTC-2", "UTC-2"),
)

ALARM_TONES = {
    "classic": {
        "label": "Classic Beep",
        "pattern": ((1200, 420, 3), (0, 0, 2), (1000, 420, 3), (0, 0, 4)),
    },
    "siren": {
        "label": "Siren",
        "pattern": ((700, 480, 2), (900, 480, 2), (1100, 480, 2), (900, 480, 2)),
    },
    "pulse": {
        "label": "Pulse",
        "pattern": ((1500, 360, 1), (0, 0, 1), (1500, 360, 1), (0, 0, 3)),
    },
    "soft": {
        "label": "Soft",
        "pattern": ((880, 260, 2), (0, 0, 2), (660, 260, 2), (0, 0, 4)),
    },
    "super_mario_main_theme_rttl": {
        "label": "Super Mario - Main Theme (RTTTL)",
        "rtttl": "Super Mario - Main Theme:d=4,o=5,b=125:a,8f.,16c,16d,16f,16p,f,16d,16c,16p,16f,16p,16f,16p,8c6,8a.,g,16c,a,8f.,16c,16d,16f,16p,f,16d,16c,16p,16f,16p,16a#,16a,16g,2f,16p,8a.,8f.,8c,8a.,f,16g#,16f,16c,16p,8g#.,2g,8a.,8f.,8c,8a.,f,16g#,16f,8c,2c6",
    },
    "super_mario_title_music_rttl": {
        "label": "Super Mario - Title Music (RTTTL)",
        "rtttl": "Super Mario - Title Music:d=4,o=5,b=125:8d7,8d7,8d7,8d6,8d7,8d7,8d7,8d6,2d#7,8d7,p,32p,8d6,8b6,8b6,8b6,8d6,8b6,8b6,8b6,8d6,8b6,8b6,8b6,16b6,16c7,b6,8a6,8d6,8a6,8a6,8a6,8d6,8a6,8a6,8a6,8d6,8a6,8a6,8a6,16a6,16b6,a6,8g6,8d6,8b6,8b6,8b6,8d6,8b6,8b6,8b6,8d6,8b6,8b6,8b6,16a6,16b6,c7,e7,8d7,8d7,8d7,8d6,8c7,8c7,8c7,8f#6,2g6",
    },
    "smbtheme_rttl": {
        "label": "SMBtheme (RTTTL)",
        "rtttl": "SMBtheme:d=4,o=5,b=100:16e6,16e6,32p,8e6,16c6,8e6,8g6,8p,8g,8p,8c6,16p,8g,16p,8e,16p,8a,8b,16a#,8a,16g.,16e6,16g6,8a6,16f6,8g6,8e6,16c6,16d6,8b,16p,8c6,16p,8g,16p,8e,16p,8a,8b,16a#,8a,16g.,16e6,16g6,8a6,16f6,8g6,8e6,16c6,16d6,8b,8p,16g6,16f#6,16f6,16d#6,16p,16e6,16p,16g#,16a,16c6,16p,16a,16c6,16d6,8p,16g6,16f#6,16f6,16d#6,16p,16e6,16p,16c7,16p,16c7,16c7,p,16g6,16f#6,16f6,16d#6,16p,16e6,16p,16g#,16a,16c6,16p,16a,16c6,16d6,8p,16d#6,8p,16d6,8p,16c6",
    },
    "smbwater_rttl": {
        "label": "SMBwater (RTTTL)",
        "rtttl": "SMBwater:d=8,o=6,b=225:4d5,4e5,4f#5,4g5,4a5,4a#5,b5,b5,b5,p,b5,p,2b5,p,g5,2e.,2d#.,2e.,p,g5,a5,b5,c,d,2e.,2d#,4f,2e.,2p,p,g5,2d.,2c#.,2d.,p,g5,a5,b5,c,c#,2d.,2g5,4f,2e.,2p,p,g5,2g.,2g.,2g.,4g,4a,p,g,2f.,2f.,2f.,4f,4g,p,f,2e.,4a5,4b5,4f,e,e,4e.,b5,2c.",
    },
    "smbunderground_rttl": {
        "label": "SMBunderground (RTTTL)",
        "rtttl": "SMBunderground:d=16,o=6,b=100:c,c5,a5,a,a#5,a#,2p,8p,c,c5,a5,a,a#5,a#,2p,8p,f5,f,d5,d,d#5,d#,2p,8p,f5,f,d5,d,d#5,d#,2p,32d#,d,32c#,c,p,d#,p,d,p,g#5,p,g5,p,c#,p,32c,f#,32f,32e,a#,32a,g#,32p,d#,b5,32p,a#5,32p,a5,g#5",
    },
    "xfiles_rttl": {
        "label": "Xfiles (RTTTL)",
        "rtttl": "Xfiles:d=4,o=5,b=125:e,b,a,b,d6,2b.,1p,e,b,a,b,e6,2b.,1p,g6,f#6,e6,d6,e6,2b.,1p,g6,f#6,e6,d6,f#6,2b.,1p,e,b,a,b,d6,2b.,1p,e,b,a,b,e6,2b.,1p,e6,2b.",
    },
    "good_bad_rttl": {
        "label": "GoodBad (RTTTL)",
        "rtttl": "GoodBad:d=4,o=5,b=56:32p,32a#,32d#6,32a#,32d#6,8a#.,16f#.,16g#.,d#,32a#,32d#6,32a#,32d#6,8a#.,16f#.,16g#.,c#6,32a#,32d#6,32a#,32d#6,8a#.,16f#.,32f.,32d#.,c#,32a#,32d#6,32a#,32d#6,8a#.,16g#.,d#",
    },
    "a_team_rttl": {
        "label": "A-Team (RTTTL)",
        "rtttl": "A-Team:d=8,o=5,b=125:4d#6,a#,2d#6,16p,g#,4a#,4d#.,p,16g,16a#,d#6,a#,f6,2d#6,16p,c#.6,16c6,16a#,g#.,2a#",
    },
    "gadget_rttl": {
        "label": "Gadget (RTTTL)",
        "rtttl": "Gadget:d=16,o=5,b=50:32d#,32f,32f#,32g#,a#,f#,a,f,g#,f#,32d#,32f,32f#,32g#,a#,d#6,4d6,32d#,32f,32f#,32g#,a#,f#,a,f,g#,f#,8d#",
    },
    "mkombat_rttl": {
        "label": "Mortal Kombat (RTTTL)",
        "rtttl": "mkombat:d=4,o=5,b=70:16a#,16a#,16c#6,16a#,16d#6,16a#,16f6,16d#6,16c#6,16c#6,16f6,16c#6,16g#6,16c#6,16f6,16c#6,16g#,16g#,16c6,16g#,16c#6,16g#,16d#6,16c#6,16f#,16f#,16a#,16f#,16c#6,16f#,16c#6,16c6.",
    },
}

RETRO_TONE_KEYS = (
    "super_mario_main_theme_rttl",
    "super_mario_title_music_rttl",
    "smbtheme_rttl",
    "smbwater_rttl",
    "smbunderground_rttl",
    "xfiles_rttl",
    "good_bad_rttl",
    "a_team_rttl",
    "gadget_rttl",
    "mkombat_rttl",
)

ALARM_RANDOM_KEY = "retro_random"
_RTTL_FRAME_MS = 200
_RTTL_DEFAULT_DUTY = 420
_RTTL_PATTERN_CACHE = {}

MARIO_ANIM_INTERVAL_MS = 140
MARIO_ANIM_STEP_PIXELS = 2
MARIO_SPRITE_WIDTH = 12
MARIO_SPRITE_HEIGHT = 12
MARIO_SPRITE_Y = 8

MARIO_FRAMES = (
    (
        "000011100000",
        "000111111000",
        "000110010000",
        "000111111100",
        "001111110000",
        "001011101000",
        "001111111000",
        "000011011000",
        "000111111100",
        "001100110000",
        "011000011000",
        "110000001100",
    ),
    (
        "000011100000",
        "000111111000",
        "000110010000",
        "000111111100",
        "001111110000",
        "001011101000",
        "001111111000",
        "000011011000",
        "000111111100",
        "001100011000",
        "000000111100",
        "000001100000",
    ),
)

_NOTE_TO_SEMITONE = {
    "c": 0,
    "c#": 1,
    "d": 2,
    "d#": 3,
    "e": 4,
    "f": 5,
    "f#": 6,
    "g": 7,
    "g#": 8,
    "a": 9,
    "a#": 10,
    "b": 11,
}


def _rttl_parse_defaults(defaults_text):
    default_duration = 4
    default_octave = 6
    bpm = 63

    parts = defaults_text.split(',')
    for part in parts:
        token = part.strip().lower()
        if '=' not in token:
            continue
        key, value = token.split('=', 1)
        try:
            parsed = int(value)
        except:
            continue

        if key == 'd' and parsed > 0:
            default_duration = parsed
        elif key == 'o' and parsed >= 0:
            default_octave = parsed
        elif key == 'b' and parsed > 0:
            bpm = parsed

    return default_duration, default_octave, bpm


def _rttl_note_to_freq(note_name, octave):
    if note_name == 'p':
        return 0

    semitone = _NOTE_TO_SEMITONE.get(note_name)
    if semitone is None:
        return 0

    midi = (int(octave) + 1) * 12 + semitone
    return int((440 * (2 ** ((midi - 69) / 12.0))) + 0.5)


def _rttl_add_pattern_step(pattern, freq, duty, duration_frames):
    if duration_frames <= 0:
        return

    if pattern and pattern[-1][0] == freq and pattern[-1][1] == duty:
        last_freq, last_duty, last_duration = pattern[-1]
        pattern[-1] = (last_freq, last_duty, last_duration + duration_frames)
        return

    pattern.append((freq, duty, duration_frames))


def _parse_rtttl_pattern(song_key, rtttl_text):
    cached = _RTTL_PATTERN_CACHE.get(song_key)
    if cached:
        return cached

    try:
        name_split = rtttl_text.split(':', 2)
        if len(name_split) == 3:
            _song_name, defaults_text, notes_text = name_split
        elif len(name_split) == 2:
            defaults_text, notes_text = name_split
        else:
            defaults_text = ''
            notes_text = rtttl_text

        default_duration, default_octave, bpm = _rttl_parse_defaults(defaults_text)
        whole_note_ms = 240000.0 / float(bpm if bpm > 0 else 63)

        pattern = []
        for raw_token in notes_text.split(','):
            token = raw_token.strip().lower()
            if not token:
                continue

            index = 0
            token_len = len(token)

            duration_value = None
            while index < token_len and token[index].isdigit():
                if duration_value is None:
                    duration_value = 0
                duration_value = (duration_value * 10) + int(token[index])
                index += 1
            if not duration_value:
                duration_value = default_duration

            if index >= token_len:
                continue

            note_char = token[index]
            index += 1
            if note_char not in ('a', 'b', 'c', 'd', 'e', 'f', 'g', 'p'):
                continue

            has_sharp = False
            if index < token_len and token[index] == '#':
                has_sharp = True
                index += 1

            dotted = False
            octave = default_octave

            if index < token_len and token[index] == '.':
                dotted = True
                index += 1

            octave_value = None
            while index < token_len and token[index].isdigit():
                if octave_value is None:
                    octave_value = 0
                octave_value = (octave_value * 10) + int(token[index])
                index += 1
            if octave_value is not None:
                octave = octave_value

            if index < token_len and token[index] == '.':
                dotted = True

            if note_char == 'p':
                note_name = 'p'
            else:
                note_name = note_char + ('#' if has_sharp else '')

            note_ms = whole_note_ms / float(duration_value if duration_value > 0 else default_duration)
            if dotted:
                note_ms *= 1.5

            duration_frames = int((note_ms / _RTTL_FRAME_MS) + 0.5)
            if duration_frames < 1:
                duration_frames = 1

            freq = _rttl_note_to_freq(note_name, octave)
            duty = _RTTL_DEFAULT_DUTY if freq > 0 else 0
            _rttl_add_pattern_step(pattern, freq, duty, duration_frames)

        if not pattern:
            fallback = ALARM_TONES["classic"]["pattern"]
            _RTTL_PATTERN_CACHE[song_key] = fallback
            return fallback

        parsed_pattern = tuple(pattern)
        _RTTL_PATTERN_CACHE[song_key] = parsed_pattern
        return parsed_pattern

    except Exception as e:
        print("RTTTL parse fout voor {}: {}".format(song_key, e))
        fallback = ALARM_TONES["classic"]["pattern"]
        _RTTL_PATTERN_CACHE[song_key] = fallback
        return fallback


def _parse_rttl_pattern(song_key, rttl_text):
    return _parse_rtttl_pattern(song_key, rttl_text)


def normalize_alarm_tone(tone_name):
    if tone_name == ALARM_RANDOM_KEY:
        return ALARM_RANDOM_KEY
    if tone_name in ALARM_TONES:
        return tone_name
    return "classic"


def get_alarm_tone_options():
    options = [{"key": ALARM_RANDOM_KEY, "label": "Retro Random (elke dag anders)"}]
    for tone_key in ALARM_TONES:
        options.append({"key": tone_key, "label": ALARM_TONES[tone_key]["label"]})
    return options


def normalize_alarm_volume(volume):
    try:
        value = int(volume)
    except:
        value = 70
    if value < 0:
        value = 0
    if value > 100:
        value = 100
    return value


def shift_time_tuple(time_tuple, offset_hours):
    year, month, day, hour, minute, second = time_tuple[:6]
    base_tuple = (year, month, day, hour, minute, second, 0, 0)
    epoch = time.mktime(base_tuple)
    shifted = time.localtime(epoch + int(offset_hours * 3600))
    return shifted[:6] + (shifted[6] + 1, shifted[7])


def parse_utc_offset(timezone_name):
    if timezone_name == "UTC":
        return 0

    if not timezone_name.startswith("UTC"):
        return 0

    offset_str = timezone_name[3:]
    if not offset_str:
        return 0

    sign = 1
    if offset_str[0] == '-':
        sign = -1
    offset_value = offset_str[1:] if offset_str[0] in "+-" else offset_str

    try:
        return sign * int(offset_value)
    except:
        return 0


def get_timezone_info_for_utc(time_tuple, timezone_name):
    timezone_name = timezone_name or "Europe/Amsterdam"

    if timezone_name == "Europe/Amsterdam" and NTPTimeSync:
        local_time = NTPTimeSync.time_tuple_to_dutch(time_tuple)
        # NTP helper returns weekday as 0..6 (ma..zo); this app uses 1..7.
        if len(local_time) >= 7:
            local_time = local_time[:6] + (int(local_time[6]) + 1,) + local_time[7:]
        is_dst = NTPTimeSync.is_dst(time_tuple[0], time_tuple[1], time_tuple[2])
        timezone_label = "CEST" if is_dst else "CET"
        return local_time, timezone_label

    offset_hours = parse_utc_offset(timezone_name)
    local_time = shift_time_tuple(time_tuple, offset_hours)
    if offset_hours == 0:
        timezone_label = "UTC"
    elif offset_hours > 0:
        timezone_label = "UTC+{}".format(offset_hours)
    else:
        timezone_label = "UTC{}".format(offset_hours)
    return local_time, timezone_label

# ====== PIN CONFIGURATIE ======
SDA_PIN = 21
SCL_PIN = 22
I2C_FREQ = 100_000

# D14: set/toggle/save, D13: uur+, D12: minuut+
UP_BUTTON_PIN = 13
DOWN_BUTTON_PIN = 12
SET_BUTTON_PIN = 14
BUZZER_PIN = 27

WIDTH = 128
HEIGHT = 64
DISPLAY_TYPE = "SH1106"
SH1106_COL_OFFSET = 2
WIFI_PORT = 80

# ====== DISPLAY DRIVERS ======

class SH1106_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C):
        self.width = width
        self.height = height
        self.i2c = i2c
        self.addr = addr
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        self._init_display()

    def _write_cmd(self, cmd):
        self.i2c.writeto(self.addr, bytes((0x80, cmd)))

    def _write_data(self, data):
        self.i2c.writeto(self.addr, b"\x40" + data)

    def _init_display(self):
        for cmd in (0xAE, 0xD5, 0x80, 0xA8, self.height - 1, 0xD3, 0x00, 0x40,
                   0xAD, 0x8B, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0x7F, 0xD9, 0x22,
                   0xDB, 0x35, 0xA4, 0xA6, 0xAF):
            self._write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        for page in range(self.pages):
            self._write_cmd(0xB0 + page)
            col = SH1106_COL_OFFSET
            self._write_cmd(col & 0x0F)
            self._write_cmd(0x10 | (col >> 4))
            start = self.width * page
            end = start + self.width
            self._write_data(self.buffer[start:end])


def init_i2c():
    return SoftI2C(sda=Pin(SDA_PIN, pull=Pin.PULL_UP),
                   scl=Pin(SCL_PIN, pull=Pin.PULL_UP),
                   freq=I2C_FREQ)


def scan_i2c_devices(i2c):
    try:
        return i2c.scan()
    except:
        return []


def init_display(i2c):
    try:
        devices = i2c.scan()
        addr = 0x3C if 0x3C in devices else (0x3D if 0x3D in devices else (devices[0] if devices else None))
        if addr is None:
            return None
        return SH1106_I2C(WIDTH, HEIGHT, i2c, addr)
    except:
        return None


# ====== DS3231 RTC MODULE ======

class DS3231:
    def __init__(self, i2c, addr=0x68, enable_ntp=True, wlan=None, ntp_server="pool.ntp.org", sync_interval=3600, timezone_name="Europe/Amsterdam"):
        self.i2c = i2c
        self.addr = addr
        self.wlan = wlan
        self.ntp_server = ntp_server
        self.sync_interval = sync_interval
        self.timezone_name = timezone_name or "Europe/Amsterdam"
        self.rtc_available = True
        self.soft_epoch = None
        self.soft_ticks_ms = 0
        self._probe_rtc()
        
        if enable_ntp and NTPTimeSync:
            self.ntp_sync = NTPTimeSync()
            self.last_sync = 0
        else:
            self.ntp_sync = None
    
    def read_time(self):
        if not self.rtc_available:
            return self._read_software_time()

        try:
            data = self.i2c.readfrom_mem(self.addr, 0x00, 7)
            sec = self._bcd_to_int(data[0] & 0x7F)
            minute = self._bcd_to_int(data[1] & 0x7F)
            hour = self._bcd_to_int(data[2] & 0x3F)
            weekday = self._normalize_weekday(self._bcd_to_int(data[3] & 0x07))
            day = self._bcd_to_int(data[4] & 0x3F)
            month = self._bcd_to_int(data[5] & 0x1F)
            year = self._bcd_to_int(data[6]) + 2000

            if not self._is_valid_date(year, month, day):
                raise ValueError("Ongeldige RTC datum")
            return (year, month, day, hour, minute, sec, weekday, 0)
        except:
            self.rtc_available = False
            return self._read_software_time()
    
    def set_time(self, year, month, day, hour, minute, second):
        if not self.rtc_available:
            weekday = self._calculate_weekday(year, month, day)
            self._set_software_time((year, month, day, hour, minute, second, weekday, 0))
            return True

        try:
            weekday = self._calculate_weekday(year, month, day)
            data = bytearray(7)
            data[0] = self._int_to_bcd(second)
            data[1] = self._int_to_bcd(minute)
            data[2] = self._int_to_bcd(hour)
            data[3] = self._int_to_bcd(weekday)
            data[4] = self._int_to_bcd(day)
            data[5] = self._int_to_bcd(month)
            data[6] = self._int_to_bcd(year - 2000)
            self.i2c.writeto_mem(self.addr, 0x00, data)
            return True
        except Exception as e:
            print("âœ— RTC set_time fout:", e)
            self.rtc_available = False
            return False
    
    def sync_ntp(self, force=False):
        """Synchroniseer RTC met NTP"""
        if not self.ntp_sync:
            return False
        
        current_time = time.time()
        if not force and (current_time - self.last_sync) < self.sync_interval:
            return False
        
        if self.wlan and not self.wlan.isconnected():
            return False
        
        try:
            import ntptime
            ntptime.host = self.ntp_server
            ntptime.settime()
            
            utc_time = time.gmtime()
            local_time, timezone_label = get_timezone_info_for_utc(utc_time, self.timezone_name)

            if not self.rtc_available:
                self._set_software_time(local_time)
                self.last_sync = current_time
                print(f"âœ“ NTP Sync ({timezone_label}): systeemtijd bijgewerkt (RTC niet gevonden)")
                return True

            if not self.set_time(*local_time[:6]):
                print("âœ— RTC update na NTP mislukt")
                return False
            
            self.last_sync = current_time
            print(f"âœ“ NTP Sync ({timezone_label}): {local_time[2]:02d}-{local_time[1]:02d}-{local_time[0]} {local_time[3]:02d}:{local_time[4]:02d}:{local_time[5]:02d}")
            return True
        
        except Exception as e:
            print(f"âœ— NTP Sync fout: {e}")
            return False
    
    def _bcd_to_int(self, bcd):
        return (bcd >> 4) * 10 + (bcd & 0x0F)
    
    def _int_to_bcd(self, val):
        return ((val // 10) << 4) | (val % 10)

    def _calculate_weekday(self, year, month, day):
        if NTPTimeSync:
            return NTPTimeSync.get_weekday(year, month, day) + 1

        if month < 3:
            month += 12
            year -= 1

        q = day
        m = month
        k = year % 100
        j = year // 100
        h = (q + ((13 * (m + 1)) // 5) + k + (k // 4) + (j // 4) - (2 * j)) % 7
        return ((h + 5) % 7) + 1

    def _normalize_weekday(self, weekday):
        weekday = int(weekday or 1)
        if weekday < 1 or weekday > 7:
            return 1
        return weekday

    def _is_valid_date(self, year, month, day):
        if year < 2024 or month < 1 or month > 12 or day < 1:
            return False

        days_in_month = (31, 29 if self._is_leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
        return day <= days_in_month[month - 1]

    def _is_leap_year(self, year):
        return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

    def _probe_rtc(self):
        try:
            self.i2c.readfrom_mem(self.addr, 0x00, 1)
            self.rtc_available = True
        except:
            self.rtc_available = False

    def has_hardware(self):
        return self.rtc_available

    def set_timezone(self, timezone_name):
        self.timezone_name = timezone_name or "Europe/Amsterdam"
        if not self.rtc_available:
            utc_time = time.gmtime()
            local_time, _timezone_label = get_timezone_info_for_utc(utc_time, self.timezone_name)
            self._set_software_time(local_time)

    def get_timezone_name(self):
        return self.timezone_name

    def get_timezone_label(self):
        current_time = self.read_time()
        if self.timezone_name == "Europe/Amsterdam" and NTPTimeSync:
            return "CEST" if NTPTimeSync.is_dst(current_time[0], current_time[1], current_time[2]) else "CET"
        return self.timezone_name

    def _set_software_time(self, local_time):
        base = (local_time[0], local_time[1], local_time[2], local_time[3], local_time[4], local_time[5], 0, 0)
        self.soft_epoch = time.mktime(base)
        self.soft_ticks_ms = time.ticks_ms()

    def _read_software_time(self):
        if self.soft_epoch is None:
            utc_time = time.gmtime()
            local_time, _timezone_label = get_timezone_info_for_utc(utc_time, self.timezone_name)
            self._set_software_time(local_time)
            return local_time

        elapsed_seconds = time.ticks_diff(time.ticks_ms(), self.soft_ticks_ms) // 1000
        now_tuple = time.localtime(self.soft_epoch + elapsed_seconds)
        weekday = self._normalize_weekday(now_tuple[6] + 1)
        return (now_tuple[0], now_tuple[1], now_tuple[2], now_tuple[3], now_tuple[4], now_tuple[5], weekday, now_tuple[7])


# ====== CONFIGURATIE BEHEER ======

class AlarmConfig:
    def __init__(self, config_manager=None):
        if config_manager:
            self.config_manager = config_manager
        else:
            if ConfigManager:
                self.config_manager = ConfigManager("config.json")
            else:
                self.config_manager = None
    
    def get(self, section, key=None, default=None):
        if self.config_manager:
            return self.config_manager.get(section, key, default)
        return default
    
    def set(self, section, key, value):
        if self.config_manager:
            return self.config_manager.set(section, key, value)
        return False

    def get_alarm_schedule(self):
        legacy_alarm = self.get("alarm", default={}) or {}
        current_schedule = self.get("alarm_schedule", default=None)
        normalized = normalize_alarm_schedule(current_schedule, legacy_alarm)

        if self.config_manager and current_schedule != normalized:
            self.config_manager.config["alarm_schedule"] = normalized
            self.config_manager.save()

        return normalized

    def set_alarm_schedule(self, schedule):
        normalized = normalize_alarm_schedule(schedule, self.get("alarm", default={}) or {})
        if self.config_manager:
            self.config_manager.config["alarm_schedule"] = normalized
            return self.config_manager.save()
        return False

    def get_alarm_tone(self):
        tone_name = self.get("alarm_sound", "tone", "classic")
        normalized = normalize_alarm_tone(tone_name)
        if normalized != tone_name and self.config_manager:
            self.config_manager.config.setdefault("alarm_sound", {})["tone"] = normalized
            self.config_manager.save()
        return normalized

    def set_alarm_tone(self, tone_name):
        normalized = normalize_alarm_tone(tone_name)
        if self.config_manager:
            self.config_manager.config.setdefault("alarm_sound", {})["tone"] = normalized
            return self.config_manager.save()
        return False

    def get_alarm_volume(self):
        volume = self.get("alarm_sound", "volume", 70)
        normalized = normalize_alarm_volume(volume)
        if normalized != volume and self.config_manager:
            self.config_manager.config.setdefault("alarm_sound", {})["volume"] = normalized
            self.config_manager.save()
        return normalized

    def set_alarm_volume(self, volume):
        normalized = normalize_alarm_volume(volume)
        if self.config_manager:
            self.config_manager.config.setdefault("alarm_sound", {})["volume"] = normalized
            return self.config_manager.save()
        return False


# ====== WEB SERVER ======

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alarmklok (Lite)</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 16px; background: #f4f7fb; }
        .card { background: #fff; border-radius: 10px; padding: 14px; margin-bottom: 12px; }
        h2 { margin: 0 0 8px 0; }
        label { display: block; margin-top: 8px; font-weight: bold; }
        input, select, button { width: 100%; padding: 10px; margin-top: 6px; box-sizing: border-box; }
        .time { font-size: 34px; text-align: center; color: #1f6fd6; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Alarmklok Lite</h2>
        <div class="time" id="t">--:--:--</div>
        <div id="d"></div>
    </div>

    <div class="card">
        <label>Tijd</label>
        <input type="time" id="time" value="12:00">
        <label>Seconde</label>
        <input type="number" id="sec" min="0" max="59" value="0">
        <button onclick="setTime()">Stel Tijd In</button>
    </div>

    <div class="card">
        <label>Tijdzone</label>
        <select id="tz">
            <option value="Europe/Amsterdam">Europe/Amsterdam</option>
            <option value="UTC">UTC</option>
            <option value="UTC+1">UTC+1</option>
            <option value="UTC+2">UTC+2</option>
            <option value="UTC-1">UTC-1</option>
        </select>
        <button onclick="saveTimezone()">Sla Tijdzone Op</button>
        <button onclick="syncNtp()">Sync Met NTP</button>
    </div>

    <div class="card">
        <label>Alarm geluid</label>
        <select id="tone"></select>
        <label>Volume %</label>
        <input type="number" id="vol" min="0" max="100" value="70">
        <label>Testduur sec</label>
        <input type="number" id="dur" min="1" max="60" value="10">
        <button onclick="saveAlarm()">Sla Alarminstellingen Op</button>
        <button onclick="testAlarm()">Test Alarm</button>
    </div>

    <script>
        function refresh() {
            fetch('/api/time').then(r => r.json()).then(data => {
                document.getElementById('t').textContent = `${String(data.hour).padStart(2,'0')}:${String(data.minute).padStart(2,'0')}:${String(data.second).padStart(2,'0')}`;
                document.getElementById('d').textContent = `${data.weekday_name} ${String(data.day).padStart(2,'0')}-${String(data.month).padStart(2,'0')}-${data.year} (${data.timezone_label})`;
                document.getElementById('time').value = `${String(data.hour).padStart(2,'0')}:${String(data.minute).padStart(2,'0')}`;
                document.getElementById('sec').value = data.second;
                document.getElementById('tz').value = data.timezone_name || 'Europe/Amsterdam';
                const tone = document.getElementById('tone');
                const current = tone.value;
                tone.innerHTML = (data.alarm_tones || []).map(t => `<option value="${t.key}">${t.label}</option>`).join('');
                tone.value = data.alarm_tone || current || 'classic';
                document.getElementById('vol').value = data.alarm_volume ?? 70;
            });
        }
        function setTime(){
            const [hour, minute] = document.getElementById('time').value.split(':').map(Number);
            const second = Number(document.getElementById('sec').value || 0);
            fetch('/api/set-time',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hour,minute,second})});
            setTimeout(refresh, 300);
        }
        function saveTimezone(){
            const timezone = document.getElementById('tz').value;
            fetch('/api/set-timezone',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({timezone})});
            setTimeout(refresh, 500);
        }
        function saveAlarm(){
            const tone = document.getElementById('tone').value;
            const volume = Number(document.getElementById('vol').value || 70);
            fetch('/api/set-alarm-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tone,volume})});
            setTimeout(refresh, 300);
        }
        function testAlarm(){
            const seconds = Number(document.getElementById('dur').value || 10);
            fetch('/api/test-alarm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seconds})});
        }
        function syncNtp(){
            fetch('/api/sync-ntp',{method:'POST',headers:{'Content-Type':'application/json'}});
            setTimeout(refresh, 500);
        }
        refresh();
        setInterval(refresh, 1000);
    </script>
</body>
</html>
"""

HTML_PAGE_MIN = HTML_PAGE

HTML_PAGE = HTML_PAGE_MIN
LOW_MEMORY_WEB_MODE = True
gc.collect()


def enable_low_memory_web_mode():
        global HTML_PAGE, LOW_MEMORY_WEB_MODE
        if LOW_MEMORY_WEB_MODE:
                return
        HTML_PAGE = HTML_PAGE_MIN
        LOW_MEMORY_WEB_MODE = True
        gc.collect()


class WebServer:
    def __init__(self, rtc, config, display=None, alarm_controller=None):
        self.rtc = rtc
        self.config = config
        self.display = display
        self.alarm_controller = alarm_controller
        self.server_socket = None
        self.running = False
    
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('0.0.0.0', WIFI_PORT))
        self.server_socket.listen(5)
        
        self.running = True
        print(f"Web server gestart op http://192.168.X.X")

    def _json_response(self, payload, status="200 OK"):
        return "HTTP/1.1 {}\r\nContent-Type: application/json\r\n\r\n{}".format(status, json.dumps(payload))

    def _send_html_page(self, client_socket):
        # Verstuur HTML in kleine brokken om RAM pieken te voorkomen op MicroPython.
        header = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
        client_socket.send(header.encode())
        chunk_size = 384
        page_len = len(HTML_PAGE)
        index = 0
        while index < page_len:
            client_socket.send(HTML_PAGE[index:index + chunk_size].encode())
            index += chunk_size

    def _recv_http_request(self, client_socket):
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 4096:
            chunk = client_socket.recv(512)
            if not chunk:
                break
            data += chunk

        if b"\r\n\r\n" in data:
            header_bytes, body_bytes = data.split(b"\r\n\r\n", 1)
            content_length = 0
            for line in header_bytes.split(b"\r\n"):
                low = line.lower()
                if low.startswith(b"content-length:"):
                    try:
                        content_length = int(line.split(b":", 1)[1].strip())
                    except:
                        content_length = 0
                    break

            while len(body_bytes) < content_length and len(data) < 8192:
                chunk = client_socket.recv(min(512, content_length - len(body_bytes)))
                if not chunk:
                    break
                data += chunk
                body_bytes += chunk

        return data.decode("utf-8", "ignore")

    def _read_json_body(self, request):
        parts = request.split('\r\n\r\n', 1)
        if len(parts) < 2 or not parts[1]:
            return {}
        return json.loads(parts[1])
    
    def handle_request(self, client_socket):
        try:
            gc.collect()
            request = self._recv_http_request(client_socket)
            request_line = request.split('\r\n', 1)[0]
            
            if "GET / HTTP/" in request_line:
                self._send_html_page(client_socket)

            elif "GET /favicon.ico " in request_line:
                client_socket.send("HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n".encode())
            
            elif "GET /api/time " in request_line:
                current_time = self.rtc.read_time()
                schedule = self.config.get_alarm_schedule()
                weekday = current_time[6]
                data = {
                    "year": current_time[0],
                    "month": current_time[1],
                    "day": current_time[2],
                    "hour": current_time[3],
                    "minute": current_time[4],
                    "second": current_time[5],
                    "weekday": weekday,
                    "weekday_name": day_key_to_name(weekday_to_day_key(weekday)),
                    "timezone_name": self.rtc.get_timezone_name(),
                    "timezone_label": self.rtc.get_timezone_label(),
                    "alarm_tone": self.config.get_alarm_tone(),
                    "alarm_volume": self.config.get_alarm_volume(),
                    "alarm_tones": get_alarm_tone_options(),
                    "schedule": schedule
                }
                response = self._json_response(data)
                client_socket.send(response.encode())

            elif "POST /api/set-timezone " in request_line:
                data = self._read_json_body(request)
                timezone_name = data.get("timezone", "Europe/Amsterdam")
                self.rtc.set_timezone(timezone_name)
                if self.rtc.wlan and self.rtc.wlan.isconnected():
                    self.rtc.sync_ntp(force=True)
                saved = self.config.set("ntp", "timezone", timezone_name)
                response = self._json_response({
                    "status": "ok" if saved else "warn",
                    "ok": True,
                    "saved": bool(saved),
                    "timezone": self.rtc.get_timezone_name(),
                })
                client_socket.send(response.encode())
                print("Tijdzone bijgewerkt:", timezone_name)
            
            elif "POST /api/set-time " in request_line:
                data = self._read_json_body(request)
                
                current_time = self.rtc.read_time()
                second = int(data.get('second', 0)) % 60
                success = self.rtc.set_time(current_time[0], current_time[1], current_time[2],
                                            int(data['hour']) % 24, int(data['minute']) % 60, second)
                
                response = self._json_response({"status": "ok" if success else "error", "ok": bool(success)})
                client_socket.send(response.encode())
                print(f"Tijd ingesteld: {int(data['hour']) % 24:02d}:{int(data['minute']) % 60:02d}:{second:02d}")
            
            elif "POST /api/set-alarm-schedule " in request_line:
                data = self._read_json_body(request)
                schedule = data.get("schedule", {})
                success = self.config.set_alarm_schedule(schedule)
                response = self._json_response({"status": "ok" if success else "error", "ok": bool(success)})
                client_socket.send(response.encode())
                print("Weekschema bijgewerkt")

            elif "POST /api/sync-ntp " in request_line:
                success = self.rtc.sync_ntp(force=True)
                response = self._json_response({"status": "ok" if success else "error", "ok": bool(success)})
                client_socket.send(response.encode())
                print("NTP synchronisatie handmatig gestart")

            elif "POST /api/set-alarm-settings " in request_line:
                data = self._read_json_body(request)
                tone_name = data.get("tone", "classic")
                volume = data.get("volume", 70)
                normalized_tone = normalize_alarm_tone(tone_name)
                normalized_volume = normalize_alarm_volume(volume)
                if self.alarm_controller:
                    self.alarm_controller.set_alarm_tone(normalized_tone)
                    self.alarm_controller.set_alarm_volume(normalized_volume)
                saved_tone = self.config.set_alarm_tone(normalized_tone)
                saved_volume = self.config.set_alarm_volume(normalized_volume)
                response = self._json_response({
                    "status": "ok" if (saved_tone and saved_volume) else "warn",
                    "ok": True,
                    "saved": bool(saved_tone and saved_volume),
                    "tone": normalized_tone,
                    "volume": normalized_volume,
                })
                client_socket.send(response.encode())
                print("Alarminstellingen bijgewerkt:", normalized_tone, normalized_volume)

            elif "POST /api/test-alarm " in request_line:
                data = self._read_json_body(request)
                seconds = int(data.get("seconds", 10))
                success = False
                if self.alarm_controller:
                    success = self.alarm_controller.trigger_test_alarm(seconds)
                response = self._json_response({"status": "ok" if success else "error", "ok": bool(success)})
                client_socket.send(response.encode())
                print("Alarm test gestart (sec):", seconds)
                
            else:
                response = "HTTP/1.1 404 Not Found\r\n\r\n"
                client_socket.send(response.encode())
        
        except Exception as e:
            print(f"Fout bij request: {e}")
            gc.collect()
        
        finally:
            client_socket.close()
    
    def run_server(self):
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                self.handle_request(client_socket)
            except Exception as e:
                print(f"Server fout: {e}")


# ====== HOOFDAPPLICATIE ======

class AlarmClock:
    def __init__(self):
        print("\n=== ESP32 ALARMKLOK OPSTARTEN ===\n")
        self.web_server = None
        self.wifi_connected = False
        self.alarm_tone = "classic"
        self.active_alarm_tone = "classic"
        self.alarm_volume = 70
        self.alarm_test_until = None
        self.alarm_edit_mode = False
        self.alarm_edit_hour = 7
        self.alarm_edit_minute = 0
        self.alarm_edit_day_key = "mon"
        self.mario_x = -MARIO_SPRITE_WIDTH
        self.mario_frame_idx = 0
        self.mario_last_ms = time.ticks_ms()
        
        self.i2c = init_i2c()
        devices = scan_i2c_devices(self.i2c)
        print("I2C apparaten:", devices)
        if 0x68 not in devices:
            print("! RTC (0x68) niet gedetecteerd - klok gebruikt systeemtijd")
        self.display = init_display(self.i2c)
        
        if self.display:
            self.display.fill(0)
            self.display.text("OPSTARTEN...", 20, 25)
            self.display.show()
        
        # Laad configuratie
        if ConfigManager:
            config_manager = ConfigManager("config.json")
            print(f"âœ“ Config geladen")
        else:
            config_manager = None
        
        self.config = AlarmConfig(config_manager)
        self.config.get_alarm_schedule()
        self.alarm_tone = self.config.get_alarm_tone()
        self.alarm_volume = self.config.get_alarm_volume()
        
        # Config
        wifi_ssid = self.config.get("wifi", "ssid", "SL2")
        wifi_password = self.config.get("wifi", "password", "anuslikker101")
        ntp_enabled = self.config.get("ntp", "enabled", True)
        ntp_server = self.config.get("ntp", "server", "pool.ntp.org")
        ntp_interval = self.config.get("ntp", "sync_interval", 3600)
        timezone_name = self.config.get("ntp", "timezone", "Europe/Amsterdam")

        # RTC en basis hardware altijd initialiseren, ook zonder WiFi
        self.rtc = DS3231(self.i2c, enable_ntp=ntp_enabled, wlan=None, ntp_server=ntp_server, sync_interval=ntp_interval, timezone_name=timezone_name)
        if not self.rtc.has_hardware():
            print("! DS3231 niet bereikbaar op I2C (0x68)")

        # Knoppen: D14 set/toggle/save, D13 uur+, D12 minuut+
        self.btn_up = Pin(UP_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.btn_down = Pin(DOWN_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self.btn_set = Pin(SET_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
        self._button_state = {
            "set": {"pressed": False, "start": 0, "long": False, "last_edge": 0},
            "up": {"pressed": False, "start": 0, "long": False, "last_edge": 0},
            "down": {"pressed": False, "start": 0, "long": False, "last_edge": 0},
        }

        # Buzzer
        buzzer_volume = self.config.get("buzzer", "volume", 500)
        self.buzzer = PWM(Pin(BUZZER_PIN))
        self.buzzer.freq(buzzer_volume)
        self.buzzer.duty(0)

        self.alarm_ringing = False

        # Verbind met WiFi
        if wifi_ssid == "AlarmClock":
            print("! Waarschuwing: SSID staat op default 'AlarmClock'")
            print("! Upload of controleer config.json op de ESP32")
        
        if WIFI_MANAGER_IMPORT_ERROR:
            print("! Externe wifi_manager import mislukt:", WIFI_MANAGER_IMPORT_ERROR)
            print("! Ingebouwde WiFiManager fallback wordt gebruikt")

        try:
            gc.collect()
            self.wifi_manager = WiFiManager(wifi_ssid, wifi_password)
        except Exception as e:
            if "Out of Memory" in str(e) and not LOW_MEMORY_WEB_MODE:
                print("! Geheugentekort bij WiFi init, schakel over naar Lite webinterface")
                enable_low_memory_web_mode()
                try:
                    gc.collect()
                    self.wifi_manager = WiFiManager(wifi_ssid, wifi_password)
                except Exception as e2:
                    self.wifi_manager = None
                    self.wifi_connected = False
                    print("âœ— WiFi initialisatie mislukt:", e2)
                    print("  â†’ Herstart ESP32 (power cycle) en probeer opnieuw")
                    print("  â†’ Verwijder ongebruikte modules van het device voor meer geheugen")
                    if self.display:
                        self.display.fill(0)
                        self.display.text("WiFi init FOUT", 8, 20)
                        self.display.text("Power cycle", 20, 40)
                        self.display.show()
                    return
            else:
                self.wifi_manager = None
                self.wifi_connected = False
                print("âœ— WiFi initialisatie mislukt:", e)
                print("  â†’ Herstart ESP32 (power cycle) en probeer opnieuw")
                print("  â†’ Verwijder ongebruikte modules van het device voor meer geheugen")
                if self.display:
                    self.display.fill(0)
                    self.display.text("WiFi init FOUT", 8, 20)
                    self.display.text("Power cycle", 20, 40)
                    self.display.show()
                return

        self.wifi_connected = self.wifi_manager.connect()
        if not self.wifi_connected:
            print("âœ— WiFi verbinding mislukt!")
            print("  â†’ Controleer SSID en wachtwoord")
            print("  â†’ Check config.json")
            if self.display:
                self.display.fill(0)
                self.display.text("WiFi FOUT!", 25, 20)
                self.display.text("Check config", 10, 40)
                self.display.show()
            return
        
        # RTC koppelen aan actieve WLAN voor NTP checks
        sta = network.WLAN(network.STA_IF)
        self.rtc.wlan = sta
        
        # Sync NTP
        if ntp_enabled and self.wifi_manager and self.wifi_manager.is_connected():
            print("â†’ NTP synchroniseren...")
            self.rtc.sync_ntp(force=True)
        
        # Web Server
        self.web_server = WebServer(self.rtc, self.config, self.display, alarm_controller=self)
        self.web_server.start()
        
        # Display IP adres
        if self.display and self.wifi_manager:
            ip = self.wifi_manager.get_ip()
            if ip:
                print(f"\nâœ“ Open in browser: http://{ip}\n")
    
    def _current_day_alarm(self):
        current_time = self.rtc.read_time()
        day_key = weekday_to_day_key(current_time[6])
        schedule = self.config.get_alarm_schedule()
        row = schedule.get(day_key, {"enabled": False, "hour": 7, "minute": 0})
        return day_key, schedule, row

    def _toggle_today_alarm(self):
        day_key, schedule, row = self._current_day_alarm()
        enabled = not bool(row.get("enabled", False))
        row["enabled"] = enabled
        schedule[day_key] = {
            "enabled": bool(row.get("enabled", False)),
            "hour": int(row.get("hour", 7)) % 24,
            "minute": int(row.get("minute", 0)) % 60,
        }
        self.config.set_alarm_schedule(schedule)
        state = "AAN" if enabled else "UIT"
        print("Alarm {}: {:02d}:{:02d}".format(state, schedule[day_key]["hour"], schedule[day_key]["minute"]))

    def _enter_alarm_edit_mode(self):
        day_key, _schedule, row = self._current_day_alarm()
        self.alarm_edit_mode = True
        self.alarm_edit_day_key = day_key
        self.alarm_edit_hour = int(row.get("hour", 7)) % 24
        self.alarm_edit_minute = int(row.get("minute", 0)) % 60
        print("Alarm instellen: {:02d}:{:02d}".format(self.alarm_edit_hour, self.alarm_edit_minute))

    def _save_alarm_edit_mode(self):
        schedule = self.config.get_alarm_schedule()
        schedule[self.alarm_edit_day_key] = {
            "enabled": True,
            "hour": int(self.alarm_edit_hour) % 24,
            "minute": int(self.alarm_edit_minute) % 60,
        }
        self.config.set_alarm_schedule(schedule)
        self.alarm_edit_mode = False
        print("Alarm opgeslagen: {} {:02d}:{:02d}".format(self.alarm_edit_day_key, self.alarm_edit_hour, self.alarm_edit_minute))

    def _set_short_press(self):
        if self.alarm_ringing:
            self.stop_alarm()
            return
        if self.alarm_edit_mode:
            return
        self._toggle_today_alarm()

    def _set_long_press(self):
        if self.alarm_ringing:
            self.stop_alarm()
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

    def _process_button(self, name, pin, short_cb=None, long_cb=None):
        state = self._button_state[name]
        now = time.ticks_ms()
        pressed = (pin.value() == 0)

        if pressed and not state["pressed"]:
            if time.ticks_diff(now, state["last_edge"]) < 120:
                return
            state["pressed"] = True
            state["start"] = now
            state["long"] = False
            state["last_edge"] = now
            return

        if pressed and state["pressed"]:
            if long_cb and (not state["long"]) and time.ticks_diff(now, state["start"]) >= 2000:
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
        self._process_button("down", self.btn_down, short_cb=self._down_short_press)
    
    def ring_alarm(self):
        self.alarm_ringing = True
        self.active_alarm_tone = self._resolve_alarm_tone_for_today()
        self._play_alarm_tone(0)
    
    def stop_alarm(self):
        self.buzzer.duty(0)
        self.alarm_ringing = False
        self.alarm_test_until = None

    def set_alarm_tone(self, tone_name):
        self.alarm_tone = normalize_alarm_tone(tone_name)
        if not self.alarm_ringing:
            self.active_alarm_tone = self.alarm_tone

    def set_alarm_volume(self, volume):
        self.alarm_volume = normalize_alarm_volume(volume)

    def trigger_test_alarm(self, seconds):
        try:
            test_seconds = int(seconds)
        except:
            test_seconds = 10

        if test_seconds < 1:
            test_seconds = 1
        if test_seconds > 60:
            test_seconds = 60

        self.ring_alarm()
        self.alarm_test_until = time.ticks_add(time.ticks_ms(), test_seconds * 1000)
        return True

    def _resolve_alarm_tone_for_today(self):
        selected = normalize_alarm_tone(self.alarm_tone)
        if selected != ALARM_RANDOM_KEY:
            return selected

        current_time = self.rtc.read_time()
        year, month, day = current_time[0], current_time[1], current_time[2]
        seed = (year * 372) + (month * 31) + day
        idx = seed % len(RETRO_TONE_KEYS)
        return RETRO_TONE_KEYS[idx]

    def _play_alarm_tone(self, frame):
        tone_name = normalize_alarm_tone(self.active_alarm_tone)
        if tone_name == ALARM_RANDOM_KEY:
            tone_name = self._resolve_alarm_tone_for_today()
        tone_def = ALARM_TONES.get(tone_name, ALARM_TONES["classic"])
        pattern = tone_def.get("pattern")
        if pattern is None:
            song_text = tone_def.get("rtttl") or tone_def.get("rttl")
            if song_text:
                pattern = _parse_rtttl_pattern(tone_name, song_text)
        if pattern is None:
            pattern = ALARM_TONES["classic"]["pattern"]

        total_frames = 0
        for _freq, _duty, duration in pattern:
            total_frames += duration

        if total_frames <= 0:
            self.buzzer.duty(0)
            return

        position = frame % total_frames
        elapsed = 0
        for freq, duty, duration in pattern:
            elapsed += duration
            if position < elapsed:
                if duty <= 0 or freq <= 0:
                    self.buzzer.duty(0)
                else:
                    scaled_duty = int((int(duty) * self.alarm_volume) / 100)
                    if scaled_duty < 0:
                        scaled_duty = 0
                    if scaled_duty > 1023:
                        scaled_duty = 1023
                    self.buzzer.freq(freq)
                    self.buzzer.duty(scaled_duty)
                return

        self.buzzer.duty(0)

    def _update_mario_animation(self):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.mario_last_ms) < MARIO_ANIM_INTERVAL_MS:
            return

        self.mario_last_ms = now
        self.mario_x += MARIO_ANIM_STEP_PIXELS
        if self.mario_x > WIDTH:
            self.mario_x = -MARIO_SPRITE_WIDTH
        self.mario_frame_idx = (self.mario_frame_idx + 1) % len(MARIO_FRAMES)

    def _draw_mario_animation(self):
        if not self.display:
            return

        frame_rows = MARIO_FRAMES[self.mario_frame_idx]
        for row in range(MARIO_SPRITE_HEIGHT):
            row_bits = frame_rows[row]
            y = MARIO_SPRITE_Y + row
            if y < 0 or y >= HEIGHT:
                continue

            for col in range(MARIO_SPRITE_WIDTH):
                if row_bits[col] != '1':
                    continue
                x = self.mario_x + col
                if 0 <= x < WIDTH:
                    self.display.pixel(x, y, 1)
    
    def check_alarm(self):
        current_time = self.rtc.read_time()
        hour = current_time[3]
        minute = current_time[4]
        day_key = weekday_to_day_key(current_time[6])
        day_alarm = self.config.get_alarm_schedule().get(day_key, {})
        
        if not day_alarm.get("enabled", False):
            return

        alarm_hour = day_alarm.get("hour", 7)
        alarm_minute = day_alarm.get("minute", 0)
        
        if hour == alarm_hour and minute == alarm_minute and not self.alarm_ringing:
            self.ring_alarm()
    
    def draw_display(self):
        if not self.display:
            return

        if self.alarm_edit_mode:
            self.display.fill(0)
            self.display.text("ALARM INSTELLEN", 4, 4, 1)
            self.display.text("{:02d}:{:02d}".format(self.alarm_edit_hour, self.alarm_edit_minute), 34, 24, 1)
            self.display.text("D13=UUR+", 6, 42, 1)
            self.display.text("D12=MIN+", 66, 42, 1)
            self.display.text("Houd D14 2s op", 6, 54, 1)
            self.display.show()
            return

        self._update_mario_animation()
        
        self.display.fill(0)
        
        current_time = self.rtc.read_time()
        hour, minute, second = current_time[3], current_time[4], current_time[5]
        weekday_name = day_key_to_name(weekday_to_day_key(current_time[6]))
        
        time_str = f"{hour:02d}:{minute:02d}"
        self.display.text(time_str, 30, 20, 1)
        self.display.text(f"{second:02d}s", 100, 25, 1)
        self.display.text(weekday_name[:8], 5, 2, 1)
        
        day_key = weekday_to_day_key(current_time[6])
        day_alarm = self.config.get_alarm_schedule().get(day_key, {})
        if day_alarm.get("enabled", False):
            # Klein wekker-icoon + alarmtijd zichtbaar in normale stand.
            self.display.rect(2, 40, 8, 8, 1)
            self.display.pixel(3, 39, 1)
            self.display.pixel(8, 39, 1)
            self.display.text(f"{day_alarm.get('hour', 7):02d}:{day_alarm.get('minute', 0):02d}", 14, 40, 1)
        
        if self.wifi_manager and self.wifi_manager.is_connected():
            ip = self.wifi_manager.get_ip()
            if ip:
                # Toon alleen laatste deel van IP
                ip_short = ip.split('.')[-1]
                self.display.text(f"WiFi: {ip_short}", 15, 50, 1)
        else:
            self.display.text("WiFi GEEN VERBINDING", 5, 50, 1)

        self._draw_mario_animation()
        
        self.display.show()
    
    def draw_alarm_ringing(self):
        if not self.display:
            return
        
        self.display.fill(0)
        self.display.text("ALARM AFGAAN!", 25, 20, 1)
        self.display.text("SET = UITZETTEN", 15, 40, 1)
        self.display.show()
    
    def run(self):
        print("Alarmklok draait!\n")
        
        # Start server in achtergrond als WiFi beschikbaar is
        if self.web_server:
            import _thread
            _thread.start_new_thread(self.web_server.run_server, ())
        else:
            print("Webserver uitgeschakeld (geen WiFi verbinding)")
        
        frame = 0
        while True:
            try:
                self._handle_buttons()
                self.check_alarm()

                if self.alarm_ringing and self.alarm_test_until is not None:
                    if time.ticks_diff(time.ticks_ms(), self.alarm_test_until) >= 0:
                        self.stop_alarm()
                
                if self.alarm_ringing:
                    self.draw_alarm_ringing()
                    self._play_alarm_tone(frame)
                else:
                    self.draw_display()
                
                # NTP sync elke uur
                if frame % 18000 == 0:  # 3600 seconden = 1 uur
                    if self.config.get("ntp", "enabled", True) and self.wifi_manager and self.wifi_manager.is_connected():
                        self.rtc.sync_ntp(force=True)
                
                frame += 1
                time.sleep(0.2)
            
            except Exception as e:
                print(f"Fout in main loop: {e}")
                time.sleep(1)


# ====== MAIN ======

if __name__ == "__main__":
    try:
        clock = AlarmClock()
        clock.run()
    except Exception as e:
        print(f"Fatale fout: {e}")
        try:
            import sys
            sys.print_exception(e)
        except:
            pass


