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

    def set_wifi_credentials(self, ssid, password, keep_alive=None):
        """Sla WiFi-gegevens op in de config."""
        try:
            defaults = self._get_defaults().get("wifi", {})
            wifi = self.config.setdefault("wifi", {})
            wifi["mode"] = wifi.get("mode", defaults.get("mode", "sta"))
            wifi["ssid"] = str(ssid or "").strip()
            wifi["password"] = str(password or "")
            wifi["channel"] = int(wifi.get("channel", defaults.get("channel", 6)) or 6)
            if keep_alive is not None:
                wifi["keep_alive"] = bool(keep_alive)
            elif "keep_alive" not in wifi:
                wifi["keep_alive"] = bool(defaults.get("keep_alive", False))
            if wifi["ssid"] and wifi["ssid"] != defaults.get("ssid", ""):
                wifi["custom_profile"] = {
                    "ssid": wifi["ssid"],
                    "password": wifi["password"],
                    "channel": wifi["channel"],
                    "keep_alive": wifi["keep_alive"],
                }
            return self.save()
        except Exception as e:
            print(f"✗ Fout bij opslaan WiFi-gegevens: {e}")
            return False

    def toggle_wifi_profile(self):
        """Wissel tussen default WiFi en laatst opgeslagen custom WiFi-profiel."""
        try:
            defaults = dict(self._get_defaults().get("wifi", {}))
            wifi = self.config.setdefault("wifi", {})
            current_ssid = str(wifi.get("ssid", "") or "").strip()
            current_password = str(wifi.get("password", "") or "")
            current_channel = int(wifi.get("channel", defaults.get("channel", 6)) or 6)
            current_keep_alive = bool(wifi.get("keep_alive", defaults.get("keep_alive", False)))

            custom = wifi.get("custom_profile", {})
            custom_ssid = str(custom.get("ssid", "") or "").strip()
            custom_password = str(custom.get("password", "") or "")
            custom_channel = int(custom.get("channel", defaults.get("channel", 6)) or defaults.get("channel", 6) or 6)
            custom_keep_alive = bool(custom.get("keep_alive", current_keep_alive))

            default_ssid = str(defaults.get("ssid", "") or "").strip()
            default_password = str(defaults.get("password", "") or "")
            default_channel = int(defaults.get("channel", 6) or 6)
            default_keep_alive = bool(defaults.get("keep_alive", False))

            current_is_default = (current_ssid == default_ssid and current_password == default_password)

            if current_is_default:
                if not custom_ssid:
                    return {"ok": False, "error": "Geen opgeslagen custom WiFi-profiel"}
                wifi["ssid"] = custom_ssid
                wifi["password"] = custom_password
                wifi["channel"] = custom_channel
                wifi["keep_alive"] = custom_keep_alive
                target = "custom"
            else:
                if current_ssid:
                    wifi["custom_profile"] = {
                        "ssid": current_ssid,
                        "password": current_password,
                        "channel": current_channel,
                        "keep_alive": current_keep_alive,
                    }
                wifi["ssid"] = default_ssid
                wifi["password"] = default_password
                wifi["channel"] = default_channel
                wifi["keep_alive"] = default_keep_alive
                target = "default"

            if not self.save():
                return {"ok": False, "error": "Config opslaan mislukt"}
            return {"ok": True, "target": target, "ssid": wifi.get("ssid", "")}
        except Exception as e:
            print(f"✗ Fout bij wisselen WiFi-profiel: {e}")
            return {"ok": False, "error": str(e)}

    def reset_wifi_to_defaults(self):
        """Zet WiFi terug naar veilige project-defaults."""
        try:
            self.config["wifi"] = dict(self._get_defaults().get("wifi", {}))
            return self.save()
        except Exception as e:
            print(f"✗ Fout bij resetten WiFi-defaults: {e}")
            return False
    
    def _get_defaults(self):
        """Standaard instellingen"""
        return {
            "wifi": {
                "mode": "sta",
                "ssid": "",
                "password": "",
                "channel": 6,
                "keep_alive": False
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
            "ui": {
                "language": "nl"
            },
            "weather": {
                "enabled": True,
                "place": "Zevenaar",
                "latitude": 51.92,
                "longitude": 6.08,
                "interval_s": 21600,
                "updates_per_day": 4
            },
            "update": {
                "auto_update_enabled": False,
                "manifest_url": "https://sjorsansems.github.io/retro-alarm-clock/updates/stable/manifest.json",
                "check_interval_hours": 24
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
