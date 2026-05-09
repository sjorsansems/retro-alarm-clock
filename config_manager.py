"""
Config Manager - Laad instellingen uit config.json
"""

import json

class ConfigManager:
    """Beheer alle instellingen vanuit config.json"""
    
    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        self.last_load_error = None
        self.config = self.load()
    
    def load(self):
        """Laad configuratie uit JSON bestand"""
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.last_load_error = str(e)
            if "ENOENT" in str(e) or "not found" in str(e).lower():
                print(f"⚠ {self.config_file} niet gevonden, gebruik defaults")
                defaults = self._get_defaults()
                self._recover_config_file(defaults)
                return defaults

            msg = str(e).lower()
            if "json" in msg or "syntax" in msg or "valueerror" in msg:
                print(f"⚠ Fout bij laden config: {e}")
                print("⚠ config.json is ongeldig en wordt hersteld met defaults")
                defaults = self._get_defaults()
                self._recover_config_file(defaults)
                return defaults

            print(f"⚠ Fout bij laden config: {e}")
            defaults = self._get_defaults()
            self._recover_config_file(defaults)
            return defaults
    
    def save(self):
        """Sla configuratie op naar JSON bestand"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, separators=(',', ':'))
            return True
        except Exception as e:
            print(f"✗ Fout bij opslaan config: {e}")
            return False
    
    def get(self, section, key=None, default=None):
        """
        Haal instelling op
        
        get("wifi", "ssid")       → "AlarmClock"
        get("alarm")              → {"enabled": False, "hour": 7, ...}
        """
        try:
            if section not in self.config:
                return default
            
            if key is None:
                return self.config.get(section, default)
            
            section_data = self.config[section]
            return section_data.get(key, default)
        
        except:
            return default
    
    def set(self, section, key, value):
        """
        Stel instelling in
        
        set("wifi", "ssid", "MijnWiFi")
        set("alarm", "hour", 6)
        """
        try:
            if section not in self.config:
                self.config[section] = {}
            
            self.config[section][key] = value
            return self.save()
        
        except Exception as e:
            print(f"✗ Fout bij instellen {section}.{key}: {e}")
            return False
    
    def _get_defaults(self):
        """Standaard instellingen"""
        return {
            "wifi": {
                "mode": "sta",
                "ssid": "SL2_IOT",
                "password": "anuslikker102",
                "channel": 6
            },
            "ntp": {
                "enabled": True,
                "server": "pool.ntp.org",
                "sync_interval": 3600,
                "timezone": "Europe/Amsterdam"
            },
            "alarm": {
                "enabled": False,
                "hour": 7,
                "minute": 0
            },
            "alarm_schedule": {
                "mon": {"enabled": False, "hour": 7, "minute": 0},
                "tue": {"enabled": False, "hour": 7, "minute": 0},
                "wed": {"enabled": False, "hour": 7, "minute": 0},
                "thu": {"enabled": False, "hour": 7, "minute": 0},
                "fri": {"enabled": False, "hour": 7, "minute": 0},
                "sat": {"enabled": False, "hour": 7, "minute": 0},
                "sun": {"enabled": False, "hour": 7, "minute": 0}
            },
            "alarm_sound": {
                "tone": "classic",
                "volume": 70
            },
            "buzzer": {
                "volume": 500,
                "duration": 60
            },
            "display": {
                "type": "SH1106",
                "width": 128,
                "height": 64
            },
            "weather": {
                "enabled": True,
                "place": "Zevenaar",
                "latitude": 51.92,
                "longitude": 6.08,
                "interval_s": 1800
            }
        }

    def _recover_config_file(self, config_data):
        """Herstel config-bestand na ontbrekende of corrupte JSON."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config_data, f)
            print(f"✓ {self.config_file} hersteld")
            return True
        except Exception as e:
            print(f"⚠ Kon {self.config_file} niet herstellen: {e}")
            return False
    
    def print_config(self):
        """Print alle instellingen"""
        print("\n=== CONFIGURATIE ===")
        for section, settings in self.config.items():
            print(f"\n[{section.upper()}]")
            if isinstance(settings, dict):
                for key, value in settings.items():
                    print(f"  {key}: {value}")
            else:
                print(f"  {settings}")
        print()
