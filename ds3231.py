"""
DS3231 RTC driver voor MicroPython
I2C adres: 0x68

AT24C32 EEPROM driver (op DS3231-module meegebakken)
I2C adres: 0x57 — 4KB opslag, overleeft reflash van MicroPython

Bedrading (ESP32-S3 DevKitC-1):
  SDA → GPIO8   (gedeeld met OLED)
  SCL → GPIO9   (gedeeld met OLED)
  VCC → 3.3V
  GND → GND
"""

import time


_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_MAGIC_0  = 0xA7  # verhoogd t.o.v. eerdere versies om corrupte data te detecteren
_MAGIC_1  = 0x5C
# Geheugenindeling (adres 0):
#   [0]   magic byte 0
#   [1]   magic byte 1
#   [2..22] 7 dagen × 3 bytes: enabled(0/1), hour, minute


class AT24C32:
    """AT24C32 EEPROM — 4KB, I2C adres 0x57."""
    ADDR = 0x57

    def __init__(self, i2c):
        self._i2c = i2c
        if self.ADDR not in i2c.scan():
            raise OSError("AT24C32 niet gevonden op I2C adres 0x57")

    def _write_page(self, addr, data):
        """Schrijf maximaal 32 bytes naar één pagina."""
        buf = bytes([(addr >> 8) & 0xFF, addr & 0xFF]) + bytes(data)
        self._i2c.writeto(self.ADDR, buf)
        time.sleep_ms(10)  # write-cycle wachttijd

    def read(self, addr, n):
        """Lees n bytes vanaf adres."""
        self._i2c.writeto(self.ADDR, bytes([(addr >> 8) & 0xFF, addr & 0xFF]))
        return self._i2c.readfrom(self.ADDR, n)

    # ---- Alarmschema opslaan / laden ----

    def save_alarm_schedule(self, schedule):
        """Sla alarmschema op in EEPROM. schedule = dict met keys mon..sun."""
        buf = bytearray(2 + 7 * 3)
        buf[0] = _MAGIC_0
        buf[1] = _MAGIC_1
        for i, key in enumerate(_DAY_KEYS):
            day = schedule.get(key, {"enabled": False, "hour": 7, "minute": 0})
            buf[2 + i * 3]     = 1 if day.get("enabled", False) else 0
            buf[2 + i * 3 + 1] = int(day.get("hour", 7)) % 24
            buf[2 + i * 3 + 2] = int(day.get("minute", 0)) % 60
        self._write_page(0, buf)

    def load_alarm_schedule(self):
        """Laad alarmschema uit EEPROM. Geeft None als er geen geldige data is."""
        try:
            data = self.read(0, 2 + 7 * 3)
        except Exception:
            return None
        if data[0] != _MAGIC_0 or data[1] != _MAGIC_1:
            return None
        schedule = {}
        for i, key in enumerate(_DAY_KEYS):
            offset = 2 + i * 3
            schedule[key] = {
                "enabled": bool(data[offset]),
                "hour":    int(data[offset + 1]),
                "minute":  int(data[offset + 2]),
            }
        return schedule

class DS3231:
    ADDR = 0x68

    def __init__(self, i2c):
        self._i2c = i2c
        if self.ADDR not in i2c.scan():
            raise OSError("DS3231 niet gevonden op I2C adres 0x68")

    # ---- BCD helpers ----
    @staticmethod
    def _bcd2dec(bcd):
        return (bcd >> 4) * 10 + (bcd & 0x0F)

    @staticmethod
    def _dec2bcd(dec):
        return ((dec // 10) << 4) | (dec % 10)

    # ---- publieke API ----

    def datetime(self):
        """Lees tijd. Geeft tuple (jaar, maand, dag, uur, minuut, seconde, weekdag)
        weekdag: 1=maandag … 7=zondag"""
        buf = self._i2c.readfrom_mem(self.ADDR, 0x00, 7)
        sec  = self._bcd2dec(buf[0] & 0x7F)
        min_ = self._bcd2dec(buf[1] & 0x7F)
        hr   = self._bcd2dec(buf[2] & 0x3F)
        wd   = buf[3] & 0x07          # 1–7
        day  = self._bcd2dec(buf[4] & 0x3F)
        mon  = self._bcd2dec(buf[5] & 0x1F)
        yr   = self._bcd2dec(buf[6]) + 2000
        return (yr, mon, day, hr, min_, sec, wd)

    def set_datetime(self, year, month, day, hour, minute, second, weekday=1):
        """Schrijf tijd naar DS3231.
        weekday: 1=maandag … 7=zondag"""
        buf = bytes([
            self._dec2bcd(second),
            self._dec2bcd(minute),
            self._dec2bcd(hour),
            weekday & 0x07,
            self._dec2bcd(day),
            self._dec2bcd(month),
            self._dec2bcd(year - 2000),
        ])
        self._i2c.writeto_mem(self.ADDR, 0x00, buf)

    def temperature(self):
        """Geeft interne temperatuur van de DS3231 in graden Celsius (float)."""
        buf = self._i2c.readfrom_mem(self.ADDR, 0x11, 2)
        msb = buf[0]
        frac = (buf[1] >> 6) * 0.25
        if msb & 0x80:          # negatief getal
            msb = msb - 256
        return msb + frac
