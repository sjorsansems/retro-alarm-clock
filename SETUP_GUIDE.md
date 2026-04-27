# ESP32 Alarmklok - Setup Guide

## 📌 Hardware Verbindingen

### OLED Display (I2C - 1.3" SH1106)
```
OLED Pin    ESP32 Pin
GND         GND
VCC         3.3V
SCL         GPIO22 (SCL)
SDA         GPIO21 (SDA)
```

### DS3231 RTC Module (I2C - Real-Time Clock)
```
RTC Pin     ESP32 Pin
GND         GND
VCC         3.3V
SCL         GPIO22 (SCL)  [Dezelfde I2C bus als OLED]
SDA         GPIO21 (SDA)
```

### Knoppen (Pull-Up schakelaars)
```
Knop         ESP32 Pin    Functie
UP (SET)     GPIO13       Uur omhoog / Tijd modus
DOWN (ALARM) GPIO12       Minuut omhoog / Alarm modus
SET          GPIO14       Bevestigen / Alarm stoppen
```
Verbind de andere pin van elke knop met GND.

### Buzzer/Speaker (optioneel)
```
Buzzer Pin   ESP32 Pin
+ (Pos)      GPIO27 (via 330Ω weerstand)
- (Neg)      GND
```

## 🎯 Bedieningsinterface

### Display Mode (Standaard)
```
┌─────────────────┐
│     11:34       │
│       12s       │
│                 │
│ ALARM: 07:00    │
│ UP=TIJD DOWN=AL │
└─────────────────┘
```
- **UP knop**: Ga naar TIJD INSTELLEN modus
- **DOWN knop**: Ga naar ALARM INSTELLEN modus

### Tijd Instellen Mode
```
┌─────────────────┐
│  STEL TIJD IN   │
│                 │
│     13:45       │
│                 │
│ UP=UUR DOWN=MIN │
│ SET=OPSLAAN     │
└─────────────────┘
```
- **UP knop**: Verhoog uur (00-23)
- **DOWN knop**: Verhoog minuut (00-59)
- **SET knop**: Sla tijd op en terug naar display

### Alarm Instellen Mode
```
┌─────────────────┐
│  STEL ALARM IN  │
│                 │
│     07:00       │
│                 │
│ UP=UUR DOWN=MIN │
│ SET=OPSLAAN     │
└─────────────────┘
```
- **UP knop**: Verhoog alarm uur (00-23)
- **DOWN knop**: Verhoog alarm minuut (00-59)
- **SET knop**: Sla alarm op en terug naar display

### Alarm Afgaande
```
┌─────────────────┐
│                 │
│  ALARM AFGAAN!  │
│                 │
│ SET = UITZETTEN │
│                 │
└─────────────────┘
```
- **SET knop**: Stop de alarm buzz

## ⚙️ Instellingen (alarm_config.json)

De instellingen worden automatisch opgeslagen in `alarm_config.json`:

```json
{
    "alarm_enabled": true,
    "alarm_hour": 7,
    "alarm_minute": 0,
    "alarm_days": [1, 2, 3, 4, 5],
    "buzzer_volume": 500
}
```

- `alarm_enabled`: true/false - alarm aan/uit
- `alarm_hour`: 0-23 - uur van het alarm
- `alarm_minute`: 0-59 - minuut van het alarm
- `alarm_days`: Weekdagen [1=ma, 2=di, ..., 7=zo]
- `buzzer_volume`: PWM frequentie (250-1000 Hz)

## 🔧 I2C Pull-Up Weerstanden

Als het OLED/RTC niet detecteert wordt, voeg 4.7kΩ pull-up weerstanden toe:
- Van GPIO21 (SDA) naar 3.3V
- Van GPIO22 (SCL) naar 3.3V

## 📝 Eerste Start

1. Zet alle hardware aan
2. Upload `alarm_clock.py` naar ESP32 (via Thonny of esptool)
3. Het OLED scherm toont de huidige tijd (eerst standaard 00:00)
4. Druk **UP** om de huidige tijd in te stellen
5. Druk **DOWN** om het alarm in te stellen
6. Het alarm gaat af wanneer de huidige tijd het alarm uur/minuut bereikt

## 🐛 Troubleshooting

### OLED niet detecteert
- Controleer de I2C verbindingen (SDA/SCL)
- Zet pull-up weerstanden (4.7kΩ) toe op SDA en SCL
- Probeer I2C adres handmatig in code aan te passen

### DS3231 RTC niet detecteert
- Controleer voeding (3.3V)
- Zet pull-up weerstanden toe
- DS3231 delen dezelfde I2C bus als OLED (adressen verschillen)

### Knoppen reageren niet
- Controleer GPIO pinnen in code (GPIO13, GPIO12, GPIO14)
- Zorg dat GND verbinding goed zit
- Controleer debounce delay (200ms) - pas aan indien nodig

### Buzzer maakt geen geluid
- Controleer GPIO27 wiring
- Zorg voor 330Ω weerstand tussen GPIO27 en buzzer+
- Pas `buzzer_volume` aan in code (250-1000 Hz)
