"""
NTP Time Sync Module voor Nederlandse Tijd (CET/CEST)
Synchroniseer ESP32 klok met internet, inclusief zomer/wintertijd
"""

import time
import machine
import network

class NTPTimeSync:
    """NTP Client voor Nederlandse Tijdzone (UTC+1 / UTC+2)"""
    
    # NTP Server
    NTP_SERVER = "pool.ntp.org"
    NTP_TIMEOUT = 5000  # ms
    
    def __init__(self, ssid=None, password=None):
        """
        ssid: WiFi SSID (optional, voor WiFi versie)
        password: WiFi password
        """
        self.ssid = ssid
        self.password = password
        self.synced = False
    
    def connect_wifi(self):
        """Verbind met WiFi (alleen nodig voor Bluetooth versie)"""
        if not self.ssid or not self.password:
            return False
        
        wlan = network.WLAN(network.STA_IF)
        if wlan.isconnected():
            return True
        
        print("Verbinden met WiFi...")
        wlan.active(True)
        wlan.connect(self.ssid, self.password)
        
        # Wacht op verbinding (max 10 seconden)
        for i in range(20):
            if wlan.isconnected():
                print(f"✓ WiFi verbonden: {self.ssid}")
                return True
            time.sleep(0.5)
        
        print("✗ WiFi verbinding mislukt")
        return False
    
    def sync_time(self):
        """Synchroniseer tijd via NTP"""
        try:
            # Voor WiFi: gebruik bestaande verbinding
            # Voor Bluetooth: maak WiFi verbinding
            import ntptime
            
            print("NTP tijd synchroniseren...")
            ntptime.host = self.NTP_SERVER
            ntptime.settime()
            
            self.synced = True
            print("✓ NTP synchronisatie succesvol")
            
            # Update RTC met gesynchroniseerde tijd
            return True
        
        except Exception as e:
            print(f"✗ NTP fout: {e}")
            return False
    
    @staticmethod
    def get_ntp_time(server=NTP_SERVER):
        """Haal NTP tijd direct op"""
        try:
            import ntptime
            ntptime.host = server
            ntptime.settime()
            return True
        except:
            return False
    
    @staticmethod
    def is_dst(year, month, day):
        """
        Bepaal of het zomer- of wintertijd is in Nederland
        
        Nederland:
        - Zomertijd: Laatste zondag van maart tot laatste zondag van oktober
        - Wintertijd: Alle andere periode
        """
        
        # Laatste zondag van maart (zomertijd start)
        if month < 3:
            return False
        elif month > 10:
            return False
        
        # Maanden duidelijk in zomer- of wintertijd
        if 3 < month < 10:
            return True
        
        # Maart: check of na laatste zondag
        if month == 3:
            last_sunday = NTPTimeSync.get_last_sunday_of_month(year, 3)
            return day >= last_sunday
        
        # Oktober: check of voor laatste zondag
        if month == 10:
            last_sunday = NTPTimeSync.get_last_sunday_of_month(year, 10)
            return day < last_sunday
        
        return False
    
    @staticmethod
    def get_last_sunday_of_month(year, month):
        """Bepaal datum van laatste zondag van maand"""
        # Bepaal aantal dagen in maand
        if month in (1, 3, 5, 7, 8, 10, 12):
            last_day = 31
        elif month in (4, 6, 9, 11):
            last_day = 30
        else:  # Februari
            last_day = 29 if NTPTimeSync.is_leap_year(year) else 28
        
        # Werk terug van laatste dag tot zondag
        for day in range(last_day, 0, -1):
            # Bepaal weekdag (0=Maandag, 6=Zondag)
            weekday = NTPTimeSync.get_weekday(year, month, day)
            if weekday == 6:  # Zondag
                return day
        
        return last_day
    
    @staticmethod
    def is_leap_year(year):
        """Check of jaar schrikkeljaar is"""
        return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    
    @staticmethod
    def get_weekday(year, month, day):
        """
        Bepaal weekdag (0=Maandag, 6=Zondag)
        Zeller's congruence algorithm
        """
        if month < 3:
            month += 12
            year -= 1
        
        q = day
        m = month
        k = year % 100
        j = year // 100
        
        h = (q + ((13 * (m + 1)) // 5) + k + (k // 4) + (j // 4) - (2 * j)) % 7
        
        # h: 0=Sat, 1=Sun, ..., 6=Fri
        # Converteer naar: 0=Mon, 1=Tue, ..., 6=Sun
        weekday = (h + 5) % 7
        return weekday
    
    @staticmethod
    def get_dutch_time(year, month, day, hour, minute, second):
        """
        Converteer UTC tijd naar Nederlandse lokale tijd (CET/CEST)
        
        Return: (year, month, day, hour, minute, second)
        """
        
        # Bepaal offset (zomertijd +2, wintertijd +1)
        if NTPTimeSync.is_dst(year, month, day):
            offset = 2  # CEST (UTC+2)
        else:
            offset = 1  # CET (UTC+1)
        
        # Voeg offset toe
        hour += offset
        
        # Handle dag-overstap
        if hour >= 24:
            hour -= 24
            day += 1
            
            # Handle maand-overstap
            days_in_month = (31, 29 if NTPTimeSync.is_leap_year(year) else 28,
                           31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
            
            if day > days_in_month[month - 1]:
                day = 1
                month += 1
                if month > 12:
                    month = 1
                    year += 1
        
        return (year, month, day, hour, minute, second)
    
    @staticmethod
    def time_tuple_to_dutch(time_tuple):
        """Converteer time.gmtime() naar Nederlandse tijd"""
        # time_tuple format: (year, month, day, hour, minute, second, weekday, yearday)
        year, month, day, hour, minute, second = time_tuple[:6]
        
        dutch_time = NTPTimeSync.get_dutch_time(year, month, day, hour, minute, second)
        
        # Bereken weekday
        weekday = NTPTimeSync.get_weekday(dutch_time[0], dutch_time[1], dutch_time[2])
        
        return dutch_time + (weekday, time_tuple[7])


class RTCWithNTP:
    """DS3231 RTC wrapper met NTP sync mogelijkheid"""
    
    def __init__(self, i2c, addr=0x68, ntp_sync=None):
        """
        i2c: I2C bus
        addr: DS3231 adres
        ntp_sync: NTPTimeSync object (optional)
        """
        self.i2c = i2c
        self.addr = addr
        self.ntp_sync = ntp_sync
        self.last_sync = 0
        self.sync_interval = 3600  # Elk uur synchroniseren
    
    def read_time(self):
        """Lees huidige tijd van RTC"""
        try:
            data = self.i2c.readfrom(self.addr, 7)
            sec = self._bcd_to_int(data[0])
            minute = self._bcd_to_int(data[1])
            hour = self._bcd_to_int(data[2] & 0x3F)
            day = self._bcd_to_int(data[3])
            month = self._bcd_to_int(data[5] & 0x1F)
            year = self._bcd_to_int(data[6]) + 2000
            weekday = data[4]
            
            return (year, month, day, hour, minute, sec, weekday, 0)
        except:
            return (2024, 1, 1, 0, 0, 0, 1, 0)
    
    def set_time(self, year, month, day, hour, minute, second):
        """Stel RTC tijd in"""
        try:
            data = bytearray(7)
            data[0] = self._int_to_bcd(second)
            data[1] = self._int_to_bcd(minute)
            data[2] = self._int_to_bcd(hour)
            data[3] = self._int_to_bcd(day)
            data[5] = self._int_to_bcd(month)
            data[6] = self._int_to_bcd(year - 2000)
            
            self.i2c.writeto(self.addr, bytes([0x00]) + data)
            return True
        except:
            return False
    
    def sync_ntp(self, force=False):
        """
        Synchroniseer RTC met NTP
        
        force: Forceer sync (anders 1x per uur)
        """
        if not self.ntp_sync:
            return False
        
        current_time = time.time()
        if not force and (current_time - self.last_sync) < self.sync_interval:
            return False  # Niet nodig sync
        
        if self.ntp_sync.sync_time():
            # Haal UTC tijd op
            utc_time = time.gmtime()
            
            # Converteer naar Nederlandse lokale tijd
            dutch_time = NTPTimeSync.time_tuple_to_dutch(utc_time)
            
            # Stel RTC in
            self.set_time(*dutch_time[:6])
            
            self.last_sync = current_time
            print(f"✓ RTC gesynchroniseerd: {dutch_time[3]:02d}:{dutch_time[4]:02d}:{dutch_time[5]:02d}")
            return True
        
        return False
    
    def _bcd_to_int(self, bcd):
        """Zet BCD naar integer"""
        return (bcd >> 4) * 10 + (bcd & 0x0F)
    
    def _int_to_bcd(self, val):
        """Zet integer naar BCD"""
        return ((val // 10) << 4) | (val % 10)


# ====== HELPERS ======

def get_timezone_str(year, month, day):
    """Geef timezone string (CET of CEST)"""
    if NTPTimeSync.is_dst(year, month, day):
        return "CEST"  # Central European Summer Time
    else:
        return "CET"   # Central European Time


def format_time_dutch(time_tuple):
    """Format tijd in Nederlands formaat"""
    year, month, day, hour, minute, second = time_tuple[:6]
    tz = get_timezone_str(year, month, day)
    return f"{hour:02d}:{minute:02d}:{second:02d} ({tz})"


def get_time_info(year, month, day, hour, minute, second):
    """Geef uitgebreide tijdinformatie"""
    
    weekdays_nl = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
    months_nl = ["", "januari", "februari", "maart", "april", "mei", "juni",
                 "juli", "augustus", "september", "oktober", "november", "december"]
    
    weekday = NTPTimeSync.get_weekday(year, month, day)
    tz = get_timezone_str(year, month, day)
    
    return {
        "date": f"{day} {months_nl[month]} {year}",
        "weekday": weekdays_nl[weekday],
        "time": f"{hour:02d}:{minute:02d}:{second:02d}",
        "timezone": tz,
        "formatted": f"{hour:02d}:{minute:02d} op {weekdays_nl[weekday]} {day} {months_nl[month]}"
    }
