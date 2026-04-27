# Alarmklok Versies - WiFi vs Bluetooth

Je hebt nu **3 versies** van de alarmklok:

## 1️⃣ **alarm_clock.py** - Standaard versie (Alleen knoppen)
**Geschikt voor:** Basis setup met fysieke knoppen
- Geen WiFi/Bluetooth
- Tijd instellen via UP/DOWN/SET knoppen
- Klein energieverbruik
- Geen extra modules nodig

---

## 2️⃣ **alarm_clock_ble.py** - Bluetooth (BLE)
**Geschikt voor:** Controle via smartphone via Bluetooth

### Voordelen:
✅ Lage stroomverbruik  
✅ Geen WiFi netwerk nodig  
✅ Groot bereik (10-100m)  
✅ Snelle verbinding  
✅ Privacy-vriendelijk (geen Internet)  

### Nadelen:
❌ Moet speciale BLE-app op telefoon installeren  
❌ Alleen één telefoon tegelijk  

### Hoe te gebruiken:
```
1. Upload alarm_clock_ble.py naar ESP32
2. Download "nRF Connect" app (Android/iOS) GRATIS
3. Verbind met "AlarmClock"
4. Schrijf naar characteristics:
   - TIME: "13:45" (instellen huidige tijd)
   - ALARM: "07:00" (instellen alarm)
```

---

## 3️⃣ **alarm_clock_wifi.py** - WiFi Web Interface
**Geschikt voor:** Controle via browser op je telefoon/PC

### Voordelen:
✅ Makkelijk via web browser  
✅ Mooie interface  
✅ Desktop + mobiel  
✅ Geen speciale app nodig  
✅ Multiple devices tegelijk  

### Nadelen:
❌ Hoger stroomverbruik  
❌ Hotspot modus (geen Internet op andere devices)  
❌ WiFi signaal kan zwakker zijn  

### Hoe te gebruiken:
```
1. Upload alarm_clock_wifi.py naar ESP32
2. ESP32 maakt WiFi netwerk: "AlarmClock"
3. Wachtwoord: "123456789"
4. Open browser → http://192.168.4.1
5. Stel tijd/alarm in via webpagina
```

---

## 🎯 Welke versie kiezen?

| Feature | Standaard | Bluetooth | WiFi |
|---------|-----------|-----------|------|
| Eenvoudig | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Bereik | Geen | 50-100m | 10-50m |
| App nodig | Nee | Ja | Nee (browser) |
| Stroomverbruik | Laag | Laag | Hoog |
| Telefoon app | Nee | JA (nRF) | Web browser |

### 🏆 Aanbeveling:
- **Bluetooth**: Best voor energiebesparing + mobiel controle
- **WiFi**: Best voor gebruiksgemak + mooie interface
- **Standaard**: Goedkoop + betrouwbaar

---

## 📝 Extra: Bluetooth App Alternatieven

In plaats van "nRF Connect" kun je ook deze apps gebruiken:
- **iOS**: "Bluetooth Terminal" door Kyan Wang
- **Android**: "Bluetooth Electronics" door Kai Morich
- **Android**: "Serial Bluetooth Terminal" door Kai Morich

---

## 🔧 BLE Characteristic Format

Als je een custom BLE app maakt:

### TIME Characteristic (Write)
- Format: "HH:MM" (bijv. "13:45")
- Length: 5 bytes
- Voorbeeld: Schrijf "07:30" om tijd in te stellen

### ALARM Characteristic (Write)
- Format: "HH:MM" (bijv. "07:00")
- Length: 5 bytes
- Voorbeeld: Schrijf "06:45" om alarm in te stellen

### STATUS Characteristic (Read/Notify)
- Format: "T:HH:MM A:HH:MM"
- Voorbeeld: "T:13:45 A:07:00"
- Auto-update elke seconde

---

## 💾 Bestanden

Alle configuratie wordt opgeslagen in `alarm_config.json`:

```json
{
    "alarm_enabled": true,
    "alarm_hour": 7,
    "alarm_minute": 0,
    "buzzer_volume": 500
}
```

Je kunt dit handmatig aanpassen via REPL:
```python
import json
config = {"alarm_enabled": True, "alarm_hour": 6, "alarm_minute": 30, "buzzer_volume": 600}
with open("alarm_config.json", "w") as f:
    json.dump(config, f)
```
