# ESP32 Alarmklok - Setup Guide

## 📌 Hardware Verbindingen

### ESP32 Pinout Overzicht

| ESP32 Pin | Gebruik | Component | Opmerking |
|---|---|---|---|
| GPIO8 | I2C SDA | OLED (SH1106) | I2C bus voor display |
| GPIO9 | I2C SCL | OLED (SH1106) | I2C bus voor display |
| GPIO5 | I2C SDA | DS3231 RTC | Aparte I2C bus voor RTC |
| GPIO6 | I2C SCL | DS3231 RTC | Aparte I2C bus voor RTC |
| GPIO13 | Knop UP (SET) | Bedieningsknop | Ingang met pull-up, knop naar GND |
| GPIO12 | Knop DOWN (ALARM) | Bedieningsknop | Ingang met pull-up, knop naar GND |
| GPIO14 | Knop SET | Bedieningsknop | Ingang met pull-up, knop naar GND |
| GPIO17 | UART1 TX | DFPlayer Mini RX | Via 1k ohm serieweerstand |
| GPIO18 | UART1 RX | DFPlayer Mini TX | Direct verbinden |
| GPIO27 | Buzzer + | Buzzer/Speaker | Niet gebruikt in huidige versie |
| GPIO2 | LED data | WS2812 (NeoPixel) | Bitstream, byte-order GRB |
| 3.3V | Voeding + | OLED + DS3231 | Gebruik 3.3V, niet 5V |
| GND | Massa | Alle modules | Gemeenschappelijke ground |

Niet gebruikt in deze basissetup: alle overige GPIO's.

### OLED Display (I2C - 1.3" SH1106)
```
OLED Pin    ESP32 Pin
GND         GND
VCC         3.3V
SCL         GPIO9 (SCL)
SDA         GPIO8 (SDA)
```

### DS3231 RTC Module (I2C - Real-Time Clock)
```
RTC Pin     ESP32 Pin
GND         GND
VCC         3.3V
SCL         GPIO6 (SCL)  [Aparte I2C bus voor RTC]
SDA         GPIO5 (SDA)
```

### DFPlayer Mini (MP3 Player - UART)
```
DFPlayer Pin   ESP32 Pin
VCC            5V (aanbevolen) of 3.3V
GND            GND
RX             GPIO17 (UART1 TX) via 1kΩ weerstand
TX             GPIO18 (UART1 RX)
BUSY           Optioneel naar vrije GPIO (nu niet gebruikt)
SPK_1/SPK_2    Naar speaker
```

Opmerking: in de huidige code is `busy_pin=None`, dus de BUSY-lijn hoeft niet aangesloten te zijn.

### Knoppen (Pull-Up schakelaars)
```
Knop         ESP32 Pin    Functie
UP (SET)     GPIO13       Uur omhoog / Tijd modus
DOWN (ALARM) GPIO12       Minuut omhoog / Alarm modus
SET          GPIO14       Bevestigen / Alarm stoppen
```
Verbind de andere pin van elke knop met GND.

### Buzzer/Speaker (optioneel, legacy)
```
Buzzer Pin   ESP32 Pin
+ (Pos)      GPIO27 (via 330Ω weerstand)
- (Neg)      GND
```
In de huidige versie wordt de buzzer niet gebruikt; het alarm loopt via DFPlayer MP3.

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

Als het OLED/RTC niet detecteert wordt, voeg 4.7kΩ pull-up weerstanden toe op de gebruikte bus(sen):
- OLED bus: GPIO8 (SDA) naar 3.3V en GPIO9 (SCL) naar 3.3V
- RTC bus: GPIO5 (SDA) naar 3.3V en GPIO6 (SCL) naar 3.3V

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
- DS3231 gebruikt een aparte I2C bus (GPIO5/GPIO6)

### Knoppen reageren niet
- Controleer GPIO pinnen in code (GPIO13, GPIO12, GPIO14)
- Zorg dat GND verbinding goed zit
- Controleer debounce delay (200ms) - pas aan indien nodig

### MP3/DFPlayer speelt geen geluid
- Controleer UART wiring: GPIO17 -> DFPlayer RX (met 1kΩ), GPIO18 <- DFPlayer TX
- Controleer voeding van DFPlayer (liefst 5V) en gedeelde GND
- Controleer SD-kaart en bestandsnamen (`/MP3/0001.mp3`, etc.)
- Controleer speaker op `SPK_1`/`SPK_2`

## 🌈 LED Thema Kleurschema (per spel)

Bevestigde werkende WS2812 setup:
- Data pin: GPIO2
- Methode: bitstream
- Byte-order: GRB

Kleurschema per lied/spel:

1. Zelda
- Groen naar goud pulse
- R 0..200, G 200..255, B 0

2. Mario
- Rood en geel checker-patroon
- (255,0,0) en (255,255,0)

3. Synthwave
- Neon roze naar paars golf
- (255,0,100) naar (150,0,255)

4. Sonic
- Cyaan/blauw strobe
- (0,200..250,255) en (0,100,200)

5. Metroid
- Oranje naar rood (intensiteit-gedreven)
- R 255 vast, G 200..100, B 0

6. Pokemon
- Geel met rode accenten, knipperend
- (255,255,0) en (255,0,0)

7. Tetris
- Regenboogcyclus
- Rood -> oranje -> geel -> groen -> blauw -> indigo -> violet

8. Moonstone
- Maanblauw met fakkel-gouden pulse
- Basis ongeveer (40,80,180) met warme fakkel-accenten

9. Arcade
- Multicolor strobe
- Rood -> geel -> groen -> blauw -> magenta
