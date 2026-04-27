# Bluetooth vs WiFi - Snelle Setup Guide

## 🔵 BLUETOOTH Setup (Aanbevolen voor Mobiel)

### Hardware Setup (zelfde als standaard)
- OLED Display op I2C (GPIO21/22)
- DS3231 RTC op I2C (GPIO21/22)
- Knoppen op GPIO13, GPIO12, GPIO14
- Buzzer op GPIO27

### Software Setup
1. **Upload naar ESP32:**
   ```bash
   esptool.py --port COM3 write_flash 0x0 alarm_clock_ble.py
   # Of via Thonny: Bestand → Opslaan op apparaat
   ```

2. **BLE App installeren (GRATIS):**
   - **Android:** "nRF Connect" (Nordic Semiconductor)
   - **iOS:** "nRF Connect" of "Bluetooth Terminal"

3. **Verbinding maken:**
   ```
   1. Open nRF Connect app
   2. Zoek naar "AlarmClock"
   3. Tik op CONNECT
   4. Je ziet 3 services verschijnen
   ```

4. **Tijd instellen:**
   ```
   1. Klik op eerste UUID (TIME characteristic)
   2. Klik op "Write"
   3. Voer in: 13:45 (voor 13:45)
   4. Klik SEND
   ```

5. **Alarm instellen:**
   ```
   1. Klik op tweede UUID (ALARM characteristic)
   2. Klik op "Write"
   3. Voer in: 07:00 (voor 07:00)
   4. Klik SEND
   ```

### Voordelen:
- ✅ 1 knop: Alarm stoppen (SET knop fysiek)
- ✅ APP werkt tot 100m afstand
- ✅ Lage batterijverbruik (ideal voor batterij-powered)
- ✅ Werkt offline (geen Internet nodig)

---

## 📱 WIFI Setup (Aanbevolen voor Computer + Mobiel)

### Hardware Setup (zelfde als standaard)
- OLED Display op I2C (GPIO21/22)
- DS3231 RTC op I2C (GPIO21/22)
- Knoppen op GPIO13, GPIO12, GPIO14
- Buzzer op GPIO27

### Software Setup
1. **Upload naar ESP32:**
   ```bash
   esptool.py --port COM3 write_flash 0x0 alarm_clock_wifi.py
   # Of via Thonny: Bestand → Opslaan op apparaat
   ```

2. **Verbinding maken (Telefoon):**
   ```
   1. Ga naar WiFi Instellingen
   2. Zoek naar netwerk "AlarmClock"
   3. Wachtwoord: 123456789
   4. Verbinden
   ```

3. **Webpagina openen:**
   ```
   Browser adres: http://192.168.4.1
   ```

4. **Tijd instellen:**
   ```
   1. Selecteer tijd in "Huidige Tijd Instellen"
   2. Klik "Stel Tijd In"
   ```

5. **Alarm instellen:**
   ```
   1. Selecteer alarm tijd in "Alarm Tijd"
   2. Klik "Stel Alarm In"
   ```

### Voordelen:
- ✅ Mooie web interface
- ✅ Desktop + mobiel tegelijk
- ✅ Geen app nodig (gewone browser)
- ✅ Instelscherm ziet er professioneel uit

---

## ⚠️ IMPORTANT: Verschillen in Gebruik

### Knoppen bijhouden (beide versies)
```
Knop          Functie
UP (GPIO13)   (niet gebruikt in BLE/WiFi)
DOWN (GPIO12) (niet gebruikt in BLE/WiFi)
SET (GPIO14)  STOP ALARM (in beide versies!)
```

### Alarm stoppen
```
Bluetooth: SET knop + via nRF app
WiFi:      SET knop + via browser
Standaard: SET knop
```

---

## 🔌 WiFi Netwerk Details

### Access Point (Hotspot)
```
SSID:       AlarmClock
Wachtwoord: 123456789
IP-adres:   192.168.4.1
Poort:      80
```

### Webpagina's
```
GET  /              → HTML pagina
GET  /api/time      → JSON {"hour": 13, "minute": 45, ...}
POST /api/set-time  → Stel tijd in
POST /api/set-alarm → Stel alarm in
```

---

## 📡 BLE Netwerk Details

### Service UUID
```
12345678-1234-5678-1234-56789abcdef0
```

### Characteristics
```
TIME:    12345678-1234-5678-1234-56789abcdef1
ALARM:   12345678-1234-5678-1234-56789abcdef2
STATUS:  12345678-1234-5678-1234-56789abcdef3
```

### Schrijfformat
```
TIME char:   "HH:MM" → "13:45"
ALARM char:  "HH:MM" → "07:00"
STATUS char: Read-only, bijv: "T:13:45 A:07:00"
```

---

## 🔧 Troubleshooting

### Bluetooth
```
Problem: "AlarmClock" verschijnt niet
→ Check: Display laat "BLE [WACHT]" zien?
→ Reset ESP32 en upload opnieuw
→ Zorg OLED + RTC werken (hardware check)

Problem: "Write" knop grayed out
→ Handmatig hexadecimale waarde invoeren
→ Of app sluiten en opnieuw proberen
```

### WiFi
```
Problem: "AlarmClock" netwerk zichtbaar, geen verbinding
→ Wachtwoord typo checken
→ Probeer: 123456789 (9 digits)
→ Reset ESP32

Problem: http://192.168.4.1 laadt niet
→ Zorg verbonden met "AlarmClock" netwerk
→ Probeer IP in adresbalk opnieuw
→ Wacht 5 seconden na verbinding
```

---

## 💡 Quando kiezen?

**Bluetooth kiezen als:**
- Je alleen op mobiel wilt instellen
- Je batterij-powered system wilt
- Je offline wilt werken
- Je niet veel geek-setup wilt

**WiFi kiezen als:**
- Je mooie interface wilt
- Je van computer + mobiel tegelijk wilt instellen
- Je meer bereik wilt
- Je guests ook wilt laten instellen

**Standaard (knoppen) kiezen als:**
- Je altijd fysiek bij de ESP32 bent
- Je geen draadloze setup wilt
- Je maximale batterijduur wilt
